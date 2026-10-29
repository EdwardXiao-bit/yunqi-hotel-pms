# 数据库系统原理课程设计 · 14 组

> 项目根 `AGENTS.md`：给 AI 助手与组员共用的项目约定。**当前状态：选题、功能清单、技术栈均已定案；第一次提交件（xlsx + 截图 + Word）已产出待上传；表结构与页面待阶段 1–4 回填。**
> 最后更新：2026-10-29（第一次提交件产出）

## 1 项目事实（已确认）

- 课程：四川大学《数据库系统原理》课程设计（2026 学年）
- 小组：**第 14 组**，2 人
  - 胡宇书（组长）
  - 肖铭皓
- 指导教师：郭际香（见 `docs/报告封面文档.doc`）
- 技术栈（已定案 2026-10-29，不再改）：**PostgreSQL 18 + Django 6.1 + Bootstrap 4.6（AdminLTE 3.2 模板 + 服务端模板渲染）**
- 运行时（本机实测）：Python 3.12.7（`D:\anaconda3\python.exe`）、Django 6.1.2、psycopg2 2.9.13、PostgreSQL 18（服务 `postgresql-x64-18` 运行中）
- 项目名称（题目）：**云栖酒店客房预订与入住管理系统**（2026-10-29 定名；对应教师给定方案六原题名「酒店房间预订与入住管理系统」）
- 选题（已定案）：给定方案六，决策过程见 `docs/方案对比-六方案评估.md`、`docs/自定选题候选.md`
- 数据库：PostgreSQL 18，库名 `hotel_db`，端口 `5432`，编码 UTF8，时区 Asia/Shanghai
- 角色：客户（customer）、前台工作人员（receptionist）、管理员（admin）

## 2 硬节点

| 事项 | 截止 | 备注 |
| --- | --- | --- |
| 项目名称 + 描述 + 功能清单（Word） | **2026-11-12 23:59** | 提交到 send2me 链接；命名 `第14组_方案名` |
| 系统检查 + PPT 演示 | 第 15–16 周 | 占课程设计总分 60% |
| 课程报告（A4 打印） | 检查系统时交 | 版式见 `docs/00-作业要求与格式要点.md` 第 4 节 |

## 3 目录约定

