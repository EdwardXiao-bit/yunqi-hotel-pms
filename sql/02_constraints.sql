\set ON_ERROR_STOP on
\encoding UTF8

-- =============================================================================
-- 02_constraints.sql —— 数据库级业务约束（本项目 50% 得分点的技术核心）
-- 前置：先执行 sql/01_schema.sql（表已建好）。本脚本可重复执行。
--
-- 内容：
--   1) btree_gist 扩展（GiST 索引上做 bigint 等值比较，EXCLUDE 必需）
--   2) 幂等清理（视图/函数 → 触发器/函数 → 约束/索引 → 生成列）
--   3) 生成列 during / valid_during（日期区间 → 范围类型），共 3 处
--   4) EXCLUDE 排他约束：
--        · 同一房间的生效预订不得重叠（ex_reservation_room_overlap）
--        · 同一房型的价格方案区间不得重叠（ex_rate_plan_no_overlap）
--        · 同一房间的维修/停用区间不得重叠（ex_room_block_overlap）
--   5) 部分唯一索引：同一客户对同一房间同一区间不得重复占用
--   6) updated_at 自动维护触发器 + 房态变更自动写日志触发器
--   7) 跨表冲突触发器（订单 ↔ 维修/停用区间，SQLSTATE 23514）
--   8) 逐日成交价格触发器（reservation_price ↔ reservation.total_amount）
--   9) 视图 v_reservation_detail / v_check_in_detail
--  10) 函数 fn_stay_total_price() / fn_available_rooms()
--  11) 自检：排他约束/触发器/视图/函数清单
--  12) 自检：真的插临时数据验证 23P01 / 23514 / 逐日价格，最后清理
--
-- 为什么能防超卖：reservation 的 (room_id, during) 在 status 生效时互斥，
-- 任何两个“同一房间 + 日期相交 + 状态未终结”的预订都不可能同时存在，
-- 并发插入时第二个会拿到 SQLSTATE 23P01（exclusion_violation），由 Django 映射为中文提示。
--
-- SQLSTATE 约定（Django 侧统一映射）：
--   23P01 exclusion_violation —— 房间已被占用 / 价格方案区间重叠
--   23514 check_violation     —— 房间处于维修/停用、封禁区间与有效订单冲突
--   22023 invalid_parameter_value —— 可用房查询的日期非法
-- =============================================================================

SET search_path TO public;

-- ----------------------------------------------------------------------------
-- 1) btree_gist：让 gist (room_id WITH =, during WITH &&) 里的 bigint = 也能走 GiST
--    （需要超级用户权限；本项目用 postgres 连接，满足）
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ----------------------------------------------------------------------------
-- 2) 幂等清理（顺序：视图/函数 → 触发器/函数 → 约束/索引 → 生成列）
-- ----------------------------------------------------------------------------
DROP VIEW    IF EXISTS v_check_in_detail;
DROP VIEW    IF EXISTS v_reservation_detail;
DROP FUNCTION IF EXISTS fn_available_rooms(date, date, bigint);
DROP FUNCTION IF EXISTS fn_stay_total_price(bigint, date, date);

DROP TRIGGER  IF EXISTS trg_reservation_block_check ON reservation;
DROP FUNCTION IF EXISTS fn_check_reservation_block();

DROP TRIGGER  IF EXISTS trg_room_block_order_check ON room_block;
DROP FUNCTION IF EXISTS fn_check_room_block_order();

DROP TRIGGER  IF EXISTS trg_reservation_price_sync ON reservation;
DROP FUNCTION IF EXISTS fn_sync_reservation_prices();

DROP TRIGGER  IF EXISTS trg_reservation_price_total ON reservation_price;
DROP FUNCTION IF EXISTS fn_refresh_reservation_total();

DROP TRIGGER  IF EXISTS trg_room_status_log ON room;
DROP FUNCTION IF EXISTS fn_log_room_status();

