# -*- coding: utf-8 -*-
"""校验第一次提交件：功能清单 xlsx 与 Word 汇总 docx 的结构与内容。"""
import os
import sys

from docx import Document
from docx.oxml.ns import qn
from openpyxl import load_workbook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "deliverables")
XLSX = os.path.join(D, "第14组_酒店客房预订与入住管理系统_功能清单.xlsx")
DOCX = os.path.join(D, "第14组_酒店客房预订与入住管理系统.docx")

ok = True
def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        ok = False

# ---------- xlsx ----------
wb = load_workbook(XLSX)
ws = wb["功能清单"]
check(ws.max_row == 12 and ws.max_column == 5, f"sheet 功能清单 尺寸 {ws.max_row}x{ws.max_column}（期望 12x5，无脚注行）")
check("云栖酒店客房预订与入住管理系统" in (ws["A1"].value or ""), "A1 抬头含项目名称")
heads = [ws.cell(row=3, column=c).value for c in range(1, 6)]
check(heads == ["功能编号", "功能名称", "功能描述", "所属角色", "优先级"], f"表头 {heads}")
ids = [ws.cell(row=r, column=1).value for r in range(4, 13)]
check(ids == [f"F{i:02d}" for i in range(1, 10)], f"功能编号 {ids}")
empty = [(r, c) for r in range(4, 13) for c in range(1, 6) if not ws.cell(row=r, column=c).value]
check(not empty, f"数据区无空单元格（空: {empty}）")
prior = [ws.cell(row=r, column=5).value for r in range(4, 13)]
check(prior == ["P0"] * 8 + ["P1"], f"优先级 {prior}")
check(ws.cell(row=12, column=1).value == "F09", "末行是 F09（第 12 行），无脚注行")
check(ws.page_setup.orientation == "portrait", "打印方向 portrait")
check(ws.print_area.replace("$", "").endswith("A1:E12"), f"打印区域 {ws.print_area}（期望 A1:E12）")

# ---------- docx ----------
doc = Document(DOCX)
sec = doc.sections[0]
check(round(sec.page_width.cm, 1) == 21.0 and round(sec.page_height.cm, 2) == 29.7, f"页面 {sec.page_width.cm:.1f}x{sec.page_height.cm:.1f}cm")
check(round(sec.left_margin.cm, 2) == 3.17 and round(sec.top_margin.cm, 2) == 2.54, "页边距 3.17/2.54")
paras = [p for p in doc.paragraphs if p.text.strip()]
check(len(paras) >= 15, f"非空段落 {len(paras)}")
texts = [p.text for p in paras]
check(any("云栖酒店客房预订与入住管理系统" == t for t in texts), "标题段存在")
for needle in ["一、项目名称", "二、项目描述", "三、功能清单"]:
    check(needle in texts, f"含小节标题 {needle}")
check(len(doc.inline_shapes) == 1, f"内嵌图片数 {len(doc.inline_shapes)}")
check(abs(doc.inline_shapes[0].width.cm - 14.66) < 0.1, f"图片宽度 {doc.inline_shapes[0].width.cm:.2f}cm")

sizes = {run.font.size.pt for p in paras for run in p.runs if run.font.size}
bad_ea = []
for p in paras:
    for run in p.runs:
        rpr = run._element.rPr
        rfonts = rpr.find(qn("w:rFonts")) if rpr is not None else None
        if rfonts is None or rfonts.get(qn("w:eastAsia")) is None:
            bad_ea.append((p.text[:16], run.text[:10]))
check(not bad_ea, f"所有 run 均显式指定中文字体（缺失 {len(bad_ea)} 处）")

foot = sec.footer.paragraphs[0]._p
check("PAGE" in foot.xml, "页脚含 PAGE 域（页码）")
check("第 14 组" in sec.footer.paragraphs[0].text, "页脚含组号")

# 行距与首行缩进抽样
body = [p for p in paras if p.paragraph_format.line_spacing is not None and abs(p.paragraph_format.line_spacing.pt - 20) < 0.1]
check(len(body) >= 10, f"20 磅行距段落数 {len(body)}")

print("\nRESULT", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
