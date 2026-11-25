import os
import sqlite3

DB = r"D:\知识库问答系统\data\kb.db"
con = sqlite3.connect(DB)
cols = [r[1] for r in con.execute("PRAGMA table_info(videos)")]
if "course" not in cols:
    con.execute("ALTER TABLE videos ADD COLUMN course TEXT")
    print("videos + course")

rows = con.execute("SELECT id, path FROM videos").fetchall()
for vid, path in rows:
    parent = os.path.basename(os.path.dirname(path))
    course = "未分类" if parent.lower() in ("raw", "inbox") else parent
    con.execute("UPDATE videos SET course=? WHERE id=?", (course, vid))
con.commit()
print(dict(con.execute("SELECT course, COUNT(1) FROM videos GROUP BY course").fetchall()))
