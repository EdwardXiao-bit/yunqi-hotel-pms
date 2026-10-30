"""根路由：业务页面全部挂在 core 应用下（见 docs/页面约定.md §2）。"""
from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
]

# 关闭 DEBUG 时由 Django 调用（templates/errors/*.html）
handler403 = "core.views.errors.permission_denied"
handler404 = "core.views.errors.page_not_found"
handler500 = "core.views.errors.server_error"
