"""Multi-video knowledge base service: list videos, retrieve across all of them, answer with citations."""
import base64
import hashlib
import hmac
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import time

import numpy as np
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "kb.db"

if sys.stdout is None:  # running under pythonw (no console)
    (ROOT / "data" / "logs").mkdir(parents=True, exist_ok=True)
    sys.stdout = open(ROOT / "data" / "logs" / "server.out", "a", encoding="utf-8")
    sys.stderr = sys.stdout
CFG = json.loads((ROOT / "config.local.json").read_text(encoding="utf-8"))
API_KEY = CFG["api_key"]
BASE_URL = CFG.get("base_url", "https://api.deepseek.com").rstrip("/")
MODEL = CFG.get("model", "deepseek-chat")
AUTH = CFG.get("auth") or {}
SECRET = (CFG.get("secret") or "kb-dev-secret").encode()
COOKIE = "kb_session"
MAX_AGE = 7 * 24 * 3600


def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS qa_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT,
        cites TEXT,
        weak_count INTEGER DEFAULT 0,
        rating INTEGER,
        created_at TEXT
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_qa_created ON qa_logs(created_at)")
    con.commit()
    con.close()


init_db()
PUNCT = re.compile(r"[^\w\u4e00-\u9fff]+")
FILE_MIME = {".mp4": "video/mp4", ".mkv": "video/x-matroska", ".mov": "video/quicktime",
             ".webm": "video/webm", ".avi": "video/x-msvideo", ".flv": "video/x-flv",
             ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
             ".jpeg": "image/jpeg", ".webp": "image/webp", ".bmp": "image/bmp",
             ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
             ".aac": "audio/aac", ".flac": "audio/flac", ".ogg": "audio/ogg",
             ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
             ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

_cache = {"mtime": 0, "videos": {}, "segs": [], "df": {}, "avgdl": 0}
_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        from embeddings import Embedder
        _embedder = Embedder()
    return _embedder


def mmss(sec):
    s = int(sec or 0)
    return f"{s // 60:02d}:{s % 60:02d}"


def toks(text):
    s = PUNCT.sub("", text or "")
    if len(s) < 2:
        return [s] if s else []
    return [s[i:i + 2] for i in range(len(s) - 1)]


_doc_cache = {}


def _chunk_doc(rows):
    """把一份文档的句子拼成 ~500 字块（不跨文档）。"""
    chunks, buf = [], []
    for r in rows:
        buf.append(r)
        if sum(len(x["text"]) for x in buf) >= 500:
            chunks.append(buf)
            buf = [buf[-1]]  # 1 句重叠
    if buf:
        chunks.append(buf)

    out = []
    for c in chunks:
        text = "。".join(x["text"].strip("。") for x in c)
        locator = c[0]["locator"] or mmss(c[0]["start"])
        page = int(str(locator)[1:]) if str(locator).startswith("p") and str(locator)[1:].isdigit() else None
        vecs = [np.frombuffer(x["embedding"], dtype=np.float32) for x in c if x["embedding"]]
        vec = None
        if vecs:
            vec = np.mean(vecs, axis=0)
            n = float(np.linalg.norm(vec))
            vec = (vec / n).astype(np.float32) if n > 1e-8 else None
        out.append({"video_id": c[0]["video_id"], "start": c[0]["start"], "end": c[-1]["end"],
                    "seq_start": c[0]["seq"], "seq_end": c[-1]["seq"],
                    "text": text, "locator": str(locator), "page": page, "tk": toks(text), "vec": vec})
    return out


def load_index(force=False):
    """增量索引：只重建内容变化过的文档，问答日志写入不影响缓存。"""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    sig = (tuple(con.execute("SELECT COUNT(1), COALESCE(MAX(updated_at),'') FROM videos "
                             "WHERE deleted_at IS NULL").fetchone()),
           tuple(con.execute("SELECT COUNT(1), COALESCE(MAX(id),0) FROM segments").fetchone()))
    if not force and sig == _cache.get("sig") and _cache["segs"]:
        con.close()
        return _cache

    videos = {}
    for r in con.execute(
            "SELECT v.id,v.name,v.duration,v.summary,v.outline_json,v.path,v.kind,v.pages,"
            "v.course,v.updated_at,"
            "(SELECT COUNT(1) FROM segments s WHERE s.video_id=v.id) AS seg_n,"
            "(SELECT COALESCE(MAX(id),0) FROM segments s WHERE s.video_id=v.id) AS seg_mx "
            "FROM videos v WHERE v.status='ready' AND v.deleted_at IS NULL"):
        videos[r["id"]] = dict(r)

    for vid in list(_doc_cache):
        if vid not in videos:
            _doc_cache.pop(vid, None)

    changed = [vid for vid, v in videos.items()
               if force or vid not in _doc_cache
               or _doc_cache[vid]["sig"] != (v["updated_at"], v["seg_n"], v["seg_mx"])]
    if changed:
        rows = con.execute(
            "SELECT video_id,seq,start,end,text,locator,embedding FROM segments WHERE video_id IN "
            f"({','.join('?' * len(changed))}) ORDER BY video_id,seq", changed).fetchall()
        by_doc = {}
        for r in rows:
            by_doc.setdefault(r["video_id"], []).append(r)
        for vid in changed:
            v = videos[vid]
            _doc_cache[vid] = {"sig": (v["updated_at"], v["seg_n"], v["seg_mx"]),
                               "chunks": _chunk_doc(by_doc.get(vid, []))}
    con.close()

    segs = []
    for vid in sorted(_doc_cache):
        segs.extend(_doc_cache[vid]["chunks"])

    df = {}
    for s in segs:
        for t in set(s["tk"]):
            df[t] = df.get(t, 0) + 1
    _cache.update(mtime=hash(tuple(sorted(videos))), sig=sig, videos=videos, segs=segs, df=df,
                  avgdl=(sum(len(s["tk"]) for s in segs) / len(segs)) if segs else 0)
    return _cache


def bm25(queries, limit=6, segs=None):
    idx = load_index()
    docs = idx["segs"] if segs is None else segs
    if not docs:
        return []
    n, avgdl = len(docs), idx["avgdl"] or 1
    k1, b = 1.5, 0.75
    term_sets = [list(dict.fromkeys(toks(q))) for q in queries if q]
    term_sets = [t for t in term_sets if t]
    if not term_sets:
        return []

    scored = []
    for s in docs:
        tf = {}
        for t in s["tk"]:
            tf[t] = tf.get(t, 0) + 1
        dl = len(s["tk"])
        best = 0.0
        for terms in term_sets:
            score = 0.0
            for t in terms:
                f = tf.get(t, 0)
                if not f:
                    continue
                idf = math.log(1 + (n - idx["df"].get(t, 0) + 0.5) / (idx["df"].get(t, 0) + 0.5))
                score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
            compact = PUNCT.sub("", " ".join(queries))
            if compact and compact in PUNCT.sub("", s["text"]):
                score *= 1.5
            best = max(best, score)
        if best > 0:
            scored.append((best, s))
    scored.sort(key=lambda x: -x[0])

    picked = []
    for score, s in scored[:limit]:
        picked.append((score, s))
    return picked


def expand_query(question):
    """让模型把问题改写成几条检索式，弥补关键词匹配的短板。"""
    try:
        r = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL,
                  "messages": [{"role": "system",
                                "content": "把用户问题改写成 3 条中文检索式（补同义词、实体、口语说法），"
                                           "只输出 JSON 数组，例如 [\"私域流量来源\", ...]"},
                               {"role": "user", "content": question}],
                  "temperature": 0, "max_tokens": 120},
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        start, end = text.find("["), text.rfind("]")
        if start >= 0:
            arr = json.loads(text[start:end + 1])
            return [str(x) for x in arr][:4]
    except Exception:
        pass
    return []


