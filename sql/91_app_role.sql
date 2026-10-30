-- =============================================================================
-- 91_app_role.sql —— 为 Django 应用创建最小权限账号（一次性执行，可重复执行）
-- =============================================================================
-- 为什么需要它：
--   开发/演示时 Django 用 psql 的 postgres 超级用户连库并不合适，也没有必要。
--   这里创建一个只具备业务表 DML 权限的账号 yunqi_app，密码由执行者自己输入
--   （用 psql 的 \password 元命令连问两次、不回显、不写进脚本、不进 git），随后把
--   同一个密码写进仓库根目录的 `.env`（该文件已被 .gitignore 忽略）。
--
-- 执行方式（PowerShell，口令自己输）：
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d yunqi_hotel `
--       -v ON_ERROR_STOP=1 -f sql\91_app_role.sql
--
-- 为什么不用 \prompt + ALTER ROLE PASSWORD :'var'：
--   2026-10-30 实测，那样写在 Windows 控制台里可能拿到空值，导致角色建好但
--   `pg_authid.rolpassword` 为 NULL（Django 连库报「口令认证失败」）。
--   \password 由 psql 自己走加密与提示，稳定得多。
--
-- 之后在 `.env` 里写：
--   DB_USER=yunqi_app
--   DB_PASSWORD=<你刚才输入的密码>
--
-- 注意：
--   1) 本脚本不属于 00→01→02→03 建库序列，可随时重跑（幂等）。
--   2) 不给超级用户、不给 CREATE 数据库/角色的权限；DDL 仍由 postgres 跑 sql/ 脚本。
--   3) 若之前执行过 90_readonly_role.sql，只读账号 yunqi_ro 与本案互不影响。
-- =============================================================================

\set ON_ERROR_STOP on
\encoding UTF8
SET search_path TO public;

-- 1) 角色：存在则跳过创建（口令不在这里写死，交给下面的 \password 元命令）
SELECT 'CREATE ROLE yunqi_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'yunqi_app')
\gexec

-- 用 psql 的 \password 元命令设口令：连问两次、输入不回显，
-- 由 psql 自己发 ALTER ROLE ... PASSWORD，不会把明文写进脚本或命令历史。
-- 注意：\password 是 psql 元命令，不能放进 -c，必须在交互会话里执行。
\password yunqi_app

-- 2) 连接与 schema 使用权限
GRANT CONNECT ON DATABASE yunqi_hotel TO yunqi_app;
GRANT USAGE ON SCHEMA public TO yunqi_app;

-- 3) 业务表读写（13 张表 + 视图）
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO yunqi_app;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO yunqi_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO yunqi_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO yunqi_app;

-- 4) 以后新建的表/序列/函数也自动授权（下一个 owner 建的）
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO yunqi_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO yunqi_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO yunqi_app;

-- 5) 明确不给的权限（防止误操作，写清便于报告说明）
REVOKE CREATE ON SCHEMA public FROM yunqi_app;
REVOKE TRUNCATE ON ALL TABLES IN SCHEMA public FROM yunqi_app;

-- 6) 自检
SELECT rolname AS role, rolcanlogin AS can_login, rolsuper AS is_superuser
FROM pg_roles
WHERE rolname IN ('yunqi_app', 'yunqi_ro')
ORDER BY rolname;

SELECT grantee, privilege_type, COUNT(*) AS objects
FROM information_schema.role_table_grants
WHERE grantee = 'yunqi_app'
GROUP BY grantee, privilege_type
ORDER BY privilege_type;

SELECT '91_app_role.sql 执行完成：应用账号 yunqi_app 已就绪（DML + 函数执行，无 DDL）' AS result;
