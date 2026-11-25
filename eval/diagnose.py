"""逐条诊断未召回的题：gold 块在 BM25 / 向量 / 融合 各排第几。"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"D:\知识库问答系统")
sys.path.insert(0, str(ROOT))
import kb_server as kb  # noqa: E402

EVAL = ROOT / "eval"
gold = [json.loads(l) for l in (EVAL / "golden.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
last = json.loads((EVAL / "last_run.json").read_text(encoding="utf-8"))
miss_ids = {r["question"] for r in last["rows"] if r["type"] != "negative" and not r["ranks"]}


def sec(loc):
    m = re.match(r"^(\d+):(\d+)", str(loc or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


idx = kb.load_index(force=True)
emb = kb.get_embedder()
segs = idx["segs"]
print(f"索引 {len(segs)} 块，待诊断 {len(miss_ids)} 题\n")

rows = []
for it in gold:
    if it["question"] not in miss_ids:
        continue
    q = it["question"]
    qv = emb.encode([q])[0]

    bm = kb.bm25([q], limit=len(segs))
    bm_rank = {id(s): i for i, (_, s) in enumerate(bm, 1)}

    vec = sorted(((float(s["vec"] @ qv), s) for s in segs if s.get("vec") is not None),
                 key=lambda x: -x[0])
    vec_rank = {id(s): i for i, (_, s) in enumerate(vec, 1)}

    fused = {}
    for sid, r in bm_rank.items():
        fused[sid] = fused.get(sid, 0) + 1 / (60 + r)
    for sid, r in vec_rank.items():
        fused[sid] = fused.get(sid, 0) + 1 / (60 + r)
    fused_rank = {sid: i for i, (sid, _) in enumerate(sorted(fused.items(), key=lambda kv: -kv[1]), 1)}

    src = it["sources"][0]
    t = sec(src["locator"])
    cands = []
    for s in segs:
        if s["video_id"] != src["video_id"]:
            continue
        if t is not None:
            if s["start"] - 30 <= t <= s["end"] + 30:
                cands.append(s)
        elif str(s["locator"]) == str(src["locator"]):
            cands.append(s)

    if not cands:
        rows.append({"q": q, "state": "label_mismatch", "gold": src["locator"]})
        continue
    # 取所有覆盖 gold 的块里，融合排名最好的那个
    best = min(cands, key=lambda s: fused_rank.get(id(s), 10 ** 9))
    rows.append({
        "q": q, "state": "ok",
        "gold": src["locator"],
        "bm": bm_rank.get(id(best)),
        "vec": vec_rank.get(id(best)),
        "fused": fused_rank.get(id(best)),
        "cands": len(cands),
        "top1": f'{bm[0][1]["locator"] if bm else "?"}',
    })

counts = {}
for r in rows:
    if r["state"] != "ok":
        k = "① 标签对不上块"
    elif r["fused"] and r["fused"] <= 6:
        k = "④ 已召回但没引用"
    elif r["fused"] and r["fused"] <= 15:
        k = "③ 进了重排但被刷掉"
    elif (r["bm"] and r["bm"] <= 30) or (r["vec"] and r["vec"] <= 30):
        k = "② 单路能召回、融合没进前15"
    else:
        k = "⑤ 两路都没召回"
    counts[k] = counts.get(k, 0) + 1
    print(f'{k} | {r["q"][:34]} | gold {r["gold"]} | bm {r.get("bm")} | vec {r.get("vec")} | fused {r.get("fused")}')

print("\n分类统计：")
for k in sorted(counts):
    print(f"  {k}: {counts[k]}")
(Path(EVAL) / "diagnose.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
