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
    ORIENTATION_CHOICES,
    ROOM_STATUS_CHOICES,
    AppUser,
    Customer,
    RatePlan,
    Reservation,
    Room,
    RoomBlock,
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


# ---------------------------------------------------------------- 房间维护（P14，F02）

ROOM_STATUS_LABELS = dict(ROOM_STATUS_CHOICES)
ORIENTATION_LABELS = dict(ORIENTATION_CHOICES)
ROOM_STATUS_ORDER = [value for value, _label in ROOM_STATUS_CHOICES]
FLOOR_MIN, FLOOR_MAX = -2, 99


def _room_querystring(request) -> str:
    query = request.GET.copy()
    query.pop("page", None)
    return query.urlencode()


def _room_filter_values(request) -> dict:
    """筛选条件：房型 / 楼层 / 房态 / 房号关键字。"""
    room_type_raw = (request.GET.get("room_type_id") or "").strip()
    floor_raw = (request.GET.get("floor") or "").strip()
    status = (request.GET.get("status") or "").strip()
    keyword = (request.GET.get("keyword") or "").strip()
    return {
        "room_type_id": _as_int(room_type_raw),
        "floor": _as_int(floor_raw),
        "status": status if status in ROOM_STATUS_LABELS else "",
        "keyword": keyword,
    }


