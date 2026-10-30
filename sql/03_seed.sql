-- =============================================================================
-- sql/03_seed.sql  演示库样例数据
--
-- 本文件由 tools/build_seed_sql.py 生成（随机种子 20261030，可复现），
-- 不要手改；改数据改脚本后重新生成： python tools/build_seed_sql.py
--
-- 数据规模（与 docs/02-数据库设计.md 第 10 节一致）：
--   app_user        9   （1 管理员 + 2 前台 + 6 客户账号，口令统一 Hotel@123）
--   customer        7   （6 个关联账号 + 1 个线下散客）
--   room_type       6   （标准间 / 高级大床房 / 豪华双床房 / 家庭房 / 行政套房 / 无障碍房）
--   room           40   （5–12 层，每层 5 间，六种房态全覆盖）
--   rate_plan      10   （国庆加价 ×5 房型 + 元旦加价 ×5 房型）
--   reservation    60   （六种状态，含 B3 首尾相接、B4 取消后重订两组边界数据）
--   check_in_record 30  （25 条已退房 + 5 条在住）
--   payment        60   （30 押金 + 23 房费尾款 + 2 退款 + 5 在住服务费）
--   room_status_log    33（手工历史 7 + 触发器自动 26 条）
--   service_item    4 / service_order 15（增值服务，F07 用）
--
-- 执行：
--   chcp 65001
--   psql -U postgres -d yunqi_hotel -v ON_ERROR_STOP=1 -f sql/03_seed.sql
-- 可重复执行：先 TRUNCATE ... RESTART IDENTITY CASCADE，再按外键顺序插入；
-- 整段包在事务里，任何一步失败即整体回滚，不留半套数据。
-- =============================================================================

\set ON_ERROR_STOP on
\encoding UTF8

SET search_path TO public;

BEGIN;

-- 清空并按外键倒序重置自增（幂等）
TRUNCATE TABLE service_order, service_item, payment, check_in_record,
               room_status_log, reservation, rate_plan, room,
               room_type, customer, app_user
    RESTART IDENTITY CASCADE;

-- ----------------------------------------------------------------------------
-- 1) app_user 账号（口令统一 Hotel@123，PBKDF2 哈希由 Django 6.1 生成）
-- ----------------------------------------------------------------------------
INSERT INTO app_user (username, password, display_name, role, phone, email) VALUES
    ('admin', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '酒店管理员', 'admin', '13908001000', 'admin@yunqi-hotel.local'),
    ('front01', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '前台·刘敏', 'receptionist', '13908001001', 'front01@yunqi-hotel.local'),
    ('front02', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '前台·周涛', 'receptionist', '13908001002', 'front02@yunqi-hotel.local'),
    ('zhangwei', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '张伟', 'customer', '13800001101', 'zhangwei@example.com'),
    ('lina', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '李娜', 'customer', '13800001102', 'lina@example.com'),
    ('wangfang', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '王芳', 'customer', '13800001103', 'wangfang@example.com'),
    ('liuyang', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '刘洋', 'customer', '13800001104', 'liuyang@example.com'),
    ('chenjing', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '陈静', 'customer', '13800001105', 'chenjing@example.com'),
    ('yangfan', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '杨帆', 'customer', '13800001106', 'yangfan@example.com');

-- ----------------------------------------------------------------------------
-- 2) room_type 房型（标准价 288–1288 元/晚）
-- ----------------------------------------------------------------------------
INSERT INTO room_type (name, bed_type, area, capacity, base_price, description) VALUES
    ('标准间', 'twin', 25.0, 2, 288.00, '两张单人床，临街采光，基础配置'),
    ('高级大床房', 'king', 28.0, 2, 388.00, '1.8 米大床，独立卫浴，含双早'),
    ('豪华双床房', 'twin', 32.0, 2, 488.00, '两张 1.5 米床，楼层较高，安静'),
    ('家庭房', 'family', 45.0, 4, 688.00, '一大一小两床，适合家庭出行'),
    ('行政套房', 'suite', 60.0, 2, 1288.00, '客厅与卧室分离，含行政酒廊'),
    ('无障碍房', 'double', 30.0, 2, 328.00, '轮椅通道与扶手，低台面无障碍卫生间');

-- ----------------------------------------------------------------------------
-- 3) rate_plan 价格方案（同房型区间互不重叠，受 ex_rate_plan_no_overlap 约束）
-- ----------------------------------------------------------------------------
INSERT INTO rate_plan (room_type_id, name, price, valid_from, valid_to) VALUES
    (1, '国庆加价·标准间', 432.00, DATE '2026-10-01', DATE '2026-10-07'),
    (1, '元旦加价·标准间', 403.20, DATE '2026-12-30', DATE '2027-01-02'),
    (2, '国庆加价·高级大床房', 582.00, DATE '2026-10-01', DATE '2026-10-07'),
    (2, '元旦加价·高级大床房', 543.20, DATE '2026-12-30', DATE '2027-01-02'),
    (3, '国庆加价·豪华双床房', 732.00, DATE '2026-10-01', DATE '2026-10-07'),
    (3, '元旦加价·豪华双床房', 683.20, DATE '2026-12-30', DATE '2027-01-02'),
    (4, '国庆加价·家庭房', 1032.00, DATE '2026-10-01', DATE '2026-10-07'),
    (4, '元旦加价·家庭房', 963.20, DATE '2026-12-30', DATE '2027-01-02'),
    (5, '国庆加价·行政套房', 1932.00, DATE '2026-10-01', DATE '2026-10-07'),
    (5, '元旦加价·行政套房', 1803.20, DATE '2026-12-30', DATE '2027-01-02');

