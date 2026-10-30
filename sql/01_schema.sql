\set ON_ERROR_STOP on
\encoding UTF8

-- =============================================================================
-- 01_schema.sql —— 建表（云栖酒店客房预订与入住管理系统 · 第 14 组）
-- 目标库：yunqi_hotel（由 sql/00_database.sql 创建）
--
-- 用法：
--   chcp 65001
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 `
--       -d yunqi_hotel -v ON_ERROR_STOP=1 -f sql/01_schema.sql
--
-- 约定（与 AGENTS.md §4.1 一致）：
--   1) 表名 snake_case 复数，字段 snake_case；
--   2) 约束全部显式命名，前缀 pk_ / fk_ / uq_ / ck_ / idx_，报告 3.2.2 可直接引用；
--   3) 每张表、每个关键字段都有 COMMENT ON，报告截图可直接用；
--   4) 金额 numeric(10,2)，时间 timestamptz，日期 date；
--   5) 状态字段用 CHECK (… IN (…))，不用 PG 原生 ENUM；
--   6) 本脚本可重复执行：先按依赖倒序 DROP … CASCADE，再重建。
--
-- 分层：本文件只建表（PK/FK/NOT NULL/UNIQUE/CHECK/基础索引）。
--       生成列 during、EXCLUDE 排他约束、部分唯一索引、触发器、视图 → sql/02_constraints.sql。
--       因此 01 必须在 02 之前执行，且改结构后要连着跑 01 → 02。
-- =============================================================================

-- 客户端编码声明已放在文件首行（必须在任何中文之前），见文件顶部。

SET search_path TO public;

-- ----------------------------------------------------------------------------
-- 0) 清理（依赖倒序；CASCADE 会把 02 里的约束/索引一并带走，重跑 01→02 即可）
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS service_order    CASCADE;
DROP TABLE IF EXISTS service_item     CASCADE;
DROP TABLE IF EXISTS payment          CASCADE;
DROP TABLE IF EXISTS room_status_log  CASCADE;
DROP TABLE IF EXISTS check_in_record  CASCADE;
DROP TABLE IF EXISTS reservation      CASCADE;
DROP TABLE IF EXISTS rate_plan        CASCADE;
DROP TABLE IF EXISTS room             CASCADE;
DROP TABLE IF EXISTS room_type        CASCADE;
DROP TABLE IF EXISTS customer         CASCADE;
DROP TABLE IF EXISTS app_user         CASCADE;

-- =============================================================================
-- 1) app_user 账号（客户 / 前台 / 管理员）
--    说明：Django 侧用自定义用户模型（AUTH_USER_MODEL = 'core.AppUser'），
--          password 存 Django 的 PBKDF2 哈希串，不存明文。
-- =============================================================================
CREATE TABLE app_user (
    id            bigserial    NOT NULL,
    username      varchar(50)  NOT NULL,
    password      varchar(128) NOT NULL,
    display_name  varchar(50)  NOT NULL,
    role          varchar(20)  NOT NULL DEFAULT 'customer',
    phone         varchar(20),
    email         varchar(120),
    is_active     boolean      NOT NULL DEFAULT true,
    last_login    timestamptz,
    created_at    timestamptz  NOT NULL DEFAULT now(),
    updated_at    timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT pk_app_user          PRIMARY KEY (id),
    CONSTRAINT uq_app_user_username UNIQUE (username),
    CONSTRAINT ck_app_user_role     CHECK (role IN ('customer', 'receptionist', 'admin'))
);

COMMENT ON TABLE  app_user              IS '账号表：登录身份与角色（客户/前台/管理员）';
COMMENT ON COLUMN app_user.username     IS '登录名，全局唯一';
COMMENT ON COLUMN app_user.password     IS 'Django PBKDF2 密码哈希（不存明文）';
COMMENT ON COLUMN app_user.display_name IS '显示姓名';
COMMENT ON COLUMN app_user.role         IS '角色：customer 客户 / receptionist 前台 / admin 管理员';
COMMENT ON COLUMN app_user.phone        IS '联系电话';
COMMENT ON COLUMN app_user.is_active    IS '是否可登录；停用账号不删除，保留历史外键';
COMMENT ON COLUMN app_user.last_login   IS '最近登录时间';
COMMENT ON COLUMN app_user.created_at   IS '创建时间';
COMMENT ON COLUMN app_user.updated_at   IS '最后更新时间';

-- =============================================================================
-- 2) customer 客户档案
--    user_id 可空：线下散客没有账号，也要能开入住记录。
-- =============================================================================
CREATE TABLE customer (
    id          bigserial    NOT NULL,
    user_id     bigint,
    name        varchar(50)  NOT NULL,
    phone       varchar(20)  NOT NULL,
    id_card     varchar(18),
    email       varchar(120),
    remark      varchar(200),
    created_at  timestamptz  NOT NULL DEFAULT now(),
    updated_at  timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT pk_customer          PRIMARY KEY (id),
    CONSTRAINT fk_customer_user     FOREIGN KEY (user_id) REFERENCES app_user (id) ON DELETE SET NULL,
    CONSTRAINT uq_customer_user     UNIQUE (user_id),
    CONSTRAINT uq_customer_phone    UNIQUE (phone),
    CONSTRAINT uq_customer_id_card  UNIQUE (id_card),
    CONSTRAINT ck_customer_id_card  CHECK (id_card IS NULL OR char_length(id_card) IN (15, 18))
);

COMMENT ON TABLE  customer           IS '客户档案（账号客户与线下散客共用）';
COMMENT ON COLUMN customer.user_id   IS '关联登录账号；散客为空';
COMMENT ON COLUMN customer.name      IS '客户姓名';
COMMENT ON COLUMN customer.phone     IS '手机号，唯一，用于前台按手机号检索预订';
COMMENT ON COLUMN customer.id_card   IS '身份证号（15 或 18 位），唯一';
COMMENT ON COLUMN customer.remark    IS '备注';

-- =============================================================================
-- 3) room_type 房型
-- =============================================================================
CREATE TABLE room_type (
    id          bigserial    NOT NULL,
    name        varchar(50)  NOT NULL,
    bed_type    varchar(20)  NOT NULL,
    area        numeric(5,1),
    capacity    smallint     NOT NULL,
    base_price  numeric(10,2) NOT NULL,
    description varchar(200),
    is_active   boolean      NOT NULL DEFAULT true,
    created_at  timestamptz  NOT NULL DEFAULT now(),
    updated_at  timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT pk_room_type           PRIMARY KEY (id),
    CONSTRAINT uq_room_type_name      UNIQUE (name),
    CONSTRAINT ck_room_type_bed_type  CHECK (bed_type IN ('single', 'double', 'twin', 'king', 'family', 'suite')),
    CONSTRAINT ck_room_type_area      CHECK (area IS NULL OR area > 0),
    CONSTRAINT ck_room_type_capacity  CHECK (capacity BETWEEN 1 AND 8),
    CONSTRAINT ck_room_type_base_price CHECK (base_price >= 0)
);

COMMENT ON TABLE  room_type             IS '房型表：标准价、容纳人数、床型';
COMMENT ON COLUMN room_type.name        IS '房型名称，唯一（如“高级大床房”）';
COMMENT ON COLUMN room_type.bed_type    IS '床型：single 单人 / double 双人 / twin 双床 / king 大床 / family 家庭 / suite 套房';
COMMENT ON COLUMN room_type.area        IS '建筑面积（㎡）';
COMMENT ON COLUMN room_type.capacity    IS '可容纳人数，1–8';
COMMENT ON COLUMN room_type.base_price  IS '标准价（元/晚），无区间定价方案时使用';
COMMENT ON COLUMN room_type.is_active   IS '是否在售；停用后不出现在可用房查询';

-- =============================================================================
-- 4) room 具体房间
-- =============================================================================
CREATE TABLE room (
    id           bigserial    NOT NULL,
    room_type_id bigint       NOT NULL,
    room_no      varchar(10)  NOT NULL,
    floor        smallint     NOT NULL,
    orientation  varchar(10),
    status       varchar(20)  NOT NULL DEFAULT 'available',
    remark       varchar(200),
    created_at   timestamptz  NOT NULL DEFAULT now(),
    updated_at   timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT pk_room             PRIMARY KEY (id),
    CONSTRAINT fk_room_room_type   FOREIGN KEY (room_type_id) REFERENCES room_type (id) ON DELETE RESTRICT,
    CONSTRAINT uq_room_room_no     UNIQUE (room_no),
    CONSTRAINT ck_room_floor       CHECK (floor BETWEEN -2 AND 99),
    CONSTRAINT ck_room_orientation CHECK (orientation IS NULL OR orientation IN ('north', 'south', 'east', 'west')),
    CONSTRAINT ck_room_status      CHECK (status IN ('available', 'reserved', 'occupied', 'cleaning', 'maintenance', 'disabled'))
);

COMMENT ON TABLE  room              IS '房间表：房号唯一，房态随业务流转';
COMMENT ON COLUMN room.room_type_id IS '所属房型';
COMMENT ON COLUMN room.room_no      IS '房号，唯一（如 801）';
COMMENT ON COLUMN room.floor        IS '楼层（地下为负）';
COMMENT ON COLUMN room.orientation  IS '朝向：north/south/east/west';
COMMENT ON COLUMN room.status       IS '房态：available 可用 / reserved 已预订 / occupied 入住中 / cleaning 清洁中 / maintenance 维修中 / disabled 停用';
COMMENT ON COLUMN room.remark       IS '备注';

-- =============================================================================
-- 5) rate_plan 按日期区间的价格方案
--    区间重叠由 02_constraints.sql 的 EXCLUDE 约束保证（valid_during 生成列在 02 里加）。
-- =============================================================================
CREATE TABLE rate_plan (
    id           bigserial     NOT NULL,
    room_type_id bigint        NOT NULL,
    name         varchar(50),
    price        numeric(10,2) NOT NULL,
    valid_from   date          NOT NULL,
    valid_to     date          NOT NULL,
    created_at   timestamptz   NOT NULL DEFAULT now(),
    updated_at   timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT pk_rate_plan            PRIMARY KEY (id),
    CONSTRAINT fk_rate_plan_room_type  FOREIGN KEY (room_type_id) REFERENCES room_type (id) ON DELETE CASCADE,
    CONSTRAINT ck_rate_plan_price      CHECK (price >= 0),
    CONSTRAINT ck_rate_plan_range      CHECK (valid_to >= valid_from)
);

COMMENT ON TABLE  rate_plan            IS '按日期区间的价格方案（节假日加价等）';
COMMENT ON COLUMN rate_plan.room_type_id IS '所属房型';
COMMENT ON COLUMN rate_plan.name       IS '方案名称（如“国庆加价”）';
COMMENT ON COLUMN rate_plan.price      IS '该区间每晚价格（元）';
COMMENT ON COLUMN rate_plan.valid_from IS '生效起始日（含）';
COMMENT ON COLUMN rate_plan.valid_to   IS '生效截止日（含）';

-- =============================================================================
-- 6) reservation 预订主表
--    核心：check_in_date / check_out_date 为 date 列，02 里加生成列 during 并建 EXCLUDE。
-- =============================================================================
CREATE TABLE reservation (
    id              bigserial     NOT NULL,
    reservation_no  varchar(20)   NOT NULL,
    customer_id     bigint        NOT NULL,
    room_id         bigint        NOT NULL,
    check_in_date   date          NOT NULL,
    check_out_date  date          NOT NULL,
    guest_count     smallint      NOT NULL DEFAULT 1,
    price_per_night numeric(10,2) NOT NULL,
    total_amount    numeric(10,2) NOT NULL,
    status          varchar(20)   NOT NULL DEFAULT 'pending',
    source          varchar(20)   NOT NULL DEFAULT 'online',
    remark          varchar(200),
    created_at      timestamptz   NOT NULL DEFAULT now(),
    updated_at      timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT pk_reservation              PRIMARY KEY (id),
    CONSTRAINT fk_reservation_customer     FOREIGN KEY (customer_id) REFERENCES customer (id) ON DELETE RESTRICT,
    CONSTRAINT fk_reservation_room         FOREIGN KEY (room_id) REFERENCES room (id) ON DELETE RESTRICT,
    CONSTRAINT uq_reservation_no           UNIQUE (reservation_no),
    CONSTRAINT ck_reservation_date_order   CHECK (check_out_date > check_in_date),
    CONSTRAINT ck_reservation_guest_count  CHECK (guest_count > 0),
    CONSTRAINT ck_reservation_price        CHECK (price_per_night >= 0 AND total_amount >= 0),
    CONSTRAINT ck_reservation_status       CHECK (status IN ('pending', 'confirmed', 'checked_in', 'checked_out', 'cancelled', 'no_show')),
    CONSTRAINT ck_reservation_source       CHECK (source IN ('online', 'phone', 'walk_in'))
);

COMMENT ON TABLE  reservation                 IS '预订主表：一行 = 一段“某房间某日期区间”的占用';
COMMENT ON COLUMN reservation.reservation_no  IS '预订号（业务编号，唯一，如 R20261203001）';
COMMENT ON COLUMN reservation.customer_id     IS '预订客户';
COMMENT ON COLUMN reservation.room_id         IS '预订房间';
COMMENT ON COLUMN reservation.check_in_date   IS '入住日期（含）';
COMMENT ON COLUMN reservation.check_out_date  IS '离店日期（不含）：半开区间 [check_in, check_out)';
COMMENT ON COLUMN reservation.guest_count     IS '入住人数';
COMMENT ON COLUMN reservation.price_per_night IS '下单时每晚房价快照（价格调整不影响历史订单）';
COMMENT ON COLUMN reservation.total_amount    IS '订单总金额 = 晚数 × price_per_night';
COMMENT ON COLUMN reservation.status          IS '状态：pending 待确认 / confirmed 已确认 / checked_in 已入住 / checked_out 已退房 / cancelled 已取消 / no_show 未到店';
COMMENT ON COLUMN reservation.source          IS '来源：online 线上 / phone 电话 / walk_in 散客';

-- 基础索引（非约束类，02 里还有部分唯一索引与 EXCLUDE）
CREATE INDEX idx_reservation_customer   ON reservation (customer_id);
CREATE INDEX idx_reservation_room_dates ON reservation (room_id, check_in_date, check_out_date);
CREATE INDEX idx_reservation_status     ON reservation (status);

-- =============================================================================
-- 7) check_in_record 入住与结算记录
--    一个预订最多一条入住记录（散客入住也走这里，reservation_id 指向系统内自动建的单）。
-- =============================================================================
CREATE TABLE check_in_record (
    id                 bigserial     NOT NULL,
    reservation_id     bigint        NOT NULL,
    guest_name         varchar(50)   NOT NULL,
    guest_phone        varchar(20)   NOT NULL,
    guest_id_card      varchar(18),
    check_in_at        timestamptz   NOT NULL DEFAULT now(),
    actual_checkout_at timestamptz,
    deposit_amount     numeric(10,2) NOT NULL DEFAULT 0,
    room_charge        numeric(10,2) NOT NULL DEFAULT 0,
    service_charge     numeric(10,2) NOT NULL DEFAULT 0,
    total_charge       numeric(10,2) NOT NULL DEFAULT 0,
    remark             varchar(200),
    created_at         timestamptz   NOT NULL DEFAULT now(),
    updated_at         timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT pk_check_in_record              PRIMARY KEY (id),
    CONSTRAINT fk_check_in_record_reservation  FOREIGN KEY (reservation_id) REFERENCES reservation (id) ON DELETE RESTRICT,
    CONSTRAINT uq_check_in_record_reservation  UNIQUE (reservation_id),
    CONSTRAINT ck_check_in_record_time_order   CHECK (actual_checkout_at IS NULL OR actual_checkout_at >= check_in_at),
    CONSTRAINT ck_check_in_record_amounts      CHECK (deposit_amount >= 0 AND room_charge >= 0 AND service_charge >= 0 AND total_charge >= 0),
    CONSTRAINT ck_check_in_record_guest_id     CHECK (guest_id_card IS NULL OR char_length(guest_id_card) IN (15, 18))
);

COMMENT ON TABLE  check_in_record                     IS '入住与结算记录：一条预订最多一条，记录押金与实际费用';
COMMENT ON COLUMN check_in_record.reservation_id      IS '对应预订（唯一）';
COMMENT ON COLUMN check_in_record.guest_name          IS '实际入住人姓名（可能与预订人不同）';
COMMENT ON COLUMN check_in_record.guest_phone         IS '实际入住人电话';
COMMENT ON COLUMN check_in_record.guest_id_card       IS '实际入住人身份证号';
COMMENT ON COLUMN check_in_record.check_in_at         IS '实际入住时间';
COMMENT ON COLUMN check_in_record.actual_checkout_at  IS '实际退房时间；为空表示仍在住';
COMMENT ON COLUMN check_in_record.deposit_amount      IS '收取的押金';
COMMENT ON COLUMN check_in_record.room_charge         IS '房费 = 实际入住天数 × 适用房价';
COMMENT ON COLUMN check_in_record.service_charge      IS '增值服务费合计';
COMMENT ON COLUMN check_in_record.total_charge        IS '应收合计 = 房费 + 服务费（押金抵扣除后差额由 payment 体现）';

-- =============================================================================
-- 8) payment 支付 / 退款流水
-- =============================================================================
CREATE TABLE payment (
    id                bigserial     NOT NULL,
    payment_no        varchar(20)   NOT NULL,
    check_in_record_id bigint       NOT NULL,
    kind              varchar(20)   NOT NULL,
    method            varchar(20)   NOT NULL,
    amount            numeric(10,2) NOT NULL,
    paid_at           timestamptz   NOT NULL DEFAULT now(),
    operator_user_id  bigint,
    remark            varchar(200),
    CONSTRAINT pk_payment                  PRIMARY KEY (id),
    CONSTRAINT fk_payment_check_in_record  FOREIGN KEY (check_in_record_id) REFERENCES check_in_record (id) ON DELETE CASCADE,
    CONSTRAINT fk_payment_operator         FOREIGN KEY (operator_user_id) REFERENCES app_user (id) ON DELETE SET NULL,
    CONSTRAINT uq_payment_no               UNIQUE (payment_no),
    CONSTRAINT ck_payment_kind             CHECK (kind IN ('deposit', 'room_fee', 'service_fee', 'refund')),
    CONSTRAINT ck_payment_method           CHECK (method IN ('cash', 'card', 'wechat', 'alipay')),
    CONSTRAINT ck_payment_amount           CHECK (amount >= 0)
);

COMMENT ON TABLE  payment                    IS '支付/退款流水：一笔入住记录可有多笔收款与退款';
COMMENT ON COLUMN payment.payment_no         IS '流水号，唯一';
COMMENT ON COLUMN payment.check_in_record_id IS '所属入住记录';
COMMENT ON COLUMN payment.kind               IS '类型：deposit 押金 / room_fee 房费 / service_fee 服务费 / refund 退款';
COMMENT ON COLUMN payment.method             IS '支付方式：cash 现金 / card 刷卡 / wechat 微信 / alipay 支付宝';
COMMENT ON COLUMN payment.amount             IS '金额（退款也记正数，用 kind 区分方向）';
COMMENT ON COLUMN payment.paid_at            IS '收付时间';
COMMENT ON COLUMN payment.operator_user_id   IS '经办人（前台账号）';

CREATE INDEX idx_payment_record  ON payment (check_in_record_id);
CREATE INDEX idx_payment_paid_at ON payment (paid_at);

-- =============================================================================
-- 9) room_status_log 房态变更日志（状态可追溯）
-- =============================================================================
CREATE TABLE room_status_log (
    id           bigserial    NOT NULL,
    room_id      bigint       NOT NULL,
    from_status  varchar(20),
    to_status    varchar(20)  NOT NULL,
    changed_by   bigint,
    changed_at   timestamptz  NOT NULL DEFAULT now(),
    reason       varchar(200),
    CONSTRAINT pk_room_status_log        PRIMARY KEY (id),
    CONSTRAINT fk_room_status_log_room   FOREIGN KEY (room_id) REFERENCES room (id) ON DELETE CASCADE,
    CONSTRAINT fk_room_status_log_user   FOREIGN KEY (changed_by) REFERENCES app_user (id) ON DELETE SET NULL,
    CONSTRAINT ck_room_status_log_from  CHECK (from_status IS NULL OR from_status IN ('available', 'reserved', 'occupied', 'cleaning', 'maintenance', 'disabled')),
    CONSTRAINT ck_room_status_log_to    CHECK (to_status IN ('available', 'reserved', 'occupied', 'cleaning', 'maintenance', 'disabled'))
);

COMMENT ON TABLE  room_status_log            IS '房态变更日志：谁在何时把房间状态从什么改成什么';
COMMENT ON COLUMN room_status_log.room_id    IS '房间';
COMMENT ON COLUMN room_status_log.from_status IS '变更前房态（首次记录为空）';
COMMENT ON COLUMN room_status_log.to_status  IS '变更后房态';
COMMENT ON COLUMN room_status_log.changed_by IS '操作人（系统自动变更时为空）';
COMMENT ON COLUMN room_status_log.reason     IS '变更原因';

CREATE INDEX idx_room_status_log_room ON room_status_log (room_id, changed_at DESC);

-- =============================================================================
-- 10) 可选表 A：service_item 增值服务项目
--     实现 F07 增值服务时才需要；不做的组可整段注释掉（与 docs/01 的“9 必选 + 2 可选”对应）
-- =============================================================================
CREATE TABLE service_item (
    id         bigserial     NOT NULL,
    code       varchar(20)   NOT NULL,
    name       varchar(50)   NOT NULL,
    unit       varchar(10)   NOT NULL DEFAULT '份',
    price      numeric(10,2) NOT NULL,
    is_active  boolean       NOT NULL DEFAULT true,
    created_at timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT pk_service_item       PRIMARY KEY (id),
    CONSTRAINT uq_service_item_code  UNIQUE (code),
    CONSTRAINT uq_service_item_name  UNIQUE (name),
    CONSTRAINT ck_service_item_price CHECK (price >= 0)
);

COMMENT ON TABLE  service_item        IS '（可选）增值服务项目：早餐、洗衣、接送等';
COMMENT ON COLUMN service_item.code   IS '服务编码，唯一';
COMMENT ON COLUMN service_item.name   IS '服务名称';
COMMENT ON COLUMN service_item.unit   IS '计量单位';
COMMENT ON COLUMN service_item.price  IS '单价（元）';
COMMENT ON COLUMN service_item.is_active IS '是否在售';

-- =============================================================================
-- 11) 可选表 B：service_order 增值服务消费明细
-- =============================================================================
CREATE TABLE service_order (
    id                bigserial     NOT NULL,
    check_in_record_id bigint       NOT NULL,
    service_item_id   bigint        NOT NULL,
    quantity          integer       NOT NULL,
    unit_price        numeric(10,2) NOT NULL,
    amount            numeric(10,2) GENERATED ALWAYS AS (quantity * unit_price) STORED,
    ordered_at        timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT pk_service_order                  PRIMARY KEY (id),
    CONSTRAINT fk_service_order_check_in_record  FOREIGN KEY (check_in_record_id) REFERENCES check_in_record (id) ON DELETE CASCADE,
    CONSTRAINT fk_service_order_service_item     FOREIGN KEY (service_item_id) REFERENCES service_item (id) ON DELETE RESTRICT,
    CONSTRAINT ck_service_order_quantity         CHECK (quantity > 0),
    CONSTRAINT ck_service_order_unit_price       CHECK (unit_price >= 0)
);

COMMENT ON TABLE  service_order                   IS '（可选）增值服务消费明细';
COMMENT ON COLUMN service_order.check_in_record_id IS '所属入住记录';
COMMENT ON COLUMN service_order.service_item_id   IS '服务项目';
COMMENT ON COLUMN service_order.quantity          IS '数量';
COMMENT ON COLUMN service_order.unit_price        IS '消费时单价快照';
COMMENT ON COLUMN service_order.amount            IS '金额 = 数量 × 单价（生成列）';
COMMENT ON COLUMN service_order.ordered_at        IS '消费时间';

CREATE INDEX idx_service_order_record ON service_order (check_in_record_id);

-- ----------------------------------------------------------------------------
-- 自检：列出本次建成的表（期望 11 行：9 必选 + 2 可选）
-- ----------------------------------------------------------------------------
SELECT c.relname                                    AS table_name,
       obj_description(c.oid, 'pg_class')           AS comment,
       (SELECT count(*) FROM pg_attribute a
         WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped) AS columns
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relname;

SELECT count(*) AS table_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r';
