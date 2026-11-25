"""生成方案文档里的架构图（PNG），供 DOCX 使用；Markdown 里保留 ASCII 版。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W = 1800
MARGIN_X = 70
BOX_H = 142
GAP = 58
TOP = 40

BG = (255, 255, 255)
BOX_FILL = (246, 249, 252)
BOX_LINE = (185, 203, 224)
ACCENT = (31, 78, 121)
TEXT = (31, 41, 51)
SUB = (71, 84, 103)
ARROW = (140, 160, 182)
TAG = (176, 48, 96)

FONT_DIR = Path("C:/Windows/Fonts")
REG = FONT_DIR / "msyh.ttc"
BOLD = FONT_DIR / "msyhbd.ttc"
if not BOLD.exists():
    BOLD = REG

LAYERS = [
    ("① 调度层 · 订阅与触发",
     "UP 主投稿  ·  收藏夹  ·  YouTube 播放列表 RSS  ·  手动粘贴链接",
     "每天/每 6 小时增量扫描，新链接入队，状态机推进"),
    ("② 采集适配器",
     "BilibiliAdapter  ·  YouTubeAdapter  ·  yt-dlp / bilibili-api-python",
     "cookies 池  ·  串行限速  ·  失败降级  ·  平台差异只改适配器"),
    ("③ 文本获取：字幕优先，ASR 兜底",
     "有字幕 → 解析 srt / vtt / json（0 成本、秒级、带时间轴）",
     "无字幕 → ffmpeg 抽 16k 单声道 → 云 ASR（Paraformer，带时间戳）"),
    ("④ 文本加工（LLM）",
     "规整（去滚动重复 / 口头禅 / 补标点）→ 校对（术语表）→ 结构化",
     "产出：章节标题 + 每章摘要 + 全文摘要 + 要点卡片 + 关键词"),
    ("⑤ 存储层",
     "PostgreSQL：videos / segments / chapters / chunks  ·  pgvector  ·  pg_trgm",
     "文件：transcript.md / outline.json / cover.jpg  ·  content_hash 增量"),
    ("⑥ 问答层（FastAPI）",
     "Query 改写 → 双路召回（向量 + 关键词）→ RRF → Rerank → 阈值拒答",
     "LLM 强制引用 → SSE 流式返回 → 引用卡片带时间戳深链"),
    ("⑦ 界面",
     "视频库  ·  视频详情（章节大纲 + 逐字稿，可点击跳转）",
     "问答对话：先给结论，再给要点，最后给「建议观看」时间戳"),
]


def load(path, size):
    return ImageFont.truetype(str(path), size)


def fit_font(draw, text, size, max_width, bold=False):
    font = load(BOLD if bold else REG, size)
    while draw.textlength(text, font=font) > max_width and size > 12:
        size -= 1
        font = load(BOLD if bold else REG, size)
    return font, size


def main(out_path):
    height = TOP + len(LAYERS) * BOX_H + (len(LAYERS) - 1) * GAP + 40
    img = Image.new("RGB", (W, height), BG)
    d = ImageDraw.Draw(img)

    box_w = W - MARGIN_X * 2
    for i, (title, line1, line2) in enumerate(LAYERS):
        y = TOP + i * (BOX_H + GAP)
        d.rounded_rectangle(
            (MARGIN_X, y, MARGIN_X + box_w, y + BOX_H),
            radius=14, fill=BOX_FILL, outline=BOX_LINE, width=2,
        )
        d.rounded_rectangle(
            (MARGIN_X, y, MARGIN_X + 10, y + BOX_H),
            radius=5, fill=ACCENT,
        )

        tf, _ = fit_font(d, title, 31, box_w - 90, bold=True)
        d.text((MARGIN_X + 34, y + 18), title, font=tf, fill=ACCENT)

        f1, _ = fit_font(d, line1, 24, box_w - 90)
        d.text((MARGIN_X + 34, y + 66), line1, font=f1,
               fill=TAG if "Paraformer" in line1 or "有字幕" in line1 else SUB)

        f2, _ = fit_font(d, line2, 23, box_w - 90)
        d.text((MARGIN_X + 34, y + 103), line2, font=f2, fill=SUB)

        if i < len(LAYERS) - 1:
            cx = W // 2
            y1 = y + BOX_H + 4
            y2 = y + BOX_H + GAP - 8
            d.line((cx, y1, cx, y2), fill=ARROW, width=4)
            d.polygon([(cx - 10, y2 - 2), (cx + 10, y2 - 2), (cx, y2 + 12)], fill=ARROW)

    img.save(out_path, "PNG", optimize=True)
    print(f"saved: {out_path} {img.size}")


if __name__ == "__main__":
    out = Path(__file__).with_name("assets") / "architecture.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    main(str(out))
