"""消融实验：BM25 / 向量 / 融合 / 融合+重排 的召回与延迟对比。"""
import json
import statistics
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.run_eval import match  # noqa: E402

API = "http://127.0.0.1:8010"
MODES = ["bm25", "vector", "hybrid", "hybrid_rerank"]
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 40
if len(sys.argv) > 2:
    MODES = sys.argv[2].split(",")

items = [json.loads(l) for l in (ROOT / "eval" / "golden.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
items = [x for x in items if x.get("sources")][:LIMIT]

s = requests.Session()
s.post(API + "/api/login", json={"username": "boss", "password": "123456"}, timeout=10)

results = {}
for mode in MODES:
    hits, mrr, lat = 0, 0.0, []
    for it in items:
        t = time.time()
        d = s.post(API + "/api/ask", json={"question": it["question"], "debug": True, "mode": mode}, timeout=180).json()
        lat.append((time.time() - t) * 1000)
        retrieved = (d.get("debug") or {}).get("retrieved") or []
        ranks = [i for i, c in enumerate(retrieved[:10], 1)
                 if any(match(g, c) for g in it["sources"])]
        if ranks:
            hits += 1
            mrr += 1.0 / min(ranks)
    n = len(items)
    results[mode] = {
        "recall@5": round(hits / n, 3),
        "mrr": round(mrr / n, 3),
        "median_ms": round(statistics.median(lat)),
        "p95_ms": round(sorted(lat)[max(0, int(n * 0.95) - 1)]),
    }
    print(mode, results[mode], flush=True)

(ROOT / "eval" / "ablation.json").write_text(
    json.dumps({"n": len(items), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")

print("\n| 检索方式 | Recall@5 | MRR | 中位延迟 | P95 |")
print("|---|---|---|---|---|")
for mode in MODES:
    r = results[mode]
    print(f"| {mode} | {r['recall@5']:.3f} | {r['mrr']:.3f} | {r['median_ms']} ms | {r['p95_ms']} ms |")
