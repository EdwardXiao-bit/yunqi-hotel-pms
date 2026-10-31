"""P09 房态看板（F08 房态看板 + F02 房态维护）。

页面契约见 `docs/页面约定.md`（P09 `/reception/board/`）：
- 按楼层（或房型）展示房间当前 4 态，颜色分组；
- 同日显示「今日到店」「在住」信息（来自 `reservation` / `check_in_record`，不写进房态）；
- 支持清洁完成恢复正常、登记维修/停用区间、结束维修/停用、置为清洁中。

房态口径（`AGENTS.md` §4.1）：`room.status` 只表达当下物理可用性
`available / cleaning / maintenance / disabled`；“已预订”“入住中”由订单与入住记录推导。
维修/停用必须落在 `room_block` 的日期区间上（可售房夜按它扣减），
登记时会先查已有有效订单，冲突则由 `fn_check_room_block_order()` 抛 23514。
"""
from __future__ import annotations

from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from core.decorators import role_required
from core.models import (
    ROOM_STATUS_CHOICES,
    CheckInRecord,
    Reservation,
    Room,
    RoomBlock,
    RoomType,
)

ROOM_STATUS_LABELS = dict(ROOM_STATUS_CHOICES)
# 看板配色：正常=绿、清洁中=蓝、维修中=黄、停用=灰
STATUS_COLORS = {
    "available": "success",
    "cleaning": "info",
    "maintenance": "warning",
    "disabled": "secondary",
}
# 与 EXCLUDE 约束的 WHERE 子句保持一致：这三态才占用房间日期
ACTIVE_RESERVATION_STATUSES = ("pending", "confirmed", "checked_in")

ACTION_LABELS = {
    "clean": "清洁完成",
    "block": "登记维修/停用",
    "unblock": "结束维修/停用",
    "cleaning": "置为清洁中",
}


def _try_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _active_block(room_block_map: dict[int, RoomBlock], room_id: int) -> RoomBlock | None:
    return room_block_map.get(room_id)


def _set_operator(user) -> None:
    """把当前操作人写进事务级会话变量，供 `fn_log_room_status()` 记录 changed_by。

    触发器读的是 `current_setting('app.current_user_id', true)`；离线 sqlite 没有这个
    触发器与函数，直接跳过（冒烟模式）。
    """
    if connection.vendor != "postgresql":
        return
    if user is None or not getattr(user, "is_authenticated", False):
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(user.pk)])


def _block_map(today: date) -> dict[int, RoomBlock]:
    """当前正在生效（覆盖今天）的维修/停用区间：每间房取最近一条。"""
    blocks: dict[int, RoomBlock] = {}
    for block in RoomBlock.objects.filter(start_date__lte=today, end_date__gt=today).order_by("start_date"):
        blocks.setdefault(block.room_id, block)
    return blocks


def _reservation_maps(today: date) -> tuple[dict[int, Reservation], dict[int, CheckInRecord], dict[int, Reservation]]:
    """返回 (今日到店, 在住, 今日退房) 三张按房间索引的表。"""
    arrivals: dict[int, Reservation] = {}
    for reservation in (
        Reservation.objects.filter(status="confirmed", check_in_date=today)
        .select_related("customer")
        .order_by("id")
    ):
        arrivals.setdefault(reservation.room_id, reservation)

    in_house: dict[int, CheckInRecord] = {}
    departures: dict[int, Reservation] = {}
    for record in (
        CheckInRecord.objects.filter(actual_checkout_at__isnull=True)
        .select_related("reservation", "reservation__customer")
        .order_by("check_in_at")
    ):
        reservation = record.reservation
        in_house.setdefault(reservation.room_id, record)
        if reservation.check_out_date <= today:
            departures.setdefault(reservation.room_id, reservation)
    return arrivals, in_house, departures


def _room_cards(today: date, floor: int | None, room_type_id: int | None) -> list[dict]:
    rooms = Room.objects.select_related("room_type").order_by("floor", "room_no")
    if floor is not None:
        rooms = rooms.filter(floor=floor)
    if room_type_id is not None:
        rooms = rooms.filter(room_type_id=room_type_id)

    block_map = _block_map(today)
    arrivals, in_house, departures = _reservation_maps(today)

    cards: list[dict] = []
    for room in rooms:
        block = _active_block(block_map, room.id)
        arrival = arrivals.get(room.id)
        stay = in_house.get(room.id)
        departure = departures.get(room.id)
        cards.append(
            {
                "room": room,
                "status_label": ROOM_STATUS_LABELS.get(room.status, room.status),
                "status_color": STATUS_COLORS.get(room.status, "secondary"),
                "block": block,
                "arrival": arrival,
                "guest": stay.reservation.customer if stay else None,
                "stay": stay,
                "departure": departure,
                "can_clean": room.status == "cleaning",
                "can_mark_cleaning": room.status == "available" and block is None,
                "can_unblock": block is not None,
            }
        )
    return cards


