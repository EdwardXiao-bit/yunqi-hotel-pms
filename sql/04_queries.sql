-- =============================================================================
-- sql/04_queries.sql  报告第 4 章 / 演示用查询（只读，不改数据）
--
-- 对应 docs/01-功能清单.md 第 8 节的 6 类 SQL 任务，全部为多表关联或统计查询。
-- 日期锚点统一取 2026-12-15（演示库「今天」），跨年片段用 2026 全年。
--
-- 口径已对齐 13 表 / 4 态房态版本：
--   * room.status 只有 available / cleaning / maintenance / disabled，
--     不存在 reserved / occupied —— “已预订”“入住中”由 reservation / check_in_record 推导；
--   * 维修与停用用 room_block 的日期区间（during 生成列，半开区间 [start, end)）表达，
--     可售房夜要按区间扣减；
--   * 营业收入按退房结算日期（check_in_record.actual_checkout_at）归月，
--     押金不计收入、退款冲减同月；
--   * 逐日成交价在 reservation_price 里，由触发器 fn_sync_reservation_prices() 维护，
--     本脚本只读，不手工补明细。
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
--    两种写法必须逐条等价：① 函数封装（页面实际调用）；② 显式 NOT EXISTS（报告 4.1 讲解用）
--    判定条件（两边完全一致，缺一条就会比函数更严或更松）：
--      a. 房型在售：rt.is_active
--      b. 房态不是 maintenance/disabled：与函数体逐字一致
--         （维修/停用的“未来是否可售”由 room_block 的日期区间决定；房态只是当下标签，
--           两种口径必须同时排除，否则查询结果会比函数多出正在维修/停用的房间）
--      c. 不存在与该区间相交的维修/停用区间：NOT EXISTS (room_block ... during && 查询区间)
--      d. 不存在与该区间相交的生效预订：NOT EXISTS (reservation ... status IN 三态 AND during &&)
--    价格口径（两边一致）：逐晚取该晚适用的 rate_plan 价（rp.valid_during @> 当晚），
--      没有方案则用房型标准价，多条命中时取 valid_from 最新（与函数 ORDER BY 一致）；
--      total_price = 各晚合计 round 2 位；avg_price = 合计 ÷ 晚数 round 2 位
--      —— 不是「各晚均价的平均」，两者取整后可能差 1 分，要对齐函数就按「先合计再除」写。
--    半开区间：离店日当天不占房，所以 [2026-12-20, 2026-12-22) 只算 12-20、12-21 两晚。
-- ----------------------------------------------------------------------------

-- Q1-a 页面实际调用的函数（返回列即新签名：含 avg_price / total_price）
SELECT room_id          AS 房间ID,
       room_no          AS 房号,
       room_type_name   AS 房型,
       capacity         AS 可住人数,
       floor            AS 楼层,
       base_price       AS 标准价,
       avg_price        AS 每晚均价,
       total_price      AS 区间合计
FROM fn_available_rooms(DATE '2026-12-20', DATE '2026-12-22')
ORDER BY floor, room_no;

-- Q1-b 等价显式实现：行集与 Q1-a 逐条相同（行数、房号、房价都要一致）
--      若两处结果不一致，说明函数体或本段有一条被改坏，报告 4.1 就是靠这条对照做正确性证据
SELECT r.id                       AS 房间ID,
       r.room_no                  AS 房号,
       rt.name                    AS 房型,
       rt.capacity                AS 可住人数,
       r.floor                    AS 楼层,
       rt.base_price              AS 标准价,
       round(sum(n.price) / count(*), 2) AS 每晚均价,
       round(sum(n.price), 2)     AS 区间合计
FROM room r
JOIN room_type rt ON rt.id = r.room_type_id
CROSS JOIN LATERAL (
    SELECT COALESCE(
             (SELECT rp.price
              FROM rate_plan rp
              WHERE rp.room_type_id = rt.id
                AND rp.valid_during @> g.night
              ORDER BY rp.valid_from DESC, rp.id DESC
              LIMIT 1),
             rt.base_price) AS price
    FROM (SELECT gs::date AS night
          FROM generate_series(DATE '2026-12-20'::timestamp,
                               (DATE '2026-12-22' - 1)::timestamp,
                               INTERVAL '1 day') AS gs) AS g
) AS n(price)
WHERE r.status NOT IN ('maintenance', 'disabled')
  AND rt.is_active
  AND NOT EXISTS (
        SELECT 1
        FROM room_block b
        WHERE b.room_id = r.id
          AND b.during && daterange(DATE '2026-12-20', DATE '2026-12-22', '[)')
      )
  AND NOT EXISTS (
        SELECT 1
        FROM reservation v
        WHERE v.room_id = r.id
          AND v.status IN ('pending', 'confirmed', 'checked_in')
          AND v.during && daterange(DATE '2026-12-20', DATE '2026-12-22', '[)')
      )
