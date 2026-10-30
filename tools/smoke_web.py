"""Web 冒烟测试：三端登录、角色权限、页面渲染、静态资源引用。

两种模式：
    python tools/smoke_web.py                # 离线模式（内存 sqlite，自建 13 表 + 少量假数据）
    python tools/smoke_web.py --mode real    # 真库模式（读仓库根 .env，用 sql/03_seed.sql 的种子账号）

离线模式用于没有库口令时验证代码；真库模式用于验收“页面确实读到了 PostgreSQL 的数据”。
退出码 0 表示全部通过。
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

# 沙箱下往 anaconda 的 site-packages 写 .pyc 会被拒，脚本自身也统一不写字节码
sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
WORK = REPO / "work"

PASSWORD = "Hotel@123"
ACCOUNTS = {  # 角色 -> (登录名, 期望登录后落地页)
    "admin": ("admin", "/manage/"),
    "receptionist": ("front01", "/reception/"),
    "customer": ("zhangwei", "/"),
}

results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}{('  → ' + detail) if detail else ''}")


def _login(username: str, password: str = PASSWORD):
    """返回已登录的测试客户端（登录失败会抛断言，提示先修登录）。"""
    from django.test import Client

    client = Client()
    resp = client.post("/login/", {"username": username, "password": password})
    assert resp.status_code == 302, f"登录失败：{username} → {resp.status_code}"
    return client


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["sqlite", "real"], default="sqlite")
    args = parser.parse_args()

    if args.mode == "sqlite":
        sys.path.insert(0, str(WORK))
        os.environ["DJANGO_SETTINGS_MODULE"] = "check_settings"
    else:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    sys.path.insert(0, str(SRC))
    import django

    django.setup()

    from django.conf import settings
    from django.test import Client

    if "testserver" not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

    # 403 是断言里刻意触发的，不该在日志里刷 traceback
    logging.getLogger("django.request").setLevel(logging.CRITICAL)

    if args.mode == "sqlite":
        _build_sqlite_schema_and_seed()
    elif _preflight_real_db() != 0:
        return 2

    # ---------------------------------------------------------------- 静态资源
    vendor = SRC / "static" / "vendor" / "adminlte"
    for rel in (
        "dist/css/adminlte.min.css",
        "dist/js/adminlte.min.js",
        "plugins/jquery/jquery.min.js",
        "plugins/bootstrap/js/bootstrap.bundle.min.js",
        "plugins/fontawesome-free/css/all.min.css",
        "plugins/fontawesome-free/webfonts/fa-solid-900.woff2",
    ):
        path = vendor / rel
        check(path.is_file(), f"静态资源存在 {rel}", f"{path.stat().st_size if path.is_file() else 0} B")

    # ---------------------------------------------------------------- 登录页
    anonymous = Client()
    resp = anonymous.get("/login/")
    check(resp.status_code == 200, "匿名 GET /login/ 返回 200", str(resp.status_code))
    html = resp.content.decode("utf-8")
    check("云栖" in html and "登录" in html, "登录页含品牌与按钮文案")
    check("/static/vendor/adminlte/dist/css/adminlte.min.css" in html, "登录页引用本地 AdminLTE CSS")

    resp = anonymous.post("/login/", {"username": "admin", "password": "wrong-password"})
    check(
        resp.status_code == 200 and "登录名或密码不正确" in resp.content.decode("utf-8"),
        "错误口令被拒绝并提示中文文案",
        str(resp.status_code),
    )

    resp = anonymous.get("/manage/")
    check(resp.status_code == 302 and "/login/" in resp["Location"], "匿名访问 /manage/ 跳登录页", resp.get("Location", ""))

    # ---------------------------------------------------------------- 三个角色
    for role, (username, landing) in ACCOUNTS.items():
        client = Client()
        resp = client.post("/login/", {"username": username, "password": PASSWORD})
        location = resp.get("Location", "")
        check(
            resp.status_code == 302 and location == landing,
            f"{role} 登录成功并跳 {landing}",
            f"{resp.status_code} {location}",
        )

        if role == "customer":
            home = client.get("/")
            body = home.content.decode("utf-8")
            check(home.status_code == 200, "客户 GET / 返回 200", str(home.status_code))
            check("我的预订" in body, "客户首页渲染“我的预订”区块")
            check("张伟" in body or "预订记录" in body, "客户首页带客户档案/预订信息")
            check(client.get("/reception/").status_code == 403, "客户访问 /reception/ 得 403")
            check(client.get("/manage/").status_code == 403, "客户访问 /manage/ 得 403")

        if role == "receptionist":
            dash = client.get("/reception/")
            body = dash.content.decode("utf-8")
            check(dash.status_code == 200, "前台 GET /reception/ 返回 200", str(dash.status_code))
            check("今日到店" in body and "在住" in body, "前台工作台渲染到店/在住区块")
            check(client.get("/manage/").status_code == 403, "前台访问 /manage/ 得 403")
            check(client.get("/").status_code == 302, "前台访问 / 被引导到前台工作台")

        if role == "admin":
            manage = client.get("/manage/")
            body = manage.content.decode("utf-8")
            check(manage.status_code == 200, "管理员 GET /manage/ 返回 200", str(manage.status_code))
            check("数据概览" in body and "app_user" in body, "管理概览渲染 13 表行数")
            check("PostgreSQL" in body or "数据库" in body, "管理概览显示数据库连接信息")
            check(client.get("/reception/").status_code == 200, "管理员可进前台工作台")
            check(client.get("/").status_code == 200, "管理员可进客户首页")
            check(client.get("/no-such-page/").status_code == 404, "未知 URL 返回 404")

        resp = client.post("/logout/", {"x": "1"})
        check(
            resp.status_code == 302 and "/login/" in resp.get("Location", ""),
            f"{role} 登出后回到登录页",
            resp.get("Location", ""),
        )
        check(client.get("/").status_code == 302, f"{role} 登出后访问 / 被拦截")

    # ---------------------------------------------------------------- P02 可用房查询（F03）
    future_in = (date.today() + timedelta(days=30)).isoformat()
    future_out = (date.today() + timedelta(days=32)).isoformat()

    anonymous = Client()
    resp = anonymous.get("/rooms/available/")
    check(
        resp.status_code == 302 and "/login/" in resp.get("Location", ""),
        "匿名访问 /rooms/available/ 跳登录页",
        resp.get("Location", ""),
    )

    for role, (username, _landing) in ACCOUNTS.items():
        client = Client()
        client.post("/login/", {"username": username, "password": PASSWORD})

        form = client.get("/rooms/available/")
        form_body = form.content.decode("utf-8")
        check(form.status_code == 200, f"{role} 打开可用房查询页 200", str(form.status_code))
        check("可用房查询" in form_body and "查询可用房" in form_body, f"{role} 可用房页渲染查询表单")
        check("可用房查询" in form_body and "fa-door-open" in form_body, f"{role} 侧边栏出现“可用房查询”入口")

        result = client.get(
            "/rooms/available/",
            {"check_in_date": future_in, "check_out_date": future_out, "room_type_id": "", "capacity": ""},
        )
        body = result.content.decode("utf-8")
        check(
            result.status_code == 200 and "按房型汇总" in body and "房间明细" in body,
            f"{role} 可用房查询返回汇总与明细区块",
            str(result.status_code),
        )
        check(
            '<td class="text-monospace">' in body,
            f"{role} 可用房查询至少返回一间房",
            f"{body.count('text-monospace')} 处房号",
        )

        filtered = client.get(
            "/rooms/available/",
            {"check_in_date": future_in, "check_out_date": future_out, "capacity": "3"},
        )
        check(
            filtered.status_code == 200 and "已按“入住人数 ≥ 3”过滤" in filtered.content.decode("utf-8"),
            f"{role} 可用房按入住人数过滤生效",
            str(filtered.status_code),
        )

        invalid = client.get(
            "/rooms/available/", {"check_in_date": future_out, "check_out_date": future_in}
        )
        check(
            invalid.status_code == 200
            and "离店日期必须晚于入住日期" in invalid.content.decode("utf-8"),
            f"{role} 反向日期区间被拒绝并给中文提示",
            str(invalid.status_code),
        )

    # ---------------------------------------------------------------- P03/P04/P06 预订（F04/F05）
    # 读断言两种模式都跑；写断言（下单 / 确认 / 取消）只在离线模式跑，避免污染真库种子数据。
    write_checks = args.mode == "sqlite"

    for url in ("/reservations/new/", "/my/reservations/", "/reception/reservations/"):
        resp = Client().get(url)
        check(
            resp.status_code == 302 and "/login/" in resp.get("Location", ""),
            f"匿名访问 {url} 跳登录页",
            resp.get("Location", ""),
        )

    customer_client = _login("zhangwei")
    reception_client = _login("front01")
    admin_client = _login("admin")

    # 先拿一间在 [future_in, future_out) 可订的房间（与 P02 同一查询）
    avail = customer_client.get(
        "/rooms/available/",
        {"check_in_date": future_in, "check_out_date": future_out, "room_type_id": "", "capacity": ""},
    )
    room_ids = re.findall(r"room_id=(\d+)", avail.content.decode("utf-8"))
    check(bool(room_ids), "可用房页给出可下单的房间链接（P02 → P03）", f"{len(room_ids)} 个 room_id")
    room_id = room_ids[0] if room_ids else ""

    create_page = customer_client.get(
        "/reservations/new/",
        {"room_id": room_id, "check_in_date": future_in, "check_out_date": future_out},
    )
    create_body = create_page.content.decode("utf-8")
    check(create_page.status_code == 200, "客户打开 P03 预订提交页 200", str(create_page.status_code))
    check(
        'name="guest_count"' in create_body
        and 'name="guest_name"' in create_body
        and 'name="guest_phone"' in create_body
        and 'name="remark"' in create_body,
        "P03 渲染入住人数 / 联系人 / 电话 / 备注字段",
    )
    check("提交预订" in create_body and "首晚价" in create_body, "P03 渲染提交按钮与首晚价提示")
    check(
        'name="room_id"' in create_body and f'value="{room_id}"' in create_body,
        "P03 以隐藏域带入所选房间",
    )

    # 未开房态：没有 room_id 时给出中文引导
    no_room = customer_client.get("/reservations/new/")
    check(
        no_room.status_code == 200 and "没有选定房间" in no_room.content.decode("utf-8"),
        "P03 未带房间参数时给出“去查询可用房”引导",
    )

    # 越权：前台访问客户下单页可以（admin/前台也登录），但客户不能进前台预订管理
    check(
        customer_client.get("/reception/reservations/").status_code == 403,
        "客户访问 /reception/reservations/ 得 403",
    )
    check(
        reception_client.get("/reception/reservations/").status_code == 200,
        "前台打开 P06 预订管理页 200",
    )
    check(
        admin_client.get("/reception/reservations/").status_code == 200,
        "管理员可打开 P06 预订管理页",
    )

    list_page = customer_client.get("/my/reservations/")
    list_body = list_page.content.decode("utf-8")
    check(list_page.status_code == 200, "客户打开 P04 我的预订页 200", str(list_page.status_code))
    check("共 " in list_body and "条预订" in list_body, "P04 渲染预订条数与列表")
    check('name="status"' in list_body, "P04 渲染状态筛选下拉框")

    if write_checks:
        booking = customer_client.post(
            "/reservations/new/",
            {
                "room_id": room_id,
                "check_in_date": future_in,
                "check_out_date": future_out,
                "guest_count": "2",
                "guest_name": "张伟",
                "guest_phone": "13800001101",
                "remark": "冒烟测试下单",
            },
        )
        detail_url = booking.get("Location", "")
        check(
            booking.status_code == 302 and detail_url.startswith("/my/reservations/"),
            "P03 提交预订成功并跳订单详情",
            f"{booking.status_code} {detail_url}",
        )

        detail = customer_client.get(detail_url)
        detail_body = detail.content.decode("utf-8")
        check(detail.status_code == 200, "P04 打开订单详情页 200", str(detail.status_code))
        check("预订成功" in detail_body and "待确认" in detail_body, "订单详情显示成功提示与“待确认”状态")
        check("逐日成交价格" in detail_body and "当日晚价" in detail_body, "订单详情渲染逐日成交价格表")
        check("取消预订" in detail_body, "待确认订单详情显示“取消预订”按钮")

        # 同一房间同一区间重复下单 → 被可用房预检查拦下（真库上则由 23P01 兜底）
        duplicate = customer_client.post(
            "/reservations/new/",
            {
                "room_id": room_id,
                "check_in_date": future_in,
                "check_out_date": future_out,
                "guest_count": "2",
                "guest_name": "张伟",
                "guest_phone": "13800001101",
                "remark": "",
            },
        )
        check(
            duplicate.status_code == 200 and "不可预订" in duplicate.content.decode("utf-8"),
            "同房间同区间重复下单被拒绝并给中文提示",
            str(duplicate.status_code),
        )

        # 入住人数超过房型容量 → 中文提示（E01 变体）
        over_capacity = customer_client.post(
            "/reservations/new/",
            {
                "room_id": room_id,
                "check_in_date": future_in,
                "check_out_date": future_out,
                "guest_count": "8",
                "guest_name": "张伟",
                "guest_phone": "13800001101",
                "remark": "",
            },
        )
        check(
            over_capacity.status_code == 200
            and "最多可住" in over_capacity.content.decode("utf-8"),
            "入住人数超过房型容量被拒绝并给中文提示",
        )

        # 手机号格式校验
        bad_phone = customer_client.post(
            "/reservations/new/",
            {
                "room_id": room_id,
                "check_in_date": future_in,
                "check_out_date": future_out,
                "guest_count": "1",
                "guest_name": "张伟",
                "guest_phone": "12345",
                "remark": "",
            },
        )
        check(
            bad_phone.status_code == 200 and "11 位手机号" in bad_phone.content.decode("utf-8"),
            "联系电话格式错误被拒绝并给中文提示",
        )

        # 前台确认 → 取消 → 状态机再校验
        pending_id = detail_url.rstrip("/").split("/")[-1]
        confirmed = reception_client.post(
            "/reception/reservations/",
            {"reservation_id": pending_id, "action": "confirm", "next": "/reception/reservations/"},
        )
        check(confirmed.status_code == 302, "前台确认待确认预订成功（302 回列表）", str(confirmed.status_code))
        manage_body = reception_client.get("/reception/reservations/", {"status": "confirmed"}).content.decode("utf-8")
        check("已确认" in manage_body, "P06 按“已确认”筛选能看到刚确认的订单")

        reconfirm = reception_client.post(
            "/reception/reservations/",
            {"reservation_id": pending_id, "action": "confirm", "next": "/reception/reservations/"},
        )
        follow = reception_client.get(reconfirm["Location"])
        check(
            "只有“待确认”的预订可以确认" in follow.content.decode("utf-8"),
            "状态机拦截重复确认并给中文提示",
        )

        confirmed_detail = customer_client.get(detail_url).content.decode("utf-8")
        check("已确认" in confirmed_detail, "客户详情页反映前台确认后的状态")

        cancelled = reception_client.post(
            "/reception/reservations/",
            {"reservation_id": pending_id, "action": "cancel", "next": "/reception/reservations/"},
        )
        check(cancelled.status_code == 302, "前台取消已确认预订成功（302 回列表）", str(cancelled.status_code))
        cancelled_detail = customer_client.get(detail_url).content.decode("utf-8")
        check("已取消" in cancelled_detail and "取消预订" not in cancelled_detail, "取消后详情显示“已取消”且不再提供取消按钮")

        cancel_again = customer_client.post(f"/my/reservations/{pending_id}/cancel/")
        cancel_follow = customer_client.get("/my/reservations/")
        check(
            cancel_again.status_code == 302 and "已取消" in cancel_follow.content.decode("utf-8"),
            "已取消订单再次取消被拦截",
        )
    else:
        # 真库只读核对：用种子数据里“待确认”的订单验证管理页渲染
        manage_page = reception_client.get("/reception/reservations/", {"status": "pending"})
        manage_body = manage_page.content.decode("utf-8")
        check(manage_page.status_code == 200, "P06 按状态筛选返回 200", str(manage_page.status_code))
        check("待确认" in manage_body and "预订号" in manage_body, "P06 列表渲染预订号与状态")
        check(
            "确认" in manage_body,
            "P06 待确认订单带“确认”操作按钮",
        )
        kw = reception_client.get("/reception/reservations/", {"keyword": "张伟"})
        check(kw.status_code == 200 and "张伟" in kw.content.decode("utf-8"), "P06 关键字筛选命中客户姓名")
        today_in = reception_client.get("/reception/reservations/", {"quick": "today"})
        check(today_in.status_code == 200, "P06 “今日到店”快捷筛选返回 200", str(today_in.status_code))

    # ---------------------------------------------------------------- 汇总
    failed = [r for r in results if not r[0]]
    print("\n" + "=" * 72)
    print(f"结果：{len(results) - len(failed)} 项通过 / {len(failed)} 项失败（模式 {args.mode}）")
    if failed:
        for _, name, detail in failed:
            print(f"  ✗ {name} {detail}")
    print("=" * 72)
    return 1 if failed else 0


def _preflight_real_db() -> int:
    """真库模式预检：把「连不上 / 口令错」翻译成中文提示，避免 psql 本地化消息解码崩溃。"""
    import psycopg2
    from django.conf import settings

    db = settings.DATABASES["default"]
    target = f"{db.get('USER')}@{db.get('HOST')}:{db.get('PORT')}/{db.get('NAME')}"
    print(f"[PREFLIGHT] 尝试连接 {target} …")
    try:
        conn = psycopg2.connect(
            host=db.get("HOST"),
            port=db.get("PORT"),
            dbname=db.get("NAME"),
            user=db.get("USER"),
            password=db.get("PASSWORD"),
            connect_timeout=5,
        )
    except Exception as exc:  # noqa: BLE001 — 口令错会抛 UnicodeDecodeError，必须兜住
        print("[PREFLIGHT] 连不上数据库。")
        if isinstance(exc, UnicodeDecodeError):
            print(
                "  原因：PostgreSQL 返回的是中文（GBK）错误消息，Python 按 UTF-8 解码失败 ——"
                " 实际含义几乎总是「口令认证失败」。\n"
                "  排查：① 角色口令可能没设上 —— 进 psql（-U postgres -d yunqi_hotel）后执行元命令\n"
                "        \\password yunqi_app（连输两次、不回显；注意这是 psql 元命令，不能放进 -c）\n"
                "        ② 确认 .env 的 DB_PASSWORD 与上一步输入完全一致（首尾空格与引号会被 strip）\n"
                "        ③ 确认 .env 的 DB_USER=yunqi_app"
            )
        else:
            print(f"  {type(exc).__name__}: {exc}")
        return 2

    with conn, conn.cursor() as cur:
        cur.execute("SELECT current_user, current_database()")
        who, dbname = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        )
        (tables,) = cur.fetchone()
        cur.execute(
            "SELECT to_regclass('public.django_session') IS NOT NULL, "
            "(SELECT count(*) FROM pg_constraint WHERE conname LIKE 'ex\\_%')"
        )
        has_session, excludes = cur.fetchone()
        cur.execute(
            "SELECT username, role FROM app_user WHERE username IN ('admin','front01','zhangwei') ORDER BY username"
        )
        accounts = cur.fetchall()
    print(
        f"[PREFLIGHT] 连接成功：{who}@{dbname}，public 下 {tables} 张基表 / {excludes} 条 EXCLUDE，"
        f"django_session {'有' if has_session else '缺'}，种子账号 {len(accounts)}/3"
    )
    if tables < 13:
        print("  [PREFLIGHT] 基表不足 13：先跑 sql/01_schema.sql → 02_constraints.sql → 03_seed.sql")
        return 3
    if not has_session:
        print("  [PREFLIGHT] 缺 django_session：先跑 sql/05_django_tables.sql（登录要用会话表，不跑 migrate）")
        return 3
    if len(accounts) != 3:
        print("  [PREFLIGHT] 种子账号缺失：先跑 sql/03_seed.sql")
        return 3
    return 0


def _build_sqlite_schema_and_seed() -> None:
    """离线模式：把 managed=False 的模型临时置为 True，在内存 sqlite 里建表并灌最小数据。"""
    from django.apps import apps
    from django.contrib.auth.hashers import make_password
    from django.db import connection
    from django.utils import timezone

    core_models = list(apps.get_app_config("core").get_models())
    # 会话表是登录流程必需的（离线模式没有迁移，需手工建）
    from django.contrib.sessions.models import Session

    for model in [*core_models, Session]:
        model._meta.managed = True
    with connection.schema_editor() as editor:
        for model in core_models:
            editor.create_model(model)
        editor.create_model(Session)

    from core.models import AppUser, CheckInRecord, Customer, Reservation, Room, RoomBlock, RoomType

    pwd = make_password(PASSWORD)
    admin = AppUser.objects.create(
        username="admin", password=pwd, display_name="酒店管理员", role="admin", phone="13908001000"
    )
    front = AppUser.objects.create(
        username="front01", password=pwd, display_name="前台·刘敏", role="receptionist", phone="13908001001"
    )
    cust_user = AppUser.objects.create(
        username="zhangwei", password=pwd, display_name="张伟", role="customer", phone="13800001101"
    )
    customer = Customer.objects.create(
        user=cust_user, name="张伟", phone="13800001101", id_card="510101199003070011"
    )

    room_type = RoomType.objects.create(
        name="高级大床房", bed_type="king", area="32.0", capacity=2, base_price="488.00", description="演示数据"
    )
    room = Room.objects.create(room_type=room_type, room_no="801", floor=8, orientation="south", status="available")
    room2 = Room.objects.create(room_type=room_type, room_no="802", floor=8, orientation="south", status="cleaning")

    today = timezone.localdate()
    Reservation.objects.create(
        reservation_no="R-DEMO-0001",
        customer=customer,
        room=room,
        check_in_date=today,
        check_out_date=today.replace(day=today.day + 1) if today.day < 28 else today,
        guest_count=2,
        price_per_night="488.00",
        total_amount="976.00",
        status="confirmed",
        source="online",
    )
    Reservation.objects.create(
        reservation_no="R-DEMO-0002",
        customer=customer,
        room=room,
        check_in_date=today.replace(day=1),
        check_out_date=today.replace(day=2),
        guest_count=2,
        price_per_night="488.00",
        total_amount="488.00",
        status="pending",
        source="phone",
    )
    RoomBlock.objects.create(
        room=room2, start_date=today, end_date=today.replace(day=min(28, today.day + 2)),
        block_type="maintenance", reason="演示：空调保养", created_by=admin,
    )
    print(f"[SETUP] sqlite 内存库已建 {len(core_models)} 张表并灌入演示数据（admin/front01/zhangwei，口令 {PASSWORD}）")


if __name__ == "__main__":
    raise SystemExit(main())