def _group_by_floor(cards: list[dict]) -> list[dict]:
    groups: list[dict] = []
    current: dict | None = None
    for card in cards:
        floor = card["room"].floor
        if current is None or current["floor"] != floor:
            current = {"floor": floor, "cards": []}
            groups.append(current)
        current["cards"].append(card)
    return groups


def _status_summary(cards: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for card in cards:
        counts[card["room"].status] = counts.get(card["room"].status, 0) + 1
    return [
        {
            "value": status,
            "label": label,
            "count": counts.get(status, 0),
            "color": STATUS_COLORS.get(status, "secondary"),
        }
        for status, label in ROOM_STATUS_LABELS.items()
    ]


def _back_to_board(request) -> str:
    params = []
    for key in ("floor", "room_type_id"):
        value = (request.POST.get(key) or request.GET.get(key) or "").strip()
        if value:
            params.append(f"{key}={value}")
    return "/reception/board/" + (f"?{'&'.join(params)}" if params else "")


@role_required("receptionist", "admin")
def room_board(request):
    """P09 房态看板：GET 展示，POST 执行房态动作。"""
    today = timezone.localdate()
    if request.method == "POST":
        return _handle_action(request, today)

    floor = None
    raw_floor = (request.GET.get("floor") or "").strip()
    if raw_floor:
        try:
            floor = int(raw_floor)
        except ValueError:
            messages.error(request, "楼层筛选需要填写整数。")
    room_type_id = None
    raw_type = (request.GET.get("room_type_id") or "").strip()
    if raw_type:
        try:
            room_type_id = int(raw_type)
        except ValueError:
            messages.error(request, "房型筛选参数不正确。")

    cards = _room_cards(today, floor, room_type_id)
    all_cards = _room_cards(today, None, None)
    return render(
        request,
        "reception/room_board.html",
        {
            "today": today,
            "groups": _group_by_floor(cards),
            "cards_total": len(all_cards),
            "summary": _status_summary(all_cards),
            "room_types": list(RoomType.objects.order_by("id")),
            "floors": sorted({room.floor for room in Room.objects.all()}),
            "selected_floor": floor,
            "selected_room_type": room_type_id,
            "default_block_start": today.isoformat(),
            "default_block_end": (today + timedelta(days=7)).isoformat(),
            "status_labels": ROOM_STATUS_LABELS,
        },
    )


def _handle_action(request, today: date):
    action = (request.POST.get("action") or "").strip()
    back = _back_to_board(request)
    room_id = request.POST.get("room_id") or ""
    try:
        room = Room.objects.select_related("room_type").get(pk=int(room_id))
    except (TypeError, ValueError):
        messages.error(request, "房间参数不正确，请刷新页面后重试。")
        return redirect(back)
    except Room.DoesNotExist:
        messages.error(request, "房间不存在，可能已被删除。")
        return redirect(back)

    if action == "clean":
        return _mark_clean(request, room, back)
    if action == "cleaning":
        return _mark_cleaning(request, room, back)
    if action == "block":
        return _register_block(request, room, today, back)
    if action == "unblock":
        return _finish_block(request, room, today, back)

    messages.error(request, "未识别的房态操作。")
    return redirect(back)


def _active_block_of(room: Room, today: date) -> RoomBlock | None:
    return (
        RoomBlock.objects.filter(room=room, start_date__lte=today, end_date__gt=today)
        .order_by("start_date")
        .first()
    )


def _mark_clean(request, room: Room, back: str):
    if room.status != "cleaning":
        messages.error(request, f"房间 {room.room_no} 当前不是「清洁中」，无需恢复。")
        return redirect(back)
    block = _active_block_of(room, timezone.localdate())
    if block is not None:
        messages.error(
            request,
            f"房间 {room.room_no} 处于「{block.get_block_type_display()}」区间"
            f"（{block.start_date} 至 {block.end_date}），请先结束后再恢复正常。",
        )
        return redirect(back)
    with transaction.atomic():
        _set_operator(request.user)
        room.status = "available"
        room.save(update_fields=["status", "updated_at"])
    messages.success(request, f"房间 {room.room_no} 已清洁完成，恢复为「正常」。")
    return redirect(back)


def _mark_cleaning(request, room: Room, back: str):
    if room.status != "available":
        messages.error(request, f"只有「正常」状态的房间可以置为清洁中，房间 {room.room_no} 当前是「{room.get_status_display()}」。")
        return redirect(back)
    if _active_block_of(room, timezone.localdate()) is not None:
        messages.error(request, f"房间 {room.room_no} 处于维修/停用区间，不能置为清洁中。")
        return redirect(back)
    with transaction.atomic():
        _set_operator(request.user)
        room.status = "cleaning"
        room.save(update_fields=["status", "updated_at"])
    messages.success(request, f"房间 {room.room_no} 已置为「清洁中」。")
    return redirect(back)


def _overlapping_reservations(room: Room, start: date, end: date):
    """与 [start, end) 区间重叠的有效订单（口径与 EXCLUDE 约束一致）。"""
    return (
        Reservation.objects.filter(
            room=room,
            status__in=ACTIVE_RESERVATION_STATUSES,
            check_in_date__lt=end,
            check_out_date__gt=start,
        )
        .select_related("customer")
        .order_by("check_in_date")
    )


def _register_block(request, room: Room, today: date, back: str):
    block_type = (request.POST.get("block_type") or "").strip()
    start = _try_date(request.POST.get("start_date"))
    end = _try_date(request.POST.get("end_date"))
    reason = (request.POST.get("reason") or "").strip()

    if block_type not in ("maintenance", "disabled"):
        messages.error(request, "维修/停用类型不正确。")
        return redirect(back)
    if start is None or end is None:
        messages.error(request, "请填写维修/停用的开始与结束日期（格式 YYYY-MM-DD）。")
        return redirect(back)
    if end <= start:
        messages.error(request, "结束日期必须晚于开始日期（区间按“开始当天计、结束当天不计”处理）。")
        return redirect(back)
    if start < today:
        messages.error(request, "开始日期不能早于今天；如需补录历史区间，请直接改数据库脚本。")
        return redirect(back)
    if len(reason) > 200:
        messages.error(request, "原因说明最多 200 字。")
        return redirect(back)

    conflicts = _overlapping_reservations(room, start, end)
    if conflicts.exists():
        first = conflicts.first()
        messages.error(
            request,
            f"房间 {room.room_no} 在该区间已有 {conflicts.count()} 条有效订单"
            f"（如 {first.reservation_no}：{first.check_in_date} 至 {first.check_out_date}），"
            "请先处理订单（改期或换房）再登记维修/停用。",
        )
        return redirect(back)

    existing = (
        RoomBlock.objects.filter(room=room, start_date__lt=end, end_date__gt=start)
        .order_by("start_date")
        .first()
    )
    if existing is not None:
        messages.error(
            request,
            f"房间 {room.room_no} 在该区间已有维修/停用登记"
            f"（{existing.start_date} 至 {existing.end_date}，{existing.get_block_type_display()}），请勿重复登记。",
        )
        return redirect(back)

    try:
        with transaction.atomic():
            _set_operator(request.user)
            block = RoomBlock.objects.create(
                room=room,
                start_date=start,
                end_date=end,
                block_type=block_type,
                reason=reason,
                created_by=request.user if request.user.is_authenticated else None,
            )
            if start <= today < end and room.status in ("available", "cleaning"):
                room.status = block_type
                room.save(update_fields=["status", "updated_at"])
    except IntegrityError as exc:
        if "ex_room_block_overlap" in str(exc) or getattr(getattr(exc, "__cause__", None), "pgcode", "") == "23P01":
            messages.error(request, f"房间 {room.room_no} 在该区间已有维修/停用登记，请勿重复登记。")
        elif "check_violation" in str(exc) or getattr(getattr(exc, "__cause__", None), "pgcode", "") == "23514":
            messages.error(request, f"房间 {room.room_no} 在该区间与已有订单冲突，登记被数据库拒绝。")
        else:
            messages.error(request, "登记维修/停用失败，请稍后重试。")
        return redirect(back)

    label = block.get_block_type_display()
    messages.success(request, f"房间 {room.room_no} 已登记「{label}」：{start} 至 {end}（{reason or '未填写原因'}）。")
    return redirect(back)


def _finish_block(request, room: Room, today: date, back: str):
    block = _active_block_of(room, today)
    if block is None:
        messages.error(request, f"房间 {room.room_no} 当前没有正在生效的维修/停用区间。")
        return redirect(back)
    label = block.get_block_type_display()
    try:
        with transaction.atomic():
            _set_operator(request.user)
            if block.start_date >= today:
                block.delete()
            else:
                block.end_date = today
                block.save(update_fields=["end_date"])
            if room.status in ("maintenance", "disabled"):
                room.status = "available"
                room.save(update_fields=["status", "updated_at"])
    except IntegrityError:
        messages.error(request, "结束维修/停用失败：区间调整与其它登记冲突，请联系管理员。")
        return redirect(back)
    messages.success(request, f"房间 {room.room_no} 已结束「{label}」，房态恢复为「正常」。")
    return redirect(back)
