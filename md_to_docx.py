"""把方案 Markdown 转成排版良好的 DOCX（python-docx）。"""
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BODY_FONT = "微软雅黑"
CODE_FONT = "Consolas"
ACCENT = RGBColor(0x1F, 0x4E, 0x79)
GRAY = RGBColor(0x59, 0x59, 0x59)
CODE_BG = "F2F4F7"
HEADER_BG = "DCE6F1"
ZEBRA_BG = "F7F9FC"
DIAGRAM = Path(__file__).resolve().parent / "assets" / "architecture.png"


def set_run_font(run, name, east_asia=None, size=None, bold=None, color=None):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:eastAsia"), east_asia or name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def shade(element, fill):
    pr = element.get_or_add_pPr() if hasattr(element, "get_or_add_pPr") else element
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pr.append(shd)


def shade_cell(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_margins(table, top=40, bottom=40, left=80, right=80):
    tbl_pr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for tag, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        node = OxmlElement(f"w:{tag}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tbl_pr.append(mar)


def repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")
CODE_ONLY = re.compile(r"(`[^`]+`)")


def add_bold(paragraph, text, size):
    """加粗片段内部可能还嵌着行内代码，单独处理，避免把反引号带进正文。"""
    for piece in CODE_ONLY.split(text):
        if not piece:
            continue
        if piece.startswith("`") and piece.endswith("`") and len(piece) > 2:
            run = paragraph.add_run(piece[1:-1])
            set_run_font(run, CODE_FONT, east_asia=BODY_FONT, size=size - 0.5,
                         bold=True, color=RGBColor(0xB0, 0x30, 0x60))
        else:
            run = paragraph.add_run(piece)
            set_run_font(run, BODY_FONT, size=size, bold=True)


def add_inline(paragraph, text, size=10.5, color=None):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            add_bold(paragraph, part[2:-2], size)
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            set_run_font(run, CODE_FONT, east_asia=BODY_FONT, size=size - 0.5, color=RGBColor(0xB0, 0x30, 0x60))
        else:
            run = paragraph.add_run(part)
            set_run_font(run, BODY_FONT, size=size, color=color)


def strip_md(text):
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).replace("`", "")


def setup_document():
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.3)
    section.right_margin = Cm(2.3)

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    pf = normal.paragraph_format
    pf.line_spacing = 1.45
    pf.space_after = Pt(6)

    # 页脚页码
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run._element.addnext(fld)
    return doc


def h(doc, text, level):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt({1: 18, 2: 14, 3: 10}.get(level, 8))
    p.paragraph_format.space_after = Pt({1: 10, 2: 8, 3: 6}.get(level, 4))
    p.paragraph_format.keep_with_next = True
    size = {1: 17, 2: 13.5, 3: 11.5}[level]
    run = p.add_run(strip_md(text))
    set_run_font(run, BODY_FONT, size=size, bold=True, color=ACCENT)
    if level == 1:
        pPr = p._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "8")
        bottom.set(qn("w:space"), "4")
        bottom.set(qn("w:color"), "1F4E79")
        bdr.append(bottom)
        pPr.append(bdr)
    return p


def display_len(text):
    clean = strip_md(text)
    return sum(2 if ord(ch) > 127 else 1 for ch in clean)


def apply_widths(table, rows):
    """按内容长度分配列宽，避免 5 列表格各列等宽导致大量折行。"""
    ncols = len(rows[0])
    weights = []
    for j in range(ncols):
        longest = max(display_len(r[j]) if j < len(r) else 1 for r in rows)
        weights.append(min(max(longest, 5), 38))

    total_cm = 16.3
    min_cm = 1.9
    raw = [total_cm * w / sum(weights) for w in weights]
    # 保证每列不小于最小值，超出部分从最宽列按比例扣回
    for _ in range(6):
        deficit = sum(max(0, min_cm - x) for x in raw)
        if deficit <= 0.01:
            break
        raw = [max(x, min_cm) for x in raw]
        spare = [x - min_cm for x in raw]
        pool = sum(spare)
        if pool <= 0:
            break
        raw = [x - deficit * (x - min_cm) / pool for x in raw]
    raw = [max(x, min_cm) for x in raw]

    table.autofit = False
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    table._tbl.tblPr.append(layout)
    for j, width in enumerate(raw):
        table.columns[j].width = Cm(width)
        for cell in table.columns[j].cells:
            cell.width = Cm(width)


