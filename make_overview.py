import json
import sqlite3
from pathlib import Path

DB = r"D:\知识库问答系统\data\kb.db"
OUT = Path(r"D:\知识库问答系统\data\export\课程总览.md")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute("SELECT id,name,duration,summary,outline_json FROM videos ORDER BY id").fetchall()

lines = ["# 五天闭门会 · 课程总览", ""]
total = sum((r["duration"] or 0) for r in rows)
lines.append(f"共 {len(rows)} 个视频，{total / 3600:.1f} 小时。以下摘要与章节由模型根据逐字稿生成。")
lines.append("")

for r in rows:
    o = json.loads(r["outline_json"] or "{}")
    mins = int((r["duration"] or 0) // 60)
    lines.append(f"## {r['name'].strip()}")
    lines.append("")
    lines.append(f"`{mins // 60}:{mins % 60:02d}` · {len(o.get('chapters', []))} 章 · 关键词：{'、'.join(o.get('keywords', [])[:6])}")
    lines.append("")
    lines.append(r["summary"] or "")
    lines.append("")
    lines.append("| 时间 | 章节 |")
    lines.append("|---|---|")
    for ch in o.get("chapters", []):
        s = int(ch.get("start", 0))
        lines.append(f"| {s // 60:02d}:{s % 60:02d} | {ch.get('title', '')} |")
    lines.append("")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print("wrote", OUT, len(lines), "lines")