DROP TRIGGER  IF EXISTS trg_app_user_updated_at        ON app_user;
DROP TRIGGER  IF EXISTS trg_customer_updated_at        ON customer;
DROP TRIGGER  IF EXISTS trg_room_type_updated_at       ON room_type;
DROP TRIGGER  IF EXISTS trg_room_updated_at            ON room;
DROP TRIGGER  IF EXISTS trg_rate_plan_updated_at       ON rate_plan;
DROP TRIGGER  IF EXISTS trg_reservation_updated_at     ON reservation;
DROP TRIGGER  IF EXISTS trg_check_in_record_updated_at ON check_in_record;
DROP FUNCTION IF EXISTS fn_set_updated_at();

ALTER TABLE reservation DROP CONSTRAINT IF EXISTS ex_reservation_room_overlap;
ALTER TABLE rate_plan   DROP CONSTRAINT IF EXISTS ex_rate_plan_no_overlap;
ALTER TABLE room_block  DROP CONSTRAINT IF EXISTS ex_room_block_overlap;
DROP INDEX IF EXISTS uq_reservation_active_customer;

ALTER TABLE reservation DROP COLUMN IF EXISTS during;
ALTER TABLE room_block  DROP COLUMN IF EXISTS during;
ALTER TABLE rate_plan   DROP COLUMN IF EXISTS valid_during;

-- ----------------------------------------------------------------------------
-- 3) 生成列：日期区间 → 范围类型
--    reservation / room_block 用半开区间 [start, end)：
--      12-01 入住、12-03 离店 ⇒ 占用 12-01、12-02 两晚，12-03 当天可换人入住；
--      维修登记 12-10 ~ 12-12 同理，12-12 当天恢复可售。
--    rate_plan 用闭区间 [valid_from, valid_to]：价格方案“到哪天为止”含当天。
-- ----------------------------------------------------------------------------
ALTER TABLE reservation
    ADD COLUMN during daterange
    GENERATED ALWAYS AS (daterange(check_in_date, check_out_date, '[)')) STORED;

ALTER TABLE room_block
    ADD COLUMN during daterange
    GENERATED ALWAYS AS (daterange(start_date, end_date, '[)')) STORED;

ALTER TABLE rate_plan
    ADD COLUMN valid_during daterange
    GENERATED ALWAYS AS (daterange(valid_from, valid_to, '[]')) STORED;

COMMENT ON COLUMN reservation.during    IS '占用区间（生成列）：daterange(check_in_date, check_out_date, ''[)'')，半开区间';
COMMENT ON COLUMN room_block.during     IS '封禁区间（生成列）：daterange(start_date, end_date, ''[)'')，半开区间';
COMMENT ON COLUMN rate_plan.valid_during IS '生效区间（生成列）：daterange(valid_from, valid_to, ''[]'')，闭区间';

-- ----------------------------------------------------------------------------
-- 4) EXCLUDE 排他约束（核心）
--    reservation 的 WHERE 子句限定只对“仍占用房间”的状态生效：
--      已退房/已取消/未到店 的记录不参与互斥，历史单不阻塞新房。
-- ----------------------------------------------------------------------------
ALTER TABLE reservation
    ADD CONSTRAINT ex_reservation_room_overlap
    EXCLUDE USING gist (room_id WITH =, during WITH &&)
    WHERE (status IN ('pending', 'confirmed', 'checked_in'));

ALTER TABLE rate_plan
    ADD CONSTRAINT ex_rate_plan_no_overlap
    EXCLUDE USING gist (room_type_id WITH =, valid_during WITH &&);

ALTER TABLE room_block
    ADD CONSTRAINT ex_room_block_overlap
    EXCLUDE USING gist (room_id WITH =, during WITH &&);

COMMENT ON CONSTRAINT ex_reservation_room_overlap ON reservation
    IS '防超卖：同一房间在 [check_in, check_out) 内不得有两笔生效预订（pending/confirmed/checked_in）';
COMMENT ON CONSTRAINT ex_rate_plan_no_overlap ON rate_plan
    IS '同一房型的价格方案生效区间不得重叠';
COMMENT ON CONSTRAINT ex_room_block_overlap ON room_block
    IS '同一房间的维修/停用区间不得重叠';

-- ----------------------------------------------------------------------------
-- 5) 部分唯一索引：同一客户 + 同一房间 + 同一区间，不得有两条生效预订
--    （防客户重复点击/重复提交；不同房间可分别预订）
-- ----------------------------------------------------------------------------
CREATE UNIQUE INDEX uq_reservation_active_customer
    ON reservation (customer_id, room_id, check_in_date, check_out_date)
    WHERE status IN ('pending', 'confirmed', 'checked_in');