SYSTEM = """你是「企业知识库」助手，服务于没时间看原始材料的人。只能依据给定【片段】回答。

规则：
1. 只使用片段中的信息，不用片段之外的事实。
2. 可以对片段做归纳和因果推断（例如从多次交易推测"硬通货"的含义），但结论必须能在片段里找到依据，并标注 [n]。
3. 引用要克制：每个事实性陈述只标**最相关的一个**编号，最多两个；不要一句话挂一串编号，也不要为同一句话重复引用相邻片段。
4. 不得编造时间戳、数字、人名。
5. 先给结论（1-3 句），再给 2-4 条要点。
6. 只有在片段完全没有相关内容时，才说"资料中没有提到"。
7. 问题涉及多个视频时，分别说明各自的说法，不要混为一谈。
8. 【视频目录】是每个视频的摘要，可用于回答"分别讲了什么"这类概览问题；具体细节仍必须来自【片段】。
9. 用简体中文，不要大段复述原文。"""


RERANK_SYSTEM = """你是检索重排器。判断每个片段与问题的相关性。
输出严格 JSON：{"scores":[{"n":1,"score":0},{"n":2,"score":7}]}
score 取 0-10：10 表示片段直接回答了问题，0 表示完全无关。只输出 JSON。"""


def rerank(question, ranked, keep=6):
    """Use the LLM to reorder fused candidates; fall back to the original order."""
    if len(ranked) <= keep:
        return ranked
    lines = [f"[{i}] {s['text'][:120].replace(chr(10), ' ')}" for i, (_, s) in enumerate(ranked, 1)]
    user = f"【问题】{question}\n\n【片段】\n" + "\n".join(lines)
    try:
        r = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL,
                  "messages": [{"role": "system", "content": RERANK_SYSTEM},
                               {"role": "user", "content": user}],
                  "temperature": 0, "max_tokens": 400},
            timeout=40,
        )
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"]
        a, b = txt.find("{"), txt.rfind("}")
        scores = {int(x["n"]): float(x.get("score", 0))
                  for x in json.loads(txt[a:b + 1]).get("scores", [])}
        order = sorted(range(1, len(ranked) + 1),
                       key=lambda i: (-scores.get(i, 0), i))
        return [ranked[i - 1] for i in order[:keep]]
    except Exception:
        return ranked[:keep]


