# PDF + 图片 + 视频 落地实施方案

> 目标：在现有视频知识库上，接进 **PDF / Word / 图片**，做到一次上传、同一个搜索框提问、引用能跳回原文。
> 现状：视频链路已跑通（5 个视频、12.1 小时、22 倍速、带时间戳问答）。
> 本文只讲**怎么落地**：表怎么改、模块怎么拆、接口怎么定、界面怎么动、几天做完。

---

## 一、总体判断

视频、PDF、图片三者最大的差别只在"解析"和"定位"，**检索与问答是一条链路**：

视频走 ASR 得到"句子 + 时间戳"，PDF 走文本抽取得到"段落 + 页码"，图片走视觉模型得到"段落 + 图号"——**三者的产物都是「文本 + 定位」**，再统一进入 blocks → chunks → 检索 → 带引用的回答。

所以落地策略是：**把三者都归一成 `documents + blocks`，检索层只认这一套。**

现在的 `videos / segments` 迁移过去，视频不用重新转写。

---

## 二、数据模型（一次性迁移，之后只加行）

```sql
CREATE TABLE documents (
  id           INTEGER PRIMARY KEY,
  kind         TEXT NOT NULL,        -- video | pdf | docx | image | pptx | md
  title        TEXT NOT NULL,
  path         TEXT,                  -- 本地绝对路径
  url          TEXT,                  -- 网页来源（可空）
  pages        INTEGER,               -- PDF/PPT 页数
  duration     REAL,                  -- 视频时长（秒）
  size         INTEGER,
  sha256       TEXT UNIQUE,           -- 内容指纹，去重
  status       TEXT DEFAULT 'pending',-- pending|parsing|structured|ready|failed
  summary      TEXT,                  -- 一段话摘要
  outline_json TEXT,                  -- 章节/要点
  error        TEXT,
  created_at   TEXT, updated_at TEXT
);

CREATE TABLE blocks (
  id        INTEGER PRIMARY KEY,
  doc_id    INTEGER NOT NULL,
  seq       INTEGER NOT NULL,
  locator   TEXT NOT NULL,            -- "12:34" | "p12" | "图3-2" | "3.2"
  page      INTEGER,                  -- PDF/图片序号，可空
  start_s   REAL,                     -- 视频用，可空
  end_s     REAL,
  text      TEXT NOT NULL
);
CREATE INDEX idx_blocks_doc ON blocks(doc_id, seq);

CREATE TABLE chunks (
  id          INTEGER PRIMARY KEY,
  doc_id      INTEGER NOT NULL,
  start_block INTEGER NOT NULL,
  end_block   INTEGER NOT NULL,
  locator     TEXT NOT NULL,          -- 块的起点定位，用于引用
  text        TEXT NOT NULL,          -- 含上下文头
  n_chars     INTEGER
);
CREATE INDEX idx_chunks_doc ON chunks(doc_id);
```

**迁移脚本**（一次性，视频不重转）：

```sql
INSERT INTO documents(kind,title,path,duration,size,sha256,status,summary,outline_json,created_at,updated_at)
SELECT 'video', trim(name), path, duration, size, fingerprint, status, summary, outline_json, created_at, updated_at
FROM videos;

INSERT INTO blocks(doc_id,seq,locator,start_s,end_s,text)
SELECT v.id, s.seq, printf('%02d:%02d', s.start/60, s.start%60), s.start, s.end, s.text
FROM segments s JOIN videos v ON v.id = s.video_id;
```

迁移后 `videos/segments` 保留做备份，代码切到新表；确认无误再删。

---

## 三、模块拆分

```
kb/
├─ db.py                 # 连接、建表、迁移
├─ models.py             # Document / Block / Chunk 数据类
├─ parsers/
│  ├─ base.py            # Parser 接口：parse(path) -> (meta, blocks)
│  ├─ video.py           # 复用现有 asr_runtime，输出带时间戳的 blocks
│  ├─ pdf.py             # PyMuPDF：逐页取文本块，按坐标排序
│  ├─ docx.py            # python-docx：标题层级 + 段落
│  └─ image.py           # 视觉模型：读文字 + 描述，返回段落
├─ chunker.py            # 300–600 字切块，不跨定位边界
├─ pipeline.py           # 单文档：解析 → 切块 → 结构化 → 入库
├─ batch.py              # 目录扫描、队列、断点续跑（在现有基础上扩展）
└─ server.py             # 列表 / 问答 / 文件流
```

