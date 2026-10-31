"""三角色定义、各角色登录后首页、侧边栏导航配置。

角色与权限（AGENTS.md §4.2 / docs/页面约定.md §2、§5）：
- customer     客户区：`/`、`/my/...`、`/rooms/...`、`/reservations/...`
- receptionist 前台区：`/reception/...`（`role_required('receptionist', 'admin')`）
- admin        管理区：`/manage/...`（`role_required('admin')`），同时全通
"""
from __future__ import annotations

from dataclasses import dataclass, field

ROLE_CUSTOMER = "customer"
ROLE_RECEPTIONIST = "receptionist"
ROLE_ADMIN = "admin"

ALL_ROLES = (ROLE_CUSTOMER, ROLE_RECEPTIONIST, ROLE_ADMIN)

ROLE_LABELS = {
    ROLE_CUSTOMER: "客户",
    ROLE_RECEPTIONIST: "前台工作人员",
    ROLE_ADMIN: "管理员",
}

# 登录后跳转的首页（URL name）
ROLE_HOME_URL_NAME = {
    ROLE_CUSTOMER: "core:customer_home",
    ROLE_RECEPTIONIST: "core:reception_home",
    ROLE_ADMIN: "core:manage_home",
}


@dataclass(frozen=True)
class NavItem:
    label: str
    url_name: str
    icon: str = "far fa-circle"
    roles: tuple[str, ...] = ALL_ROLES

    @property
    def name(self) -> str:
        """去掉命名空间后的 url name，供模板判断高亮项。"""
        return self.url_name.split(":")[-1]


@dataclass(frozen=True)
class NavSection:
    title: str
    roles: tuple[str, ...]
    items: tuple[NavItem, ...] = field(default_factory=tuple)


# T4–T5 阶段只挂已经落地的页面；T6 起按 docs/页面约定.md 往对应区块里加条目，
# 不用改模板与权限逻辑。
NAV_SECTIONS: tuple[NavSection, ...] = (
    NavSection(
        title="客户服务",
        roles=(ROLE_CUSTOMER, ROLE_ADMIN),
        items=(
            NavItem("我的首页", "core:customer_home", "fas fa-home"),
            NavItem("可用房查询", "core:available_rooms", "fas fa-door-open"),
            NavItem("我的预订", "core:my_reservations", "fas fa-list-alt"),
        ),
    ),
    NavSection(
        title="前台作业",
        roles=(ROLE_RECEPTIONIST, ROLE_ADMIN),
        items=(
            NavItem("前台工作台", "core:reception_home", "fas fa-concierge-bell"),
            NavItem("预订管理", "core:reception_reservations", "fas fa-clipboard-check"),
            NavItem("入住办理", "core:checkin_new", "fas fa-sign-in-alt"),
            NavItem("房态看板", "core:room_board", "fas fa-th"),
            NavItem("可用房查询", "core:available_rooms", "fas fa-door-open"),
        ),
    ),
    NavSection(
        title="系统管理",
        roles=(ROLE_ADMIN,),
        items=(
            NavItem("管理概览", "core:manage_home", "fas fa-tachometer-alt"),
            NavItem("房型与价格", "core:room_type_list", "fas fa-bed"),
            NavItem("客户一览", "core:customer_list", "fas fa-users"),
        ),
    ),
)


def visible_sections(role: str) -> list[NavSection]:
    """按角色筛出可见的导航区块。"""
    return [section for section in NAV_SECTIONS if role in section.roles]
