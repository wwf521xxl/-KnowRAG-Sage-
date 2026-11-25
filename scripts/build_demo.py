"""Build a self-contained demo page (video + chapters + QA + transcript)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEG = ROOT / "data" / "text" / "demo" / "segments.json"
VIDEO = "视屏数据/e182316fa47e562613d45ab0f419b5c9.mp4"
OUT = ROOT / "demo.html"

# 术语校对：只改确定的同音/实体错误，不确定的保持原样
FIX = {
    "什么神秘硬通货": "什么才是硬通货",
    "欧拉迪坡": "奥拉迪波",
    "亚利山大": "亚历山大",
    "明星代队": "明星带队",
    "交易布朗": "交易包裹",
    "交易不朗": "交易包裹",
    "他同目的": "塔图姆的",
    "结论布朗": "杰伦·布朗",
    "比了一个中止": "比了一个中指",
    "现在的决策": "现在的角色",
    "绿菌": "绿军",
    "他这一次": "那这一次",
}


def fix(text):
    for a, b in FIX.items():
        text = text.replace(a, b)
    return text


def mmss(sec):
    s = int(sec)
    return f"{s // 60:02d}:{s % 60:02d}"


CHAPTERS = [
    (0, "开场：什么叫「硬通货」"),
    (3.5, "2017：步行者 → 雷霆"),
    (9.8, "连锁反应：小萨 → 哈利伯顿"),
    (15.1, "2019：雷霆 → 快船"),
    (21.6, "2025 总决赛：两队会师"),
    (24, "今夏再成交易筹码"),
    (33, "结论：NBA 硬通货"),
    (35, "凯尔特人首秀"),
    (42, "对球迷比中指"),
    (44, "角色转变：辅佐塔图姆"),
    (51, "他带来什么：投射、无球、协防"),
    (59, "36 岁：改变自己的命运"),
]

EXAMPLES = [
    "乔治去过哪些球队？",
    "他为什么被叫作 NBA 硬通货？",
    "他在凯尔特人的角色是什么？",
    "视频里提到他的合同金额是多少？",
]


def main():
    segs = json.loads(SEG.read_text(encoding="utf-8"))
    rows = [{"s": s["start"], "t": s["end"], "x": fix(s["text"])} for s in segs]

    html = TEMPLATE
    html = html.replace("__VIDEO__", VIDEO)
    html = html.replace("__SEGMENTS__", json.dumps(rows, ensure_ascii=False))
    html = html.replace("__CHAPTERS__", json.dumps(
        [{"t": t, "label": label, "time": mmss(t)} for t, label in CHAPTERS], ensure_ascii=False))
    html = html.replace("__EXAMPLES__", json.dumps(EXAMPLES, ensure_ascii=False))
    html = html.replace("__NSEG__", str(len(rows)))
    OUT.write_text(html, encoding="utf-8")
    print("wrote", OUT, len(html), "bytes")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>视频知识库 · 演示</title>
<style>
  :root { --ink:#1f2933; --sub:#52606d; --line:#e4e7eb; --accent:#1f4e79; --bg:#f7f9fc; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.7 "Microsoft YaHei","PingFang SC",system-ui,sans-serif; }
  .wrap { max-width: 960px; margin: 0 auto; padding: 28px 20px 80px; }
  .top { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin-bottom:6px; }
  h1 { font-size: 24px; margin:0; color:var(--accent); letter-spacing:.5px; }
  .meta { color:var(--sub); font-size:13px; }
  .badge { display:inline-block; padding:2px 8px; border-radius:999px; background:#e8f0f8;
           color:var(--accent); font-size:12px; margin-left:6px; }
  video { width:100%; border-radius:12px; background:#000; margin:14px 0 8px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:12px; padding:18px 20px; margin:14px 0; }
  .card h2 { font-size:16px; margin:0 0 10px; color:var(--accent); }
  .summary { font-size:15.5px; }
  .chapters { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:8px; }
  .ch { display:flex; gap:10px; align-items:baseline; padding:7px 10px; border-radius:8px;
        cursor:pointer; border:1px solid transparent; }
  .ch:hover { background:#f0f5fb; border-color:#d9e4f0; }
  .ch.active { background:#e8f0f8; border-color:#c3d7ea; }
  .ch time { font-family:Consolas,monospace; color:var(--accent); font-size:13px; min-width:44px; }
  .qa { border-top:1px dashed var(--line); padding-top:14px; margin-top:14px; }
  .qa:first-of-type { border-top:none; padding-top:0; margin-top:0; }
  .q { font-weight:600; margin-bottom:4px; }
  .a { color:#323f4b; }
  .cite { display:inline-flex; gap:4px; align-items:center; margin-left:6px; padding:1px 8px;
          border-radius:999px; background:#eef4fa; color:var(--accent); font-size:12px;
          cursor:pointer; font-family:Consolas,monospace; }
  .cite:hover { background:#dcebf8; }
  .transcript { max-height:none; }
  .line { display:flex; gap:12px; padding:5px 8px; border-radius:6px; cursor:pointer; }
  .line:hover { background:#f0f5fb; }
  .line.on { background:#e8f0f8; }
  .line time { font-family:Consolas,monospace; color:#8492a6; font-size:13px; min-width:44px; flex:none; }
  .note { color:var(--sub); font-size:12.5px; margin-top:10px; }
  .qmark { color:#b03060; }
  .askbar { display:flex; gap:8px; }
  .askbar input { flex:1; padding:10px 12px; border:1px solid #cfd8e3; border-radius:8px;
                  font:inherit; outline:none; }
  .askbar input:focus { border-color:#8fb3d4; box-shadow:0 0 0 3px #e8f0f8; }
  .askbar button { padding:10px 18px; border:none; border-radius:8px; background:var(--accent);
                   color:#fff; font:inherit; cursor:pointer; }
  .askbar button:hover { background:#173d5e; }
  .hits { margin-top:12px; }
  .hit { display:flex; gap:12px; padding:8px 10px; border-radius:8px; cursor:pointer; }
  .hit:hover { background:#f0f5fb; }
  .hit time { font-family:Consolas,monospace; color:var(--accent); font-size:13px; min-width:44px; flex:none; }
  .empty { color:var(--sub); padding:8px 2px; }
  .thinking { color:var(--sub); padding:8px 2px; }
  .answer { line-height:1.85; white-space:pre-wrap; }
  .chips { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
  .chip { padding:4px 10px; border-radius:999px; background:#eef4fa; color:var(--accent);
          font-size:12.5px; cursor:pointer; border:1px solid #dbe8f4; }
  .chip:hover { background:#dcebf8; }
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>为什么说保罗·乔治是 NBA 的「硬通货」</h1>
    <span class="meta">01:22 · 本地视频 · 转写 __NSEG__ 句</span>
  </div>
  <div class="meta">演示页：视频 → 时间轴文本 → 摘要 / 章节 / 问答。点击任意时间戳可跳转到原片对应位置。</div>

  <video id="v" controls preload="metadata" src="__VIDEO__"></video>

  <div class="card">
    <h2>30 秒摘要</h2>
    <div class="summary">
      这条 82 秒的解说，用保罗·乔治的转会史解释什么叫「NBA 硬通货」：2017 年步行者把他送去雷霆，
      换回的奥拉迪波、小萨博尼斯后来成了全明星，小萨又被交易换来哈利伯顿；2019 年雷霆把他送去快船，
      亚历山大借此成长为顶级巨星；2025 年总决赛正好是这两支球队。今夏乔治再次成为交易筹码，
      随后加盟凯尔特人，首场就打出高分，角色转为辅佐塔图姆。
    </div>
    <div class="note">转写里「38分73分」「36分63分」两处数字明显有误，摘要不引用具体分数。</div>
  </div>

  <div class="card">
    <h2>章节目录</h2>
    <div class="chapters" id="chapters"></div>
  </div>

  <div class="card">
    <h2>问一句 <span class="badge">已接入 DeepSeek</span></h2>
    <div class="askbar">
      <input id="q" placeholder="例如：乔治去过哪些球队？">
      <button id="go">提问</button>
    </div>
    <div id="chips" class="chips"></div>
    <div id="hits" class="hits"></div>
    <div class="note">答案只依据逐字稿；每条结论后面带时间戳，点一下跳到原片。第 4 个示例是「拒答」，用来验证它不会编。</div>
  </div>

  <div class="card transcript">
    <h2>逐字稿 <span class="badge">点击行跳转</span></h2>
    <div id="lines"></div>
    <div class="note">
      转写：faster-whisper medium（本地 CPU，82 秒音频约 3.5 分钟）。人名基本正确；
      仍有少量误差，例如「38分73分」这类数字，摘要没有引用。
    </div>
  </div>
</div>

<script>
const SEGS = __SEGMENTS__;
const CHAPTERS = __CHAPTERS__;
const EXAMPLES = __EXAMPLES__;
const v = document.getElementById('v');
const mmss = s => String(Math.floor(s/60)).padStart(2,'0') + ':' + String(Math.floor(s%60)).padStart(2,'0');

function seek(t) {
  v.currentTime = t;
  v.play();
  v.scrollIntoView({behavior:'smooth', block:'center'});
}

const chBox = document.getElementById('chapters');
CHAPTERS.forEach(c => {
  const el = document.createElement('div');
  el.className = 'ch';
  el.dataset.t = c.t;
  el.innerHTML = `<time>${c.time}</time><span>${c.label}</span>`;
  el.onclick = () => seek(c.t);
  chBox.appendChild(el);
});

const chipBox = document.getElementById('chips');
EXAMPLES.forEach(q => {
  const el = document.createElement('span');
  el.className = 'chip';
  el.textContent = q;
  el.onclick = () => { document.getElementById('q').value = q; ask(); };
  chipBox.appendChild(el);
});

const lines = document.getElementById('lines');
SEGS.forEach(s => {
  const el = document.createElement('div');
  el.className = 'line';
  el.dataset.s = s.s;
  el.innerHTML = `<time>${mmss(s.s)}</time><span>${s.x}</span>`;
  el.onclick = () => seek(s.s);
  lines.appendChild(el);
});

let last = -1;
const EXPAND = {
  '乔治': ['乔治', '保罗乔治'],
  '球队': ['步行者', '雷霆', '快船', '凯尔特人', '球队'],
  '转会': ['交易', '步行者', '雷霆', '快船'],
  '交易': ['交易', '筹码', '包裹'],
  '硬通货': ['硬通货', '筹码', '交易'],
  '凯尔特人': ['凯尔特人', '绿军'],
  '角色': ['角色', '辅助', '投射', '无球', '协防'],
  '塔图姆': ['塔图姆', '队友'],
  '年龄': ['36岁'],
  '现在': ['现在', '如今'],
  '身高': ['身高'],
  '合同': ['合同', '年薪', '金额'],
};

function termsOf(q) {
  const out = new Set();
  for (const [k, vs] of Object.entries(EXPAND)) if (q.includes(k)) vs.forEach(x => out.add(x));
  return [...out].filter(t => t.length >= 2);
}

function localHits(q) {
  const terms = termsOf(q);
  if (!terms.length) return [];
  const denom = Math.max(1, terms.reduce((a, t) => a + t.length, 0) * 0.6);
  return SEGS.map(s => {
    const hit = terms.filter(t => s.x.includes(t));
    return { s, score: hit.reduce((a, t) => a + t.length, 0) / denom };
  }).filter(x => x.score > 0).sort((a, b) => b.score - a.score).slice(0, 4);
}

function esc(t) {
  return t.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function renderAnswer(answer, cites) {
  const box = document.getElementById('hits');
  const map = {};
  (cites || []).forEach(c => { map[c.n] = c; });
  const html = esc(answer).replace(/\[(\d+)\]/g, (m, n) => {
    const c = map[n];
    return c ? `<span class="cite" data-t="${c.t}">▸ ${c.time}</span>` : m;
  });
  box.innerHTML = `<div class="answer">${html}</div>`;
  box.querySelectorAll('.cite').forEach(x => x.onclick = () => seek(parseFloat(x.dataset.t)));
}

function renderLocal(q, err) {
  const box = document.getElementById('hits');
  const hits = localHits(q);
  if (!hits.length || hits[0].score < 0.3) {
    box.innerHTML = '<div class="empty">资料中没有提到。可以换个说法，或点上面的示例问题。</div>';
    return;
  }
  let html = '<div class="note">未连上模型服务，下面是本地检索结果（原话片段）：</div>';
  hits.forEach(h => {
    html += `<div class="hit" data-t="${h.s.s}"><time>${mmss(h.s.s)}</time><span>${h.s.x}</span></div>`;
  });
  box.innerHTML = html;
  box.querySelectorAll('.hit').forEach(el => el.onclick = () => seek(parseFloat(el.dataset.t)));
}

async function ask() {
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  const box = document.getElementById('hits');
  box.innerHTML = '<div class="thinking">正在检索逐字稿并生成答案…</div>';
  try {
    const r = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
    renderAnswer(d.answer, d.cites);
  } catch (e) {
    renderLocal(q, e.message);
  }
}

document.getElementById('go').onclick = ask;
document.getElementById('q').addEventListener('keydown', e => { if (e.key === 'Enter') ask(); });

v.addEventListener('timeupdate', () => {
  const t = v.currentTime;
  document.querySelectorAll('.ch').forEach(el => {
    el.classList.toggle('active', Math.abs(parseFloat(el.dataset.t) - t) < 0.6);
  });
  let idx = -1;
  for (let i = 0; i < SEGS.length; i++) { if (SEGS[i].s <= t + 0.2) idx = i; }
  if (idx !== last) {
    document.querySelectorAll('.line').forEach((el, i) => el.classList.toggle('on', i === idx));
    last = idx;
  }
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