GROUP BY r.id, r.room_no, rt.name, rt.capacity, r.floor, rt.base_price
ORDER BY r.floor, r.room_no;

-- ----------------------------------------------------------------------------
-- Q2 某客户的历史入住与支付明细（F09 明细，5 表 JOIN）
--    customer → reservation → room → check_in_record → payment
--    行数、累计支付/退款都随种子数据重跑而变化，报告里以当次执行结果为准，不要写死数字。
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
--    口径（分子分母都要能自圆其说，报告 4.2 直接引用）：
--      已售房夜 = 有效预订（confirmed / checked_in / checked_out）按天展开，离店日不计；
--      可售房夜 = 该房型房间数 × 当月天数 − 该房型当月在修/停用的房夜；
--      维修/停用房夜按 room_block 与月份的区间交集算：
--          GREATEST(0, LEAST(end_date, 月末) − GREATEST(start_date, 月初))
--        （room_block.during 是半开区间，end_date 当天已可售，所以交集长度正好是占用晚数；
--          maintenance 与 disabled 两种 block_type 都要扣，它们都不可售）；
--      入住率 = 已售房夜 ÷ 可售房夜 × 100，round 2 位。
--    统计区间取 2026-09 ~ 2027-01（演示数据集中在这 5 个月，避免大片 0.00 的空月）。
-- ----------------------------------------------------------------------------
WITH month_series AS (
    SELECT d::date                              AS month_start,
           (d + INTERVAL '1 month')::date       AS month_end
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
blocked AS (
    -- 每个房型每个月被维修/停用占掉的房夜（两种 block_type 都扣）
    SELECT rt.id AS room_type_id,
           ms.month_start,
           sum(GREATEST(0,
                   LEAST(b.end_date, ms.month_end)
                 - GREATEST(b.start_date, ms.month_start))) AS blocked_nights
    FROM month_series ms
    CROSS JOIN room_type rt
    JOIN room rm      ON rm.room_type_id = rt.id
    JOIN room_block b ON b.room_id = rm.id
    WHERE b.during && daterange(ms.month_start, ms.month_end, '[)')
    GROUP BY rt.id, ms.month_start
),
sellable AS (
    SELECT rt.id AS room_type_id,
           rt.name,
           ms.month_start,
           count(rm.id) * (ms.month_end - ms.month_start)
             - COALESCE(bl.blocked_nights, 0) AS sellable_nights
    FROM month_series ms
    CROSS JOIN room_type rt
    LEFT JOIN room rm ON rm.room_type_id = rt.id
    LEFT JOIN blocked bl ON bl.room_type_id = rt.id AND bl.month_start = ms.month_start
    WHERE rt.is_active
    GROUP BY rt.id, rt.name, ms.month_start, ms.month_end, bl.blocked_nights
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
--    三条口径（缺一条数字就对不上账，报告 4.2 要写明）：
--      1) 归月方式：按退房结算日期归月 —— date_trunc('month', cir.actual_checkout_at)，
--         只统计已退房（reservation.status = 'checked_out' 且 actual_checkout_at 非空）；
--         不是按收款日期（paid_at）归月，也不是按入住日期。
--      2) 收入范围：kind IN ('room_fee', 'service_fee')；押金（deposit）是代收代付，不计收入。
--      3) 退款：kind = 'refund' 冲减同一结算月（同一笔入住记录的所有流水归到它的结算月）。
--    说明：一笔入住记录的房费、服务费、押金、退款都按它的结算月归集，
--          因此单月出现负数也可能是正常业务（当月结算、次月才退款的情况不会跨月串账）。
-- ----------------------------------------------------------------------------
WITH settled AS (
    SELECT cir.id                                        AS check_in_record_id,
           date_trunc('month', cir.actual_checkout_at)::date AS month_start
    FROM check_in_record cir
    JOIN reservation r ON r.id = cir.reservation_id
    WHERE r.status = 'checked_out'
      AND cir.actual_checkout_at IS NOT NULL
),
flows AS (
    SELECT s.month_start, s.check_in_record_id, p.method, p.kind, p.amount
    FROM settled s
    JOIN payment p ON p.check_in_record_id = s.check_in_record_id
    WHERE s.month_start >= DATE '2026-01-01'
      AND s.month_start <  DATE '2027-01-01'
)
SELECT month_start                                                             AS 月份,
       method                                                                  AS 支付方式,
       count(*)                                                                AS 笔数,
       COALESCE(SUM(amount) FILTER (WHERE kind IN ('room_fee', 'service_fee')), 0) AS 收入,
       COALESCE(SUM(amount) FILTER (WHERE kind = 'deposit'), 0)                AS 押金,
       COALESCE(SUM(amount) FILTER (WHERE kind = 'refund'), 0)                 AS 退款,
       COALESCE(SUM(amount) FILTER (WHERE kind IN ('room_fee', 'service_fee')), 0)
         - COALESCE(SUM(amount) FILTER (WHERE kind = 'refund'), 0)             AS 净收入
