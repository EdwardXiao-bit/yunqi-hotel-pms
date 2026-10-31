"""F07 退房与结算（P08，`/reception/checkout/<pk>/`，pk = 入住记录 id）。

结算口径（与 `docs/页面约定.md` §F07、`sql/02_constraints.sql` 的 `v_check_in_detail` 一致）：

    应收合计 total_charge = 房费 room_charge + 加收房费 extra_room_charge + 服务费 service_charge
    已收已退 settled     = Σ payment（kind='refund' 记负）
    差额     balance     = total_charge − settled

- 押金在办理入住时作为一条 `kind='deposit'` 的支付流水入账（不计营业收入，只抵减差额）。
- 退房提交时必须把差额结清（`balance == 0`）：差额为正要求补收，为负要求退款（E07 押金不足/超出）。
- 房费按**实际入住晚数**取逐日价（`reservation_price`）；提前退房时剩余房晚自动释放
  （订单置 `checked_out` 后不再是占用状态），但至少按一房晚计费。
- 退房后房间转入 `cleaning`（清洁中），由 `trg_room_status_log` 自动记一条房态变更。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import role_required
from ..models import (
    PAYMENT_KIND_CHOICES,
    PAYMENT_METHOD_CHOICES,
    CheckInRecord,
    Payment,
    Reservation,
    ReservationPrice,
    Room,
    ServiceItem,
    ServiceOrder,
)
from ..roles import ROLE_RECEPTIONIST
from .reservations import _night_prices

SETTLE_KINDS = ("room_fee", "service_fee", "refund")
KIND_LABELS = dict(PAYMENT_KIND_CHOICES)
METHOD_LABELS = dict(PAYMENT_METHOD_CHOICES)
CENT = Decimal("0.01")


# ------------------------------------------------------------------ 公共小工具


def _money(value) -> Decimal | None:
    """把表单字符串解析成两位小数金额；非法返回 None。"""
    text = (str(value) if value is not None else "").strip()
    if not text:
        return None
    try:
        return Decimal(text).quantize(CENT)
    except (InvalidOperation, ValueError):
        return None


def next_payment_no(prefix: str = "P") -> str:
    """生成支付单号 `P + YYYYMMDD + 4 位序号`（同一天内递增，冲突时调用方重试）。"""
    today = timezone.localdate()
    head = f"{prefix}{today:%Y%m%d}"
    last = (
        Payment.objects.filter(payment_no__startswith=head)
        .order_by("-payment_no")
        .values_list("payment_no", flat=True)
        .first()
    )
    seq = int(last[len(head):]) + 1 if last and last[len(head):].isdigit() else 1
    return f"{head}{seq:04d}"


def create_payment(record: CheckInRecord, *, kind: str, method: str, amount: Decimal, operator=None, remark: str = "") -> Payment:
    """写一条支付流水；单号冲突时重试（并发在同一秒下单的兜底）。"""
    for attempt in range(4):
        payment_no = next_payment_no()
        if Payment.objects.filter(payment_no=payment_no).exists():
            continue
        try:
            return Payment.objects.create(
                payment_no=payment_no,
                check_in_record=record,
                kind=kind,
                method=method,
                amount=amount,
                paid_at=timezone.now(),
                operator_user=operator,
                remark=remark or None,
            )
        except IntegrityError:  # pragma: no cover - 并发兜底
            if attempt == 3:
                raise
    raise IntegrityError("支付单号生成失败")  # pragma: no cover


def record_deposit(record: CheckInRecord, amount: Decimal, operator=None) -> Payment | None:
    """入住时把押金记成一条 deposit 流水（金额为 0 时不记）。"""
    if amount is None or amount <= 0:
        return None
    return create_payment(record, kind="deposit", method="cash", amount=amount, operator=operator, remark="入住押金")


def settle_summary(record: CheckInRecord) -> dict:
    """已收/已退与差额（等价于 `v_check_in_detail` 的 settled_amount / balance）。"""
    payments = list(record.payments.order_by("paid_at", "id"))
    settled = sum(
        (-p.amount if p.kind == "refund" else p.amount) for p in payments
    ) or Decimal("0.00")
    total = Decimal(str(record.total_charge or 0))
    return {
        "payments": payments,
        "settled": Decimal(settled).quantize(CENT),
        "balance": (total - Decimal(settled)).quantize(CENT),
    }


def _service_orders(record: CheckInRecord) -> list[ServiceOrder]:
    return list(record.service_orders.select_related("service_item").order_by("id"))


def _local_date(value: datetime) -> date:
    return timezone.localtime(value).date() if value else timezone.localdate()


def _actual_nights(record: CheckInRecord, checkout_at: datetime) -> int:
    nights = (_local_date(checkout_at) - _local_date(record.check_in_at)).days
    return max(nights, 1)


def _stay_price_rows(record: CheckInRecord, checkout_at: datetime) -> list[ReservationPrice]:
    """实际入住的逐日价：住宿日 < 退房日。"""
    return list(
        ReservationPrice.objects.filter(
            reservation_id=record.reservation_id,
            stay_date__lt=_local_date(checkout_at),
        ).order_by("stay_date")
    )


def _room_charge(record: CheckInRecord, checkout_at: datetime) -> Decimal:
    """房费 = 实际入住房晚的逐日价之和；缺明细时按取价函数口径现算（至少一房晚）。"""
    rows = _stay_price_rows(record, checkout_at)
    nights = _actual_nights(record, checkout_at)
    if rows:
        prices = [Decimal(str(r.price)) for r in rows][:nights]
        return sum(prices, Decimal("0.00")).quantize(CENT)
    reservation = record.reservation
    check_in = _local_date(record.check_in_at)
    check_out = check_in + timedelta(days=nights)
    return sum(_night_prices(reservation.room.room_type_id, check_in, check_out), Decimal("0.00")).quantize(CENT)


def _parse_datetime(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            naive = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return None


# ------------------------------------------------------------------ P08 页面


@role_required(ROLE_RECEPTIONIST, "admin")
def checkout_detail(request, pk: int):
    """P08：退房结算单（GET 预览账单，POST 提交结算）。"""
    record = get_object_or_404(
        CheckInRecord.objects.select_related("reservation__room__room_type", "reservation__customer"),
        pk=pk,
    )
    if request.method == "POST":
        return _submit_checkout(request, record)
    return _render(request, record, checkout_at=timezone.now())


def _render(request, record: CheckInRecord, *, checkout_at: datetime, error: str | None = None, posted: dict | None = None):
    reservation = record.reservation
    service_orders = _service_orders(record)
    summary = settle_summary(record)
    room_charge = _room_charge(record, checkout_at)
    extra = Decimal(str((posted or {}).get("extra_room_charge") or 0)) if posted else Decimal("0.00")
    service_charge = sum((Decimal(str(o.amount)) for o in service_orders), Decimal("0.00"))
    total_charge = (room_charge + extra + service_charge).quantize(CENT)

    planned_out = reservation.check_out_date
    actual_out = _local_date(checkout_at)
    overtime = max((actual_out - planned_out).days, 0)
    early = max((planned_out - actual_out).days, 0)

    context = {
        "record": record,
        "reservation": reservation,
        "room": reservation.room,
        "customer": reservation.customer,
        "service_orders": service_orders,
        "payments": summary["payments"],
        "settled": summary["settled"],
        "balance": (total_charge - summary["settled"]).quantize(CENT),
        "balance_abs": abs((total_charge - summary["settled"]).quantize(CENT)),
        "room_charge": room_charge,
        "service_charge": service_charge,
        "extra_room_charge": extra,
        "total_charge": total_charge,
        "nights": _actual_nights(record, checkout_at),
        "price_rows": _stay_price_rows(record, checkout_at),
        "service_items": list(ServiceItem.objects.filter(is_active=True).order_by("id")),
        "settle_kinds": [(k, KIND_LABELS.get(k, k)) for k in SETTLE_KINDS],
        "methods": list(PAYMENT_METHOD_CHOICES),
        "checkout_at_value": timezone.localtime(checkout_at).strftime("%Y-%m-%dT%H:%M"),
        "planned_out": planned_out,
        "actual_out": actual_out,
        "overtime_days": overtime,
        "early_days": early,
        "error": error,
        "posted": posted or {},
        "today": timezone.localdate(),
        "already_checked_out": record.actual_checkout_at is not None,
    }
    return render(request, "reception/checkout_detail.html", context)


def _submit_checkout(request, record: CheckInRecord):
    form = request.POST
    if record.actual_checkout_at is not None:
        stamp = timezone.localtime(record.actual_checkout_at).strftime("%Y-%m-%d %H:%M")
        return _render(
            request,
            record,
            checkout_at=record.actual_checkout_at,
            error=f"该入住记录已于 {stamp} 办过退房，不能重复结算。",
            posted=_posted_snapshot(form),
        )
    checkout_at = _parse_datetime(form.get("actual_checkout_at")) or timezone.now()
    if checkout_at < record.check_in_at:
        return _render(
            request,
            record,
            checkout_at=checkout_at,
            error="退房时间不能早于入住时间。",
            posted=_posted_snapshot(form),
        )

    extra = _money(form.get("extra_room_charge") or "0")
    if extra is None or extra < 0:
        return _render(request, record, checkout_at=checkout_at, error="加收房费请填写不小于 0 的金额。", posted=_posted_snapshot(form))

    # ---- 服务消费行（可多行；同一服务项目合并数量）
    picked: dict[int, int] = {}
    item_ids = form.getlist("service_item_id")
    quantities = form.getlist("service_quantity")
    for raw_id, raw_qty in zip(item_ids, quantities):
        item_id = (raw_id or "").strip()
        if not item_id:
            continue
        try:
            item_pk = int(item_id)
        except ValueError:
            return _render(request, record, checkout_at=checkout_at, error="服务项目选择不正确。", posted=_posted_snapshot(form))
        try:
            qty = int((raw_qty or "0").strip() or 0)
        except ValueError:
            return _render(request, record, checkout_at=checkout_at, error="服务数量请填写正整数。", posted=_posted_snapshot(form))
        if qty <= 0:
            if qty == 0:
                continue
            return _render(request, record, checkout_at=checkout_at, error="服务数量请填写正整数。", posted=_posted_snapshot(form))
        picked[item_pk] = picked.get(item_pk, 0) + qty

    # ---- 收款/退款行
    money_rows: list[dict] = []
    kinds = form.getlist("payment_kind")
    methods = form.getlist("payment_method")
    amounts = form.getlist("payment_amount")
    for raw_kind, raw_method, raw_amount in zip(kinds, methods, amounts):
        kind = (raw_kind or "").strip()
        method = (raw_method or "").strip()
        amount = _money(raw_amount)
        if not kind and not method and (raw_amount or "").strip() == "":
            continue
        if amount is None or amount <= 0:
            return _render(
                request, record, checkout_at=checkout_at,
                error="收款/退款金额请填写大于 0 的数字（没有款项的行请留空）。",
                posted=_posted_snapshot(form),
            )
        if kind not in SETTLE_KINDS:
            return _render(request, record, checkout_at=checkout_at, error="款项类型不正确。", posted=_posted_snapshot(form))
        if method not in METHOD_LABELS:
            return _render(request, record, checkout_at=checkout_at, error="支付方式不正确。", posted=_posted_snapshot(form))
        money_rows.append({"kind": kind, "method": method, "amount": amount})

    # ---- 服务项目一次取回，缺项就报错（不静默丢行）
    picked_items: dict[int, ServiceItem] = {}
    if picked:
        picked_items = {item.pk: item for item in ServiceItem.objects.filter(pk__in=list(picked))}
        missing = [pk for pk in picked if pk not in picked_items]
        if missing:
            return _render(
                request, record, checkout_at=checkout_at,
                error="选择的服务项目已下架或不存在，请刷新页面后重试。",
                posted=_posted_snapshot(form),
            )

    # ---- 先在内存里算一遍账单，差额不平就不落库
    room_charge = _room_charge(record, checkout_at)
    service_charge = sum(
        (Decimal(str(picked_items[item_pk].price)) * qty for item_pk, qty in picked.items()),
        Decimal("0.00"),
    ).quantize(CENT)
    total_charge = (room_charge + extra + service_charge).quantize(CENT)
    settled_before = settle_summary(record)["settled"]
    settled_new = sum(
        (-row["amount"] if row["kind"] == "refund" else row["amount"] for row in money_rows),
        Decimal("0.00"),
    )
    balance = (total_charge - settled_before - settled_new).quantize(CENT)
    if balance != 0:
        if balance > 0:
            return _render(
                request, record, checkout_at=checkout_at,
                error=f"还需补收 {balance:.2f} 元才能结账（应收 {total_charge:.2f}，已收 {settled_before + settled_new:.2f}）。",
                posted=_posted_snapshot(form),
            )
        return _render(
            request, record, checkout_at=checkout_at,
            error=f"还需退给客人 {abs(balance):.2f} 元才能结账（应收 {total_charge:.2f}，已收 {settled_before + settled_new:.2f}）。",
            posted=_posted_snapshot(form),
        )

    try:
        with transaction.atomic():
            # 1) 服务消费明细（单价用服务项目当前价快照）
            for item_pk, qty in picked.items():
                item = picked_items[item_pk]
                ServiceOrder.objects.create(
                    check_in_record=record,
                    service_item=item,
                    quantity=qty,
                    unit_price=item.price,
                    ordered_at=timezone.now(),
                )

            # 2) 收款/退款流水
            for row in money_rows:
                create_payment(
                    record,
                    kind=row["kind"],
                    method=row["method"],
                    amount=row["amount"],
                    operator=request.user,
                    remark="退房结算",
                )

            # 3) 回写入住记录与订单状态
            record.actual_checkout_at = checkout_at
            record.room_charge = room_charge
            record.service_charge = service_charge
            record.total_charge = total_charge
            record.save(update_fields=["actual_checkout_at", "room_charge", "service_charge", "total_charge"])

            reservation = record.reservation
            reservation.status = "checked_out"
            reservation.save(update_fields=["status"])

            # 4) 房间转清洁中（触发器自动写 room_status_log）
            Room.objects.filter(pk=reservation.room_id).update(status="cleaning")
    except IntegrityError:
        return _render(
            request, record, checkout_at=checkout_at,
            error="结算写入失败（可能是支付单号重复或数据已被他人修改），请刷新后重试。",
            posted=_posted_snapshot(form),
        )

    early = max((record.reservation.check_out_date - _local_date(checkout_at)).days, 0)
    tail = f"，提前退房释放 {early} 个房晚" if early else ""
    messages.success(
        request,
        f"退房结算完成：{record.guest_name} 房费 {room_charge:.2f} + 服务费 {service_charge:.2f}"
        f" + 加收 {extra:.2f} = 应收 {total_charge:.2f} 元{tail}；房间 {reservation.room.room_no} 已转「清洁中」。",
    )
    return redirect("core:checkin_new")


def _posted_snapshot(form) -> dict:
    """回显用户填过的值（出错的时不必重新录一遍）。"""
    return {
        "extra_room_charge": form.get("extra_room_charge") or "",
        "service_item_id": form.getlist("service_item_id"),
        "service_quantity": form.getlist("service_quantity"),
        "payment_kind": form.getlist("payment_kind"),
        "payment_method": form.getlist("payment_method"),
        "payment_amount": form.getlist("payment_amount"),
    }
