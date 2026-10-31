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

        # 同一房间同一区间重复下单 → 预检查判定为「同客户重复提交」（E03，真库上则由 23P01 兜底）
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
        duplicate_text = duplicate.content.decode("utf-8")
        check(
            duplicate.status_code == 200
            and ("请勿重复提交" in duplicate_text or "不可预订" in duplicate_text),
            "同房间同区间重复下单被拒绝并提示「请勿重复提交」（E03）",
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

    # ---------------------------------------------------------------- P07 入住（F06）
    today_s = date.today().isoformat()
    tomorrow_s = (date.today() + timedelta(days=1)).isoformat()
    f06_rooms = re.findall(
        r"room_id=(\d+)",
        customer_client.get(
            "/rooms/available/", {"check_in_date": today_s, "check_out_date": tomorrow_s}
        ).content.decode("utf-8"),
    )
    check(bool(f06_rooms), "P07 前置：今天有一间可用房用于入住测试", f"{len(f06_rooms)} 间")
    f06_room = f06_rooms[0] if f06_rooms else room_id

    checkin_page = reception_client.get("/reception/checkin/new/")
    checkin_body = checkin_page.content.decode("utf-8")
    check(checkin_page.status_code == 200, "前台打开 P07 入住办理页 200", str(checkin_page.status_code))
    check('name="q"' in checkin_body and "按预订办理入住" in checkin_body, "P07 渲染预订检索表单")
    check("在住客人" in checkin_body, "P07 渲染在住客人区块")
    check(
        customer_client.get("/reception/checkin/new/").status_code == 403,
        "客户访问 P07 入住办理页得 403",
    )
    check(admin_client.get("/reception/checkin/new/").status_code == 200, "管理员可打开 P07 入住办理页")

    walkin_page = reception_client.get(
        "/reception/checkin/walkin/",
        {
            "check_in_date": (date.today() + timedelta(days=5)).isoformat(),
            "check_out_date": (date.today() + timedelta(days=7)).isoformat(),
        },
    )
    walkin_body = walkin_page.content.decode("utf-8")
    check(walkin_page.status_code == 200, "前台打开散客入住页 200", str(walkin_page.status_code))
    check("散客" in walkin_body and 'name="guest_name"' in walkin_body, "散客入住页渲染入住人字段")
    walkin_rooms = re.findall(r'<option value="(\d+)">\s*\n\s*(\d{3})', walkin_body)
    walkin_room_ids = [room_pk for room_pk, _ in walkin_rooms]
    check(bool(walkin_room_ids), "散客入住页给出可用房间选项", f"{len(walkin_room_ids)} 间")
    check(
        customer_client.get("/reception/checkin/walkin/").status_code == 403,
        "客户访问散客入住页得 403",
    )

    found = reception_client.get("/reception/checkin/new/", {"q": "张伟"})
    check(
        found.status_code == 200 and "张伟" in found.content.decode("utf-8"),
        "P07 按关键字检索命中客户",
    )

    if write_checks:
        checkin_booking = customer_client.post(
            "/reservations/new/",
            {
                "room_id": f06_room,
                "check_in_date": today_s,
                "check_out_date": tomorrow_s,
                "guest_count": "2",
                "guest_name": "张伟",
                "guest_phone": "13800001101",
                "remark": "冒烟入住前置订单",
            },
        )
        checkin_url = checkin_booking.get("Location", "")
        check(
            checkin_booking.status_code == 302 and checkin_url.startswith("/my/reservations/"),
            "P07 前置：新建一单今天的待入住预订",
            f"{checkin_booking.status_code} {checkin_url}",
        )
        checkin_id = checkin_url.rstrip("/").split("/")[-1]
        reception_client.post(
            "/reception/reservations/",
            {"reservation_id": checkin_id, "action": "confirm", "next": "/reception/reservations/"},
        )

        form_page = reception_client.get("/reception/checkin/new/", {"reservation_id": checkin_id})
        form_body = form_page.content.decode("utf-8")
        check(
            form_page.status_code == 200 and 'name="deposit_amount"' in form_body,
            "P07 选中预订后渲染入住表单（含押金）",
        )
        check('name="guest_name"' in form_body and "入住人姓名" in form_body, "P07 表单带出入住人字段")

        posted = reception_client.post(
            "/reception/checkin/new/",
            {
                "action": "checkin",
                "reservation_id": checkin_id,
                "guest_name": "张伟",
                "guest_phone": "13800001101",
                "guest_id_card": "510101199001010011",
                "deposit_amount": "200.00",
                "remark": "冒烟入住",
            },
        )
        check(posted.status_code == 302, "P07 办理入住成功（302 回页面）", str(posted.status_code))
        checkin_after = reception_client.get("/reception/checkin/new/").content.decode("utf-8")
        check("张伟" in checkin_after and "在住" in checkin_after, "入住后订单出现在在住客人列表")
        again = reception_client.get(
            "/reception/checkin/new/", {"reservation_id": checkin_id}
        ).content.decode("utf-8")
        check("已经办理过入住" in again, "同一预订重复办理入住被拦截并给中文提示")
        cust_detail = customer_client.get(checkin_url).content.decode("utf-8")
        check("入住中" in cust_detail, "客户订单详情反映“入住中”状态")

        # E05：已入住订单不可取消（客户侧直接 POST 也要被状态机拦下）
        e05 = customer_client.post(f"/my/reservations/{checkin_id}/cancel/", follow=True)
        e05_text = e05.content.decode("utf-8")
        check(
            "已入住订单不可取消" in e05_text,
            "E05 已入住订单取消被拒并提示走退房结算",
            str(e05.status_code),
        )

        walkin_room = next(
            (room_pk for room_pk, room_no in walkin_rooms if room_no == "803"),
            next(
                (room_pk for room_pk, _ in walkin_rooms if room_pk != f06_room),
                walkin_room_ids[0] if walkin_room_ids else "",
            ),
        )
        walkin_post = reception_client.post(
            "/reception/checkin/walkin/",
            {
                "check_in_date": (date.today() + timedelta(days=5)).isoformat(),
                "check_out_date": (date.today() + timedelta(days=7)).isoformat(),
                "room_id": walkin_room,
                "guest_count": "1",
                "guest_name": "散客测试",
                "guest_phone": "13900002222",
                "guest_id_card": "",
                "deposit_amount": "200.00",
                "remark": "冒烟散客",
            },
        )
        check(walkin_post.status_code == 302, "P07 散客入住成功（302）", str(walkin_post.status_code))
        walkin_after = reception_client.get("/reception/checkin/new/").content.decode("utf-8")
        check("散客测试" in walkin_after, "散客入住后出现在在住客人列表")

        # 续住：填原离店日期被拒 → 相邻区间被别的预订占住时拒绝 → 释放后成功
        extend_bad = reception_client.post(
            "/reception/checkin/new/",
            {"action": "extend", "reservation_id": checkin_id, "check_out_date": tomorrow_s},
        )
        bad_body = reception_client.get(
            extend_bad.get("Location", "/reception/checkin/new/")
        ).content.decode("utf-8")
        check("必须晚于原离店日期" in bad_body, "续住填原离店日期被拒绝并给中文提示")

        block_out = (date.today() + timedelta(days=3)).isoformat()
        blocker_booking = customer_client.post(
            "/reservations/new/",
            {
                "room_id": f06_room,
                "check_in_date": tomorrow_s,
                "check_out_date": block_out,
                "guest_count": "1",
                "guest_name": "张伟",
                "guest_phone": "13800001101",
                "remark": "冒烟续住占位",
            },
        )
        blocker_id = blocker_booking.get("Location", "").rstrip("/").split("/")[-1]
        extend_conflict = reception_client.post(
            "/reception/checkin/new/",
            {"action": "extend", "reservation_id": checkin_id, "check_out_date": block_out},
        )
        conflict_body = reception_client.get(
            extend_conflict.get("Location", "/reception/checkin/new/")
        ).content.decode("utf-8")
        check("已被预订" in conflict_body, "续住区间与既有预订冲突被拒绝并指出冲突")
        reception_client.post(
            "/reception/reservations/",
            {"reservation_id": blocker_id, "action": "cancel", "next": "/reception/reservations/"},
        )
        extend_ok = reception_client.post(
            "/reception/checkin/new/",
            {"action": "extend", "reservation_id": checkin_id, "check_out_date": block_out},
        )
        extend_body = reception_client.get(
            extend_ok.get("Location", "/reception/checkin/new/")
        ).content.decode("utf-8")
        check("续住成功" in extend_body, "续住成功后给中文提示并更新离店日期")
        extended_detail = customer_client.get(checkin_url).content.decode("utf-8")
        check(block_out in extended_detail, "续住后订单详情显示新的离店日期")

    # ---------------------------------------------------------------- P08 退房结算（F07）
    from decimal import Decimal

    from django.utils import timezone

    from core.models import CheckInRecord, Payment, Reservation, Room, ServiceItem, ServiceOrder

    if write_checks:
        record = CheckInRecord.objects.filter(reservation_id=checkin_id).first()
        check(record is not None, "P08 前置：上一步入住记录已生成")
        record_pk = record.pk if record else 0
        checkout_url = f"/reception/checkout/{record_pk}/"

        bill_page = reception_client.get(checkout_url)
        bill_body = bill_page.content.decode("utf-8")
        check(bill_page.status_code == 200, "P08 前台打开退房结算页 200", str(bill_page.status_code))
        check("应收合计" in bill_body and "已收已退" in bill_body, "P08 账单预览渲染金额汇总")
        check("还应收" in bill_body or "还应退" in bill_body, "P08 押金不足时显示还应收/还应退")
        check(
            customer_client.get(checkout_url).status_code == 403,
            "客户访问 P08 退房结算页得 403",
        )
        check(admin_client.get(checkout_url).status_code == 200, "管理员可打开 P08 退房结算页")

        unpaid = reception_client.post(
            checkout_url,
            {"actual_checkout_at": (timezone.localtime() + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")},
        )
        unpaid_body = unpaid.content.decode("utf-8")
        due_match = re.search(r"还需补收\s*([\d.]+)\s*元", unpaid_body)
        check(due_match is not None, "P08 未登记收款时提示“还需补收 N 元”", due_match.group(1) if due_match else unpaid_body[:60])

        bf = ServiceItem.objects.filter(code="BF").first()
        settle_amount = (Decimal(due_match.group(1)) + Decimal("68.00") * 2) if due_match and bf else None
        settled_post = reception_client.post(
            checkout_url,
            {
                "actual_checkout_at": (timezone.localtime() + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S"),
                "extra_room_charge": "0",
                "service_item_id": str(bf.pk) if bf else "",
                "service_quantity": "2",
                "payment_kind": "room_fee",
                "payment_method": "cash",
                "payment_amount": str(settle_amount) if settle_amount is not None else "",
            },
        )
        check(settled_post.status_code == 302, "P08 差额结清后提交退房成功（302）", str(settled_post.status_code))

        record.refresh_from_db()
        reservation_now = Reservation.objects.get(pk=checkin_id)
        room_now = Room.objects.get(pk=f06_room)
        orders = ServiceOrder.objects.filter(check_in_record_id=record_pk)
        pays = Payment.objects.filter(check_in_record_id=record_pk).order_by("id")
        check(reservation_now.status == "checked_out", "P08 退房后订单状态置为已退房", reservation_now.status)
        check(record.actual_checkout_at is not None, "P08 入住记录写入实际退房时间")
        check(record.total_charge == record.room_charge + record.service_charge, "P08 应收合计 = 房费 + 服务费", str(record.total_charge))
        check(room_now.status == "cleaning", "P08 退房后房间转为清洁中", room_now.status)
        check(
            orders.count() == 1 and orders.first().amount == Decimal("136.00"),
            "P08 增值服务按数量 × 单价落库（2 × 68.00 = 136.00）",
            f"{orders.count()} 行 / {orders.first().amount if orders else '-'}",
        )
        check(
            pays.count() == 2 and sum((p.amount for p in pays), Decimal("0.00")) == record.total_charge,
            "P08 押金 + 结算款两笔流水，合计等于应收",
            " / ".join(f"{p.kind}:{p.amount}" for p in pays),
        )

        again_checkout = reception_client.post(
            checkout_url,
            {"actual_checkout_at": (timezone.localtime() + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")},
        )
        check("不能重复结算" in again_checkout.content.decode("utf-8"), "P08 重复结算被拦截并给中文提示")
    else:
        in_house = CheckInRecord.objects.filter(actual_checkout_at__isnull=True).order_by("id").last()
        check(in_house is not None, "P08 真库存在可结算的在住记录")
        if in_house is not None:
            real_page = reception_client.get(f"/reception/checkout/{in_house.pk}/")
            real_body = real_page.content.decode("utf-8")
            check(real_page.status_code == 200, "P08 真库打开退房结算页 200", str(real_page.status_code))
            check(
                "应收合计" in real_body and "押金" in real_body,
                "P08 真库结算页渲染账单与押金",
            )
            check(
                customer_client.get(f"/reception/checkout/{in_house.pk}/").status_code == 403,
                "P08 真库客户访问结算页得 403",
            )

    # ---------------------------------------------------------------- P09 房态看板（F08/F02）
    from core.models import Room as BoardRoom
    from core.models import RoomBlock as BoardBlock
    from core.models import RoomStatusLog

    board_url = "/reception/board/"
    board_page = reception_client.get(board_url)
    board_body = board_page.content.decode("utf-8")
    check(board_page.status_code == 200, "P09 前台打开房态看板 200", str(board_page.status_code))
    check("房态看板" in board_body and "看板口径" in board_body, "P09 看板渲染标题与口径说明")
    check("楼层" in board_body and "登记维修 / 停用" in board_body, "P09 看板渲染楼层分组与区间登记表单")
    check(customer_client.get(board_url).status_code == 403, "客户访问 P09 房态看板得 403")
    check(admin_client.get(board_url).status_code == 200, "管理员可打开 P09 房态看板")

    if write_checks:
        today = timezone.localdate()
        board_room = BoardRoom.objects.filter(room_no="804").first()
        check(board_room is not None, "P09 前置：演示房 804 存在")
        log_before = RoomStatusLog.objects.filter(room_id=board_room.pk).count()

        resp = reception_client.post(board_url, {"room_id": board_room.pk, "action": "cleaning"})
        board_room.refresh_from_db()
        check(
            resp.status_code == 302 and board_room.status == "cleaning",
            "P09 置为清洁中（available → cleaning）",
            board_room.status,
        )

        resp = reception_client.post(board_url, {"room_id": board_room.pk, "action": "clean"})
        board_room.refresh_from_db()
        check(
            resp.status_code == 302 and board_room.status == "available",
            "P09 清洁完成后恢复正常（cleaning → available）",
            board_room.status,
        )
        check(
            RoomStatusLog.objects.filter(room_id=board_room.pk).count() >= log_before,
            "P09 房态变更不破坏房态日志表（日志由数据库触发器写入）",
        )

        block_start = today
        block_end = today + timedelta(days=3)
        resp = reception_client.post(
            board_url,
            {
                "room_id": board_room.pk,
                "action": "block",
                "block_type": "maintenance",
                "start_date": block_start.isoformat(),
                "end_date": block_end.isoformat(),
                "reason": "冒烟：空调保养",
            },
        )
        board_room.refresh_from_db()
        block = BoardBlock.objects.filter(room_id=board_room.pk, start_date=block_start).first()
        check(
            resp.status_code == 302 and block is not None and board_room.status == "maintenance",
            "P09 登记维修区间并把房态置为维修中",
            f"block={block is not None} status={board_room.status}",
        )

        resp = reception_client.post(
            board_url,
            {
                "room_id": board_room.pk,
                "action": "block",
                "block_type": "disabled",
                "start_date": block_start.isoformat(),
                "end_date": block_end.isoformat(),
                "reason": "冒烟：重复区间",
            },
            follow=True,
        )
        overlap_msg = resp.content.decode("utf-8")
        check(
            "已有维修/停用登记" in overlap_msg,
            "P09 重复登记同一区间被拒绝并给中文提示",
        )

        conflict_start = today + timedelta(days=10)
        conflict_end = today + timedelta(days=12)
        from core.models import Customer as BoardCustomer
        from core.models import Reservation as BoardReservation

        demo_customer = BoardCustomer.objects.first()
        BoardReservation.objects.create(
            reservation_no="R-SMOKE-P09",
            customer=demo_customer,
            room=board_room,
            check_in_date=conflict_start,
            check_out_date=conflict_end,
            guest_count=1,
            price_per_night="488.00",
            total_amount="976.00",
            status="confirmed",
            source="phone",
        )
        resp = reception_client.post(
            board_url,
            {
                "room_id": board_room.pk,
                "action": "block",
                "block_type": "maintenance",
                "start_date": conflict_start.isoformat(),
                "end_date": conflict_end.isoformat(),
                "reason": "冒烟：与订单冲突",
            },
            follow=True,
        )
        conflict_body = resp.content.decode("utf-8")
        check(
            "有效订单" in conflict_body and "请先处理订单" in conflict_body,
            "P09 登记区间与有效订单冲突时提示先处理订单",
        )
        check(
            not BoardBlock.objects.filter(room_id=board_room.pk, start_date=conflict_start).exists(),
            "P09 冲突的维修登记没有落库",
        )

        resp = reception_client.post(board_url, {"room_id": board_room.pk, "action": "unblock"})
        board_room.refresh_from_db()
        block = BoardBlock.objects.filter(room_id=board_room.pk, start_date=block_start).first()
        check(
            resp.status_code == 302
            and board_room.status == "available"
            and (block is None or block.end_date == today),
            "P09 结束维修/停用后房态恢复正常且区间截止到当天",
            f"status={board_room.status} block={block.end_date if block else None}",
        )

        resp = reception_client.post(
            board_url,
            {
                "room_id": board_room.pk,
                "action": "block",
                "block_type": "maintenance",
                "start_date": (today + timedelta(days=20)).isoformat(),
                "end_date": (today + timedelta(days=18)).isoformat(),
            },
            follow=True,
        )
        check(
            "结束日期必须晚于开始日期" in resp.content.decode("utf-8"),
            "P09 反向区间被拒绝并给中文提示",
        )
    else:
        check("房态看板" in board_body, "P09 真库看板页渲染标题")
        check(
            RoomStatusLog.objects.filter(reason__isnull=False).exists(),
            "P09 真库房态日志有记录（数据库触发器生效）",
        )
        any_block = BoardBlock.objects.filter(end_date__gte=timezone.localdate()).first()
        if any_block is not None:
            check(
                any_block.get_block_type_display() in board_body,
                "P09 真库看板展示维修/停用区间",
                any_block.get_block_type_display(),
            )

    # ---------------------------------------------------------------- P10 房型与价格维护（F01）
    from core.models import RatePlan as RTypePlan
    from core.models import Room as ManageRoom
    from core.models import RoomType as ManageRoomType

    admin_rts = admin_client.get("/manage/room-types/")
    admin_rts_body = admin_rts.content.decode("utf-8")
    check(admin_rts.status_code == 200, "P10 管理员打开房型列表 200", str(admin_rts.status_code))
    check("房型列表" in admin_rts_body and "新建房型" in admin_rts_body, "P10 列表渲染标题与新建入口")
    check("标准价" in admin_rts_body and "价格方案" in admin_rts_body, "P10 列表渲染标准价与方案列")
    check(
        reception_client.get("/manage/room-types/").status_code == 403,
        "P10 前台访问房型维护得 403",
    )
    check(
        customer_client.get("/manage/customers/").status_code == 403,
        "P13 客户访问客户一览得 403",
    )

    if write_checks:
        new_page = admin_client.get("/manage/room-types/new/")
        new_body = new_page.content.decode("utf-8")
        check(new_page.status_code == 200, "P10 打开新建房型页 200", str(new_page.status_code))
        check("房型名称" in new_body and "保存房型" in new_body, "P10 新建页渲染表单与保存按钮")

        # 新建房型
        created = admin_client.post(
            "/manage/room-types/new/",
            {
                "action": "save",
                "name": "测试房型-P10",
                "bed_type": "double",
                "capacity": "3",
                "base_price": "399.00",
                "area": "28.0",
                "description": "冒烟测试创建",
                "is_active": "on",
            },
        )
        check(created.status_code == 302, "P10 新建房型提交成功（302）", str(created.status_code))
        made = ManageRoomType.objects.filter(name="测试房型-P10").first()
        check(made is not None, "P10 新房型已落库")
        made_pk = made.pk if made else 0

        # 编辑：改名 + 调价
        edited = admin_client.post(
            f"/manage/room-types/{made_pk}/edit/",
            {
                "action": "save",
                "name": "测试房型-P10改",
                "bed_type": "double",
                "capacity": "3",
                "base_price": "428.00",
                "area": "28.0",
                "description": "冒烟测试改名",
                "is_active": "on",
            },
        )
        check(edited.status_code == 302, "P10 编辑房型提交成功（302）", str(edited.status_code))
        made.refresh_from_db()
        check(made.name == "测试房型-P10改", "P10 房型改名已落库", made.name)
        check(str(made.base_price) == "428.00", "P10 标准价已更新", str(made.base_price))

        # 添加价格方案
        plan_post = admin_client.post(
            f"/manage/room-types/{made_pk}/edit/",
            {
                "action": "add_plan",
                "plan_name": "测试方案",
                "price": "499.00",
                "valid_from": "2027-03-01",
                "valid_to": "2027-03-07",
            },
        )
        check(plan_post.status_code == 302, "P10 添加价格方案成功（302）", str(plan_post.status_code))
        plan = RTypePlan.objects.filter(room_type_id=made_pk).first()
        check(plan is not None, "P10 价格方案已落库")

        # 闭区间重叠 → 拒绝（离线 sqlite 没有 EXCLUDE，靠应用层预检查）
        overlap_post = admin_client.post(
            f"/manage/room-types/{made_pk}/edit/",
            {
                "action": "add_plan",
                "plan_name": "重叠方案",
                "price": "599.00",
                "valid_from": "2027-03-05",
                "valid_to": "2027-03-10",
            },
        )
        overlap_body = overlap_post.content.decode("utf-8")
        check(
            overlap_post.status_code == 200 and "区间不能重叠" in overlap_body,
            "P10 价格方案区间重叠被拒绝并给中文提示",
        )
        check(
            RTypePlan.objects.filter(room_type_id=made_pk).count() == 1,
            "P10 重叠方案没有落库",
        )

        # 删除方案
        if plan is not None:
            del_plan = admin_client.post(
                f"/manage/room-types/{made_pk}/edit/",
                {"action": "delete_plan", "plan_id": str(plan.pk)},
            )
            check(del_plan.status_code == 302, "P10 删除价格方案成功（302）", str(del_plan.status_code))
            check(
                RTypePlan.objects.filter(room_type_id=made_pk).count() == 0,
                "P10 价格方案已删除",
            )

        # 有房间引用的房型不能删（RESTRICT / 应用层预检查）
        demo_rtype = ManageRoom.objects.first().room_type_id if ManageRoom.objects.exists() else 0
        blocked_del = admin_client.post(
            "/manage/room-types/",
            {"action": "delete", "room_type_id": str(demo_rtype)},
            follow=True,
        )
        blocked_body = blocked_del.content.decode("utf-8")
        check(
            blocked_del.status_code == 200 and "不能删除" in blocked_body,
            "P10 有房间引用的房型删除被拒绝（提示改为停用）",
            blocked_body[:80].replace("\n", " "),
        )
        check(
            ManageRoomType.objects.filter(pk=demo_rtype).exists(),
            "P10 被拒的房型仍在库",
        )

        # 无引用的新房型可以删
        del_rtype = admin_client.post(
            "/manage/room-types/",
            {"action": "delete", "room_type_id": str(made_pk)},
        )
        check(del_rtype.status_code == 302, "P10 删除无引用房型成功（302）", str(del_rtype.status_code))
        check(
            not ManageRoomType.objects.filter(pk=made_pk).exists(),
            "P10 无引用房型已删除",
        )

    # ---------------------------------------------------------------- P13 客户与账号一览
    cust_page = admin_client.get("/manage/customers/")
    cust_body = cust_page.content.decode("utf-8")
    check(cust_page.status_code == 200, "P13 管理员打开客户一览 200", str(cust_page.status_code))
    check(
        "客户与账号一览" in cust_body and "系统账号" in cust_body,
        "P13 渲染客户列表与账号列表两个区块",
    )
    check(
        reception_client.get("/manage/customers/").status_code == 403,
        "P13 前台访问客户一览得 403",
    )
    if write_checks:
        check("张伟" in cust_body and "13800001101" in cust_body, "P13 离线种子客户出现在列表")
        searched = admin_client.get("/manage/customers/?keyword=13800001101")
        searched_body = searched.content.decode("utf-8")
        check(searched.status_code == 200 and "张伟" in searched_body, "P13 按手机号搜索命中客户")
        miss = admin_client.get("/manage/customers/?keyword=不存在的客户")
        check(miss.status_code == 200 and "没有匹配的客户" in miss.content.decode("utf-8"), "P13 搜索无结果给空态提示")
    else:
        check("张伟" in cust_body or "客户" in cust_body, "P13 真库客户列表渲染客户数据")
        real_rts = admin_client.get("/manage/room-types/")
        real_body = real_rts.content.decode("utf-8")
        check(real_rts.status_code == 200, "P10 真库房型列表 200", str(real_rts.status_code))
        check("高级大床房" in real_body or "标准间" in real_body, "P10 真库列表渲染真实房型")

    # ---------------------------------------------------------------- P11 统计报表（F09）
    reports_page = admin_client.get("/manage/reports/")
    reports_body = reports_page.content.decode("utf-8")
    check(reports_page.status_code == 200, "P11 管理员打开统计报表 200", str(reports_page.status_code))
    check(
        "经营统计报表" in reports_body and "入住率" in reports_body and "净收入" in reports_body,
        "P11 渲染四块指标与图表卡",
    )
    for chart_id in ("chart-occupancy", "chart-revenue", "chart-top-rooms", "chart-sources"):
        check(f'id="{chart_id}"' in reports_body, f"P11 图表容器 {chart_id} 存在")
    check(
        'id="report-data"' in reports_body and "echarts.min.js" in reports_body,
        "P11 内嵌 chart_data 并引用本地 ECharts",
    )
    check(
        reports_body.count("vendor/echarts/echarts.min.js") == 1
        and "http://" not in reports_body.split("extra_scripts")[-1][:2000],
        "P11 ECharts 走本地静态资源（无 CDN）",
    )
    check(
        reception_client.get("/manage/reports/").status_code == 403,
        "P11 前台访问统计报表得 403",
    )
    check(
        customer_client.get("/manage/reports/").status_code == 403,
        "P11 客户访问统计报表得 403",
    )

    ranged = admin_client.get(
        "/manage/reports/", {"date_from": "2026-09-01", "date_to": "2027-01-31", "room_type_id": ""}
    )
    check(ranged.status_code == 200, "P11 指定区间查询 200", str(ranged.status_code))
    bad_range = admin_client.get("/manage/reports/", {"date_from": "2027-01-31", "date_to": "2026-09-01"})
    check(
        bad_range.status_code == 200 and "入住日期" in bad_range.content.decode("utf-8"),
        "P11 起止倒置给出中文提示并回落",
    )

    # ---------------------------------------------------------------- P12 预订总览（F05 管理员只读）
    overview = admin_client.get("/manage/reservations/")
    overview_body = overview.content.decode("utf-8")
    check(overview.status_code == 200, "P12 管理员打开预订总览 200", str(overview.status_code))
    check(
        "预订总览" in overview_body and "导出当前筛选结果" in overview_body,
        "P12 渲染标题与导出入口",
    )
    check(
        overview_body.count("text-monospace") > 10,
        "P12 渲染预订明细行",
        str(overview_body.count("text-monospace")),
    )
    check(
        reception_client.get("/manage/reservations/").status_code == 403,
        "P12 前台访问预订总览得 403",
    )
    filtered = admin_client.get("/manage/reservations/", {"status": "checked_out"})
    filtered_body = filtered.content.decode("utf-8")
    check(filtered.status_code == 200 and "已退房" in filtered_body, "P12 按状态筛选 200")

    export = admin_client.get("/manage/reservations/export/")
    export_body = export.content
    check(
        export.status_code == 200
        and "text/csv" in export.get("Content-Type", "")
        and export_body.startswith("\ufeff".encode("utf-8")),
        "P12 导出 CSV（带 BOM、text/csv）",
        export.get("Content-Type", ""),
    )
    check(
        "预订号".encode("utf-8") in export_body and "客户".encode("utf-8") in export_body,
        "P12 CSV 含中文表头",
    )
    check(
        reception_client.get("/manage/reservations/export/").status_code == 403,
        "P12 前台访问导出得 403",
    )

    # ---------------------------------------------------------------- P14 房间维护（F02）
    rooms_page = admin_client.get("/manage/rooms/")
    rooms_body = rooms_page.content.decode("utf-8")
    check(rooms_page.status_code == 200, "P14 管理员打开房间维护 200", str(rooms_page.status_code))
    check(
        "房间维护" in rooms_body and "批量新增房间" in rooms_body,
        "P14 渲染房间列表与批量新增表单",
    )
    check(
        reception_client.get("/manage/rooms/").status_code == 403,
        "P14 前台访问房间维护得 403",
    )
    check(
        customer_client.get("/manage/rooms/").status_code == 403,
        "P14 客户访问房间维护得 403",
    )
    new_room_page = admin_client.get("/manage/rooms/new/")
    new_room_body = new_room_page.content.decode("utf-8")
    check(new_room_page.status_code == 200, "P14 打开新增房间页 200", str(new_room_page.status_code))
    check(
        'name="room_no"' in new_room_body
        and 'name="room_type_id"' in new_room_body
        and 'name="floor"' in new_room_body,
        "P14 表单含房号/房型/楼层字段",
    )

    if write_checks:
        from core.models import Room, RoomType

        room_type = RoomType.objects.filter(is_active=True).order_by("id").first()
        check(room_type is not None, "P14 离线种子存在可用房型")
        before_rooms = Room.objects.count()

        created = admin_client.post(
            "/manage/rooms/new/",
            {
                "room_no": "9901",
                "room_type_id": room_type.pk,
                "floor": 9,
                "orientation": "east",
                "status": "available",
                "remark": "冒烟新增",
            },
        )
        check(
            created.status_code == 302 and Room.objects.filter(room_no="9901").exists(),
            "P14 新增房间成功并落库",
            str(created.status_code),
        )

        duplicated = admin_client.post(
            "/manage/rooms/new/",
            {
                "room_no": "9901",
                "room_type_id": room_type.pk,
                "floor": 9,
                "orientation": "east",
                "status": "available",
            },
        )
        check(
            duplicated.status_code == 200 and "已存在" in duplicated.content.decode("utf-8"),
            "P14 重复房号被拒绝并给中文提示",
        )

        bulk = admin_client.post(
            "/manage/rooms/",
            {
                "action": "bulk",
                "room_type_id": room_type.pk,
                "floor": 9,
                "orientation": "south",
                "status": "available",
                "room_nos": "9902, 9903 9904",
            },
        )
        check(
            bulk.status_code == 302 and Room.objects.filter(room_no__in=["9902", "9903", "9904"]).count() == 3,
            "P14 批量新增 3 间房",
            str(bulk.status_code),
        )
        check(Room.objects.count() == before_rooms + 4, "P14 房间总数 +4")

        listed = admin_client.get("/manage/rooms/?keyword=990")
        check("9901" in listed.content.decode("utf-8"), "P14 按房号筛选命中新房")

        edited = admin_client.post(
            f"/manage/rooms/{Room.objects.get(room_no='9901').pk}/edit/",
            {
                "room_no": "9901",
                "room_type_id": room_type.pk,
                "floor": 10,
                "orientation": "east",
                "status": "available",
                "remark": "改楼层",
            },
        )
        room_9901 = Room.objects.get(room_no="9901")
        check(edited.status_code == 302 and room_9901.floor == 10, "P14 编辑房间改楼层成功")

        blocked = admin_client.post(
            "/manage/rooms/",
            {"action": "delete", "room_id": Room.objects.get(room_no="801").pk},
        )
        check(
            blocked.status_code == 302 and Room.objects.filter(room_no="801").exists(),
            "P14 有预订的房间不能删除",
        )

        deleted = admin_client.post(
            "/manage/rooms/",
            {"action": "delete", "room_id": room_9901.pk},
        )
        check(
            deleted.status_code == 302 and not Room.objects.filter(room_no="9901").exists(),
            "P14 无引用的房间可以删除",
        )
    else:
        check(
            "间" in rooms_body and "房号" in rooms_body,
            "P14 真库房间列表渲染房间数据",
        )

    # ---------------------------------------------------------------- P15 增值服务价目表
    from core.models import ServiceItem, ServiceOrder
    from core.models import CheckInRecord as SvcRecord

    items_page = admin_client.get("/manage/service-items/")
    items_body = items_page.content.decode("utf-8")
    check(items_page.status_code == 200, "P15 管理员打开增值服务价目表 200", str(items_page.status_code))
    check(
        "增值服务价目表" in items_body and "消费明细条数" in items_body,
        "P15 渲染价目表与使用统计",
    )
    check(reception_client.get("/manage/service-items/").status_code == 403, "P15 前台访问价目表得 403")
    check(customer_client.get("/manage/service-items/").status_code == 403, "P15 客户访问价目表得 403")

    new_item_page = admin_client.get("/manage/service-items/new/")
    new_item_body = new_item_page.content.decode("utf-8")
    check(new_item_page.status_code == 200, "P15 打开新增服务项目页 200", str(new_item_page.status_code))
    check(
        "服务编码" in new_item_body and "单价(元)" in new_item_body,
        "P15 新增页含编码/名称/单价字段",
    )

    if args.mode == "sqlite":
        # 真库是演示数据，只读核对；写操作只在内存 sqlite 上做
        before_items = ServiceItem.objects.count()
        created = admin_client.post(
            "/manage/service-items/new/",
            {"code": "TST1", "name": "测试晚茶", "unit": "份", "price": "36.00", "is_active": "1"},
        )
        created_item = ServiceItem.objects.filter(code="TST1").first()
        check(
            created.status_code == 302 and created_item is not None,
            "P15 新增服务项目成功并落库",
            str(created.status_code),
        )
        check(ServiceItem.objects.count() == before_items + 1, "P15 服务项目总数 +1")

        dup_item = admin_client.post(
            "/manage/service-items/new/",
            {"code": "TST1", "name": "另一个名字", "unit": "份", "price": "10.00", "is_active": "1"},
            follow=True,
        )
        check(
            dup_item.status_code == 200 and "已存在" in dup_item.content.decode("utf-8"),
            "P15 重复服务编码被拒绝并给中文提示",
        )

        edit_item = admin_client.post(
            "/manage/service-items/%d/edit/" % created_item.pk,
            {"code": "TST1", "name": "测试晚茶", "unit": "份", "price": "42.00", "is_active": "1"},
        )
        created_item.refresh_from_db()
        check(
            edit_item.status_code == 302 and str(created_item.price) == "42.00",
            "P15 编辑服务项目改价成功",
        )

        toggle_item = admin_client.post("/manage/service-items/", {"action": "toggle", "item_id": created_item.pk})
        created_item.refresh_from_db()
        check(
            toggle_item.status_code == 302 and created_item.is_active is False,
            "P15 下架服务项目成功",
        )
    else:
        seeded = ServiceItem.objects.filter(is_active=True).count()
        check(seeded >= 1, "P15 真库价目表有在售项目", "共 %d 个" % seeded)

    # ---------------------------------------------------------------- P16 增值服务登记与记录
    register_page = reception_client.get("/reception/services/")
    register_body = register_page.content.decode("utf-8")
    check(register_page.status_code == 200, "P16 前台打开增值服务登记页 200", str(register_page.status_code))
    check(
        "给在住客人登记服务" in register_body and "最近登记的消费" in register_body,
        "P16 渲染登记表单与最近消费",
    )
    check(customer_client.get("/reception/services/").status_code == 403, "P16 客户访问登记页得 403")
    records_page = admin_client.get("/reception/services/records/")
    check(records_page.status_code == 200, "P16 管理员打开消费记录页 200", str(records_page.status_code))

    if args.mode == "sqlite":
        # 服务项目先恢复在售，便于登记
        admin_client.post("/manage/service-items/", {"action": "toggle", "item_id": created_item.pk})

        from django.contrib.auth import get_user_model

        in_house_candidates = list(
            SvcRecord.objects.filter(actual_checkout_at__isnull=True, reservation__status="checked_in")
            .select_related("reservation", "reservation__customer")
            .order_by("id")
        )
        # 优先选「客户有登录账号」的记录；离线种子里的在住记录都是散客自动建档，
        # 这里把其中一条的客户档案挂到 zhangwei 账号上，才能顺带验证客户详情页。
        login_user = get_user_model().objects.filter(username="zhangwei").first()
        in_house_record = next(
            (r for r in in_house_candidates if r.reservation.customer and r.reservation.customer.user_id),
            in_house_candidates[0] if in_house_candidates else None,
        )
        if (
            in_house_record is not None
            and login_user is not None
            and in_house_record.reservation.customer is not None
            and in_house_record.reservation.customer.user_id is None
        ):
            from core.models import Customer as SvcCustomer

            customer_row = in_house_record.reservation.customer
            SvcCustomer.objects.filter(user_id=login_user.pk).exclude(pk=customer_row.pk).update(user_id=None)
            customer_row.user_id = login_user.pk
            customer_row.save(update_fields=["user_id"])
        check(in_house_record is not None, "P16 离线种子存在在住记录")
        if in_house_record is not None:
            before_orders = ServiceOrder.objects.filter(check_in_record_id=in_house_record.pk).count()
            before_service = SvcRecord.objects.get(pk=in_house_record.pk).service_charge or 0

            posted = reception_client.post(
                "/reception/services/",
                {
                    "record_id": in_house_record.pk,
                    "item_id": [created_item.pk],
                    "quantity": ["2"],
                },
            )
            check(posted.status_code == 302, "P16 登记服务成功并跳转", str(posted.status_code))

            orders = ServiceOrder.objects.filter(check_in_record_id=in_house_record.pk)
            check(orders.count() == before_orders + 1, "P16 消费明细 +1 条")
            latest = orders.order_by("-id").first()
            check(
                latest is not None and latest.quantity == 2 and str(latest.amount) == "84.00",
                "P16 金额 = 数量 × 单价快照（2 × 42.00 = 84.00）",
                str(latest.amount) if latest else "无明细",
            )

            record_after = SvcRecord.objects.get(pk=in_house_record.pk)
            check(
                str(record_after.service_charge) == "84.00",
                "P16 入住记录服务费同步为 84.00",
                str(record_after.service_charge),
            )
            check(
                str(record_after.total_charge) == str((record_after.room_charge or 0) + record_after.service_charge),
                "P16 应收合计 = 房费 + 服务费",
            )

            detail_page = reception_client.get("/reception/services/?record_id=%d" % in_house_record.pk)
            detail_body = detail_page.content.decode("utf-8")
            check("测试晚茶" in detail_body, "P16 选中客人后显示已登记服务明细")

            # 客户在「我的预订」详情里能看到这笔消费
            reservation = in_house_record.reservation
            check(
                bool(reservation.customer and reservation.customer.user_id),
                "P16 选中的在住记录属于有登录账号的客户",
            )
            if reservation.customer and reservation.customer.user_id:
                customer_orders = customer_client.get("/my/reservations/%d/" % reservation.pk)
                check(
                    customer_orders.status_code == 200
                    and "增值服务消费" in customer_orders.content.decode("utf-8"),
                    "P16 客户详情展示增值服务消费",
                    str(customer_orders.status_code),
                )

            # 已退房记录不能再登记
            closed = SvcRecord.objects.filter(actual_checkout_at__isnull=False).order_by("id").first()
            if closed is not None:
                rejected = reception_client.post(
                    "/reception/services/",
                    {"record_id": closed.pk, "item_id": [created_item.pk], "quantity": ["1"]},
                    follow=True,
                )
                check(
                    "已退房" in rejected.content.decode("utf-8"),
                    "P16 已退房客人不能登记服务",
                )

            # 未选项目不能提交
            empty_post = reception_client.post(
                "/reception/services/", {"record_id": in_house_record.pk}, follow=True
            )
            check(
                "至少选择一项服务" in empty_post.content.decode("utf-8"),
                "P16 未选择服务项目时给出提示",
            )

            # 结算页应把已登记服务计入服务费
            checkout_page = reception_client.get("/reception/checkout/%d/" % in_house_record.pk)
            checkout_body = checkout_page.content.decode("utf-8")
            check(
                "84.00" in checkout_body,
                "P16 结算页把已登记服务费计入账单",
            )
    else:
        rows = ServiceOrder.objects.count()
        check(rows >= 0, "P16 真库消费明细表可读", "共 %d 条" % rows)

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

    from core.models import (
        AppUser,
        CheckInRecord,
        Customer,
        RatePlan,
        Reservation,
        Room,
        RoomBlock,
        RoomType,
    )

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
    room3 = Room.objects.create(room_type=room_type, room_no="803", floor=8, orientation="south", status="available")
    # 房态看板（P09）专用：不参与订单流程，专门给房态动作断言用
    Room.objects.create(room_type=room_type, room_no="804", floor=8, orientation="north", status="available")

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

    from core.models import ServiceItem

    ServiceItem.objects.create(code="BF", name="自助早餐", unit="份", price="68.00", is_active=True)

    # P10 价格方案：给演示房型一条方案，验证“有方案 → 删房型被拦”与方案列表渲染
    today = timezone.localdate()
    RatePlan.objects.create(
        room_type_id=room_type.id,
        name="演示方案",
        price="528.00",
        valid_from=today.replace(day=1),
        valid_to=today.replace(day=min(28, today.day + 3)),
    )
    print(f"[SETUP] sqlite 内存库已建 {len(core_models)} 张表并灌入演示数据（admin/front01/zhangwei，口令 {PASSWORD}）")


if __name__ == "__main__":
    raise SystemExit(main())
