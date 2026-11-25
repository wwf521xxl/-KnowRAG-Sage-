"""Move one course's files into a dedicated folder and update the database paths."""
import re
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(r"D:\知识库问答系统")
DB = ROOT / "data" / "kb.db"
DEST = ROOT / "data" / "courses" / "会员营销课"
FIRST, LAST = 23, 41


def safe(name):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "").strip().rstrip(".")
    return s[:80] or "video"


con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute("SELECT id,name,path FROM videos WHERE id BETWEEN ? AND ? ORDER BY id",
                   (FIRST, LAST)).fetchall()
DEST.mkdir(parents=True, exist_ok=True)

moved = 0
for r in rows:
    src = Path(r["path"])
    if not src.exists():
        print(f"#{r['id']} 源文件不存在，跳过：{src.name}")
        continue
    dst = DEST / f"{safe(r['name'])}{src.suffix.lower()}"
    if dst.exists():
        dst = DEST / f"{safe(r['name'])}_{r['id']}{src.suffix.lower()}"
    shutil.move(str(src), str(dst))
    con.execute("UPDATE videos SET path=? WHERE id=?", (str(dst), r["id"]))
    moved += 1
con.commit()
con.close()

print(f"移动 {moved} 个文件到 {DEST}")
print("目录内文件数：", len(list(DEST.glob('*'))))