def log_qa(question, answer, cites):
    try:
        con = sqlite3.connect(DB)
        weak = sum(1 for c in cites if c.get("weak"))
        cur = con.execute(
            "INSERT INTO qa_logs(question,answer,cites,weak_count,created_at) "
            "VALUES(?,?,?,?,datetime('now','localtime'))",
            (question, answer, json.dumps(cites, ensure_ascii=False), weak))
        con.commit()
        log_id = cur.lastrowid
        con.close()
        return log_id
    except Exception:
        return None


def trim_citations(text, max_per_sentence=2):
    """一句话挂太多编号时，只保留最靠前的几个（编号越小召回排名越高）。"""
    def fix(sentence):
        nums = re.findall(r"\[(\d+)\]", sentence)
        if len(set(nums)) <= max_per_sentence:
            return sentence
        keep = set(sorted({int(n) for n in nums})[:max_per_sentence])
        out = sentence
        for n in set(nums):
            if int(n) not in keep:
                out = out.replace(f"[{n}]", "", 1)
        return out

    return re.sub(r"[^。！？\n]+[。！？]?", lambda m: fix(m.group(0)), text)


RRF_K = 10  # RRF 平滑常数：越小越看重头部排名


def ask(question, course=None, debug=False, mode="hybrid"):
    t0 = time.time()
    idx = load_index()
    t_load = time.time()
    queries = [question] + expand_query(question)
    t_expand = time.time()

    pool = idx["segs"]
    if course and course != "全部":
        pool = [s for s in pool if idx["videos"].get(s["video_id"], {}).get("course") == course]
    if not pool:
        msg = "这门课里还没有可检索的内容。"
        return {"answer": msg, "cites": [], "used": 0, "log_id": log_qa(question, msg, [])}

    bm_hits = bm25(queries, limit=30, segs=pool)
    t_bm = time.time()
    vec_hits = []
    best_sim = 0.0
    try:
        qv = get_embedder().encode([question])[0]
        scored = []
        for s in pool:
            if s.get("vec") is None:
                continue
            sim = float(s["vec"] @ qv)
            scored.append((sim, s))
        scored.sort(key=lambda x: -x[0])
        vec_hits = scored[:30]
        best_sim = scored[0][0] if scored else 0.0
    except Exception:
        vec_hits = []
    t_vec = time.time()
    bm_map = {id(s): sc for sc, s in bm_hits}
    vec_map = {id(s): sc for sc, s in vec_hits}

    if (not bm_hits or bm_hits[0][0] < 0.8) and best_sim < 0.42:
        msg = "资料中没有提到。可以换个说法，或先确认相关视频已经入库。"
        out = {"answer": msg, "cites": [], "used": 0, "log_id": log_qa(question, msg, [])}
        if debug:
            out["debug"] = {"retrieved": [], "timings": {
                "load_ms": round((t_load - t0) * 1000), "expand_ms": round((t_expand - t_load) * 1000),
                "bm25_ms": round((t_bm - t_expand) * 1000), "vec_ms": round((t_vec - t_bm) * 1000),
                "rerank_ms": 0, "answer_ms": 0, "total_ms": round((time.time() - t0) * 1000)},
                "refused": True}
        return out

    # RRF：关键词与语义两路各自排名，倒数求和
    fusion, pool = {}, {}
    for rank, (_, s) in enumerate(bm_hits):
        pool[id(s)] = s
        fusion[id(s)] = fusion.get(id(s), 0) + 0.7 / (RRF_K + rank)
    for rank, (_, s) in enumerate(vec_hits):
        pool[id(s)] = s
        fusion[id(s)] = fusion.get(id(s), 0) + 0.3 / (RRF_K + rank)
    ranked = sorted(fusion.items(), key=lambda kv: -kv[1])[:15]
    # 支持消融实验：bm25 / vector / hybrid（不重排）/ hybrid_rerank（默认）
    mode = (mode or "hybrid_rerank").lower()
    if mode == "bm25":
        hits = [(sc, s) for sc, s in bm_hits[:6]]
    elif mode == "vector":
        hits = [(sc, s) for sc, s in vec_hits[:6]]
    elif mode == "hybrid":
        hits = [(score, pool[k]) for k, score in ranked[:6]]
    else:
        # 分差明显时跳过低置信重排，省 1–1.5 秒；分差小才重排
        top = ranked[0][1] if ranked else 0
        second = ranked[1][1] if len(ranked) > 1 else 0
        clear_winner = second > 0 and top / max(second, 1e-9) > 1.5
        if clear_winner:
            hits = [(score, pool[k]) for k, score in ranked[:6]]
        else:
            hits = rerank(question, [(score, pool[k]) for k, score in ranked], keep=6)
    t_rerank = time.time()

    retrieved = []
    for rank, (score, s) in enumerate(hits, 1):
        v = idx["videos"].get(s["video_id"], {})
        retrieved.append({"rank": rank, "video_id": s["video_id"], "locator": s["locator"],
                          "start": s["start"], "end": s["end"],
                          "seq_start": s.get("seq_start"), "seq_end": s.get("seq_end"),
                          "kind": v.get("kind", "video"), "name": v.get("name", ""),
                          "bm25": round(bm_map.get(id(s), 0.0), 3),
                          "vec": round(vec_map.get(id(s), 0.0), 4),
                          "fused": round(float(score), 4)})

    # 命中块的上一块往往包含前因，补进来，避免“只看到结论看不到理由”
    chosen = {id(s): s for _, s in hits}
    for _, s in hits[:2]:
        prev = [c for c in idx["segs"]
                if c["video_id"] == s["video_id"] and c["start"] < s["start"]]
        if prev:
            chosen[id(prev[-1])] = prev[-1]
    ordered = sorted(chosen.values(), key=lambda c: (c["video_id"], c["start"]))

    lines, cites = [], []
    for i, s in enumerate(ordered, 1):
        v = idx["videos"].get(s["video_id"], {})
        kind = v.get("kind", "video")
        if kind == "pdf":
            where = f"第{s['page']}页" if s.get("page") else s["locator"]
        elif kind in ("docx", "image", "pptx", "xlsx"):
            where = s["locator"]
        else:
            where = f"{mmss(s['start'])}-{mmss(s['end'])}"
        lines.append(f"[{i}]《{v.get('name', '')}》 {where}\n{s['text']}")
        cites.append({"n": i, "video_id": s["video_id"], "name": v.get("name", ""),
                      "t": s["start"], "time": where, "kind": kind,
                      "page": s.get("page"), "locator": s["locator"],
                      "snippet": s["text"][:280], "full": s["text"]})

    parts = []
    for v in sorted(idx["videos"].values(), key=lambda x: x["id"]):
        if course and course != "全部" and (v.get("course") or "未分类") != course:
            continue
        meta = f"{v.get('pages') or 0} 页" if v.get("kind") == "pdf" else mmss(v["duration"])
        parts.append(f"- 《{v['name'].strip()}》（{meta}）：{(v.get('summary') or '').strip()[:110]}")
    catalog = "\n".join(parts)
    user = ("【视频目录】（用于概括每个视频的主题，可不用编号引用）\n" + catalog +
            "\n\n【片段】（具体细节必须引用这里的编号）\n" + "\n\n".join(lines) +
            f"\n\n【问题】\n{question}")
    r = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL,
              "messages": [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": user}],
              "temperature": 0.2, "max_tokens": 700},
        timeout=120,
    )
    r.raise_for_status()
    answer = r.json()["choices"][0]["message"]["content"].strip()
    answer = trim_citations(answer, 2)
    used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})

    # 引用校验：答案里引用该编号的句子，与片段文本的字面重合度太低，就标为“弱引用”
    sentences = [x for x in re.split(r"[。！？\n]", answer) if x.strip()]

    def support(n, passage):
        related = "".join(x for x in sentences if f"[{n}]" in x)
        if not related:
            return 1.0
        a, b = set(toks(related)), set(toks(passage))
        if not a:
            return 1.0
        return len(a & b) / len(a)

    picked = []
    for c in cites:
        c["weak"] = support(c["n"], c["full"]) < 0.1
        c.pop("full", None)
        if c["n"] in used:
            picked.append(c)
    result = {"answer": answer, "cites": picked, "used": len(hits),
              "log_id": log_qa(question, answer, picked)}
    if debug:
        t_end = time.time()
        result["debug"] = {"retrieved": retrieved, "timings": {
            "load_ms": round((t_load - t0) * 1000), "expand_ms": round((t_expand - t_load) * 1000),
            "bm25_ms": round((t_bm - t_expand) * 1000), "vec_ms": round((t_vec - t_bm) * 1000),
            "rerank_ms": round((t_rerank - t_vec) * 1000),
            "answer_ms": round((t_end - t_rerank) * 1000),
            "total_ms": round((t_end - t0) * 1000)},
            "refused": False}
    return result


