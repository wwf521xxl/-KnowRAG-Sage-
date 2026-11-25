"""Batch pipeline: scan local videos, transcribe on GPU, structure with an LLM.

Usage:
    python batch.py scan "D:\\videos" [--recursive]
    python batch.py run [--limit N] [--retry-failed] [--model medium]
    python batch.py status
    python batch.py export [--id N]
    python batch.py reset --id N
"""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import av
import requests

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "kb.db"
MODEL_DIR = ROOT / "models" / "faster-whisper-medium"
CFG_PATH = ROOT / "config.local.json"
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".wmv", ".webm", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
DOC_EXT = {".pdf", ".docx"}
PPT_EXT = {".pptx"}
XLS_EXT = {".xlsx", ".xlsm"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SUPPORTED_EXT = VIDEO_EXT | AUDIO_EXT | DOC_EXT | PPT_EXT | XLS_EXT | IMG_EXT

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT UNIQUE NOT NULL,
  name TEXT,
  duration REAL,
  size INTEGER,
  fingerprint TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER DEFAULT 0,
  error TEXT,
  device TEXT,
  asr_seconds REAL,
  summary TEXT,
  outline_json TEXT,
  created_at TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id INTEGER NOT NULL,
  seq INTEGER NOT NULL,
  start REAL,
  end REAL,
  text TEXT
);
CREATE INDEX IF NOT EXISTS idx_segments_video ON segments(video_id, seq);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def mmss(sec):
    s = int(sec or 0)
    return f"{s // 60:02d}:{s % 60:02d}"


def human(sec):
    sec = sec or 0
    if sec >= 3600:
        return f"{sec / 3600:.1f} 小时"
    return f"{sec / 60:.0f} 分钟"


def probe(path):
    """Return (kind, duration, pages, has_audio)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import fitz
        with fitz.open(str(path)) as doc:
            return "pdf", 0.0, doc.page_count, True
    if suffix == ".docx":
        return "docx", 0.0, None, True
    if suffix == ".pptx":
        from pptx import Presentation
        return "pptx", 0.0, len(Presentation(str(path)).slides), True
    if suffix in XLS_EXT:
        return "xlsx", 0.0, None, True
    if suffix in IMG_EXT:
        return "image", 0.0, None, True
    with av.open(str(path)) as container:
        duration = float(container.duration / av.time_base) if container.duration else 0.0
        has_audio = any(s.type == "audio" for s in container.streams)
    kind = "audio" if suffix in AUDIO_EXT else "video"
    return kind, duration, None, has_audio


def fingerprint(path, size):
    h = hashlib.blake2b(digest_size=16)
    h.update(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(2 << 20))
        if size > 4 << 20:
            f.seek(-(2 << 20), 2)
            h.update(f.read(2 << 20))
    return h.hexdigest()


def load_cfg():
    if not CFG_PATH.exists():
        return None
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- LLM outline
SYSTEM = """你是视频内容编辑。根据带时间戳的逐字稿，输出严格 JSON（不要 markdown 代码块）：
{"summary": "不超过200字的中文摘要，讲清这个视频到底说了什么",
 "chapters": [{"title": "不超过18字", "start": "mm:ss", "end": "mm:ss", "summary": "不超过40字"}],
 "keywords": ["3-8个关键词"]}