-- ----------------------------------------------------------------------------
-- 4) customer 客户档案（第 7 条为线下散客，user_id 为空）
-- ----------------------------------------------------------------------------
INSERT INTO customer (user_id, name, phone, id_card, email, remark) VALUES
    (4, '张伟', '13800001101', '510101199003070011', 'zhangwei@example.com', '常客，偏好高楼层'),
    (5, '李娜', '13800001102', '510104199205120022', 'lina@example.com', NULL),
    (6, '王芳', '13800001103', '510107198811230033', 'wangfang@example.com', '对早餐过敏，需无坚果'),
    (7, '刘洋', '13800001104', '510108199507040044', 'liuyang@example.com', NULL),
    (8, '陈静', '13800001105', '510109199310150055', 'chenjing@example.com', '公司协议价客户'),
    (9, '杨帆', '13800001106', '510110199901200066', 'yangfan@example.com', NULL),
    (NULL, '赵磊', '13800001107', '510111198706250077', NULL, '线下散客，前台代订');

-- ----------------------------------------------------------------------------
-- 5) room 房间（先统一建成 available，再在文末按业务流转改房态以产生变更日志）
-- ----------------------------------------------------------------------------
INSERT INTO room (room_type_id, room_no, floor, orientation, status, remark) VALUES
    (1, '501', 5, 'east', 'available', NULL),
    (1, '502', 5, 'west', 'available', NULL),
    (1, '503', 5, 'north', 'available', NULL),
    (1, '504', 5, 'south', 'available', NULL),
    (1, '505', 5, 'east', 'available', NULL),
    (1, '601', 6, 'west', 'available', NULL),
    (1, '602', 6, 'north', 'available', NULL),
    (1, '603', 6, 'south', 'available', NULL),
    (1, '604', 6, 'east', 'available', NULL),
    (1, '605', 6, 'west', 'available', NULL),
    (2, '701', 7, 'north', 'available', NULL),
    (2, '702', 7, 'south', 'available', NULL),
    (2, '703', 7, 'east', 'available', NULL),
    (2, '704', 7, 'west', 'available', NULL),
    (2, '705', 7, 'north', 'available', NULL),
    (2, '801', 8, 'south', 'available', NULL),
    (2, '802', 8, 'east', 'available', NULL),
    (2, '803', 8, 'west', 'available', NULL),
    (2, '804', 8, 'north', 'available', NULL),
    (2, '805', 8, 'south', 'available', NULL),
    (3, '901', 9, 'east', 'available', NULL),
    (3, '902', 9, 'west', 'available', NULL),
    (3, '903', 9, 'north', 'available', NULL),
    (3, '904', 9, 'south', 'available', NULL),
    (3, '905', 9, 'east', 'available', NULL),
    (4, '1001', 10, 'west', 'available', NULL),
    (4, '1002', 10, 'north', 'available', NULL),
    (4, '1003', 10, 'south', 'available', NULL),
    (4, '1004', 10, 'east', 'available', NULL),
    (4, '1005', 10, 'west', 'available', NULL),
    (5, '1101', 11, 'north', 'available', NULL),
    (5, '1102', 11, 'south', 'available', NULL),
    (5, '1103', 11, 'east', 'available', NULL),
    (5, '1104', 11, 'west', 'available', NULL),
    (5, '1105', 11, 'north', 'available', NULL),
    (6, '1201', 12, 'south', 'available', '无障碍设施'),
    (6, '1202', 12, 'east', 'available', '无障碍设施'),
    (6, '1203', 12, 'west', 'available', '无障碍设施'),
    (6, '1204', 12, 'north', 'available', '无障碍设施'),
    (6, '1205', 12, 'south', 'available', '无障碍设施');

