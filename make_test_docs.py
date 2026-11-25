from pathlib import Path

from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches

out = Path(r"D:\知识库问答系统\data\_testdocs")
out.mkdir(parents=True, exist_ok=True)

# PPT
prs = Presentation()
s1 = prs.slides.add_slide(prs.slide_layouts[1])
s1.shapes.title.text = "会员权益设计"
s1.placeholders[1].text = "买单权益：按就餐流程给优惠\n非买单权益：体验与特权"
s2 = prs.slides.add_slide(prs.slide_layouts[1])
s2.shapes.title.text = "会员等级"
s2.placeholders[1].text = "银星、玉星、金星三个等级\n升级按累积消费"
prs.save(out / "会员课PPT.pptx")

# Excel
wb = Workbook()
ws = wb.active
ws.title = "会员档位"
ws.append(["等级", "年消费", "折扣"])
ws.append(["银星", 0, "无"])
ws.append(["玉星", 2000, "95折"])
ws.append(["金星", 5000, "9折"])
ws2 = wb.create_sheet("储值")
ws2.append(["档位", "金额", "赠送"])
ws2.append(["一档", 500, 50])
ws2.append(["二档", 1000, 150])
wb.save(out / "会员价格表.xlsx")
print("created", list(p.name for p in out.iterdir()))