统一接口：

```python
class Parser:
    kinds = ("pdf",)
    def parse(self, path: Path) -> tuple[dict, list[Block]]: ...
```

`Block` 只有四个字段：`locator, page, start_s/end_s, text`。

---

## 四、三种解析器的具体做法

### 4.1 视频（已有，包装一下）

- 沿用 `asr_runtime.transcribe_chunked`（10 分钟切片，22 倍速）；
- 每句 → 一个 block，`locator=mm:ss`，`start_s/end_s` 填上；
- 状态流转不变。

### 4.2 PDF

```python
import fitz  # PyMuPDF
doc = fitz.open(path)
for pno, page in enumerate(doc, 1):
    blocks = page.get_text("blocks")          # (x0,y0,x1,y1,text,...)
    blocks.sort(key=lambda b: (round(b[1] / 10), b[0]))  # 先按行再按列，处理双栏
    for b in blocks:
        text = clean(b[4])
        if len(text) < 2: continue
        yield Block(locator=f"p{pno}", page=pno, text=text)
```

- **扫描版检测**：`sum(len(page.get_text()) for page in doc) / pages < 50` → 标记 `needs_ocr`，暂不解析（后续接 PaddleOCR）；
- 表格：`page.find_tables()` 抽出后转成"| 列1 | 列2 |"文本块，避免串行；
- 页眉页脚：连续 3 页重复出现的行，直接丢弃。

### 4.3 图片

```python
resp = llm.chat(model="deepseek-chat", messages=[{
    "role": "user",
    "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]}])
```

`PROMPT` 要求返回严格 JSON：

```json
{"type":"截图|图表|海报|照片","title":"一句话标题",
 "paragraphs":["图中文字段落1","段落2"],
 "description":"这张图在讲什么，2-3 句",
 "tables":[["列1","列2"]],
 "confidence":"high|medium|low"}
```

- 每个 paragraph → 一个 block，`locator="图{n}-{i}"`，`page=n`；
- 超过 2000px 高的长图先横向切片，再逐片读，拼接段序号；
- `confidence=low` 的文档打标，问答时提示"图片识别置信度低"。

**实测**：900×420 中文截图，250 token、约 1 秒、原文一字不差。

---

## 五、切块规则

| 来源 | 边界 | 块大小 | 块头 |
|---|---|---|---|
| 视频 | 不跨 30 秒窗口 | 300–600 字 | `《第一天》 12:34–13:02` |
| PDF | **不跨页** | 300–600 字 | `《XX报告》 第12页` |
| 图片 | **不跨图**（长图不跨切片） | 200–500 字 | `《截图03》 图3-2` |

**硬规则：一个块绝不能跨定位边界**，否则引用会指错地方。宁可块小一点。

---

## 六、接口设计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/documents?kind=pdf` | 列表（id、标题、类型、页数/时长、摘要） |
| GET | `/api/doc/{id}` | 详情：摘要、章节、blocks 前 N 条 |
| GET | `/api/progress` | 各状态计数 + 当前处理项 |
| POST | `/api/ask` | `{question}` → `{answer, cites:[{doc_id,kind,locator,page,time,title}]}` |
| GET | `/file/{id}` | 原文件流（支持 Range，PDF/图片/视频共用） |

`cites` 的 `locator` 已经是给人看的字符串，前端按 `kind` 决定跳转方式。

---

## 七、界面改动

### 7.1 列表

- 顶部筛选：`全部 / 视频 / 文档 / 图片`；
- 每项带类型图标和元信息：视频 `2:01`、PDF `36 页`、图片 `3 张`；
- 搜索框保留，输入即搜（跨类型）。

### 7.2 引用与阅读器