def add_table(doc, rows):
    header, body = rows[0], rows[1:]
    table = doc.add_table(rows=len(rows), cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    set_cell_margins(table)

    for j, text in enumerate(header):
        cell = table.cell(0, j)
        cell.text = ""
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.15
        add_inline(p, text, size=9.5)
        for run in p.runs:
            run.bold = True
        shade_cell(cell, HEADER_BG)
    repeat_header(table.rows[0])

    for i, row in enumerate(body, start=1):
        for j, text in enumerate(row):
            cell = table.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.2
            add_inline(p, text, size=9.5)
            if i % 2 == 0:
                shade_cell(cell, ZEBRA_BG)

    for row in table.rows:
        tr_pr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        cant.set(qn("w:val"), "true")
        tr_pr.insert(0, cant)

    # 小表尽量整体不跨页；大表允许在行间断开（表头会重复）
    if len(rows) <= 6:
        for row in table.rows[:-1]:
            for cell in row.cells:
                for para in cell.paragraphs:
                    para.paragraph_format.keep_with_next = True

    apply_widths(table, rows)

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(0)
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.line_spacing = 1.0
    spacer.add_run(" ").font.size = Pt(4)
    return table


def add_diagram(doc, image_path):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(4)
    shape = p.add_run().add_picture(str(image_path), width=Cm(16.2))
    # 部分渲染器会给图片补一条默认描边，显式声明无边框
    sp_pr = shape._inline.graphic.graphicData.pic.spPr
    ln = OxmlElement("a:ln")
    ln.append(OxmlElement("a:noFill"))
    sp_pr.append(ln)
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(14)
    run = cap.add_run("图 1　总体数据流：任一环节失败可重跑，不阻塞其他视频")
    set_run_font(run, BODY_FONT, size=9, color=GRAY)


def add_code(doc, lines):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.3)
    pf.space_before = Pt(4)
    pf.space_after = Pt(8)
    pf.line_spacing = 1.05
    shade(p._p, CODE_BG)
    for i, line in enumerate(lines):
        run = p.add_run(line)
        set_run_font(run, CODE_FONT, east_asia=BODY_FONT, size=8.5, color=RGBColor(0x24, 0x29, 0x2E))
        if i < len(lines) - 1:
            run.add_break()


def add_bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.4
    add_inline(p, text)


def add_numbered(doc, num, text):
    """手写序号，避免 Word 的 List Number 跨列表连续编号。"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.75)
    pf.first_line_indent = Cm(-0.4)
    pf.space_after = Pt(3)
    pf.line_spacing = 1.4
    run = p.add_run(f"{num}. ")
    set_run_font(run, BODY_FONT, size=10.5, bold=True)
    add_inline(p, text)


def add_quote(doc, lines):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.6)
    pf.space_before = Pt(4)
    pf.space_after = Pt(10)
    pf.line_spacing = 1.45
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "18")
    left.set(qn("w:space"), "10")
    left.set(qn("w:color"), "1F4E79")
    bdr.append(left)
    pPr.append(bdr)
    for i, text in enumerate(lines):
        add_inline(p, text, size=10, color=GRAY)
        if i < len(lines) - 1:
            p.add_run().add_break()


def split_row(line):
    s = line.strip().strip("|")
    cells, buf, in_code = [], "", False
    for ch in s:
        if ch == "`":
            in_code = not in_code
            buf += ch
        elif ch == "|" and not in_code:
            cells.append(buf.strip())
            buf = ""
        else:
            buf += ch
    cells.append(buf.strip())
    return cells


def convert(md_path, docx_path):
    lines = Path(md_path).read_text(encoding="utf-8").splitlines()
    doc = setup_document()
    i, first_h1 = 0, True
    in_code = False
    code_buf = []
    table_buf = []

    def flush_table():
        if len(table_buf) >= 2:
            add_table(doc, table_buf[:])
        table_buf.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                if any("调度层" in l for l in code_buf) and DIAGRAM.exists():
                    add_diagram(doc, DIAGRAM)
                else:
                    add_code(doc, code_buf)
                code_buf, in_code = [], False
            else:
                flush_table()
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            cells = split_row(stripped)
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                i += 1
                continue
            table_buf.append(cells)
            i += 1
            continue
        else:
            flush_table()

        if not stripped:
            i += 1
            continue

        if stripped == "---":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            pPr = p._p.get_or_add_pPr()
            bdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "4")
            bottom.set(qn("w:space"), "1")
            bottom.set(qn("w:color"), "BFBFBF")
            bdr.append(bottom)
            pPr.append(bdr)
            i += 1
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped[level:].strip()
            if level == 1 and first_h1:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(24)
                p.paragraph_format.space_after = Pt(18)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                run = p.add_run(strip_md(text))
                set_run_font(run, BODY_FONT, size=22, bold=True, color=ACCENT)
                first_h1 = False
            else:
                h(doc, text, min(level, 3))
            i += 1
            continue

        if stripped.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                piece = lines[i].strip().lstrip(">").strip()
                if piece:
                    quote_lines.append(piece)
                i += 1
            if quote_lines:
                add_quote(doc, quote_lines)
            continue

        if stripped.startswith("- [ ] "):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.first_line_indent = Cm(-0.35)
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run("☐  ")
            set_run_font(run, BODY_FONT, size=10.5)
            add_inline(p, stripped[6:])
            i += 1
            continue

        m = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if m:
            add_bullet(doc, m.group(2))
            i += 1
            continue

        m = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if m:
            add_numbered(doc, m.group(2), m.group(3))
            i += 1
            continue

        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0.0)
        add_inline(p, stripped)
        i += 1

    flush_table()
    if in_code and code_buf:
        add_code(doc, code_buf)

    doc.save(docx_path)
    print(f"saved: {docx_path}")


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
