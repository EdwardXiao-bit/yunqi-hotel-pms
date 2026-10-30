-- =============================================================================
-- 00_database.sql —— 创建演示库 yunqi_hotel（可重复执行）
-- 项目：云栖酒店客房预订与入住管理系统（第 14 组）
--
-- 用法（必须连到 postgres 库执行，CREATE DATABASE 不能建在目标库自己身上）：
--   cd C:\Users\Ed\dsh_workspace\yunqi-hotel-pms
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 `
--       -d postgres -v ON_ERROR_STOP=1 -f sql/00_database.sql
--   口令在 psql 交互提示里输入，不写进脚本、不写进命令行。
--   建议先在终端执行 chcp 65001（切 UTF-8 控制台），中文输出才不会乱码；
--   脚本内部已用 \encoding UTF8 声明客户端编码，编码正确性与控制台代码页无关。
--
-- 设计要点：
--   1) CREATE DATABASE 不能出现在事务/DO 块里，所以用 psql 的 \gexec 实现幂等：
--      先 SELECT 出建库语句，再由 \gexec 执行；库已存在时 SELECT 返回 0 行，什么也不做。
--   2) Windows 中文环境的 template1 默认 locale 是 Chinese (Simplified)_China.936（WIN936），
--      与 ENCODING 'UTF8' 冲突（报 new encoding (UTF8) is incompatible with ... WIN936）。
--      因此必须 TEMPLATE template0 + 显式 LC_COLLATE/LC_CTYPE 'C'（按字节排序，足够课程设计用；
--      若要按中文拼音排序可改 ICU，见文件末尾注释）。
--   3) 时区在库级固定为 Asia/Shanghai，与 docs/AGENTS.md 的约定一致；
--      Django 侧 settings.py 的 TIME_ZONE 保持同值，避免报告里时间对不上。
-- =============================================================================

\set ON_ERROR_STOP on

-- NOTE (Windows): the console/psql client encoding defaults to GBK (cp936) while this
-- file is UTF-8. Without the line below psql declares GBK to the server and the server
-- mis-decodes our UTF-8 bytes, failing with:
--     invalid byte sequence for encoding "UTF8": 0xae 0xa2
-- Declaring the client encoding here fixes every Chinese literal/comment below.
\encoding UTF8

-- 1) 建库（幂等）
SELECT $sql$
CREATE DATABASE yunqi_hotel
    WITH OWNER    = postgres
         ENCODING = 'UTF8'
         LC_COLLATE = 'C'
         LC_CTYPE   = 'C'
         TEMPLATE   = template0
         CONNECTION LIMIT = -1
$sql$
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'yunqi_hotel')
\gexec

-- 2) 库级参数与注释（ALTER / COMMENT 天然幂等，可重复执行）
ALTER DATABASE yunqi_hotel SET timezone TO 'Asia/Shanghai';
ALTER DATABASE yunqi_hotel SET datestyle TO 'ISO, YMD';

COMMENT ON DATABASE yunqi_hotel IS
    '云栖酒店客房预订与入住管理系统 —— 《数据库系统原理》课程设计 第 14 组';

-- 3) 自检：打印编码、locale、时区，报告/截图可直接引用这段输出
SELECT d.datname,
       pg_encoding_to_char(d.encoding)  AS encoding,
       d.datcollate                      AS lc_collate,
       d.datctype                        AS lc_ctype,
       d.datacl,
       pg_get_userbyid(d.datdba)         AS owner
FROM pg_database d
WHERE d.datname = 'yunqi_hotel';

SHOW timezone;

-- =============================================================================
-- 后续步骤（都在 yunqi_hotel 库上执行，不要再用 postgres 库）：
--   psql -U postgres -h 127.0.0.1 -d yunqi_hotel -v ON_ERROR_STOP=1 -f sql/01_schema.sql
--   psql -U postgres -h 127.0.0.1 -d yunqi_hotel -v ON_ERROR_STOP=1 -f sql/02_constraints.sql
--   psql -U postgres -h 127.0.0.1 -d yunqi_hotel -v ON_ERROR_STOP=1 -f sql/03_seed.sql
--   psql -U postgres -h 127.0.0.1 -d yunqi_hotel -v ON_ERROR_STOP=1 -f sql/04_queries.sql
--
-- 可选：若要建专用应用角色（报告里可写“最小权限”），在 postgres 库上额外执行：
--   CREATE ROLE yunqi_app LOGIN PASSWORD '<自己设置的强口令>';
--   GRANT CONNECT ON DATABASE yunqi_hotel TO yunqi_app;
--   然后在 yunqi_hotel 库上：GRANT USAGE ON SCHEMA public TO yunqi_app;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA public
--       GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO yunqi_app;
--   Django 的 .env 里 DB_USER 用 yunqi_app —— 课程演示用 postgres 亦可，二选一写进报告即可。
--
-- 可选：若确实需要中文排序（按拼音排房型名），PG 18 可用 ICU locale：
--   CREATE DATABASE yunqi_hotel WITH TEMPLATE template0 ENCODING 'UTF8'
--       LOCALE_PROVIDER icu ICU_LOCALE 'zh-CN' LC_COLLATE 'C' LC_CTYPE 'C';
--   本课程设计不涉及排序展示，默认用 'C' 即可。
-- =============================================================================
