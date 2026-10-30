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
import sys
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
