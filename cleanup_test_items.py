import sqlite3
from pathlib import Path

DB = r"D:\知识库问答系统\data\kb.db"
names = ("上传测试", "空白测试")
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(f"SELECT id,path FROM videos WHERE name IN ({','.join('?'*len(names))})",
                   names).fetchall()
for r in rows:
    con.execute("DELETE FROM segments WHERE video_id=?", (r["id"],))
    con.execute("DELETE FROM videos WHERE id=?", (r["id"],))
    p = Path(r["path"])
    if p.exists():
        p.unlink()
    print("removed", r["id"], p.name)
con.commit()
print("left:", con.execute("SELECT COUNT(1) FROM videos").fetchone()[0])
con.close()
