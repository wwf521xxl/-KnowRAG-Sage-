from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
# 圆角蓝底
d.rounded_rectangle([8, 8, size - 8, size - 8], radius=52, fill=(31, 78, 121, 255))
# 白色书本线条
d.rounded_rectangle([56, 78, 200, 190], radius=10, fill=(255, 255, 255, 235))
d.line([128, 84, 128, 184], fill=(31, 78, 121, 255), width=6)
for y in (112, 136, 160):
    d.line([74, y, 116, y], fill=(31, 78, 121, 200), width=5)
    d.line([140, y, 182, y], fill=(31, 78, 121, 200), width=5)

# 顶部小点缀
try:
    f = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 20)
except Exception:
    f = None

out = Path(r"D:\知识库问答系统\app.ico")
img.save(out, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("saved", out, out.stat().st_size)