COMMENT ON INDEX uq_reservation_active_customer
    IS '同一客户对同一房间同一区间只允许一条生效预订';

-- ----------------------------------------------------------------------------
-- 6) updated_at 自动维护
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_set_updated_at() IS '通用触发器函数：更新行时刷新 updated_at';

CREATE TRIGGER trg_app_user_updated_at        BEFORE UPDATE ON app_user        FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_customer_updated_at        BEFORE UPDATE ON customer        FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_room_type_updated_at       BEFORE UPDATE ON room_type       FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_room_updated_at            BEFORE UPDATE ON room            FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_rate_plan_updated_at       BEFORE UPDATE ON rate_plan       FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_reservation_updated_at     BEFORE UPDATE ON reservation     FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_check_in_record_updated_at BEFORE UPDATE ON check_in_record FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ----------------------------------------------------------------------------
-- 7) 房态变更自动记日志
--    操作人由应用在事务内 SET LOCAL app.current_user_id = '<id>' 传入；
--    没设或不是合法账号时记 NULL（系统自动变更）。
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_log_room_status()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_uid bigint;
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        BEGIN
            v_uid := NULLIF(current_setting('app.current_user_id', true), '')::bigint;
        EXCEPTION WHEN others THEN
            v_uid := NULL;
        END;

        IF v_uid IS NOT NULL AND NOT EXISTS (SELECT 1 FROM app_user WHERE id = v_uid) THEN
            v_uid := NULL;
        END IF;

        INSERT INTO room_status_log (room_id, from_status, to_status, changed_by, reason)
        VALUES (NEW.id, OLD.status, NEW.status, v_uid, '系统自动记录（room.status 变更）');
    END IF;
    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION fn_log_room_status() IS '触发器函数：room.status 变更后写 room_status_log（只记 4 态）';

CREATE TRIGGER trg_room_status_log
    AFTER UPDATE OF status ON room
    FOR EACH ROW EXECUTE FUNCTION fn_log_room_status();

-- ----------------------------------------------------------------------------
-- 8) 视图：列表页与报告 4 章直接引用
--    v_reservation_detail 在原有列之后追加 avg_price（= reservation.price_per_night，
--    由逐日明细汇总而来），原有列一个不删，Django 侧按列名取值不受影响。
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_reservation_detail AS
SELECT r.id                                   AS reservation_id,
       r.reservation_no,
       r.status,
       r.source,
       r.check_in_date,
       r.check_out_date,
       (r.check_out_date - r.check_in_date)   AS nights,
       r.guest_count,
       r.price_per_night,
       r.total_amount,
       r.created_at,
       r.updated_at,
       c.id                                   AS customer_id,
       c.name                                 AS customer_name,
       c.phone                                AS customer_phone,
       rm.id                                  AS room_id,
       rm.room_no,
       rm.floor,
       rt.id                                  AS room_type_id,
       rt.name                                AS room_type_name,
       rt.capacity,
       r.price_per_night                      AS avg_price
FROM reservation r
JOIN customer  c  ON c.id  = r.customer_id
JOIN room      rm ON rm.id = r.room_id
JOIN room_type rt ON rt.id = rm.room_type_id;

COMMENT ON VIEW v_reservation_detail IS '预订详情：预订 + 客户 + 房间 + 房型；total_amount 由逐日价格汇总，avg_price = 平均成交单价';

CREATE OR REPLACE VIEW v_check_in_detail AS
SELECT cir.id                                  AS check_in_record_id,
       cir.reservation_id,
       cir.guest_name,
       cir.guest_phone,
       cir.check_in_at,
       cir.actual_checkout_at,
       cir.deposit_amount,
       cir.room_charge,
       cir.service_charge,
       cir.total_charge,
       COALESCE(p.settled, 0)                  AS settled_amount,
       cir.total_charge - COALESCE(p.settled, 0) AS balance
