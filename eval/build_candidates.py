"""从现有内容自动生成评测候选问题（LLM 出题，人工审核）。

用法：
    python eval/build_candidates.py --video 60 --pdf 30 --docx 10 --image 10 --neg 20
输出：eval/candidates.jsonl
"""
import argparse
import json
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "kb.db"
CFG = json.loads((ROOT / "config.local.json").read_text(encoding="utf-8"))
OUT = ROOT / "eval" / "candidates.jsonl"

PROMPT = """你在为知识库出评测题。下面是资料中的一个片段。

【资料】《{name}》 {locator}
{text}

要求：
1. 出一个**业务人员会问的业务问题**，例如"会员等级怎么设计""储值活动有什么好处"；
2. 严禁出现"这段""片段""录音""上面说的"这类指代资料本身的说法；
3. 答案必须能从上面片段中找到依据；
4. 给出 2-4 条答案要点；
5. 摘出片段中最能支撑答案的一句原文作为依据。

只输出 JSON：
{{"question": "...", "answer_points": ["...", "..."], "quote": "原文句子"}}
"""

NEG_PROMPT = """你在为知识库出"拒答题"。下面是资料中的一个片段。

【资料】《{name}》 {locator}
{text}

请提出一个**与这段内容主题相关、但这段话并没有回答**的问题。
例如这段讲会员等级设计，就问"会员等级每年调整几次"这种文中没说的。
问题要自然、具体，不能是"这段讲了什么"。

只输出 JSON：
{{"question": "..."}}
"""


def parse_json(txt):
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("no json")
    return json.loads(txt[a:b + 1])


def call(prompt, retries=2):
    for i in range(retries + 1):
        try:
            r = requests.post(
                CFG.get("base_url", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {CFG['api_key']}", "Content-Type": "application/json"},
                json={"model": CFG.get("model", "deepseek-chat"),
                      "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.3, "max_tokens": 500},
                timeout=90)
            r.raise_for_status()
            return parse_json(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            if i == retries:
                raise
            time.sleep(2)


def mmss(sec):
    sec = int(sec or 0)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def load_segments():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT s.video_id, s.locator, s.start, s.text, v.name, v.kind
        FROM segments s JOIN videos v ON v.id = s.video_id
        WHERE v.status='ready' AND v.deleted_at IS NULL
          AND length(s.text) BETWEEN 30 AND 1200
    """).fetchall()
    con.close()
    # 过滤 ASR 噪声（重复词太多、字符多样性太低）
    return [r for r in rows if len(set(r["text"])) / max(1, len(r["text"])) > 0.22]


BAD_Q = ("这段", "片段", "录音", "上面", "刚才", "讲了什么", "内容是什么", "本段")


def usable(item):
    q = item.get("question", "")
    if len(q) < 6 or any(b in q for b in BAD_Q):
        return False
    if not item.get("answer_points"):
        return False
    return True


def pick(rows, kind, n, rng):
    pool = [r for r in rows if r["kind"] == kind]
    rng.shuffle(pool)
    # 按文档轮转，避免全来自同一份
    by_doc = {}
    for r in pool:
        by_doc.setdefault(r["video_id"], []).append(r)
    picked, i = [], 0
    while len(picked) < n and any(by_doc.values()):
        for vid in list(by_doc):
            if by_doc[vid] and len(picked) < n:
                picked.append(by_doc[vid].pop())
        i += 1
        if i > 50:
            break
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", type=int, default=60)
    ap.add_argument("--pdf", type=int, default=30)
    ap.add_argument("--docx", type=int, default=10)
    ap.add_argument("--image", type=int, default=10)
    ap.add_argument("--neg", type=int, default=20)
    args = ap.parse_args()

    rng = random.Random(42)
    rows = load_segments()
    print("候选片段池:", len(rows))

    plan = []
    for kind, n in (("video", args.video), ("pdf", args.pdf),
                    ("docx", args.docx), ("image", args.image)):
        plan += [(kind, r) for r in pick(rows, kind, n, rng)]
    negatives = pick(rows, "video", args.neg, rng)
    print("计划出题:", len(plan), "+ 负样本", len(negatives))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = 0
    with open(OUT, "w", encoding="utf-8") as f:
        idx = 1
        for kind, r in plan:
            loc = r["locator"] or mmss(r["start"])
            q = call(PROMPT.format(name=r["name"], locator=loc, text=r["text"][:1200]))
            item = {"id": f"q{idx:03d}", "type": "fact", "kind": kind,
                    "question": q.get("question", "").strip(),
                    "answer_points": [p for p in q.get("answer_points", []) if p][:4],
                    "sources": [{"video_id": r["video_id"], "locator": loc,
                                 "name": r["name"], "quote": q.get("quote", "")[:200]}],
                    "chunk_text": r["text"][:600]}
            if usable(item):
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
                done += 1
            idx += 1
            if done % 10 == 0:
                print(f"  {done}/{len(plan)}", flush=True)

        for r in negatives:
            loc = r["locator"] or mmss(r["start"])
            q = call(NEG_PROMPT.format(name=r["name"], locator=loc, text=r["text"][:1200]))
            item = {"id": f"q{idx:03d}", "type": "negative", "kind": "negative",
                    "question": q.get("question", "").strip(), "answer_points": [],
                    "sources": [], "chunk_text": r["text"][:300]}
            if item["question"] and not any(b in item["question"] for b in BAD_Q):
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
                done += 1
            idx += 1
    print(f"完成：{done} 条 -> {OUT}")


if __name__ == "__main__":
    main()

