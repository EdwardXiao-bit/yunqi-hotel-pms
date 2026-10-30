"""视图包：按页面分区拆文件，`urls.py` 从这里导入。"""
from .auth import login_view, logout_view
from .errors import page_not_found, permission_denied, server_error
from .home import customer_home, manage_home, reception_home
from .rooms import available_rooms

__all__ = [
    "login_view",
    "logout_view",
    "customer_home",
    "reception_home",
    "manage_home",
    "available_rooms",
    "permission_denied",
    "page_not_found",
    "server_error",
]
