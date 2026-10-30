"""core 应用路由。所有页面统一 `app_name = 'core'`，模板用 {% url 'core:xxx' %}。"""
from __future__ import annotations

from django.urls import path

from .views import auth, home, reservations, rooms

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
    # 管理概览
    path("manage/", home.manage_home, name="manage_home"),
]
