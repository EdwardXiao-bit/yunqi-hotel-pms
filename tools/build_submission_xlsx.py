# -*- coding: utf-8 -*-
"""生成第一次提交用的“软件功能清单”Excel。

输出：deliverables/第14组_酒店客房预订与入住管理系统_功能清单.xlsx
（文件名按课程要求“第x组_给定方案名称”，项目名仍为 云栖酒店客房预订与入住管理系统）
数据来源：work/leader_docx_dump.txt（胡宇书修改版 docx 的 10x5 表格），逐字一致。
"""
import math
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.properties import PageSetupProperties

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "deliverables")
OUT = os.path.join(OUT_DIR, "第14组_酒店客房预订与入住管理系统_功能清单.xlsx")
os.makedirs(OUT_DIR, exist_ok=True)

PROJECT = "云栖酒店客房预订与入住管理系统"
GROUP = "第 14 组（胡宇书、肖铭皓）"

HEADERS = ["功能编号", "功能名称", "功能描述", "所属角色", "优先级"]

# 文案逐字取自 work/leader_docx_dump.txt 的 T0018 表格（含表头 10 行 × 5 列）
ROWS = [
    ("F01", "房型与价格维护",
     "维护房型名称、床型、面积、容纳人数、标准价与简介，支持新增、修改及停用；维护按日期区间定价方案，"
     "同一房型的价格方案不得重叠，无专项价格时采用标准价。保存订单逐日成交价格，后续调价不修改已确认价格。",
     "管理员", "P0"),
    ("F02", "房间与基础信息管理",
     "维护唯一房号、所属房型、楼层、朝向及备注；管理正常、清洁中、维修中、停用状态，并记录维修、停用的起止日期。"
     "房态变更记录操作人与时间。管理员维护员工账号和角色；前台仅办理授权范围内的房态操作。",
     "管理员、前台", "P0"),
    ("F03", "可用房间查询",
     "按入住日期、离店日期、房型（可选）和人数查询，返回区间内无有效订单冲突且无维修、停用冲突的房间，"
     "按房型汇总余量及区间报价。校验离店日期晚于入住日期、入住人数不超过房型容量。清洁中房间须完成清洁后才能实际入住。",
     "客户、前台", "P0"),
    ("F04", "预订提交",
     "客户选定房间及日期后提交预订，校验日期、人数、区间冲突与重复提交；通过后生成唯一预订号，状态为待确认并占用对应日期。"
     "保存报价，前台确认时核对成交价格。并发提交由数据库约束与事务控制，冲突时提示重新选择。",
     "客户", "P0"),
    ("F05", "预订管理",
     "前台确认或取消预订，按约定到店时限核实未到店订单并释放占用；客户可查看、取消本人尚未入住的预订，"
     "查询本人历史入住及消费记录。状态按待确认→已确认→入住中→已完成流转；待确认、已确认可取消，"
     "已确认可转未到店；拒绝非法状态变更。",
     "客户、前台", "P0"),
    ("F06", "入住与续住办理",
     "按预订号或手机号检索订单，核验客户、房间交付状态及日期后办理入住，记录实际入住时间、预计离店日期和押金。"
     "散客入住须先建立订单，检查整个区间并保存价格。续住检查新增日期的订单及维修、停用冲突，"
     "通过后延长占用区间并保存新增日期价格。",
     "前台", "P0"),
    ("F07", "退房与结算",
     "记录实际离店时间，按保存的逐日价格与实际计费房晚结算房费，至少计一房晚；登记增值服务项目、数量、单价及费用。"
     "结算时抵扣押金，多退少补，保存支付方式及收付款记录。支持提前退房，释放剩余日期占用；"
     "超时退房提示前台处理。完成后订单转为已完成，房间转为清洁中。",
     "前台", "P0"),
    ("F08", "房态看板",
     "按楼层或房型展示当前运行状态、当日预订与在住信息；预订及在住信息从订单和入住记录获取。"
     "支持清洁完成后恢复正常、登记维修区间及结束维修；新增维修、停用安排须检查已有订单，存在冲突时提示先处理订单。",
     "前台、管理员", "P0"),
    ("F09", "经营统计报表",
     "按日期区间及房型筛选：①入住率＝实际入住房晚数÷可售房晚数，可售房晚扣除维修、停用期间，分母为0时显示不适用；"
     "②营业收入按退房结算日期汇总房费与服务费，押金不计收入，按支付方式展示净收款；"
     "③热门房型分别按有效订单数和实际入住房晚排名；④列出近90天无实际入住的房间，"
     "并统计取消率＝已取消订单数÷同期创建订单总数，分母为0时显示不适用。",
     "管理员", "P1"),
]

