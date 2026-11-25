"""跑评测：召回 / 引用 / 拒答 / 延迟。

用法：
    python eval/run_eval.py                     # 跑一遍，打印指标
    python eval/run_eval.py --save-baseline     # 存为基线
    python eval/run_eval.py --check             # 和基线比，掉太多则退出码 1
"""
import argparse
import json
import math
import re
import statistics
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
API = "http://127.0.0.1:8010"
CFG = json.loads((ROOT / "config.local.json").read_text(encoding="utf-8"))
BASELINE = EVAL / "baseline.json"
LAST = EVAL / "last_run.json"

# 允许的下降幅度 / 最低要求
GATE = {
    "recall@5": {"min": 0.75, "drop_max": 0.04},
    "mrr": {"min": 0.60, "drop_max": 0.04},
    "citation_recall": {"min": 0.75, "drop_max": 0.04},
    "refusal_accuracy": {"min": 0.85, "drop_max": 0.05},
}


def login():
    s = requests.Session()
    s.post(API + "/api/login",
           json={"username": CFG.get("auth", {}).get("username", "boss"),
                 "password": PASSWORD}, timeout=10)
    return s


def parse_loc(loc):
    if not loc:
        return None
    s = str(loc)
    if s.startswith("p") and s[1:].isdigit():
        return ("page", int(s[1:]))
    m = re.match(r"^(\d+):(\d+)", s)
    if m:
        return ("time", int(m.group(1)) * 60 + int(m.group(2)))
    return ("label", s)


def match(gold, cand):
    """同一文档 + 定位接近，算命中。"""
    if int(gold["video_id"]) != int(cand["video_id"]):
        return False
    g, c = parse_loc(gold.get("locator")), parse_loc(cand.get("locator"))
    if g is None or c is None:
        return True
    if g[0] == "time" and c[0] == "time":
        start = c[1]
        end = cand.get("end") or start
        # 块覆盖区间内命中；或起点相差 90 秒内
        if start - 30 <= g[1] <= end + 30:
            return True
        return abs(g[1] - start) <= 90
    if g[0] == "page" and c[0] == "page":
        return abs(g[1] - c[1]) <= 1
    # Word/图片的"第N段"：看块的 seq 区间是否覆盖
    m = re.match(r"^第(\d+)段$", str(gold.get("locator") or ""))
    if m and cand.get("seq_start") is not None:
        n = int(m.group(1)) - 1
        return cand["seq_start"] <= n <= cand["seq_end"]
    return g == c


def match_cite(gold, cite, tol=180):
    """引用匹配：同文档且时间相差 tol 秒内（默认 3 分钟，容忍相邻块）。"""
    if int(gold["video_id"]) != int(cite["video_id"]):
        return False
    g, c = parse_loc(gold.get("locator")), parse_loc(cite.get("locator"))
    if g is None or c is None:
        return True
    if g[0] == "time" and c[0] == "time":
        return abs(g[1] - c[1]) <= tol
    if g[0] == "page" and c[0] == "page":
        return abs(g[1] - c[1]) <= 1
    return g == c


def is_refusal(answer):
    return ("没有提到" in answer) or ("资料中没有" in answer) or ("没有相关内容" in answer)


def p95(values):
    if not values:
        return 0
    values = sorted(values)
    k = max(0, int(math.ceil(len(values) * 0.95)) - 1)
    return values[k]


def run(items, session):
    rows = []
    for n, it in enumerate(items, 1):
        t = time.time()
        r = session.post(API + "/api/ask",
                         json={"question": it["question"], "debug": True}, timeout=180)
        wall = round((time.time() - t) * 1000)
        d = r.json()
        dbg = d.get("debug") or {}
        retrieved = dbg.get("retrieved") or []
        cites = d.get("cites") or []
        answer = d.get("answer") or ""

        rec = {"id": it.get("id"), "type": it.get("type", "fact"),
               "question": it["question"], "answer": answer[:400],
               "latency_ms": wall, "ranks": [], "citation_hits": 0,
               "citation_hits_strict": 0,
               "citation_total": len(cites), "refused": is_refusal(answer)}
        if it.get("sources"):
            for rank, cand in enumerate(retrieved[:10], 1):
                if any(match(g, cand) for g in it["sources"]):
                    rec["ranks"].append(rank)
            rec["citation_hits"] = sum(
                1 for c in cites if any(match_cite(g, c, 180) for g in it["sources"]))
            rec["citation_hits_strict"] = sum(
                1 for c in cites if any(match_cite(g, c, 90) for g in it["sources"]))
        rows.append(rec)
        if n % 10 == 0:
            print(f"  {n}/{len(items)}", flush=True)
    return rows


