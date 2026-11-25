# 视频知识库 · 批量入库 README

> 当前状态：本地 GPU 转写 + LLM 结构化 + **多视频检索问答**已跑通。
> 环境：Python 3.10（`.venv`）、faster-whisper 1.1.1、CUDA（RTX 4060）、DeepSeek API。

---

## 零、多视频问答（新）

```powershell
.venv\Scripts\python.exe batch.py scan "F:\某课程目录"
.venv\Scripts\python.exe batch.py run
D:\Anaconda\python.exe kb_server.py 8010
```

浏览器打开 `http://127.0.0.1:8010`：

- 左侧按**课程分组**（父文件夹名），一张卡片代表一门课，点开折叠展开各集；
- 顶部提问，可**选择问答范围**（全部 / 某门课），答案结论后面带 `▸ 12:34` 引用；
- 点引用直接打开该视频并跳到对应秒数。

### 导入与状态（新增）

- **支持格式**：视频（mp4/mkv/mov…）、**PDF**、**Word（.docx）**、**图片（png/jpg/webp）**；PDF 引用显示"第 N 页"并跳页，Word 引用显示"第 N 段"并展示原文片段，图片引用显示"图 N"并打开原图；
- **扫描版 PDF**：没有文字层会被标记失败并提示"需要 OCR"，不会产生空内容；
- **归档**：处理完的文件自动从 `inbox` 移到 `data\raw\`，避免重复扫描；
- **网页导入**：左侧「＋ 导入文件」→ 选文件 → 看预估（时长/费用）→ 开始导入；
- **共享目录**：把文件丢进 `data\inbox`，`watch.py` 每 60 秒扫一次并自动处理；
- **状态徽章**：`处理中`（不可点、不参与问答）/ `可用` / `建议检查`；
- **回收站**：弹窗里点「删除」→ 侧栏回收站可「恢复」或「彻底删除」；
- **日报**：`python report.py` 生成 `data\logs\report-YYYY-MM-DD.md`。

启动监听：双击 `run_watch.bat`（或 `python watch.py --interval 60`）。


### 周报与自检

- python weekly_report.py → 生成 data\reports\weekly-YYYY-MM-DD.md（新增内容、提问量、有用率、最常问、待改进、没答上来）；
- python healthcheck.py → 一条命令检查端口、登录页、数据库、模型、磁盘、备份、监听进程，全 PASS 才算健康。

### 反馈与看板

- 每条答案下面有 👍 / 👎，记录到 `qa_logs` 表；
- 侧栏「数据看板」：本周提问、有用 / 没用、弱引用数、最常问、待改进（点过 👎）、没答上来的问题；
- 每周看一次「待改进」和「没答上来」，缺什么内容就补什么。


### 双击即用（桌面版）

- 桌面图标「知识库」：双击打开控制面板，点「打开知识库」进网页；
- 关闭窗口 = 收进右下角托盘，服务继续跑；
- 托盘右键可打开/退出；
- 开机自动启动（收进托盘，不弹窗）；
- 面板上的「备份」「重启」可一键操作；
- 服务意外退出时，面板会自动拉起。

### 登录、自启与备份
- **登录**：打开 `http://127.0.0.1:8010` 会跳转登录页；账号默认 `boss`，密码由 `set_password.py` 设置；
  改密码：`.venv\Scripts\python.exe set_password.py 新密码`；
- **开机自启**：`KB-Autostart.bat` 已放入系统「启动」文件夹，登录 Windows 后自动拉起服务和监听；
  手动启动用 `start_all.bat`；
- **每日备份**：`backup.py` 打包 `kb.db` + 文本目录到 `data\backup\`，保留 30 份；
  监听进程每天 3 点后自动跑一次，也可手动 `python backup.py`。

检索方式：句子拼成 ~500 字块 → **BM25（关键词）+ 向量（BGE-small-zh，本地 ONNX）双路召回 → RRF 融合 → LLM 重排取前 6** → 补上「前一块」（避免只看到结论看不到前因）→ 生成带引用的答案 → **引用校验**（答案句子与片段字面重合度过低时标为弱引用）。

---

## 一、三条命令

```powershell
cd D:\知识库问答系统