def stats_payload():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    since = "datetime('now','-7 days','localtime')"
    total = con.execute("SELECT COUNT(*) n FROM qa_logs").fetchone()["n"]
    week = con.execute(f"SELECT COUNT(*) n FROM qa_logs WHERE created_at >= {since}").fetchone()["n"]
    up = con.execute("SELECT COUNT(*) n FROM qa_logs WHERE rating=1").fetchone()["n"]
    down = con.execute("SELECT COUNT(*) n FROM qa_logs WHERE rating=-1").fetchone()["n"]
    weak = con.execute("SELECT COALESCE(SUM(weak_count),0) n FROM qa_logs").fetchone()["n"]
    top = con.execute(f"SELECT question, COUNT(*) c FROM qa_logs WHERE created_at >= {since} "
                      "GROUP BY question ORDER BY c DESC LIMIT 10").fetchall()
    bad = con.execute("SELECT id, question, created_at FROM qa_logs WHERE rating=-1 "
                      "ORDER BY id DESC LIMIT 20").fetchall()
    missing = con.execute("SELECT id, question FROM qa_logs WHERE answer LIKE '%没有提到%' "
                          "ORDER BY id DESC LIMIT 10").fetchall()
    con.close()
    return {
        "total": total, "week": week, "up": up, "down": down, "weak": weak,
        "top": [dict(r) for r in top],
        "bad": [dict(r) for r in bad],
        "missing": [dict(r) for r in missing],
    }


