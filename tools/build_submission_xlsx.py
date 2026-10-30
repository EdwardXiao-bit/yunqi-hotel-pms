# -*- coding: utf-8 -*-
"""生成第一次提交用的「软件功能清单」Excel。

输出：deliverables/第14组_酒店客房预订与入住管理系统_功能清单.xlsx
（文件名按课程要求「第x组_给定方案名称」，项目名仍为 云栖酒店客房预订与入住管理系统）
数据来源：docs/01-功能清单.md 第 4 节（逐字一致）。
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

ROWS = [
    ("F01", "房型与价格维护",
     "维护房型（名称、床型、面积、容纳人数、标准价、简介）与按日期区间的定价方案。支持新增、修改、停用房型；"
     "同一房型在同一日期区间的价格方案不得重叠，价格调整后历史账单按原价保留。",
     "管理员", "P0"),
    ("F02", "房间与房态管理",
     "维护具体房间（房号唯一、所属房型、楼层、朝向、备注），并管理房态：可用/已预订/入住中/清洁中/维修中/停用。"
     "房间停用后不参与可用房查询；房态每次变更写入房态日志，可追溯变更人与时间。",
     "管理员、前台", "P0"),
    ("F03", "可用房间查询",
     "客户输入入住日期、离店日期、房型（可选）、入住人数后，系统返回该日期区间内没有预订冲突且房态可用的房间，"
     "并按房型汇总剩余数量与区间总价。日期非法（离店早于或等于入住）时给出提示。",
     "客户", "P0"),
    ("F04", "预订提交",
     "客户选定房间与日期后提交预订，系统校验：日期区间合法、该房间该区间无其他有效预订、客户无重复提交。"
     "校验通过生成唯一预订号，状态为「待确认」；与已有预订冲突时明确提示冲突日期区间。",
     "客户", "P0"),
    ("F05", "预订管理",
     "前台确认、取消预订，并处理「未到店」：未到店与取消的预订释放房间占用；客户可自助取消自己的预订，"
     "已入住的预订不允许取消，状态流转不合法时给出提示。",
     "客户、前台", "P0"),
    ("F06", "入住办理",
     "前台按预订号或客户手机号检索预订，核验后办理入住：生成入住记录、房间房态转为「入住中」、"
     "记录实际入住时间与押金，支持无预订的散客直接入住。",
     "前台", "P0"),
    ("F07", "退房与结算",
     "前台办理退房：按实际入住天数与当时适用的房价计算房费，叠加增值服务费用并扣除押金，生成支付记录；"
     "房间房态转为「清洁中」。支持提前退房（按实际天数计费）与超时退房提示。",
     "前台", "P0"),
    ("F08", "房态看板",
     "以房间为单位的看板视图：按楼层/房型分组展示全部房间的实时房态与当日预订、在住客信息；"
     "支持把房间在「清洁中↔可用」「维修中↔可用」之间切换，维修中的房间不参与预订与入住。",
     "前台、管理员", "P0"),
    ("F09", "经营统计报表",
     "四类统计：①各房型月度入住率（已售房夜/可售房夜）；②月度营业收入（房费+服务费，按支付方式拆分）；"
     "③最受欢迎房型 Top N（按订单数与房夜数）；④长期空闲房间（近 90 天无任何预订）与取消率。"
     "支持按日期区间与房型筛选。",
     "管理员", "P1"),
]

THIN = Side(style="thin", color="808080")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="D9E2F3")
ZEBRA_FILL = PatternFill("solid", fgColor="F2F2F2")

COLS = {"A": 9, "B": 18, "C": 46, "D": 12, "E": 7}
COL_C_CAP = 51  # 描述列每行可容纳的显示宽度（中文按 2 计；按 144dpi 渲染回测校准）


def disp_width(text):
    return sum(2 if ord(ch) > 127 else 1 for ch in text)


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
            lines = max(1, math.ceil(disp_width(val) / COL_C_CAP))
            ws.row_dimensions[r].height = lines * 14.4 + 4
        elif idx == 2:
            c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        else:
            c.alignment = Alignment(horizontal="center", vertical="center")

LAST_ROW = HEAD_ROW + len(ROWS)

for col, width in COLS.items():
    ws.column_dimensions[col].width = width

# ---- 打印与视图 ----
ws.freeze_panes = f"A{HEAD_ROW + 1}"
ws.print_title_rows = f"{HEAD_ROW}:{HEAD_ROW}"
ws.page_setup.orientation = "portrait"
ws.page_setup.paperSize = 9  # A4
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0
ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
ws.print_area = f"A1:E{LAST_ROW}"

wb.save(OUT)
print("WROTE", OUT)
print("SHEET", ws.title, "rows", ws.max_row, "cols", ws.max_column)