@role_required("admin")
def room_list(request):
    """房间维护：按房型/楼层/房态筛选，支持单间新增、批量新增、编辑与删除。"""
    if request.method == "POST":
        return _handle_room_action(request)

    filters = _room_filter_values(request)
    rooms = Room.objects.select_related("room_type")

    if filters["room_type_id"]:
        rooms = rooms.filter(room_type_id=filters["room_type_id"])
    if filters["floor"] is not None:
        rooms = rooms.filter(floor=filters["floor"])
    if filters["status"]:
        rooms = rooms.filter(status=filters["status"])
    if filters["keyword"]:
        rooms = rooms.filter(room_no__icontains=filters["keyword"])

    rooms = rooms.order_by("floor", "room_no")
    paginator = Paginator(rooms, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    all_rooms = Room.objects.all()
    summary = {
        "total": all_rooms.count(),
        "by_status": [
            {
                "value": value,
                "label": ROOM_STATUS_LABELS[value],
                "count": all_rooms.filter(status=value).count(),
            }
            for value in ROOM_STATUS_ORDER
        ],
        "room_types": RoomType.objects.filter(is_active=True).count(),
    }

    return render(
        request,
        "manage/room_list.html",
        {
            "page": page,
            "rooms": page.object_list,
            "paginator": paginator,
            "querystring": _room_querystring(request),
            "filters": filters,
            "room_types": RoomType.objects.order_by("name"),
            "floors": (
                Room.objects.order_by("floor")
                .values_list("floor", flat=True)
                .distinct()
            ),
            "status_options": [{"value": v, "label": ROOM_STATUS_LABELS[v]} for v in ROOM_STATUS_ORDER],
            "orientation_options": [
                {"value": value, "label": label} for value, label in ORIENTATION_CHOICES
            ],
            "orientation_labels": ORIENTATION_LABELS,
            "room_status_labels": ROOM_STATUS_LABELS,
            "summary": summary,
            "today": date.today(),
        },
    )


def _handle_room_action(request):
    action = (request.POST.get("action") or "").strip()
    if action == "bulk":
        return _room_bulk_create(request)
    if action == "delete":
        return _room_delete(request)
    messages.error(request, "未识别的操作。")
    return redirect("core:room_list")


def _parse_room_nos(raw: str) -> list[str]:
    """把「801,802 803；804」这类输入拆成房号列表（去重保序）。"""
    cleaned = raw.replace("，", ",").replace("、", ",").replace("；", ",").replace(";", ",")
    for sep in ("\n", "\r", "\t", " "):
        cleaned = cleaned.replace(sep, ",")
    seen: list[str] = []
    for item in cleaned.split(","):
        room_no = item.strip()
        if room_no and room_no not in seen:
            seen.append(room_no)
    return seen


def _room_bulk_create(request):
    """批量新增房间：同房型、同楼层、同朝向一次建多间。"""
    room_type_id = _as_int(request.POST.get("room_type_id"))
    floor = _as_int(request.POST.get("floor"))
    orientation = (request.POST.get("orientation") or "").strip() or None
    status = (request.POST.get("status") or "available").strip()
    room_nos = _parse_room_nos(request.POST.get("room_nos") or "")

    room_type = RoomType.objects.filter(pk=room_type_id).first() if room_type_id else None
    if room_type is None:
        messages.error(request, "请选择房型。")
        return redirect("core:room_list")
    if not room_nos:
        messages.error(request, "请填写房号，多个房号用逗号、空格或换行分隔。")
        return redirect("core:room_list")
    if floor is None or not (FLOOR_MIN <= floor <= FLOOR_MAX):
        messages.error(request, "楼层请填写 %d ~ %d 之间的整数。" % (FLOOR_MIN, FLOOR_MAX))
        return redirect("core:room_list")
    if orientation is not None and orientation not in ORIENTATION_LABELS:
        orientation = None
    if status not in ROOM_STATUS_LABELS:
        status = "available"
    if len(room_nos) > 50:
        messages.error(request, "一次最多批量新增 50 间。")
        return redirect("core:room_list")

    created: list[str] = []
    skipped: list[str] = []
    try:
        with transaction.atomic():
            for room_no in room_nos:
                if len(room_no) > 10:
                    skipped.append(room_no)
                    continue
                if Room.objects.filter(room_no=room_no).exists():
                    skipped.append(room_no)
                    continue
                Room.objects.create(
                    room_type=room_type,
                    room_no=room_no,
                    floor=floor,
                    orientation=orientation,
                    status=status,
                    remark=None,
                )
                created.append(room_no)
    except IntegrityError:
        messages.error(request, "批量新增失败：房号有重复，请检查后重试。")
        return redirect("core:room_list")

    if created:
        messages.success(
            request,
            "已新增 %d 间房：%s（房型 %s，%d 层）。" % (
                len(created), "、".join(created), room_type.name, floor,
            ),
        )
    if skipped:
        messages.warning(request, "以下房号已存在或超长，已跳过：%s。" % "、".join(skipped))
    if not created and not skipped:
        messages.error(request, "没有可新增的房号。")
    return redirect("core:room_list")


@role_required("admin")
def room_form(request, pk: int | None = None):
    """单间房间的新增与编辑。"""
    room = get_object_or_404(Room, pk=pk) if pk else None
    if request.method == "POST":
        return _save_room(request, room)

    return render(
        request,
        "manage/room_form.html",
        {
            "room": room,
            "form": _room_form_values(room),
            "room_types": RoomType.objects.order_by("name"),
            "orientation_options": [
                {"value": value, "label": label} for value, label in ORIENTATION_CHOICES
            ],
            "status_options": [{"value": v, "label": ROOM_STATUS_LABELS[v]} for v in ROOM_STATUS_ORDER],
            "floor_range": (FLOOR_MIN, FLOOR_MAX),
        },
    )


def _room_form_values(room: Room | None, posted: dict | None = None) -> dict:
    posted = posted or {}

    def pick(key: str, default: str = "") -> str:
        if key in posted:
            return posted.get(key) or ""
        if room is None:
            return default
        value = getattr(room, key)
        return "" if value is None else str(value)

    return {
        "room_no": pick("room_no"),
        "room_type_id": pick("room_type_id", str(room.room_type_id) if room else ""),
        "floor": pick("floor", ""),
        "orientation": pick("orientation"),
        "status": pick("status", "available") if room is None else pick("status"),
        "remark": pick("remark"),
    }


def _save_room(request, room: Room | None):
    post = request.POST
    values = _room_form_values(room, post)
    room_no = values["room_no"].strip()
    room_type_id = _as_int(values["room_type_id"])
    floor = _as_int(values["floor"])
    orientation = values["orientation"].strip() or None
    status = values["status"].strip()
    remark = values["remark"].strip()

    errors: list[str] = []
    if not room_no:
        errors.append("请填写房号。")
    elif len(room_no) > 10:
        errors.append("房号最多 10 个字符。")
    else:
        duplicated = Room.objects.filter(room_no=room_no)
        if room is not None:
            duplicated = duplicated.exclude(pk=room.pk)
        if duplicated.exists():
            errors.append("房号 %s 已存在，请换一个。" % room_no)
    room_type = RoomType.objects.filter(pk=room_type_id).first() if room_type_id else None
    if room_type is None:
        errors.append("请选择房型。")
    if floor is None or not (FLOOR_MIN <= floor <= FLOOR_MAX):
        errors.append("楼层请填写 %d ~ %d 之间的整数。" % (FLOOR_MIN, FLOOR_MAX))
    if orientation is not None and orientation not in ORIENTATION_LABELS:
        errors.append("朝向请从下拉选项中选择。")
    if status not in ROOM_STATUS_LABELS:
        errors.append("房态请从下拉选项中选择。")
    if len(remark) > 200:
        errors.append("备注最多 200 个字符。")

    if errors:
        for item in errors:
            messages.error(request, item)
        return render(
            request,
            "manage/room_form.html",
            {
                "room": room,
                "form": values,
                "room_types": RoomType.objects.order_by("name"),
                "orientation_options": [
                    {"value": value, "label": label} for value, label in ORIENTATION_CHOICES
                ],
                "status_options": [
                    {"value": v, "label": ROOM_STATUS_LABELS[v]} for v in ROOM_STATUS_ORDER
                ],
                "floor_range": (FLOOR_MIN, FLOOR_MAX),
            },
        )

    if room is None:
        room = Room(
            room_no=room_no,
            room_type=room_type,
            floor=floor,
            orientation=orientation,
            status=status,
            remark=remark or None,
        )
        action_label = "新增"
    else:
        room.room_no = room_no
        room.room_type = room_type
        room.floor = floor
        room.orientation = orientation
        room.status = status
        room.remark = remark or None
        action_label = "保存"

    try:
        with transaction.atomic():
            _set_room_operator(request.user)
            room.save()
    except IntegrityError as exc:
        messages.error(request, _translate_room_error(exc, room_no))
        return redirect("core:room_form", pk=room.pk) if room.pk else redirect("core:room_form_new")

    messages.success(
        request,
        "房间 %s 已%s（%s · %d 层 · %s）。" % (
            room.room_no, action_label, room.room_type.name, room.floor,
            ROOM_STATUS_LABELS.get(room.status, room.status),
        ),
    )
    return redirect("core:room_list")


def _set_room_operator(user) -> None:
    """把当前操作人写进事务级会话变量，供 trg_room_status_log 记录 changed_by。"""
    if connection.vendor != "postgresql" or not getattr(user, "is_authenticated", False):
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(user.pk)])


