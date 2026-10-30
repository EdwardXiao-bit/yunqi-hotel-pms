"""core 应用路由。所有页面统一 `app_name = 'core'`，模板用 {% url 'core:xxx' %}。"""
from __future__ import annotations

from django.urls import path

from .views import auth, home, rooms

app_name = "core"

urlpatterns = [
    # P00 登录 / 登出
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),
    # P01 客户首页
    path("", home.customer_home, name="customer_home"),
    # P02 可用房查询（F03）
    path("rooms/available/", rooms.available_rooms, name="available_rooms"),
    # P05 前台工作台
    path("reception/", home.reception_home, name="reception_home"),
    # 管理概览
    path("manage/", home.manage_home, name="manage_home"),
]