| 类型 | 引用显示 | 点击后 |
|---|---|---|
| 视频 | ▸ 12:34 | 播放器弹窗跳秒（已有） |
| PDF | ▸ 第12页 | `<iframe src="/file/12#page=12">` 弹窗 |
| 图片 | ▸ 图3-2 | `<img src="/file/12">` 弹窗 |

PDF 用浏览器原生阅读器，零开发量；要"高亮命中段落"再换 PDF.js。

### 7.3 上传

- 现在靠 `scan` 目录；
- 后续加一个拖拽上传框，存到 `data/inbox/`，自动入队（1 天）。

---

## 八、任务拆解与工期

| 阶段 | 任务 | 产出 | 工期 |
|---|---|---|---|
| D1 | 新表 + 迁移脚本 + 现有视频迁入 | 迁移后视频问答不回归 | 1 天 |
| D2 | Parser 接口 + PDF 解析 + 切块入库 | PDF 能搜、能引用到页 | 1 天 |
| D3 | 图片解析（视觉模型）+ 长图切片 | 截图/图表能搜 | 1 天 |
| D4 | 接口改造 + 前端列表/筛选/阅读器 | 三类混合列表与跳转 | 1 天 |
| D5 | 混合评测 + 修边角（表格、页眉、扫描件标记） | 20 题评测报告 | 1 天 |

**合计 5 人日**（不含 OCR 与向量检索）。

---

## 九、验收标准（10 条）

- [ ] 迁移后 5 个视频问答结果与迁移前一致（同一问题同一引用）
- [ ] 文字版 PDF 能搜到正文，引用点开是正确页
- [ ] 扫描版 PDF 被标记 `needs_ocr`，不产生空块
- [ ] 中文截图能搜到图中文字，引用点开是原图
- [ ] 长图（聊天记录）切段后段落顺序正确
- [ ] 问"视频里说的定位三原则，PDF 里有没有类似说法"能同时命中两类
- [ ] 引用卡片显示正确类型（▶ / 页 / 图）
- [ ] 列表筛选 `PDF` 只显示 PDF
- [ ] 同一文件重复扫描不重复入库（sha256）
- [ ] P95 首字 ≤ 5 秒

---

## 十、成本

| 项目 | 单价 | 备注 |
|---|---|---|
| PDF/DOCX 解析 | 0 | 本地库 |
| 图片识别 | 0.0003–0.001 元/张 | 1000 张 < 1 元 |
| 文档摘要（LLM） | 约 1 元/200 页 | 可批量 |
| OCR（可选） | 本地 0 / 云 1–2 分/页 | 仅扫描件 |
| 存储 | 原文件保留 | 按 GB，可忽略 |

---

## 十一、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 扫描版 PDF | 解析为空 | 检测字符密度，标 `needs_ocr`，二期接 OCR |
| 双栏 / 复杂版式 | 文本串行 | 按坐标排序；表格单独成块 |
| 图片长截图 | 模型漏读 | 横向切片，逐片读 |
| 图片手写/低清 | 错字 | `confidence=low` 标记，抽检 |
| 大 PDF（500 页+） | 结构化超时 | 按章 map-reduce 摘要 |
| 迁移出错 | 视频问答回归 | 迁移前备份 kb.db；保留旧表 7 天 |

---

## 十二、交付物

1. 迁移后的 `data/kb.db`（documents / blocks / chunks）；
2. `kb/` 模块与 3 个解析器；
3. 改造后的 `kb_server.py` + `kb.html`（三类列表、筛选、阅读器）；
4. 一份《混合检索评测报告》（20 题、正确率、引用准确率）；
5. 一页使用说明（怎么加 PDF、加图片）。

---

## 十三、建议的起步动作

1. 先备份 `data/kb.db`；
2. 建新表、迁移 5 个视频，跑一遍现有问题，确认不回归；
3. 拿 2 份 PDF（一份文字版、一份扫描版）+ 3 张截图试解析；
4. 接进前端，用一个混合问题验收；
5. 再批量导入其余资料。

> 一句话：**先把"视频 + PDF + 图片"跑成一条链路，再谈 OCR 和向量；不要一次把所有格式都做到完美。**
