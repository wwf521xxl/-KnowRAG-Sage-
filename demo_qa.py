"""Minimal retrieval QA over timestamped sentences (no LLM needed).

Scores sentences with IDF-weighted character bigrams, returns top passages with timestamps.
This is the retrieval half of the product; the generation half plugs into the same hits.
"""
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

try:
    from zhconv import convert as to_simplified
except Exception:
    def to_simplified(t, _="zh-cn"):
        return t

PUNCT = re.compile(r"[\s，。！？；：、,.!?;:\"'“”‘’（）()\[\]【】—\-…·]")


def norm(text):
    return PUNCT.sub("", to_simplified(text, "zh-cn"))


def bigrams(s):
    return [s[i:i + 2] for i in range(len(s) - 1)] if len(s) > 1 else [s]


def fmt(sec):
    s = int(sec)
    return f"{s // 60:02d}:{s % 60:02d}"


def load(seg_path):
    segs = json.loads(Path(seg_path).read_text(encoding="utf-8"))
    docs = [norm(s["text"]) for s in segs]
    df = Counter()
    for d in docs:
        for g in set(bigrams(d)):
            df[g] += 1
    n = len(docs)
    return segs, docs, {g: math.log((n + 1) / (c + 0.5)) for g, c in df.items()}


def ask(query, segs, docs, idf, topk=3):
    q = norm(query)
    qs = set(bigrams(q))
    scored = []
    for i, d in enumerate(docs):
        hits = [g for g in qs if g in d]
        if not hits:
            continue
        score = sum(idf.get(g, 1.0) for g in hits) / math.sqrt(len(qs) + 1)
        # 完全命中查询中的名词短语时给一点奖励
        if q and q in d:
            score *= 1.5
        scored.append((score, i))
    scored.sort(reverse=True)
    return scored[:topk]


def main(seg_path, *questions):
    segs, docs, idf = load(seg_path)
    for q in questions:
        print(f"\n问：{q}")
        hits = ask(q, segs, docs, idf)
        if not hits or hits[0][0] < 0.9:
            print("答：资料中没有提到。")
            continue
        for rank, (score, idx) in enumerate(hits, 1):
            s = segs[idx]
            print(f"  [{rank}] {fmt(s['start'])}  {s['text']}   (score {score:.2f})")


if __name__ == "__main__":
    main(*sys.argv[1:])
