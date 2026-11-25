import sqlite3

con = sqlite3.connect(r"D:\知识库问答系统\data\kb.db")
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT v.id, v.name, v.kind, COUNT(s.id) n FROM videos v LEFT JOIN segments s ON s.video_id=v.id "
    "WHERE v.name LIKE '%巨量%' GROUP BY v.id").fetchall()
for r in rows:
    print(dict(r))
locs = con.execute(
    "SELECT DISTINCT s.locator FROM segments s JOIN videos v ON v.id=s.video_id "
    "WHERE v.name LIKE '%巨量%' ORDER BY s.seq LIMIT 12").fetchall()
print("locators:", [x[0] for x in locs])