def compute(rows):
    pos = [r for r in rows if r["type"] != "negative"]
    neg = [r for r in rows if r["type"] == "negative"]

    recall5 = (sum(1 for r in pos if r["ranks"] and min(r["ranks"]) <= 5) / len(pos)) if pos else 0
    mrr = (sum(1.0 / min(r["ranks"]) for r in pos if r["ranks"]) / len(pos)) if pos else 0
    cite_total = sum(r["citation_total"] for r in pos)
    cite_hit = sum(r["citation_hits"] for r in pos)
    cite_prec = (cite_hit / cite_total) if cite_total else 0
    # 引用召回：gold 出处是否出现在引用里（比 precision 更贴近"引用对不对"）
    cite_recall = (sum(1 for r in pos if r["citation_hits"] > 0) / len(pos)) if pos else 0
    cite_recall_strict = (sum(1 for r in pos if r["citation_hits_strict"] > 0) / len(pos)) if pos else 0
    avg_cites = round(cite_total / len(pos), 2) if pos else 0
    refusal = (sum(1 for r in neg if r["refused"]) / len(neg)) if neg else 0
    lats = [r["latency_ms"] for r in rows]
    return {"recall@5": round(recall5, 3), "mrr": round(mrr, 3),
            "citation_precision": round(cite_prec, 3),
            "citation_recall": round(cite_recall, 3),
            "citation_recall_strict": round(cite_recall_strict, 3),
            "avg_cites": avg_cites,
            "refusal_accuracy": round(refusal, 3),
            "median_latency_ms": round(statistics.median(lats)) if lats else 0,
            "p95_latency_ms": p95(lats), "n": len(rows), "n_positive": len(pos), "n_negative": len(neg)}


def main():
    global PASSWORD
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(EVAL / "golden.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--password", default="123456")
    ap.add_argument("--save-baseline", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    PASSWORD = args.password

    path = Path(args.file)
    if not path.exists():
        print(f"找不到 {path}，先用 build_candidates.py 生成候选")
        return 1
    items = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        items = items[:args.limit]
    print(f"评测 {len(items)} 条：{path.name}")

    session = login()
    if session.get(API + "/api/videos", timeout=10).status_code != 200:
        print("登录失败或服务未启动")
        return 1
    rows = run(items, session)
    m = compute(rows)
    LAST.write_text(json.dumps({"metrics": m, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n指标")
    print(f"  Recall@5          {m['recall@5']:.3f}")
    print(f"  MRR               {m['mrr']:.3f}")
    print(f"  引用召回（±3分）   {m['citation_recall']:.3f}")
    print(f"  引用召回（±90秒）  {m['citation_recall_strict']:.3f}")
    print(f"  平均引用数         {m['avg_cites']}")
    print(f"  引用准确率         {m['citation_precision']:.3f}")
    print(f"  拒答准确率         {m['refusal_accuracy']:.3f}")
    print(f"  延迟 中位/P95      {m['median_latency_ms']} / {m['p95_latency_ms']} ms")
    print(f"  样本               {m['n']}（正 {m['n_positive']} / 负 {m['n_negative']}）")

    if args.save_baseline:
        BASELINE.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已保存基线 -> {BASELINE}")
        return 0

    if args.check:
        if not BASELINE.exists():
            print("\n没有基线，先跑 --save-baseline")
            return 1
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        bad = []
        for k, g in GATE.items():
            cur, old = m[k], base.get(k, 0)
            if cur < g["min"]:
                bad.append(f"{k} 低于下限：{cur:.3f} < {g['min']}")
            elif old - cur > g["drop_max"]:
                bad.append(f"{k} 下降过多：{old:.3f} -> {cur:.3f}")
        if bad:
            print("\n门禁未通过：")
            for b in bad:
                print("  -", b)
            return 1
        print("\n门禁通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
