"""Delete library records (and generated files) that do not belong to the 三把刀 course."""
import shutil
import sqlite3
from pathlib import Path

DB = Path(r"D:\知识库问答系统\data\kb.db")
LIB = Path(r"D:\知识库问答系统\data\library")
EXPORT = Path(r"D:\知识库问答系统\data\export")
KEEP = "三把刀宋老师"

con = sqlite3.connect(DB, timeout=15)
con.row_factory = sqlite3.Row
rows = con.execute("SELECT id,name,status,path FROM videos").fetchall()
victims = [r for r in rows if KEEP not in (r["path"] or "")]

print("将删除：")
for r in victims:
    print(f"  #{r['id']:<3} {r['status']:<12} {r['name'][:50]}")
print(f"\n保留 {len(rows) - len(victims)} 条，删除 {len(victims)} 条\n")

ids = [r["id"] for r in victims]
if ids:
    q = ",".join("?" * len(ids))
    con.execute(f"DELETE FROM segments WHERE video_id IN ({q})", ids)
    con.execute(f"DELETE FROM videos WHERE id IN ({q})", ids)
    con.commit()
con.close()

removed_dirs = 0
for vid in ids:
    for base in (LIB, EXPORT):
        if not base.exists():
            continue
        for p in base.glob(f"{vid:04d}_*"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            removed_dirs += 1

con = sqlite3.connect(DB)
left = con.execute("SELECT COUNT(*), COALESCE(SUM(duration),0) FROM videos").fetchone()
print(f"清理完成：删除记录 {len(ids)} 条、文件目录 {removed_dirs} 个")
print(f"库内剩余 {left[0]} 条 / {left[1] / 3600:.1f} 小时")
