# -*- coding: utf-8 -*-
"""生成第一次提交用的 Word 汇总文档。

输出：deliverables/第14组_酒店客房预订与入住管理系统.docx
（文件名按课程要求“第x组_给定方案名称”，项目名仍为 云栖酒店客房预订与入住管理系统）
内容：一 项目名称 + 二 项目描述 + 三 功能清单（Excel 表格截图，1–2 张）+ 四 数据库要点
文案：二、三 两节逐字取自 work/leader_docx_dump.txt（胡宇书修改版 docx 的文本转储）。
版式：A4、正文小四号宋体、行距 20 磅、一级标题黑体 14pt、大标题黑体 18pt 加粗居中、页脚页码。
"""
import glob
import os

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "deliverables")
OUT = os.path.join(OUT_DIR, "第14组_酒店客房预订与入住管理系统.docx")
IMG_DIR = os.path.join(OUT_DIR, "images")

PROJECT = "云栖酒店客房预订与入住管理系统"
SCHEME = "酒店客房预订与入住管理系统"  # 教师给定方案六的原题名，文件名按此命名

# ---- 二、项目描述（逐字取自组长修改版：总述 + 客户侧/前台侧/管理员侧 + 核心业务规则 5 条）----
DESC_PARAS = [
    "本系统面向中小型酒店，支持客户按日期查询房间并预订，前台办理入住、续住、退房与费用结算，"
    "管理员维护基础信息并查看经营统计。系统聚焦预订—入住—退房—统计主流程，不包含会员营销、渠道直连与硬件对接。",
    "客户侧：按入住日期、离店日期、房型及人数查询可预订房间；提交、查看和取消自己的预订；查询本人历史入住及消费记录。",
    "前台侧：确认预订、处理取消和未到店，办理预订入住与散客入住、续住、提前退房及结算，维护清洁与维修状态。"
    "管理员侧：维护房型、房间、价格及员工账号，查看入住率、营业收入、热门房型和长期空闲房间等统计。",
    "核心业务规则如下：",
    "（1）日期区间采用［入住日期，离店日期），离店日期必须晚于入住日期。例如，11月1日入住、11月3日离店，"
    "占用两个房晚，不与11月3日入住的订单冲突。",
    "（2）房间运行状态分为正常、清洁中、维修中、停用；预订状态单独管理。指定日期是否可订，"
    "依据有效订单的占用区间及维修、停用安排判断；实际办理入住时还须确认房间已清洁且可交付。",
    "（3）待确认、已确认及入住中的订单占用对应日期；已取消、未到店的订单释放占用。待确认订单由前台确认或取消；"
    "未到店由前台按约定到店时限核实后处理。散客入住也须建立订单并检查整个入住区间，续住须检查新增区间。",
    "（4）预订确认时保存逐日成交价格，散客入住时保存入住区间价格，后续调价不影响已确认价格。"
    "续住新增日期按续住确认时的价格计费。提前退房按实际占用房晚结算，至少计一房晚；"
    "超时退房由前台提示并处理，本期不自动加收超时费用。",
    "（5）退房结算金额为房费加服务费，再扣除押金，多退少补；押金不计入营业收入。"
    "数据库通过主外键、检查约束、日期区间排他约束与事务控制，统一校验预订和散客入住的房间占用，防止重叠日期重复占用。",
]

# ---- 三、功能清单说明（逐字取自组长修改版）----
FUNC_NOTE = "功能清单共9项，覆盖基础信息维护、业务办理、状态管理及查询统计。P0为核心功能，P1为完善功能。"

# ---- 四、数据库要点（与 13 张表的设计口径一致）----
DB_PARAS = [
    "数据库共 13 张表：app_user、customer、room_type、room、rate_plan、reservation、"
    "reservation_price（逐日成交价格）、check_in_record、payment、room_status_log、"
    "room_block（维修/停用区间）、service_item、service_order。房间运行状态只保留四态："
    "available（正常）、cleaning（清洁中）、maintenance（维修中）、disabled（停用）；"
    "“已预订”“入住中”由订单与入住记录推导，不写入房态字段。",
    "核心约束“同一房间在重叠日期内不得存在两条有效预订”由生成列 during 上的排他约束实现："
    "during 由 daterange(check_in_date, check_out_date, '[)') 生成，约束为 "
    "EXCLUDE USING gist (room_id WITH =, during WITH &&) WHERE (status IN ('pending','confirmed','checked_in'))。"
    "维修、停用区间存于 room_block，与订单冲突时拒绝；逐日价格存于 reservation_price，订单总额随明细用触发器汇总；"
    "押金不计营业收入，营业收入按退房结算日期归月；入住率的可售房晚需扣除维修、停用占用。",
]

IMG_DPI = 300  # 截图按 300 dpi 渲染（libreoffice-kit render --dpi 300）


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


def body_para(doc, text, indent=True, size=12, space_after=0, keep_with_next=False):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(20)
    pf.space_before = Pt(0)
    pf.space_after = Pt(space_after)
    pf.first_line_indent = Pt(size * 2) if indent else Pt(0)
    pf.keep_with_next = keep_with_next
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


def figure_images():
    """按顺序返回要嵌入的截图：第 1 页 feature-list.png，其后 feature-list-2.png 等（或 page-0002.png）。"""
    imgs = []
    first = os.path.join(IMG_DIR, "feature-list.png")
    if os.path.exists(first):
        imgs.append(first)
    imgs.extend(sorted(glob.glob(os.path.join(IMG_DIR, "feature-list-*.png"))))
    imgs.extend(sorted(glob.glob(os.path.join(IMG_DIR, "page-*.png"))))
    return imgs


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
USABLE_W = Cm(21.0 - 3.17 * 2)  # 14.66cm

# ---- 默认样式（避免 Normal 样式带回 Calibri） ----
normal = doc.styles["Normal"]
normal.font.name = "Times New Roman"
normal.font.size = Pt(12)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

# ---- 大标题 ----
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(6)
p.paragraph_format.space_after = Pt(24)
p.paragraph_format.line_spacing = Pt(30)
set_run_font(p.add_run(PROJECT), cn="黑体", size=18, bold=True)

# ---- 一、项目名称 ----
h1(doc, "一、项目名称")
body_para(doc, f"项目名称：{PROJECT}")
body_para(doc, f"方案来源：给定方案六（{SCHEME}）")
body_para(doc, "组　　号：第 14 组")
body_para(doc, "小组成员：胡宇书（组长）、肖铭皓")
body_para(doc, "指导教师：郭际香")

# ---- 二、项目描述 ----
h1(doc, "二、项目描述")
for text in DESC_PARAS:
    body_para(doc, text)

# ---- 三、功能清单（标题—说明—截图—图注用 keep_with_next 串成一块：
#      截图放不下时整块一起换页，避免标题与表格图被拆到两页） ----
h1(doc, "三、功能清单")
body_para(doc, FUNC_NOTE, keep_with_next=True)

imgs = figure_images()
if not imgs:
    raise SystemExit(f"缺少截图：{os.path.join(IMG_DIR, 'feature-list.png')}")

for i, img in enumerate(imgs, start=1):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(img, width=USABLE_W)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    cap = "图 1　软件功能清单（Excel 表格截图）" if i == 1 else f"图 {i}　软件功能清单（Excel 表格截图·续）"
    set_run_font(p.add_run(cap), cn="宋体", size=10.5)

# ---- 四、数据库要点 ----
h1(doc, "四、数据库要点", page_break=True)
for text in DB_PARAS:
    body_para(doc, text)

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
print("IMAGES", len(imgs), [os.path.basename(i) for i in imgs])
