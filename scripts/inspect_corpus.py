import json
import sqlite3

con = sqlite3.connect(r"D:\知识库问答系统\data\kb.db")
con.row_factory = sqlite3.Row
rows = con.execute("SELECT id,name,duration,status,summary,outline_json FROM videos ORDER BY id").fetchall()

for r in rows:
    outline = json.loads(r["outline_json"] or "{}")
    chapters = outline.get("chapters", [])
    mins = (r["duration"] or 0) / 60
    print(f"#{r['id']} {r['name'].strip()}  {mins:.0f} 分钟  {r['status']}  章节 {len(chapters)}")
    print("   摘要：", (r["summary"] or "")[:140])
    for ch in chapters[:5]:
        start = int(ch.get("start", 0))
        print(f"     {start // 60:02d}:{start % 60:02d}  {ch.get('title', '')}")
    print()
