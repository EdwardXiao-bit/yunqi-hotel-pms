\set ON_ERROR_STOP on
\encoding UTF8

-- =============================================================================
-- 02_constraints.sql —— 数据库级业务约束（本项目 50% 得分点的技术核心）
-- 前置：先执行 sql/01_schema.sql（表已建好）。本脚本可重复执行。
--
-- 内容：
--   1) btree_gist 扩展（GiST 索引上做 bigint 等值比较，EXCLUDE 必需）
--   2) 生成列 during / valid_during（日期区间 → 范围类型）
--   3) EXCLUDE 排他约束：同一房间的生效预订不得重叠；同房型价格方案区间不得重叠
--   4) 部分唯一索引：同一客户对同一房间同一区间不得重复占用
--   5) updated_at 自动维护触发器 + 房态变更自动写日志触发器
--   6) 视图 v_reservation_detail / v_check_in_detail，函数 fn_available_rooms()
--   7) 自检：列出约束/触发器，并实际插入重叠预订验证 23P01 被拒绝
--
-- 为什么能防超卖：reservation 的 (room_id, during) 在 status 生效时互斥，
-- 任何两个“同一房间 + 日期相交 + 状态未终结”的预订都不可能同时存在，
-- 并发插入时第二个会拿到 SQLSTATE 23P01（exclusion_violation），由 Django 映射为中文提示。
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
DROP INDEX IF EXISTS uq_reservation_active_customer;

ALTER TABLE reservation DROP COLUMN IF EXISTS during;
ALTER TABLE rate_plan   DROP COLUMN IF EXISTS valid_during;

-- ----------------------------------------------------------------------------
-- 3) 生成列：日期区间 → 范围类型
--    reservation 用半开区间 [check_in, check_out)：
--      12-01 入住、12-03 离店 ⇒ 占用 12-01、12-02 两晚，12-03 当天可换人入住。
--    rate_plan 用闭区间 [valid_from, valid_to]：价格方案“到哪天为止”含当天。
-- ----------------------------------------------------------------------------
ALTER TABLE reservation
    ADD COLUMN during daterange
    GENERATED ALWAYS AS (daterange(check_in_date, check_out_date, '[)')) STORED;

ALTER TABLE rate_plan
    ADD COLUMN valid_during daterange
    GENERATED ALWAYS AS (daterange(valid_from, valid_to, '[]')) STORED;

COMMENT ON COLUMN reservation.during    IS '占用区间（生成列）：daterange(check_in_date, check_out_date, ''[)'')，半开区间';
COMMENT ON COLUMN rate_plan.valid_during IS '生效区间（生成列）：daterange(valid_from, valid_to, ''[]'')，闭区间';

-- ----------------------------------------------------------------------------
-- 4) EXCLUDE 排他约束（核心）
--    WHERE 子句限定只对“仍占用房间”的状态生效：
--      已退房/已取消/未到店 的记录不参与互斥，历史单不阻塞新房。
-- ----------------------------------------------------------------------------
ALTER TABLE reservation
    ADD CONSTRAINT ex_reservation_room_overlap
    EXCLUDE USING gist (room_id WITH =, during WITH &&)
    WHERE (status IN ('pending', 'confirmed', 'checked_in'));

ALTER TABLE rate_plan
    ADD CONSTRAINT ex_rate_plan_no_overlap
    EXCLUDE USING gist (room_type_id WITH =, valid_during WITH &&);

COMMENT ON CONSTRAINT ex_reservation_room_overlap ON reservation
    IS '防超卖：同一房间在 [check_in, check_out) 内不得有两笔生效预订（pending/confirmed/checked_in）';
COMMENT ON CONSTRAINT ex_rate_plan_no_overlap ON rate_plan
    IS '同一房型的价格方案生效区间不得重叠';

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

COMMENT ON FUNCTION fn_log_room_status() IS '触发器函数：room.status 变更后写 room_status_log';

CREATE TRIGGER trg_room_status_log
    AFTER UPDATE OF status ON room
    FOR EACH ROW EXECUTE FUNCTION fn_log_room_status();

-- ----------------------------------------------------------------------------
-- 8) 视图：列表页与报告 4 章直接引用
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
       rt.capacity
FROM reservation r
JOIN customer  c  ON c.id  = r.customer_id
JOIN room      rm ON rm.id = r.room_id
JOIN room_type rt ON rt.id = rm.room_type_id;

