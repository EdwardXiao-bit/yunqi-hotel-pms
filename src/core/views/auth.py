"""登录 / 登出视图（P00）。

登录成功后按 `role` 跳对应首页；`next` 参数只允许站内相对路径（防开放重定向）。
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters

from ..forms import LoginForm
from ..roles import ROLE_HOME_URL_NAME

DEFAULT_HOME_URL_NAME = "core:customer_home"


def _safe_next(request) -> str | None:
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return None


@never_cache
@csrf_protect
@sensitive_post_parameters("password")
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_home_for(request.user))

    form = LoginForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
            if user is None:
                messages.error(request, "登录名或密码不正确，请重试。")
            elif not user.is_active:
                messages.error(request, "该账号已停用，请联系管理员。")
            else:
                login(request, user)
                messages.success(request, f"欢迎回来，{user.get_full_name()}（{user.role_label}）。")
                return redirect(_safe_next(request) or _home_for(user))
        else:
            messages.error(request, "请填写登录名与密码。")

    return render(
        request,
        "login.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


def logout_view(request):
    """登出。Django 5+ 要求 POST，导航栏用表单提交；GET 仅提示不执行。"""
    if request.method != "POST":
        return redirect(reverse("core:login"))
    name = request.user.get_full_name() if request.user.is_authenticated else "访客"
    logout(request)
    messages.info(request, f"{name} 已退出登录。")
    return redirect(reverse("core:login"))


def _home_for(user) -> str:
    name = ROLE_HOME_URL_NAME.get(getattr(user, "role", ""), DEFAULT_HOME_URL_NAME)
    return reverse(name)
