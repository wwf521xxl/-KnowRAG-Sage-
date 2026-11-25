import sqlite3

DB = r"D:\知识库问答系统\data\kb.db"
con = sqlite3.connect(DB)

vcols = [r[1] for r in con.execute("PRAGMA table_info(videos)")]
scols = [r[1] for r in con.execute("PRAGMA table_info(segments)")]

if "kind" not in vcols:
    con.execute("ALTER TABLE videos ADD COLUMN kind TEXT DEFAULT 'video'")
    print("videos + kind")
if "pages" not in vcols:
    con.execute("ALTER TABLE videos ADD COLUMN pages INTEGER")
    print("videos + pages")
if "locator" not in scols:
    con.execute("ALTER TABLE segments ADD COLUMN locator TEXT")
    print("segments + locator")

con.commit()
print([r[1] for r in con.execute("PRAGMA table_info(videos)")])
print([r[1] for r in con.execute("PRAGMA table_info(segments)")])
