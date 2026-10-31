"""校验演示库是否与 `docs/05-查询结果与测试记录.md` 记录的数字一致（只读）。

用法：
    python tools/verify_docs05.py

说明：
  - 只做 SELECT，不写库；连库参数读仓库根 `.env`（DB_USER / DB_PASSWORD 等）。
  - 各项 SQL **逐字复制** `sql/04_queries.sql` 的 Q1/Q3/Q4-b/Q5/Q6-a/Q6-b/Q7 与状态分布，
    避免另写一套口径造成假报警。
  - 期望值来自 `docs/05-查询结果与测试记录.md`（13 表版，2026-10-30 17:22 实跑）。
  - 打印 PASS / MISMATCH；退出码 0 = 全部一致。演示库被测试写入污染时，重跑
    `sql/03_seed.sql`（幂等）恢复规格后再跑本脚本即可复验。
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402

PASS = 0
FAIL = 0


def norm(value):
    """把 Decimal / date / tuple / list 递归归一成便于比较的字符串。"""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, (list, tuple)):
        return [norm(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def check(label: str, actual, expected) -> None:
    global PASS, FAIL
    actual = [norm(row) for row in actual] if isinstance(actual, list) else norm(actual)
    expected = [norm(row) for row in expected] if isinstance(expected, list) else norm(expected)
    ok = actual == expected
    if ok:
        PASS += 1
        print(f"  [PASS] {label} = {actual!r}")
    else:
        FAIL += 1
        print(f"  [MISMATCH] {label}\n      库中: {actual!r}\n      文档: {expected!r}")


def rows(sql: str, params=None) -> list[tuple]:
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        return cur.fetchall()


def one(sql: str, params=None):
    result = rows(sql, params)
    return result[0][0] if result else None


# --- 与 sql/04_queries.sql 逐字一致 -------------------------------------------------

SQL_Q1 = """
SELECT room_id AS 房间ID
FROM fn_available_rooms(DATE '2026-12-20', DATE '2026-12-22')
"""

SQL_Q3 = """
WITH month_series AS (
    SELECT d::date                              AS month_start,
           (d + INTERVAL '1 month')::date       AS month_end
    FROM generate_series(DATE '2026-09-01', DATE '2027-01-01', INTERVAL '1 month') AS d
),
sold AS (
    SELECT rt.id                            AS room_type_id,
           date_trunc('month', stay)::date  AS month_start,
           count(*)                         AS sold_nights
    FROM reservation r
    JOIN room rm      ON rm.id = r.room_id
    JOIN room_type rt ON rt.id = rm.room_type_id
    CROSS JOIN LATERAL generate_series(r.check_in_date, r.check_out_date - 1, INTERVAL '1 day') AS stay
    WHERE r.status IN ('confirmed', 'checked_in', 'checked_out')
    GROUP BY 1, 2
),
blocked AS (
    SELECT rt.id AS room_type_id,
           ms.month_start,
           sum(GREATEST(0,
                   LEAST(b.end_date, ms.month_end)
                 - GREATEST(b.start_date, ms.month_start))) AS blocked_nights
    FROM month_series ms
    CROSS JOIN room_type rt
    JOIN room rm      ON rm.room_type_id = rt.id
    JOIN room_block b ON b.room_id = rm.id
    WHERE b.during && daterange(ms.month_start, ms.month_end, '[)')
    GROUP BY rt.id, ms.month_start
),
sellable AS (
    SELECT rt.id AS room_type_id,
           rt.name,
           ms.month_start,
           count(rm.id) * (ms.month_end - ms.month_start)
             - COALESCE(bl.blocked_nights, 0) AS sellable_nights
    FROM month_series ms
    CROSS JOIN room_type rt
    LEFT JOIN room rm ON rm.room_type_id = rt.id
    LEFT JOIN blocked bl ON bl.room_type_id = rt.id AND bl.month_start = ms.month_start
    WHERE rt.is_active
    GROUP BY rt.id, rt.name, ms.month_start, ms.month_end, bl.blocked_nights
)
SELECT s.name                                    AS 房型,
       to_char(s.month_start, 'YYYY-MM')          AS 月份,
       COALESCE(so.sold_nights, 0)               AS 已售房夜,
       s.sellable_nights                         AS 可售房夜,
       round(COALESCE(so.sold_nights, 0)::numeric / s.sellable_nights * 100, 2) AS 入住率百分比