要求：章节 3-10 个，时间单调递增且落在逐字稿范围内；不要编造逐字稿里没有的事实。"""


def call_llm(cfg, user, temperature=0.2, max_tokens=1200, system=None):
    r = requests.post(
        cfg.get("base_url", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
        json={"model": cfg.get("model", "deepseek-chat"),
              "messages": [{"role": "system", "content": system or SYSTEM},
                           {"role": "user", "content": user}],
              "temperature": temperature, "max_tokens": max_tokens},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no json object")
    return json.loads(text[start:end + 1])


def to_seconds(value):
    if isinstance(value, (int, float)):
        return float(value)
    parts = [int(p) for p in str(value).split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def transcript_text(rows):
    return "\n".join(f"[{mmss(r['start'])}] {r['text']}" for r in rows)


def outline_for(cfg, rows, title, duration):
    text = transcript_text(rows)
    user = f"【视频标题】{title}\n【时长】{mmss(duration)}\n\n【逐字稿】\n{text}\n\n只输出 JSON。"
    try:
        data = parse_json(call_llm(cfg, user))
    except Exception:
        data = parse_json(call_llm(cfg, user + "\n\n注意：只输出 JSON，不要任何解释。", temperature=0))

    chapters = []
    for ch in data.get("chapters", []):
        st, en = to_seconds(ch.get("start", 0)), to_seconds(ch.get("end", 0))
        if en < st:
            st, en = en, st
        chapters.append({"title": ch.get("title", "").strip(),
                         "start": min(max(st, 0), duration or st),
                         "end": min(max(en, st), duration or en),
                         "summary": ch.get("summary", "").strip()})
    chapters.sort(key=lambda c: c["start"])
    return {"summary": data.get("summary", "").strip(),
            "chapters": chapters,
            "keywords": data.get("keywords", [])[:8]}


# ------------------------------------------------------------------- commands
def cmd_scan(args):
    root = Path(args.dir).expanduser().resolve()
    if not root.exists():
        sys.exit(f"目录不存在: {root}")
    files = sorted(p for p in (root.rglob("*") if args.recursive else root.glob("*"))
                   if p.suffix.lower() in SUPPORTED_EXT)
    c = conn()
    added = dup = bad = 0
    for p in files:
        size = p.stat().st_size
        fp = fingerprint(p, size)
        if c.execute("SELECT 1 FROM videos WHERE fingerprint=?", (fp,)).fetchone():
            dup += 1
            continue
        try:
            kind, duration, pages, has_audio = probe(p)
            if kind == "video" and not has_audio:
                print(f"  [skip] 无音轨: {p.name}")
                bad += 1
                continue
        except Exception as e:
            print(f"  [skip] 读取失败 {p.name}: {type(e).__name__}")
            bad += 1
            continue
        parent = p.parent.name
        course = "未分类" if parent.lower() in ("inbox", "raw") else parent
        c.execute(
            "INSERT INTO videos(path,name,duration,size,fingerprint,kind,pages,course,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(p), p.stem, round(duration, 1), size, fp, kind, pages, course, now(), now()))
        added += 1
        extra = f"{mmss(duration)}" if kind == "video" else f"{pages} 页"
        print(f"  [add] {p.name}  {extra}  {size / 1e6:.0f}MB")
    c.commit()
    total = c.execute("SELECT COUNT(*) n, COALESCE(SUM(duration),0) d FROM videos").fetchone()
    print(f"\n扫描完成：新增 {added}，重复 {dup}，跳过 {bad}；"
          f"库内共 {total['n']} 条 / {human(total['d'])}")


def mark(c, vid, status, error=None, **extra):
    fields = ["status=?", "updated_at=?"]
    values = [status, now()]
    if status in ("ready", "transcribed"):
        fields.append("error=NULL")
    if error is not None:
        fields.append("error=?")
        values.append(error)
    for k, v in extra.items():
        fields.append(f"{k}=?")
        values.append(v)
    values.append(vid)
    c.execute(f"UPDATE videos SET {', '.join(fields)} WHERE id=?", values)
    c.commit()


def cmd_run(args):
    cfg = load_cfg()
    c = conn()
    # 上次中断留下的“进行中”状态，回收成 pending 继续跑
    c.execute("UPDATE videos SET status='pending' WHERE status='transcribing'")
    c.commit()
    statuses = ["pending", "transcribed", "structured"]
    if args.retry_failed:
        statuses.append("failed")
    q = f"SELECT * FROM videos WHERE status IN ({','.join('?' * len(statuses))})"
    params = list(statuses)
    if args.dir:
        q += " AND path LIKE ?"
        params.append(f"%{args.dir}%")
    q += " ORDER BY duration ASC"
    todo = c.execute(q, params).fetchall()
    if args.limit:
        todo = todo[:args.limit]
    if not todo:
        print("没有待处理的视频。先 scan。")
        return

    from asr_runtime import make_pipeline, transcribe_chunked, transcribe_with
    rt = None
    if any((v["kind"] or "video") == "video" for v in todo):
        print(f"加载模型 {args.model} ...", flush=True)
        t0 = time.time()
        rt = make_pipeline(MODEL_DIR if args.model == "medium" else MODEL_DIR.with_name(f"faster-whisper-{args.model}"),
                           args.device)
        print(f"模型就绪：{rt['device']}/{rt['compute']}，加载 {time.time() - t0:.1f}s\n", flush=True)
    else:
        print("本批只有文档，跳过模型加载\n", flush=True)

    done_audio = 0.0
    started = time.time()
    for i, v in enumerate(todo, 1):
        kind = v["kind"] or "video"
        name, dur, vid = v["name"], v["duration"] or 0, v["id"]
        label = {"video": mmss(dur), "pdf": f"{v['pages'] or '?'} 页", "docx": "Word",
                 "pptx": f"{v['pages'] or '?'} 张", "xlsx": "Excel", "audio": "音频"}.get(kind, "图片")
        print(f"[{i}/{len(todo)}] {name}  ({label})", flush=True)
        try:
            rows = None
            if v["status"] in ("transcribed", "structured"):
                rows = [{"start": r["start"], "end": r["end"], "text": r["text"], "locator": r["locator"]}
                        for r in c.execute(
                            "SELECT start,end,text,locator FROM segments WHERE video_id=? ORDER BY seq", (vid,))]
                asr_s = v["asr_seconds"] or 0
                print(f"    已有内容（{len(rows)} 段），跳过解析", flush=True)
            else:
                mark(c, vid, "transcribing", attempts=v["attempts"] + 1)
                t1 = time.time()
                if kind in ("pdf", "docx", "pptx", "xlsx", "image"):
                    if kind == "pdf":
                        rows = extract_pdf(v["path"])
                    elif kind == "docx":
                        rows = extract_docx(v["path"])
                    elif kind == "pptx":
                        rows = extract_pptx(v["path"])
                    elif kind == "xlsx":
                        rows = extract_xlsx(v["path"])
                    else:
                        if not cfg:
                            raise ValueError("图片识别需要配置 LLM")
                        rows = extract_image(v["path"], cfg)
                    if not rows:
                        raise ValueError("未提取到文字，可能是扫描版/图片型文档（需要 OCR）")
                    asr_s = time.time() - t1
                    print(f"    解析 {asr_s:.1f}s，{len(rows)} 段", flush=True)
                    c.execute("DELETE FROM segments WHERE video_id=?", (vid,))
                    c.executemany(
                        "INSERT INTO segments(video_id,seq,start,end,text,locator) VALUES(?,?,?,?,?,?)",
                        [(vid, j, r["start"], r["end"], r["text"], r["locator"]) for j, r in enumerate(rows)])
                    mark(c, vid, "transcribed", device=kind, asr_seconds=round(asr_s, 1))
                    embeddings_for(c, vid)
                else:
                    if args.words:
                        rows, meta = transcribe_with(rt, v["path"], batch_size=args.batch,
                                                     word_timestamps=True)
                    else:
                        rows, meta = transcribe_chunked(rt, v["path"], chunk_seconds=args.chunk,
                                                        batch_size=args.batch)
                    asr_s = time.time() - t1
                    speed = (dur / asr_s) if asr_s else 0
                    print(f"    转写 {asr_s:.1f}s（{speed:.1f}x）{len(rows)} 句", flush=True)

                    c.execute("DELETE FROM segments WHERE video_id=?", (vid,))
                    c.executemany("INSERT INTO segments(video_id,seq,start,end,text) VALUES(?,?,?,?,?)",
                                  [(vid, j, r["start"], r["end"], r["text"]) for j, r in enumerate(rows)])
                    mark(c, vid, "transcribed", device=meta["device"], asr_seconds=round(asr_s, 1))
                    embeddings_for(c, vid)

            if cfg and v["outline_json"]:
                out = json.loads(v["outline_json"])
                print("    已有结构化结果，直接写文件", flush=True)
            elif cfg:
                t2 = time.time()
                if kind == "pdf":
                    out = outline_pdf(cfg, rows, name, v["pages"] or 1)
                elif kind in ("docx", "pptx", "xlsx"):
                    out = outline_docx(cfg, rows, name)
                elif kind == "image":
                    out = outline_image(cfg, rows, name)
                else:
                    out = outline_for(cfg, rows, name, dur)
                mark(c, vid, "structured", summary=out["summary"],
                     outline_json=json.dumps(out, ensure_ascii=False))
                print(f"    结构化 {time.time() - t2:.1f}s，{len(out['chapters'])} 节", flush=True)
            else:
                out = {"summary": "", "chapters": [], "keywords": []}

            write_library(v, rows, out, kind)
            mark(c, vid, "ready")
            archive_source(c, v)
            done_audio += dur
        except Exception as e:
            mark(c, vid, "failed", error=f"{type(e).__name__}: {str(e)[:300]}")
            print(f"    失败：{type(e).__name__}: {str(e)[:160]}", flush=True)

        elapsed = time.time() - started
        if done_audio and elapsed > 2:
            speed = done_audio / elapsed
            remaining = sum(x["duration"] or 0 for x in todo[i:])
            print(f"    —— 已处理 {done_audio / 60:.0f} 分钟音频，"
                  f"{speed:.1f}x，预计剩余 {remaining / speed / 60:.1f} 分钟\n", flush=True)

    s = c.execute("SELECT status, COUNT(*) n FROM videos GROUP BY status").fetchall()
    print("完成。状态：" + "，".join(f"{r['status']}={r['n']}" for r in s))


PDF_SYSTEM = """你是文档编辑。根据按页切分的 PDF 文本，输出严格 JSON（不要 markdown 代码块）：
{"summary": "不超过200字的中文摘要，讲清这份文档在讲什么",
 "sections": [{"title": "不超过18字", "page": 12, "summary": "不超过40字"}],
 "keywords": ["3-8个关键词"]}