-- ----------------------------------------------------------------------------
-- 6) reservation 预订 60 条
--    同一房间的活跃区间（pending/confirmed/checked_in）互不重叠；
--    含两组边界数据：B3 首尾相接（离店日 = 下一段入住日，合法）、
--    B4 取消后同区间重订（取消单不参与排他约束，合法）。
-- ----------------------------------------------------------------------------
INSERT INTO reservation (reservation_no, customer_id, room_id, check_in_date,
                         check_out_date, guest_count, price_per_night, total_amount,
                         status, source, remark) VALUES
    ('R20261109001', 3, 36, DATE '2026-11-09', DATE '2026-11-11', 1, 328.00, 656.00, 'checked_out', 'phone', NULL),
    ('R20261106002', 1, 18, DATE '2026-11-06', DATE '2026-11-09', 2, 388.00, 1164.00, 'checked_out', 'phone', NULL),
    ('R20261023003', 2, 10, DATE '2026-10-23', DATE '2026-10-25', 1, 288.00, 576.00, 'checked_out', 'online', NULL),
    ('R20261007004', 6, 23, DATE '2026-10-07', DATE '2026-10-09', 2, 732.00, 1464.00, 'checked_out', 'phone', NULL),
    ('R20261024005', 1, 6, DATE '2026-10-24', DATE '2026-10-27', 2, 288.00, 864.00, 'checked_out', 'phone', NULL),
    ('R20261021006', 5, 14, DATE '2026-10-21', DATE '2026-10-25', 2, 388.00, 1552.00, 'checked_out', 'online', NULL),
    ('R20261019007', 1, 12, DATE '2026-10-19', DATE '2026-10-21', 1, 388.00, 776.00, 'checked_out', 'phone', NULL),
    ('R20260924008', 5, 31, DATE '2026-09-24', DATE '2026-09-27', 2, 1288.00, 3864.00, 'checked_out', 'online', NULL),
    ('R20260917009', 7, 7, DATE '2026-09-17', DATE '2026-09-18', 1, 288.00, 288.00, 'checked_out', 'phone', NULL),
    ('R20260910010', 4, 26, DATE '2026-09-10', DATE '2026-09-14', 1, 688.00, 2752.00, 'checked_out', 'walk_in', NULL),
    ('R20260920011', 1, 6, DATE '2026-09-20', DATE '2026-09-22', 2, 288.00, 576.00, 'checked_out', 'phone', NULL),
    ('R20261125012', 6, 5, DATE '2026-11-25', DATE '2026-11-28', 1, 288.00, 864.00, 'checked_out', 'walk_in', NULL),
    ('R20260927013', 3, 40, DATE '2026-09-27', DATE '2026-10-01', 2, 328.00, 1312.00, 'checked_out', 'online', NULL),
    ('R20260913014', 3, 39, DATE '2026-09-13', DATE '2026-09-16', 2, 328.00, 984.00, 'checked_out', 'walk_in', NULL),
    ('R20260926015', 3, 17, DATE '2026-09-26', DATE '2026-09-27', 1, 388.00, 388.00, 'checked_out', 'walk_in', NULL),
    ('R20261122016', 6, 3, DATE '2026-11-22', DATE '2026-11-23', 2, 288.00, 288.00, 'checked_out', 'walk_in', NULL),
    ('R20261018017', 2, 32, DATE '2026-10-18', DATE '2026-10-22', 1, 1288.00, 5152.00, 'checked_out', 'phone', NULL),
    ('R20260906018', 6, 19, DATE '2026-09-06', DATE '2026-09-10', 2, 388.00, 1552.00, 'checked_out', 'phone', NULL),
    ('R20261025019', 7, 25, DATE '2026-10-25', DATE '2026-10-26', 1, 488.00, 488.00, 'checked_out', 'phone', NULL),
    ('R20260925020', 6, 12, DATE '2026-09-25', DATE '2026-09-29', 1, 388.00, 1552.00, 'checked_out', 'online', NULL),
    ('R20260911021', 4, 20, DATE '2026-09-11', DATE '2026-09-14', 1, 388.00, 1164.00, 'checked_out', 'walk_in', NULL),
    ('R20261008022', 4, 16, DATE '2026-10-08', DATE '2026-10-11', 2, 388.00, 1164.00, 'checked_out', 'walk_in', NULL),
    ('R20261123023', 1, 18, DATE '2026-11-23', DATE '2026-11-26', 1, 388.00, 1164.00, 'checked_out', 'online', NULL),
    ('R20261128024', 1, 1, DATE '2026-11-28', DATE '2026-11-30', 2, 288.00, 576.00, 'checked_out', 'online', 'B3 边界用例：上一段退房当天由下一位客人接续入住'),
    ('R20261130025', 2, 1, DATE '2026-11-30', DATE '2026-12-02', 1, 288.00, 576.00, 'checked_out', 'phone', 'B3 边界用例：与上一段首尾相接，占用不冲突'),
    ('R20261114026', 2, 19, DATE '2026-11-14', DATE '2026-11-16', 1, 388.00, 776.00, 'cancelled', 'phone', NULL),
    ('R20261021027', 2, 18, DATE '2026-10-21', DATE '2026-10-22', 1, 388.00, 388.00, 'cancelled', 'online', NULL),
    ('R20261030028', 5, 3, DATE '2026-10-30', DATE '2026-10-31', 2, 288.00, 288.00, 'cancelled', 'phone', NULL),
    ('R20261011029', 2, 16, DATE '2026-10-11', DATE '2026-10-12', 1, 388.00, 388.00, 'cancelled', 'online', NULL),
    ('R20260924030', 6, 11, DATE '2026-09-24', DATE '2026-09-27', 1, 388.00, 1164.00, 'cancelled', 'walk_in', NULL),
    ('R20261112031', 4, 15, DATE '2026-11-12', DATE '2026-11-15', 2, 388.00, 1164.00, 'no_show', 'phone', NULL),
    ('R20261018032', 5, 38, DATE '2026-10-18', DATE '2026-10-19', 2, 328.00, 328.00, 'no_show', 'online', NULL),
    ('R20261114033', 1, 3, DATE '2026-11-14', DATE '2026-11-16', 1, 288.00, 576.00, 'no_show', 'walk_in', NULL),
    ('R20260930034', 2, 16, DATE '2026-09-30', DATE '2026-10-03', 2, 388.00, 1164.00, 'no_show', 'online', NULL),
    ('R20261212035', 3, 5, DATE '2026-12-12', DATE '2026-12-16', 2, 288.00, 1152.00, 'checked_in', 'phone', NULL),
    ('R20261214036', 1, 16, DATE '2026-12-14', DATE '2026-12-17', 2, 388.00, 1164.00, 'checked_in', 'phone', NULL),
    ('R20261213037', 3, 38, DATE '2026-12-13', DATE '2026-12-16', 2, 328.00, 984.00, 'checked_in', 'phone', NULL),
    ('R20261214038', 6, 30, DATE '2026-12-14', DATE '2026-12-18', 1, 688.00, 2752.00, 'checked_in', 'phone', NULL),
    ('R20261213039', 3, 34, DATE '2026-12-13', DATE '2026-12-17', 1, 1288.00, 5152.00, 'checked_in', 'online', NULL),
    ('R20261224040', 1, 13, DATE '2026-12-24', DATE '2026-12-25', 1, 388.00, 388.00, 'pending', 'phone', NULL),
    ('R20261220041', 1, 20, DATE '2026-12-20', DATE '2026-12-21', 2, 388.00, 388.00, 'pending', 'walk_in', NULL),
    ('R20261228042', 6, 24, DATE '2026-12-28', DATE '2027-01-01', 1, 488.00, 1952.00, 'pending', 'online', NULL),
    ('R20261229043', 5, 39, DATE '2026-12-29', DATE '2027-01-01', 2, 328.00, 984.00, 'pending', 'phone', NULL),
    ('R20261225044', 6, 32, DATE '2026-12-25', DATE '2026-12-29', 1, 1288.00, 5152.00, 'pending', 'phone', NULL),
    ('R20270110045', 1, 40, DATE '2027-01-10', DATE '2027-01-13', 2, 328.00, 984.00, 'pending', 'online', NULL),
    ('R20270107046', 6, 14, DATE '2027-01-07', DATE '2027-01-08', 1, 388.00, 388.00, 'pending', 'online', NULL),
    ('R20270106047', 4, 3, DATE '2027-01-06', DATE '2027-01-07', 2, 288.00, 288.00, 'confirmed', 'walk_in', NULL),
    ('R20261228048', 6, 29, DATE '2026-12-28', DATE '2027-01-01', 2, 688.00, 2752.00, 'confirmed', 'phone', NULL),
    ('R20261223049', 4, 35, DATE '2026-12-23', DATE '2026-12-24', 1, 1288.00, 1288.00, 'confirmed', 'online', NULL),
    ('R20261219050', 6, 25, DATE '2026-12-19', DATE '2026-12-22', 1, 488.00, 1464.00, 'confirmed', 'phone', NULL),
    ('R20261221051', 6, 28, DATE '2026-12-21', DATE '2026-12-22', 2, 688.00, 688.00, 'confirmed', 'online', NULL),
    ('R20261224052', 2, 27, DATE '2026-12-24', DATE '2026-12-27', 1, 688.00, 2064.00, 'confirmed', 'online', NULL),
    ('R20270101053', 3, 35, DATE '2027-01-01', DATE '2027-01-03', 1, 1803.20, 3606.40, 'confirmed', 'phone', NULL),
    ('R20261226054', 4, 37, DATE '2026-12-26', DATE '2026-12-28', 1, 328.00, 656.00, 'confirmed', 'phone', NULL),
    ('R20270107055', 4, 33, DATE '2027-01-07', DATE '2027-01-11', 1, 1288.00, 5152.00, 'confirmed', 'online', NULL),
    ('R20270102056', 4, 11, DATE '2027-01-02', DATE '2027-01-04', 1, 543.20, 1086.40, 'confirmed', 'online', NULL),
    ('R20261220057', 3, 1, DATE '2026-12-20', DATE '2026-12-22', 2, 288.00, 576.00, 'cancelled', 'online', 'B4 边界用例：客户取消后再下同区间订单'),
    ('R20261220058', 3, 1, DATE '2026-12-20', DATE '2026-12-22', 2, 288.00, 576.00, 'confirmed', 'online', 'B4 边界用例：取消单不计入排他约束，同区间可重新预订'),
    ('R20270105059', 5, 1, DATE '2027-01-05', DATE '2027-01-07', 1, 288.00, 576.00, 'confirmed', 'phone', 'B3 边界用例：前一位 01-07 退房'),
    ('R20270107060', 6, 1, DATE '2027-01-07', DATE '2027-01-09', 2, 288.00, 576.00, 'pending', 'online', 'B3 边界用例：与上一段首尾相接，活跃态也不冲突');

