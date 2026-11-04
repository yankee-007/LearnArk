"""CLI command handlers for SkillMap (direction A).

Commands: init/start/say/status/pause/switch/map/next/diagnose/review/sync/
doctor/export.  All state changes happen through :mod:`sm_engine`, so every
command shares one evidence rule set.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from learncore import cli
from learncore import clock
from learncore.fsutil import LearnError
from learncore.sync import GitSync, ensure_git_identity
from learncore import mentor as core_mentor

import sm_engine
import sm_model
import sm_mentors
import sm_state

VARIANT_DIR = Path(__file__).resolve().parent.parent


class UsageError(LearnError):
    """Bad command line: exit code 2."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def open_ctx(args, llm) -> sm_engine.Context:
    root = sm_state.resolve_project_root(getattr(args, "project", None))
    return sm_engine.Context(root, VARIANT_DIR, llm)


def _speaker(mentor: str) -> str:
    return sm_model.MENTOR_LABELS.get(mentor, mentor)


def _record_block(lines: list[str]) -> str:
    if not lines:
        return ""
    return "—— 记录 ——\n" + "\n".join(f"- {line}" for line in lines)


def _display_width(text: str) -> int:
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))


def _pad(text: str, width: int) -> str:
    return str(text) + " " * max(0, width - _display_width(text))


def _table(rows: list[list[str]], headers: list[str]) -> str:
    """``cli.table`` equivalent that aligns CJK text by display width."""
    data = [headers] + [[str(cell) for cell in row] for row in rows]
    widths = [max(_display_width(row[i]) for row in data) for i in range(len(data[0]))]
    lines = []
    for index, row in enumerate(data):
        lines.append("  ".join(_pad(cell, widths[i]) for i, cell in enumerate(row)).rstrip())
        if index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)


def _minutes_suffix(ctx: sm_engine.Context) -> str:
    """State the actual budget; never claim 20 minutes when the learner gave 10."""
    minutes = ctx.minutes()
    if not minutes:
        return ""
    if minutes < sm_model.SHORT_DIAGNOSIS_MINUTES:
        return f"（今天只有 {minutes} 分钟，只做一个最小单元）"
    return f"（今天大约 {minutes} 分钟）"


def _system_turn(ctx: sm_engine.Context, trigger: str, user_text: str):
    """Runtime-owned opening / resume / switch: system event, not a learner turn.

    It used to be written as a learner utterance (``开始学习``) and consumed a
    ``turn_index``; both polluted the authoritative session and the handoff
    turn counts.
    """
    if ctx.llm is None:
        return None
    mentor = ctx.mentor()
    activity = ctx.activity_id()
    turn = sm_mentors.turn(
        ctx.llm,
        system=ctx.system_prompt(),
        context=ctx.model_context(),
        user=user_text,
        transcript=ctx.transcript(),
    )
    ok, problems = sm_engine.validate_turn(ctx, turn)
    if not ok:
        sm_engine.record_invalid(ctx, turn, problems, mentor)
    ctx.mark("plan")
    if getattr(turn, "repaired", False):
        ctx.event(
            "mentor_update_retried",
            {
                "session_id": ctx.plan.get("session_id"),
                "turn_index": int(ctx.plan.get("turn_index", 0)),
                "mentor": mentor,
                "reason": "missing learn-update block on first reply",
                "retries": 1,
                "opening": True,
            },
            dedupe_key=f"retried:{ctx.plan.get('session_id')}:{activity}:{int(ctx.plan.get('turn_index', 0))}:{trigger}",
        )
    opened = ctx.event(
        "session_opened",
        {
            "session_id": ctx.plan.get("session_id"),
            "mentor": mentor,
            "activity_id": activity,
            "mode": ctx.mode_name(),
            "trigger": trigger,
            "mentor_text": turn.text,
            "offline": ctx.mode == "mock",
            "repaired": bool(getattr(turn, "repaired", False)),
        },
        dedupe_key=f"opened:{ctx.plan.get('session_id')}:{trigger}:{int(ctx.plan.get('turn_index', 0))}",
    )
    if opened is None:
        # Re-running `start` in the same turn is idempotent: the opening is
        # already in the session file and must not be appended twice.
        return turn
    ctx.p.append_session_system(
        ctx.plan,
        mentor=mentor,
        activity_id=activity,
        trigger=trigger,
        mentor_text=turn.text,
        record=[f"系统事件：{trigger}", f"导师 {mentor}", f"活动 {activity}"],
    )
    return turn


def _article_hint(ctx: sm_engine.Context, node: dict, stage: str) -> str:
    if stage != "apply":
        return ""
    if ctx.template == "email":
        return f"产物：把这一版邮件存成 `artifacts/{node['id'].lower()}-apply.md`（接受 .md/.txt），再回一句文件路径。"
    return f"产物：把可运行脚本放进 `artifacts/`（如 `artifacts/{node['id'].lower()}_demo.py`），回一句相对路径。"


def _card(ctx: sm_engine.Context) -> str:
    node = ctx.node()
    if node is None:
        return ""
    stage = ctx.plan.get("stage") or "explain"
    decision = ctx.plan.get("last_decision") or {}
    reasons = decision.get("reasons") or []
    breakdown = ctx.budget_breakdown()
    estimate = breakdown["activity"]
    minutes = breakdown["budget"]
    budget_text = ""
    if minutes:
        budget_text = (
            f"（本次预算 {minutes} 分钟：诊断 {breakdown['diagnosis']} + 活动 {estimate} + 收尾 {breakdown['reserve']}，"
            "只承诺推进一个阶段）"
        )
    lines = [
        "—— 今日任务 ——",
        f"节点：{node['id']} {node['title']}（L{int(node.get('level', 0))} → 目标 L{int(node.get('target_level', 3))}）",
        f"阶段：{sm_model.stage_label(stage)} {stage} · 导师：{_speaker(ctx.next_mentor())} · 活动：{node['id']}-{stage}",
        f"预计：{estimate} 分钟{budget_text}",
    ]
    hint = _article_hint(ctx, node, stage)
    if hint:
        lines.append(hint)
    if reasons:
        lines.append("理由：")
        for index, reason in enumerate(reasons[:3], start=1):
            lines.append(f"  {index}. {reason}")
    catalog = " · ".join(f"{item['label']}（{item['reason']}）" for item in ctx.mentor_catalog())
    lines.append(f"可切换导师：{catalog}；用 `switch <id>`")
    lines.append(f"下一步：{sm_engine.next_action(ctx)}")
    return "\n".join(lines)


