-- =============================================================================
-- sql/04_queries.sql  报告第 4 章 / 演示用查询（只读，不改数据）
--
-- 对应 docs/01-功能清单.md 第 8 节的 6 类 SQL 任务，全部为多表关联或统计查询。
-- 日期锚点统一取 2026-12-15（演示库「今天」），跨年片段用 2026 全年。
--
-- 执行：
--   chcp 65001
--   psql -U postgres -d yunqi_hotel -v ON_ERROR_STOP=1 -f sql/04_queries.sql
-- 报告里贴的查询结果截图，必须由本文件原样执行得到，不要手改数字。
-- 需要换演示区间时，改各查询里的 DATE 字面量即可（不要用 CURRENT_DATE，演示库是固定日期）。
-- =============================================================================

\set ON_ERROR_STOP on
\encoding UTF8

SET search_path TO public;

-- ----------------------------------------------------------------------------
-- Q1 指定日期区间的可用房间（F03 可用房查询）
--    两种写法：① 函数封装（页面实际调用）；② 显式 NOT EXISTS（报告 4.1 讲解用）
-- ----------------------------------------------------------------------------

-- Q1-a 页面实际调用的函数
SELECT room_no          AS 房号,
       room_type_name   AS 房型,
       capacity         AS 可住人数,
       floor            AS 楼层,
       price            AS 每晚房价
FROM fn_available_rooms(DATE '2026-12-20', DATE '2026-12-22')
ORDER BY price, room_no;

-- Q1-b 等价显式实现（与函数体逐条对齐：房态排除维修/停用 + 房型启用 + 半开区间 + 三态过滤）
--      与 Q1-a 应返回同样的 34 间；若两处数字不一致说明有一边被改坏了
SELECT r.room_no        AS 房号,
       rt.name          AS 房型,
       rt.capacity      AS 可住人数,
       rt.base_price    AS 标准价
FROM room r
JOIN room_type rt ON rt.id = r.room_type_id
WHERE r.status NOT IN ('maintenance', 'disabled')
  AND rt.is_active
  AND NOT EXISTS (
        SELECT 1
        FROM reservation v
        WHERE v.room_id = r.id
          AND v.status IN ('pending', 'confirmed', 'checked_in')
          AND v.during && daterange(DATE '2026-12-20', DATE '2026-12-22', '[)')
      )
ORDER BY rt.base_price, r.room_no;

-- ----------------------------------------------------------------------------
-- Q2 某客户的历史入住与支付明细（F09 明细，5 表 JOIN）
--    customer → reservation → room → check_in_record → payment
-- ----------------------------------------------------------------------------
SELECT c.name                                   AS 客户,
       c.phone                                  AS 手机,
       r.reservation_no                         AS 预订号,
       r.status                                 AS 预订状态,
       rt.name                                  AS 房型,
       rm.room_no                               AS 房号,
       r.check_in_date                          AS 入住日期,
       r.check_out_date                         AS 离店日期,
       ck.check_in_at                           AS 实际入住时间,
       ck.actual_checkout_at                    AS 实际退房时间,
       ck.total_charge                          AS 应收合计,
       ck.deposit_amount                        AS 押金,
       COALESCE(SUM(p.amount) FILTER (WHERE p.kind <> 'refund'), 0) AS 累计支付,
       COALESCE(SUM(p.amount) FILTER (WHERE p.kind = 'refund'), 0) AS 累计退款
FROM customer c
JOIN reservation r          ON r.customer_id = c.id
JOIN room rm                ON rm.id = r.room_id
JOIN room_type rt           ON rt.id = rm.room_type_id
LEFT JOIN check_in_record ck ON ck.reservation_id = r.id
LEFT JOIN payment p          ON p.check_in_record_id = ck.id
WHERE c.name = '张伟'
GROUP BY c.name, c.phone, r.reservation_no, r.status, rt.name, rm.room_no,
         r.check_in_date, r.check_out_date, ck.check_in_at, ck.actual_checkout_at,
         ck.total_charge, ck.deposit_amount
ORDER BY r.check_in_date;

