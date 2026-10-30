"""可用房查询（F03 / P02，`/rooms/available/`）。

契约见 `docs/页面约定.md` §3 F03：
- GET 参数：`check_in_date`、`check_out_date`、`room_type_id`（可空＝全部房型）、`capacity`（可空＝不限）
- 查询走数据库函数 `fn_available_rooms(check_in, check_out, room_type_id)`：函数内部用
  `NOT EXISTS(r.during && daterange(...))` 判占用、`NOT EXISTS(room_block.during && ...)` 判维修停用，
  并按 `rate_plan` 逐日取价（无专项价用标准价），返回标准价 / 每晚均价 / 区间合计。
- 应用层只做参数校验与中文提示；真正的“同一房间重叠日期不得两条有效预订”由数据库排他约束兜底。
"""
from __future__ import annotations

from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import render
from django.utils import timezone

from ..models import Reservation, Room, RoomBlock, RoomType

# 有效占用状态（与 reservation 排他约束的 WHERE 子句一致；docs/02 §3）
OCCUPYING_STATUSES = ("pending", "confirmed", "checked_in")
# 房态里“物理不可售”的两态（函数同样排除；docs/02 §3.4）
UNSELLABLE_STATUSES = ("maintenance", "disabled")


def _parse_iso(value: str) -> date:
    """把 `YYYY-MM-DD` 解析成 date，失败抛 ValueError（由调用方翻译成中文提示）。"""
    return date.fromisoformat(value.strip())


@login_required
def available_rooms(request):
    """P02 可用房查询：GET 表单 → 调用数据库函数 → 按房型汇总 + 房间明细。"""
    today = timezone.localdate()
    params = {
        "check_in_date": (request.GET.get("check_in_date") or (today + timedelta(days=1)).isoformat()),
        "check_out_date": (request.GET.get("check_out_date") or (today + timedelta(days=3)).isoformat()),
        "room_type_id": (request.GET.get("room_type_id") or "").strip(),
        "capacity": (request.GET.get("capacity") or "").strip(),
    }
    room_types = RoomType.objects.filter(is_active=True).order_by("base_price", "id")
    context = {
        "params": params,
        "submitted": bool(request.GET),
        "room_types": room_types,
        "today": today,
        "errors": [],
        "rows": [],
        "summary": [],
        "nights": 0,
        "room_type_name": "",
        "capacity_limit": None,
    }

    if not request.GET:
        # 首次进入：只渲染表单与默认日期，不查库
        return render(request, "customer/available_rooms.html", context)

    errors: list[str] = []
    check_in = check_out = None
    try:
        check_in = _parse_iso(params["check_in_date"])
    except ValueError:
        errors.append("入住日期格式不正确，请用 2026-12-20 这样的写法。")
    try:
        check_out = _parse_iso(params["check_out_date"])
    except ValueError:
        errors.append("离店日期格式不正确，请用 2026-12-22 这样的写法。")
    if check_in and check_out and check_out <= check_in:
        errors.append("离店日期必须晚于入住日期（日期区间按“入住当天计、离店当天不计”计算，同一晚不能被两天重复占用）。")
    if check_in and check_in < today:
        errors.append(f"入住日期不能早于今天（{today.isoformat()}）。")

    room_type_id = None
    if params["room_type_id"]:
        try:
            room_type_id = int(params["room_type_id"])
        except ValueError:
            errors.append("房型筛选值不正确，请从下拉列表重新选择。")

    capacity_limit = None
    if params["capacity"]:
        try:
            capacity_limit = int(params["capacity"])
            if capacity_limit < 1:
                errors.append("入住人数至少为 1。")
                capacity_limit = None
        except ValueError:
            errors.append("入住人数必须是整数。")

    if errors:
        context["errors"] = errors
        return render(request, "customer/available_rooms.html", context)

    assert check_in is not None and check_out is not None  # 供类型检查器
    nights = (check_out - check_in).days
    try:
        rows = _query_available(check_in, check_out, room_type_id, capacity_limit)
    except Exception as exc:  # noqa: BLE001 — 数据库异常统一翻译成中文提示
        messages.error(request, _translate_db_error(exc))
        rows = []

    context.update(
        {
            "rows": rows,
            "nights": nights,
            "check_in": check_in,
            "check_out": check_out,
            "capacity_limit": capacity_limit,
            "room_type_name": _room_type_name(room_types, room_type_id),
            "summary": _summarize(rows),
        }
    )
    return render(request, "customer/available_rooms.html", context)


