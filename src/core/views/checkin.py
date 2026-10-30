"""F06 入住与续住办理（P07，`/reception/checkin/new/`）。

三条路径：
1. 按预订办理入住：检索预订号 / 手机号 / 姓名 / 房号 → 填入住人信息与押金 → 写 `check_in_record`
   并把 `reservation.status` 置为 `checked_in`（同一事务）。
2. 散客入住：没有预订的客人先在库里建客户档案（`customer.user_id IS NULL`）与一条
   `source='walk_in'` 的预订，再写入住记录。
3. 续住：在住订单延长离店日期，先查区间冲突（其他有效预订 / 维修停用区间），再更新
   `check_out_date` 让触发器重算逐日价格（离线 sqlite 由本模块补等价明细）。

房态约定：`room.status` 只表达物理可用性（4 态），**入住不会把房间写成「入住中」**；占用由订单推导。
入住前若房间处于 `cleaning`，按契约要求先在看板标记清洁完成，本页只给提示不代改。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from ..decorators import role_required
from ..models import (
    CheckInRecord,
    Customer,
    Reservation,
    ReservationPrice,
    Room,
    RoomBlock,
    RoomType,
)
from ..roles import ROLE_RECEPTIONIST
from .reservations import (
    PHONE_RE,
    _as_int,
    _is_duplicate_reservation_no,
    _night_prices,
    _translate_booking_error,
    _try_date,
)
from .rooms import _query_available

DEFAULT_DEPOSIT = Decimal("200.00")
ID_CARD_RE = re.compile(r"^(?:\d{15}|\d{17}[\dXx])$")
SEARCH_STATUSES = ("pending", "confirmed", "checked_in")
IN_HOUSE_LIMIT = 12


# ------------------------------------------------------------------ P07 主页面


@role_required(ROLE_RECEPTIONIST, "admin")
def checkin_new(request):
    """P07：检索预订、办理入住、查看在住客人（含续住入口）。"""
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "extend":
            return _extend_stay(request)
        return _submit_checkin(request)

    keyword = (request.GET.get("q") or "").strip()
    reservation_id = _as_int(request.GET.get("reservation_id"))
    selected = None
    if reservation_id:
        selected = (
            Reservation.objects.select_related("customer", "room__room_type", "check_in")
            .filter(pk=reservation_id)
            .first()
        )
        if selected is None:
            messages.error(request, "没有找到该预订单，请重新检索。")

    context = {
        "keyword": keyword,
        "results": _search_reservations(keyword) if keyword else [],
        "selected": selected,
        "block_reason": _checkin_block_reason(selected) if selected else None,
        "in_house": _in_house_reservations(),
        "default_deposit": DEFAULT_DEPOSIT,
        "today": timezone.localdate(),
    }
    return render(request, "reception/checkin_new.html", context)


def _search_reservations(keyword: str) -> list[Reservation]:
    """按预订号 / 手机号 / 姓名 / 房号检索，只返回还能办理或正在住的订单。"""
    qs = (
        Reservation.objects.select_related("customer", "room__room_type", "check_in")
        .filter(status__in=SEARCH_STATUSES)
        .filter(
            Q(reservation_no__icontains=keyword)
            | Q(customer__phone__icontains=keyword)
            | Q(customer__name__icontains=keyword)
            | Q(room__room_no__icontains=keyword)
        )
        .order_by("check_in_date", "id")
    )
    return list(qs[:20])


def _in_house_reservations() -> list[Reservation]:
    """当前在住（已入住且未退房）的订单，按离店日期排序。"""
    return list(
        Reservation.objects.select_related("customer", "room__room_type", "check_in")
        .filter(status="checked_in", check_in__actual_checkout_at__isnull=True)
        .order_by("check_out_date", "id")[:IN_HOUSE_LIMIT]
    )


def _checkin_block_reason(reservation: Reservation) -> str | None:
    """办理入住前的前置检查（不满足时页面直接给一条中文原因）。"""
    today = timezone.localdate()
    if reservation.status == "pending":
        return "该预订尚未确认，请先在「预订管理」里确认后再办理入住。"
    if reservation.status == "checked_in":
        return "该预订已经办理过入住。"
    if reservation.status not in ("confirmed",):
        return f"当前状态为「{reservation.get_status_display()}」，不能办理入住。"
    if reservation.check_in_date > today:
        return (
            f"入住日期还没到（{reservation.check_in_date.isoformat()}），"
            "如需提前入住请先在「预订管理」里改期。"
        )
    room = reservation.room
    if room.status in ("maintenance", "disabled"):
        return f"房间 {room.room_no} 当前是「{room.get_status_display()}」，不能入住，请先处理房态。"
    if room.status == "cleaning":
        return f"房间 {room.room_no} 仍在清洁中，请先在看板里标记清洁完成，再办理入住。"
    return None


# ------------------------------------------------------------ 按预订办理入住


def _submit_checkin(request):
    reservation = (
        Reservation.objects.select_related("customer", "room__room_type", "check_in")
        .filter(pk=_as_int(request.POST.get("reservation_id")) or 0)
        .first()
    )
    if reservation is None:
        messages.error(request, "没有找到该预订单，请重新检索。")
        return redirect("core:checkin_new")

    block_reason = _checkin_block_reason(reservation)
    if block_reason:
        messages.error(request, block_reason)
        return redirect(_back_to(reservation))

    data = {
        "guest_name": (request.POST.get("guest_name") or "").strip(),
        "guest_phone": (request.POST.get("guest_phone") or "").strip(),
        "guest_id_card": (request.POST.get("guest_id_card") or "").strip().upper(),
        "deposit_amount": (request.POST.get("deposit_amount") or "").strip(),
        "remark": (request.POST.get("remark") or "").strip(),
    }
    errors = _validate_guest(data)
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect(_back_to(reservation))

    deposit = _parse_money(data["deposit_amount"])
    if deposit is None:
        messages.error(request, "押金请填写不小于 0 的金额（例如 200.00）。")
        return redirect(_back_to(reservation))

    try:
        with transaction.atomic():
            CheckInRecord.objects.create(
                reservation=reservation,
                guest_name=data["guest_name"],
                guest_phone=data["guest_phone"],
                guest_id_card=data["guest_id_card"] or None,
                check_in_at=timezone.now(),
                deposit_amount=deposit,
                room_charge=reservation.total_amount,
                service_charge=Decimal("0.00"),
                total_charge=reservation.total_amount,
                remark=data["remark"] or None,
            )
            reservation.status = "checked_in"
            reservation.save(update_fields=["status", "updated_at"])
    except IntegrityError as exc:
        messages.error(request, _translate_checkin_error(exc))
        return redirect(_back_to(reservation))

    messages.success(
        request,
        f"入住办理完成：{reservation.reservation_no}，房间 {reservation.room.room_no}，"
        f"入住人 {data['guest_name']}，押金 {deposit:.2f} 元。",
    )
    return redirect("core:checkin_new")


def _validate_guest(data: dict) -> list[str]:
    errors: list[str] = []
    if not data["guest_name"]:
        errors.append("请填写入住人姓名。")
    elif len(data["guest_name"]) > 50:
        errors.append("入住人姓名不能超过 50 个字。")
    if not data["guest_phone"]:
        errors.append("请填写入住人手机号。")
    elif not PHONE_RE.match(data["guest_phone"]):
        errors.append("入住人手机号请填写 11 位手机号（例如 13800001101）。")
    if data["guest_id_card"] and not ID_CARD_RE.match(data["guest_id_card"]):
        errors.append("证件号请填写 15 位或 18 位身份证号（末位可为 X）。")
    if len(data["remark"]) > 200:
        errors.append("备注不能超过 200 个字。")
    return errors


def _translate_checkin_error(exc: IntegrityError) -> str:
    text = f"{exc} {exc.__cause__ or ''}"
    if "uq_check_in_record_reservation" in text or "check_in_record_reservation" in text:
        return "该预订已经有一条入住记录，不能重复办理入住。"
    if "23514" in text or "fn_check" in text:
        return "所选区间与该房间的维修/停用区间冲突，无法办理入住。"
    return f"入住办理失败：{exc.__cause__ or exc}"


def _back_to(reservation: Reservation) -> str:
    return f"/reception/checkin/new/?reservation_id={reservation.pk}"


# ------------------------------------------------------------------ 散客入住


@role_required(ROLE_RECEPTIONIST, "admin")
def walkin_checkin(request):
    """没有预订的客人：选房 + 建客户档案 + 建 walk_in 预订 + 入住，一步完成。"""
    today = timezone.localdate()
    if request.method == "POST":
        return _submit_walkin(request)

    check_in = _try_date(request.GET.get("check_in_date")) or today
    check_out = _try_date(request.GET.get("check_out_date")) or (check_in + timedelta(days=1))
    if check_out <= check_in:
        check_out = check_in + timedelta(days=1)
    room_type_id = _as_int(request.GET.get("room_type_id")) or None
    available = _query_available(check_in, check_out, room_type_id, None)
    if check_in <= today:
        # 当天入住要求房间“当场可交付”：清洁中的房间先不出现在散客列表里
        available = [row for row in available if not _is_cleaning(row["room_id"])]
    context = {
        "check_in": check_in,
        "check_out": check_out,
        "room_type_id": room_type_id,
        "room_types": list(RoomType.objects.filter(is_active=True).order_by("base_price")),
        "available": available,
        "default_deposit": DEFAULT_DEPOSIT,
        "today": today,
    }
    return render(request, "reception/checkin_walkin.html", context)


def _submit_walkin(request):
    today = timezone.localdate()
    check_in = _try_date(request.POST.get("check_in_date")) or today
    check_out = _try_date(request.POST.get("check_out_date"))
    room_id = _as_int(request.POST.get("room_id"))
    data = {
        "guest_name": (request.POST.get("guest_name") or "").strip(),
        "guest_phone": (request.POST.get("guest_phone") or "").strip(),
        "guest_id_card": (request.POST.get("guest_id_card") or "").strip().upper(),
        "deposit_amount": (request.POST.get("deposit_amount") or "").strip(),
        "remark": (request.POST.get("remark") or "").strip(),
        "guest_count": (request.POST.get("guest_count") or "1").strip(),
    }

    errors = _validate_guest(data)
    if check_out is None:
        errors.append("请填写离店日期。")
    elif check_out <= check_in:
        errors.append("离店日期必须晚于入住日期（离店当天不计房晚）。")
    if check_in < today:
        errors.append(f"入住日期不能早于今天（{today.isoformat()}）。")
    if room_id is None:
        errors.append("请选择房间。")

    guest_count = _as_int(data["guest_count"]) or 0
    if guest_count < 1:
        errors.append("入住人数至少为 1。")

    room = Room.objects.select_related("room_type").filter(pk=room_id or 0).first()
    if room is not None:
        if room.status in ("maintenance", "disabled"):
            errors.append(f"房间 {room.room_no} 当前是「{room.get_status_display()}」，不能入住。")
        elif room.status == "cleaning":
            errors.append(f"房间 {room.room_no} 仍在清洁中，请先标记清洁完成。")
        elif guest_count > room.room_type.capacity:
            errors.append(f"{room.room_type.name} 最多可住 {room.room_type.capacity} 人。")

    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect(_walkin_back(check_in, check_out))

    assert room is not None and check_out is not None
    available_ids = {row["room_id"] for row in _query_available(check_in, check_out, None, None)}
    if room.pk not in available_ids:
        messages.error(request, "该房间在所选日期不可用（可能已被预订，或处于维修/停用区间）。")
        return redirect(_walkin_back(check_in, check_out))

    deposit = _parse_money(data["deposit_amount"])
    if deposit is None:
        messages.error(request, "押金请填写不小于 0 的金额（例如 200.00）。")
        return redirect(_walkin_back(check_in, check_out))

    try:
        with transaction.atomic():
            customer = _resolve_walkin_customer(data["guest_name"], data["guest_phone"], data["guest_id_card"])
            prices = _night_prices(room.room_type_id, check_in, check_out)
            total = sum(prices, Decimal("0.00"))
            nights = len(prices)
            price_per_night = (total / nights).quantize(Decimal("0.01")) if nights else Decimal("0.00")
            reservation = _insert_walkin_reservation(
                customer=customer,
                room=room,
                check_in=check_in,
                check_out=check_out,
                guest_count=guest_count,
                price_per_night=price_per_night,
                total_amount=total,
                remark=data["remark"],
            )
            CheckInRecord.objects.create(
                reservation=reservation,
                guest_name=data["guest_name"],
                guest_phone=data["guest_phone"],
                guest_id_card=data["guest_id_card"] or None,
                check_in_at=timezone.now(),
                deposit_amount=deposit,
                room_charge=total,
                service_charge=Decimal("0.00"),
                total_charge=total,
                remark="散客入住",
            )
    except IntegrityError as exc:
        messages.error(request, _translate_booking_error(exc))
        return redirect(_walkin_back(check_in, check_out))

    messages.success(
        request,
        f"散客入住完成：{reservation.reservation_no}，房间 {room.room_no}，"
        f"{check_in.isoformat()} → {check_out.isoformat()}，共 {nights} 晚，金额 {total:.2f} 元。",
    )
    return redirect("core:checkin_new")


def _resolve_walkin_customer(name: str, phone: str, id_card: str) -> Customer:
    """散客按手机号复用客户档案；没有就建一条不绑定登录账号的档案（`user_id IS NULL`）。"""
    customer = Customer.objects.filter(phone=phone).first()
    if customer is not None:
        return customer
    return Customer.objects.create(
        user=None,
        name=name,
        phone=phone,
        id_card=id_card or None,
        remark="散客入住自动建档",
    )


def _insert_walkin_reservation(
    *,
    customer: Customer,
    room: Room,
    check_in: date,
    check_out: date,
    guest_count: int,
    price_per_night: Decimal,
    total_amount: Decimal,
    remark: str,
) -> Reservation:
    """散客预订直接落成 `checked_in`；离线 sqlite 补逐日价格明细（PG 上由触发器生成）。"""
    from .reservations import _next_reservation_no

    last_error: IntegrityError | None = None
    for attempt in range(3):
        reservation_no = _next_reservation_no(check_in, attempt)
        try:
            with transaction.atomic():
                reservation = Reservation.objects.create(
                    reservation_no=reservation_no,
                    customer=customer,
                    room=room,
                    check_in_date=check_in,
                    check_out_date=check_out,
                    guest_count=guest_count,
                    price_per_night=price_per_night,
                    total_amount=total_amount,
                    status="checked_in",
                    source="walk_in",
                    remark=remark or None,
                )
                if connection.vendor != "postgresql":
                    prices = _night_prices(room.room_type_id, check_in, check_out)
                    ReservationPrice.objects.bulk_create(
                        [
                            ReservationPrice(reservation=reservation, stay_date=stay_date, price=price)
                            for stay_date, price in zip(
                                (check_in + timedelta(days=i) for i in range(len(prices))), prices
                            )
                        ]
                    )
                return reservation
        except IntegrityError as exc:  # noqa: PERF203 — 只有编号冲突才重试
            last_error = exc
            if not _is_duplicate_reservation_no(exc):
                raise
    assert last_error is not None
    raise last_error


def _is_cleaning(room_id: int) -> bool:
    """房间是否处于清洁中（当天散客入住需要先清洁完成）。"""
    status = Room.objects.filter(pk=room_id).values_list("status", flat=True).first()
    return status == "cleaning"


def _walkin_back(check_in: date, check_out: date) -> str:
    return f"/reception/checkin/walkin/?check_in_date={check_in.isoformat()}&check_out_date={check_out.isoformat()}"


# ---------------------------------------------------------------------- 续住


def _extend_stay(request):
    """续住：延长在住订单的离店日期，先查冲突再更新（PG 触发器回写逐日价与总额）。"""
    reservation = (
        Reservation.objects.select_related("customer", "room__room_type", "check_in")
        .filter(pk=_as_int(request.POST.get("reservation_id")) or 0)
        .first()
    )
    if reservation is None:
        messages.error(request, "没有找到该预订单。")
        return redirect("core:checkin_new")
    if reservation.status != "checked_in":
        messages.error(request, "只有在住订单才能续住。")
        return redirect("core:checkin_new")

    new_check_out = _try_date(request.POST.get("check_out_date"))
    if new_check_out is None:
        messages.error(request, "请填写新的离店日期。")
        return redirect("core:checkin_new")
    if new_check_out <= reservation.check_out_date:
        messages.error(
            request,
            f"新的离店日期必须晚于原离店日期（{reservation.check_out_date.isoformat()}）。",
        )
        return redirect("core:checkin_new")

    conflict = _extend_conflict(reservation, new_check_out)
    if conflict:
        messages.error(request, conflict)
        return redirect("core:checkin_new")

    try:
        with transaction.atomic():
            reservation.check_out_date = new_check_out
            reservation.save(update_fields=["check_out_date", "updated_at"])
            if connection.vendor != "postgresql":
                _refresh_prices(reservation)
            else:
                reservation.refresh_from_db()
    except IntegrityError as exc:
        messages.error(request, _translate_booking_error(exc))
        return redirect("core:checkin_new")

    messages.success(
        request,
        f"续住成功：{reservation.reservation_no} 离店日期延长至 {new_check_out.isoformat()}，"
        f"预订总额更新为 {reservation.total_amount:.2f} 元。",
    )
    return redirect("core:checkin_new")


def _extend_conflict(reservation: Reservation, new_check_out: date) -> str | None:
    """续住的新增区间是否与其它有效订单或维修/停用区间冲突。"""
    room = reservation.room
    if room.status in ("maintenance", "disabled"):
        return f"房间 {room.room_no} 当前是「{room.get_status_display()}」，不能续住。"

    others = (
        Reservation.objects.select_related("customer")
        .filter(
            room_id=room.pk,
            status__in=("pending", "confirmed", "checked_in"),
            check_in_date__lt=new_check_out,
            check_out_date__gt=reservation.check_out_date,
        )
        .exclude(pk=reservation.pk)
        .order_by("check_in_date")
    )
    other = others.first()
    if other is not None:
        return (
            f"续住失败：房间 {room.room_no} 在 {other.check_in_date.isoformat()} 起已被预订"
            f"（{other.reservation_no}），请先处理该订单或换房。"
        )

    block = (
        RoomBlock.objects.filter(
            room_id=room.pk,
            start_date__lt=new_check_out,
            end_date__gt=reservation.check_out_date,
        )
        .order_by("start_date")
        .first()
    )
    if block is not None:
        return (
            f"续住失败：房间 {room.room_no} 在 {block.start_date.isoformat()} → "
            f"{block.end_date.isoformat()} 有{block.get_block_type_display()}登记，不能连续入住。"
        )
    return None


def _refresh_prices(reservation: Reservation) -> None:
    """离线 sqlite 用：重算逐日价格明细与总额（与 PG 触发器同口径）。"""
    prices = _night_prices(
        reservation.room.room_type_id, reservation.check_in_date, reservation.check_out_date
    )
    ReservationPrice.objects.filter(reservation=reservation).delete()
    ReservationPrice.objects.bulk_create(
        [
            ReservationPrice(
                reservation=reservation,
                stay_date=reservation.check_in_date + timedelta(days=index),
                price=price,
            )
            for index, price in enumerate(prices)
        ]
    )
    total = sum(prices, Decimal("0.00"))
    reservation.total_amount = total
    reservation.price_per_night = (
        (total / len(prices)).quantize(Decimal("0.01")) if prices else Decimal("0.00")
    )
    reservation.save(update_fields=["total_amount", "price_per_night", "updated_at"])


# ---------------------------------------------------------------------- 小工具


def _parse_money(value: str) -> Decimal | None:
    if not value:
        return Decimal("0.00")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    if amount < 0:
        return None
    return amount.quantize(Decimal("0.01"))
