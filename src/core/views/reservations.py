"""预订提交与预订管理（F04 / F05；P03、P04、P06）。

契约见 `docs/页面约定.md` §3 F04 / F05：

- P03 预订提交 `/reservations/new/`：从 P02 带 `room_id` + 两个日期进入，确认房号/房型/首晚价后提交。
- P04 我的预订 `/my/reservations/`（列表 + 筛选 + 分页）与 `/my/reservations/<pk>/`（详情 + 取消）。
- P06 预订管理 `/reception/reservations/`：前台按状态 / 日期 / 关键字筛选，执行确认 / 取消。

写操作全部走 POST，成功后 `redirect()` + `messages`；状态机在服务端再校验一次（不靠前端禁用按钮）。
数据库侧的三条兜底（`docs/02` §7）：
- 23P01 `ex_reservation_room_overlap` → 该房间在所选日期已被预订（E02）
- 23514 `fn_check_reservation_block()` → 所选日期处于维修 / 停用区间（E04）
- 23505 `uq_reservation_active_customer` → 已提交过相同区间、相同房间的预订（E03）
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..decorators import role_required
from ..models import (
    CheckInRecord,
    Customer,
    Payment,
    RatePlan,
    Reservation,
    ReservationPrice,
    Room,
    RoomType,
)
from ..roles import ROLE_CUSTOMER, ROLE_RECEPTIONIST
from .rooms import _query_available, _translate_db_error

# 预订状态机（docs/02 §4.1 / 页面约定 F05）
CANCELLABLE_STATUSES = ("pending", "confirmed")
ACTIVE_STATUSES = ("pending", "confirmed", "checked_in")
STATUS_LABELS = dict(Reservation._meta.get_field("status").choices)

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
GUEST_COUNT_MAX = 8

# 前台 P06 每页条数（页面约定 §4：服务端分页，每页 20）
PAGE_SIZE = 20


# ---------------------------------------------------------------- P03 预订提交


@login_required
def reservation_create(request):
    """P03 预订提交：GET 确认信息 + 表单，POST 落库（区间冲突由数据库约束兜底）。"""
    customer = _current_customer(request)
    if customer is None:
        messages.error(request, "当前账号没有关联的客户档案，无法下单；请联系前台用手机号建立客户档案。")
        return redirect("core:customer_home")

    if request.method == "POST":
        return _create_from_post(request, customer)
    return _render_create_form(request, customer)


def _render_create_form(request, customer, *, data: dict | None = None, errors: list[str] | None = None):
    """渲染 P03（GET 与 POST 失败复用同一份上下文）。"""
    today = timezone.localdate()
    data = data or {}
    room_id = data.get("room_id") or request.GET.get("room_id") or ""
    check_in_raw = data.get("check_in_date") or request.GET.get("check_in_date") or ""
    check_out_raw = data.get("check_out_date") or request.GET.get("check_out_date") or ""

    room = None
    if room_id:
        room = (
            Room.objects.select_related("room_type")
            .filter(pk=_as_int(room_id) or 0)
            .first()
        )
    used_room_id = room.pk if room else room_id

    # 默认日期：没带参数时按「明天 → 后天」
    if not check_in_raw:
        check_in_raw = (today + timedelta(days=1)).isoformat()
    if not check_out_raw:
        check_out_raw = (today + timedelta(days=3)).isoformat()

    check_in = _try_date(check_in_raw) or today + timedelta(days=1)
    check_out = _try_date(check_out_raw) or (check_in + timedelta(days=2))
    nights = max((check_out - check_in).days, 0)

    # 首晚价格：与库里触发器 fn_sync_reservation_prices 同口径（rate_plan 命中价否则标准价）
    first_night_price = Decimal("0.00")
    estimate_total = Decimal("0.00")
    if room is not None and nights > 0:
        prices = _night_prices(room.room_type_id, check_in, check_out)
        if prices:
            first_night_price = prices[0]
            estimate_total = sum(prices, Decimal("0.00"))

    return render(
        request,
        "customer/reservation_create.html",
        {
            "customer": customer,
            "room": room,
            "room_id": used_room_id,
            "check_in_date": check_in,
            "check_out_date": check_out,
            "nights": nights,
            "first_night_price": first_night_price,
            "estimate_total": estimate_total,
            "guest_count": data.get("guest_count") or (room.room_type.capacity if room else 1),
            "capacity": room.room_type.capacity if room else GUEST_COUNT_MAX,
            "guest_name": data.get("guest_name") or customer.name,
            "guest_phone": data.get("guest_phone") or customer.phone,
            "remark": data.get("remark") or "",
            "today": today,
            "errors": errors or [],
        },
    )


def _create_from_post(request, customer):
    """校验 POST → 落库。失败回显原页（保留已填内容）。"""
    data = {
        "room_id": (request.POST.get("room_id") or "").strip(),
        "check_in_date": (request.POST.get("check_in_date") or "").strip(),
        "check_out_date": (request.POST.get("check_out_date") or "").strip(),
        "guest_count": (request.POST.get("guest_count") or "").strip(),
        "guest_name": (request.POST.get("guest_name") or "").strip(),
        "guest_phone": (request.POST.get("guest_phone") or "").strip(),
        "remark": (request.POST.get("remark") or "").strip(),
    }

    errors = _validate_booking(data, customer)
    room = Room.objects.select_related("room_type").filter(pk=_as_int(data["room_id"]) or 0).first()
    if not errors and room is None:
        errors.append("房间参数不正确，请回到可用房查询页重新选择房间。")

    if not errors:
        check_in = _try_date(data["check_in_date"])
        check_out = _try_date(data["check_out_date"])
        assert check_in is not None and check_out is not None
        guest_count = int(data["guest_count"])
        # 预检查（并发下的最终保证是 ex_reservation_room_overlap）
        available_ids = {row["room_id"] for row in _query_available(check_in, check_out, None, None)}
        if room.pk not in available_ids:
            errors.append(
                "该房间在所选日期不可预订（可能已被预订，或处于维修/停用区间）。请重新查询可用房或调整日期。"
            )

    if errors:
        return _render_create_form(request, customer, data=data, errors=errors)

    assert room is not None
    check_in = _try_date(data["check_in_date"])
    check_out = _try_date(data["check_out_date"])
    assert check_in is not None and check_out is not None
    prices = _night_prices(room.room_type_id, check_in, check_out)
    total = sum(prices, Decimal("0.00"))
    nights = len(prices)
    price_per_night = (total / nights).quantize(Decimal("0.01")) if nights else Decimal("0.00")

    try:
        reservation = _insert_reservation(
            customer=customer,
            room=room,
            check_in=check_in,
            check_out=check_out,
            guest_count=int(data["guest_count"]),
            price_per_night=price_per_night,
            total_amount=total,
            remark=data["remark"],
        )
    except IntegrityError as exc:
        messages.error(request, _translate_booking_error(exc))
        return _render_create_form(request, customer, data=data, errors=[])

    messages.success(
        request,
        f"预订成功：{reservation.reservation_no}（{room.room_no} {room.room_type.name}，"
        f"{check_in.isoformat()} → {check_out.isoformat()}，共 {nights} 晚，"
        f"金额 {total:.2f} 元），等待前台确认。",
    )
    return redirect("core:my_reservation_detail", pk=reservation.pk)


def _validate_booking(data: dict, customer: Customer) -> list[str]:
    """应用层校验（字段级）。区间冲突不在这里判，交给数据库与可用房预检查。"""
    errors: list[str] = []
    today = timezone.localdate()

    check_in = _try_date(data["check_in_date"])
    check_out = _try_date(data["check_out_date"])
    if not data["check_in_date"]:
        errors.append("请填写入住日期。")
    elif check_in is None:
        errors.append("入住日期格式不正确，请用 2026-12-20 这样的写法。")
    if not data["check_out_date"]:
        errors.append("请填写离店日期。")
    elif check_out is None:
        errors.append("离店日期格式不正确，请用 2026-12-22 这样的写法。")
    if check_in and check_out and check_out <= check_in:
        errors.append("离店日期必须晚于入住日期（离店当天不计房晚）。")
    if check_in and check_in < today:
        errors.append(f"入住日期不能早于今天（{today.isoformat()}）。")

    if not data["guest_count"]:
        errors.append("请填写入住人数。")
    else:
        try:
            guest_count = int(data["guest_count"])
        except ValueError:
            errors.append("入住人数必须是整数。")
        else:
            if guest_count < 1:
                errors.append("入住人数至少为 1。")
            elif guest_count > GUEST_COUNT_MAX:
                errors.append(f"入住人数不能超过 {GUEST_COUNT_MAX} 人。")
            else:
                room = Room.objects.select_related("room_type").filter(pk=_as_int(data["room_id"]) or 0).first()
                if room is not None and guest_count > room.room_type.capacity:
                    errors.append(
                        f"{room.room_type.name} 最多可住 {room.room_type.capacity} 人，请减少入住人数或换房型。"
                    )

    if not data["guest_name"]:
        errors.append("请填写联系人姓名。")
    elif len(data["guest_name"]) > 50:
        errors.append("联系人姓名不能超过 50 个字。")

    if not data["guest_phone"]:
        errors.append("请填写联系人手机号。")
    elif not PHONE_RE.match(data["guest_phone"]):
        errors.append("联系电话请填写 11 位手机号（例如 13800001101）。")

    if len(data["remark"]) > 200:
        errors.append("备注不能超过 200 个字。")

    return errors


def _insert_reservation(
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
    """插入预订；`reservation_no` 冲突（并发）时换号重试 3 次。

    PostgreSQL 上逐日价格与总额由触发器 `fn_sync_reservation_prices()` /
    `fn_refresh_reservation_total()` 回写；离线 sqlite 冒烟没有触发器，这里补一份等价明细，
    保证两种模式页面表现一致（口径与 `_night_prices()` 相同）。
    """
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
                    status="pending",
                    source="online",
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


def _next_reservation_no(check_in: date, attempt: int) -> str:
    """预订号 `R{YYYYMMDD}{5 位序号}`，与种子数据同一风格。"""
    prefix = f"R{check_in:%Y%m%d}"
    last = (
        Reservation.objects.filter(reservation_no__startswith=prefix)
        .order_by("-reservation_no")
        .values_list("reservation_no", flat=True)
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(last[len(prefix):]) + 1
        except ValueError:
            seq = 1
    return f"{prefix}{seq + attempt:05d}"


def _is_duplicate_reservation_no(exc: IntegrityError) -> bool:
    constraint = _constraint_name(exc)
    return constraint is not None and "reservation_no" in constraint


def _translate_booking_error(exc: IntegrityError) -> str:
    """把预订落库时的数据库异常翻成中文（E02 / E03 / E04）。"""
    constraint = _constraint_name(exc) or ""
    text = f"{exc} {exc.__cause__ or ''}"
    if "23P01" in text or "ex_reservation_room_overlap" in text or "exclusion" in text.lower():
        return "该房间在所选日期已被预订，请换一间或调整日期。"
    if "23514" in text or constraint.startswith("fn_check"):
        return "所选日期处于该房间的维修/停用区间，无法预订，请换一间或调整日期。"
    if "uq_reservation_active_customer" in text or "reservation_active_customer" in constraint:
        return "您已提交过相同区间、相同房间的预订，请勿重复提交。"
    if "uq_reservation_no" in text or "reservation_no" in constraint:
        return "预订号生成冲突，请重试一次。"
    return f"预订提交失败：{_translate_db_error(exc)}"


def _constraint_name(exc: IntegrityError) -> str | None:
    """从 psycopg2 异常里取约束名（sqlite 没有 diag，返回 None）。"""
    cause = exc.__cause__
    diag = getattr(cause, "diag", None)
    return getattr(diag, "constraint_name", None)


# ---------------------------------------------------------------- P04 我的预订


@login_required
def my_reservations(request):
    """P04 我的预订：列表 + 状态筛选 + 服务端分页。"""
    customer = _current_customer(request)
    if customer is None:
        messages.error(request, "当前账号没有关联的客户档案。")
        return redirect("core:customer_home")

    status = (request.GET.get("status") or "").strip()
    queryset = (
        Reservation.objects.filter(customer_id=customer.pk)
        .select_related("room", "room__room_type")
        .order_by("-check_in_date", "-id")
    )
    if status in STATUS_LABELS:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "customer/my_reservations.html",
        {
            "customer": customer,
            "page_obj": page,
            "reservations": page.object_list,
            "status": status,
            "status_choices": list(STATUS_LABELS.items()),
            "total": paginator.count,
            "today": timezone.localdate(),
        },
    )


@login_required
def my_reservation_detail(request, pk: int):
    """P04 详情：住宿明细（逐日价）+ 入住/支付信息 + 取消按钮（仅待确认/已确认）。"""
    customer = _current_customer(request)
    if customer is None:
        messages.error(request, "当前账号没有关联的客户档案。")
        return redirect("core:customer_home")

    reservation = get_object_or_404(
        Reservation.objects.select_related("room", "room__room_type", "customer"),
        pk=pk,
        customer_id=customer.pk,
    )
    return _render_detail(request, reservation, template="customer/reservation_detail.html")


def _render_detail(request, reservation: Reservation, *, template: str):
    daily_prices = ReservationPrice.objects.filter(reservation_id=reservation.pk).order_by("stay_date")
    check_in_record = CheckInRecord.objects.filter(reservation_id=reservation.pk).first()
    payments = (
        Payment.objects.filter(check_in_record_id=check_in_record.pk).order_by("paid_at", "id")
        if check_in_record
        else Payment.objects.none()
    )
    return render(
        request,
        template,
        {
            "reservation": reservation,
            "daily_prices": daily_prices,
            "check_in_record": check_in_record,
            "payments": payments,
            "status_label": STATUS_LABELS.get(reservation.status, reservation.status),
            "can_cancel": _can_cancel(reservation),
            "today": timezone.localdate(),
        },
    )


def _can_cancel(reservation: Reservation) -> bool:
    """客户侧可取消：待确认/已确认，且尚未到入住日（到店后由前台处理）。"""
    return reservation.status in CANCELLABLE_STATUSES and reservation.check_in_date >= timezone.localdate()


@login_required
@require_POST
def my_reservation_cancel(request, pk: int):
    """P04 取消预订：服务端再校验一次状态机（E05）。"""
    customer = _current_customer(request)
    if customer is None:
        messages.error(request, "当前账号没有关联的客户档案。")
        return redirect("core:customer_home")

    reservation = get_object_or_404(Reservation, pk=pk, customer_id=customer.pk)
    try:
        _cancel_reservation(reservation, actor=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"已取消预订 {reservation.reservation_no}，占用日期已释放。")
    return redirect("core:my_reservation_detail", pk=reservation.pk)


# ---------------------------------------------------------------- P06 预订管理


@role_required(ROLE_RECEPTIONIST, "admin")
def reception_reservations(request):
    """P06 预订管理：按状态 / 入住日期区间 / 关键字筛选 + 分页；POST 执行确认 / 取消。"""
    if request.method == "POST":
        return _handle_reception_action(request)

    status = (request.GET.get("status") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    keyword = (request.GET.get("keyword") or "").strip()

    queryset = Reservation.objects.select_related("customer", "room", "room__room_type").order_by(
        "-check_in_date", "-id"
    )
    quick = (request.GET.get("quick") or "").strip()
    if quick == "today":  # 今日到店快捷筛选（前台工作台常用）
        queryset = queryset.filter(check_in_date=timezone.localdate(), status="confirmed")
    if status in STATUS_LABELS:
        queryset = queryset.filter(status=status)
    if date_from and _try_date(date_from):
        queryset = queryset.filter(check_in_date__gte=_try_date(date_from))
    if date_to and _try_date(date_to):
        queryset = queryset.filter(check_in_date__lte=_try_date(date_to))
    if keyword:
        queryset = queryset.filter(
            Q(reservation_no__icontains=keyword)
            | Q(customer__name__icontains=keyword)
            | Q(customer__phone__icontains=keyword)
        )

    paginator = Paginator(queryset, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "reception/reservation_manage.html",
        {
            "page_obj": page,
            "reservations": page.object_list,
            "status": status,
            "status_choices": list(STATUS_LABELS.items()),
            "date_from": date_from,
            "date_to": date_to,
            "keyword": keyword,
            "quick": quick,
            "total": paginator.count,
            "today": timezone.localdate(),
        },
    )


def _handle_reception_action(request):
    """确认 / 取消：同一个端点，`action` 决定动作，状态机在服务端校验。"""
    reservation_id = _as_int((request.POST.get("reservation_id") or "").strip())
    action = (request.POST.get("action") or "").strip()
    redirect_to = reverse("core:reception_reservations")
    if request.POST.get("next"):
        redirect_to = request.POST["next"]

    if reservation_id is None:
        messages.error(request, "缺少预订编号，请重试。")
        return HttpResponseRedirect(redirect_to)

    reservation = Reservation.objects.filter(pk=reservation_id).first()
    if reservation is None:
        messages.error(request, "预订不存在或已被删除。")
        return HttpResponseRedirect(redirect_to)

    try:
        if action == "confirm":
            _confirm_reservation(reservation)
            messages.success(request, f"已确认预订 {reservation.reservation_no}。")
        elif action == "cancel":
            _cancel_reservation(reservation, actor=request.user)
            messages.success(request, f"已取消预订 {reservation.reservation_no}，占用日期已释放。")
        elif action == "no_show":
            _mark_no_show(reservation)
            messages.success(request, f"预订 {reservation.reservation_no} 已标记为未到店，占用日期已释放。")
        else:
            messages.error(request, "未知操作，请使用页面上的按钮。")
    except ValueError as exc:
        messages.error(request, str(exc))
    return HttpResponseRedirect(redirect_to)


def _confirm_reservation(reservation: Reservation) -> None:
    if reservation.status != "pending":
        raise ValueError(f"只有“待确认”的预订可以确认，当前状态为“{STATUS_LABELS.get(reservation.status)}”。")
    reservation.status = "confirmed"
    reservation.save(update_fields=["status", "updated_at"])


def _cancel_reservation(reservation: Reservation, *, actor) -> None:
    if reservation.status not in CANCELLABLE_STATUSES:
        raise ValueError(
            f"只有“待确认 / 已确认”的预订可以取消，当前状态为“{STATUS_LABELS.get(reservation.status)}”；"
            "已入住订单请走退房结算，已退房/已取消订单无需再取消。"
        )
    if reservation.status == "confirmed" and reservation.check_in_date < timezone.localdate():
        raise ValueError("该预订的入住日期已过，请用“未到店”处理，不要取消。")
    reservation.status = "cancelled"
    reservation.save(update_fields=["status", "updated_at"])


def _mark_no_show(reservation: Reservation) -> None:
    if reservation.status != "confirmed":
        raise ValueError("只有“已确认”的预订可以标记为未到店。")
    if reservation.check_in_date > timezone.localdate():
        raise ValueError("入住日期还没到，不能标记为未到店。")
    reservation.status = "no_show"
    reservation.save(update_fields=["status", "updated_at"])


# ---------------------------------------------------------------- 公共小工具


def _current_customer(request) -> Customer | None:
    """登录账号关联的客户档案（管理员/前台账号通常没有）。"""
    if not request.user.is_authenticated:
        return None
    return Customer.objects.filter(user_id=request.user.pk).first()


def _as_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _try_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def _night_prices(room_type_id: int, check_in: date, check_out: date) -> list[Decimal]:
    """逐日成交价：与 `fn_sync_reservation_prices()` 同口径（命中 rate_plan 否则标准价）。"""
    plans = list(
        RatePlan.objects.filter(room_type_id=room_type_id).order_by("-valid_from", "-id")
    )
    base_price = (
        RoomType.objects.filter(pk=room_type_id).values_list("base_price", flat=True).first()
        or Decimal("0.00")
    )
    prices: list[Decimal] = []
    cursor = check_in
    while cursor < check_out:
        price = Decimal(str(base_price))
        for plan in plans:
            if plan.valid_from <= cursor <= plan.valid_to:
                price = Decimal(str(plan.price))
                break
        prices.append(price)
        cursor += timedelta(days=1)
    return prices
