"""Fix absolute paths in kb.db after moving the project folder to another machine."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "kb.db"
RAW = ROOT / "data" / "raw"

if not DB.exists():
    print("没有找到 data/kb.db，跳过")
    raise SystemExit(0)

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute("SELECT id, path FROM videos").fetchall()
fixed = 0
for r in rows:
    p = Path(r["path"])
    if p.exists():
        continue
    cand = RAW / p.name
    if cand.exists():
        con.execute("UPDATE videos SET path=? WHERE id=?", (str(cand), r["id"]))
        fixed += 1
        print(f"#{r['id']} -> {cand.name}")
    else:
        print(f"#{r['id']} 找不到原文件：{p}")
con.commit()
con.close()
print(f"路径修复完成：{fixed} 条")
