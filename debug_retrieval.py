import sys

sys.path.insert(0, r"D:\知识库问答系统")
import kb_server as k

q = "乔治为什么被叫作NBA硬通货？"
idx = k.load_index(force=True)
queries = [q] + k.expand_query(q)
print("queries:", queries)
hits = k.bm25(queries, limit=6)
print("hits:")
for score, s in hits:
    print(f"  {score:.2f} vid={s['video_id']} {k.mmss(s['start'])} len={len(s['text'])}")
chosen = {id(s): s for _, s in hits}
for _, s in hits[:3]:
    prev = [c for c in idx["segs"] if c["video_id"] == s["video_id"] and c["start"] < s["start"]]
    if prev:
        chosen[id(prev[-1])] = prev[-1]
ordered = sorted(chosen.values(), key=lambda c: (c["video_id"], c["start"]))
print("\ncontext:")
for i, s in enumerate(ordered, 1):
    print(f"[{i}] vid={s['video_id']} {k.mmss(s['start'])}: {s['text'][:80]}")
print("\nvideo1 chunks:", [(k.mmss(c["start"]), len(c["text"])) for c in idx["segs"] if c["video_id"] == 1])