def _query_available(check_in: date, check_out: date, room_type_id: int | None, capacity_limit: int | None):
    """调用 `fn_available_rooms`（PostgreSQL）；sqlite 离线冒烟走等价的 Python 实现。"""
    if connection.vendor == "postgresql":
        rows = _query_available_postgres(check_in, check_out, room_type_id)
    else:
        rows = _query_available_python(check_in, check_out, room_type_id)

    if capacity_limit:
        rows = [r for r in rows if r["capacity"] >= capacity_limit]
    rows.sort(key=lambda r: (r["room_type_name"], r["floor"] or 0, r["room_no"]))
    return rows


def _query_available_postgres(check_in: date, check_out: date, room_type_id: int | None):
    """数据库侧计算：占用区间与封禁区间都在 SQL 里判，应用层只做展示。"""
    sql = """
        SELECT room_id,
               room_no,
               room_type_id,
               room_type_name,
               capacity,
               floor,
               base_price,
               avg_price,
               total_price
          FROM fn_available_rooms(%s, %s, %s)
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [check_in, check_out, room_type_id])
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _query_available_python(check_in: date, check_out: date, room_type_id: int | None):
    """离线冒烟用的等价实现（只在非 PostgreSQL 后端生效，生产路径永远是上面的 SQL）。

    与函数保持同样的判定口径：房态不在 maintenance/disabled、无重叠有效预订、无重叠封禁区间。
    """
    rooms = (
        Room.objects.select_related("room_type")
        .filter(room_type__is_active=True)
        .exclude(status__in=UNSELLABLE_STATUSES)
        .order_by("room_type__name", "floor", "room_no")
    )
    if room_type_id:
        rooms = rooms.filter(room_type_id=room_type_id)

    busy_room_ids = set(
        Reservation.objects.filter(
            status__in=OCCUPYING_STATUSES,
            check_in_date__lt=check_out,
            check_out_date__gt=check_in,
        ).values_list("room_id", flat=True)
    )
    blocked_room_ids = set(
        RoomBlock.objects.filter(start_date__lt=check_out, end_date__gt=check_in).values_list(
            "room_id", flat=True
        )
    )

    rows = []
    nights = (check_out - check_in).days
    for room in rooms:
        if room.pk in busy_room_ids or room.pk in blocked_room_ids:
            continue
        base_price = float(room.room_type.base_price)
        total_price = round(base_price * nights, 2)
        rows.append(
            {
                "room_id": room.pk,
                "room_no": room.room_no,
                "room_type_id": room.room_type_id,
                "room_type_name": room.room_type.name,
                "capacity": room.room_type.capacity,
                "floor": room.floor,
                "base_price": base_price,
                "avg_price": base_price,
                "total_price": total_price,
            }
        )
    return rows


def _summarize(rows):
    """按房型汇总余量与区间报价（F03：按房型汇总余量与区间报价）。"""
    buckets: dict[str, dict] = {}
    for row in rows:
        bucket = buckets.setdefault(
            row["room_type_name"],
            {
                "room_type_name": row["room_type_name"],
                "room_type_id": row["room_type_id"],
                "capacity": row["capacity"],
                "count": 0,
                "base_price": float(row["base_price"]),
                "min_total_price": float(row["total_price"]),
                "avg_price": float(row["avg_price"]),
            },
        )
        bucket["count"] += 1
        bucket["min_total_price"] = min(bucket["min_total_price"], float(row["total_price"]))
    return sorted(buckets.values(), key=lambda item: (-item["count"], item["base_price"]))


def _room_type_name(room_types, room_type_id):
    if not room_type_id:
        return ""
    for room_type in room_types:
        if room_type.pk == room_type_id:
            return room_type.name
    return ""


def _translate_db_error(exc: Exception) -> str:
    """把数据库异常翻译成中文提示（E02/E04 依赖这一层，本页主要处理日期参数异常 22023）。"""
    message = str(exc)
    if "22023" in message or "离店日期" in message or "入住日期" in message:
        return "查询参数不合法：离店日期必须晚于入住日期。"
    return f"可用房查询失败：{message}"
