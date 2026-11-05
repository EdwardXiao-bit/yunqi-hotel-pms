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
XLSX = os.environ.get(
    "SUBMISSION_XLSX",
    os.path.join(D, "第14组_酒店客房预订与入住管理系统_软件功能清单.xlsx"),
)
DOCX = os.environ.get(
    "SUBMISSION_DOCX",
    os.path.join(D, "第14组_酒店客房预订与入住管理系统.docx"),
)

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

# ---------- xlsx（软件功能清单 SR 表） ----------
wb = load_workbook(XLSX)
check("软件功能清单" in wb.sheetnames, f"sheet 名含「软件功能清单」（{wb.sheetnames}）")
ws = wb["软件功能清单"]
check(ws.max_row == 31 and ws.max_column == 7, f"sheet 尺寸 {ws.max_row}x{ws.max_column}（期望 31x7 = 抬头2 + 表头1 + 28 条 SR）")
check("软件功能清单" in (ws["A1"].value or "") and "云栖酒店" in (ws["A1"].value or ""), "A1 抬头含表名与项目名称")
check("第14组" in (ws["A2"].value or "") and "客户" in (ws["A2"].value or ""), f"A2 抬头含组号与角色（{ws['A2'].value}）")
heads = [ws.cell(row=3, column=c).value for c in range(1, 8)]
check(heads == ["需求编号", "需求名称", "需求描述", "约束条件", "输入", "处理", "输出"], f"表头 {heads}")
ids = [ws.cell(row=r, column=1).value for r in range(4, 32)]
check(ids == [f"SR-{i:02d}" for i in range(1, 29)], f"需求编号 {ids[:3]} … {ids[-1]}（共 {len(ids)} 条）")
empty = [(r, c) for r in range(4, 32) for c in range(1, 8) if not ws.cell(row=r, column=c).value]
check(not empty, f"数据区无空单元格（空: {empty}）")
lens = [len(ws.cell(row=r, column=2).value) for r in range(4, 32)]
check(min(lens) >= 4, f"需求名称列均非空（最短 {min(lens)} 字）")
check(all(ws.cell(row=r, column=3).alignment.wrap_text for r in range(4, 32)), "需求描述列已开自动换行")

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
check(any(t.startswith("软件功能清单按需求规格") for t in texts), "功能清单说明为 SR 口径")
check(any("13 张表" in t and "room_block" in t and "reservation_price" in t for t in texts), "数据库要点含 13 表 + 新增两表")
check(any("EXCLUDE USING gist" in t and "during" in t for t in texts), "数据库要点含区间排他约束")

# 截图：SR 表 4 页，按版心宽度缩小插入（不改页面尺寸，全篇 A4 纵向 14.66cm）
n_img = len(doc.inline_shapes)
check(n_img == 4, f"内嵌图片数 {n_img}（期望 4：SR 表分 4 页）")
w_list = [round(s.width.cm, 2) for s in doc.inline_shapes]
check(all(abs(w - 14.66) < 0.1 for w in w_list), f"图片宽度 {w_list}cm（期望 14.66cm，版心宽）")
caps = [t for t in texts if t.startswith("图 ")]
check(len(caps) == n_img and caps and caps[0].startswith("图 1"), f"图注 {caps}")
h_list = [round(s.height.cm, 2) for s in doc.inline_shapes]
check(all(h < 24.6 for h in h_list), f"图片高度 {h_list}cm 未超纵向版心高度")
check(any("28 条功能需求" in t for t in texts), "功能清单说明写明 28 条功能需求")
check(any("SR-01~SR-28" in t for t in texts), "功能清单说明写明 SR-01~SR-28")
secs = doc.sections
check(len(secs) == 1, f"节数 {len(secs)}（期望 1：全篇 A4 纵向，不改页面尺寸）")
check(all(round(s.page_width.cm, 1) == 21.0 and round(s.page_height.cm, 2) == 29.7 for s in secs),
      f"所有节均为 A4 纵向（{[(round(s.page_width.cm,1), round(s.page_height.cm,1)) for s in secs]}）")

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
