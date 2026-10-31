"""管理区：F09 经营统计报表（P11）+ P12 预订总览（只读）。

页面契约见 `docs/页面约定.md`：
- P11 `/manage/reports/`：4 张图（入住率趋势 / 月度净收入 / 房型排行 / 来源取消率）+ 日期筛选
- P12 `/manage/reservations/`：管理员视角的预订总览（只读 + CSV 导出）

数据口径（**必须**与 `sql/04_queries.sql` 一致，页面不另算一套）：
- 入住率（Q3）：已售房夜 = 有效预订（confirmed/checked_in/checked_out）按天展开、离店日不计；
  可售房夜 = 房型房间数 × 区间天数 − 该区间内维修/停用房夜（`room_block` 交集）；
- 月度净收入（Q4-b）：按**退房结算日期** `check_in_record.actual_checkout_at` 归月，
  收入 = `room_fee + service_fee`，押金不计，退款冲减同一结算月；
- 房型排行（Q5）：订单数与房夜数双口径，房夜优先用 `check_in_record` 的实际区间；
- 来源取消率（Q6-b）：取消率 = 取消数 ÷ 同期订单数，未到店单独列出、计入分母不计入分子。

真库走手写 SQL（`connection.cursor()`，报告 4 章要贴真实执行的 SQL）；
离线 sqlite 冒烟模式没有 `generate_series` / `daterange` / `FILTER`，用等价的 Python 聚合兜底，
两种模式给同一份 `chart_data`，模板与前端逻辑不变。
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render

from core.decorators import role_required
from core.models import (
    PAYMENT_KIND_CHOICES,
    RESERVATION_SOURCE_CHOICES,
    RESERVATION_STATUS_CHOICES,
    CheckInRecord,
    Payment,
    Reservation,
    Room,
    RoomBlock,
    RoomType,
)

STATUS_LABELS = dict(RESERVATION_STATUS_CHOICES)
SOURCE_LABELS = dict(RESERVATION_SOURCE_CHOICES)
KIND_LABELS = dict(PAYMENT_KIND_CHOICES)

ACTIVE_STATUSES = ("confirmed", "checked_in", "checked_out")
PAGE_SIZE = 20
MAX_RANGE_DAYS = 400
EXPORT_LIMIT = 5000


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #
def _try_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _months_between(start: date, end: date) -> list[date]:
    """返回覆盖 [start, end] 的月份首日列表（含首尾所在月）。"""
    cursor = _month_start(start)
    last = _month_start(end)
    months: list[date] = []
    while cursor <= last and len(months) < 60:
        months.append(cursor)
        cursor = _next_month(cursor)
    return months


def _clip(start: date, end: date, low: date, high: date) -> int:
    """[start, end) 与 [low, high) 的交集天数。"""
    lo = max(start, low)
    hi = min(end, high)
    return max(0, (hi - lo).days)


def _round2(value: float) -> float:
    return round(float(value) + 1e-12, 2)


# --------------------------------------------------------------------------- #
# 四个数据集的取数（真库 SQL / 离线 Python 兜底）
# --------------------------------------------------------------------------- #
def _occupancy_pg(date_from: date, date_to: date) -> list[dict]:
    sql = """
        WITH months AS (
            SELECT d::date                             AS month_start,
                   (d + INTERVAL '1 month')::date      AS month_end
            FROM generate_series(
                     date_trunc('month', %(date_from)s::date),
                     date_trunc('month', %(date_to)s::date),
                     INTERVAL '1 month'
                 ) AS d
        ),
        sold AS (
            SELECT rm.room_type_id,
                   date_trunc('month', stay)::date AS month_start,
                   count(*)                        AS sold_nights
            FROM reservation r
            JOIN room rm ON rm.id = r.room_id
            CROSS JOIN LATERAL generate_series(
                     GREATEST(r.check_in_date, %(date_from)s::date),
                     LEAST(r.check_out_date - 1, %(date_to)s::date),
                     INTERVAL '1 day'
                 ) AS stay
            WHERE r.status IN ('confirmed', 'checked_in', 'checked_out')
              AND r.check_in_date <= %(date_to)s::date
              AND r.check_out_date > %(date_from)s::date
            GROUP BY 1, 2
        ),
        blocked AS (
            SELECT rm.room_type_id,
                   ms.month_start,
                   sum(GREATEST(0,
                           LEAST(b.end_date, ms.month_end)
                         - GREATEST(b.start_date, ms.month_start))) AS blocked_nights
            FROM months ms
            JOIN room rm      ON TRUE
            JOIN room_block b ON b.room_id = rm.id
            WHERE b.during && daterange(ms.month_start, ms.month_end, '[)')
            GROUP BY 1, 2
        ),
        sellable AS (
            SELECT rt.id AS room_type_id,
                   rt.name,
                   ms.month_start,
                   count(rm.id) * (ms.month_end - ms.month_start)
                     - COALESCE(bl.blocked_nights, 0) AS sellable_nights
            FROM months ms
            JOIN room_type rt ON rt.is_active
            LEFT JOIN room rm  ON rm.room_type_id = rt.id
            LEFT JOIN blocked bl ON bl.room_type_id = rt.id AND bl.month_start = ms.month_start
            GROUP BY rt.id, rt.name, ms.month_start, ms.month_end, bl.blocked_nights
        )
        SELECT s.name,
               s.month_start,
               COALESCE(so.sold_nights, 0) AS sold_nights,
               s.sellable_nights
        FROM sellable s
        LEFT JOIN sold so ON so.room_type_id = s.room_type_id AND so.month_start = s.month_start
        ORDER BY s.month_start, s.name
    """
    rows: list[dict] = []
    with connection.cursor() as cur:
        cur.execute(sql, {"date_from": date_from, "date_to": date_to})
        for name, month_start, sold, sellable in cur.fetchall():
            sellable = int(sellable or 0)
            rate = _round2(sold / sellable * 100) if sellable else 0.0
            rows.append(
                {
                    "room_type": name,
                    "month": month_start.isoformat()[:7],
                    "sold": int(sold or 0),
                    "sellable": sellable,
                    "rate": rate,
                }
            )
    return rows


def _occupancy_python(date_from: date, date_to: date) -> list[dict]:
    months = _months_between(date_from, date_to)
    room_types = list(RoomType.objects.filter(is_active=True).order_by("id"))
    room_ids_by_type: dict[int, list[int]] = {rt.pk: [] for rt in room_types}
    for room in Room.objects.all().only("pk", "room_type_id"):
        if room.room_type_id in room_ids_by_type:
            room_ids_by_type[room.room_type_id].append(room.pk)

    sold: dict[tuple[int, date], int] = {}
    for reservation in Reservation.objects.filter(status__in=ACTIVE_STATUSES).only(
        "pk", "room_id", "check_in_date", "check_out_date"
    ):
        room_type_id = None
        for rt_id, ids in room_ids_by_type.items():
            if reservation.room_id in ids:
                room_type_id = rt_id
                break
        if room_type_id is None:
            continue
        stay = reservation.check_in_date
        while stay < reservation.check_out_date:
            if date_from <= stay <= date_to:
                key = (room_type_id, _month_start(stay))
                sold[key] = sold.get(key, 0) + 1
            stay += timedelta(days=1)

    blocked: dict[tuple[int, date], int] = {}
    for block in RoomBlock.objects.all().only("pk", "room_id", "start_date", "end_date"):
        room_type_id = None
        for rt_id, ids in room_ids_by_type.items():
            if block.room_id in ids:
                room_type_id = rt_id
                break
        if room_type_id is None:
            continue
        for month in months:
            days = _clip(block.start_date, block.end_date, max(month, date_from), _next_month(month))
            if days:
                key = (room_type_id, month)
                blocked[key] = blocked.get(key, 0) + days

    rows: list[dict] = []
    for month in months:
        month_end = _next_month(month)
        for rt in room_types:
            room_count = len(room_ids_by_type.get(rt.pk, []))
            span_days = _clip(max(month, date_from), month_end, date_from, date_to + timedelta(days=1))
            sellable = room_count * span_days - blocked.get((rt.pk, month), 0)
            sold_nights = sold.get((rt.pk, month), 0)
            rate = _round2(sold_nights / sellable * 100) if sellable else 0.0
            rows.append(
                {
                    "room_type": rt.name,
                    "month": month.isoformat()[:7],
                    "sold": sold_nights,
                    "sellable": sellable,
                    "rate": rate,
                }
            )
    rows.sort(key=lambda row: (row["month"], row["room_type"]))
    return rows


def _revenue_pg(date_from: date, date_to: date) -> list[dict]:
    sql = """
        SELECT date_trunc('month', cir.actual_checkout_at)::date AS month_start,
               count(DISTINCT cir.id)                            AS records,
               COALESCE(SUM(p.amount) FILTER (WHERE p.kind IN ('room_fee', 'service_fee')), 0) AS income,
               COALESCE(SUM(p.amount) FILTER (WHERE p.kind = 'refund'), 0)                      AS refund
        FROM check_in_record cir
        JOIN reservation r ON r.id = cir.reservation_id
        JOIN payment p     ON p.check_in_record_id = cir.id
        WHERE r.status = 'checked_out'
          AND cir.actual_checkout_at IS NOT NULL
          AND cir.actual_checkout_at >= %(date_from)s::date
          AND cir.actual_checkout_at <  (%(date_to)s::date + INTERVAL '1 day')
        GROUP BY 1
        ORDER BY 1
    """
    rows: list[dict] = []
    with connection.cursor() as cur:
        cur.execute(sql, {"date_from": date_from, "date_to": date_to})
        for month_start, records, income, refund in cur.fetchall():
            income = Decimal(income or 0)
            refund = Decimal(refund or 0)
            rows.append(
                {
                    "month": month_start.isoformat()[:7],
                    "records": int(records or 0),
                    "income": float(income),
                    "refund": float(refund),
                    "net": float(income - refund),
                }
            )
    return rows


def _revenue_python(date_from: date, date_to: date) -> list[dict]:
    buckets: dict[date, dict] = {}
    records = (
        CheckInRecord.objects.select_related("reservation")
        .filter(reservation__status="checked_out", actual_checkout_at__isnull=False)
        .all()
    )
    for record in records:
        local = record.actual_checkout_at.date()
        if not (date_from <= local <= date_to):
            continue
        key = _month_start(local)
        bucket = buckets.setdefault(key, {"records": set(), "income": Decimal("0"), "refund": Decimal("0")})
        bucket["records"].add(record.pk)
    # 付款按记录逐条归集（离线数据量小，直白比花哨更可靠）
    for record in records:
        local = record.actual_checkout_at.date()
        if not (date_from <= local <= date_to):
            continue
        key = _month_start(local)
        bucket = buckets.setdefault(key, {"records": set(), "income": Decimal("0"), "refund": Decimal("0")})
        bucket["records"].add(record.pk)
        for payment in Payment.objects.filter(check_in_record_id=record.pk):
            if payment.kind in ("room_fee", "service_fee"):
                bucket["income"] += payment.amount
            elif payment.kind == "refund":
                bucket["refund"] += payment.amount
    rows = []
    for key in sorted(buckets):
        bucket = buckets[key]
        rows.append(
            {
                "month": key.isoformat()[:7],
                "records": len(bucket["records"]),
                "income": float(bucket["income"]),
                "refund": float(bucket["refund"]),
                "net": float(bucket["income"] - bucket["refund"]),
            }
        )
    return rows


def _top_rooms_pg(date_from: date, date_to: date) -> list[dict]:
    sql = """
        SELECT rt.name,
               count(*) AS orders,
               SUM(COALESCE(cir.actual_checkout_at::date - cir.check_in_at::date,
                            r.check_out_date - r.check_in_date)) AS nights,
               SUM(r.check_out_date - r.check_in_date)           AS planned_nights,
               SUM(r.total_amount)                                AS amount
        FROM reservation r
        JOIN room rm      ON rm.id = r.room_id
        JOIN room_type rt ON rt.id = rm.room_type_id
        LEFT JOIN check_in_record cir ON cir.reservation_id = r.id
        WHERE r.status IN ('confirmed', 'checked_in', 'checked_out')
          AND r.check_in_date BETWEEN %(date_from)s::date AND %(date_to)s::date
        GROUP BY rt.name
        ORDER BY orders DESC, nights DESC
        LIMIT 6
    """
    rows: list[dict] = []
    with connection.cursor() as cur:
        cur.execute(sql, {"date_from": date_from, "date_to": date_to})
        for name, orders, nights, planned, amount in cur.fetchall():
            rows.append(
                {
                    "room_type": name,
                    "orders": int(orders or 0),
                    "nights": int(nights or 0),
                    "planned_nights": int(planned or 0),
                    "amount": float(amount or 0),
                }
            )
    return rows


def _top_rooms_python(date_from: date, date_to: date) -> list[dict]:
    buckets: dict[str, dict] = {}
    reservations = (
        Reservation.objects.select_related("room__room_type", "check_in")
        .filter(status__in=ACTIVE_STATUSES, check_in_date__range=(date_from, date_to))
        .all()
    )
    for reservation in reservations:
        name = reservation.room.room_type.name
        bucket = buckets.setdefault(
            name, {"orders": 0, "nights": 0, "planned_nights": 0, "amount": Decimal("0")}
        )
        planned = (reservation.check_out_date - reservation.check_in_date).days
        record = getattr(reservation, "check_in", None)
        if record is not None and record.actual_checkout_at:
            nights = (record.actual_checkout_at.date() - record.check_in_at.date()).days
        else:
            nights = planned
        bucket["orders"] += 1
        bucket["nights"] += nights
        bucket["planned_nights"] += planned
        bucket["amount"] += reservation.total_amount
    rows = [
        {
            "room_type": name,
            "orders": bucket["orders"],
            "nights": bucket["nights"],
            "planned_nights": bucket["planned_nights"],
            "amount": float(bucket["amount"]),
        }
        for name, bucket in buckets.items()
    ]
    rows.sort(key=lambda row: (-row["orders"], -row["nights"]))
    return rows[:6]


def _source_pg(date_from: date, date_to: date) -> list[dict]:
    sql = """
        SELECT r.source,
               count(*)                                        AS total,
               count(*) FILTER (WHERE r.status = 'cancelled')  AS cancelled,
               count(*) FILTER (WHERE r.status = 'no_show')    AS no_show
        FROM reservation r
        WHERE r.check_in_date BETWEEN %(date_from)s::date AND %(date_to)s::date
        GROUP BY r.source
        ORDER BY total DESC
    """
    rows: list[dict] = []
    with connection.cursor() as cur:
        cur.execute(sql, {"date_from": date_from, "date_to": date_to})
        for source, total, cancelled, no_show in cur.fetchall():
            total = int(total or 0)
            cancelled = int(cancelled or 0)
            rows.append(
                {
                    "source": source,
                    "label": SOURCE_LABELS.get(source, source),
                    "total": total,
                    "cancelled": cancelled,
                    "no_show": int(no_show or 0),
                    "cancel_rate": _round2(cancelled / total * 100) if total else 0.0,
                }
            )
    return rows


def _source_python(date_from: date, date_to: date) -> list[dict]:
    buckets: dict[str, dict] = {}
    for reservation in Reservation.objects.filter(check_in_date__range=(date_from, date_to)).only(
        "pk", "source", "status"
    ):
        bucket = buckets.setdefault(reservation.source, {"total": 0, "cancelled": 0, "no_show": 0})
        bucket["total"] += 1
        if reservation.status == "cancelled":
            bucket["cancelled"] += 1
        elif reservation.status == "no_show":
            bucket["no_show"] += 1
    rows = [
        {
            "source": source,
            "label": SOURCE_LABELS.get(source, source),
            "total": bucket["total"],
            "cancelled": bucket["cancelled"],
            "no_show": bucket["no_show"],
            "cancel_rate": _round2(bucket["cancelled"] / bucket["total"] * 100) if bucket["total"] else 0.0,
        }
        for source, bucket in buckets.items()
    ]
    rows.sort(key=lambda row: -row["total"])
    return rows


def _build_chart_data(date_from: date, date_to: date) -> dict:
    is_pg = connection.vendor == "postgresql"
    occupancy = _occupancy_pg(date_from, date_to) if is_pg else _occupancy_python(date_from, date_to)
    revenue = _revenue_pg(date_from, date_to) if is_pg else _revenue_python(date_from, date_to)
    top_rooms = _top_rooms_pg(date_from, date_to) if is_pg else _top_rooms_python(date_from, date_to)
    sources = _source_pg(date_from, date_to) if is_pg else _source_python(date_from, date_to)

    months = sorted({row["month"] for row in occupancy})
    series_by_type: dict[str, list[float]] = {}
    for month in months:
        for row in occupancy:
            if row["month"] == month:
                series_by_type.setdefault(row["room_type"], [0.0] * len(months))
    for row in occupancy:
        index = months.index(row["month"])
        series_by_type[row["room_type"]][index] = row["rate"]

    total_sold = sum(row["sold"] for row in occupancy)
    total_sellable = sum(row["sellable"] for row in occupancy)
    totals = {
        "occupancy": _round2(total_sold / total_sellable * 100) if total_sellable else 0.0,
        "sold_nights": total_sold,
        "sellable_nights": total_sellable,
        "income": _round2(sum(row["income"] for row in revenue)),
        "refund": _round2(sum(row["refund"] for row in revenue)),
        "net": _round2(sum(row["net"] for row in revenue)),
        "checked_out_records": sum(row["records"] for row in revenue),
        "top_orders": sum(row["orders"] for row in top_rooms),
        "cancel_rate": None,
    }
    total_reservations = sum(row["total"] for row in sources)
    total_cancelled = sum(row["cancelled"] for row in sources)
    totals["reservations"] = total_reservations
    totals["cancelled"] = total_cancelled
    if total_reservations:
        totals["cancel_rate"] = _round2(total_cancelled / total_reservations * 100)

    return {
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "occupancy": {"months": months, "series": series_by_type, "rows": occupancy},
        "revenue": {"rows": revenue},
        "top_rooms": top_rooms,
        "sources": sources,
        "totals": totals,
        "vendor": connection.vendor,
    }


# --------------------------------------------------------------------------- #
# P11 经营统计报表
# --------------------------------------------------------------------------- #
@role_required("admin")
def reports(request):
    today = date.today()
    raw_from = request.GET.get("date_from")
    raw_to = request.GET.get("date_to")
    date_from = _try_date(raw_from) or (today - timedelta(days=30))
    date_to = _try_date(raw_to) or today
    errors: list[str] = []
    if date_from > date_to:
        errors.append("入住日期区间无效：起始日期不能晚于结束日期，已按默认区间显示。")
        date_from, date_to = today - timedelta(days=30), today
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        errors.append(f"区间最多 {MAX_RANGE_DAYS} 天，已截断。")
        date_from = date_to - timedelta(days=MAX_RANGE_DAYS)

    room_type_id = (request.GET.get("room_type_id") or "").strip()
    selected_room_type = None
    if room_type_id:
        selected_room_type = RoomType.objects.filter(pk=room_type_id).first()
        if selected_room_type is None:
            errors.append("所选房型不存在，已按全部房型显示。")

    data = _build_chart_data(date_from, date_to)
    if selected_room_type is not None:
        # 图表 1/4 仍展示全部房型（对比才有意义），房型筛选只作用于明细表与“排行”卡
        data["top_rooms"] = [row for row in data["top_rooms"] if row["room_type"] == selected_room_type.name]

    quick_ranges = [
        {"label": "近 30 天", "from": (today - timedelta(days=30)).isoformat(), "to": today.isoformat()},
        {"label": "近 90 天", "from": (today - timedelta(days=90)).isoformat(), "to": today.isoformat()},
        {"label": "演示数据全区间", "from": "2026-09-01", "to": "2027-01-31"},
    ]

    context = {
        "date_from": date_from,
        "date_to": date_to,
        "raw_from": raw_from or "",
        "raw_to": raw_to or "",
        "room_types": RoomType.objects.filter(is_active=True).order_by("id"),
        "selected_room_type": selected_room_type,
        "chart_data": data,
        "errors": errors,
        "quick_ranges": quick_ranges,
        "today": today,
    }
    return render(request, "manage/reports.html", context)


# --------------------------------------------------------------------------- #
# P12 预订总览（只读 + CSV 导出）
# --------------------------------------------------------------------------- #
def _filtered_reservations(request):
    queryset = (
        Reservation.objects.select_related("customer", "room", "room__room_type")
        .order_by("-check_in_date", "-pk")
    )
    status = (request.GET.get("status") or "").strip()
    keyword = (request.GET.get("keyword") or "").strip()
    raw_from = request.GET.get("date_from")
    raw_to = request.GET.get("date_to")
    date_from = _try_date(raw_from)
    date_to = _try_date(raw_to)
    errors: list[str] = []
    if status:
        if status in STATUS_LABELS:
            queryset = queryset.filter(status=status)
        else:
            errors.append("状态筛选值无效，已忽略。")
    if keyword:
        queryset = queryset.filter(
            Q(reservation_no__icontains=keyword)
            | Q(customer__name__icontains=keyword)
            | Q(customer__phone__icontains=keyword)
            | Q(room__room_no__icontains=keyword)
        )
    if date_from and date_to and date_from > date_to:
        errors.append("起始日期不能晚于结束日期，已忽略日期筛选。")
        date_from = date_to = None
    if date_from:
        queryset = queryset.filter(check_in_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(check_in_date__lte=date_to)
    return queryset, {
        "status": status,
        "keyword": keyword,
        "date_from": raw_from or "",
        "date_to": raw_to or "",
        "parsed_from": date_from,
        "parsed_to": date_to,
        "errors": errors,
    }


@role_required("admin")
def reservation_list(request):
    queryset, filters = _filtered_reservations(request)
    paginator = Paginator(queryset, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    counts = {
        row["status"]: row["total"]
        for row in Reservation.objects.values("status").annotate(total=Count("pk"))
    }
    status_rows = [
        {"value": value, "label": label, "count": counts.get(value, 0)}
        for value, label in RESERVATION_STATUS_CHOICES
    ]
    querystring = request.GET.copy()
    querystring.pop("page", None)
    context = {
        "page": page,
        "paginator": paginator,
        "reservations": page.object_list,
        "filters": filters,
        "status_labels": STATUS_LABELS,
        "source_labels": SOURCE_LABELS,
        "statuses": RESERVATION_STATUS_CHOICES,
        "status_rows": status_rows,
        "counts": counts,
        "total_count": sum(counts.values()),
        "querystring": querystring.urlencode(),
    }
    return render(request, "manage/reservation_list.html", context)


@role_required("admin")
def reservation_export(request):
    queryset, _filters = _filtered_reservations(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"预订总览_{date.today():%Y%m%d}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")  # Excel 打开 UTF-8 CSV 需要 BOM
    writer = csv.writer(response)
    writer.writerow(
        ["预订号", "客户", "手机", "房号", "房型", "入住日期", "离店日期", "晚数", "人数",
         "金额", "状态", "来源", "创建时间"]
    )
    for reservation in queryset[:EXPORT_LIMIT]:
        writer.writerow(
            [
                reservation.reservation_no,
                reservation.customer.name,
                reservation.customer.phone,
                reservation.room.room_no,
                reservation.room.room_type.name,
                reservation.check_in_date.isoformat(),
                reservation.check_out_date.isoformat(),
                reservation.nights,
                reservation.guest_count,
                f"{reservation.total_amount:.2f}",
                STATUS_LABELS.get(reservation.status, reservation.status),
                SOURCE_LABELS.get(reservation.source, reservation.source),
                reservation.created_at.strftime("%Y-%m-%d %H:%M") if reservation.created_at else "",
            ]
        )
    return response