要求：section 3-10 个，页码必须落在给定范围内；不要编造文档里没有的事实。"""


def extract_pdf(path, target=480):
    """Extract text page by page, merging blocks into ~480 char chunks (never across pages)."""
    import fitz

    rows = []
    with fitz.open(str(path)) as doc:
        for pno in range(doc.page_count):
            page = doc[pno]
            blocks = [b for b in page.get_text("blocks") if str(b[4]).strip()]
            blocks.sort(key=lambda b: (round(b[1] / 8), b[0]))
            buf = []
            for b in blocks:
                text = re.sub(r"[ \t]+", " ", str(b[4])).strip()
                if not text:
                    continue
                buf.append(text)
                merged = "\n".join(buf)
                if len(merged) >= target:
                    rows.append({"start": 0, "end": 0, "locator": f"p{pno + 1}", "text": merged})
                    buf = []
            if buf:
                rows.append({"start": 0, "end": 0, "locator": f"p{pno + 1}", "text": "\n".join(buf)})
    return rows


def outline_pdf(cfg, rows, title, pages):
    text = "\n".join(f"[第{int(str(r['locator']).lstrip('p'))}页] {r['text']}" for r in rows)
    user = f"【文档】{title}\n【页数】{pages}\n\n【正文】\n{text}\n\n只输出 JSON。"
    try:
        data = parse_json(call_llm(cfg, user, system=PDF_SYSTEM))
    except Exception:
        data = parse_json(call_llm(cfg, user + "\n\n注意：只输出 JSON。", temperature=0, system=PDF_SYSTEM))

    chapters = []
    for s in data.get("sections", []):
        try:
            page = max(1, min(int(s.get("page", 1)), pages))
        except Exception:
            page = 1
        chapters.append({"title": s.get("title", "").strip(), "page": page,
                         "start": page, "end": page, "summary": s.get("summary", "").strip()})
    chapters.sort(key=lambda c: c["page"])
    return {"summary": data.get("summary", "").strip(), "chapters": chapters,
            "keywords": data.get("keywords", [])[:8]}


DOCX_SYSTEM = """你是文档编辑。根据 Word 文档的正文（含小节标题），输出严格 JSON（不要 markdown 代码块）：
{"summary": "不超过200字的中文摘要，讲清这份文档在讲什么",
 "keywords": ["3-8个关键词"]}