-- ----------------------------------------------------------------------------
-- 7) check_in_record 入住记录 30 条（25 已退房 + 5 在住，在住的 actual_checkout_at 为空）
-- ----------------------------------------------------------------------------
INSERT INTO check_in_record (reservation_id, guest_name, guest_phone, guest_id_card,
                             check_in_at, actual_checkout_at, deposit_amount,
                             room_charge, service_charge, total_charge, remark) VALUES
    (1, '王芳', '13800001103', '510107198811230033', TIMESTAMPTZ '2026-11-09 14:00:00+08', TIMESTAMPTZ '2026-11-11 12:00:00+08', 1146.00, 656.00, 390.00, 1046.00, NULL),
    (2, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-11-06 14:00:00+08', TIMESTAMPTZ '2026-11-09 12:00:00+08', 200.00, 1164.00, 0.00, 1164.00, NULL),
    (3, '李娜', '13800001102', '510104199205120022', TIMESTAMPTZ '2026-10-23 14:00:00+08', TIMESTAMPTZ '2026-10-25 12:00:00+08', 200.00, 576.00, 0.00, 576.00, NULL),
    (4, '杨帆', '13800001106', '510110199901200066', TIMESTAMPTZ '2026-10-07 14:00:00+08', TIMESTAMPTZ '2026-10-09 12:00:00+08', 200.00, 1464.00, 0.00, 1464.00, NULL),
    (5, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-10-24 14:00:00+08', TIMESTAMPTZ '2026-10-27 12:00:00+08', 200.00, 864.00, 0.00, 864.00, NULL),
    (6, '陈静', '13800001105', '510109199310150055', TIMESTAMPTZ '2026-10-21 14:00:00+08', TIMESTAMPTZ '2026-10-25 12:00:00+08', 200.00, 1552.00, 308.00, 1860.00, NULL),
    (7, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-10-19 14:00:00+08', TIMESTAMPTZ '2026-10-21 12:00:00+08', 200.00, 776.00, 0.00, 776.00, NULL),
    (8, '陈静', '13800001105', '510109199310150055', TIMESTAMPTZ '2026-09-24 14:00:00+08', TIMESTAMPTZ '2026-09-27 12:00:00+08', 3964.00, 3864.00, 0.00, 3864.00, NULL),
    (9, '赵磊', '13800001107', '510111198706250077', TIMESTAMPTZ '2026-09-17 14:00:00+08', TIMESTAMPTZ '2026-09-18 12:00:00+08', 200.00, 288.00, 0.00, 288.00, NULL),
    (10, '刘洋', '13800001104', '510108199507040044', TIMESTAMPTZ '2026-09-10 14:00:00+08', TIMESTAMPTZ '2026-09-14 12:00:00+08', 200.00, 2752.00, 0.00, 2752.00, NULL),
    (11, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-09-20 14:00:00+08', TIMESTAMPTZ '2026-09-22 12:00:00+08', 200.00, 576.00, 60.00, 636.00, NULL),
    (12, '杨帆', '13800001106', '510110199901200066', TIMESTAMPTZ '2026-11-25 14:00:00+08', TIMESTAMPTZ '2026-11-28 12:00:00+08', 200.00, 864.00, 0.00, 864.00, NULL),
    (13, '王芳', '13800001103', '510107198811230033', TIMESTAMPTZ '2026-09-27 14:00:00+08', TIMESTAMPTZ '2026-10-01 12:00:00+08', 200.00, 1312.00, 0.00, 1312.00, NULL),
    (14, '王芳', '13800001103', '510107198811230033', TIMESTAMPTZ '2026-09-13 14:00:00+08', TIMESTAMPTZ '2026-09-16 12:00:00+08', 200.00, 984.00, 0.00, 984.00, NULL),
    (15, '王芳', '13800001103', '510107198811230033', TIMESTAMPTZ '2026-09-26 14:00:00+08', TIMESTAMPTZ '2026-09-27 12:00:00+08', 200.00, 388.00, 0.00, 388.00, NULL),
    (16, '杨帆', '13800001106', '510110199901200066', TIMESTAMPTZ '2026-11-22 14:00:00+08', TIMESTAMPTZ '2026-11-23 12:00:00+08', 200.00, 288.00, 30.00, 318.00, NULL),
    (17, '李娜', '13800001102', '510104199205120022', TIMESTAMPTZ '2026-10-18 14:00:00+08', TIMESTAMPTZ '2026-10-22 12:00:00+08', 200.00, 5152.00, 0.00, 5152.00, NULL),
    (18, '杨帆', '13800001106', '510110199901200066', TIMESTAMPTZ '2026-09-06 14:00:00+08', TIMESTAMPTZ '2026-09-10 12:00:00+08', 200.00, 1552.00, 0.00, 1552.00, NULL),
    (19, '赵磊', '13800001107', '510111198706250077', TIMESTAMPTZ '2026-10-25 14:00:00+08', TIMESTAMPTZ '2026-10-26 12:00:00+08', 200.00, 488.00, 0.00, 488.00, NULL),
    (20, '杨帆', '13800001106', '510110199901200066', TIMESTAMPTZ '2026-09-25 14:00:00+08', TIMESTAMPTZ '2026-09-29 12:00:00+08', 200.00, 1552.00, 0.00, 1552.00, NULL),
    (21, '刘洋', '13800001104', '510108199507040044', TIMESTAMPTZ '2026-09-11 14:00:00+08', TIMESTAMPTZ '2026-09-14 12:00:00+08', 200.00, 1164.00, 136.00, 1300.00, NULL),
    (22, '刘洋', '13800001104', '510108199507040044', TIMESTAMPTZ '2026-10-08 14:00:00+08', TIMESTAMPTZ '2026-10-11 12:00:00+08', 200.00, 1164.00, 0.00, 1164.00, NULL),
    (23, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-11-23 14:00:00+08', TIMESTAMPTZ '2026-11-26 12:00:00+08', 200.00, 1164.00, 0.00, 1164.00, NULL),
    (24, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-11-28 14:00:00+08', TIMESTAMPTZ '2026-11-30 12:00:00+08', 200.00, 576.00, 0.00, 576.00, NULL),
    (25, '李娜', '13800001102', '510104199205120022', TIMESTAMPTZ '2026-11-30 14:00:00+08', TIMESTAMPTZ '2026-12-02 12:00:00+08', 200.00, 576.00, 0.00, 576.00, NULL),
    (35, '王芳', '13800001103', '510107198811230033', TIMESTAMPTZ '2026-12-12 14:00:00+08', NULL, 200.00, 1152.00, 300.00, 1452.00, '在店，尚未退房'),
    (36, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-12-14 14:00:00+08', NULL, 200.00, 1164.00, 150.00, 1314.00, '在店，尚未退房'),
    (37, '王芳', '13800001103', '510107198811230033', TIMESTAMPTZ '2026-12-13 14:00:00+08', NULL, 200.00, 984.00, 150.00, 1134.00, '在店，尚未退房'),
    (38, '杨帆', '13800001106', '510110199901200066', TIMESTAMPTZ '2026-12-14 14:00:00+08', NULL, 200.00, 2752.00, 68.00, 2820.00, '在店，尚未退房'),
    (39, '王芳', '13800001103', '510107198811230033', TIMESTAMPTZ '2026-12-13 14:00:00+08', NULL, 200.00, 5152.00, 180.00, 5332.00, '在店，尚未退房');

-- ----------------------------------------------------------------------------
-- 8) service_item 增值服务项目 + service_order 消费明细
-- ----------------------------------------------------------------------------
INSERT INTO service_item (code, name, unit, price) VALUES
    ('BF', '自助早餐', '份', 68.00),
    ('LD', '洗衣服务', '件', 30.00),
    ('AP', '机场接送', '次', 120.00),
    ('EB', '加床服务', '张', 150.00);


INSERT INTO service_order (check_in_record_id, service_item_id, quantity, unit_price, ordered_at) VALUES
    (1, 4, 1, 150.00, TIMESTAMPTZ '2026-11-09 16:00:00+08'),
    (1, 3, 2, 120.00, TIMESTAMPTZ '2026-11-09 16:00:00+08'),
    (6, 1, 1, 68.00, TIMESTAMPTZ '2026-10-21 16:00:00+08'),
    (6, 3, 2, 120.00, TIMESTAMPTZ '2026-10-21 16:00:00+08'),
    (11, 2, 2, 30.00, TIMESTAMPTZ '2026-09-20 16:00:00+08'),
    (16, 2, 1, 30.00, TIMESTAMPTZ '2026-11-22 16:00:00+08'),
    (21, 1, 2, 68.00, TIMESTAMPTZ '2026-09-11 16:00:00+08'),
    (26, 2, 2, 30.00, TIMESTAMPTZ '2026-12-12 16:00:00+08'),
    (26, 3, 2, 120.00, TIMESTAMPTZ '2026-12-12 16:00:00+08'),
    (27, 4, 1, 150.00, TIMESTAMPTZ '2026-12-14 16:00:00+08'),
    (28, 2, 1, 30.00, TIMESTAMPTZ '2026-12-13 16:00:00+08'),
    (28, 3, 1, 120.00, TIMESTAMPTZ '2026-12-13 16:00:00+08'),
    (29, 1, 1, 68.00, TIMESTAMPTZ '2026-12-14 16:00:00+08'),
    (30, 2, 1, 30.00, TIMESTAMPTZ '2026-12-13 16:00:00+08'),
    (30, 4, 1, 150.00, TIMESTAMPTZ '2026-12-13 16:00:00+08');

-- ----------------------------------------------------------------------------
-- 9) payment 支付流水 60 笔（kind=refund 的金额也记正数，靠 kind 区分方向）
-- ----------------------------------------------------------------------------
INSERT INTO payment (payment_no, check_in_record_id, kind, method, amount, paid_at,
                     operator_user_id, remark) VALUES
    ('P20261109001', 1, 'deposit', 'cash', 1146.00, TIMESTAMPTZ '2026-11-09 14:30:00+08', 2, NULL),
    ('P20261111002', 1, 'refund', 'cash', 100.00, TIMESTAMPTZ '2026-11-11 12:10:00+08', 2, 'E07：押金多收部分退回'),
    ('P20261106003', 2, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-11-06 14:30:00+08', 3, NULL),
    ('P20261109004', 2, 'room_fee', 'alipay', 964.00, TIMESTAMPTZ '2026-11-09 12:00:00+08', 3, NULL),
    ('P20261023005', 3, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-10-23 14:30:00+08', 2, NULL),
    ('P20261025006', 3, 'room_fee', 'cash', 376.00, TIMESTAMPTZ '2026-10-25 12:00:00+08', 2, NULL),
    ('P20261007007', 4, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-10-07 14:30:00+08', 3, NULL),
    ('P20261009008', 4, 'room_fee', 'cash', 1264.00, TIMESTAMPTZ '2026-10-09 12:00:00+08', 3, NULL),
    ('P20261024009', 5, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-10-24 14:30:00+08', 2, NULL),
    ('P20261027010', 5, 'room_fee', 'wechat', 664.00, TIMESTAMPTZ '2026-10-27 12:00:00+08', 2, NULL),
    ('P20261021011', 6, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-10-21 14:30:00+08', 3, NULL),
    ('P20261025012', 6, 'room_fee', 'cash', 1660.00, TIMESTAMPTZ '2026-10-25 12:00:00+08', 3, NULL),
    ('P20261019013', 7, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-10-19 14:30:00+08', 2, NULL),
    ('P20261021014', 7, 'room_fee', 'card', 576.00, TIMESTAMPTZ '2026-10-21 12:00:00+08', 2, NULL),
    ('P20260924015', 8, 'deposit', 'alipay', 3964.00, TIMESTAMPTZ '2026-09-24 14:30:00+08', 3, NULL),
    ('P20260927016', 8, 'refund', 'alipay', 100.00, TIMESTAMPTZ '2026-09-27 12:10:00+08', 3, 'E07：押金多收部分退回'),
    ('P20260917017', 9, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-09-17 14:30:00+08', 2, NULL),
    ('P20260918018', 9, 'room_fee', 'cash', 88.00, TIMESTAMPTZ '2026-09-18 12:00:00+08', 2, NULL),
    ('P20260910019', 10, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-09-10 14:30:00+08', 3, NULL),
    ('P20260914020', 10, 'room_fee', 'wechat', 2552.00, TIMESTAMPTZ '2026-09-14 12:00:00+08', 3, NULL),
    ('P20260920021', 11, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-09-20 14:30:00+08', 2, NULL),
    ('P20260922022', 11, 'room_fee', 'card', 436.00, TIMESTAMPTZ '2026-09-22 12:00:00+08', 2, NULL),
    ('P20261125023', 12, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-11-25 14:30:00+08', 3, NULL),
    ('P20261128024', 12, 'room_fee', 'alipay', 664.00, TIMESTAMPTZ '2026-11-28 12:00:00+08', 3, NULL),
    ('P20260927025', 13, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-09-27 14:30:00+08', 2, NULL),
    ('P20261001026', 13, 'room_fee', 'card', 1112.00, TIMESTAMPTZ '2026-10-01 12:00:00+08', 2, NULL),
    ('P20260913027', 14, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-09-13 14:30:00+08', 3, NULL),
    ('P20260916028', 14, 'room_fee', 'wechat', 784.00, TIMESTAMPTZ '2026-09-16 12:00:00+08', 3, NULL),
    ('P20260926029', 15, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-09-26 14:30:00+08', 2, NULL),
    ('P20260927030', 15, 'room_fee', 'card', 188.00, TIMESTAMPTZ '2026-09-27 12:00:00+08', 2, NULL),
    ('P20261122031', 16, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-11-22 14:30:00+08', 3, NULL),
    ('P20261123032', 16, 'room_fee', 'card', 118.00, TIMESTAMPTZ '2026-11-23 12:00:00+08', 3, NULL),
    ('P20261018033', 17, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-10-18 14:30:00+08', 2, NULL),
    ('P20261022034', 17, 'room_fee', 'wechat', 4952.00, TIMESTAMPTZ '2026-10-22 12:00:00+08', 2, NULL),
    ('P20260906035', 18, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-09-06 14:30:00+08', 3, NULL),
    ('P20260910036', 18, 'room_fee', 'wechat', 1352.00, TIMESTAMPTZ '2026-09-10 12:00:00+08', 3, NULL),
    ('P20261025037', 19, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-10-25 14:30:00+08', 2, NULL),
    ('P20261026038', 19, 'room_fee', 'card', 288.00, TIMESTAMPTZ '2026-10-26 12:00:00+08', 2, NULL),
    ('P20260925039', 20, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-09-25 14:30:00+08', 3, NULL),
    ('P20260929040', 20, 'room_fee', 'cash', 1352.00, TIMESTAMPTZ '2026-09-29 12:00:00+08', 3, NULL),
    ('P20260911041', 21, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-09-11 14:30:00+08', 2, NULL),
    ('P20260914042', 21, 'room_fee', 'wechat', 1100.00, TIMESTAMPTZ '2026-09-14 12:00:00+08', 2, NULL),
    ('P20261008043', 22, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-10-08 14:30:00+08', 3, NULL),
    ('P20261011044', 22, 'room_fee', 'card', 964.00, TIMESTAMPTZ '2026-10-11 12:00:00+08', 3, NULL),
    ('P20261123045', 23, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-11-23 14:30:00+08', 2, NULL),
    ('P20261126046', 23, 'room_fee', 'wechat', 964.00, TIMESTAMPTZ '2026-11-26 12:00:00+08', 2, NULL),
    ('P20261128047', 24, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-11-28 14:30:00+08', 3, NULL),
    ('P20261130048', 24, 'room_fee', 'cash', 376.00, TIMESTAMPTZ '2026-11-30 12:00:00+08', 3, NULL),
    ('P20261130049', 25, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-11-30 14:30:00+08', 2, NULL),
    ('P20261202050', 25, 'room_fee', 'cash', 376.00, TIMESTAMPTZ '2026-12-02 12:00:00+08', 2, NULL),
    ('P20261212051', 26, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-12-12 14:30:00+08', 3, NULL),
    ('P20261215052', 26, 'service_fee', 'wechat', 300.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 3, '在住期间增值服务费'),
    ('P20261214053', 27, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-12-14 14:30:00+08', 2, NULL),
    ('P20261215054', 27, 'service_fee', 'wechat', 150.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 2, '在住期间增值服务费'),
    ('P20261213055', 28, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-12-13 14:30:00+08', 3, NULL),
    ('P20261215056', 28, 'service_fee', 'wechat', 150.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 3, '在住期间增值服务费'),
    ('P20261214057', 29, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-12-14 14:30:00+08', 2, NULL),
    ('P20261215058', 29, 'service_fee', 'wechat', 68.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 2, '在住期间增值服务费'),
    ('P20261213059', 30, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-12-13 14:30:00+08', 3, NULL),
    ('P20261215060', 30, 'service_fee', 'wechat', 180.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 3, '在住期间增值服务费');

-- ----------------------------------------------------------------------------
-- 10) room_status_log 手工历史（触发器会自动记录房态变更，这里补几段典型轨迹）
-- ----------------------------------------------------------------------------
INSERT INTO room_status_log (room_id, from_status, to_status, changed_by, changed_at, reason) VALUES
    (16, NULL, 'available', 2, TIMESTAMPTZ '2026-11-01 09:00:00+08', '房间交付，初始化为可用'),
    (16, 'available', 'reserved', 2, TIMESTAMPTZ '2026-11-05 10:20:00+08', '客人电话预订'),
    (16, 'reserved', 'occupied', 2, TIMESTAMPTZ '2026-12-02 14:05:00+08', '办理入住'),
    (16, 'occupied', 'cleaning', 3, TIMESTAMPTZ '2026-12-05 12:15:00+08', '退房后转清扫'),
    (16, 'cleaning', 'available', 3, TIMESTAMPTZ '2026-12-05 15:40:00+08', '清扫完成，恢复可用'),
    (16, 'available', 'maintenance', 2, TIMESTAMPTZ '2026-12-10 08:30:00+08', '空调检修'),
    (16, 'maintenance', 'available', 2, TIMESTAMPTZ '2026-12-10 17:10:00+08', '检修完成');

-- ----------------------------------------------------------------------------
-- 11) 按业务流转更新房态（AFTER UPDATE 触发器自动写入 room_status_log）：
--     checked_in 的房间 → occupied；有 future 预订 → reserved；
--     空闲房里挑 2 间 cleaning、1 间 maintenance、1 间 disabled。
-- ----------------------------------------------------------------------------
UPDATE room SET status = v.status, updated_at = now()
FROM (VALUES
    (1, 'reserved'),
    (3, 'reserved'),
    (5, 'occupied'),
    (11, 'reserved'),
    (12, 'maintenance'),
    (13, 'reserved'),
    (14, 'reserved'),
    (16, 'occupied'),
    (17, 'cleaning'),
    (19, 'disabled'),
    (20, 'reserved'),
    (22, 'cleaning'),
    (24, 'reserved'),
    (25, 'reserved'),
    (27, 'reserved'),
    (28, 'reserved'),
    (29, 'reserved'),
    (30, 'occupied'),
    (32, 'reserved'),
    (33, 'reserved'),
    (34, 'occupied'),
    (35, 'reserved'),
    (37, 'reserved'),
    (38, 'occupied'),
    (39, 'reserved'),
    (40, 'reserved')
) AS v(id, status)
WHERE room.id = v.id;

-- updated_at 触发器已被更新语句自然触发，这里再校正一次时间基线不影响数据
ANALYZE;

-- ----------------------------------------------------------------------------
-- 12) 自检：条数、状态分布、重叠检测、可用房函数、视图
-- ----------------------------------------------------------------------------
SELECT 'app_user'        AS table_name, count(*) AS rows FROM app_user
UNION ALL SELECT 'customer',        count(*) FROM customer
UNION ALL SELECT 'room_type',       count(*) FROM room_type
UNION ALL SELECT 'room',            count(*) FROM room
UNION ALL SELECT 'rate_plan',       count(*) FROM rate_plan
UNION ALL SELECT 'reservation',     count(*) FROM reservation
UNION ALL SELECT 'check_in_record', count(*) FROM check_in_record
UNION ALL SELECT 'service_item',    count(*) FROM service_item
UNION ALL SELECT 'service_order',   count(*) FROM service_order
UNION ALL SELECT 'payment',         count(*) FROM payment
UNION ALL SELECT 'room_status_log', count(*) FROM room_status_log
ORDER BY table_name;

SELECT status, count(*) AS cnt FROM reservation GROUP BY status ORDER BY status;

SELECT status, count(*) AS cnt FROM room GROUP BY status ORDER BY status;

-- 重叠检测：活跃状态下同一房间区间相交的行数，期望 0
SELECT count(*) AS overlap_pairs
FROM reservation a
JOIN reservation b ON a.room_id = b.room_id AND a.id < b.id
WHERE a.status IN ('pending', 'confirmed', 'checked_in')
  AND b.status IN ('pending', 'confirmed', 'checked_in')
  AND a.during && b.during;

-- 支付平衡：押金 + 房费尾款 - 退款 应等于（应收合计 - 未结部分），这里只看口径是否有异常行
SELECT p.kind, count(*) AS cnt, sum(p.amount) AS amount_sum
FROM payment p GROUP BY p.kind ORDER BY p.kind;

-- 可用房函数：演示 2026-12-20 至 2026-12-22 的可订房间数
SELECT count(*) AS available_rooms_demo
FROM fn_available_rooms(DATE '2026-12-20', DATE '2026-12-22');

-- 视图连通性
SELECT count(*) AS reservation_detail_rows FROM v_reservation_detail;
SELECT count(*) AS check_in_detail_rows FROM v_check_in_detail;

SELECT '03_seed.sql 执行完成：60 条预订 / 30 条入住 / 60 笔支付' AS result;

COMMIT;

