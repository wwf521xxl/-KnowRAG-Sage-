"""Daily digest: what was added, what failed, how much space is used.

Usage:
    python report.py            # print + write data/logs/report-YYYYMMDD.md
    set KB_WEBHOOK=...          # optional: POST the text to a webhook (WeCom/DingTalk)
"""
import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "kb.db"
LOGS = ROOT / "data" / "logs"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    added = cur.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(duration),0) d FROM videos "
        "WHERE created_at >= datetime('now','-1 day') AND deleted_at IS NULL").fetchone()
    total = cur.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(duration),0) d, COALESCE(SUM(size),0) s "
        "FROM videos WHERE deleted_at IS NULL").fetchone()
    ready = cur.execute("SELECT COUNT(*) n FROM videos WHERE status='ready' AND deleted_at IS NULL").fetchone()["n"]
    failed = cur.execute("SELECT id,name,error FROM videos WHERE status='failed' AND deleted_at IS NULL").fetchall()
    pending = cur.execute("SELECT COUNT(*) n FROM videos WHERE status NOT IN ('ready','failed') "
                          "AND deleted_at IS NULL").fetchone()["n"]
    trash = cur.execute("SELECT COUNT(*) n FROM videos WHERE deleted_at IS NOT NULL").fetchone()["n"]
    con.close()

    day = date.today().isoformat()
    lines = [
        f"# 知识库日报 {day}",
        "",
        f"- 库内：{total['n']} 个视频 / {total['d'] / 3600:.1f} 小时 / {total['s'] / 1e9:.1f} GB",
        f"- 状态：可用 {ready}，处理中 {pending}，失败 {len(failed)}",
        f"- 昨日新增：{added['n']} 个 / {added['d'] / 60:.0f} 分钟",
        f"- 回收站：{trash} 条",
    ]
    if failed:
        lines += ["", "## 需要处理", ""]
        for f in failed:
            lines.append(f"- #{f['id']} {f['name']}: {(f['error'] or '')[:80]}")

    text = "\n".join(lines)
    LOGS.mkdir(parents=True, exist_ok=True)
    out = LOGS / f"report-{day}.md"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n(已写入 {out})")

    hook = os.environ.get("KB_WEBHOOK")
    if hook:
        try:
            requests.post(hook, json={"msgtype": "text", "text": {"content": text}}, timeout=10)
            print("webhook sent")
        except Exception as e:
            print("webhook failed:", type(e).__name__, str(e)[:80])


if __name__ == "__main__":
    main()