FROM flows
GROUP BY 1, 2
ORDER BY 1, 2;

-- Q4-b 月度营收总览（与 Q4 同口径，按月一种口径，给折线图用）
WITH settled AS (
    SELECT cir.id                                        AS check_in_record_id,
           date_trunc('month', cir.actual_checkout_at)::date AS month_start
    FROM check_in_record cir
    JOIN reservation r ON r.id = cir.reservation_id
    WHERE r.status = 'checked_out'
      AND cir.actual_checkout_at IS NOT NULL
),
flows AS (
    SELECT s.month_start, s.check_in_record_id, p.kind, p.amount
    FROM settled s
    JOIN payment p ON p.check_in_record_id = s.check_in_record_id
    WHERE s.month_start >= DATE '2026-01-01'
      AND s.month_start <  DATE '2027-01-01'
)
SELECT month_start                                                             AS 月份,
       count(DISTINCT check_in_record_id)                                      AS 涉及入住记录,
       COALESCE(SUM(amount) FILTER (WHERE kind IN ('room_fee', 'service_fee')), 0) AS 收入,
       COALESCE(SUM(amount) FILTER (WHERE kind = 'refund'), 0)                 AS 退款,
       COALESCE(SUM(amount) FILTER (WHERE kind IN ('room_fee', 'service_fee')), 0)
         - COALESCE(SUM(amount) FILTER (WHERE kind = 'refund'), 0)             AS 净收入
FROM flows
GROUP BY 1
ORDER BY 1;

-- ----------------------------------------------------------------------------
-- Q5 最受欢迎房型 Top 3（订单数 + 房夜数双口径，RANK 窗口函数）
--    「房夜数」用 check_in_record 的实际入住区间（actual_checkout_at::date − check_in_at::date），
--    不是订单计划区间（check_out_date − check_in_date）：提前退房、延住都会让两者不同，
--    用实际区间才能和经营口径对上。没有入住记录的订单（未到店/未入住）退回计划区间。
--    「计划房夜数」一列并列给出，报告里说明两者的差异来源。
-- ----------------------------------------------------------------------------
WITH t AS (
    SELECT rt.name                              AS 房型,
           count(*)                             AS 订单数,
           SUM(COALESCE(cir.actual_checkout_at::date - cir.check_in_at::date,
                        r.check_out_date - r.check_in_date)) AS 房夜数,
           SUM(r.check_out_date - r.check_in_date)       AS 计划房夜数,
           SUM(r.total_amount)                  AS 预订金额
    FROM reservation r
    JOIN room rm      ON rm.id = r.room_id
    JOIN room_type rt ON rt.id = rm.room_type_id
    LEFT JOIN check_in_record cir ON cir.reservation_id = r.id
    WHERE r.status IN ('confirmed', 'checked_in', 'checked_out')
    GROUP BY rt.name
)
SELECT 房型, 订单数, 房夜数, 计划房夜数, 预订金额,
       RANK() OVER (ORDER BY 订单数 DESC) AS 订单数排名,
       RANK() OVER (ORDER BY 房夜数 DESC) AS 房夜数排名
FROM t
ORDER BY 订单数 DESC, 房夜数 DESC
LIMIT 3;

-- ----------------------------------------------------------------------------
-- Q6 长期空闲房间与取消率（F09 经营预警）
-- ----------------------------------------------------------------------------

-- Q6-a 近 90 天（2026-09-16 起）无实际入住、且未来 45 天（到 2027-01-29）也无活跃订单的房间
--      两个条件都要求，否则「只有远期预订」的房间会被误判成长期空闲。
--      口径说明：本查询衡量的是**房间经营效率**（有没有人住），不是可售率，
--      所以不扣 room_block 的维修/停用区间 —— 一间正在维修、本来就不该卖的房，
--      仍然应当出现在「长期空闲」名单里让管理员复核，而不是被过滤掉。
--      要算可售率请用 Q3（那边才扣维修/停用）。
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
--      取消率 = 已取消订单数 ÷ 同期创建的订单总数；
--      no_show（未到店）单独一列，计入分母但不计入分子 —— 未到店是履约失败，不是取消。
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
--    balance > 0 表示在店尚未结清房费；= 0 表示已结清。逻辑未变，只是列名对齐。
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
-- Q8 约束验证演示（两段，都在 DO 块里捕异常打 NOTICE，脚本不中断、不留演示数据）
--    ① 房间排他：复制一条已确认预订的区间、换个客户再插入 → 应被 ex_reservation_room_overlap 拒绝
--       （SQLSTATE 23P01 exclusion_violation）；
--    ② 跨表冲突：往 room_block 的维修/停用区间里插一条预订 → 应被 fn_check_reservation_block()
--       以 23514 check_violation 拒绝（“房态标签说可用”不够，日期区间才是硬约束）。
--    两个 NOTICE 都用 ASCII 前缀：Windows 控制台下 psql 不转换服务端消息编码，
--    中文 NOTICE 在 cp936 终端与 UTF-8 落盘之间必有一边乱码，ASCII 两边都安全。
-- ----------------------------------------------------------------------------
DO $$
DECLARE
    v_customer  bigint;
    v_room      bigint;
    v_in        date;
    v_out       date;
    v_price     numeric(10, 2);
    v_guest     integer;
    b_room      bigint;
    b_in        date;
    b_out       date;
    b_type      text;
