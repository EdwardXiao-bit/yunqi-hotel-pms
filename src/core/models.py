"""13 张业务表的 Django 模型映射。

**全部 `managed = False`**：表结构与约束由 `sql/00_database.sql` → `01_schema.sql` →
`02_constraints.sql` 唯一决定，Django 只负责读写，不生成 migration、不建表。

注意事项
--------
1. 生成列（`reservation.during` / `room_block.during` / `rate_plan.valid_during`）不映射，
   留给数据库；`service_order.amount` 用 `GeneratedField` 映射，只为“读”，不会被写。
2. 外键一律 `on_delete=DO_NOTHING`：删除策略（RESTRICT / CASCADE / SET NULL）已经在
   `sql/01_schema.sql` 用 `FOREIGN KEY ... ON DELETE` 表达，Django 不要另做一遍。
3. 列名以 `db_column` 显式钉死，避免以后改字段名把 SQL 里的列名改错。
"""
from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone

# ---------------------------------------------------------------- 枚举（与 CHECK 一致）

ROLE_CHOICES = [
    ("customer", "客户"),
    ("receptionist", "前台工作人员"),
    ("admin", "管理员"),
]

ROOM_STATUS_CHOICES = [
    ("available", "正常"),
    ("cleaning", "清洁中"),
    ("maintenance", "维修中"),
    ("disabled", "停用"),
]

RESERVATION_STATUS_CHOICES = [
    ("pending", "待确认"),
    ("confirmed", "已确认"),
    ("checked_in", "入住中"),
    ("checked_out", "已退房"),
    ("cancelled", "已取消"),
    ("no_show", "未到店"),
]

RESERVATION_SOURCE_CHOICES = [
    ("online", "线上"),
    ("phone", "电话"),
    ("walk_in", "散客到店"),
]

BED_TYPE_CHOICES = [
    ("single", "单床"),
    ("double", "大床"),
    ("twin", "双床"),
    ("king", "特大床"),
    ("family", "家庭房"),
    ("suite", "套房"),
]

ORIENTATION_CHOICES = [
    ("north", "朝北"),
    ("south", "朝南"),
    ("east", "朝东"),
    ("west", "朝西"),
]

BLOCK_TYPE_CHOICES = [
    ("maintenance", "维修"),
    ("disabled", "停用"),
]

PAYMENT_KIND_CHOICES = [
    ("deposit", "押金"),
    ("room_fee", "房费"),
    ("service_fee", "服务费"),
    ("refund", "退款"),
]

PAYMENT_METHOD_CHOICES = [
    ("cash", "现金"),
    ("card", "银行卡"),
    ("wechat", "微信"),
    ("alipay", "支付宝"),
]


class _BaseModel(models.Model):
    """所有业务表共用：主键 bigserial、created_at/updated_at 由数据库默认值与触发器维护。"""

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True, db_column="created_at")
    updated_at = models.DateTimeField("更新时间", auto_now=True, db_column="updated_at")

    class Meta:
        abstract = True


# ---------------------------------------------------------------- 1 app_user

class AppUserManager(BaseUserManager):
    def get_by_natural_key(self, username: str) -> "AppUser":
        return self.get(**{self.model.USERNAME_FIELD: username})


class AppUser(AbstractBaseUser):
    """账号表：三种角色共用一张表，用 `role` 列区分（AGENTS.md §4.2）。"""

    username = models.CharField("登录名", max_length=50, unique=True, db_column="username")
    display_name = models.CharField("显示名", max_length=50, db_column="display_name")
    role = models.CharField("角色", max_length=20, choices=ROLE_CHOICES, default="customer", db_column="role")
    phone = models.CharField("手机号", max_length=20, blank=True, null=True, db_column="phone")
    email = models.EmailField("邮箱", max_length=120, blank=True, null=True, db_column="email")
    is_active = models.BooleanField("是否启用", default=True, db_column="is_active")
    last_login = models.DateTimeField("最后登录", null=True, blank=True, db_column="last_login")
    created_at = models.DateTimeField("创建时间", auto_now_add=True, db_column="created_at")
    updated_at = models.DateTimeField("更新时间", auto_now=True, db_column="updated_at")

    objects = AppUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["display_name", "role"]

    class Meta:
        managed = False
        db_table = "app_user"
        verbose_name = verbose_name_plural = "账号"
        ordering = ["id"]

    # Django 会话/模板会用到的属性
    @property
    def is_staff(self) -> bool:
        return self.role == "admin"

    @property
    def is_superuser(self) -> bool:
        return self.role == "admin"

    @property
    def role_label(self) -> str:
        return dict(ROLE_CHOICES).get(self.role, self.role)

    def get_full_name(self) -> str:
        return self.display_name or self.username

    def get_short_name(self) -> str:
        return self.display_name or self.username

    def has_perm(self, perm: str, obj=None) -> bool:  # 不用 Django 权限体系
        return self.role == "admin"

    def has_module_perms(self, app_label: str) -> bool:
        return self.role == "admin"

    def __str__(self) -> str:
        return f"{self.display_name}({self.username})"


