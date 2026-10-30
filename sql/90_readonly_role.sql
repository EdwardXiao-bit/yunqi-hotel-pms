-- 90_readonly_role.sql —— 为 MCP / 报表 / 演示创建一个只读账号
--
-- 用途：给 PostgreSQL MCP Server（或任何外部工具）一个**只能读**的数据库账号，
--       避免把 postgres 超级用户口令交给第三方进程。
-- 说明：本脚本不属于建库版本序列（00→01→02→03），随时可重复执行；改口令也跑它。
-- 执行：psql -U postgres -d yunqi_hotel -v ON_ERROR_STOP=1 -f "sql/90_readonly_role.sql"
--       密码运行时用 \prompt 输入，不写进文件、不进 git。
--
-- NOTE (ASCII on purpose): the header/comments above are Chinese but placed AFTER
--       \encoding UTF8 so psql decodes them correctly on a GBK console.

\set ON_ERROR_STOP on
\encoding UTF8
SET search_path TO public;

\prompt '请输入只读账号 yunqi_ro 的密码（输入不回显、不落盘）: ' ro_pw

-- 1) 建角色（已存在则跳过；已存在时下面 ALTER 覆盖口令）
SELECT format(
         'CREATE ROLE yunqi_ro LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
         :'ro_pw'
       )
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'yunqi_ro')
\gexec

-- 2) 口令改为本次输入（角色已存在时同样生效）
ALTER ROLE yunqi_ro PASSWORD :'ro_pw';

-- 3) 最小权限：连库 + 读 schema + 读全部表 + 调用函数（fn_available_rooms 等在函数里读表）
GRANT CONNECT ON DATABASE yunqi_hotel TO yunqi_ro;
GRANT USAGE ON SCHEMA public TO yunqi_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO yunqi_ro;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO yunqi_ro;

-- 4) 以后新建的表也自动可读（Django 侧不建业务表，但视图/新表仍受益）
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO yunqi_ro;

-- 5) 兜底：确保没有写权限（显式撤销，已无权限时是空操作）
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM yunqi_ro;

-- 6) 自检
SELECT r.rolname,
       r.rolsuper,
       r.rolcreatedb,
       r.rolcreaterole,
       r.rolcanlogin,
       pg_get_userbyid(d.datdba) AS db_owner
FROM pg_roles r
CROSS JOIN pg_database d
WHERE r.rolname = 'yunqi_ro' AND d.datname = 'yunqi_hotel';

SELECT table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) AS privileges
FROM information_schema.role_table_grants
WHERE grantee = 'yunqi_ro' AND table_schema = 'public'
GROUP BY table_name
ORDER BY table_name;

SELECT '90_readonly_role.sql 执行完成：yunqi_ro 已具备只读权限' AS result;
