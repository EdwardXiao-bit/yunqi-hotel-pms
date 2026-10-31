# 数据库系统原理课程设计 · 14 组

> 项目根 `AGENTS.md`：给 AI 助手与组员共用的项目约定。**当前状态（2026-10-31）：选题、功能清单、技术栈、13 张表结构与 SQL 脚本均已定案并全部 psql 实跑通过（阶段 0–1 完成）；第一次提交件 v2（A4 三页，39 项断言全 PASS）待上传；Django 骨架 + 登录 + 三角色权限（T4–T5）已真库验收；**F02 房态维护、F03 可用房查询、F04 预订提交、F05 预订管理、F06 入住与续住办理、F07 退房结算、F08 房态看板（P02/P03/P04/P06/P07/P08/P09）已落地并双模式冒烟通过**；F01/F09 未开始。**
> 最后更新：2026-10-31（T10 的 F08+F02 落地：`src/core/views/board.py` + `templates/reception/room_board.html`（楼层/房型筛选、4 态配色、内联清洁完成/置为清洁中/登记维修停用/结束维修）、房态动作在事务内 `set_config('app.current_user_id')` 让触发器记录操作人；冒烟 sqlite 141 项 / 真库只读 100 项；`work/check_f08_real.py` 真库事务内 22 项核对后回滚，`changed_by` 实测=前台账号）

## 1 项目事实（已确认）

- 课程：四川大学《数据库系统原理》课程设计（2026 学年）
- 小组：**第 14 组**，2 人
  - 胡宇书（组长）
  - 肖铭皓
- 指导教师：郭际香（见 `docs/报告封面文档.doc`）
- 技术栈（已定案 2026-10-29，不再改）：**PostgreSQL 18 + Django 6.1 + Bootstrap 4.6（AdminLTE 3.2 模板 + 服务端模板渲染）**
- 运行时（本机实测）：Python 3.12.7（`D:\anaconda3\python.exe`）、Django 6.1.2、psycopg2 2.9.13、PostgreSQL 18（服务 `postgresql-x64-18` 运行中）
- 项目名称（题目）：**云栖酒店客房预订与入住管理系统**（2026-10-29 定名；对应教师给定方案六原题名“酒店客房预订与入住管理系统”）
- 交付件命名：**`第14组_酒店客房预订与入住管理系统`**（课程要求“第x组_给定方案名称”，文件名用方案名、正文标题用自定项目名）
- 仓库与本地目录名：**`yunqi-hotel-pms`**（2026-10-30 由 `database-course-project` 改名；远端 <https://github.com/EdwardXiao-bit/yunqi-hotel-pms>）
- 选题（已定案）：给定方案六，决策过程见 `docs/方案对比-六方案评估.md`、`docs/自定选题候选.md`
- 数据库：PostgreSQL 18，库名 `yunqi_hotel`，端口 `5432`，编码 UTF8，时区 Asia/Shanghai
- 角色：客户（customer）、前台工作人员（receptionist）、管理员（admin）

## 2 硬节点

| 事项 | 截止 | 备注 |
| --- | --- | --- |
| 项目名称 + 描述 + 功能清单（Word） | **2026-11-12 23:59** | 提交到 send2me 链接；命名 `第14组_方案名` |
| 系统检查 + PPT 演示 | 第 15–16 周 | 占课程设计总分 60% |
| 课程报告（A4 打印） | 检查系统时交 | 版式见 `docs/00-作业要求与格式要点.md` 第 4 节 |

## 3 目录约定