def _placeholder_cover(course, out):
    try:
        from PIL import Image, ImageDraw, ImageFont

        palette = [(31, 78, 121), (47, 125, 79), (138, 90, 0), (91, 63, 130), (176, 48, 96)]
        color = palette[sum(course.encode("utf-8")) % len(palette)]
        img = Image.new("RGB", (640, 360), color)
        d = ImageDraw.Draw(img)
        try:
            f = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 64)
        except Exception:
            f = None
        d.text((32, 150), (course or "课程")[:6], font=f, fill="white")
        img.save(out, "JPEG", quality=82)
        return out
    except Exception:
        return None


def ensure_cover(course):
    """Grab a frame from the first video of a course; fall back to a colored placeholder."""
    import hashlib

    covers = ROOT / "data" / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    out = covers / (hashlib.md5(course.encode("utf-8")).hexdigest() + ".jpg")
    if out.exists() and out.stat().st_size > 1000:
        return out

    con = sqlite3.connect(DB)
    row = con.execute(
        "SELECT path FROM videos WHERE course=? AND kind='video' AND status='ready' "
        "AND deleted_at IS NULL AND path IS NOT NULL ORDER BY id LIMIT 1", (course,)).fetchone()
    con.close()
    if not row or not os.path.exists(row[0]):
        return _placeholder_cover(course, out)

    try:
        import av
        from PIL import Image

        with av.open(row[0]) as container:
            stream = container.streams.video[0]
            duration = float(container.duration / av.time_base) if container.duration else 60
            container.seek(int(duration * 0.15 * av.time_base), stream=stream)
            frame = next(container.decode(stream))
            img = frame.to_image().convert("RGB")
            img.thumbnail((640, 360))
            img.save(out, "JPEG", quality=82)
        return out
    except Exception:
        return _placeholder_cover(course, out)


def progress_payload():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT status, COUNT(*) n, COALESCE(SUM(duration),0) d "
                       "FROM videos WHERE deleted_at IS NULL GROUP BY status").fetchall()
    cur = con.execute("SELECT name,duration FROM videos WHERE status='transcribing' "
                      "AND deleted_at IS NULL ORDER BY id LIMIT 1").fetchone()
    con.close()
    stats = {r["status"]: {"n": r["n"], "hours": round((r["d"] or 0) / 3600, 2)} for r in rows}
    total = sum(s["n"] for s in stats.values())
    total_h = round(sum(s["hours"] for s in stats.values()), 2)
    return {"ready": stats.get("ready", {"n": 0, "hours": 0}),
            "pending": stats.get("pending", {"n": 0, "hours": 0}),
            "failed": stats.get("failed", {"n": 0, "hours": 0}),
            "total": total, "total_hours": total_h,
            "current": dict(cur) if cur else None}


def trash_payload():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id,name,duration,deleted_at FROM videos "
                       "WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
    con.close()
    return [{"id": r["id"], "name": r["name"], "time": mmss(r["duration"]),
             "deleted_at": r["deleted_at"]} for r in rows]


def make_token(username):
    exp = int(time.time()) + MAX_AGE
    payload = base64.urlsafe_b64encode(f"{username}:{exp}".encode()).decode()
    sig = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def check_token(token):
    try:
        payload, sig = token.rsplit(".", 1)
        expect = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expect):
            return None
        user, exp = base64.urlsafe_b64decode(payload.encode()).decode().rsplit(":", 1)
        if int(exp) < time.time():
            return None
        return user
    except Exception:
        return None