def _resume_note(ctx: sm_engine.Context) -> str:
    node = ctx.node()
    if node is None:
        return ""
    runtime = ctx.runtime_next()
    stage = ctx.plan.get("stage") or "explain"
    activity = runtime.get("activity_id") or f"{node['id']}-{stage}"
    progress = ctx.plan.get("stage_progress") or {}
    # Only attempts on the *current* activity count; a passed apply does not make
    # the following check "passed" (round-06 reported that false claim).
    attempts = [
        event
        for event in ctx.journal.of_kind("attempt")
        if (event.get("payload") or {}).get("activity_id") == activity
    ]
    if not attempts and not progress.get("turn_count"):
        return ""
    if attempts:
        last = attempts[-1]["payload"]
        passed = bool(progress.get("passed"))
        if last.get("correct") is True and passed:
            clause = f"第 {len(attempts)} 次提交已通过；"
        elif last.get("correct") is True:
            clause = f"第 {len(attempts)} 次提交已判定正确、阶段未收口；"
        elif last.get("correct") is False:
            clause = f"第 {len(attempts)} 次提交未通过；"
        else:
            clause = f"第 {len(attempts)} 次提交待判定；"
    else:
        clause = "本阶段还没有提交记录；"
    placement = "（诊断定位起点）" if (ctx.plan.get("placement") or {}).get("node") == node["id"] else ""
    return (
        f"上次停在 {node['id']} 的 {sm_model.stage_label(stage)}{placement}，{clause}"
        f"今天续做 {activity}，约 {ctx.activity_estimate()} 分钟。"
    )


def _git(ctx: sm_engine.Context) -> GitSync:
    # core 1.0.1's GitSync trims only trailing newlines, so porcelain paths parse
    # correctly.  No local override is needed (or wanted).
    return GitSync(ctx.p.root, exclude=[".learnark/usage.jsonl"])


def _fetch_divergence(git: GitSync) -> tuple[int, int]:
    """Fetch (when a remote exists) and return ``(ahead, behind)`` for the upstream."""
    if not git.remotes():
        return (0, 0)
    try:
        git.run("fetch", "origin", timeout=60)
    except Exception:  # offline is not an error: fall back to local tracking refs
        pass
    try:
        return git._ahead_behind()
    except Exception:
        return (0, 0)


def _print_sync_dict(report: dict) -> None:
    print(f"git state: {report.get('state')} (written={'yes' if report.get('written') else 'no'}, "
          f"committed={'yes' if report.get('committed') else 'no'}, pushed={'yes' if report.get('pushed') else 'no'})")
    print(f"written: {'yes' if report.get('written') else 'no'}")
    committed = "yes" if report.get("committed") else "no"
    if report.get("committed") and report.get("sha"):
        committed += f" (sha {report['sha']}, files {len(report.get('files') or [])})"
    print(f"committed: {committed}")
    print(f"pushed: {'yes' if report.get('pushed') else 'no'}")
    print(f"remote: {report.get('remote') or '（none：无远程，真实 GitHub 同步未验证）'}")
    for path in report.get("files") or []:
        print(f"file: {path}")
    if report.get("detail"):
        print(f"detail: {report['detail']}")
    if report.get("recovery"):
        print(f"recovery: {report['recovery']}")


def _recover_report(ctx: sm_engine.Context, message: str, *, emit: bool = True) -> dict:
    """Delegate to core 1.0.2 `GitSync.recover()`.

    Core performs the safe divergence path: commit, pull, union-merge journal
    conflicts by event id (dedupe index rebuilt), keep the local snapshot choice,
    and abort with the real file list when non-journal files conflict.
    """
    git = _git(ctx)
    try:
        report = git.recover(message)
    except Exception as exc:  # git missing/broken: never lose local state
        data = {
            "state": "no-git",
            "written": True,
            "committed": False,
            "pushed": False,
            "remote": "",
            "files": [],
            "detail": str(exc),
            "recovery": "安装/修复 git 后重试；本地学习记录已保存。",
        }
        if emit:
            _print_sync_dict(data)
        return data
    data = report.as_dict()
    files: list[str] = []
    if report.state == "conflict":
        detail = report.detail or ""
        payload = {}
        if detail.startswith("{"):
            try:
                payload = json.loads(detail)
            except json.JSONDecodeError:
                payload = {}
        files = list(payload.get("blocking") or payload.get("unmerged") or [])
        if not files:
            try:
                files = git.unmerged_paths()
            except Exception:
                files = []
    data["files"] = files
    if emit:
        _print_sync_dict(data)
    return data


