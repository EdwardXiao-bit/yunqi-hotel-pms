-- =============================================================================
-- sql/03_seed.sql  演示库样例数据
--
-- 本文件由 tools/build_seed_sql.py 生成（随机种子 20261030，可复现），
-- 不要手改；改数据改脚本后重新生成： python tools/build_seed_sql.py
--
-- 数据规模（与 docs/02-数据库设计.md 第 10 节一致）：
--   app_user        27  （1 管理员 + 2 前台 + 24 客户账号，口令统一 Hotel@123）
--   customer        30  （24 个关联账号 + 6 个线下散客）
--   room_type       6   （标准间 / 高级大床房 / 豪华双床房 / 家庭房 / 行政套房 / 无障碍房）
--   room           40   （5–12 层，每层 5 间，六种房态全覆盖）
--   rate_plan      10   （国庆加价 ×5 房型 + 元旦加价 ×5 房型）
--   reservation    96  （六种状态，含 B3 首尾相接、B4 取消后重订两组边界数据）
--   check_in_record 48  （40 条已退房 + 8 条在住）
--   payment        96  （48 押金 + 37 房费尾款 + 3 退款 + 8 在住服务费）
--   room_status_log    35（手工历史 7 + 触发器自动 28 条）
--   service_item    8 / service_order 57（增值服务，F07 结算与统计用）
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
    ('yangfan', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '杨帆', 'customer', '13800001106', 'yangfan@example.com'),
    ('guest07', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '孙明', 'customer', '13800001207', 'guest07@example.com'),
    ('guest08', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '马静', 'customer', '13800001208', 'guest08@example.com'),
    ('guest09', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '朱强', 'customer', '13800001209', 'guest09@example.com'),
    ('guest10', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '胡敏', 'customer', '13800001210', 'guest10@example.com'),
    ('guest11', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '郭磊', 'customer', '13800001211', 'guest11@example.com'),
    ('guest12', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '何霞', 'customer', '13800001212', 'guest12@example.com'),
    ('guest13', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '高军', 'customer', '13800001213', 'guest13@example.com'),
    ('guest14', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '林丽', 'customer', '13800001214', 'guest14@example.com'),
    ('guest15', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '罗刚', 'customer', '13800001215', 'guest15@example.com'),
    ('guest16', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '郑艳', 'customer', '13800001216', 'guest16@example.com'),
    ('guest17', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '梁涛', 'customer', '13800001217', 'guest17@example.com'),
    ('guest18', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '谢娟', 'customer', '13800001218', 'guest18@example.com'),
    ('guest19', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '宋鹏', 'customer', '13800001219', 'guest19@example.com'),
    ('guest20', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '唐浩', 'customer', '13800001220', 'guest20@example.com'),
    ('guest21', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '许娜', 'customer', '13800001221', 'guest21@example.com'),
    ('guest22', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '韩伟', 'customer', '13800001222', 'guest22@example.com'),
    ('guest23', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '冯超', 'customer', '13800001223', 'guest23@example.com'),
    ('guest24', 'pbkdf2_sha256$1500000$NQeiCToT5UjyxTTUYJfshv$HcsKlErH2WUrLTM1YXRcYuZa+7X80tsbsvSAxL8/C+o=', '邓燕', 'customer', '13800001224', 'guest24@example.com');

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
    (10, '孙明', '13800001207', '510107198508150077', 'guest07@example.com', NULL),
    (11, '马静', '13800001208', '510108198509150088', 'guest08@example.com', NULL),
    (12, '朱强', '13800001209', '510109198510150099', 'guest09@example.com', NULL),
    (13, '胡敏', '13800001210', '510110198511150100', 'guest10@example.com', NULL),
    (14, '郭磊', '13800001211', '510111198512150111', 'guest11@example.com', NULL),
    (15, '何霞', '13800001212', '510112198501150122', 'guest12@example.com', NULL),
    (16, '高军', '13800001213', '510113198502150133', 'guest13@example.com', NULL),
    (17, '林丽', '13800001214', '510114198503150144', 'guest14@example.com', NULL),
    (18, '罗刚', '13800001215', '510115198504150155', 'guest15@example.com', NULL),
    (19, '郑艳', '13800001216', '510116198505150166', 'guest16@example.com', NULL),
    (20, '梁涛', '13800001217', '510117198506150177', 'guest17@example.com', NULL),
    (21, '谢娟', '13800001218', '510118198507150188', 'guest18@example.com', NULL),
    (22, '宋鹏', '13800001219', '510119198508150199', 'guest19@example.com', NULL),
    (23, '唐浩', '13800001220', '510120198509150200', 'guest20@example.com', NULL),
    (24, '许娜', '13800001221', '510121198510150211', 'guest21@example.com', NULL),
    (25, '韩伟', '13800001222', '510122198511150222', 'guest22@example.com', NULL),
    (26, '冯超', '13800001223', '510123198512150233', 'guest23@example.com', NULL),
    (27, '邓燕', '13800001224', '510124198501150244', 'guest24@example.com', NULL),
    (NULL, '曹鑫', '13800001325', '510225198702180255', NULL, '线下散客，前台代订'),
    (NULL, '彭雪', '13800001326', '510226198703180266', NULL, '线下散客，前台代订'),
    (NULL, '曾帆', '13800001327', '510227198704180277', NULL, '线下散客，前台代订'),
    (NULL, '萧雨', '13800001328', '510228198705180288', NULL, '线下散客，前台代订'),
    (NULL, '田昊', '13800001329', '510229198706180299', NULL, '线下散客，前台代订'),
    (NULL, '董欣', '13800001330', '510230198707180300', NULL, '线下散客，前台代订');

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
-- 6) reservation 预订 96 条
--    同一房间的活跃区间（pending/confirmed/checked_in）互不重叠；
--    含两组边界数据：B3 首尾相接（离店日 = 下一段入住日，合法）、
--    B4 取消后同区间重订（取消单不参与排他约束，合法）。
-- ----------------------------------------------------------------------------
INSERT INTO reservation (reservation_no, customer_id, room_id, check_in_date,
                         check_out_date, guest_count, price_per_night, total_amount,
                         status, source, remark) VALUES
    ('R20261109001', 11, 36, DATE '2026-11-09', DATE '2026-11-11', 1, 328.00, 656.00, 'checked_out', 'phone', NULL),
    ('R20261106002', 4, 18, DATE '2026-11-06', DATE '2026-11-09', 2, 388.00, 1164.00, 'checked_out', 'phone', NULL),
    ('R20261023003', 6, 10, DATE '2026-10-23', DATE '2026-10-25', 1, 288.00, 576.00, 'checked_out', 'online', NULL),
    ('R20261007004', 30, 23, DATE '2026-10-07', DATE '2026-10-09', 2, 732.00, 1464.00, 'checked_out', 'walk_in', NULL),
    ('R20261109005', 3, 21, DATE '2026-11-09', DATE '2026-11-13', 2, 488.00, 1952.00, 'checked_out', 'online', NULL),
    ('R20261014006', 6, 32, DATE '2026-10-14', DATE '2026-10-18', 1, 1288.00, 5152.00, 'checked_out', 'walk_in', NULL),
    ('R20261009007', 20, 36, DATE '2026-10-09', DATE '2026-10-13', 1, 328.00, 1312.00, 'checked_out', 'walk_in', NULL),
    ('R20261121008', 15, 1, DATE '2026-11-21', DATE '2026-11-23', 1, 288.00, 576.00, 'checked_out', 'online', NULL),
    ('R20261004009', 27, 38, DATE '2026-10-04', DATE '2026-10-08', 2, 328.00, 1312.00, 'checked_out', 'online', NULL),
    ('R20260917010', 27, 7, DATE '2026-09-17', DATE '2026-09-18', 1, 288.00, 288.00, 'checked_out', 'phone', NULL),
    ('R20260910011', 16, 26, DATE '2026-09-10', DATE '2026-09-14', 1, 688.00, 2752.00, 'checked_out', 'walk_in', NULL),
    ('R20260920012', 3, 6, DATE '2026-09-20', DATE '2026-09-22', 2, 288.00, 576.00, 'checked_out', 'phone', NULL),
    ('R20261125013', 23, 5, DATE '2026-11-25', DATE '2026-11-28', 1, 288.00, 864.00, 'checked_out', 'walk_in', NULL),
    ('R20260927014', 9, 40, DATE '2026-09-27', DATE '2026-10-01', 2, 328.00, 1312.00, 'checked_out', 'online', NULL),
    ('R20260913015', 9, 39, DATE '2026-09-13', DATE '2026-09-16', 2, 328.00, 984.00, 'checked_out', 'walk_in', NULL),
    ('R20260926016', 12, 17, DATE '2026-09-26', DATE '2026-09-27', 1, 388.00, 388.00, 'checked_out', 'walk_in', NULL),
    ('R20261122017', 24, 4, DATE '2026-11-22', DATE '2026-11-23', 2, 288.00, 288.00, 'checked_out', 'walk_in', NULL),
    ('R20261018018', 5, 30, DATE '2026-10-18', DATE '2026-10-22', 1, 688.00, 2752.00, 'checked_out', 'phone', NULL),
    ('R20260906019', 23, 19, DATE '2026-09-06', DATE '2026-09-10', 2, 388.00, 1552.00, 'checked_out', 'phone', NULL),
    ('R20261025020', 25, 24, DATE '2026-10-25', DATE '2026-10-26', 1, 488.00, 488.00, 'checked_out', 'phone', NULL),
    ('R20260925021', 21, 12, DATE '2026-09-25', DATE '2026-09-29', 1, 388.00, 1552.00, 'checked_out', 'online', NULL),
    ('R20260911022', 14, 20, DATE '2026-09-11', DATE '2026-09-14', 1, 388.00, 1164.00, 'checked_out', 'walk_in', NULL),
    ('R20261008023', 16, 16, DATE '2026-10-08', DATE '2026-10-11', 2, 388.00, 1164.00, 'checked_out', 'walk_in', NULL),
    ('R20261123024', 4, 18, DATE '2026-11-23', DATE '2026-11-26', 1, 388.00, 1164.00, 'checked_out', 'online', NULL),
    ('R20261014025', 11, 34, DATE '2026-10-14', DATE '2026-10-15', 2, 1288.00, 1288.00, 'checked_out', 'walk_in', NULL),
    ('R20261007026', 5, 31, DATE '2026-10-07', DATE '2026-10-09', 1, 1932.00, 3864.00, 'checked_out', 'phone', NULL),
    ('R20261003027', 2, 6, DATE '2026-10-03', DATE '2026-10-05', 1, 432.00, 864.00, 'checked_out', 'phone', NULL),
    ('R20260906028', 8, 20, DATE '2026-09-06', DATE '2026-09-09', 1, 388.00, 1164.00, 'checked_out', 'online', NULL),
    ('R20260918029', 4, 5, DATE '2026-09-18', DATE '2026-09-19', 1, 288.00, 288.00, 'checked_out', 'walk_in', NULL),
    ('R20261120030', 18, 33, DATE '2026-11-20', DATE '2026-11-22', 2, 1288.00, 2576.00, 'checked_out', 'online', NULL),
    ('R20261030031', 20, 13, DATE '2026-10-30', DATE '2026-11-02', 2, 388.00, 1164.00, 'checked_out', 'walk_in', NULL),
    ('R20260928032', 27, 3, DATE '2026-09-28', DATE '2026-10-01', 2, 288.00, 864.00, 'checked_out', 'online', NULL),
    ('R20260907033', 5, 16, DATE '2026-09-07', DATE '2026-09-09', 2, 388.00, 776.00, 'checked_out', 'online', NULL),
    ('R20261113034', 10, 18, DATE '2026-11-13', DATE '2026-11-14', 1, 388.00, 388.00, 'checked_out', 'walk_in', NULL),
    ('R20261008035', 16, 3, DATE '2026-10-08', DATE '2026-10-10', 2, 288.00, 576.00, 'checked_out', 'walk_in', NULL),
    ('R20261030036', 20, 25, DATE '2026-10-30', DATE '2026-11-02', 1, 488.00, 1464.00, 'checked_out', 'walk_in', NULL),
    ('R20260922037', 19, 40, DATE '2026-09-22', DATE '2026-09-26', 1, 328.00, 1312.00, 'checked_out', 'phone', NULL),
    ('R20261024038', 1, 25, DATE '2026-10-24', DATE '2026-10-28', 1, 488.00, 1952.00, 'checked_out', 'online', NULL),
    ('R20261128039', 1, 1, DATE '2026-11-28', DATE '2026-11-30', 1, 288.00, 576.00, 'checked_out', 'online', 'B3 边界用例：上一段退房当天由下一位客人接续入住'),
    ('R20261130040', 2, 1, DATE '2026-11-30', DATE '2026-12-02', 1, 288.00, 576.00, 'checked_out', 'phone', 'B3 边界用例：与上一段首尾相接，占用不冲突'),
    ('R20260917041', 1, 3, DATE '2026-09-17', DATE '2026-09-19', 2, 288.00, 576.00, 'cancelled', 'online', NULL),
    ('R20260920042', 13, 18, DATE '2026-09-20', DATE '2026-09-23', 2, 388.00, 1164.00, 'cancelled', 'walk_in', NULL),
    ('R20261223043', 5, 4, DATE '2026-12-23', DATE '2026-12-26', 2, 288.00, 864.00, 'cancelled', 'phone', NULL),
    ('R20261124044', 16, 34, DATE '2026-11-24', DATE '2026-11-27', 2, 1288.00, 3864.00, 'cancelled', 'online', NULL),
    ('R20261110045', 4, 19, DATE '2026-11-10', DATE '2026-11-13', 2, 388.00, 1164.00, 'cancelled', 'walk_in', NULL),
    ('R20261128046', 23, 17, DATE '2026-11-28', DATE '2026-11-29', 1, 388.00, 388.00, 'cancelled', 'walk_in', NULL),
    ('R20261222047', 6, 3, DATE '2026-12-22', DATE '2026-12-23', 2, 288.00, 288.00, 'cancelled', 'phone', NULL),
    ('R20260910048', 15, 3, DATE '2026-09-10', DATE '2026-09-13', 2, 288.00, 864.00, 'cancelled', 'walk_in', NULL),
    ('R20260930049', 14, 30, DATE '2026-09-30', DATE '2026-10-03', 2, 688.00, 2064.00, 'cancelled', 'walk_in', NULL),
    ('R20261027050', 3, 6, DATE '2026-10-27', DATE '2026-10-30', 2, 288.00, 864.00, 'cancelled', 'walk_in', NULL),
    ('R20261010051', 9, 2, DATE '2026-10-10', DATE '2026-10-11', 2, 288.00, 288.00, 'cancelled', 'phone', NULL),
    ('R20261103052', 1, 4, DATE '2026-11-03', DATE '2026-11-04', 2, 288.00, 288.00, 'no_show', 'phone', NULL),
    ('R20260923053', 10, 7, DATE '2026-09-23', DATE '2026-09-25', 2, 288.00, 576.00, 'no_show', 'walk_in', NULL),
    ('R20261005054', 8, 15, DATE '2026-10-05', DATE '2026-10-06', 2, 582.00, 582.00, 'no_show', 'online', NULL),
    ('R20261222055', 7, 22, DATE '2026-12-22', DATE '2026-12-24', 2, 488.00, 976.00, 'no_show', 'walk_in', NULL),
    ('R20260927056', 18, 18, DATE '2026-09-27', DATE '2026-09-30', 2, 388.00, 1164.00, 'no_show', 'phone', NULL),
    ('R20260916057', 16, 32, DATE '2026-09-16', DATE '2026-09-18', 1, 1288.00, 2576.00, 'no_show', 'phone', NULL),
    ('R20261214058', 6, 15, DATE '2026-12-14', DATE '2026-12-16', 1, 388.00, 776.00, 'checked_in', 'phone', NULL),
    ('R20261214059', 1, 24, DATE '2026-12-14', DATE '2026-12-17', 2, 488.00, 1464.00, 'checked_in', 'phone', NULL),
    ('R20261213060', 17, 13, DATE '2026-12-13', DATE '2026-12-17', 2, 388.00, 1552.00, 'checked_in', 'phone', NULL),
    ('R20261214061', 14, 7, DATE '2026-12-14', DATE '2026-12-18', 2, 288.00, 1152.00, 'checked_in', 'online', NULL),
    ('R20261214062', 5, 14, DATE '2026-12-14', DATE '2026-12-17', 1, 388.00, 1164.00, 'checked_in', 'online', NULL),
    ('R20261214063', 17, 27, DATE '2026-12-14', DATE '2026-12-17', 3, 688.00, 2064.00, 'checked_in', 'online', NULL),
    ('R20261213064', 16, 1, DATE '2026-12-13', DATE '2026-12-16', 2, 288.00, 864.00, 'checked_in', 'online', NULL),
    ('R20261214065', 1, 12, DATE '2026-12-14', DATE '2026-12-18', 1, 388.00, 1552.00, 'checked_in', 'online', NULL),
    ('R20270108066', 6, 21, DATE '2027-01-08', DATE '2027-01-09', 2, 488.00, 488.00, 'pending', 'phone', NULL),
    ('R20261225067', 16, 5, DATE '2026-12-25', DATE '2026-12-27', 2, 288.00, 576.00, 'pending', 'online', NULL),
    ('R20261222068', 18, 8, DATE '2026-12-22', DATE '2026-12-25', 2, 288.00, 864.00, 'pending', 'online', NULL),
    ('R20270105069', 4, 37, DATE '2027-01-05', DATE '2027-01-09', 1, 328.00, 1312.00, 'pending', 'phone', NULL),
    ('R20270103070', 5, 23, DATE '2027-01-03', DATE '2027-01-05', 1, 488.00, 976.00, 'pending', 'walk_in', NULL),
    ('R20261230071', 4, 15, DATE '2026-12-30', DATE '2027-01-02', 2, 543.20, 1629.60, 'pending', 'walk_in', NULL),
    ('R20261226072', 4, 3, DATE '2026-12-26', DATE '2026-12-29', 2, 288.00, 864.00, 'pending', 'phone', NULL),
    ('R20261229073', 1, 26, DATE '2026-12-29', DATE '2026-12-31', 3, 688.00, 1376.00, 'pending', 'walk_in', NULL),
    ('R20270106074', 12, 9, DATE '2027-01-06', DATE '2027-01-10', 2, 288.00, 1152.00, 'pending', 'online', NULL),
    ('R20270106075', 13, 6, DATE '2027-01-06', DATE '2027-01-09', 2, 288.00, 864.00, 'pending', 'walk_in', NULL),
    ('R20270103076', 2, 32, DATE '2027-01-03', DATE '2027-01-04', 2, 1288.00, 1288.00, 'pending', 'phone', NULL),
    ('R20261224077', 10, 15, DATE '2026-12-24', DATE '2026-12-25', 2, 388.00, 388.00, 'pending', 'online', NULL),
    ('R20270103078', 16, 19, DATE '2027-01-03', DATE '2027-01-07', 2, 388.00, 1552.00, 'pending', 'walk_in', NULL),
    ('R20261218079', 3, 9, DATE '2026-12-18', DATE '2026-12-19', 2, 288.00, 288.00, 'confirmed', 'online', NULL),
    ('R20261229080', 13, 35, DATE '2026-12-29', DATE '2027-01-02', 2, 1288.00, 5152.00, 'confirmed', 'online', NULL),
    ('R20270103081', 16, 11, DATE '2027-01-03', DATE '2027-01-05', 1, 388.00, 776.00, 'confirmed', 'walk_in', NULL),
    ('R20261223082', 16, 37, DATE '2026-12-23', DATE '2026-12-24', 2, 328.00, 328.00, 'confirmed', 'online', NULL),
    ('R20270115083', 5, 11, DATE '2027-01-15', DATE '2027-01-18', 2, 388.00, 1164.00, 'confirmed', 'phone', NULL),
    ('R20261227084', 6, 4, DATE '2026-12-27', DATE '2026-12-30', 2, 288.00, 864.00, 'confirmed', 'phone', NULL),
    ('R20270113085', 6, 8, DATE '2027-01-13', DATE '2027-01-14', 2, 288.00, 288.00, 'confirmed', 'phone', NULL),
    ('R20261226086', 18, 20, DATE '2026-12-26', DATE '2026-12-29', 2, 388.00, 1164.00, 'confirmed', 'online', NULL),
    ('R20270112087', 14, 27, DATE '2027-01-12', DATE '2027-01-16', 2, 688.00, 2752.00, 'confirmed', 'walk_in', NULL),
    ('R20270109088', 6, 34, DATE '2027-01-09', DATE '2027-01-10', 2, 1288.00, 1288.00, 'confirmed', 'walk_in', NULL),
    ('R20261219089', 10, 11, DATE '2026-12-19', DATE '2026-12-22', 2, 388.00, 1164.00, 'confirmed', 'phone', NULL),
    ('R20270102090', 5, 27, DATE '2027-01-02', DATE '2027-01-04', 3, 963.20, 1926.40, 'confirmed', 'walk_in', NULL),
    ('R20261227091', 23, 19, DATE '2026-12-27', DATE '2026-12-28', 2, 388.00, 388.00, 'confirmed', 'online', NULL),
    ('R20270109092', 17, 8, DATE '2027-01-09', DATE '2027-01-10', 1, 288.00, 288.00, 'confirmed', 'walk_in', NULL),
    ('R20261220093', 1, 1, DATE '2026-12-20', DATE '2026-12-22', 2, 288.00, 576.00, 'cancelled', 'online', 'B4 边界用例：客户取消后再下同区间订单'),
    ('R20261220094', 1, 1, DATE '2026-12-20', DATE '2026-12-22', 2, 288.00, 576.00, 'confirmed', 'online', 'B4 边界用例：取消单不计入排他约束，同区间可重新预订'),
    ('R20270105095', 5, 1, DATE '2027-01-05', DATE '2027-01-07', 2, 288.00, 576.00, 'confirmed', 'phone', 'B3 边界用例：前一位 01-07 退房'),
    ('R20270107096', 6, 1, DATE '2027-01-07', DATE '2027-01-09', 1, 288.00, 576.00, 'pending', 'online', 'B3 边界用例：与上一段首尾相接，活跃态也不冲突');

