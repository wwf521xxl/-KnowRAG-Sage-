import os
import sqlite3

con = sqlite3.connect(r"D:\知识库问答系统\data\kb.db")
con.row_factory = sqlite3.Row
rows = con.execute("SELECT id,name,duration,status,path FROM videos ORDER BY id").fetchall()

groups = {}
for r in rows:
    key = os.path.basename(os.path.dirname(r["path"]))
    groups.setdefault(key, []).append(r)

for key, items in groups.items():
    hours = sum(i["duration"] or 0 for i in items) / 3600
    print(f"[{key}] {len(items)} 条 / {hours:.1f} 小时")
    for i in items:
        print(f"   #{i['id']:<3} {i['status']:<12} {i['name'][:50]}")
