"""视图包：按页面分区拆文件，`urls.py` 从这里导入。"""
from .auth import login_view, logout_view
from .board import room_board
from .checkin import checkin_new, walkin_checkin
from .checkout import checkout_detail
from .errors import page_not_found, permission_denied, server_error
from .home import customer_home, manage_home, reception_home
from .manage import customer_list, room_form, room_list, room_type_form, room_type_list
from .reports import reports, reservation_export, reservation_list
from .reservations import (
    my_reservation_cancel,
    my_reservation_detail,
    my_reservations,
    reception_reservations,
    reservation_create,
)
from .rooms import available_rooms
from .services import (
    service_item_form,
    service_item_list,
    service_record_list,
    service_register,
)

__all__ = [
    "service_item_list",
    "service_item_form",
    "service_register",
    "service_record_list",
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
    "checkout_detail",
    "room_board",
    "room_type_list",
    "room_type_form",
    "customer_list",
    "reports",
    "reservation_list",
    "reservation_export",
    "permission_denied",
    "page_not_found",
    "server_error",
]