FROM check_in_record cir
LEFT JOIN (
    SELECT check_in_record_id,
           sum(CASE WHEN kind = 'refund' THEN -amount ELSE amount END) AS settled
    FROM payment
    GROUP BY check_in_record_id
) p ON p.check_in_record_id = cir.id;

COMMENT ON VIEW v_check_in_detail IS '入住结算详情：房费/服务费/押金、已收退金额与差额';

-- ----------------------------------------------------------------------------
-- 9) 函数：整段房费（逐日取价求和）
--    取价规则与 fn_sync_reservation_prices() 完全一致：
--      该房型当天命中 rate_plan（valid_during @> 当天；多条命中取 valid_from 最新）
--      则用方案价，否则用 room_type.base_price。
--    p_check_in..p_check_out-1 每天一档；区间非法/无房型时返回 0（调用方自行校验日期）。
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_stay_total_price(
    p_room_type_id bigint,
    p_check_in     date,
    p_check_out    date
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(round(sum(d.day_price), 2), 0)
    FROM (
        SELECT COALESCE(
                   (SELECT rp.price
                      FROM rate_plan rp
                     WHERE rp.room_type_id = p_room_type_id
                       AND rp.valid_during @> p_check_in + g.n
                     ORDER BY rp.valid_from DESC, rp.id DESC
                     LIMIT 1),
                   (SELECT rt.base_price
                      FROM room_type rt
                     WHERE rt.id = p_room_type_id)
               ) AS day_price
        FROM generate_series(0, (p_check_out - p_check_in) - 1) AS g(n)
    ) d;
$$;

COMMENT ON FUNCTION fn_stay_total_price(bigint, date, date)
    IS '整段房费：入住日到离店日前一天逐日取价（rate_plan 命中价，否则房型标准价）求和';

-- ----------------------------------------------------------------------------
-- 10) 函数：可用房查询（F03 的服务端查询，避开 ORM，报告 4 章可贴 SQL）
--    判定：房型在售 + 房态不是停用/维修 + 无维修停用区间重叠 + 无生效预订重叠。
--    价格：base_price 标准价；total_price 整段房费；avg_price = 整段房费 ÷ 晚数。
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_available_rooms(
    p_check_in     date,
    p_check_out    date,
    p_room_type_id bigint DEFAULT NULL
)
RETURNS TABLE (
    room_id        bigint,
    room_no        varchar,
    room_type_id   bigint,
    room_type_name varchar,
    capacity       smallint,
    floor          smallint,
    base_price     numeric,
    avg_price      numeric,
    total_price    numeric
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_nights integer;
BEGIN
    IF p_check_in IS NULL OR p_check_out IS NULL THEN
        RAISE EXCEPTION '入住日期与离店日期不能为空' USING ERRCODE = '22023';
    END IF;
    IF p_check_out <= p_check_in THEN
        RAISE EXCEPTION '离店日期必须晚于入住日期' USING ERRCODE = '22023';
    END IF;

    v_nights := p_check_out - p_check_in;

    RETURN QUERY
    SELECT rm.id,
           rm.room_no,
           rt.id,
           rt.name,
           rt.capacity,
           rm.floor,
           rt.base_price,
           round(fn_stay_total_price(rt.id, p_check_in, p_check_out) / v_nights, 2) AS avg_price,
           round(fn_stay_total_price(rt.id, p_check_in, p_check_out), 2)            AS total_price
    FROM room rm
    JOIN room_type rt ON rt.id = rm.room_type_id
    WHERE rt.is_active
      AND rm.status NOT IN ('maintenance', 'disabled')
      AND (p_room_type_id IS NULL OR rt.id = p_room_type_id)
      AND NOT EXISTS (
            SELECT 1
            FROM room_block rb
            WHERE rb.room_id = rm.id
              AND rb.during && daterange(p_check_in, p_check_out, '[)')
      )
      AND NOT EXISTS (
            SELECT 1
            FROM reservation r
            WHERE r.room_id = rm.id
              AND r.status IN ('pending', 'confirmed', 'checked_in')
              AND r.during && daterange(p_check_in, p_check_out, '[)')
      )
    ORDER BY rm.floor, rm.room_no;
END;
$$;

COMMENT ON FUNCTION fn_available_rooms(date, date, bigint)
    IS '可用房查询：给定入住/离店日期（半开区间）与可选房型，返回可用房间、标准价、均价与整段房费';

-- ----------------------------------------------------------------------------
-- 11) 触发器函数：跨表冲突（订单 ↔ 维修/停用区间）
--     SQLSTATE 统一用 23514（check_violation），Django 侧映射成中文提示。
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_check_reservation_block()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_room_no     varchar(10);
    v_block_start date;
    v_block_end   date;