```
yunqi-hotel-pms/
├─ AGENTS.md                    本项目约定（本文件）
├─ docs/                        交付文档与设计文档
│  ├─ 00-作业要求与格式要点.md   课程要求事实提取（已建）
│  ├─ 方案对比-六方案评估.md     选题决策依据：6 方案打分（已建）
│  ├─ 自定选题候选.md           自拟题目备选 A–E（已建，未采用）
│  ├─ 01-功能清单.md            项目名/描述/角色/9 项功能/异常清单（已建）
│  ├─ 02-数据库设计.md          ER/关系、13 表结构、约束与索引、触发器与视图、数据样例（已建 2026-10-30）
│  ├─ 03-实施计划.md            里程碑/WBS/风险/测试验收（已建）
│  ├─ 04-报告撰写规范.md        6 章大纲与版式参数（待写）
│  ├─ 05-查询结果与测试记录.md   04_queries 的实测结果，报告 4 章素材（已建 2026-10-30）
│  ├─ 页面约定.md               14 个业务页 + 3 个错误页的 URL/模板/表单字段/负责人契约（已建 2026-10-30，WBS T4 前置）
│  └─ 2026学年…docx / 报告封面文档.doc   教师下发原件，只读
├─ tools/                       docx/doc 解析 + 交付件生成脚本
│  ├─ dump_docx.py / doc_extract.py  读教师原件
│  ├─ build_submission_xlsx.py 生成功能清单 Excel
│  ├─ build_submission_docx.py 生成 Word 汇总（内嵌截图）
│  ├─ build_seed_sql.py        生成 sql/03_seed.sql（30 客户/96 预订/48 入住/96 支付/57 服务明细，含冲突自检）
│  ├─ smoke_web.py             Web 冒烟测试：默认离线 sqlite（自建 13 表+假数据），`--mode real` 走真库
│  └─ verify_submission.py     两个交付件的结构与版式自检
├─ deliverables/                对外交付件（第一次提交）
│  ├─ 第14组_酒店客房预订与入住管理系统.docx      文件名按给定方案名（内部项目名为云栖…）
│  ├─ 第14组_酒店客房预订与入住管理系统_功能清单.xlsx
│  └─ images/feature-list.png   300 dpi 表格截图，Word 内嵌源
├─ work/                        脚本中间产物（可清理）
├─ sql/                         00–04 均已写完并 psql 实跑通过（13 表版）；05_django_tables.sql（会话表，已执行）、90_readonly_role.sql（MCP 只读账号）、91_app_role.sql（Django 最小权限账号，已执行）
└─ src/                         Django 6.1 工程（T4–T5 已落地）：manage.py、config/、core/、templates/、static/（vendor/adminlte 本地资源）
```

- `docs/` 内教师原件**只读**，派生文件另起新名，不要覆盖。
- 交付物命名严格按 `第14组_<方案名>`，编号文档按 `NN-名称.md`。
- 已建文档之间不要重复内容：功能细节只写 `01`，排期只写 `03`，实现约定写本文件。

## 4 技术约定（骨架，实现期回填）

### 4.1 数据库（PostgreSQL）

- 命名：表 `snake_case` 复数（`schedule` 这类不可数词保持单数）、字段 `snake_case`。
- 约束**必须显式命名**：`pk_` / `fk_` / `uq_` / `ck_` / `idx_` 前缀，便于报告 3.2.2 直接引用。
- 每个业务表必须有注释 `COMMENT ON TABLE/COLUMN`（报告截图可直接用）。
- 时间统一 `timestamptz`，日期区间用 `daterange` / `tsrange`；不用字符串存日期。
- 状态字段用 `CHECK (status IN (...))` 而非 PG 原生 ENUM（迁移与报告书写都省事）。
- 业务约束优先下沉到数据库（`CHECK`、部分唯一索引、`EXCLUDE`），应用层只做提示文案 —— 这是本作业 50% 得分点的核心策略。
- 每个库版本对应一份 `sql/` 脚本：`01_schema.sql`、`02_constraints.sql`、`03_seed.sql`、`04_queries.sql`；可重复执行（`DROP ... IF EXISTS` / `IF NOT EXISTS`）。
- **区间排他约束的落地方式**（本作业的技术核心）：`reservation` 保留 `check_in_date` / `check_out_date` 两个 `date` 列（报告 3.2.2 表结构好写），另加生成列
  `during daterange GENERATED ALWAYS AS (daterange(check_in_date, check_out_date, '[)')) STORED`，
  `EXCLUDE USING gist (room_id WITH =, during WITH &&) WHERE (status IN ('pending','confirmed','checked_in'))` 建在生成列上（约束名 `ex_reservation_room_overlap`）。