def _translate_room_error(exc: Exception, room_no: str) -> str:
    text = str(exc)
    if "uq_room_room_no" in text or "room_no" in text:
        return "房号 %s 已存在，请换一个。" % room_no
    return "保存失败：数据校验未通过，请检查房号与房型。"


def _room_delete(request):
    """删除房间：有预订/封禁记录时拒绝（改为停用）。"""
    room_id = _as_int(request.POST.get("room_id"))
    room = Room.objects.filter(pk=room_id).first()
    if room is None:
        messages.error(request, "房间不存在或已被删除。")
        return redirect("core:room_list")

    if Reservation.objects.filter(room_id=room.pk).exists():
        messages.error(
            request,
            "房间 %s 已有预订记录，不能删除；如果不再使用，请把房态改为「停用」。"
            % room.room_no,
        )
        return redirect("core:room_list")
    if RoomBlock.objects.filter(room_id=room.pk).exists():
        messages.error(
            request,
            "房间 %s 有维修/停用登记，不能删除；请先结束这些登记，或把房态改为「停用」。"
            % room.room_no,
        )
        return redirect("core:room_list")

    try:
        with transaction.atomic():
            room.delete()
    except IntegrityError:
        messages.error(request, "房间 %s 仍被其他数据引用，不能删除。" % room.room_no)
        return redirect("core:room_list")

    messages.success(request, "房间 %s 已删除。" % room.room_no)
    return redirect("core:room_list")