BEGIN
    -- 只有“仍占用房间”的状态才校验；已退房/已取消/未到店不阻塞维修登记
    IF NEW.status NOT IN ('pending', 'confirmed', 'checked_in') THEN
        RETURN NEW;
    END IF;

    SELECT rm.room_no, rb.start_date, rb.end_date
      INTO v_room_no, v_block_start, v_block_end
      FROM room_block rb
      JOIN room       rm ON rm.id = rb.room_id
     WHERE rb.room_id = NEW.room_id
       AND rb.during && daterange(NEW.check_in_date, NEW.check_out_date, '[)')
     ORDER BY rb.start_date
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION '房间 % 在 % ~ % 之间处于维修/停用状态，不可预订',
                        v_room_no, v_block_start, v_block_end
            USING ERRCODE = '23514',
                  HINT    = '请更换房间或调整入住/离店日期；或先解除该房间的维修/停用登记（room_block）';
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_check_reservation_block()
    IS '订单落库前校验：房间在该区间内是否被维修/停用区间封禁（SQLSTATE 23514）';

CREATE OR REPLACE FUNCTION fn_check_room_block_order()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_check_in  date;
    v_check_out date;
BEGIN
    -- 注意：during 是 STORED 生成列，BEFORE 触发器里还没算出来
    -- （PostgreSQL 在 BEFORE 触发器之后才计算生成列），所以这里用 start_date/end_date 现算区间。
    SELECT r.check_in_date, r.check_out_date
      INTO v_check_in, v_check_out
      FROM reservation r
     WHERE r.room_id = NEW.room_id
       AND r.status IN ('pending', 'confirmed', 'checked_in')
       AND r.during && daterange(NEW.start_date, NEW.end_date, '[)')
     ORDER BY r.check_in_date
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION '该房间在 % ~ % 之间存在有效订单，请先处理订单再登记维修/停用',
                        v_check_in, v_check_out
            USING ERRCODE = '23514',
                  HINT    = '请先取消或调整该订单，或改选不与订单重叠的封禁区间';
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_check_room_block_order()
    IS '维修/停用登记前校验：该区间内是否已有生效订单（SQLSTATE 23514）';

-- ----------------------------------------------------------------------------
-- 12) 触发器函数：逐日成交价格
--     fn_sync_reservation_prices()  —— 订单区间变化时，删区间外明细、补齐缺失房晚；
--                                      已有房晚不动（下单价固化，后续调价不影响）。
--     fn_refresh_reservation_total() —— 明细变化后，把 sum(price) 汇总回订单主表。
--     两个函数只写 total_amount / price_per_night，不动 room_id / check_in_date /
--     check_out_date，因此不会再把 trg_reservation_price_sync 触发一次（无递归）。
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_sync_reservation_prices()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_room_type_id bigint;
BEGIN
    SELECT rm.room_type_id
      INTO v_room_type_id
      FROM room rm
     WHERE rm.id = NEW.room_id;

    IF v_room_type_id IS NULL THEN
        RETURN NULL;   -- 房间不存在（FK 已拦），纯防御
    END IF;

    -- 1) 改期后，区间外的旧房晚不再属于本单
    DELETE FROM reservation_price rp
     WHERE rp.reservation_id = NEW.id
       AND (rp.stay_date < NEW.check_in_date OR rp.stay_date >= NEW.check_out_date);

    -- 2) 补齐缺失房晚：当天命中 rate_plan 用方案价（多条命中取 valid_from 最新），
    --    否则用该房型标准价；已存在的房晚保留原成交价
    INSERT INTO reservation_price (reservation_id, stay_date, price)
    SELECT NEW.id,
           g.ts::date,
           COALESCE(p.price, rt.base_price)
    FROM generate_series(NEW.check_in_date::timestamp,
                         (NEW.check_out_date - 1)::timestamp,
                         interval '1 day') AS g(ts)
    JOIN room_type rt ON rt.id = v_room_type_id
    LEFT JOIN LATERAL (
        SELECT rp2.price
          FROM rate_plan rp2
         WHERE rp2.room_type_id = rt.id
           AND rp2.valid_during @> g.ts::date
         ORDER BY rp2.valid_from DESC, rp2.id DESC
         LIMIT 1
    ) p ON true
    ON CONFLICT (reservation_id, stay_date) DO NOTHING;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION fn_sync_reservation_prices()
    IS '触发器函数：按订单区间逐日生成/删除 reservation_price 明细（价格取 rate_plan 命中价或房型标准价）';

