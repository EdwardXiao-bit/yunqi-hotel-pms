"""错误页视图（E1–E3）。

禁用 DEBUG 时，Django 用 ROOT_URLCONF 里的 handler403/404/500 渲染这些模板；
403 同时覆盖 CSRF 校验失败与 `role_required` 越权两种场景。
"""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render


def permission_denied(request, exception=None):
    if request.path.startswith("/api/"):  # 预留：本项目不写 JSON API
        return JsonResponse({"detail": "无访问权限"}, status=403)
    return render(request, "errors/403.html", {"exception": exception}, status=403)


def page_not_found(request, exception=None):
    return render(request, "errors/404.html", {"exception": exception}, status=404)


def server_error(request):
    return render(request, "errors/500.html", status=500)
