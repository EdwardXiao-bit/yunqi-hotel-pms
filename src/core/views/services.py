"""增值服务（F07 的消费明细）：价目表维护（P15）+ 前台登记与记录（P16）。

设计要点：
- `service_order` 是「入住期间发生的消费」，登记一次就落一条明细，`unit_price` 存当时单价（快照），
  `amount` 由数据库生成列 `quantity * unit_price` 算出，应用层不写。
- 登记后把 `check_in_record.service_charge` / `total_charge` 按**全部**已登记明细重算，
  保证退房结算页的「服务费」与明细一致（结算页只负责加收房费与收退款，不再重复登记已有明细）。
- 价目表停用（`is_active=False`）只影响「还能不能选」，历史明细仍按快照保留。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from core.decorators import role_required
from core.models import CheckInRecord, Customer, ServiceItem, ServiceOrder

CENT = Decimal("0.01")


def _money(value) -> Decimal | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None
    if amount < 0:
        return None
    return amount.quantize(CENT)


def _items_with_usage():
    return ServiceItem.objects.annotate(
        order_count=Count("orders", distinct=True),
        order_total=Sum("orders__amount"),
    ).order_by("code")


# ---------------------------------------------------------------- 价目表维护（P15）

@role_required("admin")
def service_item_list(request):
    """增值服务项目：价目表维护 + 使用统计。"""
    if request.method == "POST":
        return _handle_item_action(request)

    keyword = (request.GET.get("keyword") or "").strip()
    active = (request.GET.get("active") or "").strip()

    items = _items_with_usage()
    if keyword:
        items = items.filter(Q(code__icontains=keyword) | Q(name__icontains=keyword))
    if active in {"1", "0"}:
        items = items.filter(is_active=(active == "1"))

    summary = {
        "total": ServiceItem.objects.count(),
        "active": ServiceItem.objects.filter(is_active=True).count(),
        "orders": ServiceOrder.objects.count(),
        "revenue": ServiceOrder.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
    }

    return render(
        request,
        "manage/service_item_list.html",
        {
            "items": items,
            "keyword": keyword,
            "active": active,
            "summary": summary,
        },
    )


def _handle_item_action(request):
    action = (request.POST.get("action") or "").strip()
    item = ServiceItem.objects.filter(pk=(request.POST.get("item_id") or 0)).first()
    if item is None:
        messages.error(request, "服务项目不存在或已被删除。")
        return redirect("core:service_item_list")

    if action == "toggle":
        item.is_active = not item.is_active
        item.save(update_fields=["is_active"])
        messages.success(
            request,
            "服务项目「%s」已%s。" % (item.name, "上架" if item.is_active else "下架（历史明细保留）"),
        )
        return redirect("core:service_item_list")

    if action == "delete":
        if ServiceOrder.objects.filter(service_item_id=item.pk).exists():
            messages.error(
                request,
                "「%s」已有消费记录，不能删除；如果不再提供，请下架。" % item.name,
            )
            return redirect("core:service_item_list")
        try:
            with transaction.atomic():
                item.delete()
        except IntegrityError:
            messages.error(request, "「%s」仍被其他数据引用，不能删除。" % item.name)
            return redirect("core:service_item_list")
        messages.success(request, "服务项目「%s」已删除。" % item.name)
        return redirect("core:service_item_list")

    messages.error(request, "未识别的操作。")
    return redirect("core:service_item_list")


@role_required("admin")
def service_item_form(request, pk: int | None = None):
    """新建 / 编辑增值服务项目。"""
    item = get_object_or_404(ServiceItem, pk=pk) if pk else None
    values = _item_form_values(item, request.POST if request.method == "POST" else None)

    if request.method == "POST":
        errors: list[str] = []
        code = values["code"].strip()
        name = values["name"].strip()
        unit = values["unit"].strip() or "份"
        price = _money(values["price"])
        is_active = values["is_active"] == "1"

        if not code:
            errors.append("请填写服务编码，例如 BF、SPA。")
        elif len(code) > 20:
            errors.append("服务编码最多 20 个字符。")
        else:
            duplicated = ServiceItem.objects.filter(code=code)
            if item is not None:
                duplicated = duplicated.exclude(pk=item.pk)
            if duplicated.exists():
                errors.append("服务编码 %s 已存在，请换一个。" % code)
        if not name:
            errors.append("请填写服务名称。")
        elif len(name) > 50:
            errors.append("服务名称最多 50 个字符。")
        else:
            duplicated = ServiceItem.objects.filter(name=name)
            if item is not None:
                duplicated = duplicated.exclude(pk=item.pk)
            if duplicated.exists():
                errors.append("服务名称已存在，请换一个。")
        if len(unit) > 10:
            errors.append("计量单位最多 10 个字符。")
        if price is None:
            errors.append("请填写单价（不小于 0 的数字，可带两位小数）。")

        if errors:
            for text in errors:
                messages.error(request, text)
            return render(
                request,
                "manage/service_item_form.html",
                {"item": item, "form": values, "active_options": [("1", "在售"), ("0", "下架")]},
            )

        if item is None:
            item = ServiceItem(code=code, name=name, unit=unit, price=price, is_active=is_active)
            verb = "新增"
        else:
            item.code = code
            item.name = name
            item.unit = unit
            item.price = price
            item.is_active = is_active
            verb = "保存"
        try:
            with transaction.atomic():
                item.save()
        except IntegrityError:
            messages.error(request, "保存失败：服务编码或名称重复，请检查后重试。")
            return redirect("core:service_item_list")

        messages.success(
            request,
            "服务项目「%s」已%s（%s %.2f 元/%s）。" % (item.name, verb, item.code, item.price, item.unit),
        )
        return redirect("core:service_item_list")

    return render(
        request,
        "manage/service_item_form.html",
        {"item": item, "form": values, "active_options": [("1", "在售"), ("0", "下架")]},
    )


def _item_form_values(item: ServiceItem | None, posted: dict | None = None) -> dict:
    posted = posted or {}

    def pick(key: str, default: str = "") -> str:
        if key in posted:
            return posted.get(key) or ""
        if item is None:
            return default
        value = getattr(item, key)
        if value is None:
            return ""
        if key == "is_active":
            return "1" if value else "0"
        return str(value)

    return {
        "code": pick("code"),
        "name": pick("name"),
        "unit": pick("unit", "份"),
        "price": pick("price"),
        "is_active": pick("is_active", "1") or "1",
    }


# ---------------------------------------------------------------- 前台登记与记录（P16）

IN_HOUSE_LIMIT = 30
RECENT_LIMIT = 20


def _in_house_records():
    """在住（已入住且未退房）的入住记录。"""
    return (
        CheckInRecord.objects.select_related("reservation", "reservation__room", "reservation__customer")
        .filter(actual_checkout_at__isnull=True, reservation__status="checked_in")
        .order_by("check_in_at")
    )


def _charge_summary(record: CheckInRecord) -> dict:
    orders = list(record.service_orders.select_related("service_item").order_by("id"))
    service_total = sum((Decimal(str(order.amount)) for order in orders), Decimal("0.00")).quantize(CENT)
    return {"orders": orders, "service_total": service_total}


def _sync_charges(record: CheckInRecord) -> None:
    """按全部服务明细重算入住记录的服务费与应收合计。"""
    summary = _charge_summary(record)
    room_charge = Decimal(str(record.room_charge or "0.00"))
    service_total = summary["service_total"]
    record.service_charge = service_total
    record.total_charge = (room_charge + service_total).quantize(CENT)
    record.save(update_fields=["service_charge", "total_charge"])


@role_required("receptionist", "admin")
def service_register(request):
    """前台：给在住客人登记增值服务，并查看最近登记记录。"""
    if request.method == "POST":
        return _submit_service_register(request)

    selected_id = request.GET.get("record_id")
    selected = CheckInRecord.objects.filter(pk=selected_id).first() if selected_id else None
    selected_summary = _charge_summary(selected) if selected else None

    recent_orders = (
        ServiceOrder.objects.select_related(
            "service_item", "check_in_record", "check_in_record__reservation",
            "check_in_record__reservation__room", "check_in_record__reservation__customer",
        )
        .order_by("-ordered_at", "-id")[:RECENT_LIMIT]
    )

    return render(
        request,
        "reception/service_register.html",
        {
            "records": _in_house_records()[:IN_HOUSE_LIMIT],
            "items": ServiceItem.objects.filter(is_active=True).order_by("code"),
            "selected": selected,
            "selected_summary": selected_summary,
            "recent_orders": recent_orders,
            "today": None,
        },
    )


def _submit_service_register(request):
    record = CheckInRecord.objects.filter(pk=(request.POST.get("record_id") or 0)).first()
    if record is None:
        messages.error(request, "请选择在住客人。")
        return redirect("core:service_register")
    if record.actual_checkout_at is not None or record.reservation.status != "checked_in":
        messages.error(request, "该客人已退房，不能再登记增值服务。")
        return redirect("core:service_register")

    item_ids = request.POST.getlist("item_id")
    quantities = request.POST.getlist("quantity")
    # 行数不限；同一个服务项目选了多行时合并数量（避免重复明细）
    merged: dict[int, int] = {}
    for raw_id, raw_qty in zip(item_ids, quantities):
        if not (raw_id or "").strip():
            continue
        try:
            item_id = int(raw_id)
            qty = int((raw_qty or "").strip() or "0")
        except (TypeError, ValueError):
            return _register_error(request, record, "服务数量请填写正整数。")
        if qty <= 0:
            return _register_error(request, record, "服务数量请填写正整数。")
        if qty > 99:
            return _register_error(request, record, "单项服务一次最多登记 99 份。")
        merged[item_id] = merged.get(item_id, 0) + qty

    picked: list[tuple[int, int]] = list(merged.items())
    if not picked:
        return _register_error(request, record, "请至少选择一项服务并填写数量。")
    over = [pk for pk, qty in picked if qty > 99]
    if over:
        return _register_error(request, record, "单项服务一次最多登记 99 份。")

    items = {item.pk: item for item in ServiceItem.objects.filter(pk__in=[pk for pk, _ in picked])}
    missing = [pk for pk, _ in picked if pk not in items]
    if missing:
        return _register_error(request, record, "选择的服务项目已下架或不存在，请刷新页面后重试。")
    inactive = [item.name for item in items.values() if not item.is_active]
    if inactive:
        return _register_error(
            request, record, "服务项目「%s」已下架，不能登记。" % "、".join(inactive),
        )

    try:
        with transaction.atomic():
            for item_id, qty in picked:
                ServiceOrder.objects.create(
                    check_in_record=record,
                    service_item=items[item_id],
                    quantity=qty,
                    unit_price=items[item_id].price,
                )
            _sync_charges(record)
    except IntegrityError:
        return _register_error(request, record, "登记失败：数据校验未通过，请重试。")

    record.refresh_from_db()
    names = "、".join("%s×%d" % (items[pk].name, qty) for pk, qty in picked)
    messages.success(
        request,
        "已为 %s（%s）登记：%s；本单服务费合计 %.2f 元。"
        % (
            record.guest_name,
            record.reservation.room.room_no,
            names,
            Decimal(str(record.service_charge)),
        ),
    )
    return redirect("%s?record_id=%d" % ("/reception/services/", record.pk))


def _register_error(request, record: CheckInRecord, text: str):
    messages.error(request, text)
    return redirect("%s?record_id=%d" % ("/reception/services/", record.pk))


@role_required("receptionist", "admin")
def service_record_list(request):
    """全部服务消费记录（可按房号 / 客人 / 日期筛选）。"""
    keyword = (request.GET.get("keyword") or "").strip()
    orders = ServiceOrder.objects.select_related(
        "service_item", "check_in_record", "check_in_record__reservation",
        "check_in_record__reservation__room", "check_in_record__reservation__customer",
    )
    if keyword:
        orders = orders.filter(
            Q(check_in_record__guest_name__icontains=keyword)
            | Q(check_in_record__guest_phone__icontains=keyword)
            | Q(check_in_record__reservation__room__room_no__icontains=keyword)
            | Q(service_item__name__icontains=keyword)
        )
    orders = orders.order_by("-ordered_at", "-id")

    total = orders.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return render(
        request,
        "reception/service_record_list.html",
        {"orders": orders[:500], "keyword": keyword, "total": total, "count": orders.count()},
    )