- **DDL 唯一事实来源是 `sql/` 脚本**（2026-10-30 定）：Django 模型一律 `managed = False`，表由脚本创建，`manage.py migrate` 只建 `auth_*`/`contenttypes`/`sessions` 等框架表；不再用 `migrations.RunSQL` 重写一份 DDL（避免两份漂移）。表结构文档见 `docs/02-数据库设计.md`。
- **表数 13 张**（2026-10-30 晚定，按胡宇书提交件文案合并）：11 张业务表 + `room_block`（维修/停用**日期区间**）+ `reservation_price`（逐日成交价格）。
- **房态 4 态**（2026-10-30 晚定）：`room.status` 只表达当下物理可用性 `available / cleaning / maintenance / disabled`；“已预订”“入住中”由 `reservation` / `check_in_record` 推导，**不再写进房态字段**。`room_status_log` 记录 4 态流转。
- **维修/停用区间**：`room_block(room_id, start_date, end_date, block_type IN ('maintenance','disabled'), reason, created_by)`，生成列 `during` + `EXCLUDE USING gist (room_id WITH =, during WITH &&)`（`ex_room_block_overlap`）；可售房夜按它扣减。
- **逐日成交价格**：`reservation_price(reservation_id, stay_date, price)`，`UNIQUE (reservation_id, stay_date)`；触发器 `fn_sync_reservation_prices()` 按 `rate_plan` 命中价/标准价逐日生成明细，`fn_refresh_reservation_total()` 汇总回 `reservation.total_amount`；后续调价不影响已确认价格。
- **跨表冲突校验**：`fn_check_reservation_block()`（订单区间 vs 维修停用，23514）与 `fn_check_room_block_order()`（新增维修停用 vs 有效订单，23514）。
- **营业收入口径**（2026-10-30 晚定）：按 `check_in_record.actual_checkout_at`（退房结算日期）归月，押金不计收入，退款冲减；入住率分母扣维修/停用房夜。

### 4.2 后端（Django，服务端渲染）

- 工程：`src/` 下 `manage.py` + `config/`（settings/urls/wsgi）+ 业务 app `core/`；单进程 `python manage.py runserver 8000`，**不拆前后端**。
- 渲染：服务端模板 + 表单 POST（`{% csrf_token %}`）；不写 JSON API、不引 DRF。写操作走 POST → `redirect()` + `messages`，杜绝“Ajax 提交 + 前端提示”的双份校验。
- SQL 纪律：复杂查询（可用房、入住率、月度营业额）用 `connection.cursor()` 手写 SQL 或 `QuerySet.raw()`，ORM 只做简单 CRUD —— 报告 4 章要贴**真实执行的 SQL**。
- 异常：业务校验失败抛 `ValidationError`，视图捕获后 `messages.error()` 并回显原页面；数据库 `IntegrityError`（尤其 EXCLUDE 冲突）必须映射成中文提示，E02/E04 靠这一层。
- 鉴权：自定义用户模型 `core.AppUser`（表 `app_user`，`managed = False`）用 `role` 列区分 customer / receptionist / admin，`@login_required` + 自定义 `role_required` 装饰器；不用 `Group` 绕一层，不自己造 JWT。
- 配置：`SECRET_KEY`、DB 口令走环境变量（`.env` 不入库，提供 `.env.example`）；本机 `.env` 已配 `DB_USER=yunqi_app`。**设置角色口令用 psql 元命令 `\password <role>`**，不要用 `\prompt` + `ALTER ROLE ... PASSWORD :'var'`（Windows 控制台下 `\prompt` 取到空值，2026-10-30 实测踩过，表现为 psycopg2 `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xd6`）。
- **工程现状**（2026-10-30 晚落地，路径以 `src/` 为根）：`config/settings.py` 自带极简 `.env` 解析（不引第三方包，先读仓库根 `.env` 再读 `src/.env`，不覆盖已有环境变量）；`INSTALLED_APPS` **不含 `django.contrib.admin`**（业务后台自建，见 T11）；URL 命名空间 `core:`（`core:customer_home` / `core:reception_home` / `core:manage_home` / `core:login` / `core:logout`）。
- **模型映射**：13 个模型全部 `managed = False` + 显式 `db_table` 与 `db_column`，外键 `on_delete=DO_NOTHING`（删除策略只听 SQL 的 `ON DELETE`）；`AppUser` 继承 `AbstractBaseUser`（`AUTH_USER_MODEL = 'core.AppUser'`），认证后端 `core.backends.AppUserBackend`，种子口令统一 `Hotel@123`（PBKDF2，`PASSWORD_HASHERS` 首位保留 `pbkdf2_sha256` 以兼容种子哈希）。
- **权限**：`core.decorators.role_required(*roles)`（未登录跳登录页、角色不符 403）+ `core.roles.ROLE_HOME_URL_NAME` 决定三角色落地页；侧边栏由 `core.roles.NAV_SECTIONS` 按角色过滤、经 `core.context_processors.navigation` 注入。
- **交互细节**：登出只接受 POST（GET 直接回登录页）；错误页 `handler403/404/500` 走 `core.views.errors`；模板 `partials/messages.html` 渲染 `messages`（`MESSAGE_TAGS` 把 error 映射成 `danger`）。
- 数据库账号建议用 `sql/91_app_role.sql` 建的 `yunqi_app`（最小权限：`SELECT/INSERT/UPDATE/DELETE` + 序列 usage + 函数 execute，无 DDL），口令写进 `.env` 的 `DB_PASSWORD`。
- **验证方式**：`python tools/smoke_web.py`（默认离线 sqlite：把 13 个模型临时置 `managed=True` 建表灌假数据，35 项断言，不依赖库口令；需 `PYTHONPATH` 同时含 `src` 与 `work`，Windows 下用分号分隔）与 `python tools/smoke_web.py --mode real`（真库 + 种子账号，先跑 `_preflight_real_db()`：基表数 / `django_session` / 种子账号 3/3 / EXCLUDE 条数，失败给中文排查提示）。两者当前分别为 **141/141（离线 sqlite）** 与 **100/100（真库只读）**（F02–F08 落地后）；真库**写入**路径另由 `work/check_f04_real.py`（下单/确认/取消 15 项）、`work/check_f06_real.py`（入住/重复入住/续住 22 项）、`work/check_f07_real.py`（入住→结算→重复结算 26 项）与 `work/check_f08_real.py`（房态变更→触发器日志→维修区间→冲突拒绝→结束维修 22 项）在事务内真实写入并核对触发器回写后强制回滚，不污染演示库。

