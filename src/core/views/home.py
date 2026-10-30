"""三端首页（P01 客户首页 / P05 前台工作台 / 管理概览）。

T4–T5 阶段先做“骨架 + 真实数据摘要”，不做业务写操作；各功能的完整页面
按 `docs/页面约定.md` 在 T6 起逐个落地。
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.utils import timezone

from ..decorators import role_required
from ..models import (
    AppUser,
    CheckInRecord,
    Customer,
    Payment,
    Reservation,
    Room,
    RoomBlock,
    RoomType,
    ServiceItem,
    ServiceOrder,
)
from ..roles import ROLE_CUSTOMER, ROLE_RECEPTIONIST


@login_required
def customer_home(request):
    """P01 客户首页：我的预订概览 + 最近预订。"""
    if request.user.role == ROLE_RECEPTIONIST:
        return redirect("core:reception_home")

    customer = Customer.objects.filter(user_id=request.user.pk).first()
    reservations = Reservation.objects.none()
    status_counts: dict[str, int] = {}
    if customer is not None:
        qs = Reservation.objects.filter(customer_id=customer.pk).select_related("room", "room__room_type")
        reservations = qs.order_by("-check_in_date", "-id")[:5]
        status_counts = {
            row["status"]: row["n"] for row in qs.values("status").annotate(n=Count("id"))
        }

    return render(
        request,
        "customer/index.html",
        {
            "customer": customer,
            "reservations": reservations,
            "status_counts": status_counts,
            "today": timezone.localdate(),
            "room_types": RoomType.objects.filter(is_active=True).order_by("base_price"),
        },
    )


@role_required(ROLE_RECEPTIONIST, "admin")
def reception_home(request):
    """P05 前台工作台：今日到店 / 在住 / 待清洁 / 待确认。"""
    today = timezone.localdate()
    arrivals = (
        Reservation.objects.filter(status="confirmed", check_in_date=today)
        .select_related("customer", "room", "room__room_type")
        .order_by("room__room_no")
    )
    in_house = (
        CheckInRecord.objects.filter(actual_checkout_at__isnull=True)
        .select_related("reservation", "reservation__room", "reservation__customer")
        .order_by("check_in_at")[:10]
    )
    room_status = {row["status"]: row["n"] for row in Room.objects.values("status").annotate(n=Count("id"))}
    cleaning_rooms = Room.objects.filter(status="cleaning").order_by("floor", "room_no")
    pending_count = Reservation.objects.filter(status="pending").count()
    upcoming_blocks = (
        RoomBlock.objects.filter(end_date__gte=today)
        .select_related("room")
        .order_by("start_date")[:5]
    )

    return render(
        request,
        "reception/dashboard.html",
        {
            "today": today,
            "arrivals": arrivals,
            "arrivals_count": arrivals.count(),
            "in_house": in_house,
            "in_house_count": CheckInRecord.objects.filter(actual_checkout_at__isnull=True).count(),
            "room_status": room_status,
            "room_total": Room.objects.count(),
            "cleaning_rooms": cleaning_rooms,
            "pending_count": pending_count,
            "upcoming_blocks": upcoming_blocks,
        },
    )


@role_required("admin")
def manage_home(request):
    """管理概览：13 张表行数 + 本月关键指标 + 数据库版本（原始 SQL 示例）。"""
    today = timezone.localdate()
    month_start = today.replace(day=1)

    table_counts = [
        ("账号 app_user", "app_user", "fas fa-user-shield", AppUser),
        ("客户 customer", "customer", "fas fa-users", Customer),
        ("房型 room_type", "room_type", "fas fa-bed", RoomType),
        ("房间 room", "room", "fas fa-door-open", Room),
        ("维修/停用 room_block", "room_block", "fas fa-tools", RoomBlock),
        ("预订 reservation", "reservation", "fas fa-calendar-check", Reservation),
        ("入住 check_in_record", "check_in_record", "fas fa-key", CheckInRecord),
        ("支付 payment", "payment", "fas fa-money-bill-wave", Payment),
        ("增值服务 service_item", "service_item", "fas fa-concierge-bell", ServiceItem),
        ("服务明细 service_order", "service_order", "fas fa-receipt", ServiceOrder),
    ]
    counts = [(label, model.objects.count(), icon) for label, _table, icon, model in table_counts]

    # 本月指标：手写 SQL（报告第 4 章要贴真实执行的语句）
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'checked_in')          AS in_house,
                COUNT(*) FILTER (WHERE status = 'pending')             AS pending,
                COUNT(*) FILTER (WHERE check_in_date >= %s)            AS this_month_arrivals
            FROM reservation
            """,
            [month_start],
        )
        row = cursor.fetchone()
        if connection.vendor == "postgresql":
            cursor.execute("SELECT current_database(), current_user, version()")
            db_name, db_user, db_version = cursor.fetchone()
            db_info = {"name": db_name, "user": db_user, "version": db_version.split(",")[0]}
        else:
            # 离线校验模式（tools/smoke_web.py）用的是 sqlite，没有这些 PG 函数
            db_info = {"name": str(connection.settings_dict.get("NAME")), "user": "-", "version": connection.vendor}

    metrics = {"in_house": row[0], "pending": row[1], "this_month_arrivals": row[2]}

    occupancy = (
        Room.objects.aggregate(
            total=Count("id"),
            available=Count("id", filter=Q(status="available")),
            blocked=Count("id", filter=Q(status__in=["maintenance", "disabled"])),
        )
    )

    return render(
        request,
        "manage/index.html",
        {
            "counts": counts,
            "metrics": metrics,
            "db_info": db_info,
            "occupancy": occupancy,
            "today": today,
        },
    )
