# -*- coding: utf-8 -*-
"""生成 sql/03_seed.sql（演示库样例数据）。

设计依据：docs/02-数据库设计.md 第 10 节「数据样例规划」。

为什么用脚本生成而不是手写 SQL：
- 96 条预订必须保证「同一房间 + 活跃状态」的时间区间互不重叠（EXCLUDE 约束），
  手写极易撞车；脚本里维护 busy[room_id] 区间表，落库前就做冲突检测。
- 需要精确的条数口径（30 客户 / 96 预订 / 48 入住 / ≥80 支付 / 8 服务项目 /
  ≥50 服务明细 / 6 种房态全覆盖），脚本末尾 assert 校验，生成物与文档一致。
- 固定随机种子，同样输入永远生成同样输出，便于 diff 与复现。

用法：
    python tools/build_seed_sql.py            # 生成并自检
    python tools/build_seed_sql.py --check    # 只自检不写文件

产物：sql/03_seed.sql（UTF-8 无 BOM，LF 换行）
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sql" / "03_seed.sql"

# 演示口令 Hotel@123 的 Django PBKDF2 哈希（Django 6.1.2 / pbkdf2_sha256 / 1500000 轮）
# 生成命令：
#   python -c "from django.conf import settings; settings.configure(); \
#              from django.contrib.auth.hashers import make_password; \
#              print(make_password('Hotel@123'))"
PWD_HASH = (
    "pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$"
    "HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o="
)

# 日期锚点：演示时把「今天」当成 2026-12-15
ANCHOR = date(2026, 12, 15)

SEED = 20261030
rng = random.Random(SEED)

# =============================================================================
# 1. 静态数据定义
# =============================================================================

# (名称, 床型, 面积, 可住人数, 标准价, 描述)
ROOM_TYPES = [
    ("标准间", "twin", "25.0", 2, Decimal("288.00"), "两张单人床，临街采光，基础配置"),
    ("高级大床房", "king", "28.0", 2, Decimal("388.00"), "1.8 米大床，独立卫浴，含双早"),
    ("豪华双床房", "twin", "32.0", 2, Decimal("488.00"), "两张 1.5 米床，楼层较高，安静"),
    ("家庭房", "family", "45.0", 4, Decimal("688.00"), "一大一小两床，适合家庭出行"),
    ("行政套房", "suite", "60.0", 2, Decimal("1288.00"), "客厅与卧室分离，含行政酒廊"),
    ("无障碍房", "double", "30.0", 2, Decimal("328.00"), "轮椅通道与扶手，低台面无障碍卫生间"),
]

# 楼层 → 房型（每层 5 间，共 8 层 40 间）
FLOOR_TYPE = {
    5: "标准间",
    6: "标准间",
    7: "高级大床房",
    8: "高级大床房",
    9: "豪华双床房",
    10: "家庭房",
    11: "行政套房",
    12: "无障碍房",
}

# 员工账号：1 管理员 + 2 前台
STAFF_USERS = [
    ("admin", "酒店管理员", "admin", "13908001000", "admin@yunqi-hotel.local"),
    ("front01", "前台·刘敏", "receptionist", "13908001001", "front01@yunqi-hotel.local"),
    ("front02", "前台·周涛", "receptionist", "13908001002", "front02@yunqi-hotel.local"),
]

# 客户档案：共 30 条 = 24 个有账号客户 + 6 个线下散客（user_id 为空）
# 前 6 位沿用固定姓名（docs/05 的查询样例以张伟为主要样本，便于对照截图）
CORE_CUSTOMERS = [
    # (用户名, 姓名, 手机, 身份证, 邮箱, 备注)
    ("zhangwei", "张伟", "13800001101", "510101199003070011", "zhangwei@example.com", "常客，偏好高楼层"),
    ("lina", "李娜", "13800001102", "510104199205120022", "lina@example.com", None),
    ("wangfang", "王芳", "13800001103", "510107198811230033", "wangfang@example.com", "对早餐过敏，需无坚果"),
    ("liuyang", "刘洋", "13800001104", "510108199507040044", "liuyang@example.com", None),
    ("chenjing", "陈静", "13800001105", "510109199310150055", "chenjing@example.com", "公司协议价客户"),
    ("yangfan", "杨帆", "13800001106", "510110199901200066", "yangfan@example.com", None),
]

# 其余 18 个有账号客户 + 6 个散客按固定规则拼姓名，保证姓名/手机/身份证唯一
SURNAMES = ["孙", "马", "朱", "胡", "郭", "何", "高", "林", "罗", "郑",
            "梁", "谢", "宋", "唐", "许", "韩", "冯", "邓", "曹", "彭",
            "曾", "萧", "田", "董"]
GIVEN_NAMES = ["明", "静", "强", "敏", "磊", "霞", "军", "丽", "刚", "艳",
               "涛", "娟", "鹏", "浩", "娜", "伟", "超", "燕", "鑫", "雪",
               "帆", "雨", "昊", "欣"]

APP_USERS: list[tuple[str, str, str, str, str]] = list(STAFF_USERS)
CUSTOMERS: list[tuple[int | None, str, str, str, str | None, str | None]] = []

# 客户 1–6：有账号
for username, name, phone, id_card, email, remark in CORE_CUSTOMERS:
    APP_USERS.append((username, name, "customer", phone, email))
    CUSTOMERS.append((len(APP_USERS), name, phone, id_card, email, remark))

# 客户 7–24：有账号（guest07 … guest24）
for i in range(18):
    seq = 7 + i
    name = SURNAMES[i] + GIVEN_NAMES[i]
    phone = f"138000012{seq:02d}"
    id_card = f"5101{seq:02d}1985{(seq % 12) + 1:02d}15{seq:03d}{seq % 10}"
    email = f"guest{seq:02d}@example.com"
    APP_USERS.append((f"guest{seq:02d}", name, "customer", phone, email))
    CUSTOMERS.append((len(APP_USERS), name, phone, id_card, email, None))

# 客户 25–30：线下散客，user_id 为空，前台代订
for i in range(6):
    seq = 25 + i
    name = SURNAMES[18 + i] + GIVEN_NAMES[18 + i]
    phone = f"138000013{seq:02d}"
    id_card = f"5102{seq:02d}1987{(seq % 12) + 1:02d}18{seq:03d}{seq % 10}"
    CUSTOMERS.append((None, name, phone, id_card, None, "线下散客，前台代订"))

assert len(APP_USERS) == 27, len(APP_USERS)
assert len(CUSTOMERS) == 30, len(CUSTOMERS)
assert len({c[2] for c in CUSTOMERS}) == 30, "客户手机号重复"
assert len({c[3] for c in CUSTOMERS}) == 30, "客户身份证重复"
assert all(len(c[3]) == 18 for c in CUSTOMERS), "身份证长度必须为 18"

# 增值服务项目（F07 退房结算：房费 + 服务费；docs/01 第 10 张表已转为必选）
SERVICE_ITEMS = [
    ("BF", "自助早餐", "份", Decimal("68.00")),
    ("LD", "洗衣服务", "件", Decimal("30.00")),
    ("AP", "机场接送", "次", Decimal("120.00")),
    ("EB", "加床服务", "张", Decimal("150.00")),
    ("LC", "午餐套餐", "份", Decimal("88.00")),
    ("DN", "晚餐套餐", "份", Decimal("128.00")),
    ("SP", "SPA 水疗", "次", Decimal("268.00")),
    ("PK", "停车位", "晚", Decimal("20.00")),
]

# =============================================================================
# 2. 派生数据
# =============================================================================

BASE_PRICE = {name: price for name, _bed, _area, _cap, price, _desc in ROOM_TYPES}
CAPACITY = {name: cap for name, _bed, _area, cap, _price, _desc in ROOM_TYPES}

# 房间：(房号, 楼层, 房型, 朝向)
ROOMS: list[tuple[str, int, str, str]] = []
ORIENT = ["north", "south", "east", "west"]
for floor, tname in FLOOR_TYPE.items():
    for i in range(1, 6):
        ROOMS.append((f"{floor}{i:02d}", floor, tname, ORIENT[(floor + i) % 4]))

assert len(ROOMS) == 40, len(ROOMS)
assert len({r[0] for r in ROOMS}) == 40, "房号重复"

ROOM_BY_NO = {no: idx for idx, (no, _f, _t, _o) in enumerate(ROOMS, start=1)}
TYPE_OF_ROOM = {idx: t for idx, (_no, _f, t, _o) in enumerate(ROOMS, start=1)}
ALL_ROOM_IDS = list(range(1, 41))

# 价格方案：国庆 / 元旦 各覆盖 5 个房型（无障碍房只用标准价）
RATE_PLANS: list[tuple[str, date, date, Decimal]] = []
for name, _bed, _area, _cap, price, _desc in ROOM_TYPES:
    if name == "无障碍房":
        continue
    RATE_PLANS.append((name, date(2026, 10, 1), date(2026, 10, 7), (price * Decimal("1.5")).quantize(Decimal("0.01"))))
    RATE_PLANS.append((name, date(2026, 12, 30), date(2027, 1, 2), (price * Decimal("1.4")).quantize(Decimal("0.01"))))

assert len(RATE_PLANS) == 10, len(RATE_PLANS)


def price_for(room_id: int, stay_start: date) -> Decimal:
    """落单时的每晚房价快照：命中价格方案用方案价，否则用房型标准价。"""
    tname = TYPE_OF_ROOM[room_id]
    for plan_type, start, end, price in RATE_PLANS:
        if plan_type == tname and start <= stay_start <= end:
            return price
    return BASE_PRICE[tname]


# =============================================================================
# 3. 预订生成（带冲突检测）
# =============================================================================

busy: dict[int, list[tuple[date, date]]] = {rid: [] for rid in ALL_ROOM_IDS}
reservations: list[dict] = []
_seq = 0


def free(room_id: int, start: date, end: date) -> bool:
    """半开区间 [start, end) 在该房间是否空闲；首尾相接视为空闲。"""
    return all(end <= bs or start >= be for bs, be in busy[room_id])


def add(room_id: int, start: date, end: date, status: str, customer_id: int,
        source: str, remark: str = "") -> dict:
    global _seq
    _seq += 1
    price = price_for(room_id, start)
    nights = (end - start).days
    room = {
        "no": f"R{start:%Y%m%d}{_seq:03d}",
        "customer_id": customer_id,
        "room_id": room_id,
        "start": start,
        "end": end,
        "nights": nights,
        "guest_count": min(rng.randint(1, 3), CAPACITY[TYPE_OF_ROOM[room_id]]),
        "price": price,
        "total": (price * nights).quantize(Decimal("0.01")),
        "status": status,
        "source": source,
        "remark": remark,
    }
    busy[room_id].append((start, end))
    reservations.append(room)
    return room


def random_slot(window_start: date, window_end: date, nights: tuple[int, int]) -> tuple[date, date, int]:
    for _ in range(5000):
        start = window_start + timedelta(days=rng.randint(0, (window_end - window_start).days))
        end = start + timedelta(days=rng.randint(*nights))
        cands = [rid for rid in ALL_ROOM_IDS if free(rid, start, end)]
        if cands:
            return start, end, rng.choice(cands)
    raise RuntimeError(f"无法在 {window_start}–{window_end} 找到空房，预订数过多")


def fill(count: int, status: str, window: tuple[date, date], nights: tuple[int, int],
         customer_pool: list[int], remark: str = "") -> None:
    for _ in range(count):
        start, end, rid = random_slot(*window, nights)
        add(rid, start, end, status, rng.choice(customer_pool), rng.choice(["online", "phone", "walk_in"]), remark)


ACCOUNT_CUSTOMERS = list(range(1, 25))   # 有账号的客户 1–24
ALL_CUSTOMERS = list(range(1, 31))       # 含 25–30 的线下散客
RECEPTIONIST_IDS = [2, 3]

# --- 历史已退房 38 条（2026-09 ~ 2026-11）---
fill(38, "checked_out", (date(2026, 9, 1), date(2026, 11, 26)), (1, 4), ALL_CUSTOMERS)

# --- 首尾相接的已退房一对（B3：12-01 离店，同日 12-01 另一客入住）---
room_b3_past = next(rid for rid in ALL_ROOM_IDS
                    if free(rid, date(2026, 11, 28), date(2026, 11, 30))
                    and free(rid, date(2026, 11, 30), date(2026, 12, 2)))
add(room_b3_past, date(2026, 11, 28), date(2026, 11, 30), "checked_out", 1, "online",
    "B3 边界用例：上一段退房当天由下一位客人接续入住")
add(room_b3_past, date(2026, 11, 30), date(2026, 12, 2), "checked_out", 2, "phone",
    "B3 边界用例：与上一段首尾相接，占用不冲突")

# --- 已取消 11 条（连同 B4 的取消单共 12 条）---
fill(11, "cancelled", (date(2026, 9, 10), date(2026, 12, 24)), (1, 3), ACCOUNT_CUSTOMERS)

# --- 未到店 6 条 ---
fill(6, "no_show", (date(2026, 9, 10), date(2026, 12, 28)), (1, 3), ACCOUNT_CUSTOMERS)

# --- 入住中 8 条（跨 2026-12-15）---
for _ in range(8):
    for _try in range(5000):
        start = ANCHOR - timedelta(days=rng.randint(1, 3))
        end = start + timedelta(days=rng.randint(2, 4))
        if start <= ANCHOR < end:
            cands = [rid for rid in ALL_ROOM_IDS if free(rid, start, end)]
            if cands:
                add(rng.choice(cands), start, end, "checked_in", rng.choice(ACCOUNT_CUSTOMERS),
                    rng.choice(["online", "phone"]))
                break
    else:
        raise RuntimeError("无法安排入住中预订")

# --- 待确认 13 条 + 已确认 14 条（未来区间，连同 B3/B4 的活跃单共 14 + 16 条）---
fill(13, "pending", (date(2026, 12, 20), date(2027, 1, 10)), (1, 4), ACCOUNT_CUSTOMERS)
fill(14, "confirmed", (date(2026, 12, 18), date(2027, 1, 18)), (1, 4), ACCOUNT_CUSTOMERS)

# --- B4：先取消再重订（同客户、同房间、同区间）---
# B4 取消后重订用的客户改成 1 号（保证「同客户 + 同房间 + 同区间」的判重样本落在主样本客户上）
room_b4 = next(rid for rid in ALL_ROOM_IDS if free(rid, date(2026, 12, 20), date(2026, 12, 22)))
add(room_b4, date(2026, 12, 20), date(2026, 12, 22), "cancelled", 1, "online",
    "B4 边界用例：客户取消后再下同区间订单")
add(room_b4, date(2026, 12, 20), date(2026, 12, 22), "confirmed", 1, "online",
    "B4 边界用例：取消单不计入排他约束，同区间可重新预订")

# --- B3 活跃态首尾相接：已确认 01-05~01-07 与待确认 01-07~01-09 同房间 ---
room_b3 = next(rid for rid in ALL_ROOM_IDS
               if free(rid, date(2027, 1, 5), date(2027, 1, 7))
               and free(rid, date(2027, 1, 7), date(2027, 1, 9)))
add(room_b3, date(2027, 1, 5), date(2027, 1, 7), "confirmed", 5, "phone",
    "B3 边界用例：前一位 01-07 退房")
add(room_b3, date(2027, 1, 7), date(2027, 1, 9), "pending", 6, "online",
    "B3 边界用例：与上一段首尾相接，活跃态也不冲突")

# 状态汇总校验（docs/03 §4.3 目标：预订 ≥60、入住 ≥40、支付 ≥80）
STATUS_EXPECT = {
    "checked_out": 40,
    "cancelled": 12,
    "no_show": 6,
    "checked_in": 8,
    "pending": 14,
    "confirmed": 16,
}
counts: dict[str, int] = {}
for r in reservations:
    counts[r["status"]] = counts.get(r["status"], 0) + 1
assert counts == STATUS_EXPECT, f"预订状态分布不符：{counts} != {STATUS_EXPECT}"
assert len(reservations) == 96, len(reservations)

# 冲突总校验：活跃状态区间两两不重叠（首尾相接合法）
ACTIVE = ("pending", "confirmed", "checked_in")
active = [r for r in reservations if r["status"] in ACTIVE]
for i, a in enumerate(active):
    for b in active[i + 1:]:
        if a["room_id"] == b["room_id"] and a["start"] < b["end"] and b["start"] < a["end"]:
            raise AssertionError(f"活跃区间重叠：{a['no']} / {b['no']}")

# =============================================================================
# 4. 入住记录（48 条 = 40 已退房 + 8 在住）
# =============================================================================

checkins: list[dict] = []
for res_idx, r in enumerate(reservations, start=1):  # res_idx = reservation.id（按插入顺序）
    if r["status"] not in ("checked_out", "checked_in"):
        continue
    cust = CUSTOMERS[r["customer_id"] - 1]
    checkins.append({
        "reservation_id": res_idx,
        "reservation_no": r["no"],
        "room_id": r["room_id"],
        "room_charge": r["total"],
        "nights": r["nights"],
        "status": r["status"],
        "guest_name": cust[1],
        "guest_phone": cust[2],
        "guest_id_card": cust[3],
        "check_in_at": (r["start"], 14, 0),
        "actual_checkout_at": None if r["status"] == "checked_in" else (r["end"], 12, 0),
        "deposit": Decimal("200.00"),
        "service_charge": Decimal("0.00"),
        "orders": [],
    })

assert len(checkins) == 48, len(checkins)
# 增值服务明细：在住 8 条全部有消费；已退房 40 条里约 3/4 有消费（F07 结算与统计都要有样本）
for idx, rec in enumerate(checkins):
    if rec["status"] == "checked_in" or idx % 4 != 3:
        items = rng.sample(SERVICE_ITEMS, rng.randint(1, 2))
        charge = Decimal("0.00")
        for code, name, unit, price in items:
            qty = rng.randint(1, 2)
            amount = (price * qty).quantize(Decimal("0.01"))
            charge += amount
            rec["orders"].append({
                "code": code, "name": name, "unit": unit,
                "quantity": qty, "unit_price": price, "amount": amount,
            })
        rec["service_charge"] = charge
    rec["total_charge"] = (rec["room_charge"] + rec["service_charge"]).quantize(Decimal("0.01"))

order_count = sum(len(rec["orders"]) for rec in checkins)
assert 45 <= order_count <= 90, f"service_order 条数异常：{order_count}"
assert all(rec["service_charge"] > 0 for rec in checkins if rec["status"] == "checked_in"), \
    "在住记录必须有服务消费（支付流水里的 service_fee 依赖它）"

# =============================================================================
# 5. 支付流水（48 押金 + 37 房费尾款 + 3 退款 + 8 在住服务费 = 96 笔）
# =============================================================================

payments: list[dict] = []
_pseq = 0


def add_payment(rec: dict, kind: str, amount: Decimal, when: tuple[date, int, int],
                method: str, remark: str = "") -> None:
    global _pseq
    _pseq += 1
    day, hh, mm = when
    payments.append({
        "no": f"P{day:%Y%m%d}{_pseq:03d}",
        "record_idx": idx_of_record[rec["reservation_no"]],
        "kind": kind,
        "method": method,
        "amount": amount.quantize(Decimal("0.01")),
        "when": (day, hh, mm),
        "remark": remark,
    })


idx_of_record = {rec["reservation_no"]: i for i, rec in enumerate(checkins)}

refund_records = {checkins[0]["reservation_no"], checkins[7]["reservation_no"],
                  checkins[15]["reservation_no"]}
assert len(refund_records) == 3, "E07 押金退款样本应为 3 条"
for rec in checkins:
    method = rng.choice(["cash", "card", "wechat", "alipay"])
    if rec["reservation_no"] in refund_records:
        # E07 押金场景：押金多收，退房时退回差额
        rec["deposit"] = (rec["total_charge"] + Decimal("100.00")).quantize(Decimal("0.01"))
    add_payment(rec, "deposit", rec["deposit"], (rec["check_in_at"][0], 14, 30), method)

    if rec["status"] == "checked_out":
        if rec["reservation_no"] in refund_records:
            add_payment(rec, "refund", Decimal("100.00"), (rec["actual_checkout_at"][0], 12, 10),
                        method, "E07：押金多收部分退回")
        else:
            final = (rec["total_charge"] - rec["deposit"]).quantize(Decimal("0.01"))
            assert final > 0, f"房费尾款应为正：{rec['reservation_no']} {final}"
            add_payment(rec, "room_fee", final, (rec["actual_checkout_at"][0], 12, 0), method)
    else:  # checked_in：在店的增值服务费先结
        assert rec["service_charge"] > 0, "在住记录需要有服务费"
        add_payment(rec, "service_fee", rec["service_charge"],
                    (ANCHOR, 10, 0), "wechat", "在住期间增值服务费")

kind_counts: dict[str, int] = {}
for p in payments:
    kind_counts[p["kind"]] = kind_counts.get(p["kind"], 0) + 1
EXPECTED_KINDS = {
    "deposit": sum(1 for r in checkins),
    "room_fee": sum(1 for r in checkins if r["status"] == "checked_out") - len(refund_records),
    "refund": len(refund_records),
    "service_fee": sum(1 for r in checkins if r["status"] == "checked_in"),
}
assert kind_counts == EXPECTED_KINDS, f"支付类型分布不符：{kind_counts} != {EXPECTED_KINDS}"
assert len(payments) >= 80, f"支付流水应 ≥80 笔（docs/03 §4.3 目标），实际 {len(payments)}"

# =============================================================================
# 6. 房态派生（六种房态全覆盖）
# =============================================================================

final_status: dict[int, str] = {rid: "available" for rid in ALL_ROOM_IDS}
for r in reservations:
    if r["status"] == "checked_in":
        final_status[r["room_id"]] = "occupied"
for r in reservations:
    if r["status"] in ("confirmed", "pending") and final_status[r["room_id"]] == "available":
        final_status[r["room_id"]] = "reserved"

free_rooms = [rid for rid in ALL_ROOM_IDS if final_status[rid] == "available"]
rng.shuffle(free_rooms)
for rid, status in zip(free_rooms, ["cleaning", "cleaning", "maintenance", "disabled"]):
    final_status[rid] = status

status_cover = {s: sum(1 for v in final_status.values() if v == s) for s in
                ("available", "reserved", "occupied", "cleaning", "maintenance", "disabled")}
assert all(v >= 1 for v in status_cover.values()), f"房态未全覆盖：{status_cover}"

# =============================================================================
# 7. SQL 输出
# =============================================================================

lines: list[str] = []


def w(s: str = "") -> None:
    lines.append(s)


def q(s: str | None) -> str:
    if s is None:
        return "NULL"
    return "'" + s.replace("'", "''") + "'"


def money(v: Decimal) -> str:
    return f"{v:.2f}"


def d(x: date) -> str:
    return f"DATE '{x.isoformat()}'"


def ts(when: tuple[date, int, int] | None) -> str:
    if when is None:
        return "NULL"
    day, hh, mm = when
    return f"TIMESTAMPTZ '{day.isoformat()} {hh:02d}:{mm:02d}:00+08'"


w("-- =============================================================================")
w("-- sql/03_seed.sql  演示库样例数据")
w("--")
w("-- 本文件由 tools/build_seed_sql.py 生成（随机种子 20261030，可复现），")
w("-- 不要手改；改数据改脚本后重新生成： python tools/build_seed_sql.py")
w("--")
w("-- 数据规模（与 docs/02-数据库设计.md 第 10 节一致）：")
w(f"--   app_user        {len(APP_USERS)}  （1 管理员 + 2 前台 + {len(APP_USERS) - 3} 客户账号，口令统一 Hotel@123）")
w(f"--   customer        {len(CUSTOMERS)}  （{sum(1 for c in CUSTOMERS if c[0] is not None)} 个关联账号 + {sum(1 for c in CUSTOMERS if c[0] is None)} 个线下散客）")
w("--   room_type       6   （标准间 / 高级大床房 / 豪华双床房 / 家庭房 / 行政套房 / 无障碍房）")
w("--   room           40   （5–12 层，每层 5 间，六种房态全覆盖）")
w("--   rate_plan      10   （国庆加价 ×5 房型 + 元旦加价 ×5 房型）")
w(f"--   reservation    {len(reservations)}  （六种状态，含 B3 首尾相接、B4 取消后重订两组边界数据）")
w(f"--   check_in_record {len(checkins)}  （{sum(1 for r in checkins if r['status'] == 'checked_out')} 条已退房 + {sum(1 for r in checkins if r['status'] == 'checked_in')} 条在住）")
w(f"--   payment        {len(payments)}  （{kind_counts.get('deposit', 0)} 押金 + {kind_counts.get('room_fee', 0)} 房费尾款 + {kind_counts.get('refund', 0)} 退款 + {kind_counts.get('service_fee', 0)} 在住服务费）")
w(f"--   room_status_log    {7 + sum(1 for v in final_status.values() if v != 'available')}（手工历史 7 + 触发器自动 {sum(1 for v in final_status.values() if v != 'available')} 条）")
w(f"--   service_item    {len(SERVICE_ITEMS)} / service_order {order_count}（增值服务，F07 结算与统计用）")
w("--")
w("-- 执行：")
w("--   chcp 65001")
w("--   psql -U postgres -d yunqi_hotel -v ON_ERROR_STOP=1 -f sql/03_seed.sql")
w("-- 可重复执行：先 TRUNCATE ... RESTART IDENTITY CASCADE，再按外键顺序插入；")
w("-- 整段包在事务里，任何一步失败即整体回滚，不留半套数据。")
w("-- =============================================================================")
w()
w("\\set ON_ERROR_STOP on")
w("\\encoding UTF8")
w()
w("SET search_path TO public;")
w()
w("BEGIN;")
w()
w("-- 清空并按外键倒序重置自增（幂等）")
w("TRUNCATE TABLE service_order, service_item, payment, check_in_record,")
w("               room_status_log, reservation, rate_plan, room,")
w("               room_type, customer, app_user")
w("    RESTART IDENTITY CASCADE;")
w()

# --- app_user ---
w("-- ----------------------------------------------------------------------------")
w("-- 1) app_user 账号（口令统一 Hotel@123，PBKDF2 哈希由 Django 6.1 生成）")
w("-- ----------------------------------------------------------------------------")
w("INSERT INTO app_user (username, password, display_name, role, phone, email) VALUES")
rows = []
for username, display, role, phone, email in APP_USERS:
    rows.append(f"    ({q(username)}, {q(PWD_HASH)}, {q(display)}, {q(role)}, {q(phone)}, {q(email)})")
w(",\n".join(rows) + ";")
w()

# --- room_type ---
w("-- ----------------------------------------------------------------------------")
w("-- 2) room_type 房型（标准价 288–1288 元/晚）")
w("-- ----------------------------------------------------------------------------")
w("INSERT INTO room_type (name, bed_type, area, capacity, base_price, description) VALUES")
rows = []
for name, bed, area, cap, price, desc in ROOM_TYPES:
    rows.append(f"    ({q(name)}, {q(bed)}, {area}, {cap}, {money(price)}, {q(desc)})")
w(",\n".join(rows) + ";")
w()

# --- rate_plan ---
w("-- ----------------------------------------------------------------------------")
w("-- 3) rate_plan 价格方案（同房型区间互不重叠，受 ex_rate_plan_no_overlap 约束）")
w("-- ----------------------------------------------------------------------------")
type_id = {name: i for i, (name, *_rest) in enumerate(ROOM_TYPES, start=1)}
w("INSERT INTO rate_plan (room_type_id, name, price, valid_from, valid_to) VALUES")
rows = []
for tname, start, end, price in RATE_PLANS:
    label = "国庆加价" if start.month == 10 else "元旦加价"
    rows.append(f"    ({type_id[tname]}, {q(label + '·' + tname)}, {money(price)}, {d(start)}, {d(end)})")
w(",\n".join(rows) + ";")
w()

# --- customer ---
w("-- ----------------------------------------------------------------------------")
w("-- 4) customer 客户档案（第 7 条为线下散客，user_id 为空）")
w("-- ----------------------------------------------------------------------------")
w("INSERT INTO customer (user_id, name, phone, id_card, email, remark) VALUES")
rows = []
for user_id, name, phone, id_card, email, remark in CUSTOMERS:
    rows.append(f"    ({'NULL' if user_id is None else user_id}, {q(name)}, {q(phone)}, "
                f"{q(id_card)}, {q(email)}, {q(remark)})")
w(",\n".join(rows) + ";")
w()

# --- room ---
w("-- ----------------------------------------------------------------------------")
w("-- 5) room 房间（先统一建成 available，再在文末按业务流转改房态以产生变更日志）")
w("-- ----------------------------------------------------------------------------")
w("INSERT INTO room (room_type_id, room_no, floor, orientation, status, remark) VALUES")
rows = []
for idx, (no, floor, tname, orient) in enumerate(ROOMS, start=1):
    remark = "无障碍设施" if tname == "无障碍房" else None
    rows.append(f"    ({type_id[tname]}, {q(no)}, {floor}, {q(orient)}, 'available', {q(remark)})")
w(",\n".join(rows) + ";")
w()

# --- reservation ---
w("-- ----------------------------------------------------------------------------")
w(f"-- 6) reservation 预订 {len(reservations)} 条")
w("--    同一房间的活跃区间（pending/confirmed/checked_in）互不重叠；")
w("--    含两组边界数据：B3 首尾相接（离店日 = 下一段入住日，合法）、")
w("--    B4 取消后同区间重订（取消单不参与排他约束，合法）。")
w("-- ----------------------------------------------------------------------------")
w("INSERT INTO reservation (reservation_no, customer_id, room_id, check_in_date,")
w("                         check_out_date, guest_count, price_per_night, total_amount,")
w("                         status, source, remark) VALUES")
rows = []
for r in reservations:
    rows.append(
        f"    ({q(r['no'])}, {r['customer_id']}, {r['room_id']}, {d(r['start'])}, {d(r['end'])}, "
        f"{r['guest_count']}, {money(r['price'])}, {money(r['total'])}, "
        f"{q(r['status'])}, {q(r['source'])}, {q(r['remark'] or None)})"
    )
w(",\n".join(rows) + ";")
w()

# --- check_in_record ---
w("-- ----------------------------------------------------------------------------")
w(f"-- 7) check_in_record 入住记录 {len(checkins)} 条（{sum(1 for r in checkins if r['status'] == 'checked_out')} 已退房 + {sum(1 for r in checkins if r['status'] == 'checked_in')} 在住，在住的 actual_checkout_at 为空）")
w("-- ----------------------------------------------------------------------------")
w("INSERT INTO check_in_record (reservation_id, guest_name, guest_phone, guest_id_card,")
w("                             check_in_at, actual_checkout_at, deposit_amount,")
w("                             room_charge, service_charge, total_charge, remark) VALUES")
rows = []
for rec in checkins:
    remark = "在店，尚未退房" if rec["status"] == "checked_in" else None
    rows.append(
        f"    ({rec['reservation_id']}, {q(rec['guest_name'])}, {q(rec['guest_phone'])}, {q(rec['guest_id_card'])}, "
        f"{ts(rec['check_in_at'])}, {ts(rec['actual_checkout_at'])}, {money(rec['deposit'])}, "
        f"{money(rec['room_charge'])}, {money(rec['service_charge'])}, {money(rec['total_charge'])}, "
        f"{q(remark)})"
    )
w(",\n".join(rows) + ";")
w()

# --- service_item / service_order ---
w("-- ----------------------------------------------------------------------------")
w("-- 8) service_item 增值服务项目 + service_order 消费明细")
w("-- ----------------------------------------------------------------------------")
w("INSERT INTO service_item (code, name, unit, price) VALUES")
rows = [f"    ({q(code)}, {q(name)}, {q(unit)}, {money(price)})" for code, name, unit, price in SERVICE_ITEMS]
w(",\n".join(rows) + ";")
w()

service_id = {code: i for i, (code, *_rest) in enumerate(SERVICE_ITEMS, start=1)}
w()
w("INSERT INTO service_order (check_in_record_id, service_item_id, quantity, unit_price, ordered_at) VALUES")
rows = []
for rec_idx, rec in enumerate(checkins, start=1):
    for od in rec["orders"]:
        rows.append(
            f"    ({rec_idx}, {service_id[od['code']]}, {od['quantity']}, {money(od['unit_price'])}, "
            f"{ts((rec['check_in_at'][0], 16, 0))})"
        )
w(",\n".join(rows) + ";")
w()

# --- payment ---
w("-- ----------------------------------------------------------------------------")
w(f"-- 9) payment 支付流水 {len(payments)} 笔（kind=refund 的金额也记正数，靠 kind 区分方向）")
w("-- ----------------------------------------------------------------------------")
w("INSERT INTO payment (payment_no, check_in_record_id, kind, method, amount, paid_at,")
w("                     operator_user_id, remark) VALUES")
rows = []
for p in payments:
    op = RECEPTIONIST_IDS[p["record_idx"] % 2]
    rows.append(
        f"    ({q(p['no'])}, {p['record_idx'] + 1}, {q(p['kind'])}, {q(p['method'])}, "
        f"{money(p['amount'])}, {ts(p['when'])}, {op}, {q(p['remark'] or None)})"
    )
w(",\n".join(rows) + ";")
w()

# --- room_status_log 手工历史 ---
w("-- ----------------------------------------------------------------------------")
w("-- 10) room_status_log 手工历史（触发器会自动记录房态变更，这里补几段典型轨迹）")
w("-- ----------------------------------------------------------------------------")
hist_room = ROOM_BY_NO["801"]
w("INSERT INTO room_status_log (room_id, from_status, to_status, changed_by, changed_at, reason) VALUES")
w(f"    ({hist_room}, NULL, 'available', 2, TIMESTAMPTZ '2026-11-01 09:00:00+08', '房间交付，初始化为可用'),")
w(f"    ({hist_room}, 'available', 'reserved', 2, TIMESTAMPTZ '2026-11-05 10:20:00+08', '客人电话预订'),")
w(f"    ({hist_room}, 'reserved', 'occupied', 2, TIMESTAMPTZ '2026-12-02 14:05:00+08', '办理入住'),")
w(f"    ({hist_room}, 'occupied', 'cleaning', 3, TIMESTAMPTZ '2026-12-05 12:15:00+08', '退房后转清扫'),")
w(f"    ({hist_room}, 'cleaning', 'available', 3, TIMESTAMPTZ '2026-12-05 15:40:00+08', '清扫完成，恢复可用'),")
w(f"    ({hist_room}, 'available', 'maintenance', 2, TIMESTAMPTZ '2026-12-10 08:30:00+08', '空调检修'),")
w(f"    ({hist_room}, 'maintenance', 'available', 2, TIMESTAMPTZ '2026-12-10 17:10:00+08', '检修完成');")
w()

# --- room 状态更新（触发器产生日志）---
w("-- ----------------------------------------------------------------------------")
w("-- 11) 按业务流转更新房态（AFTER UPDATE 触发器自动写入 room_status_log）：")
w("--     checked_in 的房间 → occupied；有 future 预订 → reserved；")
w("--     空闲房里挑 2 间 cleaning、1 间 maintenance、1 间 disabled。")
w("-- ----------------------------------------------------------------------------")
w("UPDATE room SET status = v.status, updated_at = now()")
w("FROM (VALUES")
rows = [f"    ({rid}, {q(final_status[rid])})" for rid in ALL_ROOM_IDS if final_status[rid] != "available"]
w(",\n".join(rows))
w(") AS v(id, status)")
w("WHERE room.id = v.id;")
w()
w("-- updated_at 触发器已被更新语句自然触发，这里再校正一次时间基线不影响数据")
w("ANALYZE;")
w()

# --- 自检 ---
w("-- ----------------------------------------------------------------------------")
w("-- 12) 自检：条数、状态分布、重叠检测、可用房函数、视图")
w("-- ----------------------------------------------------------------------------")
w("SELECT 'app_user'        AS table_name, count(*) AS rows FROM app_user")
w("UNION ALL SELECT 'customer',        count(*) FROM customer")
w("UNION ALL SELECT 'room_type',       count(*) FROM room_type")
w("UNION ALL SELECT 'room',            count(*) FROM room")
w("UNION ALL SELECT 'rate_plan',       count(*) FROM rate_plan")
w("UNION ALL SELECT 'reservation',     count(*) FROM reservation")
w("UNION ALL SELECT 'check_in_record', count(*) FROM check_in_record")
w("UNION ALL SELECT 'service_item',    count(*) FROM service_item")
w("UNION ALL SELECT 'service_order',   count(*) FROM service_order")
w("UNION ALL SELECT 'payment',         count(*) FROM payment")
w("UNION ALL SELECT 'room_status_log', count(*) FROM room_status_log")
w("ORDER BY table_name;")
w()
w("SELECT status, count(*) AS cnt FROM reservation GROUP BY status ORDER BY status;")
w()
w("SELECT status, count(*) AS cnt FROM room GROUP BY status ORDER BY status;")
w()
w("-- 重叠检测：活跃状态下同一房间区间相交的行数，期望 0")
w("SELECT count(*) AS overlap_pairs")
w("FROM reservation a")
w("JOIN reservation b ON a.room_id = b.room_id AND a.id < b.id")
w("WHERE a.status IN ('pending', 'confirmed', 'checked_in')")
w("  AND b.status IN ('pending', 'confirmed', 'checked_in')")
w("  AND a.during && b.during;")
w()
w("-- 支付平衡：押金 + 房费尾款 - 退款 应等于（应收合计 - 未结部分），这里只看口径是否有异常行")
w("SELECT p.kind, count(*) AS cnt, sum(p.amount) AS amount_sum")
w("FROM payment p GROUP BY p.kind ORDER BY p.kind;")
w()
w("-- 可用房函数：演示 2026-12-20 至 2026-12-22 的可订房间数")
w("SELECT count(*) AS available_rooms_demo")
w("FROM fn_available_rooms(DATE '2026-12-20', DATE '2026-12-22');")
w()
w("-- 视图连通性")
w("SELECT count(*) AS reservation_detail_rows FROM v_reservation_detail;")
w("SELECT count(*) AS check_in_detail_rows FROM v_check_in_detail;")
w()
w(f"SELECT '03_seed.sql 执行完成：{len(reservations)} 条预订 / {len(checkins)} 条入住 / {len(payments)} 笔支付 / {order_count} 条服务明细' AS result;")
w()
w("COMMIT;")
w()

text = "\n".join(lines) + "\n"

if "--check" in sys.argv:
    print("[check] 行数:", len(lines))
    print("[check] 预订:", len(reservations), "状态分布:", counts)
    print("[check] 入住:", len(checkins), "支付:", len(payments), kind_counts)
    print("[check] 房态:", status_cover)
    raise SystemExit(0)

OUT.write_text(text, encoding="utf-8", newline="\n")
print(f"[ok] 已生成 {OUT.relative_to(ROOT)}（{len(text.splitlines())} 行，{len(text.encode('utf-8'))} 字节）")
print(f"[ok] 预订 {len(reservations)} 条，状态 {counts}")
print(f"[ok] 入住 {len(checkins)} 条，支付 {len(payments)} 条 {kind_counts}")
print(f"[ok] 房态分布 {status_cover}")
