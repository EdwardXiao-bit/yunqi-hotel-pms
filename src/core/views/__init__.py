"""视图包：按页面分区拆文件，`urls.py` 从这里导入。"""
from .auth import login_view, logout_view
from .checkin import checkin_new, walkin_checkin
from .errors import page_not_found, permission_denied, server_error
from .home import customer_home, manage_home, reception_home
from .reservations import (
    my_reservation_cancel,
    my_reservation_detail,
    my_reservations,
    reception_reservations,
    reservation_create,
)
from .rooms import available_rooms

__all__ = [
    "login_view",
    "logout_view",
    "customer_home",
    "reception_home",
    "manage_home",
    "available_rooms",
    "reservation_create",
    "my_reservations",
    "my_reservation_detail",
    "my_reservation_cancel",
    "reception_reservations",
    "checkin_new",
    "walkin_checkin",
    "permission_denied",
    "page_not_found",
    "server_error",
]
