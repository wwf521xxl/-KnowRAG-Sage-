"""对负样本用 LLM 复核：是否真的回答了，而不是只说“没有提到”。

用法：python eval/rejudge.py
读 eval/last_run.json，更新 eval/baseline.json 的 refusal_accuracy。
"""
import json
import statistics
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
CFG = json.loads((ROOT / "config.local.json").read_text(encoding="utf-8"))

PROMPT = """判断下面的回答是否给出了**具体答案**。

【问题】{q}
【回答】{a}

规则：
- 如果回答只说明"资料中没有/未提及"，或只提供背景、没有回答所问的具体点 → answered=false
- 如果回答给出了明确的具体答案（哪怕是部分）→ answered=true
只输出 JSON：{{"answered": true, "reason": "一句话"}}
"""


def judge(q, a):
    r = requests.post(
        CFG.get("base_url", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {CFG['api_key']}", "Content-Type": "application/json"},
        json={"model": CFG.get("model", "deepseek-chat"),
              "messages": [{"role": "user", "content": PROMPT.format(q=q, a=a[:800])}],
              "temperature": 0, "max_tokens": 120},
        timeout=60)
    txt = r.json()["choices"][0]["message"]["content"]
    a_, b_ = txt.find("{"), txt.rfind("}")
    return json.loads(txt[a_:b_ + 1])


def main():
    d = json.loads((EVAL / "last_run.json").read_text(encoding="utf-8"))
    rows = d["rows"]
    pos = [r for r in rows if r["type"] != "negative"]
    neg = [r for r in rows if r["type"] == "negative"]

    answered = 0
    details = []
    for r in neg:
        try:
            j = judge(r["question"], r["answer"])
        except Exception:
            j = {"answered": not r["refused"], "reason": "judge failed"}
        if j.get("answered"):
            answered += 1
            details.append({"q": r["question"], "reason": j.get("reason", "")})

    refusal = round(1 - answered / len(neg), 3) if neg else 0
    m = d["metrics"]
    m["refusal_accuracy"] = refusal
    m["citation_recall"] = round(sum(1 for r in pos if r["citation_hits"] > 0) / len(pos), 3) if pos else 0
    m["avg_cites"] = round(sum(r["citation_total"] for r in pos) / len(pos), 2) if pos else 0
    m["median_latency_ms"] = round(statistics.median([r["latency_ms"] for r in rows]))
    (EVAL / "baseline.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    print("负样本", len(neg), "被判为“回答了”的", answered)
    for x in details:
        print("  -", x["q"][:40], "|", x["reason"][:50])
    print("\n修正后的指标：")
    for k in ("recall@5", "mrr", "citation_recall", "citation_precision",
              "avg_cites", "refusal_accuracy", "median_latency_ms", "p95_latency_ms"):
        print(f"  {k:18s} {m[k]}")


if __name__ == "__main__":
    main()