CREATE OR REPLACE FUNCTION fn_refresh_reservation_total()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_reservation_id bigint;
    v_total          numeric(10,2);
    v_nights         integer;
BEGIN
    v_reservation_id := COALESCE(NEW.reservation_id, OLD.reservation_id);

    SELECT (r.check_out_date - r.check_in_date)
      INTO v_nights
      FROM reservation r
     WHERE r.id = v_reservation_id;

    -- 订单已不存在（级联清理明细）或日期异常：不再回写
    IF v_nights IS NULL OR v_nights <= 0 THEN
        RETURN NULL;
    END IF;

    SELECT COALESCE(sum(rp.price), 0)
      INTO v_total
      FROM reservation_price rp
     WHERE rp.reservation_id = v_reservation_id;

    UPDATE reservation
       SET total_amount    = v_total,
           price_per_night = round(v_total / v_nights, 2)
     WHERE id = v_reservation_id;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION fn_refresh_reservation_total()
    IS '触发器函数：reservation_price 变动后重算 reservation.total_amount 与平均单价 price_per_night';

-- ----------------------------------------------------------------------------
-- 13) 触发器：跨表冲突 + 逐日价格
--     · trg_reservation_block_check —— 订单落库/改期/改状态前，比对维修停用区间
--     · trg_room_block_order_check  —— 登记维修停用前，比对生效订单
--     · trg_reservation_price_sync  —— 订单区间变化后，同步逐日价格
--     · trg_reservation_price_total —— 逐日价格变化后，回写订单总额
-- ----------------------------------------------------------------------------
CREATE TRIGGER trg_reservation_block_check
    BEFORE INSERT OR UPDATE OF room_id, check_in_date, check_out_date, status ON reservation
    FOR EACH ROW EXECUTE FUNCTION fn_check_reservation_block();

CREATE TRIGGER trg_room_block_order_check
    BEFORE INSERT OR UPDATE ON room_block
    FOR EACH ROW EXECUTE FUNCTION fn_check_room_block_order();

CREATE TRIGGER trg_reservation_price_sync
    AFTER INSERT OR UPDATE OF room_id, check_in_date, check_out_date ON reservation
    FOR EACH ROW EXECUTE FUNCTION fn_sync_reservation_prices();

CREATE TRIGGER trg_reservation_price_total
    AFTER INSERT OR UPDATE OR DELETE ON reservation_price
    FOR EACH ROW EXECUTE FUNCTION fn_refresh_reservation_total();

-- ----------------------------------------------------------------------------
-- 14) 自检 A：排他约束 / 部分唯一索引 / 触发器 / 视图 / 函数清单
-- ----------------------------------------------------------------------------
SELECT conrelid::regclass AS table_name,
       conname            AS constraint_name,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE contype = 'x'
ORDER BY 1, 2;

-- 期望 3 条：ex_reservation_room_overlap / ex_rate_plan_no_overlap / ex_room_block_overlap
SELECT count(*) AS exclusion_constraint_count
FROM pg_constraint
WHERE contype = 'x';

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN ('uq_reservation_active_customer')
ORDER BY indexname;

-- 期望 12 条：7 个 updated_at + 1 个房态日志 + 4 个业务校验/价格触发器
SELECT tgname AS trigger_name,
       tgrelid::regclass AS table_name
FROM pg_trigger
WHERE NOT tgisinternal
ORDER BY 2, 1;

