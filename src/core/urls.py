"""core 应用路由。所有页面统一 `app_name = 'core'`，模板用 {% url 'core:xxx' %}。"""
from __future__ import annotations

from django.urls import path

from .views import auth, board, checkin, checkout, home, manage, reservations, rooms
from .views.reports import reports as reports_view
from .views.reports import reservation_export, reservation_list

app_name = "core"

urlpatterns = [
    # P00 登录 / 登出
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),
    # P01 客户首页
    path("", home.customer_home, name="customer_home"),
    # P02 可用房查询（F03）
    path("rooms/available/", rooms.available_rooms, name="available_rooms"),
    # P03 预订提交（F04）
    path("reservations/new/", reservations.reservation_create, name="reservation_create"),
    # P04 我的预订（F05）
    path("my/reservations/", reservations.my_reservations, name="my_reservations"),
    path("my/reservations/<int:pk>/", reservations.my_reservation_detail, name="my_reservation_detail"),
    path(
        "my/reservations/<int:pk>/cancel/",
        reservations.my_reservation_cancel,
        name="my_reservation_cancel",
    ),
    # P05 前台工作台
    path("reception/", home.reception_home, name="reception_home"),
    # P06 预订管理（F05）
    path("reception/reservations/", reservations.reception_reservations, name="reception_reservations"),
    # P07 入住与续住办理（F06）
    path("reception/checkin/new/", checkin.checkin_new, name="checkin_new"),
    path("reception/checkin/walkin/", checkin.walkin_checkin, name="walkin_checkin"),
    # P08 退房与结算（F07）
    path("reception/checkout/<int:pk>/", checkout.checkout_detail, name="checkout_detail"),
    path("reception/board/", board.room_board, name="room_board"),
    # 管理概览
    path("manage/", home.manage_home, name="manage_home"),
    # P10 房型与价格维护（F01）
    path("manage/room-types/", manage.room_type_list, name="room_type_list"),
    path("manage/room-types/new/", manage.room_type_form, name="room_type_new"),
    path("manage/room-types/<int:pk>/edit/", manage.room_type_form, name="room_type_edit"),
    # P13 客户与账号一览
    path("manage/customers/", manage.customer_list, name="customer_list"),
    # P14 房间维护（F02）
    path("manage/rooms/", manage.room_list, name="room_list"),
    path("manage/rooms/new/", manage.room_form, name="room_new"),
    path("manage/rooms/<int:pk>/edit/", manage.room_form, name="room_edit"),
    # P11 经营统计报表（F09）
    path("manage/reports/", reports_view, name="reports"),
    # P12 预订总览（F05 管理员视角，只读 + 导出）
    path("manage/reservations/", reservation_list, name="reservation_list"),
    path("manage/reservations/export/", reservation_export, name="reservation_export"),
]