不要编造文档里没有的事实。"""


def extract_docx(path, target=480):
    """Paragraphs -> ~480 char chunks; headings become section prefixes."""
    import docx

    document = docx.Document(str(path))
    rows, buf = [], []
    section = ""
    seq = 0

    def flush():
        nonlocal buf, seq
        if not buf:
            return
        seq += 1
        text = "\n".join(buf)
        if section:
            text = f"【{section}】\n{text}"
        rows.append({"start": 0, "end": 0, "locator": f"第{seq}段", "text": text})
        buf = []

    for p in document.paragraphs:
        t = (p.text or "").strip()
        if not t:
            continue
        style = (p.style.name or "") if p.style is not None else ""
        if style.startswith("Heading") or style == "Title":
            flush()
            section = t
            continue
        buf.append(t)
        if len("\n".join(buf)) >= target:
            flush()
    flush()

    # 表格单独成块
    for table in document.tables:
        rows_txt = []
        for r in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in r.cells]
            if any(cells):
                rows_txt.append(" | ".join(cells))
        if rows_txt:
            seq += 1
            rows.append({"start": 0, "end": 0, "locator": f"第{seq}段",
                         "text": "【表格】\n" + "\n".join(rows_txt)})
    return rows


def extract_pptx(path):
    """PPT：每张幻灯片一个块，标题作为章节。"""
    from pptx import Presentation

    prs = Presentation(str(path))
    rows = []
    for i, slide in enumerate(prs.slides, 1):
        texts, title = [], ""
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            t = (shape.text_frame.text or "").strip()
            if not t:
                continue
            if not title and len(t) <= 30:
                title = t.replace("\n", " ")
            texts.append(t)
        if slide.has_notes_slide:
            note = (slide.notes_slide.notes_text_frame.text or "").strip()
            if note:
                texts.append("备注：" + note)
        if not texts:
            continue
        prefix = f"【第{i}张 {title}】" if title else f"【第{i}张】"
        rows.append({"start": 0, "end": 0, "locator": f"第{i}张",
                     "text": prefix + "\n" + "\n".join(texts)[:1200]})
    return rows


def extract_xlsx(path, target=800):
    """Excel：按工作表 + 行区间切块，保留表头上下文。"""
    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    rows = []
    for ws in wb.worksheets:
        buf, start = [], 1
        for idx, row in enumerate(ws.iter_rows(values_only=True), 1):
            cells = [str(c).strip() for c in row if c not in (None, "")]
            if not cells:
                continue
            buf.append(" | ".join(cells))
            if sum(len(x) for x in buf) >= target:
                rows.append({"start": 0, "end": 0, "locator": f"{ws.title}!第{start}-{idx}行",
                             "text": f"【{ws.title}】\n" + "\n".join(buf)})
                buf, start = [], idx + 1
        if buf:
            rows.append({"start": 0, "end": 0, "locator": f"{ws.title}!第{start}行起",
                         "text": f"【{ws.title}】\n" + "\n".join(buf)})
    wb.close()
    return rows


def outline_docx(cfg, rows, title):
    text = "\n".join(f"[{r['locator']}] {r['text']}" for r in rows)[:24000]
    user = f"【文档】{title}\n\n【正文】\n{text}\n\n只输出 JSON。"
    try:
        data = parse_json(call_llm(cfg, user, system=DOCX_SYSTEM))
    except Exception:
        data = parse_json(call_llm(cfg, user + "\n\n注意：只输出 JSON。", temperature=0, system=DOCX_SYSTEM))

    chapters = []
    for r in rows:
        head = re.match(r"【(.+?)】", r["text"])
        if head:
            chapters.append({"title": head.group(1)[:18], "locator": r["locator"],
                             "start": 0, "end": 0, "page": None, "summary": ""})
    chapters = chapters[:10]
    return {"summary": data.get("summary", "").strip(), "chapters": chapters,
            "keywords": data.get("keywords", [])[:8]}


IMG_SYSTEM = """你看一张图片，把它转成可检索的文字。只输出严格 JSON（不要 markdown 代码块）：
{"type": "截图|聊天记录|图表|海报|照片|表格",
 "title": "不超过18字的标题",
 "paragraphs": ["图中文字，按阅读顺序分段，保留原文"],
 "description": "这张图在讲什么，2-3 句",
 "confidence": "high|medium|low"}
