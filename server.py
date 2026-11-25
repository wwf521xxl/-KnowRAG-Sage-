"""Local demo service: serve the page and answer questions over the transcript with DeepSeek."""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.local.json").read_text(encoding="utf-8"))
API_KEY = CFG["api_key"]
BASE_URL = CFG.get("base_url", "https://api.deepseek.com").rstrip("/")
MODEL = CFG.get("model", "deepseek-chat")

from build_demo import CHAPTERS, FIX, fix  # noqa: E402  (术语校对表与章节目录复用)

TITLE = "为什么说保罗·乔治是 NBA 的「硬通货」"
SEGS = json.loads((ROOT / "data" / "text" / "demo" / "segments.json").read_text(encoding="utf-8"))
ROWS = [{"start": s["start"], "text": fix(s["text"])} for s in SEGS]


def mmss(sec):
    s = int(sec)
    return f"{s // 60:02d}:{s % 60:02d}"


def build_context(limit_chars=20000):
    lines, total, ci = [], 0, 0
    for i, r in enumerate(ROWS, 1):
        while ci < len(CHAPTERS) and CHAPTERS[ci][0] <= r["start"] + 0.01:
            block = f"\n## 章节 {mmss(CHAPTERS[ci][0])} · {CHAPTERS[ci][1]}"
            lines.append(block)
            total += len(block)
            ci += 1
        line = f"[{i}] ({mmss(r['start'])}) {r['text']}"
        lines.append(line)
        total += len(line)
        if total > limit_chars:
            break
    return "\n".join(lines)


SYSTEM = """你是「视频知识库」助手，服务于没时间看原视频的人。你只能依据给定的【逐字稿】回答。

规则：
1. 只使用逐字稿中的信息；不要用常识补事实。
2. 每个事实性陈述后面标注来源句子编号，如 [3][7]，编号必须是逐字稿里真实存在的。
3. 允许基于上下文做直接推断，并在句中标注「（推断）」，同时给出依据编号。
   例如逐字稿说「来到凯尔特人的第一场……他成了主角」「他想证明自己比杰伦·布朗更加适配凯尔特人」，
   就可以推断他当时在凯尔特人打球（推断）[19][26][27]。
   整段解说围绕同一个人展开时，后续省略主语的句子默认指这个人，不要因为没重复姓名就拒答。
4. 涉及数字、比分、金额、合同的内容，逐字稿不清楚就说不确定，绝对不要猜。
5. 只有在逐字稿完全没有相关线索时，才回答“资料中没有提到”，并说明缺的是什么。
   只要线索足以推出一个最可能的答案，就给出答案并标注「（推断）」，不得以“未明确说明”为由拒答。
6. 不得编造时间戳、人名、球队名。
7. 回答结构：先给结论（1-2 句），再给 2-4 条要点（每条一个短句）。
8. 不要大段复述原文，单条引用不超过 30 字；用简体中文回答。"""


def ask_llm(question):
    context = build_context()
    user = (
        f"【视频】{TITLE}（时长 01:22）\n\n"
        f"【逐字稿】（## 开头的是人工校对的章节标题，可作定位线索）\n{context}\n\n"
        f"【问题】\n{question}"
    )
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_tokens": 700,
    }
    r = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    r.raise_for_status()
    data = r.json()
    answer = data["choices"][0]["message"]["content"].strip()
    used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
    cites = []
    for n in used:
        if 1 <= n <= len(ROWS):
            cites.append({"n": n, "t": ROWS[n - 1]["start"], "time": mmss(ROWS[n - 1]["start"])})
    usage = data.get("usage", {})
    return answer, cites, usage


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (ROOT / "demo.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._send(200, json.dumps({"ok": True, "segments": len(ROWS)}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/api/ask":
            self._send(404, json.dumps({"error": "not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length).decode("utf-8"))
            question = (req.get("question") or "").strip()
            if not question:
                self._send(400, json.dumps({"error": "空问题"}))
                return
            answer, cites, usage = ask_llm(question)
            self._send(200, json.dumps(
                {"answer": answer, "cites": cites, "usage": usage}, ensure_ascii=False))
        except Exception as e:
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"serving http://127.0.0.1:{port}  model={MODEL} segments={len(ROWS)}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