# ---------------------------------------------------------------- 2 customer

class Customer(_BaseModel):
    user = models.ForeignKey(
        AppUser, verbose_name="关联账号", null=True, blank=True,
        on_delete=models.DO_NOTHING, db_column="user_id", related_name="customers",
    )
    name = models.CharField("姓名", max_length=50, db_column="name")
    phone = models.CharField("手机号", max_length=20, unique=True, db_column="phone")
    id_card = models.CharField("身份证号", max_length=18, blank=True, null=True, db_column="id_card")
    email = models.EmailField("邮箱", max_length=120, blank=True, null=True, db_column="email")
    remark = models.CharField("备注", max_length=200, blank=True, null=True, db_column="remark")

    class Meta:
        managed = False
        db_table = "customer"
        verbose_name = verbose_name_plural = "客户"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.name}({self.phone})"


# ---------------------------------------------------------------- 3 room_type

class RoomType(_BaseModel):
    name = models.CharField("房型名称", max_length=50, unique=True, db_column="name")
    bed_type = models.CharField("床型", max_length=20, choices=BED_TYPE_CHOICES, db_column="bed_type")
    area = models.DecimalField("面积(㎡)", max_digits=5, decimal_places=1, blank=True, null=True, db_column="area")
    capacity = models.SmallIntegerField("可住人数", db_column="capacity")
    base_price = models.DecimalField("标准价(元)", max_digits=10, decimal_places=2, db_column="base_price")
    description = models.CharField("简介", max_length=200, blank=True, null=True, db_column="description")
    is_active = models.BooleanField("是否在售", default=True, db_column="is_active")

    class Meta:
        managed = False
        db_table = "room_type"
        verbose_name = verbose_name_plural = "房型"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------- 4 room

class Room(_BaseModel):
    room_type = models.ForeignKey(
        RoomType, verbose_name="房型", on_delete=models.DO_NOTHING,
        db_column="room_type_id", related_name="rooms",
    )
    room_no = models.CharField("房号", max_length=10, unique=True, db_column="room_no")
    floor = models.SmallIntegerField("楼层", db_column="floor")
    orientation = models.CharField(
        "朝向", max_length=10, choices=ORIENTATION_CHOICES, blank=True, null=True, db_column="orientation"
    )
    status = models.CharField(
        "房间状态", max_length=20, choices=ROOM_STATUS_CHOICES, default="available", db_column="status"
    )
    remark = models.CharField("备注", max_length=200, blank=True, null=True, db_column="remark")

    class Meta:
        managed = False
        db_table = "room"
        verbose_name = verbose_name_plural = "房间"
        ordering = ["floor", "room_no"]

    def __str__(self) -> str:
        return self.room_no


# ---------------------------------------------------------------- 5 room_block

class RoomBlock(_BaseModel):
    """维修 / 停用区间（F02 登记、F03 排除、F09 扣减可售房夜）。"""

    # room_block 只有 created_at（登记时间），没有 updated_at —— 区间一经登记不原地改，
    # 要改就删旧登记新建，避免与 EXCLUDE 约束、状态日志产生歧义。
    updated_at = None

    room = models.ForeignKey(
        Room, verbose_name="房间", on_delete=models.DO_NOTHING,
        db_column="room_id", related_name="blocks",
    )
    start_date = models.DateField("开始日期", db_column="start_date")
    end_date = models.DateField("结束日期", db_column="end_date")
    block_type = models.CharField("类型", max_length=20, choices=BLOCK_TYPE_CHOICES, db_column="block_type")
    reason = models.CharField("原因", max_length=200, blank=True, null=True, db_column="reason")
    created_by = models.ForeignKey(
        AppUser, verbose_name="登记人", null=True, blank=True, on_delete=models.DO_NOTHING,
        db_column="created_by", related_name="room_blocks_created",
    )

    class Meta:
        managed = False
        db_table = "room_block"
        verbose_name = verbose_name_plural = "维修/停用区间"
        ordering = ["-start_date"]
        constraints = []   # 排他约束 ex_room_block_overlap 在 sql/02

    def __str__(self) -> str:
        return f"{self.room_id} {self.start_date}~{self.end_date} {self.get_block_type_display()}"


# ---------------------------------------------------------------- 6 rate_plan

