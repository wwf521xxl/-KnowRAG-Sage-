import json
from pathlib import Path

p = Path(r"D:\知识库问答系统\eval\last_run.json")
d = json.loads(p.read_text(encoding="utf-8"))
rows = d["rows"]

neg = [r for r in rows if r["type"] == "negative"]
print("负样本", len(neg), "拒答", sum(1 for r in neg if r["refused"]))
for r in neg[:8]:
    print(" -", r["question"][:40], "| refused:", r["refused"], "| cites:", r["citation_total"])
    print("   ans:", r["answer"][:70].replace("\n", " "))

pos = [r for r in rows if r["type"] != "negative"]
cites = [r["citation_total"] for r in pos]
hits = [r["citation_hits"] for r in pos]
print("\n正样本", len(pos), "平均引用数", round(sum(cites) / len(cites), 2))
print("有引用命中 gold 的题数", sum(1 for h in hits if h > 0))
print("引用命中率(按题)", round(sum(1 for h in hits if h > 0) / len(pos), 3))
no_cite = [r for r in pos if r["citation_total"] == 0]
print("无引用题数", len(no_cite))
