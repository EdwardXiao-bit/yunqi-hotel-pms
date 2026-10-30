# -*- coding: utf-8 -*-
"""生成第一次提交用的 Word 汇总文档。

输出：deliverables/第14组_云栖酒店客房预订与入住管理系统.docx
内容：项目名称 + 项目描述 + 功能清单（Excel 表格截图）+ 数据库要点
版式：A4、正文小四号宋体、行距 20 磅、标题黑体（沿用课程报告版式要求）。
"""
import os

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "deliverables")
OUT = os.path.join(OUT_DIR, "第14组_云栖酒店客房预订与入住管理系统.docx")
IMG = os.path.join(OUT_DIR, "images", "feature-list.png")

PROJECT = "云栖酒店客房预订与入住管理系统"

ONE_LINER = (
    "面向中小型酒店的客房管理系统：客户按日期区间查询可用房间并在线预订，前台办理入住、退房与费用结算并调度房态，"
    "管理员维护房型、房间与价格并查看入住率和营业收入统计；数据库层用日期区间排他约束保证同一房间在重叠日期内绝不会被重复预订。"
)

DESC_CORE = (
    "酒店客房业务的核心矛盾是「房间在时间维度上的独占性」：同一间房在同一晚只能卖给一位客户，而一位客户可能连续住多晚、"
    "也可能续住或提前退房。本系统把预订、入住、结算、房态建成相互关联的数据对象，围绕预订—入住—退房—统计展开。"
)

DESC_ROLES = [
    "客户侧：按入住/离店日期、房型、人数查询可用房间；提交预订、查看与取消自己的预订；查看历史入住与消费记录。",
    "前台侧：核验预订办理入住、办理退房并结算房费与增值服务、处理未到店与取消、调度房态（清洁中/维修中）。",
    "管理员侧：维护房型、房间、按日期区间定价、员工账号，查看入住率、营业收入、热门房型、长期空闲房间等统计。",
]

DESC_SCOPE = (
    "系统不扩展为完整酒店信息系统（不含会员营销、渠道直连与硬件对接），聚焦预订、入住、退房与经营统计主链路，"
    "在 9 张相互关联的表上实现完整的主外键、检查约束、排他约束与多表统计查询。"
)

FUNC_NOTE = (
    "功能清单共 9 项（要求 5–10 项），覆盖基础信息维护（F01、F02）、业务办理（F04、F06、F07）、"
    "状态管理（F02、F05）与查询统计（F03、F09）四类。下表在 Excel 中制作，以截图形式附于本文档。"
)

DB_NOTE = (
    "数据库设计要点：9 项功能落到 9 张相互关联的表上（app_user、customer、room_type、room、rate_plan、"
    "reservation、check_in_record、payment、room_status_log）。核心约束「同一房间在重叠日期内不得存在两条有效预订」"
    "用 PostgreSQL 的 EXCLUDE USING gist 在（房间号 =、日期区间 &&）上实现；房号唯一、离店晚于入住、"
    "同一房型定价区间不重叠等亦以显式命名的 CHECK / UNIQUE / EXCLUDE 约束落在数据库层。"
)


def set_run_font(run, cn="宋体", size=12, bold=False, en=None):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(0, 0, 0)
    run.font.name = en or cn
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = parse_xml(f'<w:rFonts {nsdecls("w")}/>')
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), cn)
    rfonts.set(qn("w:ascii"), en or "Times New Roman")
    rfonts.set(qn("w:hAnsi"), en or "Times New Roman")


def body_para(doc, text, indent=True, size=12, space_after=0):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(20)
    pf.space_before = Pt(0)
    pf.space_after = Pt(space_after)
    pf.first_line_indent = Pt(size * 2) if indent else Pt(0)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_run_font(p.add_run(text), cn="宋体", size=size)
    return p


def h1(doc, text, page_break=False):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(24)
    pf.space_before = Pt(12)
    pf.space_after = Pt(6)
    pf.keep_with_next = True
    if page_break:
        pf.page_break_before = True
    set_run_font(p.add_run(text), cn="黑体", size=14, bold=False)
    return p


doc = Document()

# ---- 页面：A4，页边距 ----
sec = doc.sections[0]
sec.page_width = Cm(21.0)
sec.page_height = Cm(29.7)
sec.top_margin = Cm(2.54)
sec.bottom_margin = Cm(2.54)
sec.left_margin = Cm(3.17)
sec.right_margin = Cm(3.17)
sec.footer_distance = Cm(1.5)
USABLE_W = Cm(21.0 - 3.17 * 2)

# ---- 默认样式（避免 Normal 样式带回 Calibri） ----
normal = doc.styles["Normal"]
normal.font.name = "Times New Roman"
normal.font.size = Pt(12)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

# ---- 标题区 ----
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(6)
p.paragraph_format.space_after = Pt(6)
p.paragraph_format.line_spacing = Pt(30)
set_run_font(p.add_run(PROJECT), cn="黑体", size=18, bold=True)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(18)
p.paragraph_format.line_spacing = Pt(20)
set_run_font(p.add_run("数据库系统原理课程设计 · 第 14 组 · 第一次提交材料"), cn="宋体", size=12)

# ---- 一、项目名称 ----
h1(doc, "一、项目名称")
body_para(doc, f"项目名称：{PROJECT}（给定方案六）")
body_para(doc, "组　　号：第 14 组")
body_para(doc, "小组成员：胡宇书（组长）、肖铭皓")
body_para(doc, "指导教师：郭际香")

# ---- 二、项目描述 ----
h1(doc, "二、项目描述")
body_para(doc, ONE_LINER)
body_para(doc, DESC_CORE)
for line in DESC_ROLES:
    body_para(doc, line)
body_para(doc, DESC_SCOPE)

# ---- 三、功能清单（另起一页：表格图占满整页宽度） ----
h1(doc, "三、功能清单", page_break=True)
body_para(doc, FUNC_NOTE)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(6)
p.paragraph_format.space_after = Pt(3)
p.add_run().add_picture(IMG, width=USABLE_W)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(6)
set_run_font(p.add_run("图 1　软件功能清单（Excel 表格截图）"), cn="宋体", size=10.5)

# ---- 页脚：组号 + 页码 ----
footer = sec.footer
fp = footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
set_run_font(fp.add_run("第 14 组　数据库系统原理课程设计　第 "), cn="宋体", size=9)
fp._p.append(parse_xml(
    f'<w:fldSimple {nsdecls("w")} w:instr=" PAGE ">'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体"/>'
    '<w:sz w:val="18"/></w:rPr><w:t>1</w:t></w:r></w:fldSimple>'
))
set_run_font(fp.add_run(" 页"), cn="宋体", size=9)

doc.save(OUT)
print("WROTE", OUT)