### 4.3 前端（AdminLTE 3.2 + Bootstrap 4.6）

- 版本：AdminLTE **3.2**（[官方文档](https://adminlte.io/docs/3.2/)，仓库 ColorlibHQ/AdminLTE），底层 Bootstrap 4.6 + jQuery 3.5.1 + Popper 1.16.1，图标 FontAwesome 5。
- 落位：`static/vendor/adminlte/{dist,plugins}/` 放官方包；`static/css/site.css` 只放少量覆盖样式；**不用 CDN**（演示机可能断网）。
- 布局：`templates/base.html` + `templates/partials/{head,sidebar,navbar,footer,scripts}.html`，业务页 `{% extends 'base.html' %}` 只填 `{% block content %}`；登录页独立，不套后台布局。
- 个性化裁剪（官方包默认带全部 demo 与插件）：删 `pages/` 下 demo 页；插件按需引用，保留 Bootstrap/jQuery/Popper/FontAwesome/DataTables/DateRangePicker(moment)，统计图表优先 ECharts（不经 jQuery 插件链）；不用 Summernote、CodeMirror、Dropzone、FullCalendar、jsGrid、flot、uPlot、sparkline、jqvmap、pace、filterizr、pdfmake 等。
- 交互：后端 `messages` → Bootstrap alert / toastr 渲染；删除、取消预订等破坏性操作加 SweetAlert2 二次确认。
- 列表页分页：用 Django `Paginator` **服务端分页** + 表单单选/日期筛选，查询在库里跑；**不用 DataTables 前端分页**（会砍掉“多表查询”的展示，报告 4 章没 SQL 可贴）。DataTables 只在纯展示型静态表格上可选项。
- 中文观感：`site.css` 补中文字体栈（`"Microsoft YaHei", "PingFang SC", ...`）与表格/表单字号，避免 Bootstrap 默认英文排版。

## 5 文档与报告约定

- 报告版式以 `docs/00-作业要求与格式要点.md` 第 4 节为准（小四宋体、行距 20 磅、标题小二号黑体、摘要 150 字、参考文献五号宋体）。
- 报告 6 章结构固定，不得增删一级标题。
- 所有 SQL 片段必须**可直接在演示库执行**，报告里的查询结果截图与脚本一致。
- 生成文档只用 `tools/` 下脚本（python-docx / XlsxWriter），不手工改二进制文件；中文文件一律 UTF-8，不经 PowerShell 管道改写。
- 中文引号统一用弯引号“”，**不用直角引号（U+300C / U+300D）**（交付件、docs、代码注释一致；脚本里中文多，改文案优先用 Python 处理，别在 PowerShell 里写中文）。

## 6 协作与纪律（给 AI 助手）

- 每次会话先读本文件与 `docs/00`、`docs/方案对比`，再动手。
- 定案事项立即落盘到 `docs/`，不在对话里留结论。
- 改 SQL 后必须跑 `psql -f` 验证可重复执行，并保留输出。
- 教师下发原件不改；交付物（docx/pptx/xlsx）用 `present` 给用户。
- **每完成一个 WBS 任务，收尾必须同时更新三处状态**（2026-10-31 事故后新增）：① `docs/03` 任务状态表里本任务那一行；② **同一张表上方的里程碑「阶段」行**（阶段内任务全绿时立刻翻 ✅）；③ 里程碑前的「状态说明」行。三处不一致即视为未完成收尾——T8/T9/T10 就是只改了 ①③、漏了 ②，导致阶段 4 在功能全部落地后仍显示“未开始”。
- 未定事项集中在下方“待定”。

## 7 待定（TODO）

### 已定案（留档，勿再讨论）
- [x] 选题：给定方案六（酒店客房预订与入住管理系统）→ 本组题目定名 **云栖酒店客房预订与入住管理系统**，交付件文件名仍用方案名
- [x] 第一次提交件（**v2，2026-10-30 晚按胡宇书文案重做**）：`deliverables/第14组_酒店客房预订与入住管理系统.docx`（A4 三页：一 项目名称含“方案来源：给定方案六”/ 二 项目描述含规则 1–5 / 三 功能清单+截图 / 四 数据库要点）+ `_功能清单.xlsx`（12 行 × 5 列、print_area A1:E12、无页脚行）+ `deliverables/images/feature-list.png`（2299×2815 px，300 dpi 单页）；`tools/verify_submission.py` **39 项断言全 PASS**；组长原稿「（修改版）」副本已删，避免误传
- [x] 项目描述、角色清单、9 项功能与异常清单 → `docs/01-功能清单.md`
- [x] 技术栈：PostgreSQL 18 + Django 6.1 + AdminLTE 3.2（服务端模板渲染，单进程 8000）
- [x] 区间排他约束落地方式：生成列 `during` + `EXCLUDE USING gist`（见 §4.1）
- [x] 排期与分工 → `docs/03-实施计划.md`
- [x] 远端仓库：`https://github.com/EdwardXiao-bit/yunqi-hotel-pms`（main 已推送 README / 文档 / 交付件）
- [x] 仓库清理（2026-10-30）：截图改名 `deliverables/images/feature-list.png`（ASCII，避免非中文环境编码问题），删除早期 Word COM 实验脚本 `tools/convert_doc.ps1`，清掉旧项目名的过期交付件
- [x] 数据库表数口径（2026-10-30 定，**10-30 晚再次改口径**）：**13 张正式表** = 11 张业务表 + `room_block` + `reservation_price`（原「9 必选 + 2 可选」与「11 张」表述均作废）；`docs/01` §1/§7、`docs/02`、`docs/03`、README 全部对齐
- [x] 提交件文案合并（2026-10-30 晚，用户定案 m01258）：①②③⑤ 四条冲突按最优方案合并 —— ① 加 `room_block` 存维修/停用区间；② 加 `reservation_price` 逐日成交价格 + 触发器同步；③ 房态改 4 态（`available/cleaning/maintenance/disabled`），已预订/入住中由订单推导；⑤ 入住率分母扣维修停用房夜；④ 营业收入改为**按退房结算日期（`actual_checkout_at`）归月**（原按 `paid_at` 收款日期）。功能清单 9 行文案、项目描述与核心业务规则 5 条采用胡宇书改写版；排版用本组版式（A4 + 宋体/黑体 + Excel 截图 + 页脚 PAGE）
- [x] 角色与功能编号（2026-10-30 修正）：删掉笔误 F10；客户 F03/F04/F05、前台 F02（房态）/F03（查房）/F05/F06/F07/F08、管理员 F01–F09（超级管理员）
- [x] WBS 人日（2026-10-30 修正）：T1–T17 明细相加 **28.5 人日**（原文“26.5”有误）；折算胡宇书 57% / 肖铭皓 43%，见 `docs/03` §3 人日与占比表
- [x] 方案对比文档归档（2026-10-30）：补第 0 节定案记录（选方案六）并填完 §6 决策清单，§1 原判断标注为留档
- [x] 数据库设计文档与建库脚本（2026-10-30）：`docs/02-数据库设计.md` 已按 13 表 / 房态 4 态重写（ER + 关系、13 表结构、约束清单、索引、触发器/视图/函数、边界用例 B1–B12、数据样例、Django 衔接）；`sql/00`–`04` 的 **13 表版已 psql 实跑通过**（13 表 / 3 条 EXCLUDE / 12 触发器 / 2 视图 / 8 函数；DO 块 9 步自检全过，实测 23P01 与 23514；`overlap_pairs = 0`、`blocked_overlap_pairs = 0`、金额 `mismatch = 0`）；`sql/03_seed.sql` 由 `tools/build_seed_sql.py` 生成（种子 20261030，可复现）
- [x] 约束命名统一（2026-10-30）：排他约束改 `ex_reservation_room_overlap` / `ex_rate_plan_no_overlap`（原 `docs/01` 的 `ex_room_date_overlap` 已对齐）；`docs/01` §8 可用房查询改用生成列 `during`
- [x] 种子数据扩量 + 增值服务两表转正（2026-10-30 晚）：`tools/build_seed_sql.py` 改参数重跑并 psql 实跑通过 → `app_user 27 / customer 30 / room_type 6 / room 40 / rate_plan 10 / reservation 96 / check_in_record 48 / payment 96 / room_status_log 35 / service_item 8 / service_order 57`；**13 表版（v3）另加** `room_block 4` 段封禁、`reservation_price 239`（= 96 单房晚总数，触发器生成）、`room_status_log` 降为 **11**（手工 7 + 4 态流转触发器 4；35 是 v1 改 26 间房态的旧数）；`docs/03` §4.3 目标值**全部达标**（T14 提前完成）；`service_item` / `service_order` 不再称“可选表”，接入 F07 结算（`service_order.amount` 生成列 + 单价快照）
- [x] 查询脚本与实测记录（2026-10-30）：`sql/04_queries.sql`（Q1–Q8）**已在 13 表版上 psql 实跑通过**，结果写进 `docs/05-查询结果与测试记录.md`（Q1 可用房 **35 间**、Q2 张伟 9 条、Q4 按退房月归集后 13 行、Q4-b 月度净收入 12400 / 23568 / 11092 / 376 合计 47436、Q5 高级大床房 20 单 55 房夜、Q6-a 4 间、Q6-b walk_in 17.65%）；原始输出 `work/04_queries_out.txt`
- [x] EXPLAIN 证据（2026-10-30）：`fn_available_rooms(2026-12-20, 12-22)` 执行计划存 `work/explain_available_rooms.txt` 并写入 `docs/03` §5.3 —— **13 表版实测 Function Scan 35 行、`shared hit=233`、Execution 6.264 ms、Planning 0.048 ms**（两个 `NOT EXISTS` 分别走 EXCLUDE 的 gist 索引与 `idx_room_block_room_dates`）；F09 入住率查询的 EXPLAIN 随 T12 补
- [x] 前端排期口径（2026-10-30 定，组内确认）：**不设独立前端阶段**，按功能纵向切片（每个 WBS 任务的产出同时含视图 + 模板 + 表单 + 提示），前端集中在 T4–T5 做骨架；`docs/03` 新增 §4.4「前端实现节奏」并把 WBS 表加「前端产物」列；`docs/页面约定.md` 已提前建立（14 业务页 + 3 错误页的 URL/模板/表单字段/负责人），作为 T4 的前置契约
- [x] T4–T5 工程骨架与登录权限（2026-10-30 深夜，提前落地）：`src/` 下 Django 6.1 工程（`manage.py`、`config/`、`core/`、`templates/`、`static/`）；AdminLTE 3.2 本地资源 23 文件（提交前删 source map：6.41 MiB → **2.7 MB**）无 CDN（`work/adminlte_check.txt` verdict=PASS）；`base.html` + 6 个 `partials/` + 独立登录页 + 客户/前台/管理三端首页 + 3 个错误页；13 个模型 `managed=False`；`tools/smoke_web.py` 离线模式 **35 项断言全 PASS**、`manage.py check` 0 issue；提交 `6732f49` 已推送
- [x] T4–T5 **真库验收**（2026-10-30 23:40）：`sql/91_app_role.sql` 建 `yunqi_app` 最小权限账号（**已执行**，口令由用户用 psql `\password` 自设、我不代持）+ `sql/05_django_tables.sql` 建 `django_session`（已执行）+ `.env` 配 `DB_USER=yunqi_app`；`python tools/smoke_web.py --mode real` **35 项全 PASS**（预检：14 张基表 / 3 条 EXCLUDE / 种子账号 3/3）。三处修复记录：① `sql/91` 原用 `\prompt` + `ALTER ROLE ... PASSWORD :'var'` 在 Windows 控制台下拿到空值 → 改用 psql 元命令 `\password`（连问两次、不回显、由 psql 加密）；② Django session 表不在 `sql/` 序列里 → 新增幂等 `05_django_tables.sql`（**不跑 migrate**，DDL 仍以 sql/ 为唯一事实源）；③ `room_block`/`service_item` 模型多带 `updated_at`（DB 无此列）→ 两模型写 `updated_at = None`，`work/check_models_vs_db.py` 复核字段对齐

### 进行中（按 `docs/03` WBS 推进）
- [~] **T6 起业务流程页**：**F03 可用房查询已完成（2026-10-31，P02 `/rooms/available/`）** —— `src/core/views/rooms.py` 走 `fn_available_rooms` 手写 SQL（sqlite 离线走等价 Python 实现）、`templates/customer/available_rooms.html`（表单 + 按房型汇总 + 房间明细 + 中文校验提示）、路由 `core:available_rooms`、侧边栏入口；真库 12-20~12-22 明细 35 行 = 函数 35 行；`tools/smoke_web.py` 扩到 **57 项**。**F04/F05 已于 10-31 完成（P03/P04/P06）**：`src/core/views/reservations.py`（提交 + 客户列表/详情/取消 + 前台 confirm/cancel/no_show 状态机）、4 模板、5 路由；下单前用 `_query_available` 预检查、写库 `transaction.atomic()`、23P01/23514/23505 映射中文；`work/check_f04_real.py` 真库事务内 15 项核对后回滚（96 → 96 行）。**F06 入住与续住已于 10-31 完成（P07）**：`src/core/views/checkin.py`（按预订入住 + 散客入住 + 续住）、`templates/reception/{checkin_new,checkin_walkin}.html`、2 条路由；入住写 `check_in_record` 与订单状态同一事务、不写房态，续住先查有效订单与 `room_block` 再改离店日；冒烟扩到 sqlite 111 / 真库只读 88，`work/check_f06_real.py` 真库事务内 22 项核对后回滚。**F07 退房结算已于 10-31 完成（P08）**：`src/core/views/checkout.py`（账单 = 房费 + 加收 + 服务费，`settled` 含押金，差额必须为 0 才退房；押金在入住时由 `record_deposit()` 记 `deposit` 流水）、`templates/reception/checkout_detail.html`、路由 `core:checkout_detail`，退房后订单置 `checked_out`、房间转 `cleaning`；冒烟扩到 sqlite 126 / 真库只读 92，`work/check_f07_real.py` 真库事务内 26 项核对后回滚。**F08 房态看板 + F02 房态维护已于 10-31 完成（P09）**：`src/core/views/board.py`（楼层/房型筛选、4 态配色、今日到店/在住/今日退房标记、清洁完成/置为清洁中/登记维修停用区间/结束维修四个动作）+ `templates/reception/room_board.html`、路由 `core:room_board`；维修区间先查有效订单再落 `room_block`（EXCLUDE + `fn_check_room_block_order` 双保险），房态动作在事务内写 `app.current_user_id` 让 `trg_room_status_log` 记录操作人；冒烟扩到 sqlite 141 / 真库只读 100，`work/check_f08_real.py` 真库事务内 22 项核对后回滚。**下一步 T11 F01 房型与价格维护（P10）+ P13 客户与账号一览**；每页按 `docs/页面约定.md` 的 P 编号与字段契约实现，复杂查询走手写 SQL；每完成一页更新 `docs/03` 状态与冒烟断言

### 仍需确认
- [ ] **两人学号**（封面“学生学号”与页脚必填）—— 阻塞报告成稿
- [ ] **报告第 6 章分工占比百分比**（按工作量排序，两人合计 100%）—— 建议值 **胡宇书 57% / 肖铭皓 43%**，已按 WBS 明细折算写入 `docs/03` §3，需组内确认
- [ ] **报告纸张 A4 还是模板“16 开”**（两处要求冲突；现按 A4 准备，交前向教师确认一次，见 `docs/00` §2）
- [ ] 第 15–16 周的**具体日期**（按校历补进 `docs/03` 里程碑后平移排期）
- [ ] 11-12 提交件是否需附**项目描述之外的补充说明**（教师未要求，默认不附）