class RatePlan(_BaseModel):
    room_type = models.ForeignKey(
        RoomType, verbose_name="房型", on_delete=models.DO_NOTHING,
        db_column="room_type_id", related_name="rate_plans",
    )
    name = models.CharField("方案名称", max_length=50, blank=True, null=True, db_column="name")
    price = models.DecimalField("价格(元)", max_digits=10, decimal_places=2, db_column="price")
    valid_from = models.DateField("生效起", db_column="valid_from")
    valid_to = models.DateField("生效止", db_column="valid_to")

    class Meta:
        managed = False
        db_table = "rate_plan"
        verbose_name = verbose_name_plural = "价格方案"
        ordering = ["room_type_id", "valid_from"]

    def __str__(self) -> str:
        return f"{self.name or '价格方案'} {self.valid_from}~{self.valid_to} {self.price}"


# ---------------------------------------------------------------- 7 reservation

class Reservation(_BaseModel):
    reservation_no = models.CharField("预订号", max_length=20, unique=True, db_column="reservation_no")
    customer = models.ForeignKey(
        Customer, verbose_name="客户", on_delete=models.DO_NOTHING,
        db_column="customer_id", related_name="reservations",
    )
    room = models.ForeignKey(
        Room, verbose_name="房间", on_delete=models.DO_NOTHING,
        db_column="room_id", related_name="reservations",
    )
    check_in_date = models.DateField("入住日期", db_column="check_in_date")
    check_out_date = models.DateField("离店日期", db_column="check_out_date")
    guest_count = models.SmallIntegerField("入住人数", default=1, db_column="guest_count")
    price_per_night = models.DecimalField("每晚均价(元)", max_digits=10, decimal_places=2, db_column="price_per_night")
    total_amount = models.DecimalField("预订总金额(元)", max_digits=10, decimal_places=2, db_column="total_amount")
    status = models.CharField(
        "预订状态", max_length=20, choices=RESERVATION_STATUS_CHOICES, default="pending", db_column="status"
    )
    source = models.CharField(
        "来源", max_length=20, choices=RESERVATION_SOURCE_CHOICES, default="online", db_column="source"
    )
    remark = models.CharField("备注", max_length=200, blank=True, null=True, db_column="remark")

    class Meta:
        managed = False
        db_table = "reservation"
        verbose_name = verbose_name_plural = "预订"
        ordering = ["-check_in_date", "-id"]

    def __str__(self) -> str:
        return self.reservation_no

    @property
    def nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days


# ---------------------------------------------------------------- 8 reservation_price

class ReservationPrice(models.Model):
    """逐日成交价格（预订确认时由触发器 fn_sync_reservation_prices 写入）。"""

    id = models.BigAutoField(primary_key=True)
    reservation = models.ForeignKey(
        Reservation, verbose_name="预订", on_delete=models.DO_NOTHING,
        db_column="reservation_id", related_name="daily_prices",
    )
    stay_date = models.DateField("住宿日期", db_column="stay_date")
    price = models.DecimalField("当日成交价(元)", max_digits=10, decimal_places=2, db_column="price")
    created_at = models.DateTimeField("创建时间", auto_now_add=True, db_column="created_at")

    class Meta:
        managed = False
        db_table = "reservation_price"
        verbose_name = verbose_name_plural = "逐日成交价格"
        ordering = ["reservation_id", "stay_date"]

    def __str__(self) -> str:
        return f"{self.reservation_id} {self.stay_date} {self.price}"


# ---------------------------------------------------------------- 9 check_in_record

class CheckInRecord(_BaseModel):
    reservation = models.OneToOneField(
        Reservation, verbose_name="预订", on_delete=models.DO_NOTHING,
        db_column="reservation_id", related_name="check_in",
    )
    guest_name = models.CharField("入住人姓名", max_length=50, db_column="guest_name")
    guest_phone = models.CharField("入住人手机", max_length=20, db_column="guest_phone")
    guest_id_card = models.CharField("入住人证件号", max_length=18, blank=True, null=True, db_column="guest_id_card")
    check_in_at = models.DateTimeField("入住时间", default=timezone.now, db_column="check_in_at")
    actual_checkout_at = models.DateTimeField("实际退房时间", null=True, blank=True, db_column="actual_checkout_at")
    deposit_amount = models.DecimalField("押金(元)", max_digits=10, decimal_places=2, default=0, db_column="deposit_amount")
    room_charge = models.DecimalField("房费(元)", max_digits=10, decimal_places=2, default=0, db_column="room_charge")
    service_charge = models.DecimalField("服务费(元)", max_digits=10, decimal_places=2, default=0, db_column="service_charge")
    total_charge = models.DecimalField("应收合计(元)", max_digits=10, decimal_places=2, default=0, db_column="total_charge")
    remark = models.CharField("备注", max_length=200, blank=True, null=True, db_column="remark")

    class Meta:
        managed = False
        db_table = "check_in_record"
        verbose_name = verbose_name_plural = "入住记录"
        ordering = ["-check_in_at"]

    def __str__(self) -> str:
        return f"{self.guest_name} @ {self.reservation_id}"


