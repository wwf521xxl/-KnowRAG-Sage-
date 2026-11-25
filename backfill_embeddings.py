"""Add embedding column and backfill all existing segments."""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from embeddings import Embedder  # noqa: E402

DB = r"D:\知识库问答系统\data\kb.db"
con = sqlite3.connect(DB)
cols = [r[1] for r in con.execute("PRAGMA table_info(segments)")]
if "embedding" not in cols:
    con.execute("ALTER TABLE segments ADD COLUMN embedding BLOB")
    con.commit()
    print("segments + embedding")

rows = con.execute("SELECT id, text FROM segments WHERE embedding IS NULL AND text IS NOT NULL").fetchall()
print("to embed:", len(rows))
if not rows:
    sys.exit(0)

emb = Embedder()
t0 = time.time()
batch = 32
for i in range(0, len(rows), batch):
    part = rows[i:i + batch]
    vecs = emb.encode([r[1][:1000] for r in part], batch_size=batch)
    con.executemany("UPDATE segments SET embedding=? WHERE id=?",
                    [(v.astype("float32").tobytes(), r[0]) for v, r in zip(vecs, part)])
    con.commit()
print(f"embedded {len(rows)} in {time.time() - t0:.1f}s")
