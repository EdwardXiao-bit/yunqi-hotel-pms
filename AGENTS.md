# 数据库系统原理课程设计 · 14 组

> 项目根 `AGENTS.md`：给 AI 助手与组员共用的项目约定。**当前状态（2026-10-30）：选题、功能清单、技术栈、表结构与 SQL 脚本均已定案并实跑通过（阶段 0–1 完成，阶段 1 提前 4 天）；第一次提交件已产出待上传；Django 工程（阶段 3–5）未开始。**
> 最后更新：2026-10-30（阶段 1 收尾 + `docs/03` 里程碑/任务状态回填）

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
│  ├─ 02-数据库设计.md          ER/关系、11 表结构、约束与索引、触发器与视图、数据样例（已建 2026-10-30）
│  ├─ 03-实施计划.md            里程碑/WBS/风险/测试验收（已建）
│  ├─ 04-报告撰写规范.md        6 章大纲与版式参数（待写）
│  ├─ 05-查询结果与测试记录.md   04_queries 的实测结果，报告 4 章素材（已建 2026-10-30）
│  └─ 2026学年…docx / 报告封面文档.doc   教师下发原件，只读
├─ tools/                       docx/doc 解析 + 交付件生成脚本
│  ├─ dump_docx.py / doc_extract.py  读教师原件
│  ├─ build_submission_xlsx.py 生成功能清单 Excel
│  ├─ build_submission_docx.py 生成 Word 汇总（内嵌截图）
│  ├─ build_seed_sql.py        生成 sql/03_seed.sql（60 预订/30 入住/60 支付，含冲突自检）
│  └─ verify_submission.py     两个交付件的结构与版式自检
├─ deliverables/                对外交付件（第一次提交）
│  ├─ 第14组_酒店客房预订与入住管理系统.docx      文件名按给定方案名（内部项目名为云栖…）
│  ├─ 第14组_酒店客房预订与入住管理系统_功能清单.xlsx
│  └─ images/feature-list.png   300 dpi 表格截图，Word 内嵌源
├─ work/                        脚本中间产物（可清理）
├─ sql/                         00_database / 01_schema / 02_constraints / 03_seed / 04_queries 均已实跑
└─ src/                         待建：Django 工程（manage.py、config/、core/、templates/、static/）
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

### 4.2 后端（Django，服务端渲染）

- 工程：`src/` 下 `manage.py` + `config/`（settings/urls/wsgi）+ 业务 app `core/`；单进程 `python manage.py runserver 8000`，**不拆前后端**。
- 渲染：服务端模板 + 表单 POST（`{% csrf_token %}`）；不写 JSON API、不引 DRF。写操作走 POST → `redirect()` + `messages`，杜绝“Ajax 提交 + 前端提示”的双份校验。
- SQL 纪律：复杂查询（可用房、入住率、月度营业额）用 `connection.cursor()` 手写 SQL 或 `QuerySet.raw()`，ORM 只做简单 CRUD —— 报告 4 章要贴**真实执行的 SQL**。
- 异常：业务校验失败抛 `ValidationError`，视图捕获后 `messages.error()` 并回显原页面；数据库 `IntegrityError`（尤其 EXCLUDE 冲突）必须映射成中文提示，E02/E04 靠这一层。
- 鉴权：自定义用户模型 `core.AppUser`（表 `app_user`，`managed = False`）用 `role` 列区分 customer / receptionist / admin，`@login_required` + 自定义 `role_required` 装饰器；不用 `Group` 绕一层，不自己造 JWT。
- 配置：`SECRET_KEY`、DB 口令走环境变量（`.env` 不入库，提供 `.env.example`）。

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
- 未定事项集中在下方“待定”。

## 7 待定（TODO）

