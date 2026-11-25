"""Weekly digest: new content + question quality, written to data/reports/."""
import json
import os
import sqlite3
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "kb.db"
OUT = ROOT / "data" / "reports"
KIND_NAME = {"video": "视频", "pdf": "PDF", "docx": "Word", "image": "图片"}


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    since = "datetime('now','-7 days','localtime')"

    new = con.execute(
        f"SELECT kind, COUNT(*) n, COALESCE(SUM(duration),0) d FROM videos "
        f"WHERE created_at >= {since} AND deleted_at IS NULL GROUP BY kind").fetchall()
    total = con.execute("SELECT COUNT(*) n, COALESCE(SUM(duration),0) d FROM videos "
                        "WHERE deleted_at IS NULL").fetchone()
    qa = con.execute(f"SELECT COUNT(*) n FROM qa_logs WHERE created_at >= {since}").fetchone()["n"]
    up = con.execute(f"SELECT COUNT(*) n FROM qa_logs WHERE rating=1 AND created_at >= {since}").fetchone()["n"]
    down = con.execute(f"SELECT COUNT(*) n FROM qa_logs WHERE rating=-1 AND created_at >= {since}").fetchone()["n"]
    weak = con.execute(f"SELECT COALESCE(SUM(weak_count),0) n FROM qa_logs WHERE created_at >= {since}").fetchone()["n"]
    top = con.execute(f"SELECT question, COUNT(*) c FROM qa_logs WHERE created_at >= {since} "
                      "GROUP BY question ORDER BY c DESC LIMIT 5").fetchall()
    bad = con.execute(f"SELECT question FROM qa_logs WHERE rating=-1 AND created_at >= {since} "
                      "ORDER BY id DESC LIMIT 5").fetchall()
    missing = con.execute(f"SELECT question FROM qa_logs WHERE answer LIKE '%没有提到%' "
                          f"AND created_at >= {since} ORDER BY id DESC LIMIT 5").fetchall()
    con.close()

    lines = [f"# 知识库周报 · {date.today().isoformat()}", ""]
    lines.append(f"库内共 {total['n']} 条内容（{total['d'] / 3600:.1f} 小时视频）。")
    lines.append("")
    lines.append("## 本周新增")
    lines.append("")
    if new:
        for r in new:
            name = KIND_NAME.get(r["kind"], r["kind"])
            extra = f"，{r['d'] / 3600:.1f} 小时" if r["kind"] == "video" else ""
            lines.append(f"- {name} {r['n']} 条{extra}")
    else:
        lines.append("- 本周没有新增内容")
    lines.append("")
    lines.append("## 问答情况")
    lines.append("")
    lines.append(f"- 提问 {qa} 次｜👍 {up}｜👎 {down}｜弱引用 {weak} 条")
    ratio = (up / (up + down) * 100) if (up + down) else 0
    lines.append(f"- 有用率 {ratio:.0f}%（按已评价的算）")
    lines.append("")
    if top:
        lines.append("## 最常问")
        lines.append("")
        for r in top:
            lines.append(f"- {r['question']}（{r['c']} 次）")
        lines.append("")
    if bad:
        lines.append("## 需要改进（👎）")
        lines.append("")
        lines.extend(f"- {r['question']}" for r in bad)
        lines.append("")
    if missing:
        lines.append("## 没答上来（缺内容）")
        lines.append("")
        lines.extend(f"- {r['question']}" for r in missing)
        lines.append("")

    text = "\n".join(lines)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"weekly-{date.today().isoformat()}.md"
    path.write_text(text, encoding="utf-8")
    print(text)
    print(f"(已写入 {path})")

    hook = os.environ.get("KB_WEBHOOK")
    if hook:
        try:
            requests.post(hook, json={"msgtype": "markdown", "markdown": {"content": text}}, timeout=10)
            print("webhook sent")
        except Exception as e:
            print("webhook failed:", type(e).__name__)


if __name__ == "__main__":
    main()
