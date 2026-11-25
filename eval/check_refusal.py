import os
"""用 10 条“明显超出资料范围”的问题测拒答能力，并更新 baseline。"""
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
CFG = json.loads((ROOT / "config.local.json").read_text(encoding="utf-8"))
API = "http://127.0.0.1:8010"

JUDGE = """判断回答是否给出了具体答案。只说明“资料中没有/未提及”或只给背景 → false；给出明确具体答案 → true。
【问题】{q}
【回答】{a}
只输出 JSON：{{"answered": true, "reason": "一句话"}}"""


def judge(q, a):
    r = requests.post(
        CFG.get("base_url", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {CFG['api_key']}", "Content-Type": "application/json"},
        json={"model": CFG.get("model", "deepseek-chat"),
              "messages": [{"role": "user", "content": JUDGE.format(q=q, a=a[:700])}],
              "temperature": 0, "max_tokens": 120}, timeout=60)
    t = r.json()["choices"][0]["message"]["content"]
    a_, b_ = t.find("{"), t.rfind("}")
    return json.loads(t[a_:b_ + 1])


def main():
    s = requests.Session()
    s.post(API + "/api/login", json={"username": "boss", "password": os.environ.get("KB_PASS", "")}, timeout=10)
    qs = json.loads((EVAL / "negatives_manual.json").read_text(encoding="utf-8"))
    ok = 0
    rows = []
    for it in qs:
        d = s.post(API + "/api/ask", json={"question": it["question"]}, timeout=120).json()
        j = judge(it["question"], d.get("answer", ""))
        refused = not j.get("answered")
        ok += 1 if refused else 0
        rows.append({"q": it["question"], "refused": refused, "answer": d["answer"][:120]})
        print(("✅" if refused else "❌"), it["question"][:30], "|", d["answer"][:50].replace("\n", " "))

    rate = round(ok / len(qs), 3)
    print(f"\n拒答准确率 {rate}  ({ok}/{len(qs)})")

    base_p = EVAL / "baseline.json"
    if base_p.exists():
        m = json.loads(base_p.read_text(encoding="utf-8"))
        m["refusal_accuracy"] = rate
        m["n_negative"] = len(qs)
        base_p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print("baseline 已更新")
    (EVAL / "refusal_run.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
