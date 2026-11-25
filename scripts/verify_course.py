import os
import sqlite3

import requests

B = "http://127.0.0.1:8010"
s = requests.Session()
s.post(B + "/api/login", json={"username": "boss", "password": os.environ.get("KB_PASS", "")}, timeout=10)
r = s.get(B + "/file/23", headers={"Range": "bytes=0-99"}, timeout=8)
print("file 23:", r.status_code, r.headers.get("Content-Type"), len(r.content))

con = sqlite3.connect(r"D:\知识库问答系统\data\kb.db")
print("path 23:", con.execute("SELECT path FROM videos WHERE id=23").fetchone()[0])
print("ready count:", con.execute(
    "SELECT COUNT(1) FROM videos WHERE status='ready' AND id BETWEEN 23 AND 41").fetchone()[0])
print("in folder:", con.execute(
    "SELECT COUNT(1) FROM videos WHERE path LIKE '%会员营销课%'").fetchone()[0])
