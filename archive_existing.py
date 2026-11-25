"""Move already-processed inbox files into data/raw and update their paths."""
import re
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(r"D:\知识库问答系统")
DB = ROOT / "data" / "kb.db"
RAW = ROOT / "data" / "raw"


def safe(name):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "").strip().rstrip(".")
    return s[:40] or "doc"


con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute("SELECT id,name,path FROM videos WHERE path LIKE ?",
                   (str(ROOT / "data" / "inbox") + "%",)).fetchall()
RAW.mkdir(parents=True, exist_ok=True)
for r in rows:
    p = Path(r["path"])
    if not p.exists():
        continue
    dest = RAW / f"{r['id']:04d}_{safe(r['name'])}{p.suffix.lower()}"
    shutil.move(str(p), str(dest))
    con.execute("UPDATE videos SET path=? WHERE id=?", (str(dest), r["id"]))
    print(f"#{r['id']} -> {dest.name}")
con.commit()
print("remaining inbox files:", [q.name for q in (ROOT / "data" / "inbox").glob("*")])
