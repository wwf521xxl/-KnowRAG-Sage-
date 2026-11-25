import sqlite3

c = sqlite3.connect(r"D:\知识库问答系统\data\kb.db")
for k in ("video", "pdf", "docx", "image"):
    n = c.execute(
        "SELECT COUNT(1) FROM segments s JOIN videos v ON v.id=s.video_id "
        "WHERE v.kind=? AND length(s.text) BETWEEN 30 AND 1200", (k,)).fetchone()[0]
    print(k, n)
