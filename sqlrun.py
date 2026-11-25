import sqlite3
import sys

DB = r"D:\知识库问答系统\data\kb.db"
con = sqlite3.connect(DB)
con.execute(sys.argv[1])
con.commit()
print("ok, changed", con.total_changes)