FROM sellable s
LEFT JOIN sold so ON so.room_type_id = s.room_type_id AND so.month_start = s.month_start
ORDER BY s.month_start, s.name
"""

SQL_Q4B = """
WITH settled AS (
    SELECT cir.id                                        AS check_in_record_id,
           date_trunc('month', cir.actual_checkout_at)::date AS month_start
    FROM check_in_record cir
    JOIN reservation r ON r.id = cir.reservation_id
    WHERE r.status = 'checked_out'
      AND cir.actual_checkout_at IS NOT NULL
),
flows AS (
    SELECT s.month_start, s.check_in_record_id, p.kind, p.amount
    FROM settled s
    JOIN payment p ON p.check_in_record_id = s.check_in_record_id
    WHERE s.month_start >= DATE '2026-01-01'
      AND s.month_start <  DATE '2027-01-01'
)
SELECT to_char(month_start, 'YYYY-MM')                                              AS 月份,
       count(DISTINCT check_in_record_id)                                           AS 涉及入住记录,
       COALESCE(SUM(amount) FILTER (WHERE kind IN ('room_fee', 'service_fee')), 0)  AS 收入,
       COALESCE(SUM(amount) FILTER (WHERE kind = 'refund'), 0)                      AS 退款,
       COALESCE(SUM(amount) FILTER (WHERE kind IN ('room_fee', 'service_fee')), 0)
         - COALESCE(SUM(amount) FILTER (WHERE kind = 'refund'), 0)                  AS 净收入
FROM flows
GROUP BY 1
ORDER BY 1
"""

SQL_Q5 = """
WITH t AS (
    SELECT rt.name                              AS 房型,
           count(*)                             AS 订单数,
           SUM(COALESCE(cir.actual_checkout_at::date - cir.check_in_at::date,
                        r.check_out_date - r.check_in_date)) AS 房夜数,
           SUM(r.check_out_date - r.check_in_date)       AS 计划房夜数,
           SUM(r.total_amount)                  AS 预订金额
    FROM reservation r
    JOIN room rm      ON rm.id = r.room_id
    JOIN room_type rt ON rt.id = rm.room_type_id
    LEFT JOIN check_in_record cir ON cir.reservation_id = r.id
    WHERE r.status IN ('confirmed', 'checked_in', 'checked_out')
    GROUP BY rt.name
)
SELECT 房型, 订单数, 房夜数, 计划房夜数, 预订金额,
       RANK() OVER (ORDER BY 订单数 DESC) AS 订单数排名,
       RANK() OVER (ORDER BY 房夜数 DESC) AS 房夜数排名
FROM t
ORDER BY 订单数 DESC, 房夜数 DESC
LIMIT 3
"""

SQL_Q6A = """
SELECT r.room_no AS 房号
FROM room r
JOIN room_type rt ON rt.id = r.room_type_id
WHERE NOT EXISTS (
        SELECT 1
        FROM reservation rv
        WHERE rv.room_id = r.id
          AND rv.during && daterange(DATE '2026-09-16', DATE '2026-12-15', '[)')
      )
  AND NOT EXISTS (
        SELECT 1
        FROM reservation rv
        WHERE rv.room_id = r.id
          AND rv.status IN ('pending', 'confirmed', 'checked_in')
          AND rv.during && daterange(DATE '2026-12-15', DATE '2027-01-29', '[)')
      )
ORDER BY r.room_no
"""

SQL_Q6B = """
SELECT r.source                                                             AS 预订来源,
       count(*)                                                             AS 订单总数,
       count(*) FILTER (WHERE r.status = 'cancelled')                       AS 取消数,
       count(*) FILTER (WHERE r.status = 'no_show')                         AS 未到店数,
       round(count(*) FILTER (WHERE r.status = 'cancelled')::numeric
             / count(*) * 100, 2)                                           AS 取消率百分比
