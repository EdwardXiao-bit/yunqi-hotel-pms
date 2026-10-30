-- =============================================================================
-- 05_django_tables.sql —— Django 框架表（一次性执行，可重复执行）
-- =============================================================================
-- 为什么单独一份：
--   本项目的业务表全部由 sql/01、02 建，Django 模型一律 managed = False，
--   因此不跑 `manage.py migrate`（否则会为业务模型生成第二份 DDL，违反
--   “DDL 唯一事实来源是 sql/ 脚本”的约定）。但登录依赖 SessionMiddleware，
--   它需要一张真实的 django_session 表 —— 这里用纯 SQL 建出来，与业务表
--   同源管理，进 git、可重复执行、报告里也能直接引用。
--
-- 执行顺序：00（建库）→ 01 → 02 → 03（种子）→ 05（本脚本）→ 启动 Django
-- 执行方式：
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d yunqi_hotel `
--       -v ON_ERROR_STOP=1 -f sql\05_django_tables.sql
-- =============================================================================

\set ON_ERROR_STOP on
\encoding UTF8
SET search_path TO public;

-- 1) 会话表：字段与长度对齐 Django 6.1 内置 sessions 后端
CREATE TABLE IF NOT EXISTS django_session (
    session_key  varchar(40)  NOT NULL,
    session_data text         NOT NULL,
    expire_date  timestamptz  NOT NULL,
    CONSTRAINT pk_django_session PRIMARY KEY (session_key)
);

COMMENT ON TABLE  django_session            IS 'Django 会话表（SessionMiddleware 使用；业务表见 app_user 等 13 张）';
COMMENT ON COLUMN django_session.session_key IS '会话键（浏览器 cookie 中保存）';
COMMENT ON COLUMN django_session.session_data IS '会话内容（base64 编码的序列化数据）';
COMMENT ON COLUMN django_session.expire_date  IS '过期时间；Django 定时清理';

-- 2) 过期清理走索引
CREATE INDEX IF NOT EXISTS idx_django_session_expire ON django_session (expire_date);

-- 3) 应用账号的 DML 权限（角色由 sql/91_app_role.sql 创建，未建则跳过）
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'yunqi_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON django_session TO yunqi_app;
        RAISE NOTICE 'GRANT OK: django_session -> yunqi_app';
    ELSE
        RAISE NOTICE 'SKIP: role yunqi_app not found (run sql/91_app_role.sql first if you need it)';
    END IF;
END
$$;

-- 4) 自检
SELECT
    c.relname                                   AS table_name,
    (SELECT count(*) FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'django_session') AS columns,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS size
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = 'django_session';

SELECT '05_django_tables.sql 执行完成：django_session 已就绪' AS result;