-- ----------------------------------------------------------------------------
-- 7) check_in_record 入住记录 48 条（40 已退房 + 8 在住，在住的 actual_checkout_at 为空）
-- ----------------------------------------------------------------------------
INSERT INTO check_in_record (reservation_id, guest_name, guest_phone, guest_id_card,
                             check_in_at, actual_checkout_at, deposit_amount,
                             room_charge, service_charge, total_charge, remark) VALUES
    (1, '郭磊', '13800001211', '510111198512150111', TIMESTAMPTZ '2026-11-09 14:00:00+08', TIMESTAMPTZ '2026-11-11 12:00:00+08', 906.00, 656.00, 150.00, 806.00, NULL),
    (2, '刘洋', '13800001104', '510108199507040044', TIMESTAMPTZ '2026-11-06 14:00:00+08', TIMESTAMPTZ '2026-11-09 12:00:00+08', 200.00, 1164.00, 88.00, 1252.00, NULL),
    (3, '杨帆', '13800001106', '510110199901200066', TIMESTAMPTZ '2026-10-23 14:00:00+08', TIMESTAMPTZ '2026-10-25 12:00:00+08', 200.00, 576.00, 300.00, 876.00, NULL),
    (4, '董欣', '13800001330', '510230198707180300', TIMESTAMPTZ '2026-10-07 14:00:00+08', TIMESTAMPTZ '2026-10-09 12:00:00+08', 200.00, 1464.00, 0.00, 1464.00, NULL),
    (5, '王芳', '13800001103', '510107198811230033', TIMESTAMPTZ '2026-11-09 14:00:00+08', TIMESTAMPTZ '2026-11-13 12:00:00+08', 200.00, 1952.00, 188.00, 2140.00, NULL),
    (6, '杨帆', '13800001106', '510110199901200066', TIMESTAMPTZ '2026-10-14 14:00:00+08', TIMESTAMPTZ '2026-10-18 12:00:00+08', 200.00, 5152.00, 120.00, 5272.00, NULL),
    (7, '唐浩', '13800001220', '510120198509150200', TIMESTAMPTZ '2026-10-09 14:00:00+08', TIMESTAMPTZ '2026-10-13 12:00:00+08', 200.00, 1312.00, 108.00, 1420.00, NULL),
    (8, '罗刚', '13800001215', '510115198504150155', TIMESTAMPTZ '2026-11-21 14:00:00+08', TIMESTAMPTZ '2026-11-23 12:00:00+08', 676.00, 576.00, 0.00, 576.00, NULL),
    (9, '曾帆', '13800001327', '510227198704180277', TIMESTAMPTZ '2026-10-04 14:00:00+08', TIMESTAMPTZ '2026-10-08 12:00:00+08', 200.00, 1312.00, 60.00, 1372.00, NULL),
    (10, '曾帆', '13800001327', '510227198704180277', TIMESTAMPTZ '2026-09-17 14:00:00+08', TIMESTAMPTZ '2026-09-18 12:00:00+08', 200.00, 288.00, 256.00, 544.00, NULL),
    (11, '郑艳', '13800001216', '510116198505150166', TIMESTAMPTZ '2026-09-10 14:00:00+08', TIMESTAMPTZ '2026-09-14 12:00:00+08', 200.00, 2752.00, 240.00, 2992.00, NULL),
    (12, '王芳', '13800001103', '510107198811230033', TIMESTAMPTZ '2026-09-20 14:00:00+08', TIMESTAMPTZ '2026-09-22 12:00:00+08', 200.00, 576.00, 0.00, 576.00, NULL),
    (13, '冯超', '13800001223', '510123198512150233', TIMESTAMPTZ '2026-11-25 14:00:00+08', TIMESTAMPTZ '2026-11-28 12:00:00+08', 200.00, 864.00, 176.00, 1040.00, NULL),
    (14, '朱强', '13800001209', '510109198510150099', TIMESTAMPTZ '2026-09-27 14:00:00+08', TIMESTAMPTZ '2026-10-01 12:00:00+08', 200.00, 1312.00, 196.00, 1508.00, NULL),
    (15, '朱强', '13800001209', '510109198510150099', TIMESTAMPTZ '2026-09-13 14:00:00+08', TIMESTAMPTZ '2026-09-16 12:00:00+08', 200.00, 984.00, 304.00, 1288.00, NULL),
    (16, '何霞', '13800001212', '510112198501150122', TIMESTAMPTZ '2026-09-26 14:00:00+08', TIMESTAMPTZ '2026-09-27 12:00:00+08', 488.00, 388.00, 0.00, 388.00, NULL),
    (17, '邓燕', '13800001224', '510124198501150244', TIMESTAMPTZ '2026-11-22 14:00:00+08', TIMESTAMPTZ '2026-11-23 12:00:00+08', 200.00, 288.00, 190.00, 478.00, NULL),
    (18, '陈静', '13800001105', '510109199310150055', TIMESTAMPTZ '2026-10-18 14:00:00+08', TIMESTAMPTZ '2026-10-22 12:00:00+08', 200.00, 2752.00, 150.00, 2902.00, NULL),
    (19, '冯超', '13800001223', '510123198512150233', TIMESTAMPTZ '2026-09-06 14:00:00+08', TIMESTAMPTZ '2026-09-10 12:00:00+08', 200.00, 1552.00, 360.00, 1912.00, NULL),
    (20, '曹鑫', '13800001325', '510225198702180255', TIMESTAMPTZ '2026-10-25 14:00:00+08', TIMESTAMPTZ '2026-10-26 12:00:00+08', 200.00, 488.00, 0.00, 488.00, NULL),
    (21, '许娜', '13800001221', '510121198510150211', TIMESTAMPTZ '2026-09-25 14:00:00+08', TIMESTAMPTZ '2026-09-29 12:00:00+08', 200.00, 1552.00, 150.00, 1702.00, NULL),
    (22, '林丽', '13800001214', '510114198503150144', TIMESTAMPTZ '2026-09-11 14:00:00+08', TIMESTAMPTZ '2026-09-14 12:00:00+08', 200.00, 1164.00, 238.00, 1402.00, NULL),
    (23, '郑艳', '13800001216', '510116198505150166', TIMESTAMPTZ '2026-10-08 14:00:00+08', TIMESTAMPTZ '2026-10-11 12:00:00+08', 200.00, 1164.00, 276.00, 1440.00, NULL),
    (24, '刘洋', '13800001104', '510108199507040044', TIMESTAMPTZ '2026-11-23 14:00:00+08', TIMESTAMPTZ '2026-11-26 12:00:00+08', 200.00, 1164.00, 0.00, 1164.00, NULL),
    (25, '郭磊', '13800001211', '510111198512150111', TIMESTAMPTZ '2026-10-14 14:00:00+08', TIMESTAMPTZ '2026-10-15 12:00:00+08', 200.00, 1288.00, 240.00, 1528.00, NULL),
    (26, '陈静', '13800001105', '510109199310150055', TIMESTAMPTZ '2026-10-07 14:00:00+08', TIMESTAMPTZ '2026-10-09 12:00:00+08', 200.00, 3864.00, 150.00, 4014.00, NULL),
    (27, '李娜', '13800001102', '510104199205120022', TIMESTAMPTZ '2026-10-03 14:00:00+08', TIMESTAMPTZ '2026-10-05 12:00:00+08', 200.00, 864.00, 60.00, 924.00, NULL),
    (28, '马静', '13800001208', '510108198509150088', TIMESTAMPTZ '2026-09-06 14:00:00+08', TIMESTAMPTZ '2026-09-09 12:00:00+08', 200.00, 1164.00, 0.00, 1164.00, NULL),
    (29, '刘洋', '13800001104', '510108199507040044', TIMESTAMPTZ '2026-09-18 14:00:00+08', TIMESTAMPTZ '2026-09-19 12:00:00+08', 200.00, 288.00, 312.00, 600.00, NULL),
    (30, '谢娟', '13800001218', '510118198507150188', TIMESTAMPTZ '2026-11-20 14:00:00+08', TIMESTAMPTZ '2026-11-22 12:00:00+08', 200.00, 2576.00, 536.00, 3112.00, NULL),
    (31, '唐浩', '13800001220', '510120198509150200', TIMESTAMPTZ '2026-10-30 14:00:00+08', TIMESTAMPTZ '2026-11-02 12:00:00+08', 200.00, 1164.00, 268.00, 1432.00, NULL),
    (32, '曾帆', '13800001327', '510227198704180277', TIMESTAMPTZ '2026-09-28 14:00:00+08', TIMESTAMPTZ '2026-10-01 12:00:00+08', 200.00, 864.00, 0.00, 864.00, NULL),
    (33, '陈静', '13800001105', '510109199310150055', TIMESTAMPTZ '2026-09-07 14:00:00+08', TIMESTAMPTZ '2026-09-09 12:00:00+08', 200.00, 776.00, 296.00, 1072.00, NULL),
    (34, '胡敏', '13800001210', '510110198511150100', TIMESTAMPTZ '2026-11-13 14:00:00+08', TIMESTAMPTZ '2026-11-14 12:00:00+08', 200.00, 388.00, 176.00, 564.00, NULL),
    (35, '郑艳', '13800001216', '510116198505150166', TIMESTAMPTZ '2026-10-08 14:00:00+08', TIMESTAMPTZ '2026-10-10 12:00:00+08', 200.00, 576.00, 20.00, 596.00, NULL),
    (36, '唐浩', '13800001220', '510120198509150200', TIMESTAMPTZ '2026-10-30 14:00:00+08', TIMESTAMPTZ '2026-11-02 12:00:00+08', 200.00, 1464.00, 0.00, 1464.00, NULL),
    (37, '宋鹏', '13800001219', '510119198508150199', TIMESTAMPTZ '2026-09-22 14:00:00+08', TIMESTAMPTZ '2026-09-26 12:00:00+08', 200.00, 1312.00, 136.00, 1448.00, NULL),
    (38, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-10-24 14:00:00+08', TIMESTAMPTZ '2026-10-28 12:00:00+08', 200.00, 1952.00, 836.00, 2788.00, NULL),
    (39, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-11-28 14:00:00+08', TIMESTAMPTZ '2026-11-30 12:00:00+08', 200.00, 576.00, 70.00, 646.00, NULL),
    (40, '李娜', '13800001102', '510104199205120022', TIMESTAMPTZ '2026-11-30 14:00:00+08', TIMESTAMPTZ '2026-12-02 12:00:00+08', 200.00, 576.00, 0.00, 576.00, NULL),
    (58, '杨帆', '13800001106', '510110199901200066', TIMESTAMPTZ '2026-12-14 14:00:00+08', NULL, 200.00, 776.00, 176.00, 952.00, '在店，尚未退房'),
    (59, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-12-14 14:00:00+08', NULL, 200.00, 1464.00, 88.00, 1552.00, '在店，尚未退房'),
    (60, '梁涛', '13800001217', '510117198506150177', TIMESTAMPTZ '2026-12-13 14:00:00+08', NULL, 200.00, 1552.00, 180.00, 1732.00, '在店，尚未退房'),
    (61, '林丽', '13800001214', '510114198503150144', TIMESTAMPTZ '2026-12-14 14:00:00+08', NULL, 200.00, 1152.00, 108.00, 1260.00, '在店，尚未退房'),
    (62, '陈静', '13800001105', '510109199310150055', TIMESTAMPTZ '2026-12-14 14:00:00+08', NULL, 200.00, 1164.00, 328.00, 1492.00, '在店，尚未退房'),
    (63, '梁涛', '13800001217', '510117198506150177', TIMESTAMPTZ '2026-12-14 14:00:00+08', NULL, 200.00, 2064.00, 368.00, 2432.00, '在店，尚未退房'),
    (64, '郑艳', '13800001216', '510116198505150166', TIMESTAMPTZ '2026-12-13 14:00:00+08', NULL, 200.00, 864.00, 418.00, 1282.00, '在店，尚未退房'),
    (65, '张伟', '13800001101', '510101199003070011', TIMESTAMPTZ '2026-12-14 14:00:00+08', NULL, 200.00, 1552.00, 128.00, 1680.00, '在店，尚未退房');

-- ----------------------------------------------------------------------------
-- 8) service_item 增值服务项目 + service_order 消费明细
-- ----------------------------------------------------------------------------
INSERT INTO service_item (code, name, unit, price) VALUES
    ('BF', '自助早餐', '份', 68.00),
    ('LD', '洗衣服务', '件', 30.00),
    ('AP', '机场接送', '次', 120.00),
    ('EB', '加床服务', '张', 150.00),
    ('LC', '午餐套餐', '份', 88.00),
    ('DN', '晚餐套餐', '份', 128.00),
    ('SP', 'SPA 水疗', '次', 268.00),
    ('PK', '停车位', '晚', 20.00);


INSERT INTO service_order (check_in_record_id, service_item_id, quantity, unit_price, ordered_at) VALUES
    (1, 4, 1, 150.00, TIMESTAMPTZ '2026-11-09 16:00:00+08'),
    (2, 1, 1, 68.00, TIMESTAMPTZ '2026-11-06 16:00:00+08'),
    (2, 8, 1, 20.00, TIMESTAMPTZ '2026-11-06 16:00:00+08'),
    (3, 4, 2, 150.00, TIMESTAMPTZ '2026-10-23 16:00:00+08'),
    (5, 6, 1, 128.00, TIMESTAMPTZ '2026-11-09 16:00:00+08'),
    (5, 2, 2, 30.00, TIMESTAMPTZ '2026-11-09 16:00:00+08'),
    (6, 3, 1, 120.00, TIMESTAMPTZ '2026-10-14 16:00:00+08'),
    (7, 5, 1, 88.00, TIMESTAMPTZ '2026-10-09 16:00:00+08'),
    (7, 8, 1, 20.00, TIMESTAMPTZ '2026-10-09 16:00:00+08'),
    (9, 2, 2, 30.00, TIMESTAMPTZ '2026-10-04 16:00:00+08'),
    (10, 6, 2, 128.00, TIMESTAMPTZ '2026-09-17 16:00:00+08'),
    (11, 3, 2, 120.00, TIMESTAMPTZ '2026-09-10 16:00:00+08'),
    (13, 5, 2, 88.00, TIMESTAMPTZ '2026-11-25 16:00:00+08'),
    (14, 1, 1, 68.00, TIMESTAMPTZ '2026-09-27 16:00:00+08'),
    (14, 6, 1, 128.00, TIMESTAMPTZ '2026-09-27 16:00:00+08'),
    (15, 6, 1, 128.00, TIMESTAMPTZ '2026-09-13 16:00:00+08'),
    (15, 5, 2, 88.00, TIMESTAMPTZ '2026-09-13 16:00:00+08'),
    (17, 4, 1, 150.00, TIMESTAMPTZ '2026-11-22 16:00:00+08'),
    (17, 8, 2, 20.00, TIMESTAMPTZ '2026-11-22 16:00:00+08'),
    (18, 2, 1, 30.00, TIMESTAMPTZ '2026-10-18 16:00:00+08'),
    (18, 3, 1, 120.00, TIMESTAMPTZ '2026-10-18 16:00:00+08'),
    (19, 4, 2, 150.00, TIMESTAMPTZ '2026-09-06 16:00:00+08'),
    (19, 2, 2, 30.00, TIMESTAMPTZ '2026-09-06 16:00:00+08'),
    (21, 4, 1, 150.00, TIMESTAMPTZ '2026-09-25 16:00:00+08'),
    (22, 4, 1, 150.00, TIMESTAMPTZ '2026-09-11 16:00:00+08'),
    (22, 5, 1, 88.00, TIMESTAMPTZ '2026-09-11 16:00:00+08'),
    (23, 6, 2, 128.00, TIMESTAMPTZ '2026-10-08 16:00:00+08'),
    (23, 8, 1, 20.00, TIMESTAMPTZ '2026-10-08 16:00:00+08'),
    (25, 3, 2, 120.00, TIMESTAMPTZ '2026-10-14 16:00:00+08'),
    (26, 4, 1, 150.00, TIMESTAMPTZ '2026-10-07 16:00:00+08'),
    (27, 2, 2, 30.00, TIMESTAMPTZ '2026-10-03 16:00:00+08'),
    (29, 1, 2, 68.00, TIMESTAMPTZ '2026-09-18 16:00:00+08'),
    (29, 5, 2, 88.00, TIMESTAMPTZ '2026-09-18 16:00:00+08'),
    (30, 7, 2, 268.00, TIMESTAMPTZ '2026-11-20 16:00:00+08'),
    (31, 7, 1, 268.00, TIMESTAMPTZ '2026-10-30 16:00:00+08'),
    (33, 6, 2, 128.00, TIMESTAMPTZ '2026-09-07 16:00:00+08'),
    (33, 8, 2, 20.00, TIMESTAMPTZ '2026-09-07 16:00:00+08'),
    (34, 5, 2, 88.00, TIMESTAMPTZ '2026-11-13 16:00:00+08'),
    (35, 8, 1, 20.00, TIMESTAMPTZ '2026-10-08 16:00:00+08'),
    (37, 1, 2, 68.00, TIMESTAMPTZ '2026-09-22 16:00:00+08'),
    (38, 7, 2, 268.00, TIMESTAMPTZ '2026-10-24 16:00:00+08'),
    (38, 4, 2, 150.00, TIMESTAMPTZ '2026-10-24 16:00:00+08'),
    (39, 8, 2, 20.00, TIMESTAMPTZ '2026-11-28 16:00:00+08'),
    (39, 2, 1, 30.00, TIMESTAMPTZ '2026-11-28 16:00:00+08'),
    (41, 5, 2, 88.00, TIMESTAMPTZ '2026-12-14 16:00:00+08'),
    (42, 5, 1, 88.00, TIMESTAMPTZ '2026-12-14 16:00:00+08'),
    (43, 4, 1, 150.00, TIMESTAMPTZ '2026-12-13 16:00:00+08'),
    (43, 2, 1, 30.00, TIMESTAMPTZ '2026-12-13 16:00:00+08'),
    (44, 8, 2, 20.00, TIMESTAMPTZ '2026-12-14 16:00:00+08'),
    (44, 1, 1, 68.00, TIMESTAMPTZ '2026-12-14 16:00:00+08'),
    (45, 2, 2, 30.00, TIMESTAMPTZ '2026-12-14 16:00:00+08'),
    (45, 7, 1, 268.00, TIMESTAMPTZ '2026-12-14 16:00:00+08'),
    (46, 3, 2, 120.00, TIMESTAMPTZ '2026-12-14 16:00:00+08'),
    (46, 6, 1, 128.00, TIMESTAMPTZ '2026-12-14 16:00:00+08'),
    (47, 7, 1, 268.00, TIMESTAMPTZ '2026-12-13 16:00:00+08'),
    (47, 4, 1, 150.00, TIMESTAMPTZ '2026-12-13 16:00:00+08'),
    (48, 6, 1, 128.00, TIMESTAMPTZ '2026-12-14 16:00:00+08');

-- ----------------------------------------------------------------------------
-- 9) payment 支付流水 96 笔（kind=refund 的金额也记正数，靠 kind 区分方向）
-- ----------------------------------------------------------------------------
INSERT INTO payment (payment_no, check_in_record_id, kind, method, amount, paid_at,
                     operator_user_id, remark) VALUES
    ('P20261109001', 1, 'deposit', 'wechat', 906.00, TIMESTAMPTZ '2026-11-09 14:30:00+08', 2, NULL),
    ('P20261111002', 1, 'refund', 'wechat', 100.00, TIMESTAMPTZ '2026-11-11 12:10:00+08', 2, 'E07：押金多收部分退回'),
    ('P20261106003', 2, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-11-06 14:30:00+08', 3, NULL),
    ('P20261109004', 2, 'room_fee', 'card', 1052.00, TIMESTAMPTZ '2026-11-09 12:00:00+08', 3, NULL),
    ('P20261023005', 3, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-10-23 14:30:00+08', 2, NULL),
    ('P20261025006', 3, 'room_fee', 'card', 676.00, TIMESTAMPTZ '2026-10-25 12:00:00+08', 2, NULL),
    ('P20261007007', 4, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-10-07 14:30:00+08', 3, NULL),
    ('P20261009008', 4, 'room_fee', 'card', 1264.00, TIMESTAMPTZ '2026-10-09 12:00:00+08', 3, NULL),
    ('P20261109009', 5, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-11-09 14:30:00+08', 2, NULL),
    ('P20261113010', 5, 'room_fee', 'wechat', 1940.00, TIMESTAMPTZ '2026-11-13 12:00:00+08', 2, NULL),
    ('P20261014011', 6, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-10-14 14:30:00+08', 3, NULL),
    ('P20261018012', 6, 'room_fee', 'wechat', 5072.00, TIMESTAMPTZ '2026-10-18 12:00:00+08', 3, NULL),
    ('P20261009013', 7, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-10-09 14:30:00+08', 2, NULL),
    ('P20261013014', 7, 'room_fee', 'wechat', 1220.00, TIMESTAMPTZ '2026-10-13 12:00:00+08', 2, NULL),
    ('P20261121015', 8, 'deposit', 'card', 676.00, TIMESTAMPTZ '2026-11-21 14:30:00+08', 3, NULL),
    ('P20261123016', 8, 'refund', 'card', 100.00, TIMESTAMPTZ '2026-11-23 12:10:00+08', 3, 'E07：押金多收部分退回'),
    ('P20261004017', 9, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-10-04 14:30:00+08', 2, NULL),
    ('P20261008018', 9, 'room_fee', 'alipay', 1172.00, TIMESTAMPTZ '2026-10-08 12:00:00+08', 2, NULL),
    ('P20260917019', 10, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-09-17 14:30:00+08', 3, NULL),
    ('P20260918020', 10, 'room_fee', 'cash', 344.00, TIMESTAMPTZ '2026-09-18 12:00:00+08', 3, NULL),
    ('P20260910021', 11, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-09-10 14:30:00+08', 2, NULL),
    ('P20260914022', 11, 'room_fee', 'wechat', 2792.00, TIMESTAMPTZ '2026-09-14 12:00:00+08', 2, NULL),
    ('P20260920023', 12, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-09-20 14:30:00+08', 3, NULL),
    ('P20260922024', 12, 'room_fee', 'cash', 376.00, TIMESTAMPTZ '2026-09-22 12:00:00+08', 3, NULL),
    ('P20261125025', 13, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-11-25 14:30:00+08', 2, NULL),
    ('P20261128026', 13, 'room_fee', 'wechat', 840.00, TIMESTAMPTZ '2026-11-28 12:00:00+08', 2, NULL),
    ('P20260927027', 14, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-09-27 14:30:00+08', 3, NULL),
    ('P20261001028', 14, 'room_fee', 'cash', 1308.00, TIMESTAMPTZ '2026-10-01 12:00:00+08', 3, NULL),
    ('P20260913029', 15, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-09-13 14:30:00+08', 2, NULL),
    ('P20260916030', 15, 'room_fee', 'wechat', 1088.00, TIMESTAMPTZ '2026-09-16 12:00:00+08', 2, NULL),
    ('P20260926031', 16, 'deposit', 'alipay', 488.00, TIMESTAMPTZ '2026-09-26 14:30:00+08', 3, NULL),
    ('P20260927032', 16, 'refund', 'alipay', 100.00, TIMESTAMPTZ '2026-09-27 12:10:00+08', 3, 'E07：押金多收部分退回'),
    ('P20261122033', 17, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-11-22 14:30:00+08', 2, NULL),
    ('P20261123034', 17, 'room_fee', 'alipay', 278.00, TIMESTAMPTZ '2026-11-23 12:00:00+08', 2, NULL),
    ('P20261018035', 18, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-10-18 14:30:00+08', 3, NULL),
    ('P20261022036', 18, 'room_fee', 'wechat', 2702.00, TIMESTAMPTZ '2026-10-22 12:00:00+08', 3, NULL),
    ('P20260906037', 19, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-09-06 14:30:00+08', 2, NULL),
    ('P20260910038', 19, 'room_fee', 'card', 1712.00, TIMESTAMPTZ '2026-09-10 12:00:00+08', 2, NULL),
    ('P20261025039', 20, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-10-25 14:30:00+08', 3, NULL),
    ('P20261026040', 20, 'room_fee', 'cash', 288.00, TIMESTAMPTZ '2026-10-26 12:00:00+08', 3, NULL),
    ('P20260925041', 21, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-09-25 14:30:00+08', 2, NULL),
    ('P20260929042', 21, 'room_fee', 'card', 1502.00, TIMESTAMPTZ '2026-09-29 12:00:00+08', 2, NULL),
    ('P20260911043', 22, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-09-11 14:30:00+08', 3, NULL),
    ('P20260914044', 22, 'room_fee', 'wechat', 1202.00, TIMESTAMPTZ '2026-09-14 12:00:00+08', 3, NULL),
    ('P20261008045', 23, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-10-08 14:30:00+08', 2, NULL),
    ('P20261011046', 23, 'room_fee', 'alipay', 1240.00, TIMESTAMPTZ '2026-10-11 12:00:00+08', 2, NULL),
    ('P20261123047', 24, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-11-23 14:30:00+08', 3, NULL),
    ('P20261126048', 24, 'room_fee', 'cash', 964.00, TIMESTAMPTZ '2026-11-26 12:00:00+08', 3, NULL),
    ('P20261014049', 25, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-10-14 14:30:00+08', 2, NULL),
    ('P20261015050', 25, 'room_fee', 'alipay', 1328.00, TIMESTAMPTZ '2026-10-15 12:00:00+08', 2, NULL),
    ('P20261007051', 26, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-10-07 14:30:00+08', 3, NULL),
    ('P20261009052', 26, 'room_fee', 'card', 3814.00, TIMESTAMPTZ '2026-10-09 12:00:00+08', 3, NULL),
    ('P20261003053', 27, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-10-03 14:30:00+08', 2, NULL),
    ('P20261005054', 27, 'room_fee', 'alipay', 724.00, TIMESTAMPTZ '2026-10-05 12:00:00+08', 2, NULL),
    ('P20260906055', 28, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-09-06 14:30:00+08', 3, NULL),
    ('P20260909056', 28, 'room_fee', 'wechat', 964.00, TIMESTAMPTZ '2026-09-09 12:00:00+08', 3, NULL),
    ('P20260918057', 29, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-09-18 14:30:00+08', 2, NULL),
    ('P20260919058', 29, 'room_fee', 'card', 400.00, TIMESTAMPTZ '2026-09-19 12:00:00+08', 2, NULL),
    ('P20261120059', 30, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-11-20 14:30:00+08', 3, NULL),
    ('P20261122060', 30, 'room_fee', 'wechat', 2912.00, TIMESTAMPTZ '2026-11-22 12:00:00+08', 3, NULL),
    ('P20261030061', 31, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-10-30 14:30:00+08', 2, NULL),
    ('P20261102062', 31, 'room_fee', 'card', 1232.00, TIMESTAMPTZ '2026-11-02 12:00:00+08', 2, NULL),
    ('P20260928063', 32, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-09-28 14:30:00+08', 3, NULL),
    ('P20261001064', 32, 'room_fee', 'alipay', 664.00, TIMESTAMPTZ '2026-10-01 12:00:00+08', 3, NULL),
    ('P20260907065', 33, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-09-07 14:30:00+08', 2, NULL),
    ('P20260909066', 33, 'room_fee', 'wechat', 872.00, TIMESTAMPTZ '2026-09-09 12:00:00+08', 2, NULL),
    ('P20261113067', 34, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-11-13 14:30:00+08', 3, NULL),
    ('P20261114068', 34, 'room_fee', 'alipay', 364.00, TIMESTAMPTZ '2026-11-14 12:00:00+08', 3, NULL),
    ('P20261008069', 35, 'deposit', 'wechat', 200.00, TIMESTAMPTZ '2026-10-08 14:30:00+08', 2, NULL),
    ('P20261010070', 35, 'room_fee', 'wechat', 396.00, TIMESTAMPTZ '2026-10-10 12:00:00+08', 2, NULL),
    ('P20261030071', 36, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-10-30 14:30:00+08', 3, NULL),
    ('P20261102072', 36, 'room_fee', 'card', 1264.00, TIMESTAMPTZ '2026-11-02 12:00:00+08', 3, NULL),
    ('P20260922073', 37, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-09-22 14:30:00+08', 2, NULL),
    ('P20260926074', 37, 'room_fee', 'card', 1248.00, TIMESTAMPTZ '2026-09-26 12:00:00+08', 2, NULL),
    ('P20261024075', 38, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-10-24 14:30:00+08', 3, NULL),
    ('P20261028076', 38, 'room_fee', 'card', 2588.00, TIMESTAMPTZ '2026-10-28 12:00:00+08', 3, NULL),
    ('P20261128077', 39, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-11-28 14:30:00+08', 2, NULL),
    ('P20261130078', 39, 'room_fee', 'alipay', 446.00, TIMESTAMPTZ '2026-11-30 12:00:00+08', 2, NULL),
    ('P20261130079', 40, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-11-30 14:30:00+08', 3, NULL),
    ('P20261202080', 40, 'room_fee', 'card', 376.00, TIMESTAMPTZ '2026-12-02 12:00:00+08', 3, NULL),
    ('P20261214081', 41, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-12-14 14:30:00+08', 2, NULL),
    ('P20261215082', 41, 'service_fee', 'wechat', 176.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 2, '在住期间增值服务费'),
    ('P20261214083', 42, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-12-14 14:30:00+08', 3, NULL),
    ('P20261215084', 42, 'service_fee', 'wechat', 88.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 3, '在住期间增值服务费'),
    ('P20261213085', 43, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-12-13 14:30:00+08', 2, NULL),
    ('P20261215086', 43, 'service_fee', 'wechat', 180.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 2, '在住期间增值服务费'),
    ('P20261214087', 44, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-12-14 14:30:00+08', 3, NULL),
    ('P20261215088', 44, 'service_fee', 'wechat', 108.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 3, '在住期间增值服务费'),
    ('P20261214089', 45, 'deposit', 'cash', 200.00, TIMESTAMPTZ '2026-12-14 14:30:00+08', 2, NULL),
    ('P20261215090', 45, 'service_fee', 'wechat', 328.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 2, '在住期间增值服务费'),
    ('P20261214091', 46, 'deposit', 'alipay', 200.00, TIMESTAMPTZ '2026-12-14 14:30:00+08', 3, NULL),
    ('P20261215092', 46, 'service_fee', 'wechat', 368.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 3, '在住期间增值服务费'),
    ('P20261213093', 47, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-12-13 14:30:00+08', 2, NULL),
    ('P20261215094', 47, 'service_fee', 'wechat', 418.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 2, '在住期间增值服务费'),
    ('P20261214095', 48, 'deposit', 'card', 200.00, TIMESTAMPTZ '2026-12-14 14:30:00+08', 3, NULL),
    ('P20261215096', 48, 'service_fee', 'wechat', 128.00, TIMESTAMPTZ '2026-12-15 10:00:00+08', 3, '在住期间增值服务费');

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
    (1, 'occupied'),
    (3, 'reserved'),
    (4, 'reserved'),
    (5, 'reserved'),
    (6, 'reserved'),
    (7, 'occupied'),
    (8, 'reserved'),
    (9, 'reserved'),
    (10, 'cleaning'),
    (11, 'reserved'),
    (12, 'occupied'),
    (13, 'occupied'),
    (14, 'occupied'),
    (15, 'occupied'),
    (19, 'reserved'),
    (20, 'reserved'),
    (21, 'reserved'),
    (23, 'reserved'),
    (24, 'occupied'),
    (26, 'reserved'),
    (27, 'occupied'),
    (31, 'cleaning'),
    (32, 'reserved'),
    (34, 'reserved'),
    (35, 'reserved'),
    (36, 'maintenance'),
    (37, 'reserved'),
    (38, 'disabled')
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

SELECT '03_seed.sql 执行完成：96 条预订 / 48 条入住 / 96 笔支付 / 57 条服务明细' AS result;

COMMIT;