### 已定案（留档，勿再讨论）
- [x] 选题：给定方案六（酒店客房预订与入住管理系统）→ 本组题目定名 **云栖酒店客房预订与入住管理系统**，交付件文件名仍用方案名
- [x] 第一次提交件：功能清单 xlsx（9 行 × 5 列，无脚注行）+ 300 dpi 截图 + Word 汇总（A4 两页）→ `deliverables/`，`verify_submission.py` 全绿
- [x] 项目描述、角色清单、9 项功能与异常清单 → `docs/01-功能清单.md`
- [x] 技术栈：PostgreSQL 18 + Django 6.1 + AdminLTE 3.2（服务端模板渲染，单进程 8000）
- [x] 区间排他约束落地方式：生成列 `during` + `EXCLUDE USING gist`（见 §4.1）
- [x] 排期与分工 → `docs/03-实施计划.md`
- [x] 远端仓库：`https://github.com/EdwardXiao-bit/yunqi-hotel-pms`（main 已推送 README / 文档 / 交付件）
- [x] 仓库清理（2026-10-30）：截图改名 `deliverables/images/feature-list.png`（ASCII，避免非中文环境编码问题），删除早期 Word COM 实验脚本 `tools/convert_doc.ps1`，清掉旧项目名的过期交付件
- [x] 数据库表数口径（2026-10-30 统一）：**9 张必选 + 2 张可选**（可选为 `service_item` / `service_order`）；`docs/01` §1 与 §7、`docs/03` §1、README §9 四处已对齐
- [x] 角色与功能编号（2026-10-30 修正）：删掉笔误 F10；客户 F03/F04/F05、前台 F02/F05/F06/F07/F08、管理员 F01–F09（超级管理员）
- [x] WBS 人日（2026-10-30 修正）：T1–T17 明细相加 **28.5 人日**（原文“26.5”有误）；折算胡宇书 57% / 肖铭皓 43%，见 `docs/03` §3 人日与占比表
- [x] 方案对比文档归档（2026-10-30）：补第 0 节定案记录（选方案六）并填完 §6 决策清单，§1 原判断标注为留档
- [x] 数据库设计文档与建库脚本（2026-10-30）：`docs/02-数据库设计.md` 已建（ER/关系、11 表结构、约束清单、索引、触发器/视图/函数、边界用例 B1–B9、数据样例规划、Django 衔接）；`sql/00`、`01_schema.sql`、`02_constraints.sql`、`03_seed.sql` 全部 **psql 实跑通过**（11 表、2 条 EXCLUDE、8 触发器、2 视图、2 函数；DO 块实测 23P01；种子 60 预订/30 入住/60 支付、overlap_pairs = 0）；`sql/03_seed.sql` 由 `tools/build_seed_sql.py` 生成（种子 20261030，可复现）
- [x] 约束命名统一（2026-10-30）：排他约束改 `ex_reservation_room_overlap` / `ex_rate_plan_no_overlap`（原 `docs/01` 的 `ex_room_date_overlap` 已对齐）；`docs/01` §8 可用房查询改用生成列 `during`
- [x] 查询脚本与实测记录（2026-10-30）：`sql/04_queries.sql`（Q1–Q8）**psql 实跑通过**；结果落 `work/04_queries_out.txt`（纯 UTF-8）并整理成 `docs/05-查询结果与测试记录.md`（报告第 4 章素材：Q1 可用房 34 间、Q2 客户 11 条、Q3 30 行入住率、Q4 15 行营收、Q5 房型 Top3、Q6 7 间长期空闲与取消率、Q7 视图余额、Q8 实测 23P01）
- [x] 实施计划按实际进度回填（2026-10-30）：`docs/03` 阶段 0/1 标 ✅（阶段 1 提前 4 天）、WBS T1–T3 标完成、§4.1/4.2/4.3/5.3/§7 与实测对齐（`sql/00–04`、`managed = False`、Q1–Q8）

### 进行中（按 `docs/03` WBS 推进）
- [ ] **种子数据量未达 `docs/03` §4.3 目标**：客户 7（目标 ≥30）、入住 30（≥40）、支付 60（≥80）→ 由 T14 改 `tools/build_seed_sql.py` 参数重跑，差距表见 `docs/03` §4.3
- [ ] **T4–T5 Django 工程骨架与登录/角色权限**（`src/`，模型 `managed = False`）—— 下一阶段入口，未开始

### 仍需确认
- [ ] **两人学号**（封面“学生学号”与页脚必填）—— 阻塞报告成稿
- [ ] **报告第 6 章分工占比百分比**（按工作量排序，两人合计 100%）—— 建议值 **胡宇书 57% / 肖铭皓 43%**，已按 WBS 明细折算写入 `docs/03` §3，需组内确认
- [ ] **报告纸张 A4 还是模板“16 开”**（两处要求冲突；现按 A4 准备，交前向教师确认一次，见 `docs/00` §2）
- [ ] 第 15–16 周的**具体日期**（按校历补进 `docs/03` 里程碑后平移排期）
- [ ] 11-12 提交件是否需附**项目描述之外的补充说明**（教师未要求，默认不附）