COMMENT ON VIEW v_reservation_detail IS '预订详情：预订 + 客户 + 房间 + 房型，列表页与多表查询用';

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
-- 9) 函数：可用房查询（F03 的服务端查询，避开 ORM，报告 4 章可贴 SQL）
--    判定：房态非维修/停用、房型在售、且不存在与 [check_in, check_out) 相交的生效预订。
--    价格取入住首晚适用的价格方案，没有方案则用房型标准价。
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
    price          numeric
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF p_check_in IS NULL OR p_check_out IS NULL THEN
        RAISE EXCEPTION '入住日期与离店日期不能为空' USING ERRCODE = '22023';
    END IF;
    IF p_check_out <= p_check_in THEN
        RAISE EXCEPTION '离店日期必须晚于入住日期' USING ERRCODE = '22023';
    END IF;

    RETURN QUERY
    SELECT rm.id,
           rm.room_no,
           rt.id,
           rt.name,
           rt.capacity,
           rm.floor,
           COALESCE(rp.price, rt.base_price)
    FROM room rm
    JOIN room_type rt ON rt.id = rm.room_type_id
    LEFT JOIN rate_plan rp
           ON rp.room_type_id = rt.id
          AND rp.valid_during @> p_check_in
    WHERE rm.status NOT IN ('maintenance', 'disabled')
      AND rt.is_active
      AND (p_room_type_id IS NULL OR rt.id = p_room_type_id)
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
    IS '可用房查询：给定入住/离店日期（半开区间）与可选房型，返回可用房间及首晚价格';

-- ----------------------------------------------------------------------------
-- 10) 自检 A：列出排他约束与关键索引
-- ----------------------------------------------------------------------------
SELECT conrelid::regclass AS table_name,
       conname            AS constraint_name,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE contype = 'x'
ORDER BY 1, 2;

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN ('uq_reservation_active_customer')
ORDER BY indexname;

SELECT tgname AS trigger_name,
       tgrelid::regclass AS table_name
FROM pg_trigger
WHERE NOT tgisinternal
ORDER BY 2, 1;

-- ----------------------------------------------------------------------------
-- 11) 自检 B：真的插一笔重叠预订，验证被 23P01 拒绝（插入的都是临时数据，最后删除）
-- ----------------------------------------------------------------------------
DO $$
DECLARE
    v_type_id bigint;
    v_room_id bigint;
    v_cust_id bigint;
    v_msg     text;
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

    -- 第一笔：12-01 入住，12-03 离店（占 12-01、12-02 两晚）
    INSERT INTO reservation (reservation_no, customer_id, room_id,
                             check_in_date, check_out_date,
                             price_per_night, total_amount, status)
    VALUES ('__TEST__-1', v_cust_id, v_room_id,
            DATE '2026-12-01', DATE '2026-12-03',
            100.00, 200.00, 'confirmed');

    -- 第二笔：与第一笔相交（12-02 ~ 12-04），必须被 EXCLUDE 拒绝
    BEGIN
        INSERT INTO reservation (reservation_no, customer_id, room_id,
                                 check_in_date, check_out_date,
                                 price_per_night, total_amount, status)
        VALUES ('__TEST__-2', v_cust_id, v_room_id,
                DATE '2026-12-02', DATE '2026-12-04',
                100.00, 200.00, 'pending');
        RAISE EXCEPTION '自检失败：重叠预订竟然插入成功，EXCLUDE 未生效';
    EXCEPTION
        WHEN exclusion_violation THEN
            GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT;
            RAISE NOTICE '自检通过：重叠预订被拒绝（SQLSTATE 23P01）→ %', v_msg;
    END;

    -- 第三笔：与第一笔首尾相接（12-03 ~ 12-05），半开区间下不冲突，必须成功
    INSERT INTO reservation (reservation_no, customer_id, room_id,
                             check_in_date, check_out_date,
                             price_per_night, total_amount, status)
    VALUES ('__TEST__-3', v_cust_id, v_room_id,
            DATE '2026-12-03', DATE '2026-12-05',
            100.00, 200.00, 'pending');
    RAISE NOTICE '自检通过：相邻区间（12-03 起）不冲突，半开区间语义正确';

    -- 清理临时数据（先删预订，因 FK 为 RESTRICT）
    DELETE FROM reservation WHERE customer_id = v_cust_id;
    DELETE FROM customer    WHERE id = v_cust_id;
    DELETE FROM room        WHERE id = v_room_id;
    DELETE FROM room_type   WHERE id = v_type_id;

    RAISE NOTICE '自检数据已清理';
END;
$$;

-- ----------------------------------------------------------------------------
-- 12) 自检 C：视图与函数可用性
-- ----------------------------------------------------------------------------
SELECT count(*) AS available_rooms_demo
FROM fn_available_rooms(DATE '2026-12-10', DATE '2026-12-12');

SELECT count(*) AS reservation_detail_rows FROM v_reservation_detail;
SELECT count(*) AS check_in_detail_rows    FROM v_check_in_detail;

-- 完成提示
SELECT '02_constraints.sql 执行完成' AS result;
