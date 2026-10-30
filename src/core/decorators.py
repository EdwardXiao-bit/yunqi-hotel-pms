"""权限装饰器：按 `app_user.role` 放行，越权统一抛 PermissionDenied → 403 页面。"""
from __future__ import annotations

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def role_required(*roles: str):
    """要求登录且角色在 `roles` 内；未登录先跳登录页，角色不符抛 403。

    用法::

        @role_required("receptionist", "admin")
        def view(request): ...
    """

    allowed = frozenset(roles)

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if user.role not in allowed:
                raise PermissionDenied(
                    f"当前角色（{user.get_role_display() if hasattr(user, 'get_role_display') else user.role}）"
                    f"无权访问该页面"
                )
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def is_admin(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "role", None) == "admin")


def is_reception(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "role", None) == "receptionist")