FROM reservation r
GROUP BY r.source
ORDER BY 取消率百分比 DESC
"""

SQL_Q7 = """
SELECT r.reservation_no AS 预订号, v.actual_checkout_at AS 退房时间, v.balance AS 余额
FROM v_check_in_detail v
JOIN reservation r ON r.id = v.reservation_id
JOIN room rm       ON rm.id = r.room_id
ORDER BY v.check_in_at DESC
LIMIT 10
"""


def main() -> int:
    with connection.cursor() as cur:
        cur.execute("SELECT current_database(), current_user")
        db_name, db_user = cur.fetchone()
    print(f"[连接] {db_user}@{db_name}\n")

    print("## 表行数")
    for table, expected in [
        ("app_user", 27), ("customer", 30), ("room_type", 6), ("room", 40),
        ("rate_plan", 10), ("reservation", 96), ("reservation_price", 239),
        ("check_in_record", 48), ("payment", 96), ("room_status_log", 11),
        ("room_block", 4), ("service_item", 8), ("service_order", 57),
    ]:
        check(f"count({table})", one(f"SELECT count(*) FROM {table}"), expected)

    print("\n## 预订状态分布（种子规格）")
    counts = dict(rows("SELECT status, count(*) FROM reservation GROUP BY status"))
    for status, expected in [
        ("pending", 14), ("confirmed", 16), ("checked_in", 8),
        ("checked_out", 40), ("cancelled", 12), ("no_show", 6),
    ]:
        check(f"{status} 条数", counts.get(status, 0), expected)

    print("\n## Q1 可用房（2026-12-20 ~ 2026-12-22）")
    check("行数", len(rows(SQL_Q1)), 35)

    print("\n## Q3 月度入住率（30 行，抽查 4 格）")
    q3 = rows(SQL_Q3)
    q3_map = {(name, month): (sold, sellable) for name, month, sold, sellable, _rate in q3}
    check("行数", len(q3), 30)
    check("2026-09 标准间", q3_map.get(("标准间", "2026-09")), (7, 285))
    check("2026-12 标准间", q3_map.get(("标准间", "2026-12")), (14, 254))
    check("2026-12 高级大床房", q3_map.get(("高级大床房", "2026-12")), (20, 310))
    check("2026-09 无障碍房", q3_map.get(("无障碍房", "2026-09")), (11, 150))

    print("\n## Q4-b 月度净收入")
    q4b = rows(SQL_Q4B)
    q4b_map = {month: (cnt, income, refund, net) for month, cnt, income, refund, net in q4b}
    check("行数", len(q4b), 4)
    for month, cnt, net in [
        ("2026-09", 12, "12400.00"),
        ("2026-10", 15, "23568.00"),
        ("2026-11", 12, "11092.00"),
        ("2026-12", 1, "376.00"),
    ]:
        got = q4b_map.get(month)
        check(f"{month} 结算笔数/净收入", (got[0], got[3]) if got else None, (cnt, net))

    print("\n## Q5 房型排行 Top3")
    check(
        "Top3（房型/订单数/房夜数/金额）",
        [(name, orders, nights, amount) for name, orders, nights, planned, amount, *_ in rows(SQL_Q5)],
        [
            ("高级大床房", 20, 55, "21340.00"),
            ("标准间", 20, 40, "11808.00"),
            ("无障碍房", 7, 22, "7216.00"),
        ],
    )

    print("\n## Q6-a 长期空闲房间")
    check("房号", [row[0] for row in rows(SQL_Q6A)], ["1003", "1004", "1204", "902"])

    print("\n## Q6-b 各来源取消率")
    q6b = {source: (total, cancelled, no_show, rate) for source, total, cancelled, no_show, rate in rows(SQL_Q6B)}
    check("walk_in", q6b.get("walk_in"), (34, 6, 2, "17.65"))
    check("phone", q6b.get("phone"), (29, 3, 3, "10.34"))
    check("online", q6b.get("online"), (33, 3, 1, "9.09"))

    print("\n## Q7 结算与余额（最近 10 条）")
    q7 = rows(SQL_Q7)
    in_house = sorted(
        (no, str(bal)) for no, out_at, bal in q7 if out_at is None
    )
    check("在住 8 条余额", in_house, sorted([
        ("R20261213060", "1352.00"), ("R20261213064", "664.00"),
        ("R20261214058", "576.00"), ("R20261214059", "1264.00"),
        ("R20261214061", "952.00"), ("R20261214062", "964.00"),
        ("R20261214063", "1864.00"), ("R20261214065", "1352.00"),
    ]))
    settled = [(no, str(bal)) for no, out_at, bal in q7 if out_at is not None]
    check("已退房 2 条余额为 0", settled, [("R20261130040", "0.00"), ("R20261128039", "0.00")])

    print(f"\n结果：{PASS} 项一致 / {FAIL} 项不一致")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
