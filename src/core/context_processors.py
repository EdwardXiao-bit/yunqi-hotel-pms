"""模板全局变量：侧边栏导航 + 当前角色，避免每个视图都传一遍。"""
from __future__ import annotations

from .roles import ROLE_LABELS, visible_sections


def navigation(request) -> dict:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"nav_sections": [], "current_role_label": ""}
    role = getattr(user, "role", "")
    return {
        "nav_sections": visible_sections(role),
        "current_role_label": ROLE_LABELS.get(role, role),
    }
