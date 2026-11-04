#!/usr/bin/env python3
"""SkillMap (LearnArk direction A) command line entry point.

Run from anywhere inside a project, or point at one with ``--project``::

    python runtime/learn.py init --goal "Agent 开发" --dir proj
    python runtime/learn.py start --project proj
    python runtime/learn.py say "我不确定 RAG 和 Agent 记忆的区别" --project proj

Exit codes: 0 ok · 2 usage / stage gate · 3 state or concurrency conflict · 4 env
(no API key, network, unexpected).
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from learncore import cli  # noqa: E402
from learncore.fsutil import LearnError, LockTimeout, StaleWrite, file_lock  # noqa: E402
from learncore.llm import LLMError, LLMUnavailable, from_env  # noqa: E402

import sm_commands  # noqa: E402
import sm_state  # noqa: E402

VARIANT_DIR = HERE.parent
FIXTURE = VARIANT_DIR / "tests" / "fixtures" / "mentor_script.jsonl"


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="learn",
        description="SkillMap — 能力地图式学习框架（LearnArk direction A）",
        epilog="全局参数可放在任意位置：--project PATH、--offline。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="建立学习项目（可重复执行）")
    p_init.add_argument("--goal", default=None, help="学习目标")
    p_init.add_argument("--minutes-per-week", type=int, default=None)
    p_init.add_argument("--template", default="agent-dev", choices=["agent-dev", "email"])
    p_init.add_argument("--dir", default=".", help="项目目录（默认当前目录）")
    p_init.add_argument("--name", default=None, help="学习者称呼")
    p_init.set_defaults(handler=sm_commands.cmd_init, needs_llm=False)

    p_start = sub.add_parser("start", help="开始或继续今天的学习")
    p_start.add_argument("--minutes", type=int, default=None, help="本次时间预算（≤20 分钟只推进一个阶段）")
    p_start.add_argument("--node", default=None, help="强制进入某个节点（越过先修门槛，等级上限 L1）")
    p_start.set_defaults(handler=sm_commands.cmd_start)

    p_say = sub.add_parser("say", help="学习者发言 / 提交答案")
    p_say.add_argument("text", help="回答内容；`-` 表示从 stdin 读")
    p_say.set_defaults(handler=sm_commands.cmd_say)

    p_status = sub.add_parser("status", help="当前状态")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(handler=sm_commands.cmd_status)

    p_pause = sub.add_parser("pause", help="收工：写交接并提交")
    p_pause.add_argument("--note", default=None)
    p_pause.set_defaults(handler=sm_commands.cmd_pause)

    p_switch = sub.add_parser("switch", help="切换导师（受阶段限制）")
    p_switch.add_argument("mentor", help="navigator | concept | coach | examiner")
    p_switch.add_argument("--reason", default=None)
    p_switch.set_defaults(handler=sm_commands.cmd_switch)

    p_map = sub.add_parser("map", help="能力地图进度")
    p_map.add_argument("--json", action="store_true")
    p_map.set_defaults(handler=sm_commands.cmd_map)

    p_next = sub.add_parser("next", help="下一个节点与理由")
    p_next.add_argument("--json", action="store_true")
    p_next.set_defaults(handler=sm_commands.cmd_next)

    p_diag = sub.add_parser("diagnose", help="重新诊断（或 --skip 跳过）")
    p_diag.add_argument("--skip", action="store_true")
    p_diag.set_defaults(handler=sm_commands.cmd_diagnose)

    p_review = sub.add_parser("review", help="到期复习队列（进入 check）")
    p_review.set_defaults(handler=sm_commands.cmd_review)

    p_sync = sub.add_parser("sync", help="git 同步")
    p_sync.add_argument("--message", default=None)
    p_sync.add_argument("--recover", action="store_true", help="分叉时合并事件流并推送（不 force push）")
    p_sync.set_defaults(handler=sm_commands.cmd_sync)

    p_doctor = sub.add_parser("doctor", help="自检")
    p_doctor.set_defaults(handler=sm_commands.cmd_doctor)

    p_export = sub.add_parser("export", help="导出学习档案")
    p_export.add_argument("--out", required=True)
    p_export.set_defaults(handler=sm_commands.cmd_export)

    return parser


def split_global(argv: list[str]) -> tuple[dict, list[str]]:
    """Pull ``--project``/``--offline`` out of argv wherever they appear."""
    project = None
    offline = False
    rest: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--offline":
            offline = True
            index += 1
            continue
        if token == "--project":
            if index + 1 >= len(argv):
                raise sm_commands.UsageError("--project needs a path")
            project = argv[index + 1]
            index += 2
            continue
        if token.startswith("--project="):
            project = token.split("=", 1)[1]
            index += 1
            continue
        rest.append(token)
        index += 1
    return {"project": project, "offline": offline}, rest


def configure_offline(offline: bool) -> None:
    if offline:
        os.environ["LEARNARK_LLM"] = "mock"
    mode = (os.environ.get("LEARNARK_LLM") or "").strip().lower()
    if mode == "mock" and not os.environ.get("LEARNARK_MOCK_SCRIPT") and FIXTURE.is_file():
        os.environ["LEARNARK_MOCK_SCRIPT"] = str(FIXTURE)


def make_llm(project_arg: str | None):
    usage = None
    try:
        root = sm_state.resolve_project_root(project_arg)
        usage = root / ".learnark" / "usage.jsonl"
    except LearnError:
        usage = None
    return from_env(usage_file=usage)


def lock_timeout() -> float:
    """Seconds to wait for the per-project write lock.

    ``LEARNARK_LOCK_TIMEOUT`` makes the wait explicit (tests and CI set it small
    so a held lock produces the documented exit-3 conflict instead of a stall).
    """
    raw = (os.environ.get("LEARNARK_LOCK_TIMEOUT") or "").strip()
    if not raw:
        return 20.0
    try:
        value = float(raw)
    except ValueError:
        return 20.0
    return max(0.1, min(value, 600.0))


def run(argv: list[str]) -> int:
    globals_, rest = split_global(argv)
    configure_offline(globals_["offline"])
    parser = build_parser()
    args = parser.parse_args(rest)
    args.project = globals_["project"]
    args.offline = globals_["offline"]
    llm = make_llm(args.project) if getattr(args, "needs_llm", True) else None
    handler = args.handler
    if args.command != "init":
        root = None
        try:
            root = sm_state.resolve_project_root(args.project)
        except LearnError:
            root = None
        if root is not None:
            # Serialise every whole command, not only the obvious writers:
            # `status`, `map`, `next` and `export` also persist refreshed node
            # statuses and repair notes, and per-document locks alone let two
            # commands interleave into a confusing StaleWrite.
            with file_lock(root / ".learnark" / "project.lock", timeout=lock_timeout()):
                return int(handler(args, llm) or 0)
    return int(handler(args, llm) or 0)


def main(argv: list[str] | None = None) -> int:
    cli.setup_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 0
    try:
        return run(args)
    except sm_commands.UsageError as exc:
        cli.warn(f"learn: {exc}")
        return 2
    except (LLMUnavailable, LLMError) as exc:
        cli.warn(f"learn: mentor backend unavailable: {exc}")
        return 4
    except (LockTimeout, StaleWrite) as exc:
        cli.warn(f"learn: state changed concurrently: {exc}")
        return 3
    except LearnError as exc:
        cli.warn(f"learn: {exc}")
        return 3
    except SystemExit as exc:  # argparse
        return int(exc.code or 0)
    except KeyboardInterrupt:
        cli.warn("learn: interrupted (writes are atomic; re-run to continue).")
        return 130
    except Exception as exc:  # pragma: no cover - defensive
        if os.environ.get("LEARNARK_DEBUG"):
            traceback.print_exc()
        cli.warn(f"learn: unexpected error: {type(exc).__name__}: {exc}")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