-- ----------------------------------------------------------------------------
-- Q3 各房型月度入住率（F09 统计）
--    已售房夜 = 每笔有效预订按天展开（离店日不计），可售房夜 = 房型房间数 × 当月天数
--    统计区间取 2026-09 ~ 2027-01（演示数据集中在这 5 个月，避免大片 0.00 的空月）
-- ----------------------------------------------------------------------------
WITH month_series AS (
    SELECT d::date AS month_start
    FROM generate_series(DATE '2026-09-01', DATE '2027-01-01', INTERVAL '1 month') AS d
),
sold AS (
    SELECT rt.id                            AS room_type_id,
           date_trunc('month', stay)::date  AS month_start,
           count(*)                         AS sold_nights
    FROM reservation r
    JOIN room rm      ON rm.id = r.room_id
    JOIN room_type rt ON rt.id = rm.room_type_id
    CROSS JOIN LATERAL generate_series(r.check_in_date, r.check_out_date - 1, INTERVAL '1 day') AS stay
    WHERE r.status IN ('confirmed', 'checked_in', 'checked_out')
    GROUP BY 1, 2
),
sellable AS (
    SELECT rt.id AS room_type_id,
           rt.name,
           ms.month_start,
           count(rm.id) * ((ms.month_start + INTERVAL '1 month')::date - ms.month_start) AS sellable_nights
    FROM month_series ms
    CROSS JOIN room_type rt
    LEFT JOIN room rm ON rm.room_type_id = rt.id
    WHERE rt.is_active
    GROUP BY rt.id, rt.name, ms.month_start
)
SELECT s.name                                    AS 房型,
       s.month_start                             AS 月份,
       COALESCE(so.sold_nights, 0)               AS 已售房夜,
       s.sellable_nights                         AS 可售房夜,
       round(COALESCE(so.sold_nights, 0)::numeric / s.sellable_nights * 100, 2) AS 入住率百分比
FROM sellable s
LEFT JOIN sold so ON so.room_type_id = s.room_type_id AND so.month_start = s.month_start
ORDER BY s.month_start, s.name;

-- ----------------------------------------------------------------------------
-- Q4 月度营业收入按支付方式拆分（F09 图表）
--    口径：收入 = room_fee + service_fee；deposit 是押金不计收入；refund 冲减收入
--    注意：退款可能落在与房费不同的月份，故个别分组净收入为负 —— 报告中说明
--    「按收款月份统计、退款冲减当月」这一口径即可，不是数据错误
-- ----------------------------------------------------------------------------
SELECT date_trunc('month', p.paid_at)::date                                   AS 月份,
       p.method                                                               AS 支付方式,
       count(*)                                                               AS 笔数,
       COALESCE(SUM(p.amount) FILTER (WHERE p.kind IN ('room_fee', 'service_fee')), 0) AS 收入,
       COALESCE(SUM(p.amount) FILTER (WHERE p.kind = 'deposit'), 0)           AS 押金,
       COALESCE(SUM(p.amount) FILTER (WHERE p.kind = 'refund'), 0)            AS 退款,
       COALESCE(SUM(p.amount) FILTER (WHERE p.kind IN ('room_fee', 'service_fee')), 0)
         - COALESCE(SUM(p.amount) FILTER (WHERE p.kind = 'refund'), 0)        AS 净收入
FROM payment p
WHERE p.paid_at >= TIMESTAMPTZ '2026-01-01 00:00:00+08'
  AND p.paid_at <  TIMESTAMPTZ '2027-01-01 00:00:00+08'
GROUP BY 1, p.method
ORDER BY 1, 2;

-- Q4-b 月度营收总览（按月一种口径，给折线图用）
SELECT date_trunc('month', p.paid_at)::date AS 月份,
       count(DISTINCT p.check_in_record_id) AS 涉及入住记录,
       COALESCE(SUM(p.amount) FILTER (WHERE p.kind IN ('room_fee', 'service_fee')), 0)
         - COALESCE(SUM(p.amount) FILTER (WHERE p.kind = 'refund'), 0) AS 净收入
FROM payment p
WHERE p.paid_at >= TIMESTAMPTZ '2026-01-01 00:00:00+08'
  AND p.paid_at <  TIMESTAMPTZ '2027-01-01 00:00:00+08'
GROUP BY 1
ORDER BY 1;

-- ----------------------------------------------------------------------------
-- Q5 最受欢迎房型 Top 3（订单数 + 房夜数双口径，RANK 窗口函数）
-- ----------------------------------------------------------------------------
WITH t AS (
    SELECT rt.name                              AS 房型,
           count(*)                             AS 订单数,
           SUM(r.check_out_date - r.check_in_date) AS 房夜数,
           SUM(r.total_amount)                  AS 预订金额
    FROM reservation r
    JOIN room rm      ON rm.id = r.room_id
    JOIN room_type rt ON rt.id = rm.room_type_id
    WHERE r.status IN ('confirmed', 'checked_in', 'checked_out')
    GROUP BY rt.name
)
SELECT 房型, 订单数, 房夜数, 预订金额,
       RANK() OVER (ORDER BY 订单数 DESC) AS 订单数排名,
       RANK() OVER (ORDER BY 房夜数 DESC) AS 房夜数排名
FROM t
ORDER BY 订单数 DESC, 房夜数 DESC
LIMIT 3;

-- ----------------------------------------------------------------------------
-- Q6 长期空闲房间与取消率（F09 经营预警）
-- ----------------------------------------------------------------------------

-- Q6-a 近 90 天（2026-09-16 起）无入住、且未来 45 天也无预订的房间
--      两个条件都要求，否则「只有远期预订」的房间会被误判成长期空闲
SELECT r.room_no  AS 房号,
       rt.name    AS 房型,
       r.floor    AS 楼层,
       r.status   AS 当前房态,
       (SELECT max(rv.check_out_date) FROM reservation rv WHERE rv.room_id = r.id) AS 最近离店日