-- 期望 2 个：v_check_in_detail / v_reservation_detail
SELECT table_name AS view_name
FROM information_schema.views
WHERE table_schema = 'public'
ORDER BY 1;

-- 期望 8 个：fn_set_updated_at / fn_log_room_status / fn_check_reservation_block /
--            fn_check_room_block_order / fn_sync_reservation_prices /
--            fn_refresh_reservation_total / fn_stay_total_price / fn_available_rooms
SELECT p.proname                     AS function_name,
       pg_get_function_arguments(p.oid) AS arguments
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname LIKE 'fn_%'
ORDER BY 1, 2;

-- ----------------------------------------------------------------------------
-- 15) 自检 B：真的插临时数据验证约束（插入的都是临时数据，最后删除）
--     NOTICE 文案全部 ASCII：Windows GBK 终端显示中文 NOTICE 会乱码，入库本身没问题。
-- ----------------------------------------------------------------------------
DO $$
DECLARE
    v_type_id   bigint;
    v_room_id   bigint;
    v_cust_id   bigint;
    v_block_id  bigint;
    v_msg       text;
    v_price_cnt integer;
    v_price_sum numeric(10,2);
    v_total     numeric(10,2);
    v_avg       numeric(10,2);
BEGIN
    INSERT INTO room_type (name, bed_type, capacity, base_price)
    VALUES ('__自检房型__', 'double', 2, 100.00)
    RETURNING id INTO v_type_id;

    INSERT INTO room (room_type_id, room_no, floor, status)
    VALUES (v_type_id, '__TEST__', 99, 'available')
    RETURNING id INTO v_room_id;

    INSERT INTO customer (name, phone)
    VALUES ('__自检客户__', '00000000000')
    RETURNING id INTO v_cust_id;

    -- (1) 第一笔：12-01 入住，12-03 离店（占 12-01、12-02 两晚）
    --     故意把金额写成 1.00：若价格触发器没跑，下面 (2) 的断言就会失败
    INSERT INTO reservation (reservation_no, customer_id, room_id,
                             check_in_date, check_out_date,
                             price_per_night, total_amount, status)
    VALUES ('__TEST__-1', v_cust_id, v_room_id,
            DATE '2026-12-01', DATE '2026-12-03',
            1.00, 1.00, 'confirmed');

    -- (2) 逐日价格：2 晚 × 100 = 200，触发器应把总额与均价回写主表
    SELECT count(*), COALESCE(sum(price), 0)
      INTO v_price_cnt, v_price_sum
      FROM reservation_price
     WHERE reservation_id = (SELECT id FROM reservation WHERE reservation_no = '__TEST__-1');

    SELECT total_amount, price_per_night
      INTO v_total, v_avg
      FROM reservation
     WHERE reservation_no = '__TEST__-1';

    IF v_price_cnt <> 2 OR v_price_sum <> 200.00 OR v_total <> 200.00 OR v_avg <> 100.00 THEN
        RAISE EXCEPTION 'CHECK FAILED: rows=% sum=% total=% avg=% (expected 2 / 200.00 / 200.00 / 100.00)',
                        v_price_cnt, v_price_sum, v_total, v_avg;
    END IF;
    RAISE NOTICE 'CHECK OK: price rows=% sum=% total=% avg=%', v_price_cnt, v_price_sum, v_total, v_avg;

    -- (3) 与第一笔相交的第二笔预订，必须被 EXCLUDE 拒绝（23P01）
    BEGIN
        INSERT INTO reservation (reservation_no, customer_id, room_id,
                                 check_in_date, check_out_date,
                                 price_per_night, total_amount, status)
        VALUES ('__TEST__-2', v_cust_id, v_room_id,
                DATE '2026-12-02', DATE '2026-12-04',
                100.00, 200.00, 'pending');
        RAISE EXCEPTION 'CHECK FAILED: overlapping reservation was accepted, EXCLUDE not working';
    EXCEPTION
        WHEN exclusion_violation THEN
            GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT;
            RAISE NOTICE 'CHECK OK: overlap rejected by EXCLUDE, SQLSTATE=23P01 (%)', v_msg;
    END;

    -- (4) 与第一笔首尾相接（12-03 起），半开区间下不冲突，必须成功
    INSERT INTO reservation (reservation_no, customer_id, room_id,
                             check_in_date, check_out_date,
                             price_per_night, total_amount, status)
    VALUES ('__TEST__-3', v_cust_id, v_room_id,
            DATE '2026-12-03', DATE '2026-12-05',
            100.00, 200.00, 'pending');
    RAISE NOTICE 'CHECK OK: adjacent range accepted (half-open [in, out) semantics)';

    -- (5) 改期（12-03 ~ 12-06）后逐日明细应变成 3 行、总额 300
    UPDATE reservation
       SET check_out_date = DATE '2026-12-06'
     WHERE reservation_no = '__TEST__-3';

    SELECT count(*), COALESCE(sum(price), 0)
      INTO v_price_cnt, v_price_sum
      FROM reservation_price
     WHERE reservation_id = (SELECT id FROM reservation WHERE reservation_no = '__TEST__-3');

    SELECT total_amount, price_per_night
      INTO v_total, v_avg
      FROM reservation
     WHERE reservation_no = '__TEST__-3';

    IF v_price_cnt <> 3 OR v_price_sum <> 300.00 OR v_total <> 300.00 OR v_avg <> 100.00 THEN
        RAISE EXCEPTION 'CHECK FAILED: after date change rows=% sum=% total=% avg=% (expected 3 / 300.00 / 300.00 / 100.00)',
                        v_price_cnt, v_price_sum, v_total, v_avg;
    END IF;
    RAISE NOTICE 'CHECK OK: date change resynced to rows=% total=%', v_price_cnt, v_total;

    -- (6) 维修/停用区间：12-10 ~ 12-12 没有订单，允许登记
    INSERT INTO room_block (room_id, start_date, end_date, block_type, reason)
    VALUES (v_room_id, DATE '2026-12-10', DATE '2026-12-12', 'maintenance', '自检：维修')
    RETURNING id INTO v_block_id;
    RAISE NOTICE 'CHECK OK: room_block inserted (no conflicting orders)';

    -- (7) 与封禁区间重叠的预订，必须被 23514 拒绝
    BEGIN
        INSERT INTO reservation (reservation_no, customer_id, room_id,
                                 check_in_date, check_out_date,
                                 price_per_night, total_amount, status)
        VALUES ('__TEST__-4', v_cust_id, v_room_id,
                DATE '2026-12-11', DATE '2026-12-13',
                100.00, 200.00, 'pending');
        RAISE EXCEPTION 'CHECK FAILED: reservation overlapping room_block was accepted';
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'CHECK OK: overlap rejected by block, SQLSTATE=23514';
    END;

    -- (8) 与有效订单重叠的封禁区间，必须被 23514 拒绝
    BEGIN
        INSERT INTO room_block (room_id, start_date, end_date, block_type, reason)
        VALUES (v_room_id, DATE '2026-12-02', DATE '2026-12-06', 'maintenance', '自检：与订单冲突');
        RAISE EXCEPTION 'CHECK FAILED: room_block overlapping active order was accepted';
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'CHECK OK: room_block rejected by active order, SQLSTATE=23514';
    END;

    -- (9) 清理临时数据（预订删除会级联删掉 reservation_price）
    DELETE FROM room_block  WHERE id = v_block_id;
    DELETE FROM reservation WHERE customer_id = v_cust_id;
    DELETE FROM customer    WHERE id = v_cust_id;
    DELETE FROM room        WHERE id = v_room_id;
    DELETE FROM room_type   WHERE id = v_type_id;

    RAISE NOTICE 'CHECK OK: temp self-check data cleaned up';
END;
$$;

-- ----------------------------------------------------------------------------
-- 16) 自检 C：视图与函数可用性（02 先于 03_seed 执行时库为空，计数为 0 属正常）
-- ----------------------------------------------------------------------------
SELECT count(*) AS available_rooms_demo
FROM fn_available_rooms(DATE '2026-12-10', DATE '2026-12-12');

SELECT count(*) AS reservation_detail_rows FROM v_reservation_detail;
SELECT count(*) AS check_in_detail_rows    FROM v_check_in_detail;

-- 完成提示
SELECT '02_constraints.sql 执行完成' AS result;