def verify_password(username, password):
    if not AUTH or username != AUTH.get("username"):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(AUTH["salt"]), 200_000).hex()
    return hmac.compare_digest(digest, AUTH["hash"])


LOGIN_PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>登录 · 知识库</title>
<style>body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
background:#f6f8fb;font:15px/1.6 "Microsoft YaHei",system-ui,sans-serif;color:#1f2933}
.box{width:320px;background:#fff;border:1px solid #e3e8ee;border-radius:14px;padding:26px 24px;
box-shadow:0 6px 24px rgba(31,78,121,.06)}
h1{font-size:19px;margin:0 0 4px;color:#1f4e79}p{color:#5b6b7c;font-size:12.5px;margin:0 0 18px}
input{width:100%;padding:10px 12px;border:1px solid #cfd8e3;border-radius:8px;font:inherit;
outline:none;margin-bottom:10px;box-sizing:border-box}
input:focus{border-color:#8fb3d4;box-shadow:0 0 0 3px #e8f0f8}
button{width:100%;padding:10px;border:none;border-radius:8px;background:#1f4e79;color:#fff;
font:inherit;cursor:pointer}button:hover{background:#173d5e}
.err{color:#b03060;font-size:12.5px;height:16px;margin-top:6px}</style></head>
<body><div class="box"><h1>视频知识库</h1><p>请输入访问口令</p>
<input id="u" placeholder="用户名" value="boss"><input id="p" type="password" placeholder="密码">
<button id="go">登录</button><div class="err" id="e"></div></div>
<script>
document.getElementById('go').onclick=async()=>{
 const u=document.getElementById('u').value.trim(),p=document.getElementById('p').value;
 const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({username:u,password:p})});
 if(r.ok){location.href='/';}else{document.getElementById('e').textContent='用户名或密码不对';}
};
document.getElementById('p').addEventListener('keydown',e=>{if(e.key==='Enter')document.getElementById('go').click();});
</script></body></html>"""


def videos_payload():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id,name,duration,status,summary,outline_json,kind,pages,course,path,error FROM videos "
                       "WHERE deleted_at IS NULL ORDER BY id").fetchall()
    con.close()
    out = []
    for r in rows:
        outline = json.loads(r["outline_json"] or "{}")
        chapters = outline.get("chapters", [])
        if r["status"] == "failed":
            state = "check"
        elif r["status"] != "ready":
            state = "processing"
        elif not r["summary"] or ((r["kind"] or "video") == "video" and len(chapters) < 2):
            state = "check"
        else:
            state = "available"
        kind = r["kind"] or "video"
        if kind == "pdf":
            label = f"{r['pages'] or 0} 页"
        elif kind == "docx":
            label = "Word 文档"
        elif kind == "pptx":
            label = f"{r['pages'] or 0} 张幻灯片"
        elif kind == "xlsx":
            label = "Excel 表格"
        elif kind == "audio":
            label = "音频"
        elif kind == "image":
            label = "图片"
        else:
            label = mmss(r["duration"])
        out.append({"id": r["id"], "name": r["name"], "duration": r["duration"],
                    "time": label, "course": r["course"] or "未分类",
                    "missing": bool(r["path"]) and not os.path.exists(r["path"]),
                    "error": (r["error"] or "").strip()[:300],
                    "summary": r["summary"] or "", "kind": kind, "pages": r["pages"],
                    "chapters": chapters, "keywords": outline.get("keywords", []),
                    "status": r["status"], "state": state})
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "kb/0.2"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def current_user(self):
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            key, _, value = part.strip().partition("=")
            if key == COOKIE:
                return check_token(value)
        return None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/login":
            return self._send(200, LOGIN_PAGE, "text/html; charset=utf-8")
        if path == "/api/logout":
            return self._send(302, "", "text/plain", {"Location": "/login",
                                                      "Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0"})
        if not self.current_user():
            if path.startswith("/api/"):
                return self._send(401, json.dumps({"error": "unauthorized"}))
            return self._send(302, "", "text/plain", {"Location": "/login"})
        if path == "/favicon.ico":
            return self._send(204, "")
        if path in ("/", "/index.html"):
            self._send(200, (ROOT / "kb.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/videos":
            self._send(200, json.dumps(videos_payload(), ensure_ascii=False))
        elif path == "/api/progress":
            self._send(200, json.dumps(progress_payload(), ensure_ascii=False))
        elif path == "/api/trash":
            self._send(200, json.dumps(trash_payload(), ensure_ascii=False))
        elif path == "/api/stats":
            self._send(200, json.dumps(stats_payload(), ensure_ascii=False))
        elif path == "/api/health":
            idx = load_index()
            self._send(200, json.dumps({"ok": True, "videos": len(idx["videos"]),
                                        "segments": len(idx["segs"])}, ensure_ascii=False))
        elif path == "/cover":
            qs = parse_qs(urlparse(self.path).query)
            course = (qs.get("course") or [""])[0]
            cover = ensure_cover(course) if course else None
            if cover and cover.exists():
                self._send(200, cover.read_bytes(), "image/jpeg",
                           {"Cache-Control": "max-age=86400"})
            else:
                self._send(404, b"", "image/jpeg")
        elif path.startswith("/video/") or path.startswith("/file/"):
            self.stream_file(path.split("/")[-1])
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def stream_file(self, vid):
        try:
            vid = int(vid)
        except ValueError:
            return self._send(400, "bad id")
        con = sqlite3.connect(DB)
        row = con.execute("SELECT path FROM videos WHERE id=?", (vid,)).fetchone()
        con.close()
        if not row or not os.path.exists(row[0]):
            return self._send(404, "file not found")
        path = row[0]
        size = os.path.getsize(path)
        ctype = FILE_MIME.get(Path(path).suffix.lower(), "application/octet-stream")
        if Path(path).suffix.lower() == ".pdf":
            ctype = "application/pdf"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            part = rng[6:].split("-")
            if part[0]:
                start = int(part[0])
            if len(part) > 1 and part[1]:
                end = min(int(part[1]), size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        length = end - start + 1
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(256 * 1024, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/login":
            return self.handle_login()
        if not self.current_user():
            return self._send(401, json.dumps({"error": "unauthorized"}))
        if path.startswith("/api/upload_chunk"):
            return self.handle_upload_chunk()
        if path.startswith("/api/upload_finish"):
            return self.handle_upload_finish()
        if path == "/api/upload":
            return self.handle_upload()
        if path == "/api/feedback":
            return self.handle_feedback()
        if path.startswith("/api/retry/"):
            return self.handle_retry(path.rsplit("/", 1)[-1])
        if path.startswith("/api/delete/"):
            return self.trash_action(path.split("/")[-1], "delete")
        if path.startswith("/api/restore/"):
            return self.trash_action(path.split("/")[-1], "restore")
        if path.startswith("/api/purge/"):
            return self.trash_action(path.split("/")[-1], "purge")
        if path != "/api/ask":
            return self._send(404, json.dumps({"error": "not found"}))
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n).decode("utf-8"))
            q = (req.get("question") or "").strip()
            course = (req.get("course") or "").strip()
            if not q:
                return self._send(400, json.dumps({"error": "空问题"}))
            self._send(200, json.dumps(ask(q, course or None, debug=bool(req.get("debug")),
                                           mode=(req.get("mode") or "hybrid")),
                                       ensure_ascii=False))
        except Exception as e:
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False))

    def handle_login(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n).decode("utf-8"))
            user = (req.get("username") or "").strip()
            pwd = req.get("password") or ""
            if not verify_password(user, pwd):
                time.sleep(0.4)
                return self._send(401, json.dumps({"error": "用户名或密码不对"}))
            token = make_token(user)
            self._send(200, json.dumps({"ok": True, "user": user}), extra={
                "Set-Cookie": f"{COOKIE}={token}; Path=/; HttpOnly; Max-Age={MAX_AGE}; SameSite=Lax"})
        except Exception as e:
            self._send(400, json.dumps({"error": f"{type(e).__name__}"}, ensure_ascii=False))

    def trash_action(self, raw_id, action):
        try:
            vid = int(raw_id)
        except ValueError:
            return self._send(400, json.dumps({"error": "bad id"}))
        con = sqlite3.connect(DB, timeout=10)
        try:
            if action == "delete":
                con.execute("UPDATE videos SET deleted_at=datetime('now','localtime') WHERE id=?", (vid,))
                con.commit()
                return self._send(200, json.dumps({"ok": True, "deleted": vid}))
            if action == "restore":
                con.execute("UPDATE videos SET deleted_at=NULL WHERE id=?", (vid,))
                con.commit()
                return self._send(200, json.dumps({"ok": True, "restored": vid}))
            if action == "purge":
                row = con.execute("SELECT path FROM videos WHERE id=? AND deleted_at IS NOT NULL",
                                  (vid,)).fetchone()
                if not row:
                    return self._send(400, json.dumps({"error": "只能彻底删除回收站里的内容"}))
                con.execute("DELETE FROM segments WHERE video_id=?", (vid,))
                con.execute("DELETE FROM videos WHERE id=?", (vid,))
                con.commit()
                for base in (ROOT / "data" / "library", ROOT / "data" / "export"):
                    if base.exists():
                        for p in base.glob(f"{vid:04d}_*"):
                            if p.is_dir():
                                shutil.rmtree(p, ignore_errors=True)
                            else:
                                p.unlink(missing_ok=True)
                return self._send(200, json.dumps({"ok": True, "purged": vid}))
        finally:
            con.close()

    def handle_feedback(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n).decode("utf-8"))
            log_id = int(req.get("id") or 0)
            rating = int(req.get("rating") or 0)
            if rating not in (1, -1, 0):
                return self._send(400, json.dumps({"error": "bad rating"}))
            con = sqlite3.connect(DB)
            con.execute("UPDATE qa_logs SET rating=? WHERE id=?", (rating, log_id))
            con.commit()
            con.close()
            self._send(200, json.dumps({"ok": True}))
        except Exception as e:
            self._send(400, json.dumps({"error": str(type(e).__name__)}))

    def handle_retry(self, vid):
        try:
            vid = int(vid)
        except ValueError:
            return self._send(400, json.dumps({"error": "bad id"}))
        con = sqlite3.connect(DB)
        con.execute("UPDATE videos SET status='pending', error=NULL, attempts=0, "
                    "updated_at=datetime('now','localtime') WHERE id=?", (vid,))
        con.commit()
        con.close()
        self._send(200, json.dumps({"ok": True}))

    def handle_upload_chunk(self):
        from urllib.parse import parse_qs
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get("upload_id") or [""])[0]
        if not re.fullmatch(r"[0-9a-f]{8,64}", uid or ""):
            return self._send(400, json.dumps({"error": "bad upload id"}))
        idx = int((qs.get("index") or ["0"])[0])
        total = int(self.headers.get("Content-Length", 0))
        d = ROOT / "data" / "tmp" / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        part = d / f"{uid}.{idx:04d}"
        got = 0
        with open(part, "wb") as f:
            while got < total:
                chunk = self.rfile.read(min(1 << 20, total - got))
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
        self._send(200, json.dumps({"ok": True, "index": idx, "bytes": got}))

    def handle_upload_finish(self):
        from urllib.parse import parse_qs
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get("upload_id") or [""])[0]
        if not re.fullmatch(r"[0-9a-f]{8,64}", uid or ""):
            return self._send(400, json.dumps({"error": "bad upload id"}))
        raw_name = (qs.get("name") or ["upload.bin"])[0]
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_name).strip().rstrip(".")[:120] or "upload.bin"
        raw_course = (qs.get("course") or [""])[0].strip()
        course = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_course).strip().rstrip(".")[:40]
        total = int((qs.get("total") or ["0"])[0])

        tmp = ROOT / "data" / "tmp" / "uploads"
        parts = sorted(tmp.glob(f"{uid}.*"))
        if len(parts) != total or total == 0:
            return self._send(400, json.dumps({"error": f"expected {total} parts, got {len(parts)}"}))

        inbox = ROOT / "data" / "inbox"
        if course:
            inbox = inbox / course
        inbox.mkdir(parents=True, exist_ok=True)
        target = inbox / name
        if target.exists():
            stem, suffix = target.stem, target.suffix
            k = 2
            while target.exists():
                target = inbox / f"{stem}_{k}{suffix}"
                k += 1

        size = 0
        with open(target, "wb") as out:
            for p in parts:
                with open(p, "rb") as f:
                    while True:
                        buf = f.read(1 << 20)
                        if not buf:
                            break
                        out.write(buf)
                        size += len(buf)
        for p in parts:
            p.unlink(missing_ok=True)
        self._send(200, json.dumps({"ok": True, "name": target.name, "bytes": size},
                                   ensure_ascii=False))

    def handle_upload(self):
        """Raw body upload: POST /api/upload?name=xxx.mp4 (streamed, no multipart parsing)."""
        from urllib.parse import parse_qs
        qs = parse_qs(urlparse(self.path).query)
        raw_name = (qs.get("name") or ["upload.bin"])[0]
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_name).strip().rstrip(".")[:120] or "upload.bin"
        raw_course = (qs.get("course") or [""])[0].strip()
        course = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_course).strip().rstrip(".")[:40]
        inbox = ROOT / "data" / "inbox"
        if course:
            inbox = inbox / course
        inbox.mkdir(parents=True, exist_ok=True)
        target = inbox / name
        if target.exists():
            stem, suffix = target.stem, target.suffix
            i = 2
            while target.exists():
                target = inbox / f"{stem}_{i}{suffix}"
                i += 1
        total = int(self.headers.get("Content-Length", 0))
        got = 0
        try:
            with open(target, "wb") as f:
                while got < total:
                    chunk = self.rfile.read(min(1 << 20, total - got))
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
            self._send(200, json.dumps({"ok": True, "name": target.name,
                                        "bytes": got}, ensure_ascii=False))
        except Exception as e:
            target.unlink(missing_ok=True)
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
    host = os.environ.get("KB_HOST", "0.0.0.0")  # 局域网可访问；只想本机用可设 KB_HOST=127.0.0.1
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"kb serving http://{host}:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

