"""状态一致性检查：把「文档状态」与「实际验证结果」对齐，防止里程碑/任务状态再次漂移。

背景（2026-10-31 两次事故）：
  1) 阶段 4 在 F06/F07/F02/F08 全部落地后仍显示「未开始」——收尾只改了任务行与说明行，漏了阶段行；
  2) 阶段 3 在 F04/F05 时被改成 🟡，之后 P01 与 EXPLAIN 补完，却没人把它翻回 ✅，且行内留着旧冒烟数字与已完成待办。

本脚本把这两类错误变成可执行的断言，提交前由 .githooks/pre-commit 调用：

  python tools/check_status_sync.py            # 只查文档一致性
  python tools/check_status_sync.py --smoke     # 再跑一次离线冒烟，核对文档里的冒烟数字
  python tools/check_status_sync.py --json      # 机器可读输出

退出码：0 一致；1 存在不一致（逐条打印，带文件与行号）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS_03 = ROOT / "docs" / "03-实施计划.md"
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"

# 阶段与其任务归属（与 docs/03 §2 里程碑的「交付物」列一致；新增阶段时同步这里）
STAGE_TASKS: dict[str, list[str]] = {
    "3": ["T4", "T5", "T6", "T7"],
    "4": ["T8", "T9", "T10"],
    "5": ["T11", "T12", "T13"],
    "6": ["T15", "T16"],   # 报告与演示（T15 报告、T16 PPT/彩排）
    "7": ["T17"],           # 现场检查
}
# 阶段 0/1/2 目前没有独立的 T 行（阶段 0 是定案、阶段 1 是数据库脚本、阶段 2 是提交材料），单独给完成判据
STAGE_FREE = {
    "0": "阶段 0 完成后应保持 ✅",
    "1": "阶段 1 五个 SQL 脚本实跑通过后应为 ✅",
    "2": "阶段 2 需等 send2me 上传留证后才可翻 ✅",
}

DONE_ICONS = ("✅",)
PARTIAL_ICONS = ("🟡",)
PENDING_WORDS = ("未开始",)

# 阶段行 / 任务行里出现这些词，说明还留着未完成的东西，不能标 ✅
LEFTOVER_PATTERNS = ("剩余", "待补", "待实跑", "待上传后", "未做")
# 允许的历史数字标注（行内出现这些词时，旧冒烟数字视为“当时的记录”，不报错）
HISTORY_MARKERS = ("阶段完成时", "当时", "阶段内", "该阶段")

SMOKE_RE = re.compile(r"sqlite\s*(\d+)\s*项\s*/\s*真库只读\s*(\d+)\s*项")
AGENTS_SMOKE_RE = re.compile(r"\*\*(\d+)/(\d+)（离线 sqlite）\*\*\s*与\s*\*\*(\d+)/(\d+)（真库只读）\*\*")

problems: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_milestone_table(text: str) -> dict[str, dict[str, str]]:
    """返回 {阶段号: {窗口, 状态, 原始行}}。"""
    stages: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*(\d)\s*([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\s*$", line)
        if not m:
            continue
        num = m.group(1)
        stages[num] = {
            "name": m.group(2).strip(),
            "window": m.group(3).strip(),
            "status": m.group(6).strip(),
            "line": line,
        }
    return stages


def parse_task_table(text: str) -> dict[str, str]:
    """返回 {T 号: 状态列}。

    只认「任务状态」表：其第 2 列是状态（✅/🟡/未开始），而 §3 的 WBS 表第 2 列是负责人（人名）。
    同一 T 号在两表都出现，故必须在状态列里认出图标才收录。
    """
    tasks: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*(T\d+)([^|]*)\|([^|]*)\|", line)
        if not m:
            continue
        first = m.group(1)
        tail = m.group(2)
        cell = m.group(3).strip()
        if not ("✅" in cell or "🟡" in cell or "未开始" in cell):
            continue
        ids = [first]
        # 合并行形如「T15–T17」：把区间展开成单个任务号
        span = re.search(r"[–\-]\s*T(\d+)", tail)
        if span:
            start, end = int(first[1:]), int(span.group(1))
            if 0 < end - start <= 10:
                ids = [f"T{n}" for n in range(start, end + 1)]
        for tid in ids:
            tasks[tid] = cell
    return tasks


ICON_ASCII = {"✅": "DONE", "🟡": "PARTIAL", "未开始": "TODO", "?": "?"}


def ascii_icon(icon: str) -> str:
    """控制台可能是 GBK，打印时把图标换成 ASCII 词。"""
    return ICON_ASCII.get(icon, icon)


def status_icon(cell: str) -> str:
    if "✅" in cell:
        return "✅"
    if "🟡" in cell:
        return "🟡"
    if any(w in cell for w in PENDING_WORDS):
        return "未开始"
    return "?"


def check_stage_vs_tasks(stages: dict[str, dict[str, str]], tasks: dict[str, str]) -> None:
    for stage, tids in STAGE_TASKS.items():
        if stage not in stages:
            fail(f"docs/03 里程碑缺少阶段 {stage} 的行")
            continue
        icon = status_icon(stages[stage]["status"])
        missing = [t for t in tids if t not in tasks]
        if missing:
            fail(f"docs/03 任务状态表缺少 {stage} 阶段的任务行：{', '.join(missing)}")
            continue
        icons = {t: status_icon(tasks[t]) for t in tids}
        all_done = all(v == "✅" for v in icons.values())
        text = stages[stage]["status"]
        if all_done and icon != "✅":
            fail(
                f"阶段 {stage}（{stages[stage]['name']}）的任务已全部完成"
                f"（{'、'.join(tids)}），但阶段行状态仍是「{text[:40]}…」——应翻 ✅ 并写提前天数"
            )
        if icon == "✅" and not all_done:
            undone = [t for t, v in icons.items() if v != "✅"]
            fail(f"阶段 {stage} 标了 ✅，但任务 {'、'.join(undone)} 仍未完成")
        if icon == "✅":
            leftovers = [p for p in LEFTOVER_PATTERNS if p in text]
            if leftovers:
                fail(
                    f"阶段 {stage} 已标 ✅，状态描述里仍留着未完成字样（{'、'.join(leftovers)}）："
                    f"{text[:60]}…"
                )


def check_stage_free(stages: dict[str, dict[str, str]]) -> None:
    for stage, hint in STAGE_FREE.items():
        if stage not in stages:
            fail(f"docs/03 里程碑缺少阶段 {stage} 的行")
            continue
        icon = status_icon(stages[stage]["status"])
        if icon == "?":
            fail(f"阶段 {stage} 状态写法无法识别：{stages[stage]['status'][:50]}")


def check_task_leftovers(tasks: dict[str, str]) -> None:
    for tid, cell in tasks.items():
        if status_icon(cell) != "✅":
            continue
        leftovers = [p for p in LEFTOVER_PATTERNS if p in cell]
        if leftovers:
            fail(f"任务行 {tid} 已标 ✅，但状态列仍有待办字样（{'、'.join(leftovers)}）：{cell[:60]}")


def check_stale_task_mentions(doc_text: str, tasks: dict[str, str]) -> None:
    """段落里写「T13、T15–T17 未开始」这类话时，被点名的任务必须确实未完成。"""
    for raw in doc_text.splitlines():
        if "未开始" not in raw:
            continue
        mentioned = [f"T{n}" for n in re.findall(r"T(\d+)", raw)]
        done = [t for t in dict.fromkeys(mentioned) if tasks.get(t) and status_icon(tasks[t]) == "✅"]
        if done:
            fail(
                f"文档里仍写着「{'、'.join(done)} 未开始」，但任务状态表已标 ✅ —— "
                f"同步这一行：{raw.strip()[:70]}"
            )


def collect_smoke_numbers(text: str) -> list[tuple[int, int, str]]:
    out = []
    for line in text.splitlines():
        for m in SMOKE_RE.finditer(line):
            out.append((int(m.group(1)), int(m.group(2)), line.strip()))
    return out


def check_smoke_baseline(doc_text: str, agents_text: str, readme_text: str) -> tuple[int, int]:
    pairs = collect_smoke_numbers(doc_text)
    if not pairs:
        fail("docs/03 里找不到任何「sqlite N 项 / 真库只读 M 项」的冒烟基线")
        return (0, 0)
    off_max = max(p[0] for p in pairs)
    real_max = max(p[1] for p in pairs)

    # 任务行的数字是“该任务完成时”的记录，允许低于基线；但「状态说明」那一句必须写当前基线，
    # 否则读者会以为基线还是旧的（阶段 3 事故就是这样把 111/88 留在表头的）。
    status_note = next(
        (ln for ln in doc_text.splitlines() if ln.startswith("> 状态列更新于")), ""
    )
    note_hits = list(SMOKE_RE.finditer(status_note))
    if status_note and not note_hits:
        fail("docs/03 的「状态说明」行（> 状态列更新于 …）里没有当前冒烟基线")
    elif note_hits:
        got = note_hits[-1]
        if (int(got.group(1)), int(got.group(2))) != (off_max, real_max):
            fail(
                f"docs/03「状态说明」行写的是 {got.group(1)}/{got.group(2)}，"
                f"不是当前基线 {off_max}/{real_max}"
            )

    # AGENTS.md §4.2 的验证方式必须与基线一致
    m = AGENTS_SMOKE_RE.search(agents_text)
    if not m:
        fail("AGENTS.md §4.2 找不到「**N/N（离线 sqlite）** 与 **M/M（真库只读）**」形式的冒烟基线")
    else:
        a_off, a_off2, a_real, a_real2 = (int(x) for x in m.groups())
        if a_off != a_off2:
            fail(f"AGENTS.md 离线冒烟数字自相矛盾：{a_off}/{a_off2}")
        if a_real != a_real2:
            fail(f"AGENTS.md 真库冒烟数字自相矛盾：{a_real}/{a_real2}")
        if (a_off, a_real) != (off_max, real_max):
            fail(
                f"AGENTS.md 冒烟基线 {a_off}/{a_real} 与 docs/03 的 {off_max}/{real_max} 不一致"
            )

    # README 至少要出现当前基线，避免 README 落后
    if (
        f"sqlite {off_max}" not in readme_text
        and f"sqlite {off_max} 项" not in readme_text
        and f"sqlite {off_max} /" not in readme_text
    ):
        warn(f"README.md 未出现当前离线冒烟基线 sqlite {off_max}")

    return (off_max, real_max)


def read_last_smoke_log() -> int | None:
    """读 work/status_smoke.log 里最近一次离线冒烟的通过项数（没跑过则返回 None）。"""
    log_path = ROOT / "work" / "status_smoke.log"
    if not log_path.exists():
        warn("没有 work/status_smoke.log（还没跑过 --smoke），本次未核对“文档数字 vs 实跑”")
        return None
    hits = re.findall(r"结果：(\d+)\s*项通过", log_path.read_text(encoding="utf-8", errors="replace"))
    return int(hits[-1]) if hits else None


def run_offline_smoke() -> int | None:
    """跑一次离线冒烟并把输出落到 work/ 下的日志文件。

    注意：Windows 沙箱下 subprocess 建管道会被拒（PermissionError: [WinError 5]），
    所以这里用文件重定向而不是 capture_output。
    """
    import os

    log_path = ROOT / "work" / "status_smoke.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "PYTHONPATH": f"{ROOT / 'src'}{os.pathsep}{ROOT / 'work'}",
        "DJANGO_SETTINGS_MODULE": "check_settings",
        "PYTHONIOENCODING": "utf-8",
    }
    with open(log_path, "w", encoding="utf-8", errors="replace") as handle:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "smoke_web.py")],
            cwd=str(ROOT),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    out = log_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"结果：(\d+)\s*项通过", out)
    if not m:
        fail(
            f"离线冒烟没有打印「结果：N 项通过」，退出码 {proc.returncode}；"
            f"日志见 work/status_smoke.log，末尾：{out[-300:]}"
        )
        return None
    return int(m.group(1))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover - 老 Python/被重定向时忽略
        pass
    ap = argparse.ArgumentParser(description="检查文档状态一致性（阶段行/任务行/冒烟基线）")
    ap.add_argument("--smoke", action="store_true", help="额外跑一次离线冒烟，核对文档里的通过项数")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args()

    doc_text = read(DOCS_03)
    agents_text = read(AGENTS)
    readme_text = read(README)

    stages = parse_milestone_table(doc_text)
    tasks = parse_task_table(doc_text)
    check_stage_free(stages)
    check_stage_vs_tasks(stages, tasks)
    check_task_leftovers(tasks)
    check_stale_task_mentions(doc_text, tasks)
    off_max, real_max = check_smoke_baseline(doc_text, agents_text, readme_text)

    smoke_count = None
    if off_max:
        if args.smoke:
            smoke_count = run_offline_smoke()
        else:
            smoke_count = read_last_smoke_log()
        if smoke_count is not None and off_max and smoke_count != off_max:
            fail(
                f"文档写离线冒烟 {off_max} 项，最近一次实跑是 {smoke_count} 项——"
                f"新增/删除断言后要同步 docs/03、AGENTS.md 的基线数字（或先跑 --smoke 刷新日志）"
            )

    summary = {
        "stages": {k: status_icon(v["status"]) for k, v in stages.items()},
        "tasks_done": sorted(t for t, c in tasks.items() if status_icon(c) == "✅"),
        "tasks_open": sorted(t for t, c in tasks.items() if status_icon(c) != "✅"),
        "smoke_baseline": {"offline": off_max, "real": real_max, "measured_offline": smoke_count},
        "problems": problems,
        "warnings": warnings,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("阶段状态：", "  ".join(f"{k}={ascii_icon(v)}" for k, v in summary["stages"].items()))
        print(f"任务完成：{len(summary['tasks_done'])} 项；未完成：{', '.join(summary['tasks_open']) or '无'}")
        print(f"冒烟基线：离线 {off_max} / 真库只读 {real_max}" + (f"（实跑 {smoke_count}）" if smoke_count else ""))
        for w in warnings:
            print(f"[WARN] {w}")
        for p in problems:
            print(f"[FAIL] {p}")

    if problems:
        print(f"\n结果：{len(problems)} 项不一致，{len(warnings)} 项提醒")
        return 1
    print(f"\n结果：状态一致（{len(warnings)} 项提醒）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