BEGIN
    -- 取一条已确认预订作为「已被占用」的区间
    SELECT r.room_id, r.check_in_date, r.check_out_date, r.price_per_night, r.guest_count
      INTO v_room, v_in, v_out, v_price, v_guest
    FROM reservation r
    WHERE r.status = 'confirmed'
    ORDER BY r.id
    LIMIT 1;

    -- 换个「当前没有活跃订单」的客户，避开 uq_reservation_active_customer 的干扰，
    -- 让失败原因只可能是房间区间排他约束
    SELECT c.id
      INTO v_customer
    FROM customer c
    WHERE NOT EXISTS (
            SELECT 1
            FROM reservation r
            WHERE r.customer_id = c.id
              AND r.status IN ('pending', 'confirmed', 'checked_in')
          )
    ORDER BY c.id
    LIMIT 1;

    BEGIN
        -- 房间与区间完全相同 → 只可能触发 ex_reservation_room_overlap
        INSERT INTO reservation (reservation_no, customer_id, room_id, check_in_date, check_out_date,
                                 guest_count, price_per_night, total_amount, status, source, remark)
        VALUES ('DEMO-OVERLAP', v_customer, v_room, v_in, v_out,
                v_guest, v_price, v_price * (v_out - v_in), 'pending', 'phone',
                'Q8 演示：刻意制造区间重叠');

        -- 走到这里说明约束没生效，清掉演示行并报错
        DELETE FROM reservation WHERE reservation_no = 'DEMO-OVERLAP';
        RAISE EXCEPTION 'Q8 FAILED: overlapping reservation was inserted, check ex_reservation_room_overlap';
    EXCEPTION
        WHEN exclusion_violation THEN
            RAISE NOTICE 'Q8 OK: overlap rejected - room % interval [%, %) refused by ex_reservation_room_overlap, SQLSTATE=%',
                         v_room, v_in, v_out, SQLSTATE;
    END;

    -- 取一条维修/停用区间（含已结束的历史区间也可，校验只看区间是否相交）
    SELECT b.room_id, b.start_date, b.end_date, b.block_type
      INTO b_room, b_in, b_out, b_type
    FROM room_block b
    ORDER BY b.id
    LIMIT 1;

    BEGIN
        -- 预订区间完全落在维修/停用区间内 → 应被 fn_check_reservation_block() 拒绝
        INSERT INTO reservation (reservation_no, customer_id, room_id, check_in_date, check_out_date,
                                 guest_count, price_per_night, total_amount, status, source, remark)
        VALUES ('DEMO-BLOCKED', v_customer, b_room, b_in, b_out,
                v_guest, v_price, v_price * (b_out - b_in), 'pending', 'phone',
                'Q8 演示：刻意插入维修/停用区间内的预订');

        DELETE FROM reservation WHERE reservation_no = 'DEMO-BLOCKED';
        RAISE EXCEPTION 'Q8 FAILED: reservation inside a % block was inserted, check fn_check_reservation_block', b_type;
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'Q8 OK: blocked range rejected - room % block % [%, %) refused, SQLSTATE=%',
                         b_room, b_type, b_in, b_out, SQLSTATE;
    END;

    -- 兜底清理：正常路径下两行都插不进去，这里防止异常路径留痕
    DELETE FROM reservation WHERE reservation_no IN ('DEMO-OVERLAP', 'DEMO-BLOCKED');
    RAISE NOTICE 'Q8 cleanup: demo rows removed, reservation rows = %', (SELECT count(*) FROM reservation);
END $$;

-- ----------------------------------------------------------------------------
-- 结论：以上查询全部可直接在演示库执行；Q8 的两条 NOTICE 文本可作为报告 4.3 异常处理证据。
-- ----------------------------------------------------------------------------
SELECT '04_queries.sql 执行完成' AS result;
