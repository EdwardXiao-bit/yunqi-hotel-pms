"""管理区：F01 房型与价格维护（P10）+ 客户与账号一览（P13）。

页面契约见 `docs/页面约定.md`：
- P10 `/manage/room-types/`、`/manage/room-types/new/`、`/manage/room-types/<pk>/edit/`
- P13 `/manage/customers/`（只读）

设计要点（与 `AGENTS.md` §4.1/§4.2 一致）：
- DDL 唯一事实源是 `sql/` 脚本，这里只做“行级维护”，不建表、不跑 migrate。
- 价格方案区间是**闭区间** `[valid_from, valid_to]`（`daterange(..., '[]')`），
  重叠由数据库 `ex_rate_plan_no_overlap`（23P01）兜底；离线 sqlite 模式没有该约束，
  所以视图层先做一次应用级预检查，两种模式行为一致。
- 房型删除受 `room.room_type_id` / `reservation.room_id` 的 RESTRICT 保护（E08），
  应用层先查引用并提示“改为停用”，仍抛 IntegrityError 时再映射中文。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.decorators import role_required
from core.models import (
    BED_TYPE_CHOICES,
    AppUser,
    Customer,
    RatePlan,
    Reservation,
    Room,
    RoomType,
)

BED_TYPE_LABELS = dict(BED_TYPE_CHOICES)
PAGE_SIZE = 20
MAX_CAPACITY = 8


# ---------------------------------------------------------------- 通用小工具

def _money(value) -> Decimal | None:
    """把 '688' / '688.00' 解析成两位小数；非法返回 None。"""
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if amount < 0:
        return None
    return amount.quantize(Decimal("0.01"))


def _try_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _as_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _back_to_list() -> redirect:
    return redirect("core:room_type_list")


def _form_values(room_type: RoomType | None, posted: dict | None = None) -> dict:
    """表单回显值：POST 的原值优先，其次库里的值，最后空。全部转成字符串/布尔。"""
    posted = posted or {}

    def pick(key: str, default="") -> str:
        value = posted.get(key)
        if value not in (None, ""):
            return str(value)
        value = getattr(room_type, key, None) if room_type is not None else None
        return default if value is None else str(value)

    if posted and "is_active" in posted:
        is_active = bool(posted.get("is_active"))
    else:
        is_active = room_type.is_active if room_type is not None else True

    return {
        "name": pick("name"),
        "bed_type": pick("bed_type"),
        "capacity": pick("capacity", "2"),
        "base_price": pick("base_price"),
        "area": pick("area"),
        "description": pick("description"),
        "is_active": is_active,
    }


# ---------------------------------------------------------------- 房型列表（P10）

@role_required("admin")
def room_type_list(request):
    """房型列表：房型 / 房间数 / 价格方案数 / 在售状态 + 停用与删除动作。"""
    if request.method == "POST":
        return _handle_list_action(request)

    room_types = list(
        RoomType.objects.annotate(
            room_count=Count("rooms", distinct=True),
            plan_count=Count("rate_plans", distinct=True),
        ).order_by("id")
    )
    # 在售房型里再单独统计“可售房间数”，看板口径与 F03 一致（维修/停用不算）
    sellable = dict(
        Room.objects.filter(status="available")
        .values_list("room_type_id")
        .annotate(total=Count("id"))
        .values_list("room_type_id", "total")
    )
    for room_type in room_types:
        room_type.sellable_count = sellable.get(room_type.id, 0)

    summary = {
        "room_types": len(room_types),
        "active": sum(1 for item in room_types if item.is_active),
        "plans": RatePlan.objects.count(),
        "rooms": Room.objects.count(),
    }
    return render(
        request,
        "manage/room_type_list.html",
        {"room_types": room_types, "summary": summary, "today": date.today()},
    )


def _handle_list_action(request):
    """列表页的 POST：启用/停用房型、删除房型。"""
    action = (request.POST.get("action") or "").strip()
    room_type = get_object_or_404(RoomType, pk=_as_int(request.POST.get("room_type_id")))

    if action == "toggle":
        room_type.is_active = not room_type.is_active
        room_type.save(update_fields=["is_active", "updated_at"])
        state = "重新上架" if room_type.is_active else "停用"
        messages.success(request, f"房型「{room_type.name}」已{state}。")
        return _back_to_list()

    if action == "delete":
        blockers = _deletion_blockers(room_type)
        if blockers:
            messages.error(request, f"房型「{room_type.name}」{blockers}，不能删除；请改为停用。")
            return _back_to_list()
        try:
            room_type.delete()
        except IntegrityError:
            # 并发或未预见的引用：数据库 RESTRICT 兜底
            messages.error(
                request,
                f"房型「{room_type.name}」仍被房间或预订引用（数据库 RESTRICT 拒绝删除），请改为停用。",
            )
            return _back_to_list()
        messages.success(request, f"房型「{room_type.name}」已删除。")
        return _back_to_list()

    messages.warning(request, "未知操作，未做任何修改。")
    return _back_to_list()


def _deletion_blockers(room_type: RoomType) -> str:
    """返回删除受阻的中文说明；无引用返回空串。"""
    room_count = Room.objects.filter(room_type_id=room_type.id).count()
    if room_count:
        return f"下还有 {room_count} 间房间"
    plan_count = RatePlan.objects.filter(room_type_id=room_type.id).count()
    if plan_count:
        return f"下还有 {plan_count} 条价格方案（先删方案才能删房型）"
    return ""


# ---------------------------------------------------------------- 房型编辑（P10）

@role_required("admin")
def room_type_form(request, pk: int | None = None):
    """新建 / 编辑房型；编辑页同时维护该房型的价格方案（闭区间，重叠即拒）。"""
    room_type = None
    if pk is not None:
        room_type = get_object_or_404(RoomType, pk=pk)

    if request.method == "POST":
        action = (request.POST.get("action") or "save").strip()
        if action == "save":
            return _save_room_type(request, room_type)
        if room_type is None:
            return _back_to_list()
        if action == "add_plan":
            return _add_rate_plan(request, room_type)
        if action == "delete_plan":
            return _delete_rate_plan(request, room_type)
        if action == "delete":
            return _delete_room_type(request, room_type)
        messages.warning(request, "未知操作，未做任何修改。")
        return redirect(request.path)

    plans = []
    if room_type is not None:
        plans = list(RatePlan.objects.filter(room_type_id=room_type.id).order_by("valid_from"))

    return render(
        request,
        "manage/room_type_form.html",
        {
            "room_type": room_type,
            "plans": plans,
            "bed_types": BED_TYPE_CHOICES,
            "today": date.today(),
            "form": _form_values(room_type),
        },
    )


def _render_form(request, room_type, *, posted=None, error=None):
    plans = []
    if room_type is not None:
        plans = list(RatePlan.objects.filter(room_type_id=room_type.id).order_by("valid_from"))
    if error:
        messages.error(request, error)
    return render(
        request,
        "manage/room_type_form.html",
        {
            "room_type": room_type,
            "plans": plans,
            "bed_types": BED_TYPE_CHOICES,
            "today": date.today(),
            "form": _form_values(room_type, posted),
        },
    )


def _read_room_type_form(post):
    """读表单并做字段级校验，返回 (data, errors)。"""
    data = {
        "name": (post.get("name") or "").strip(),
        "bed_type": (post.get("bed_type") or "").strip(),
        "capacity": (post.get("capacity") or "").strip(),
        "base_price": (post.get("base_price") or "").strip(),
        "area": (post.get("area") or "").strip(),
        "description": (post.get("description") or "").strip(),
        "is_active": post.get("is_active") == "on",
    }
    errors = []

    if not data["name"]:
        errors.append("房型名称不能为空。")
    elif len(data["name"]) > 50:
        errors.append("房型名称不能超过 50 个字。")

    if data["bed_type"] not in BED_TYPE_LABELS:
        errors.append("床型必须是：" + "、".join(BED_TYPE_LABELS.values()) + "之一。")

    capacity = _as_int(data["capacity"])
    if capacity is None or not 1 <= capacity <= MAX_CAPACITY:
        errors.append(f"可住人数必须是 1–{MAX_CAPACITY} 之间的整数。")
    else:
        data["capacity"] = capacity

    price = _money(data["base_price"])
    if price is None:
        errors.append("标准价必须是 ≥ 0 的数字（如 688.00）。")
    else:
        data["base_price"] = price

    if data["area"]:
        try:
            area = Decimal(data["area"]).quantize(Decimal("0.1"))
        except (InvalidOperation, ValueError):
            errors.append("面积必须是数字（如 28.0），可留空。")
        else:
            if area < 0:
                errors.append("面积不能为负数。")
            data["area"] = area
    else:
        data["area"] = None

    if len(data["description"]) > 200:
        errors.append("简介不能超过 200 个字。")

    return data, errors


def _save_room_type(request, room_type: RoomType | None):
    data, errors = _read_room_type_form(request.POST)

    if not errors:
        duplicate = RoomType.objects.filter(name=data["name"])
        if room_type is not None:
            duplicate = duplicate.exclude(pk=room_type.id)
        if duplicate.exists():
            errors.append(f"房型名称「{data['name']}」已存在，请换一个名称。")

    if errors:
        return _render_form(request, room_type, posted=data, error="；".join(errors))

    if room_type is None:
        room_type = RoomType.objects.create(
            name=data["name"],
            bed_type=data["bed_type"],
            area=data["area"],
            capacity=data["capacity"],
            base_price=data["base_price"],
            description=data["description"] or None,
            is_active=data["is_active"],
        )
        messages.success(request, f"房型「{room_type.name}」已创建，可继续为它添加价格方案。")
    else:
        room_type.name = data["name"]
        room_type.bed_type = data["bed_type"]
        room_type.area = data["area"]
        room_type.capacity = data["capacity"]
        room_type.base_price = data["base_price"]
        room_type.description = data["description"] or None
        room_type.is_active = data["is_active"]
        room_type.save()
        messages.success(request, f"房型「{room_type.name}」已保存。")

    return redirect("core:room_type_edit", pk=room_type.pk)


def _add_rate_plan(request, room_type: RoomType):
    name = (request.POST.get("plan_name") or "").strip()
    price = _money(request.POST.get("price"))
    valid_from = _try_date(request.POST.get("valid_from"))
    valid_to = _try_date(request.POST.get("valid_to"))

    errors = []
    if not valid_from or not valid_to:
        errors.append("价格方案的生效起止日期必须填写（格式 YYYY-MM-DD）。")
    elif valid_to < valid_from:
        errors.append("生效止日期不能早于生效起日期。")
    if price is None:
        errors.append("价格必须是 ≥ 0 的数字（如 888.00）。")
    if len(name) > 50:
        errors.append("方案名称不能超过 50 个字。")

    # 闭区间重叠预检查（与数据库 EXCLUDE 同口径）；sqlite 模式没有该约束，靠这一层
    if not errors:
        clash = _overlapping_plan(room_type.id, valid_from, valid_to)
        if clash is not None:
            errors.append(
                f"该房型在 {clash.valid_from} 至 {clash.valid_to} 已有价格方案"
                f"（{clash.name or '未命名'} · {clash.price} 元/晚），区间不能重叠。"
            )

    if errors:
        return _render_form(request, room_type, posted={}, error="；".join(errors))

    plan = RatePlan.objects.create(
        room_type_id=room_type.id,
        name=name or None,
        price=price,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    messages.success(
        request,
        f"已添加价格方案：{plan.valid_from} 至 {plan.valid_to} · {plan.price} 元/晚。"
        "注意：已确认订单的逐日价格已在 `reservation_price` 快照，改价不影响历史订单。",
    )
    return redirect("core:room_type_edit", pk=room_type.pk)


def _overlapping_plan(room_type_id: int, valid_from: date, valid_to: date) -> RatePlan | None:
    """闭区间重叠：existing.valid_from <= to AND existing.valid_to >= from。"""
    return (
        RatePlan.objects.filter(
            room_type_id=room_type_id,
            valid_from__lte=valid_to,
            valid_to__gte=valid_from,
        )
        .order_by("valid_from")
        .first()
    )


def _delete_rate_plan(request, room_type: RoomType):
    plan = get_object_or_404(RatePlan, pk=_as_int(request.POST.get("plan_id")), room_type_id=room_type.id)
    plan.delete()
    messages.success(request, f"价格方案（{plan.valid_from} 至 {plan.valid_to}）已删除。")
    return redirect("core:room_type_edit", pk=room_type.pk)


def _delete_room_type(request, room_type: RoomType):
    blockers = _deletion_blockers(room_type)
    if blockers:
        return _render_form(
            request, room_type, error=f"房型「{room_type.name}」{blockers}，不能删除；请改为停用。"
        )
    try:
        with transaction.atomic():
            room_type.delete()
    except IntegrityError:
        return _render_form(
            request,
            room_type,
            error=f"房型「{room_type.name}」仍被其他数据引用（数据库 RESTRICT 拒绝删除），请改为停用。",
        )
    messages.success(request, f"房型「{room_type.name}」已删除。")
    return _back_to_list()


# ---------------------------------------------------------------- 客户与账号一览（P13）

@role_required("admin")
def customer_list(request):
    """客户与账号一览（只读）：支持按姓名/手机/账号搜索 + 服务端分页。"""
    keyword = (request.GET.get("keyword") or "").strip()
    role = (request.GET.get("role") or "").strip()

    customers = Customer.objects.select_related("user").annotate(
        reservation_count=Count("reservations", distinct=True),
        stay_total=Sum(
            "reservations__total_amount",
            filter=Q(reservations__status__in=["checked_in", "checked_out"]),
        ),
    )
    if keyword:
        customers = customers.filter(
            Q(name__icontains=keyword)
            | Q(phone__icontains=keyword)
            | Q(user__username__icontains=keyword)
        )
    if role:
        if role == "walkin":
            customers = customers.filter(user__isnull=True)
        elif role in {"customer", "receptionist", "admin"}:
            customers = customers.filter(user__role=role)
    customers = customers.order_by("id")

    paginator = Paginator(customers, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    query = request.GET.copy()
    query.pop("page", None)
    querystring = query.urlencode()

    accounts = AppUser.objects.order_by("role", "id")
    counts = {
        "customers": Customer.objects.count(),
        "accounts": AppUser.objects.count(),
        "walkin": Customer.objects.filter(user__isnull=True).count(),
        "reservations": Reservation.objects.count(),
    }

    return render(
        request,
        "manage/customer_list.html",
        {
            "page": page,
            "customers": page.object_list,
            "paginator": paginator,
            "keyword": keyword,
            "role": role,
            "accounts": accounts,
            "counts": counts,
            "querystring": querystring,
            "role_labels": dict(AppUser._meta.get_field("role").choices),
        },
    )