要求：只写图中真实存在的内容，不要推测；图里没有文字就只给 description。"""


def call_vision(cfg, image_bytes):
    import base64
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": cfg.get("model", "deepseek-chat"),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": IMG_SYSTEM},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
        "temperature": 0,
        "max_tokens": 1500,
    }
    r = requests.post(cfg.get("base_url", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
                      headers={"Authorization": f"Bearer {cfg['api_key']}",
                               "Content-Type": "application/json"},
                      json=payload, timeout=120)
    r.raise_for_status()
    return parse_json(r.json()["choices"][0]["message"]["content"])


def extract_image(path, cfg):
    """Slice tall images, ask the vision model for text + description, return blocks."""
    import io

    from PIL import Image

    img = Image.open(str(path)).convert("RGB")
    width, height = img.size
    slices = []
    if height <= 2200:
        slices = [(1, img)]
    else:
        step, overlap, y, idx = 1800, 120, 0, 1
        while y < height:
            box = (0, y, width, min(y + step + overlap, height))
            slices.append((idx, img.crop(box)))
            y += step
            idx += 1

    rows = []
    for k, part in slices:
        buf = io.BytesIO()
        part.save(buf, "PNG")
        try:
            data = call_vision(cfg, buf.getvalue())
        except Exception as e:
            if k == 1:
                raise
            print(f"    第{k}片识别失败：{type(e).__name__}", flush=True)
            continue
        title = (data.get("title") or "").strip()
        paras = [p.strip() for p in data.get("paragraphs", []) if len(p.strip()) >= 2]
        prefix = f"【{title}】\n" if title else ""
        if paras:
            rows.append({"start": 0, "end": 0,
                         "locator": f"图{k}" if len(slices) == 1 else f"图{k}-1",
                         "text": prefix + "\n".join(paras[:6])})
            for i, extra in enumerate(paras[6:], 2):
                rows.append({"start": 0, "end": 0, "locator": f"图{k}-{i}", "text": extra})
        desc = (data.get("description") or "").strip()
        if desc:
            rows.append({"start": 0, "end": 0, "locator": f"图{k}", "text": "【图片描述】" + desc})
    if not rows:
        raise ValueError("图片里没有识别到可用内容")
    return rows


def outline_image(cfg, rows, title):
    text = "\n".join(r["text"] for r in rows)[:6000]
    user = (f"【图片文件名】{title}\n\n【图片内容】\n{text}\n\n"
            "输出严格 JSON：{\"summary\":\"不超过120字的摘要\",\"keywords\":[\"3-6个关键词\"]}")
    try:
        data = parse_json(call_llm(cfg, user, max_tokens=500))
    except Exception:
        data = {"summary": text[:120], "keywords": []}
    return {"summary": (data.get("summary") or "").strip(), "chapters": [],
            "keywords": data.get("keywords", [])[:6]}


def safe_name(name):
    """文件名里的非法字符和首尾空格会让 Windows 写入失败，统一清洗。"""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "").strip().rstrip(".")
    return (s[:40] or "video")


_EMB = None


def embeddings_for(c, vid):
    """Compute and store embeddings for segments of one document (skip if model missing)."""
    global _EMB
    try:
        if _EMB is None:
            from embeddings import Embedder
            _EMB = Embedder()
        rows = c.execute("SELECT id,text FROM segments WHERE video_id=? AND embedding IS NULL "
                         "AND text IS NOT NULL", (vid,)).fetchall()
        if not rows:
            return
        vecs = _EMB.encode([r["text"][:1000] for r in rows], batch_size=32)
        c.executemany("UPDATE segments SET embedding=? WHERE id=?",
                      [(v.astype("float32").tobytes(), r["id"]) for v, r in zip(vecs, rows)])
        c.commit()
        print(f"    向量化 {len(rows)} 段", flush=True)
    except Exception as e:
        print(f"    向量化跳过：{type(e).__name__}", flush=True)


def archive_source(c, v):
    """Move a processed file out of inbox so the watcher stops rescanning it."""
    path = Path(v["path"])
    inbox = (ROOT / "data" / "inbox").resolve()
    try:
        if inbox not in path.resolve().parents:
            return
    except OSError:
        return
    dest_dir = ROOT / "data" / "raw"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{v['id']:04d}_{safe_name(v['name'])}{path.suffix.lower()}"
    shutil.move(str(path), str(dest))
    c.execute("UPDATE videos SET path=? WHERE id=?", (str(dest), v["id"]))
    c.commit()
    print(f"    归档到 {dest.name}", flush=True)


def write_library(v, rows, out, kind="video"):
    d = ROOT / "data" / "library" / f"{v['id']:04d}_{safe_name(v['name'])}"
    d.mkdir(parents=True, exist_ok=True)
    head = {"video": f"时长 {mmss(v['duration'])}", "pdf": f"{v['pages'] or '?'} 页",
            "docx": "Word 文档", "pptx": f"{v['pages'] or '?'} 张幻灯片",
            "xlsx": "Excel 表格", "audio": f"时长 {mmss(v['duration'])}"}.get(kind, "图片")
    md = [f"# {v['name']}", "", f"{head} · {v['path']}", ""]
    if kind in ("pdf", "docx", "pptx", "xlsx", "image"):
        md += [f"[{r['locator']}] {r['text']}" for r in rows]
    else:
        md += [f"[{mmss(r['start'])}] {r['text']}" for r in rows]
    (d / "transcript.md").write_text("\n".join(md), encoding="utf-8")

    o = [f"# {v['name']}", "", "## 摘要", "", out["summary"], "", "## 章节", ""]
    for ch in out["chapters"]:
        if kind == "pdf":
            o.append(f"- **第{ch.get('page', 1)}页　{ch['title']}**：{ch['summary']}")
        elif kind in ("docx", "pptx", "xlsx"):
            o.append(f"- **{ch.get('locator', '')}　{ch['title']}**")
        else:
            o.append(f"- **{mmss(ch['start'])}–{mmss(ch['end'])}　{ch['title']}**：{ch['summary']}")
    o += ["", "## 关键词", "", "、".join(out.get("keywords", []))]
    (d / "outline.md").write_text("\n".join(o), encoding="utf-8")


def cmd_status(args):
    c = conn()
    rows = c.execute("SELECT status, COUNT(*) n, COALESCE(SUM(duration),0) d FROM videos GROUP BY status").fetchall()
    total = c.execute("SELECT COUNT(*) n, COALESCE(SUM(duration),0) d, "
                      "COALESCE(SUM(CASE WHEN status='ready' THEN duration ELSE 0 END),0) rd FROM videos").fetchone()
    print(f"库内 {total['n']} 条，{human(total['d'])}，已完成 {human(total['rd'])}")
    for r in rows:
        print(f"  {r['status']:12s} {r['n']:4d} 条  {human(r['d'])}")
    failed = c.execute("SELECT id,name,error,attempts FROM videos WHERE status='failed' LIMIT 10").fetchall()
    if failed:
        print("\n失败列表：")
        for f in failed:
            print(f"  #{f['id']} {f['name']}  [{f['attempts']} 次] {f['error']}")


def cmd_export(args):
    c = conn()
    q = "SELECT * FROM videos WHERE status='ready'" + (" AND id=?" if args.id else "")
    rows = c.execute(q, (args.id,) if args.id else ()).fetchall()
    out = ROOT / "data" / "export"
    out.mkdir(parents=True, exist_ok=True)
    for v in rows:
        segs = c.execute("SELECT * FROM segments WHERE video_id=? ORDER BY seq", (v["id"],)).fetchall()
        outd = ROOT / "data" / "library" / f"{v['id']:04d}_{safe_name(v['name'])}"
        outd.mkdir(parents=True, exist_ok=True)
        md = [f"# {v['name']}", "", "## 摘要", "", v["summary"] or "", ""]
        o = json.loads(v["outline_json"] or "{}")
        for ch in o.get("chapters", []):
            md.append(f"- **{mmss(ch['start'])}　{ch['title']}**：{ch['summary']}")
        md += ["", "## 逐字稿", ""] + [f"[{mmss(s['start'])}] {s['text']}" for s in segs]
        (out / f"{v['id']:04d}_{safe_name(v['name'])}.md").write_text("\n".join(md), encoding="utf-8")
        print(f"  exported #{v['id']} {v['name']}")


def cmd_reset(args):
    c = conn()
    c.execute("UPDATE videos SET status='pending', error=NULL WHERE id=?", (args.id,))
    c.commit()
    print(f"#{args.id} 已重置为 pending")


def main():
    ap = argparse.ArgumentParser(description="视频批量入库")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="扫描目录，登记新视频")
    p.add_argument("dir")
    p.add_argument("--recursive", action="store_true", default=True)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("run", help="处理待处理的视频")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--model", default="medium")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--words", action="store_true", help="词级时间戳（更准但慢很多）")
    p.add_argument("--dir", help="只处理路径包含该字符串的视频")
    p.add_argument("--chunk", type=int, default=1800, help="切片秒数，默认 1800")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status", help="查看进度")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("export", help="导出 Markdown")
    p.add_argument("--id", type=int)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("reset", help="重置单条任务")
    p.add_argument("--id", type=int, required=True)
    p.set_defaults(func=cmd_reset)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()