FROM room r
JOIN room_type rt ON rt.id = r.room_type_id
WHERE NOT EXISTS (
        SELECT 1
        FROM reservation rv
        WHERE rv.room_id = r.id
          AND rv.during && daterange(DATE '2026-09-16', DATE '2026-12-15', '[)')
      )
  AND NOT EXISTS (
        SELECT 1
        FROM reservation rv
        WHERE rv.room_id = r.id
          AND rv.status IN ('pending', 'confirmed', 'checked_in')
          AND rv.during && daterange(DATE '2026-12-15', DATE '2027-01-29', '[)')
      )
ORDER BY r.room_no;

-- Q6-b 各预订来源的取消率与未到店率
SELECT r.source                                                             AS 预订来源,
       count(*)                                                             AS 订单总数,
       count(*) FILTER (WHERE r.status = 'cancelled')                       AS 取消数,
       count(*) FILTER (WHERE r.status = 'no_show')                         AS 未到店数,
       round(count(*) FILTER (WHERE r.status = 'cancelled')::numeric
             / count(*) * 100, 2)                                           AS 取消率百分比
FROM reservation r
GROUP BY r.source
ORDER BY 取消率百分比 DESC;

-- ----------------------------------------------------------------------------
-- Q7 视图演示：入住记录结算与余额（v_check_in_detail 已封装支付汇总）
--    balance > 0 表示在店尚未结清房费；= 0 表示已结清
-- ----------------------------------------------------------------------------
SELECT r.reservation_no      AS 预订号,
       rm.room_no            AS 房号,
       v.guest_name          AS 客人,
       v.check_in_at         AS 入住时间,
       v.actual_checkout_at  AS 退房时间,
       v.deposit_amount      AS 押金,
       v.room_charge         AS 房费,
       v.service_charge      AS 服务费,
       v.total_charge        AS 应收合计,
       v.settled_amount      AS 已结算,
       v.balance             AS 余额
FROM v_check_in_detail v
JOIN reservation r ON r.id = v.reservation_id
JOIN room rm       ON rm.id = r.room_id
ORDER BY v.check_in_at DESC
LIMIT 10;

-- ----------------------------------------------------------------------------
-- Q8 约束验证演示：复制一条活跃预订的区间、换个客户再插入 → 应被排他约束拒绝
--    放在 DO 块里捕获异常并打 NOTICE，脚本不会中断，也不会留下演示数据
-- ----------------------------------------------------------------------------
DO $$
DECLARE
    v_customer  bigint;
    v_room      bigint;
    v_in        date;
    v_out       date;
    v_price     numeric(10, 2);
    v_guest     integer;
BEGIN
    -- 取一条已确认预订作为「已被占用」的区间
    SELECT r.customer_id, r.room_id, r.check_in_date, r.check_out_date,
           r.price_per_night, r.guest_count
      INTO v_customer, v_room, v_in, v_out, v_price, v_guest
    FROM reservation r
    WHERE r.status = 'confirmed'
    ORDER BY r.id
    LIMIT 1;

    BEGIN
        -- 换个客户（避免撞 uq_reservation_active_customer 的部分唯一索引），
        -- 房间与区间完全相同 → 只可能触发 ex_reservation_room_overlap
        INSERT INTO reservation (reservation_no, customer_id, room_id, check_in_date, check_out_date,
                                 guest_count, price_per_night, total_amount, status, source, remark)
        VALUES ('DEMO-OVERLAP', 7, v_room, v_in, v_out,
                v_guest, v_price, v_price * (v_out - v_in), 'pending', 'phone',
                'Q8 演示：刻意制造区间重叠');

        -- 走到这里说明约束没生效，清掉演示行并报错
        DELETE FROM reservation WHERE reservation_no = 'DEMO-OVERLAP';
        RAISE EXCEPTION 'Q8 FAILED: overlapping reservation was inserted, check ex_reservation_room_overlap';
    EXCEPTION
        WHEN exclusion_violation THEN
            -- 消息用 ASCII 写：Windows 控制台下 psql 不转换服务端消息的编码，
            -- 中文 NOTICE 在 cp936 终端与 UTF-8 落盘之间必有一边乱码，ASCII 两边都安全
            RAISE NOTICE 'Q8 OK: room % interval [%, %) rejected by ex_reservation_room_overlap, SQLSTATE=%',
                         v_room, v_in, v_out, SQLSTATE;
    END;
END $$;

-- ----------------------------------------------------------------------------
-- 结论：以上查询全部可直接在演示库执行；Q8 的 NOTICE 文本可作为报告 4.3 异常处理证据。
-- ----------------------------------------------------------------------------
SELECT '04_queries.sql 执行完成' AS result;