# ---------------------------------------------------------------- 10 payment

class Payment(models.Model):
    id = models.BigAutoField(primary_key=True)
    payment_no = models.CharField("支付单号", max_length=20, unique=True, db_column="payment_no")
    check_in_record = models.ForeignKey(
        CheckInRecord, verbose_name="入住记录", on_delete=models.DO_NOTHING,
        db_column="check_in_record_id", related_name="payments",
    )
    kind = models.CharField("款项类型", max_length=20, choices=PAYMENT_KIND_CHOICES, db_column="kind")
    method = models.CharField("支付方式", max_length=20, choices=PAYMENT_METHOD_CHOICES, db_column="method")
    amount = models.DecimalField("金额(元)", max_digits=10, decimal_places=2, db_column="amount")
    paid_at = models.DateTimeField("收款时间", default=timezone.now, db_column="paid_at")
    operator_user = models.ForeignKey(
        AppUser, verbose_name="经办人", null=True, blank=True, on_delete=models.DO_NOTHING,
        db_column="operator_user_id", related_name="payments_operated",
    )
    remark = models.CharField("备注", max_length=200, blank=True, null=True, db_column="remark")

    class Meta:
        managed = False
        db_table = "payment"
        verbose_name = verbose_name_plural = "支付流水"
        ordering = ["-paid_at"]

    def __str__(self) -> str:
        return f"{self.payment_no} {self.kind} {self.amount}"


# ---------------------------------------------------------------- 11 room_status_log

class RoomStatusLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    room = models.ForeignKey(
        Room, verbose_name="房间", on_delete=models.DO_NOTHING,
        db_column="room_id", related_name="status_logs",
    )
    from_status = models.CharField(
        "原状态", max_length=20, choices=ROOM_STATUS_CHOICES, blank=True, null=True, db_column="from_status"
    )
    to_status = models.CharField("新状态", max_length=20, choices=ROOM_STATUS_CHOICES, db_column="to_status")
    changed_by = models.ForeignKey(
        AppUser, verbose_name="操作人", null=True, blank=True, on_delete=models.DO_NOTHING,
        db_column="changed_by", related_name="room_status_changes",
    )
    changed_at = models.DateTimeField("变更时间", default=timezone.now, db_column="changed_at")
    reason = models.CharField("原因", max_length=200, blank=True, null=True, db_column="reason")

    class Meta:
        managed = False
        db_table = "room_status_log"
        verbose_name = verbose_name_plural = "房态变更日志"
        ordering = ["-changed_at"]


# ---------------------------------------------------------------- 12 service_item

class ServiceItem(_BaseModel):
    # service_item 只有 created_at，没有 updated_at（价目表改动直接改 price，无需审计列）
    updated_at = None

    code = models.CharField("服务编码", max_length=20, unique=True, db_column="code")
    name = models.CharField("服务名称", max_length=50, unique=True, db_column="name")
    unit = models.CharField("计量单位", max_length=10, default="份", db_column="unit")
    price = models.DecimalField("单价(元)", max_digits=10, decimal_places=2, db_column="price")
    is_active = models.BooleanField("是否在售", default=True, db_column="is_active")

    class Meta:
        managed = False
        db_table = "service_item"
        verbose_name = verbose_name_plural = "增值服务项目"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.name}({self.price}/{self.unit})"


# ---------------------------------------------------------------- 13 service_order

class ServiceOrder(models.Model):
    id = models.BigAutoField(primary_key=True)
    check_in_record = models.ForeignKey(
        CheckInRecord, verbose_name="入住记录", on_delete=models.DO_NOTHING,
        db_column="check_in_record_id", related_name="service_orders",
    )
    service_item = models.ForeignKey(
        ServiceItem, verbose_name="服务项目", on_delete=models.DO_NOTHING,
        db_column="service_item_id", related_name="orders",
    )
    quantity = models.IntegerField("数量", db_column="quantity")
    unit_price = models.DecimalField("单价快照(元)", max_digits=10, decimal_places=2, db_column="unit_price")
    # 数据库生成列 quantity * unit_price；GeneratedField 只为读取映射，不参与写
    amount = models.GeneratedField(
        expression=models.F("quantity") * models.F("unit_price"),
        output_field=models.DecimalField(max_digits=12, decimal_places=2),
        db_persist=True,
        verbose_name="金额(元)",
    )
    ordered_at = models.DateTimeField("登记时间", default=timezone.now, db_column="ordered_at")

    class Meta:
        managed = False
        db_table = "service_order"
        verbose_name = verbose_name_plural = "增值服务消费明细"
        ordering = ["-ordered_at"]
