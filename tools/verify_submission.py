# -*- coding: utf-8 -*-
"""校验第一次提交件：功能清单 xlsx 与 Word 汇总 docx 的结构与版式。

v2（2026-10-30）：文案换成胡宇书修改版（长描述、9 项）、截图可能 1–2 张、
Word 增加「四、数据库要点」（13 张表口径），断言随之更新。
"""
import os
import sys

from docx import Document
from docx.oxml.ns import qn
from openpyxl import load_workbook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "deliverables")
XLSX = os.path.join(D, "第14组_酒店客房预订与入住管理系统_功能清单.xlsx")
DOCX = os.path.join(D, "第14组_酒店客房预订与入住管理系统.docx")

NAMES = [
    "房型与价格维护", "房间与基础信息管理", "可用房间查询", "预订提交", "预订管理",
    "入住与续住办理", "退房与结算", "房态看板", "经营统计报表",
]

ok = True
def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        ok = False

# ---------- xlsx ----------
wb = load_workbook(XLSX)
ws = wb["功能清单"]
check(ws.max_row == 12 and ws.max_column == 5, f"sheet 功能清单 尺寸 {ws.max_row}x{ws.max_column}（期望 12x5 = 抬头2 + 表头1 + 数据9，无脚注行）")
check("云栖酒店客房预订与入住管理系统" in (ws["A1"].value or ""), "A1 抬头含项目名称")
check("第 14 组" in (ws["A2"].value or ""), f"A2 抬头含组号/组员（{ws['A2'].value}）")
heads = [ws.cell(row=3, column=c).value for c in range(1, 6)]
check(heads == ["功能编号", "功能名称", "功能描述", "所属角色", "优先级"], f"表头 {heads}")
ids = [ws.cell(row=r, column=1).value for r in range(4, 13)]
check(ids == [f"F{i:02d}" for i in range(1, 10)], f"功能编号 {ids}")
names = [ws.cell(row=r, column=2).value for r in range(4, 13)]
check(names == NAMES, f"功能名称 {names}")
empty = [(r, c) for r in range(4, 13) for c in range(1, 6) if not ws.cell(row=r, column=c).value]
check(not empty, f"数据区无空单元格（空: {empty}）")
prior = [ws.cell(row=r, column=5).value for r in range(4, 13)]
check(prior == ["P0"] * 8 + ["P1"], f"优先级 {prior}")
lens = [len(ws.cell(row=r, column=3).value) for r in range(4, 13)]
check(min(lens) >= 80, f"描述列均为长文案（最短 {min(lens)} 字，最长 {max(lens)} 字）")
check(ws.cell(row=12, column=1).value == "F09", "末行是 F09（第 12 行），无脚注行")
check(all(ws.cell(row=r, column=3).alignment.wrap_text for r in range(4, 13)), "描述列已开自动换行")
heights = [ws.row_dimensions[r].height for r in range(4, 13)]
check(all(h and h > 20 for h in heights), f"数据行行高已按文案撑开 {heights}")
check(ws.page_setup.orientation == "portrait", "打印方向 portrait")
check(ws.print_area.replace("$", "").endswith("A1:E12"), f"打印区域 {ws.print_area}（期望 A1:E12）")
check(ws.sheet_properties.pageSetUpPr is not None and ws.sheet_properties.pageSetUpPr.fitToPage, "已开 fitToPage（A4 一页宽）")

# ---------- docx ----------
doc = Document(DOCX)
sec = doc.sections[0]
check(round(sec.page_width.cm, 1) == 21.0 and round(sec.page_height.cm, 2) == 29.7, f"页面 {sec.page_width.cm:.1f}x{sec.page_height.cm:.1f}cm")
check(round(sec.left_margin.cm, 2) == 3.17 and round(sec.right_margin.cm, 2) == 3.17, "左右页边距 3.17")
check(round(sec.top_margin.cm, 2) == 2.54 and round(sec.bottom_margin.cm, 2) == 2.54, "上下页边距 2.54")
paras = [p for p in doc.paragraphs if p.text.strip()]
check(len(paras) >= 20, f"非空段落 {len(paras)}")
texts = [p.text for p in paras]
check(any("云栖酒店客房预订与入住管理系统" == t for t in texts), "标题段存在")
for needle in ["一、项目名称", "二、项目描述", "三、功能清单", "四、数据库要点"]:
    check(needle in texts, f"含小节标题 {needle}")

# 组长文案已逐字落地
rule_paras = [t for t in texts if t.startswith("（") and "）" in t[:4]]
check(len(rule_paras) == 5, f"核心业务规则 5 条（实测 {len(rule_paras)} 条）")
check(any(t.startswith("功能清单共9项") for t in texts), "功能清单说明为组长原文")
check(any("13 张表" in t and "room_block" in t and "reservation_price" in t for t in texts), "数据库要点含 13 表 + 新增两表")
check(any("EXCLUDE USING gist" in t and "during" in t for t in texts), "数据库要点含区间排他约束")

# 截图（1–2 张，宽度 = A4 可用宽度 14.66cm）
n_img = len(doc.inline_shapes)
check(1 <= n_img <= 2, f"内嵌图片数 {n_img}（1–2 张：Excel 截图分页时逐页嵌入）")
w_list = [round(s.width.cm, 2) for s in doc.inline_shapes]
check(all(abs(w - 14.66) < 0.1 for w in w_list), f"图片宽度 {w_list}cm（期望 14.66cm）")
caps = [t for t in texts if t.startswith("图 ")]
check(len(caps) == n_img and caps and caps[0].startswith("图 1"), f"图注 {caps}")
h_list = [round(s.height.cm, 2) for s in doc.inline_shapes]
check(all(h < 24.6 for h in h_list), f"图片高度 {h_list}cm 未超版心高度")

sizes = {run.font.size.pt for p in paras for run in p.runs if run.font.size}
check(12.0 in sizes and 14.0 in sizes, f"字号含小四 12pt 与一级标题 14pt（实测 {sorted(sizes)}）")
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
indent_n = sum(1 for p in paras if p.paragraph_format.first_line_indent and abs(p.paragraph_format.first_line_indent.pt - 24) < 0.1)
check(indent_n >= 10, f"首行缩进 2 字符（24pt）段落数 {indent_n}")

print("\nRESULT", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
