"""三种文档解析器：Word / PPT / Excel 的定位符与文本抽取。"""
from pathlib import Path

import pytest

import batch

pytest.importorskip("docx")
pytest.importorskip("pptx")
pytest.importorskip("openpyxl")


def test_extract_docx(tmp_path):
    import docx

    p = tmp_path / "a.docx"
    d = docx.Document()
    d.add_heading("第一章", level=1)
    d.add_paragraph("这是正文第一段。" * 30)
    d.add_paragraph("这是正文第二段。" * 30)
    d.save(p)

    rows = batch.extract_docx(p)
    assert rows
    assert all(r["locator"].startswith("第") for r in rows)
    assert "第一章" in rows[0]["text"]


def test_extract_pptx(tmp_path):
    from pptx import Presentation

    p = tmp_path / "a.pptx"
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "会员权益"
    s.placeholders[1].text = "买单权益\n非买单权益"
    prs.save(p)

    rows = batch.extract_pptx(p)
    assert len(rows) == 1
    assert rows[0]["locator"] == "第1张"
    assert "会员权益" in rows[0]["text"]


def test_extract_xlsx(tmp_path):
    from openpyxl import Workbook

    p = tmp_path / "a.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "价格"
    ws.append(["等级", "折扣"])
    ws.append(["金星", "9折"])
    wb.save(p)

    rows = batch.extract_xlsx(p)
    assert rows
    assert "价格" in rows[0]["locator"]
    assert "金星" in rows[0]["text"]
