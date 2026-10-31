"""带闸门的提交入口：状态不一致就不许提交。

为什么不用 git hook：
  本机 Windows 沙箱禁止 git 创建管道，`git commit` 连一个 `#!/bin/sh` 的三行钩子都跑不起来
  （实测：钩子里的 `echo > file` 都没执行，git 直接返回 exit 1 并打印 msys 崩溃模块列表）。
  所以闸门放在“提交入口”这一层：把提交命令换成这个脚本，检查不过就不调用 git。

用法：
  python tools/commit.py -F work/commit-msg.txt        # 暂存全部改动后提交
  python tools/commit.py -F msg.txt --no-add           # 只提交已暂存的内容
  python tools/commit.py -m "docs: ..." --no-add       # 直接给一句话
  python tools/commit.py -F msg.txt --smoke            # 提交前额外跑一次离线冒烟并核对基线
  python tools/commit.py -F msg.txt --dry-run          # 只跑检查，不提交

退出码：0 已提交；1 检查未通过（未提交）；2 参数错误/提交失败。
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "work" / "commit_gate.log"


def run(cmd: list[str]) -> int:
    """跑命令，输出落文件再打印（本机沙箱禁止建管道，不能 capture_output）。"""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "w", encoding="utf-8", errors="replace") as handle:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    sys.stdout.write(LOG.read_text(encoding="utf-8", errors="replace"))
    sys.stdout.flush()
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="带状态一致性闸门的 git commit")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("-F", "--file", help="提交信息文件（UTF-8）")
    group.add_argument("-m", "--message", help="提交信息（一行）")
    ap.add_argument("--no-add", action="store_true", help="不自动 git add -A")
    ap.add_argument("--smoke", action="store_true", help="提交前额外跑离线冒烟并核对基线")
    ap.add_argument("--dry-run", action="store_true", help="只跑检查，不提交")
    args = ap.parse_args()

    check_cmd = [sys.executable, str(ROOT / "tools" / "check_status_sync.py")]
    if args.smoke:
        check_cmd.append("--smoke")
    print("[gate] 状态一致性检查：" + " ".join(check_cmd).replace(str(ROOT) + os.sep, ""))
    if run(check_cmd) != 0:
        print("\n[gate] 未通过，已阻止提交。按上面 [FAIL] 行修 docs/03 与 AGENTS.md 后重试。")
        return 1

    if args.no_add:
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
        )
        if staged.returncode != 0:
            print("[gate] git 不可用")
            return 2
    else:
        print("[gate] git add -A")
        if run(["git", "add", "-A"]) != 0:
            print("[gate] git add 失败")
            return 2

    if args.dry_run:
        print("[gate] --dry-run：检查通过，未提交")
        return 0

    if args.file:
        msg_cmd = ["git", "commit", "-F", args.file]
    else:
        msg_cmd = ["git", "commit", "-m", args.message]
    print("[gate] " + " ".join(msg_cmd))
    if run(msg_cmd) != 0:
        print("[gate] git commit 失败（见上面输出）")
        return 2
    print("\n[gate] 已提交。别忘了 git push（沙箱下需 danger-full-access 才可能成功）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
