"""自定义认证后端：直接查 `app_user` 表，不做 Group/Permission。

密码哈希沿用 Django 默认 hasher（种子数据用 `make_password()` 生成，pbkdf2_sha256），
因此 `check_password()` 可直接校验；若将来把迭代次数调高，登录时会自动 rehash。
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend


class AppUserBackend(BaseBackend):
    """按 `username` + 密码校验；角色权限交给 `role_required` 装饰器。"""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or not password:
            return None
        try:
            user = UserModel._default_manager.get_by_natural_key(username)
        except UserModel.DoesNotExist:
            # 与“密码错误”耗时对齐，避免通过响应时间枚举账号
            UserModel().set_password(password)
            return None
        if not user.is_active:
            return None
        if not user.check_password(password):
            return None
        return user

    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            return UserModel._default_manager.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None

    # 不使用 Django 权限系统，但保留接口以便将来扩展
    def has_perm(self, user_obj, perm, obj=None) -> bool:
        return bool(getattr(user_obj, "role", None) == "admin")

    def has_module_perms(self, user_obj, app_label) -> bool:
        return bool(getattr(user_obj, "role", None) == "admin")