```
database-course-project/
├─ AGENTS.md                    本项目约定（本文件）
├─ docs/                        交付文档与设计文档
│  ├─ 00-作业要求与格式要点.md   课程要求事实提取（已建）
│  ├─ 方案对比-六方案评估.md     选题决策依据：6 方案打分（已建）
│  ├─ 自定选题候选.md           自拟题目备选 A–E（已建，未采用）
│  ├─ 01-功能清单.md            项目名/描述/角色/9 项功能/异常清单（已建）
│  ├─ 02-数据库设计.md          ER 图、表结构、约束、数据样例（待写）
│  ├─ 03-实施计划.md            里程碑/WBS/风险/测试验收（已建）
│  ├─ 04-报告撰写规范.md        6 章大纲与版式参数（待写）
│  └─ 2026学年…docx / 报告封面文档.doc   教师下发原件，只读
├─ tools/                       docx/doc 解析 + 交付件生成脚本
│  ├─ dump_docx.py / doc_extract.py  读教师原件
│  ├─ build_submission_xlsx.py 生成功能清单 Excel
│  ├─ build_submission_docx.py 生成 Word 汇总（内嵌截图）
│  └─ verify_submission.py     两个交付件的结构与版式自检
├─ deliverables/                对外交付件（第一次提交）
│  ├─ 第14组_云栖酒店客房预订与入住管理系统.docx
│  ├─ 第14组_云栖酒店客房预订与入住管理系统_功能清单.xlsx
│  └─ images/功能清单截图.png   300 dpi 表格截图，Word 内嵌源
├─ work/                        脚本中间产物（可清理）
├─ sql/                         待建：01_schema / 02_constraints / 03_seed / 04_queries
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
  `EXCLUDE USING gist (room_id WITH =, during WITH &&) WHERE (status IN ('pending','confirmed','checked_in'))` 建在生成列上。
  该约束同时写进 `sql/02_constraints.sql` 与 Django migration 的 `migrations.RunSQL`（migration 只跑一次，脚本可重跑，两处必须一致）。

### 4.2 后端（Django，服务端渲染）

- 工程：`src/` 下 `manage.py` + `config/`（settings/urls/wsgi）+ 业务 app `core/`；单进程 `python manage.py runserver 8000`，**不拆前后端**。
- 渲染：服务端模板 + 表单 POST（`{% csrf_token %}`）；不写 JSON API、不引 DRF。写操作走 POST → `redirect()` + `messages`，杜绝「Ajax 提交 + 前端提示」的双份校验。
- SQL 纪律：复杂查询（可用房、入住率、月度营业额）用 `connection.cursor()` 手写 SQL 或 `QuerySet.raw()`，ORM 只做简单 CRUD —— 报告 4 章要贴**真实执行的 SQL**。
- 异常：业务校验失败抛 `ValidationError`，视图捕获后 `messages.error()` 并回显原页面；数据库 `IntegrityError`（尤其 EXCLUDE 冲突）必须映射成中文提示，E02/E04 靠这一层。
- 鉴权：Django 内置 `auth` + `Group`（customer / receptionist / admin），`@login_required` + 自定义 `role_required` 装饰器；不自己造 JWT。
- 配置：`SECRET_KEY`、DB 口令走环境变量（`.env` 不入库，提供 `.env.example`）。

### 4.3 前端（AdminLTE 3.2 + Bootstrap 4.6）

- 版本：AdminLTE **3.2**（[官方文档](https://adminlte.io/docs/3.2/)，仓库 ColorlibHQ/AdminLTE），底层 Bootstrap 4.6 + jQuery 3.5.1 + Popper 1.16.1，图标 FontAwesome 5。
- 落位：`static/vendor/adminlte/{dist,plugins}/` 放官方包；`static/css/site.css` 只放少量覆盖样式；**不用 CDN**（演示机可能断网）。
- 布局：`templates/base.html` + `templates/partials/{head,sidebar,navbar,footer,scripts}.html`，业务页 `{% extends 'base.html' %}` 只填 `{% block content %}`；登录页独立，不套后台布局。
- 个性化裁剪（官方包默认带全部 demo 与插件）：删 `pages/` 下 demo 页；插件按需引用，保留 Bootstrap/jQuery/Popper/FontAwesome/DataTables/DateRangePicker(moment)，统计图表优先 ECharts（不经 jQuery 插件链）；不用 Summernote、CodeMirror、Dropzone、FullCalendar、jsGrid、flot、uPlot、sparkline、jqvmap、pace、filterizr、pdfmake 等。
- 交互：后端 `messages` → Bootstrap alert / toastr 渲染；删除、取消预订等破坏性操作加 SweetAlert2 二次确认。
- 列表页分页：用 Django `Paginator` **服务端分页** + 表单单选/日期筛选，查询在库里跑；**不用 DataTables 前端分页**（会砍掉「多表查询」的展示，报告 4 章没 SQL 可贴）。DataTables 只在纯展示型静态表格上可选项。
- 中文观感：`site.css` 补中文字体栈（`"Microsoft YaHei", "PingFang SC", ...`）与表格/表单字号，避免 Bootstrap 默认英文排版。

## 5 文档与报告约定

- 报告版式以 `docs/00-作业要求与格式要点.md` 第 4 节为准（小四宋体、行距 20 磅、标题小二号黑体、摘要 150 字、参考文献五号宋体）。
- 报告 6 章结构固定，不得增删一级标题。
- 所有 SQL 片段必须**可直接在演示库执行**，报告里的查询结果截图与脚本一致。
- 生成文档只用 `tools/` 下脚本（python-docx / XlsxWriter），不手工改二进制文件；中文文件一律 UTF-8，不经 PowerShell 管道改写。

## 6 协作与纪律（给 AI 助手）

- 每次会话先读本文件与 `docs/00`、`docs/方案对比`，再动手。
- 定案事项立即落盘到 `docs/`，不在对话里留结论。
- 改 SQL 后必须跑 `psql -f` 验证可重复执行，并保留输出。
- 教师下发原件不改；交付物（docx/pptx/xlsx）用 `present` 给用户。
- 未定事项集中在下方「待定」。

## 7 待定（TODO）

### 已定案（留档，勿再讨论）
- [x] 选题：给定方案六（酒店房间预订与入住管理系统）→ 本组题目定名 **云栖酒店客房预订与入住管理系统**
- [x] 第一次提交件：功能清单 xlsx（9 行 × 5 列，无脚注行）+ 300 dpi 截图 + Word 汇总（A4 两页）→ `deliverables/`，`verify_submission.py` 全绿
- [x] 项目描述、角色清单、9 项功能与异常清单 → `docs/01-功能清单.md`
- [x] 技术栈：PostgreSQL 18 + Django 6.1 + AdminLTE 3.2（服务端模板渲染，单进程 8000）
- [x] 区间排他约束落地方式：生成列 `during` + `EXCLUDE USING gist`（见 §4.1）
- [x] 排期与分工 → `docs/03-实施计划.md`

### 仍需确认
- [ ] **两人学号**（封面「学生学号」与页脚必填）—— 阻塞报告成稿
- [ ] **报告第 6 章分工占比百分比**（按工作量排序，两人合计 100%）
- [ ] `git init` 谁做、是否建远端私有仓库（目前尚未初始化）
- [ ] 第 15–16 周的**具体日期**（按校历补进 `docs/03` 里程碑后平移排期）
- [ ] 11-12 提交件是否需附**项目描述之外的补充说明**（教师未要求，默认不附）
