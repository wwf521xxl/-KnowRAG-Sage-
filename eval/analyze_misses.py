import json
from pathlib import Path

EVAL = Path(r"D:\知识库问答系统\eval")
d = json.loads((EVAL / "last_run.json").read_text(encoding="utf-8"))
rows = d["rows"]
pos = [r for r in rows if r["type"] != "negative"]
miss = [r for r in pos if not r["ranks"]]
print(f"正样本 {len(pos)}，召回失败 {len(miss)}")
for r in miss[:8]:
    print("-", r["question"][:44], "| cites:", r["citation_total"])
    print("   ans:", r["answer"][:80].replace("\n", " "))
low = [r for r in pos if r["ranks"] and min(r["ranks"]) > 3]
print(f"\n命中但排名靠后（>3）{len(low)}")
for r in low[:5]:
    print("-", r["question"][:40], "rank", r["ranks"][:3])
