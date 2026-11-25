"""审核页：一条条看候选题，通过/删除，导出 golden.jsonl。

启动：
    .venv\\Scripts\\python.exe eval/review_server.py
打开：
    http://127.0.0.1:8020
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
CAND = EVAL / "candidates.jsonl"
STATE = EVAL / "review_state.json"
GOLDEN = EVAL / "golden.jsonl"

ITEMS = [json.loads(l) for l in CAND.read_text(encoding="utf-8").splitlines() if l.strip()]
STATE_DATA = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}

PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>评测题审核</title>
<style>
:root{--accent:#1f4e79;--sub:#5b6b7c;--line:#e3e8ee;--ok:#2f7d4f;--bad:#b03060}
*{box-sizing:border-box}
body{margin:0;font:15px/1.7 "Microsoft YaHei UI","PingFang SC",sans-serif;color:#1f2933;background:#f6f8fa}
header{background:var(--accent);color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center}
header b{font-size:16px}
.progress{font-size:13px;opacity:.9}
main{max-width:900px;margin:24px auto;padding:0 16px}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:22px 24px;box-shadow:0 2px 10px rgba(0,0,0,.04)}
.meta{font-size:12.5px;color:var(--sub);margin-bottom:10px;display:flex;gap:12px;flex-wrap:wrap}
.q{font-size:20px;font-weight:600;line-height:1.6;outline:none;padding:6px 8px;border-radius:8px}
.q:focus{background:#f0f6fc}
.label{font-size:12px;color:var(--sub);margin:16px 0 6px}
ul{margin:6px 0;padding-left:22px}
li{margin:3px 0}
.src{background:#f7fafd;border-left:3px solid #b9cde3;padding:10px 14px;border-radius:6px;font-size:13.5px;color:#334}
.src .name{color:var(--accent);font-weight:600;margin-right:8px}
details{margin-top:12px;font-size:13px;color:#4a5a6a}
details pre{white-space:pre-wrap;background:#fafbfc;border:1px solid var(--line);padding:10px;border-radius:6px;max-height:240px;overflow:auto}
footer{position:sticky;bottom:0;background:#fff;border-top:1px solid var(--line);padding:14px 24px;display:flex;gap:10px;justify-content:center}
button{font:inherit;padding:9px 18px;border-radius:9px;border:1px solid var(--line);background:#fff;cursor:pointer}
button.ok{background:#eaf6ef;border-color:#9fd0b4;color:#1d6b3f;font-weight:600}
button.bad{background:#fdeef3;border-color:#e6a8c0;color:#a02a52;font-weight:600}
button.ghost{color:var(--sub)}
button:hover{filter:brightness(.97)}
kbd{font-size:11px;border:1px solid #ccd;border-radius:4px;padding:0 4px;color:#667;background:#fafafa}
.empty{text-align:center;color:var(--sub);padding:60px}
</style></head>
<body>
<header><b>评测题审核</b><span class="progress" id="prog"></span></header>
<main><div id="area"></div></main>
<footer>
  <button class="ok" onclick="mark('approved')">✓ 通过 <kbd>A</kbd></button>
  <button class="bad" onclick="mark('rejected')">✗ 删除 <kbd>D</kbd></button>
  <button class="ghost" onclick="mark('pending')">跳过 <kbd>S</kbd></button>
  <button class="ghost" onclick="save()">保存到 golden.jsonl</button>
</footer>
<script>
const ITEMS = __ITEMS__;
let state = __STATE__;
let idx = 0, filter = 'pending';

function counts(){
  let a=0,r=0,p=0;
  ITEMS.forEach(it=>{const s=(state[it.id]||{}).status; if(s==='approved')a++; else if(s==='rejected')r++; else p++;});
  return {a,r,p,total:ITEMS.length};
}
function render(){
  const c = counts();
  document.getElementById('prog').textContent =
    `通过 ${c.a} · 删除 ${c.r} · 未审 ${c.p} / 共 ${c.total}`;
  const area = document.getElementById('area');
  const it = ITEMS[idx];
  if(!it){ area.innerHTML='<div class="empty">全部看完了，点「保存到 golden.jsonl」。</div>'; return; }
  const st = (state[it.id]||{}).status || 'pending';
  const q = (state[it.id]||{}).question || it.question;
  const src = (it.sources&&it.sources[0]) || {};
  area.innerHTML = `
   <div class="card">
     <div class="meta"><span>#${it.id}</span><span>${it.kind||''}</span><span>${it.type}</span>
       <span>状态：${st==='approved'?'已通过':st==='rejected'?'已删除':'未审'}</span>
       <span>${idx+1} / ${ITEMS.length}</span></div>
     <div class="q" contenteditable="true" id="qtext">${escapeHtml(q)}</div>
     <div class="label">答案要点</div>
     <ul>${(it.answer_points||[]).map(p=>`<li>${escapeHtml(p)}</li>`).join('')||'<li style="color:#999">（无）</li>'}</ul>
     <div class="label">出处</div>
     <div class="src"><span class="name">${escapeHtml(src.name||'')}</span>${escapeHtml(src.locator||'')}
       <div style="margin-top:4px">${escapeHtml((src.quote||'').slice(0,120))}</div></div>
     <details><summary>看原始片段</summary><pre>${escapeHtml(it.chunk_text||'')}</pre></details>
   </div>`;
  document.getElementById('qtext').addEventListener('input', e=>{
    state[it.id] = state[it.id] || {};
    state[it.id].question = e.target.textContent.trim();
  });
}
function escapeHtml(s){return String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function mark(status){
  const it = ITEMS[idx]; if(!it) return;
  state[it.id] = Object.assign({}, state[it.id], {status});
  next();
}
function next(){
  for(let k=idx+1;k<ITEMS.length;k++){
    if(filter==='pending' && !(state[ITEMS[k].id]||{}).status){ idx=k; render(); return; }
    if(filter==='all'){ idx=k; render(); return; }
  }
  // 后面没有未审的了，回到前面找
  for(let k=0;k<ITEMS.length;k++){
    if(filter==='pending' && !(state[ITEMS[k].id]||{}).status){ idx=k; render(); return; }
  }
  idx = ITEMS.length; render();
}
async function save(){
  const r = await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({state})});
  const d = await r.json();
  alert(`已保存：通过 ${d.approved} 条 → eval/golden.jsonl`);
}
document.addEventListener('keydown', e=>{
  if(e.target.isContentEditable) return;
  if(e.key==='a'||e.key==='A'){ mark('approved'); e.preventDefault(); }
  if(e.key==='d'||e.key==='D'){ mark('rejected'); e.preventDefault(); }
  if(e.key==='s'||e.key==='S'){ next(); e.preventDefault(); }
});
render();
</script></body></html>
"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/api/export"):
            return self._send(200, json.dumps({"ok": True}))
        html = PAGE.replace("__ITEMS__", json.dumps(ITEMS, ensure_ascii=False)) \
                   .replace("__STATE__", json.dumps(STATE_DATA, ensure_ascii=False))
        self._send(200, html)

    def do_POST(self):
        if self.path.startswith("/api/save"):
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            state = data.get("state", {})
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            approved = []
            for it in ITEMS:
                s = state.get(it["id"], {})
                if s.get("status") != "approved":
                    continue
                item = dict(it)
                if s.get("question"):
                    item["question"] = s["question"]
                item.pop("chunk_text", None)
                approved.append(item)
            GOLDEN.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in approved) + "\n",
                              encoding="utf-8")
            self._send(200, json.dumps({"ok": True, "approved": len(approved)}),
                       "application/json; charset=utf-8")
            return
        self._send(404, "not found")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8020
    print(f"review http://127.0.0.1:{port}  ({len(ITEMS)} 条待审)")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__":
    main()