def _sync_report(ctx: sm_engine.Context, message: str, *, emit: bool = True) -> dict:
    from learncore.fsutil import sha256_text

    git = _git(ctx)
    ahead, behind = _fetch_divergence(git)
    try:
        unmerged = git.unmerged_paths()
    except Exception:
        unmerged = []
    if (ahead and behind) or unmerged:
        # Delegated safe path instead of blindly rebasing / stacking commits.
        return _recover_report(ctx, message, emit=emit)
    ctx.event(
        "sync",
        {"message": message, "at": clock.now_iso()},
        dedupe_key="sync:%s:%s" % (ctx.plan.get("session_id"), sha256_text(message)[:10]),
        actor="runtime",
    )
    ctx.save()
    try:
        report = git.sync(message)
    except Exception as exc:  # git missing or broken: never lose local state
        if emit:
            print(f"git state: unavailable (written=yes, committed=no, pushed=no)\nwritten: yes\ncommitted: no\npushed: no\nrecovery: {exc}")
        return {"state": "no-git", "written": True, "committed": False, "pushed": False, "remote": "", "files": [], "recovery": str(exc)}
    if emit:
        print(report.headline())
        print(f"written: {'yes' if report.written else 'no'}")
        print(f"committed: {'yes' if report.committed else 'no'}" + (f" (sha {report.sha}, files {len(report.files)})" if report.committed else ""))
        print(f"pushed: {'yes' if report.pushed else 'no'}")
        print(f"remote: {report.remote or '（none：无远程，真实 GitHub 同步未验证）'}")
        if report.detail:
            print(f"detail: {report.detail}")
        if report.recovery:
            print(f"recovery: {report.recovery}")
    return report.as_dict()


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------
def cmd_init(args, llm) -> int:
    template = args.template or sm_model.DEFAULT_TEMPLATE
    if not sm_model.is_known_template(template):
        raise UsageError(f"unknown template {template!r}; choose from {', '.join(sm_model.template_names())}")
    root = Path(args.dir or ".").expanduser()
    result = sm_state.init_project(
        root,
        goal=args.goal,
        template=template,
        minutes_per_week=args.minutes_per_week,
        learner_name=args.name,
    )
    project = result["project"]
    data = result["data"]
    git = GitSync(root)
    created: list[str] = []
    try:
        created = git.ensure_repository()
        ensure_git_identity(root)
    except LearnError as exc:
        print(f"warning: git not initialised: {exc}")
    print(f"SkillMap 项目：{root}")
    print(f"目标：{data.get('goal')}")
    print(f"模板：{template}（{len(sm_model.template_spec(template)['nodes'])} 个节点，诊断 {sm_model.total_probes(template)} 题）")
    print(f"状态：{'已存在，未覆盖（幂等）' if result['existed'] else '已创建'}")
    if result["created"]:
        print("生成：" + "、".join(result["created"]))
    if result.get("journal_repair"):
        print(f"! journal 修复：{result['journal_repair']}")
    if created:
        print("git：" + "、".join(created))
    print("")
    print("下一步：")
    print(f"  python {Path(__file__).with_name('learn.py')} start --project \"{root}\"")
    return 0


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------
def cmd_start(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    if args.minutes:
        ctx.plan["minutes_budget"] = int(args.minutes)
        ctx.mark("plan")
    if args.node:
        sm_engine.plan_next(ctx, force_node=args.node)
    mode = ctx.mode_name()
    resumed = bool(ctx.plan.get("session_active"))
    ctx.ensure_session()
    trigger = "resume" if resumed and mode == "stage" else "start"
    opening = "继续学习" if trigger == "resume" else "开始学习"
    if mode == "diagnose":
        sm_engine.ensure_probes(ctx)
        probe = ctx.current_probe()
        if probe is None:
            sm_engine.finish_diagnosis(ctx)
            mode = "stage"
        else:
            turn = _system_turn(ctx, "start" if trigger != "resume" else "resume", opening + _minutes_suffix(ctx))
            reply = sm_mentors.render_reply(turn.text, ctx.mode) if turn else "[离线脚本导师]\n（未配置导师后端）"
            print(reply)
            print("")
            print(sm_engine.probe_card(ctx, probe))
            ctx.save()
            return 0

    if ctx.plan.get("current_node") is None or (ctx.plan.get("stage_progress") or {}).get("passed"):
        decision = sm_engine.plan_next(ctx)
        if not decision.get("selected") and ctx.plan.get("current_node") is None:
            print("地图上没有可推进的节点。")
            print("建议：运行 `review` 处理到期复习，或 `map` 检查先修等级。")
            ctx.save()
            return 0
    note = _resume_note(ctx)
    turn = _system_turn(ctx, trigger, opening + _minutes_suffix(ctx))
    reply = sm_mentors.render_reply(turn.text, ctx.mode) if turn else "[离线脚本导师]\n（未配置导师后端）"
    print(reply)
    print("")
    if note:
        print(note)
        print("")
    print(_card(ctx))
    ctx.save()
    return 0


# ---------------------------------------------------------------------------
# say
# ---------------------------------------------------------------------------
def cmd_say(args, llm) -> int:
    text = args.text
    if text == "-":
        text = sys.stdin.read()
    text = (text or "").strip()
    if not text:
        raise UsageError("say needs non-empty text (or `say -` to read stdin)")
    ctx = open_ctx(args, llm)
    ctx.refresh()
    if not ctx.plan.get("session_active") or not ctx.plan.get("session_id"):
        ctx.ensure_session()
    turn_index = int(ctx.plan.get("turn_index", 0)) + 1
    dedupe = f"say:{ctx.plan.get('session_id')}:{turn_index}"
    if ctx.journal.has(dedupe):
        print("已记录：这一回合已经写入，不会重复调用导师，也不会重复计数。")
        print(f"当前：{sm_engine.next_action(ctx)}")
        ctx.save()
        return 0

    probe = ctx.current_probe() if ctx.mode_name() == "diagnose" else None
    context = ctx.model_context()
    if probe:
        context += f"\n当前诊断探针 {probe['id']}（锚点 {probe['node']}）：{probe['question']}"
    # Capture the activity/mentor *before* the turn: the turn may finish the
    # diagnosis or advance a stage, and the record must keep the label the
    # learner actually answered.
    turn_mentor = ctx.mentor()
    turn_activity = ctx.activity_id()
    turn = sm_mentors.turn(
        ctx.llm,
        system=ctx.system_prompt(),
        context=context,
        user=text,
        transcript=ctx.transcript(),
    )
    outcome = sm_engine.process_turn(ctx, text, turn)
    progress = ctx.plan.setdefault("stage_progress", {})
    if ctx.mode_name() == "stage" and progress:
        progress["turn_count"] = int(progress.get("turn_count", 0)) + 1

    record = list(outcome.record)
    if turn.updates and isinstance(turn.updates.get("help_level"), int):
        record.append(f"提示等级：{turn.updates['help_level']}")
    attempt = (turn.updates or {}).get("attempt") if isinstance((turn.updates or {}).get("attempt"), dict) else {}
    if attempt and attempt.get("correct") is not None:
        verdict = "正确" if attempt.get("correct") else "未通过"
        record.append(f"作答：{verdict}（{attempt.get('activity_id')}）")

    ctx.p.append_session_turn(
        ctx.plan,
        mentor=turn_mentor,
        activity_id=turn_activity,
        learner_text=text,
        mentor_text=outcome.reply,
        record=record or ["本轮没有新证据"],
    )
    ctx.save()

    print(outcome.reply)
    print("")
    for note in outcome.notes:
        print(f"提示：{note}")
    block = _record_block(record)
    if block:
        print(block)
    if outcome.exit_code == 2:
        return 2

    if ctx.mode_name() == "diagnose":
        probe = ctx.current_probe()
        if probe:
            print("")
            print(sm_engine.probe_card(ctx, probe))
        return 0

    if ctx.mode_name() == "review":
        queue = ctx.plan.get("review_queue") or []
        if queue:
            node = ctx.node()
            print("")
            print(f"—— 下一个复习：{node['id']} {node['title']}（一题，≤5 分钟，零提示）——")
            print(f"当前已到期：{'、'.join(queue)}")
        return 0

    if outcome.diagnosis_finished:
        print("")
        print("诊断结束：只按证据置 L0/L1，自述只作待验证假设。")
        if ctx.plan.get("placement"):
            placement = ctx.plan["placement"]
            print(
                f"定位：{placement['node']} 由探针 {placement['probe']} 判定 L1，"
                f"先修 {placement['prereqs']} 已就绪 → 跳过讲解与操练，直接从 apply 开始。"
            )
        if ctx.plan.get("current_node") is None:
            sm_engine.plan_next(ctx)
        ctx.save()
        print("")
        print(_card(ctx))
        return 0

    if ctx.plan.get("current_node") is None:
        sm_engine.plan_next(ctx)
        ctx.save()
        print("")
        print(_card(ctx))
        return 0

    print("")
    print(f"下一步：{sm_engine.next_action(ctx)}")
    return 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
def _last_handoff(ctx: sm_engine.Context) -> dict:
    events = ctx.journal.of_kind("handoff")
    if events:
        return events[-1].get("payload") or {}
    return ctx.plan.get("last_handoff") or {}


def _sync_state(ctx: sm_engine.Context) -> dict:
    git = _git(ctx)
    try:
        status = git.status()
    except Exception as exc:  # pragma: no cover - git is optional
        return {"state": "unavailable", "detail": str(exc)}
    ahead = int(status.get("ahead", 0) or 0)
    behind = int(status.get("behind", 0) or 0)
    changed = len(status.get("changed") or [])
    unmerged = list(status.get("unmerged") or [])
    if not status.get("is_repo"):
        state = "no-repository"
    elif unmerged:
        state = "unmerged"
    elif status.get("diverged") or (ahead and behind):
        state = "diverged"  # both sides committed: needs `sync --recover`
    elif ahead:
        state = "unpushed"
    elif behind:
        state = "behind"
    elif changed:
        state = "dirty"
    else:
        state = "clean"
    return {
        "state": state,
        "branch": status.get("branch") or "",
        "remote": status.get("remote") or "",
        "changed": changed,
        "ahead": ahead,
        "behind": behind,
        "unmerged": unmerged,
        "diverged": bool(status.get("diverged")) or bool(ahead and behind),
        "written": True,
        "committed": changed == 0,
        "pushed": bool(status.get("remote")) and ahead == 0 and behind == 0,
        "recovery": "运行 `sync --recover` 合并事件流" if state in ("diverged", "unmerged") else "",
    }


def _help_summary(ctx: sm_engine.Context) -> dict:
    """Help levels and evidence split, with duplicates collapsed by (node, label)."""
    attempts = ctx.journal.of_kind("attempt")
    independent = 0
    assisted_attempts = 0
    for event in attempts:
        payload = event.get("payload") or {}
        level = int(payload.get("help_level") or 0)
        if level >= 2:
            assisted_attempts += 1
        elif payload.get("correct") is True and not payload.get("assisted_context"):
            independent += 1
    assisted_completions = len(ctx.journal.of_kind("assisted_completion")) + len(ctx.journal.of_kind("assisted_carryover"))
    last_help = None
    for event in reversed(ctx.journal.of_kind("mentor_turn")):
        payload = event.get("payload") or {}
        if payload.get("session_id") == ctx.plan.get("session_id") and isinstance(payload.get("help_level"), int):
            last_help = int(payload["help_level"])
            break
    last_change = None
    for event in reversed(ctx.journal.of_kind("level_up", "level_down")):
        payload = event.get("payload") or {}
        reason = payload.get("reason") or ""
        last_change = {
            "node": payload.get("node"),
            "from": payload.get("from"),
            "to": payload.get("to"),
            "reason": reason,
            "assisted": bool(payload.get("assisted")) or reason == "after_assisted",
        }
        break
    return {
        "last_help_level": last_help,
        "independent_attempts": independent,
        "assisted_attempts": assisted_attempts,
        "assisted_completions": assisted_completions,
        "last_level_change": last_change,
    }


def status_payload(ctx: sm_engine.Context) -> dict:
    node = ctx.node()
    levels = sm_model.level_counts(ctx.map)
    counts = sm_model.status_counts(ctx.map)
    handoff = _last_handoff(ctx)
    weak: list[str] = []
    misconceptions = []
    seen: set[tuple[str, str]] = set()
    for item in ctx.map["nodes"]:
        for entry in item.get("misconceptions") or []:
            label = entry.get("label")
            key = (item["id"], label)
            if key in seen:
                continue
            seen.add(key)
            misconceptions.append({"node": item["id"], "label": label, "at": entry.get("at"), "level": int(item.get("level", 0))})
            weak.append(f"{item['id']}：{label}")
        if int(item.get("level", 0)) == 0 and item.get("status") != "locked":
            note = f"{item['id']} 仍是 L0（{item.get('title')}）"
            if note not in weak:
                weak.append(note)
    decision = sm_model.next_decision(ctx.map, ctx.plan, ctx.today, ctx.minutes())
    selected = decision.get("selected") or {}
    return {
        "schema_version": sm_model.SCHEMA_VERSION,
        "slug": ctx.pj.get("slug"),
        "goal": ctx.pj.get("goal"),
        "template": ctx.template,
        "learner": {
            "name": (ctx.pj.get("learner") or {}).get("name"),
            "self_report": (ctx.pj.get("learner") or {}).get("self_report") or [],
            "diagnosis": {
                "status": ctx.diagnosis().get("status"),
                "round": ctx.diagnosis().get("round"),
                "completed_at": ctx.diagnosis().get("completed_at"),
                "end_reason": ctx.diagnosis().get("end_reason"),
                "deferred": [
                    probe["id"] for probe in ctx.diagnosis().get("probes") or [] if probe.get("status") == "deferred"
                ],
                "probes": [
                    {
                        "id": probe["id"],
                        "node": probe["node"],
                        "status": probe["status"],
                        "level_set": probe.get("level_set"),
                        "deferred_reason": probe.get("deferred_reason"),
                    }
                    for probe in ctx.diagnosis().get("probes") or []
                ],
            },
        },
        "map": {
            "levels": levels,
            "status_counts": counts,
            "nodes": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "level": int(item.get("level", 0)),
                    "status": item.get("status"),
                    "due": (item.get("review") or {}).get("due"),
                }
                for item in ctx.map["nodes"]
            ],
            "review_due": [item["id"] for item in sm_model.due_nodes(ctx.map, ctx.today)],
        },
        "plan": {
            "mode": ctx.mode_name(),
            "current_node": ctx.plan.get("current_node"),
            "stage": ctx.plan.get("stage"),
            "activity_id": ctx.activity_id() if node else None,
            "mentor": ctx.mentor(),
            "next_mentor": ctx.next_mentor(),
            "minutes_budget": ctx.minutes(),
            "estimate_minutes": ctx.activity_estimate(),
            "session_goal": ctx.plan.get("session_goal"),
            "session_id": ctx.plan.get("session_id"),
            "turn_index": int(ctx.plan.get("turn_index", 0) or 0),
            "placement": ctx.plan.get("placement"),
        },
        "mentors": {
            "current": ctx.mentor(),
            "next": ctx.next_mentor(),
            "allowed": list(ctx.allowed_mentors()),
            "catalog": ctx.mentor_catalog(),
        },
        "current": (
            {
                "node": node["id"],
                "title": node["title"],
                "level": int(node.get("level", 0)),
                "target_level": int(node.get("target_level", 3)),
                "stage": ctx.plan.get("stage"),
                "activity_id": ctx.activity_id(),
                "mentor": ctx.mentor(),
            }
            if node
            else None
        ),
        "weak_points": weak[:8],
        "misconceptions": misconceptions[-8:],
        "help": _help_summary(ctx),
        "runtime_next": ctx.runtime_next(),
        "last_handoff": {
            "from": handoff.get("from"),
            "to": handoff.get("to"),
            "reason": handoff.get("reason"),
            "at": handoff.get("at"),
            "node": handoff.get("node"),
            "stage": handoff.get("stage"),
            "unresolved": handoff.get("unresolved") or [],
            "next": handoff.get("next") or [],
        },
        "next_action": sm_engine.next_action(ctx),
        "next": {
            "node": selected.get("node"),
            "stage": selected.get("stage"),
            "activity_id": selected.get("activity_id"),
            "estimated_minutes": decision.get("estimated_minutes"),
        },
        "sync": _sync_state(ctx),
        "offline": ctx.mode == "mock",
        "core_version": _core_version(),
        "journal": {
            "events": ctx.journal.count(),
            "last_at": (ctx.journal.last(1) or [{}])[0].get("at"),
        },
        "repairs": ctx.repairs,
    }