# 1. 扫描目录，登记新视频（自动去重、读时长）
.venv\Scripts\python.exe batch.py scan "D:\你的视频目录"

# 2. 处理队列（可加 --limit 10 先试水）
.venv\Scripts\python.exe batch.py run

# 3. 看进度 / 导出
.venv\Scripts\python.exe batch.py status
.venv\Scripts\python.exe batch.py export
```

跑大批量时用 `run_batch.bat`（日志写到 `data\logs\batch.log`，窗口最小化别关）。

---

## 二、它会做什么

```
扫描目录 → 内容指纹去重 → 登记数据库（data\kb.db）
   ↓
GPU 转写（medium，batch 8，句子级时间戳）
   ↓
写入 segments 表
   ↓
DeepSeek 生成摘要 + 章节 + 关键词
   ↓
写文件 data\library\{编号}_{标题}\transcript.md + outline.md
   ↓
状态 ready
```

**实测速度**：36 分钟视频转写 **90 秒**（24 倍速）、结构化 4 秒；按此估算 **50 小时素材约 2 小时**。
（注意：批量默认关闭词级时间戳，长视频开 `--words` 会慢十倍；时间戳按字数比例切分，误差在 30 秒窗口内。）

---

## 三、状态与断点

| 状态 | 含义 | 中断后 |
|---|---|---|
| pending | 待处理 | 下次 run 继续 |
| transcribing | 转写中 | 下次 run 自动回收为 pending 重跑 |
| transcribed | 有逐字稿、没结构化 | 跳过转写，只补结构化 |
| structured | 有结构化结果 | 只补写文件 |
| ready | 完成 | — |
| failed | 失败 | `run --retry-failed` 重试，或 `reset --id N` |

去重按**内容指纹**（文件头尾哈希 + 大小），同一个视频改名、换目录都不会重复转写。

---

## 四、常用参数

```powershell
batch.py run --limit 10          # 先跑 10 条
batch.py run --retry-failed      # 重试失败
batch.py run --model small       # 换小模型（快 1.5 倍，质量略降）
batch.py run --device cpu        # 强制 CPU（调试用）
batch.py run --batch 4           # 显存紧张时降 batch
batch.py reset --id 3            # 单条重跑
```

---

## 五、目录说明

```
data\
├─ kb.db                  # 任务与结果数据库（SQLite）
├─ library\{id}_{name}\   # 每条视频的 transcript.md / outline.md
├─ export\                # 汇总导出
└─ logs\batch.log         # 批量日志
models\faster-whisper-medium\   # 模型（1.5 GB）
cuda\                     # cuDNN 运行库（1 GB）
```

---

## 六、常见问题

**转写很慢 / 显示 device=cpu？**
cuDNN 或 cuBLAS 找不到。检查 `D:\知识库问答系统\cuda\...\bin` 和 `D:\模型ollama\lib\ollama\cuda_v12` 是否存在；删了 Ollama 目录就会退回 CPU。

**显存不足？**
`--batch 4`，或关掉游戏/绘图软件。medium fp16 约 1.5 GB。

**只想重跑摘要、不重新转写？**
把状态改成 transcribed：`python sqlrun.py "UPDATE videos SET status='transcribed' WHERE id=3"`，再 run（会跳过转写，重做结构化）。

**视频没有音轨？**
scan 阶段就会跳过并提示，不会进队列。

---

## 七、还没做的

- 多视频检索问答（当前问答服务只接了一条视频）
- 进度 Web 页面（现在是命令行）
- 云端 Paraformer 通道（本地 GPU 够用，暂不需要）