THIN = Side(style="thin", color="808080")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="D9E2F3")

# 列宽（字符单位）：描述列加宽以容纳本次的长文案，其余收窄；总宽受 A4 纵向 fitToWidth 约束
COLS = {"A": 8.5, "B": 15.5, "C": 56, "D": 12.5, "E": 7}
COL_C_CAP = 62  # 描述列每行可容纳的显示宽度（中文按 2 计；按 300dpi 渲染回测校准）
LINE_PT = 14.4  # 宋体 10pt 单行行高（磅）
PAD_PT = 5.0    # 单元格上下留白


def disp_width(text):
    return sum(2 if ord(ch) > 127 else 1 for ch in text)


def rows_needed(text, cap):
    """按显示宽度粗算换行行数：中文标点允许行尾悬挂，末行不足半行时不再多算。"""
    total = disp_width(text)
    return max(1, math.ceil(total / cap))


wb = Workbook()
ws = wb.active
ws.title = "功能清单"

# ---- 抬头 ----
ws.merge_cells("A1:E1")
c = ws["A1"]
c.value = f"软件功能清单　项目名称：{PROJECT}"
c.font = Font(name="黑体", size=14, bold=True)
c.alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[1].height = 30

ws.merge_cells("A2:E2")
c = ws["A2"]
c.value = f"数据库系统原理课程设计　{GROUP}"
c.font = Font(name="宋体", size=10)
c.alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[2].height = 20

# ---- 表头 ----
HEAD_ROW = 3
for idx, head in enumerate(HEADERS, start=1):
    c = ws.cell(row=HEAD_ROW, column=idx, value=head)
    c.font = Font(name="黑体", size=10.5, bold=True)
    c.fill = HEAD_FILL
    c.border = BORDER
    c.alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[HEAD_ROW].height = 24

# ---- 数据 ----
for i, row in enumerate(ROWS):
    r = HEAD_ROW + 1 + i
    for idx, val in enumerate(row, start=1):
        c = ws.cell(row=r, column=idx, value=val)
        c.border = BORDER
        c.font = Font(name="宋体", size=10)
        if idx == 3:
            c.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        elif idx == 2:
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        else:
            c.alignment = Alignment(horizontal="center", vertical="center")
    desc_lines = rows_needed(row[2], COL_C_CAP)
    name_lines = rows_needed(row[1], 7)  # 名称列 15.5 → 约 7 个中文
    lines = max(desc_lines, name_lines, 1)
    ws.row_dimensions[r].height = lines * LINE_PT + PAD_PT
    print(f"ROW {r} {row[0]} desc_width={disp_width(row[2])} lines={lines} height={ws.row_dimensions[r].height}")

LAST_ROW = HEAD_ROW + len(ROWS)

for col, width in COLS.items():
    ws.column_dimensions[col].width = width

# ---- 打印与视图：A4 纵向、fitToWidth、整表一页宽 ----
ws.freeze_panes = f"A{HEAD_ROW + 1}"
ws.print_title_rows = f"{HEAD_ROW}:{HEAD_ROW}"
ws.page_setup.orientation = "portrait"
ws.page_setup.paperSize = 9  # A4
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0
ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
ws.print_area = f"A1:E{LAST_ROW}"
# 页边距压小，使 9 行长描述尽量只占一页
ws.page_margins.left = 0.4
ws.page_margins.right = 0.4
ws.page_margins.top = 0.4
ws.page_margins.bottom = 0.4
ws.page_margins.header = 0.2
ws.page_margins.footer = 0.2

wb.save(OUT)
print("WROTE", OUT)
print("SHEET", ws.title, "rows", ws.max_row, "cols", ws.max_column)