def cmd_status(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    if ctx.dirty:
        ctx.save()
    payload = status_payload(ctx)
    if args.json:
        cli.emit_json(payload)
        return 0
    print(f"SkillMap · {payload['goal']}")
    print(f"项目：{payload['slug']}（template {payload['template']}）  离线：{'yes' if payload['offline'] else 'no'}")
    current = payload["current"]
    if current:
        print(f"当前：{current['node']} {current['title']} · {current['stage']}（{current['activity_id']}） · 导师 {current['mentor']}")
        budget = payload["plan"].get("minutes_budget")
        estimate = payload["plan"].get("estimate_minutes")
        print(f"进度：本阶段约 {estimate} 分钟" + (f"（本次预算 {budget} 分钟）" if budget else ""))
    elif payload["plan"]["mode"] == "diagnose":
        probes = payload["learner"]["diagnosis"]["probes"]
        done = sum(1 for p in probes if p["status"] in ("done", "skipped"))
        active = sum(1 for p in probes if p["status"] != "deferred")
        deferred = sum(1 for p in probes if p["status"] == "deferred")
        extra = f"，{deferred} 题延后" if deferred else ""
        print(f"当前：诊断中（{done}/{active} 题{extra}）")
    else:
        print("当前：未选节点")
    diagnosis_info = payload["learner"]["diagnosis"]
    if diagnosis_info.get("status") == "skipped":
        answered = sum(1 for p in diagnosis_info["probes"] if p["status"] in ("done", "skipped"))
        deferred = len(diagnosis_info.get("deferred") or [])
        print(f"诊断：已跳过（{answered} 题已答，{deferred} 题延后；已获得的等级与定位保留）")
    levels = payload["map"]["levels"]
    print(f"等级：L0 {levels.get('L0', 0)} · L1 {levels.get('L1', 0)} · L2 {levels.get('L2', 0)} · L3 {levels.get('L3', 0)}")
    mentors = payload["mentors"]
    catalog = " · ".join(f"{item['label']}（{item['reason']}）" for item in mentors["catalog"])
    print(f"导师：当前 {mentors['current']} · 下一位 {mentors['next']} · 可切换 {catalog}")
    help_info = payload["help"]
    last_help = help_info.get("last_help_level")
    last_help_text = "—" if last_help is None else str(last_help)
    print(
        f"帮助：上次提示等级 {last_help_text} · 独立通过 {help_info['independent_attempts']} 次 · "
        f"受助完成 {help_info['assisted_completions']} 次"
    )
    change = help_info.get("last_level_change")
    if change and change.get("node"):
        flavour = "受助后，不计为独立" if change.get("assisted") else "独立通过"
        print(f"最近等级变化：{change['node']} L{change.get('from')} → L{change.get('to')}（{flavour}）")
    if payload["weak_points"]:
        print("薄弱：")
        for item in payload["weak_points"][:4]:
            print(f"  - {item}")
    handoff = payload["last_handoff"]
    if handoff.get("from"):
        print(f"上次交接：{handoff['from']} → {handoff['to']}（{handoff.get('at')}）原因：{handoff.get('reason')}")
    print(f"下一步：{payload['next_action']}")
    sync = payload["sync"]
    print(f"同步：{sync.get('state')}（written={'yes' if sync.get('written') else 'no'} committed={'yes' if sync.get('committed') else 'no'} pushed={'yes' if sync.get('pushed') else 'no'}）")
    if ctx.repairs:
        for note in ctx.repairs:
            print(f"! 状态修复：{note}")
    return 0


def _core_version() -> str:
    try:
        return (VARIANT_DIR / "runtime" / "CORE_VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


# ---------------------------------------------------------------------------
# pause
# ---------------------------------------------------------------------------
def cmd_pause(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    if not ctx.plan.get("session_id"):
        ctx.ensure_session()
    result = sm_engine.write_pause_handoff(ctx, args.note or "")
    handoff = result["handoff"]
    ctx.plan["session_active"] = False
    ctx.plan["mode"] = "idle"
    ctx.mark("plan")
    ctx.save()
    print("已收工。交接已写入 .learnark/handoff/latest.md")
    print(f"- 停在：{handoff.get('node') or '（未定）'} · {handoff.get('stage') or '—'}（{handoff.get('activity_id') or '—'}）")
    for item in handoff.get("unresolved") or []:
        print(f"- 未决：{item}")
    for item in handoff.get("next") or []:
        print(f"- 下一步：{item}")
    if result["duplicate"]:
        print("- 注：同一断点的交接已存在，未重复写入。")
    message = f"learn({ctx.pj.get('slug')}): pause {clock.now().strftime('%Y-%m-%d %H:%M')}"
    _sync_report(ctx, message)
    print("恢复学习：python <variant>\\runtime\\learn.py start --project \"%s\"" % ctx.p.root)
    return 0


# ---------------------------------------------------------------------------
# switch
# ---------------------------------------------------------------------------
def cmd_switch(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    if args.mentor not in sm_model.MENTORS:
        print(f"未知导师 {args.mentor!r}。可选：{', '.join(sm_model.MENTORS)}", file=sys.stderr)
        return 2
    allowed = ctx.allowed_mentors()
    if args.mentor not in allowed:
        catalog = "；".join(f"{m}（{sm_model.mentor_reason(m)}）" for m in allowed)
        print(
            f"不能切到 {args.mentor}：当前阶段是 {sm_model.stage_label(ctx.stage_name())}，"
            f"这里可以切到：{catalog}。",
            file=sys.stderr,
        )
        if ctx.stage_name() == "check":
            print("检查阶段不接受提示：check 必须零提示，examiner 不会给台阶。", file=sys.stderr)
        print(f"可做：继续当前阶段，或用 `switch {allowed[-1]}`。", file=sys.stderr)
        return 2
    ctx.ensure_session()
    reason = args.reason or f"学习者要求切换到 {args.mentor}"
    stage_key = "review" if ctx.mode_name() == "review" else ctx.stage_name()
    on_demand = args.mentor not in sm_model.auto_allowed(stage_key)
    result = sm_engine.write_switch_handoff(ctx, args.mentor, reason)
    handoff = result["handoff"]
    if on_demand:
        ctx.event(
            "on_demand_switch",
            {
                "from": handoff.get("from"),
                "to": args.mentor,
                "stage": ctx.stage_name(),
                "reason": reason,
                "note": "按需切换：不在本阶段默认导师集内，但学习者可以主动要求（例如重新讲解）",
            },
            dedupe_key=f"on_demand_switch:{ctx.plan.get('session_id')}:{handoff.get('from')}->{args.mentor}:{int(ctx.plan.get('turn_index', 0))}",
        )
    ctx.plan["next_mentor"] = ctx.next_mentor()
    ctx.mark("plan")
    turn = _system_turn(ctx, "switch", f"换导师：{handoff['from']} → {args.mentor}，原因：{reason}" + _minutes_suffix(ctx))
    reply = sm_mentors.render_reply(turn.text, ctx.mode) if turn else ""
    ctx.save()
    if reply:
        print(reply)
        print("")
    print("—— 交接 ——")
    print(f"{handoff['from']} → {handoff['to']}：{handoff['reason']}")
    for item in handoff.get("unresolved") or []:
        print(f"- 未决：{item}")
    for item in handoff.get("next") or []:
        print(f"- 下一步：{item}")
    if on_demand:
        print(f"（按需切换：{sm_model.MENTOR_LABELS.get(args.mentor, args.mentor)} 不改变当前阶段，只负责讲解。）")
    print("交接文件：.learnark/handoff/latest.md")
    return 0


# ---------------------------------------------------------------------------
# map
# ---------------------------------------------------------------------------
def map_payload(ctx: sm_engine.Context) -> dict:
    return {
        "schema_version": sm_model.SCHEMA_VERSION,
        "template": ctx.template,
        "gate": int(ctx.map.get("gate", sm_model.GATE)),
        "rule_version": sm_model.RULE_VERSION,
        "review_intervals": list(sm_model.REVIEW_INTERVALS),
        "today": ctx.today,
        "current_node": ctx.plan.get("current_node"),
        "nodes": [
            {
                "id": node["id"],
                "title": node["title"],
                "cluster": node["cluster"],
                "prereqs": list(node.get("prereqs") or []),
                "level": int(node.get("level", 0)),
                "target_level": int(node.get("target_level", 3)),
                "status": node.get("status"),
                "level_source": node.get("level_source"),
                "gate_override": bool(node.get("gate_override")),
                "review": {
                    "interval_index": int((node.get("review") or {}).get("interval_index", 0)),
                    "due": (node.get("review") or {}).get("due"),
                    "lapses": int((node.get("review") or {}).get("lapses", 0)),
                },
                "misconceptions": [item.get("label") for item in node.get("misconceptions") or []],
            }
            for node in ctx.map["nodes"]
        ],
        "summary": {"levels": sm_model.level_counts(ctx.map), "status": sm_model.status_counts(ctx.map)},
    }


def cmd_map(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    if ctx.dirty:
        ctx.save()
    payload = map_payload(ctx)
    if args.json:
        cli.emit_json(payload)
        return 0
    print(
        f"能力地图 · {payload['template']}（可用门槛 L{payload['gate']}：先修 ≥L{payload['gate']} 即可开始；"
        f"掌握仍要 apply/check 的 L2/L3 证据，共 {len(payload['nodes'])} 节点）"
    )
    rows = []
    for node in payload["nodes"]:
        rows.append(
            [
                node["id"],
                node["title"],
                node["cluster"],
                f"L{node['level']}",
                node["status"],
                "、".join(node["prereqs"]) or "—",
                node["review"]["due"] or "—",
            ]
        )
    print(_table(rows, ["id", "节点", "簇", "等级", "状态", "先修", "复习到期"]))
    levels = payload["summary"]["levels"]
    print(f"合计：L0 {levels.get('L0', 0)} · L1 {levels.get('L1', 0)} · L2 {levels.get('L2', 0)} · L3 {levels.get('L3', 0)}")
    return 0


# ---------------------------------------------------------------------------
# next
# ---------------------------------------------------------------------------
def cmd_next(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    decision = sm_engine.decision_payload(ctx)
    ctx.save()
    if args.json:
        cli.emit_json(decision)
        return 0
    selected = decision.get("selected")
    if not selected:
        print("没有可推进的节点。")
        for item in decision.get("excluded") or []:
            print(f"- 排除 {item['reason']}")
        return 0
    print(f"下一个：{selected['node']} {selected['title']} · {sm_model.stage_label(selected['stage'])}（{selected['activity_id']}）")
    print(f"导师：{_speaker(selected['mentor'])} · 预计 {decision['estimated_minutes']} 分钟 · 当前 L{selected['level']} → 目标 L{selected['target_level']}")
    print("理由：")
    for index, reason in enumerate(decision.get("reasons") or [], start=1):
        print(f"  {index}. {reason}")
    excluded = decision.get("excluded") or []
    print(f"被排除的节点（{len(excluded)}）：")
    for item in excluded:
        print(f"  - {item['reason']}")
    review = decision.get("review_due") or []
    if review:
        print(f"到期复习：{'、'.join(review)}（运行 `review`）")
    return 0


# ---------------------------------------------------------------------------
# diagnose
# ---------------------------------------------------------------------------
def cmd_diagnose(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    diagnosis = ctx.diagnosis()
    if args.skip:
        sm_engine.ensure_probes(ctx)
        for probe in diagnosis.get("probes") or []:
            if probe.get("status") == "pending":
                probe["status"] = "skipped"
                probe["level_set"] = 0
        sm_engine.finish_diagnosis(ctx, "skipped", end_reason="diagnose_skip")
        if ctx.plan.get("current_node") is None:
            sm_engine.plan_next(ctx)
        ctx.save()
        print("诊断已跳过：没答的题按 L0 记；已经答对的等级与诊断定位保留（不会被重置）。")
        print("")
        print(_card(ctx))
        return 0
    if diagnosis.get("status") == "pending" and ctx.current_probe():
        print("诊断已在进行中：")
        print("")
        print(sm_engine.probe_card(ctx, ctx.current_probe()))
        return 0
    diagnosis["status"] = "pending"
    diagnosis["round"] = int(diagnosis.get("round") or 0) + 1
    diagnosis["probes"] = []
    diagnosis["completed_at"] = None
    ctx.mark("project")
    sm_engine.ensure_probes(ctx)
    ctx.ensure_session()
    probe = ctx.current_probe()
    turn = _system_turn(ctx, "diagnose", "重新诊断，开始学习" + _minutes_suffix(ctx))
    reply = sm_mentors.render_reply(turn.text, ctx.mode) if turn else ""
    ctx.save()
    if reply:
        print(reply)
        print("")
    print(sm_engine.probe_card(ctx, probe))
    print("")
    print("提示：诊断只把节点置为 L0/L1；已有 L2/L3 不会被降低。")
    return 0


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------
def cmd_review(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    if ctx.diagnosis().get("status") == "pending":
        print("还没完成诊断：先 `start` 做完（或 `diagnose --skip` 跳过），复习才排得出优先级。", file=sys.stderr)
        return 2
    due = sm_model.due_nodes(ctx.map, ctx.today)
    if not due:
        upcoming = sm_model.next_due_node(ctx.map, ctx.today)
        ctx.event(
            "review_checked",
            {"due": 0, "next_due": (upcoming or {}).get("review", {}).get("due"), "today": ctx.today},
            dedupe_key=f"review_checked:{ctx.today}:{ctx.plan.get('session_id')}",
        )
        ctx.save()
        if upcoming:
            print(f"0 个到期复习（今天 {ctx.today}）。最近到期：{upcoming['id']} · {upcoming['review']['due']}。")
        else:
            print("0 个到期复习：还没有安排过复习（节点达到 L1 并完成 check 后才会排期）。")
        print(f"下一步：{sm_engine.next_action(ctx)}")
        return 0
    limit = sm_model.review_limit(ctx.minutes())
    queue = [node["id"] for node in due[:limit]]
    ctx.ensure_session()
    from_mentor = ctx.mentor()
    due_text = "、".join("%s(due %s)" % (node["id"], node["review"]["due"]) for node in due[:limit])
    handoff = sm_engine.build_handoff(
        ctx,
        from_mentor=from_mentor,
        to_mentor="examiner",
        reason=f"复习到期：{due_text}",
        what_tried=[f"复习队列 {len(due)} 个到期，本会话取 {len(queue)} 个"],
        unresolved=[f"{node['id']} 复习未做" for node in due[limit:]],
        next_steps=[f"examiner 出一题零提示 check：{queue[0]}"],
    )
    ctx.plan["mode"] = "review"
    ctx.plan["review_queue"] = queue
    ctx.plan["current_node"] = queue[0]
    ctx.plan["stage"] = "check"
    ctx.plan["stage_progress"] = sm_model.fresh_progress(queue[0], "check")
    ctx.plan["mentor_override"] = None
    ctx.plan["last_handoff"] = handoff
    ctx.mark("plan")
    event = ctx.event("handoff", dict(handoff, trigger="review"), dedupe_key=f"handoff:review:{ctx.plan.get('session_id')}:{','.join(queue)}")
    if event is not None:
        ctx.p.write_handoff(handoff)
    turn = _system_turn(ctx, "review", "复习" + _minutes_suffix(ctx))
    reply = sm_mentors.render_reply(turn.text, ctx.mode) if turn else ""
    ctx.save()
    if reply:
        print(reply)
        print("")
    print(f"—— 复习队列（{len(queue)}/{len(due)}）——")
    for node_id in queue:
        node = ctx.node(node_id)
        print(f"- {node_id} {node['title']}：L{int(node.get('level', 0))}，上次间隔 {node['review']['interval_index']} 档，到期 {node['review']['due']}")
    print("规则：零提示、一题、≤5 分钟；通过间隔 +1 档，失败降 1 级、间隔退 2 档并记 lapses。")
    return 0


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------
def cmd_sync(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    ctx.save()
    message = args.message or f"learn({ctx.pj.get('slug')}): sync {clock.now().strftime('%Y-%m-%d %H:%M')}"
    if getattr(args, "recover", False):
        report = _recover_report(ctx, message)
        state = report.get("state")
        if state in ("pushed", "clean", "no-remote"):
            return 0
        print("恢复未完成，本地成果保留；按上面的 file/recovery 提示处理后重试（不会 force push）。")
        return 3
    report = _sync_report(ctx, message)
    state = report.get("state")
    if state in ("conflict", "commit-failed", "diverged", "recover-blocked", "push-failed"):
        if state == "conflict":
            files = report.get("files") or []
            if files:
                print("冲突文件：" + "、".join(files))
            print("事件流冲突可用 `sync --recover` 自动合并；状态文件冲突需要人工选择保留哪一边。")
        else:
            print("同步未完成，但本地成果已保存；按 recovery 提示处理后重试（不会 force push）。")
        return 3
    return 0


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
def cmd_doctor(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    problems: list[dict] = []
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str, fix: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "fix": fix})
        if not ok:
            problems.append({"name": name, "detail": detail, "fix": fix})

    check("项目可读", True, str(ctx.p.root))
    check("schema_version", int(ctx.pj.get("schema_version") or 0) == sm_model.SCHEMA_VERSION, f"project={ctx.pj.get('schema_version')} map={ctx.map.get('schema_version')}")
    expected_nodes = len(sm_model.template_spec(ctx.template)["nodes"])
    check("地图节点数", len(ctx.map.get("nodes") or []) == expected_nodes, f"{len(ctx.map.get('nodes') or [])}/{expected_nodes}", "删除 .learnark/state/map.json 与 map.json.bak 后重新 init 可重建（会丢等级）")
    node_ids = sm_model.node_order(ctx.map)
    current = ctx.plan.get("current_node")
    check("计划引用有效", current is None or current in node_ids, f"current_node={current}", "运行 `start` 重新选节点")

    integrity = ctx.journal.integrity()
    check("journal 完整", not integrity.get("problems"), json.dumps(integrity, ensure_ascii=False), "journal 是权威记录，损坏时从 .bak 或 git 恢复")
    index_path = ctx.p.dedupe_path
    dedupe_ok = True
    dedupe_detail = "missing (will rebuild from journal)"
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            dedupe_ok = isinstance(data, dict)
            dedupe_detail = f"{len(data)} keys"
        except (json.JSONDecodeError, OSError) as exc:
            dedupe_ok = False
            dedupe_detail = f"corrupt: {exc}"
    check("去重索引", dedupe_ok, dedupe_detail, "删除 .learnark/journal/dedupe.json，下次写入会从 journal 重建")

    locks = sorted(str(p.relative_to(ctx.p.root)) for p in ctx.p.dot.rglob("*.lock"))
    check("锁文件", True, "、".join(locks) or "none")

    git = _git(ctx)
    try:
        status = git.status()
        check("git 仓库", bool(status.get("is_repo")), f"branch={status.get('branch') or '-'} changed={len(status.get('changed') or [])} remote={status.get('remote') or '(none)'}", "run `git init` or `sync`")
        if status.get("is_repo"):
            _fetch_divergence(git)  # refresh tracking refs; offline is fine
            status = git.status()
            unmerged = status.get("unmerged") or []
            div = bool(status.get("diverged")) or bool(unmerged)
            check(
                "git 同步状态",
                not div,
                f"ahead={status.get('ahead', 0)} behind={status.get('behind', 0)} unmerged={len(unmerged)}",
                "本地与远程分叉：运行 `sync --recover` 合并事件流（不会 force push）",
            )
            if status.get("changed"):
                check("git 工作区", True, f"{len(status.get('changed') or [])} 个文件未提交（sync 会提交）")
    except Exception as exc:  # pragma: no cover
        check("git 仓库", False, str(exc), "install git")

    mode = (os.environ.get("LEARNARK_LLM") or "auto").lower()
    key = bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LEARNARK_API_KEY"))
    if mode == "mock":
        check("LLM 配置", True, "offline/mock（脚本导师，不代表真实教学质量）")
    elif key:
        check("LLM 配置", True, "api key present（不打印值）")
    else:
        check("LLM 配置", False, "no API key: 设置 DEEPSEEK_API_KEY，或用 --offline", "set DEEPSEEK_API_KEY")

    known = {event.get("id") for event in ctx.journal.all()}
    missing_events = [
        f"{node['id']}:{item.get('event_id')}"
        for node in ctx.map["nodes"]
        for item in node.get("evidence") or []
        if item.get("event_id") and item["event_id"] not in known
    ]
    check("证据可追溯", not missing_events, "、".join(missing_events[:5]) or "all evidence event ids present", "从 git 恢复 journal")

    missing_artifacts = []
    for node in ctx.map["nodes"]:
        for item in node.get("evidence") or []:
            if item.get("artifact") and not (ctx.p.root / item["artifact"]).is_file():
                missing_artifacts.append(f"{node['id']}:{item['artifact']}")
    check(
        "产物存在",
        not missing_artifacts,
        "、".join(missing_artifacts[:5]) or "ok",
        "产物被删除：等级应退回 L1（design §4），补回产物或重新 apply",
    )

    core_vendored = (ctx.p.variant_dir / "runtime" / "learncore" / "__init__.py").is_file()
    check("vendored core", core_vendored, f"CORE_VERSION={_core_version()}")
    if ctx.repairs:
        check("状态修复", True, "；".join(ctx.repairs))

    print(f"doctor · {ctx.p.root}")
    for item in checks:
        mark = "ok  " if item["ok"] else "FAIL"
        print(f"[{mark}] {item['name']}: {item['detail']}")
    if problems:
        print("")
        print("建议：")
        for problem in problems:
            print(f"- {problem['name']}: {problem['fix'] or '检查上面的 detail'}")
        print(f"共 {len(problems)} 个问题。")
        return 3
    print("")
    print("全部检查通过。")
    return 0


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
def cmd_export(args, llm) -> int:
    ctx = open_ctx(args, llm)
    ctx.refresh()
    payload = status_payload(ctx)
    map_data = map_payload(ctx)
    levels = payload["map"]["levels"]
    levels_text = " · ".join(f"L{index} {levels.get(f'L{index}', 0)}" for index in range(4))
    lines = [
        f"# SkillMap 学习档案 · {payload['goal']}",
        "",
        f"- 生成时间：{clock.now_iso()}",
        f"- 项目：{payload['slug']} · 模板 {payload['template']} · core {payload['core_version']}",
        f"- 离线模式：{'yes（脚本导师，不代表真实教学质量）' if payload['offline'] else 'no'}",
        f"- 诊断：{payload['learner']['diagnosis']['status']}（round {payload['learner']['diagnosis']['round']}）",
        f"- 等级分布：{levels_text}",
        "",
        "## 能力地图",
        "",
        "| id | 节点 | 簇 | 等级 | 状态 | 先修 | 复习到期 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for node in map_data["nodes"]:
        lines.append(
            f"| {node['id']} | {node['title']} | {node['cluster']} | L{node['level']} | {node['status']} | "
            f"{'、'.join(node['prereqs']) or '—'} | {node['review']['due'] or '—'} |"
        )
    lines += ["", "## 薄弱与错因", ""]
    if payload["misconceptions"]:
        for item in payload["misconceptions"]:
            lines.append(f"- {item['node']}（L{item['level']}，{item.get('at')}）：{item['label']}")
    else:
        lines.append("- 暂无记录")
    lines += ["", "## 最近交接", ""]
    handoff = payload["last_handoff"]
    if handoff.get("from"):
        lines += [
            f"- {handoff['from']} → {handoff['to']}（{handoff.get('at')}）：{handoff.get('reason')}",
            f"- 停在：{handoff.get('node')} · {handoff.get('stage')}",
        ]
        for item in handoff.get("unresolved") or []:
            lines.append(f"- 未决：{item}")
    else:
        lines.append("- 暂无交接")
    lines += ["", "## 会话记录", ""]
    sessions = sorted((ctx.p.sessions_dir.glob("*.md"))) if ctx.p.sessions_dir.exists() else []
    for path in sessions[-10:]:
        lines.append(f"- `{path.relative_to(ctx.p.root).as_posix()}`")
    if not sessions:
        lines.append("- 暂无会话")
    lines += ["", "## 下一步", "", f"- {payload['next_action']}", ""]
    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out
    out.parent.mkdir(parents=True, exist_ok=True)
    from learncore.fsutil import atomic_write_text

    atomic_write_text(out, "\n".join(lines))
    ctx.save()
    print(f"已导出：{out}")
    print(f"（{len(map_data['nodes'])} 个节点，{len(sessions)} 份会话记录）")
    return 0
