from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IP = "192.168.0.113"
URL = f"http://{IP}:8010"
USER = "boss"
PWD = "123456"

W, H = 960, 600
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
F = r"C:\Windows\Fonts\msyh.ttc"
FB = r"C:\Windows\Fonts\msyhbd.ttc"


def font(size, bold=False):
    return ImageFont.truetype(FB if bold else F, size)


# 顶部色块
d.rectangle([0, 0, W, 120], fill=(31, 78, 121))
d.text((60, 30), "知识库 · 访问卡片", font=font(38, True), fill="white")
d.text((60, 82), "连上「智汇达_总经理室」Wi-Fi，浏览器打开下面的地址", font=font(20), fill=(210, 226, 242))

# 地址
d.text((60, 160), "地址", font=font(18, True), fill=(91, 107, 124))
d.text((60, 188), URL, font=font(44, True), fill=(31, 78, 121))

# 账号
d.text((60, 270), "账号", font=font(18, True), fill=(91, 107, 124))
d.text((150, 266), USER, font=font(28), fill=(31, 41, 51))
d.text((330, 270), "密码", font=font(18, True), fill=(91, 107, 124))
d.text((420, 266), PWD, font=font(28), fill=(31, 41, 51))

# 分隔线
d.line([60, 330, W - 60, 330], fill=(227, 232, 238), width=2)

# 三步
steps = [
    "1. 连上「智汇达_总经理室」Wi-Fi",
    "2. 浏览器输入上面的地址，登录",
    "3. 直接提问；答案后面的时间/页码可以点开看原文",
]
y = 360
for s in steps:
    d.text((60, y), s, font=font(21), fill=(50, 63, 75))
    y += 48

d.text((60, H - 60), "打不开？先确认服务已启动，再检查是否在同一网络。", font=font(16), fill=(140, 150, 160))

out = Path(r"D:\知识库问答系统\访问卡片.png")
img.save(out)
print("saved", out, img.size)




