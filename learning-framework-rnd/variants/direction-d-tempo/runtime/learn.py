"""Tempo CLI — `python runtime/learn.py <command>` (direction-d-tempo).

Commands: init, start, say, status, pause, switch, due, plan, review, skills,
sync, doctor, export, version.

Exit codes follow shared/spec-core.md: 0 ok, 2 usage, 3 state/concurrency,
4 environment/network.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import tempo  # noqa: E402  (after sys.path injection)
from learncore import clock  # noqa: E402
from learncore import mentor as mentor_core  # noqa: E402
from learncore.cli import (  # noqa: E402
    EXIT_ENV,
    EXIT_OK,
    EXIT_STATE,
    EXIT_USAGE,
    emit_json,
    kv_block,
    main as cli_main,
    table,
    warn,
)
from learncore.fsutil import LearnError, LockTimeout, StaleWrite, file_lock, find_project_root  # noqa: E402

USAGE = """LearnArk · Tempo（方向 D：动态调度复习型）

用法:
  python learn.py init --goal "目标" [--template agent-dev|email] [--dir PATH]
                       [--minutes-per-week N] [--name SLUG] [--learner NAME]
  python learn.py start [--minutes N] ["一句话文本（含分钟数）"]
  python learn.py say "学习者原话"            # say - 从 stdin 读
  python learn.py status [--json]
  python learn.py pause [--note "…"]
  python learn.py switch <coach|trainer|examiner>
  python learn.py due [--json]
  python learn.py plan [--json]
  python learn.py review [--minutes N]
  python learn.py skills [--json]
  python learn.py sync [--message "…"]
  python learn.py doctor
  python learn.py export --out FILE

全局参数（可放在任意位置）:
  --project PATH   指定项目（默认从当前目录向上找 .learnark/）
  --offline        离线脚本导师（等价 LEARNARK_LLM=mock，输出带 [离线脚本导师]）

调度器权威：导师只能建议 next，不能改活动/预算/到期；等级只按证据提升，
纯卡练习最高 L2，L3 需块产物 + ≥7 天延迟复测。
"""


class UsageError(Exception):
    pass


# --------------------------------------------------------------------------------------
# argument helpers
# --------------------------------------------------------------------------------------


def split_globals(argv: list[str]) -> tuple[list[str], str | None, bool]:
    rest: list[str] = []
    project = None
    offline = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--project" and index + 1 < len(argv):
            project = argv[index + 1]
            index += 2
            continue
        if arg.startswith("--project="):
            project = arg.split("=", 1)[1]
            index += 1
            continue
        if arg == "--offline":
            offline = True
            index += 1
            continue
        rest.append(arg)
        index += 1
    return rest, project, offline


def parse_flags(argv: list[str], spec: dict[str, bool]) -> tuple[dict, list[str]]:
    """Parse ``--flag value`` / ``--flag=value`` / boolean flags; return (opts, positional)."""
    opts: dict = {}
    positional: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg.startswith("--"):
            name = arg[2:]
            value = None
            if "=" in name:
                name, value = name.split("=", 1)
            if name not in spec:
                raise UsageError(f"未知参数 --{name}")
            if spec[name]:
                if value is None:
                    if index + 1 >= len(argv):
                        raise UsageError(f"--{name} 需要一个值")
                    value = argv[index + 1]
                    index += 1
                opts[name] = value
            else:
                opts[name] = True if value is None else value
        else:
            positional.append(arg)
        index += 1
    return opts, positional


def resolve_root(project: str | None, *, allow_missing: bool = False) -> Path:
    if project:
        path = Path(project).expanduser()
        if allow_missing:
            return path.resolve()
        if not path.exists():
            raise LearnError(f"--project 路径不存在：{path}")
        if (path / ".learnark").is_dir():
            return path.resolve()
        try:
            return find_project_root(path)
        except LearnError as exc:
            raise LearnError(str(exc)) from exc
    try:
        return find_project_root()
    except LearnError:
        if allow_missing:
            return Path.cwd().resolve()
        raise


def lock_timeout() -> float:
    """Seconds to wait for the per-project write lock.

    ``LEARNARK_LOCK_TIMEOUT`` makes the wait explicit (tests set it small so a held
    lock produces the documented exit-3 conflict instead of a stall).
    """
    raw = (os.environ.get("LEARNARK_LOCK_TIMEOUT") or "").strip()
    if not raw:
        return 20.0
    try:
        value = float(raw)
    except ValueError:
        return 20.0
    return max(0.1, min(value, 600.0))


def load_store(root: Path, offline: bool, *, reconcile: bool = True) -> tempo.Store:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    store = tempo.Store(root, offline=offline).load()
    if reconcile:
        notes = tempo.reconcile(store)
        for note in notes:
            store.repairs.append(note)
        if notes:
            store.save()
    return store


def print_repairs(store: tempo.Store) -> None:
    for note in store.repairs:
        print(f"[恢复] {note}")


def print_day_notes(day: dict | None) -> None:
    """Surface backlog folds / decay so they are never silent."""
    for note in (day or {}).get("notes") or []:
        print(f"[调整] {note}")


def print_unfinished(store: tempo.Store) -> None:
    unfinished = [item for item in store.today_items() if not item.get("done") and item.get("activity_id")]
    for item in unfinished:
        print(
            f"[未完成] {item.get('activity_type')} · {item.get('skill') or '-'}"
            f"（{item.get('minutes')} 分钟）：保留在待办，下次会先回到它。"
        )
    return unfinished


def sync_git(store: tempo.Store, message: str | None = None, *, recover: bool = False) -> dict:
    from learncore.sync import GitSync

    slug = store.meta.get("slug") or "learnark"
    default = f"learn({slug}): {clock.now().strftime('%Y-%m-%d %H:%M')}"
    text = (message or default).strip()
    if message:
        text = f"learn({slug}): {message.strip()}"
    git = GitSync(
        store.root,
        include=[".learnark", "sessions", "artifacts", "AGENTS.md", "README.md", ".gitignore", ".gitattributes"],
    )
    # core 1.0.2: porcelain parsing, .gitattributes and journal union recovery live in core
    report = git.recover(text) if recover else git.sync(text)
    record = report.as_dict()
    record["detail"] = report.detail
    if not record.get("branch"):
        record["branch"] = git.branch()
    if not record.get("remote") and git.remotes():
        record["remote"] = git.remote_url()
    try:
        from learncore.fsutil import append_jsonl

        append_jsonl(
            store.root / ".learnark" / "sync-log.jsonl",
            {
                "at": clock.now_iso(),
                "simulated": clock.is_simulated(),
                "message": text,
                "recover": recover,
                "state": record.get("state"),
                "written": record.get("written"),
                "committed": record.get("committed"),
                "pushed": record.get("pushed"),
                "sha": record.get("sha"),
                "remote": bool(record.get("remote")),
            },
            fsync=False,
        )
    except OSError:
        pass
    return record


def print_sync(report: dict) -> None:
    headline = (
        f"git state: {report.get('state')} "
        f"(written={'yes' if report.get('written') else 'no'}, "
        f"committed={'yes' if report.get('committed') else 'no'}, "
        f"pushed={'yes' if report.get('pushed') else 'no'})"
    )
    print(headline)
    if report.get("files"):
        print(f"  提交文件：{len(report['files'])} 个（样例：{', '.join(report['files'][:5])}）")
    if report.get("sha"):
        print(f"  commit: {report['sha']}  分支: {report.get('branch') or '-'}")
    if report.get("remote"):
        print(f"  remote: {report['remote']}")
    else:
        print("  remote: 无（无远程，真实 GitHub 同步未验证；本地记录已保存）")
    if report.get("state") == "conflict":
        print("  CONFLICT：本地与远程分叉，没有 force push，本地提交完整保留。")
        detail = report.get("detail") or ""
        try:
            parsed = json.loads(detail)
        except (ValueError, TypeError):
            parsed = {}
        blocking = parsed.get("blocking") or parsed.get("unmerged") or []
        if blocking:
            print("  冲突文件：" + "、".join(str(path) for path in blocking))
        elif detail:
            print(f"  冲突详情：{detail[:400]}")
        if parsed.get("reason") == "non-journal-conflicts":
            print("  说明：只有 journal 可以自动并集合并；state 快照需要人工保留一侧。")
        print("  下一步：只冲突 journal 时运行 `sync --recover`；状态文件冲突先人工保留一侧再 sync。")
    if report.get("detail") and report.get("state") in ("pushed", "push-failed"):
        print(f"  详情：{report['detail']}")
    if report.get("recovery"):
        print(f"  恢复建议：{report['recovery']}")


# --------------------------------------------------------------------------------------
# shared entry helpers
# --------------------------------------------------------------------------------------


def apply_budget(store: tempo.Store, parsed: tempo.BudgetParse, source: str, *, additive: bool = True) -> str:
    """Record the time the learner has *for this entry*.

    Additive: stated minutes are added to the day's already-used time, so the day
    budget only grows by what the learner just declared. ``carry`` keeps the day
    budget unchanged (a same-day ``start`` without a new number must not rewrite it).
    """
    today = tempo.date_of(tempo.now_iso())
    if store.schedule.get("today", {}).get("date") != today:
        store.schedule["today"] = {
            "date": today,
            "minutes_budget": store.minutes_default(),
            "minutes_used": 0,
            "minutes_left": store.minutes_default(),
            "budget_source": "default",
            "items": [],
        }
        store.schedule["plan"] = []
    used = store.today_used()
    stated = int(parsed.minutes or store.minutes_default())
    note = parsed.note or ""
    if source == "carry":
        store.append(
            "budget_carried",
            {
                "date": today,
                "budget": store.today_budget(),
                "used": used,
                "remaining": store.today_remaining(),
                "note": "same-day start without a new minutes argument; day budget is kept",
            },
            dedupe_key=f"carry:{today}:{store.today_budget()}:{used}",
        )
        store.refresh_budget_fields()
        return note
    if additive:
        store.schedule["today"]["minutes_budget"] = used + stated
    else:
        store.schedule["today"]["minutes_budget"] = stated
    store.schedule["today"]["budget_source"] = source
    store.refresh_budget_fields()
    store.append(
        "budget_set",
        {
            "date": today,
            "minutes": stated,
            "budget_after": store.today_budget(),
            "used": used,
            "remaining": store.today_remaining(),
            "raw": parsed.raw,
            "matched": parsed.matched,
            "source": source,
            "additive": additive,
            "clamped": parsed.clamped,
            "note": note,
        },
        dedupe_key=f"budget:{today}:{stated}:{source}:{tempo.sha(parsed.matched or '', 8)}",
    )
    return note


def make_opening(store: tempo.Store, activity: dict, decision: dict, budget: int, llm, mode: str) -> dict:
    if mode == "mock":
        return {
            "text": tempo.local_opening(store, activity, decision, budget),
            "raw": "",
            "updates": None,
            "source": "local-template",
            "model": "mock",
        }
    prompt = (
        f"（开场）今天预算 {budget} 分钟，开始活动 {activity['activity_id']}"
        f"（{activity['activity_type']}，{activity.get('minutes')} 分钟，技能 {activity.get('skill')}）。"
        "请用两三句话说明这次做什么、怎么算完成，然后给出第一步；不要输出机器块以外的额外格式。"
        "完成规则：只有判对且达到完成标准才算完成；只答一部分记 partial，活动保持开放，不要说“答完就算完成”。"
    )
    session_stub = {"mentor": activity.get("mentor"), "budget": budget}
    try:
        turn = mentor_core.run_turn(
            llm,
            system=tempo.mentor_system_prompt(store, activity.get("mentor", "coach"), activity),
            context=tempo.mentor_context(store, session_stub, activity),
            user=prompt,
            transcript=[],
            max_tokens=800,
        )
        text = (turn.text or "").strip()
        if not text:
            raise LearnError("导师开场为空")
        return {
            "text": text,
            "raw": turn.raw,
            "updates": turn.updates,
            "source": "api",
            "error": turn.update_error,
            "model": turn.model,
        }
    except LearnError as exc:
        warn(f"learn: 导师开场调用失败（{exc}）；本次用本地模板开场，仍然可以继续学习。")
        return {
            "text": tempo.local_opening(store, activity, decision, budget),
            "raw": "",
            "updates": None,
            "source": "fallback",
            "model": "fallback",
        }


def begin_entry(
    store: tempo.Store,
    budget: int,
    *,
    offline: bool,
    forced: str = "",
    max_items: int | None = None,
    decision: dict | None = None,
) -> dict:
    limits = store.limits
    if decision is None:
        decision = tempo.plan_decision(
            store,
            minutes=budget,
            max_items=int(max_items if max_items is not None else limits.get("max_items_per_session", 2)),
            force_due=(forced == "review"),
            allow_repeat=(forced == "review"),
        )
    activity = dict(decision["chosen"])
    activity["template_id"] = store.template_id
    activity["budget"] = budget
    llm = tempo.llm_handle(store, offline=offline)
    mode = "mock" if getattr(llm, "mode", "api") == "mock" else "api"
    opening = make_opening(store, activity, decision, budget, llm, mode)
    session = tempo.open_session(store, activity, budget, opening["text"], forced=forced, mode=mode)
    store.append(
        "mentor_opening",
        {
            "session": session["id"],
            "activity_id": activity["activity_id"],
            "mode": mode,
            "source": opening.get("source"),
            "raw_sha256": tempo.sha(opening.get("raw") or opening["text"], 32),
            "updates_ignored": bool(opening.get("updates")),
        },
        dedupe_key=f"opening:{session['id']}",
    )
    tempo.record_schedule_decision(
        store,
        session["id"],
        decision,
        budget,
        forced=forced,
        entry=len(store.today_items()),
    )
    today = store.schedule["today"]
    today["plan"] = decision.get("plan_ids") or []
    store.schedule["plan"] = decision.get("plan_ids") or []
    if opening.get("model"):
        store.meta["last_model"] = opening["model"]
        store.touch("meta")
    store.refresh_budget_fields()
    store.touch("schedule")
    return {"session": session, "decision": decision, "activity": activity, "opening": opening, "mode": mode, "llm": llm}


def recovery_lines(store: tempo.Store) -> list[str]:
    lines = []
    last = store.schedule.get("last_activity") or {}
    if last:
        lines.append(
            f"上次停在哪：{last.get('activity_type') or '-'} · {last.get('skill') or '-'}"
            f"（{tempo.fmt_at(last.get('at'))}）"
        )
    handoff = store.root / ".learnark" / "handoff" / "latest.md"
    if handoff.exists():
        text = handoff.read_text(encoding="utf-8")
        for pattern in (r"- 下一步：(.+)", r"- 哪里不稳：(.+)"):
            match = __import__("re").search(pattern, text)
            if match:
                lines.append(f"交接{'下一步' if '下一步' in pattern else '不稳'}：{match.group(1).strip()}")
    due_cards = store.due_cards()
    if due_cards:
        lines.append(
            f"到期提醒：{len(due_cards)} 张卡到期，最久逾期 {max(tempo.overdue_days(c.get('due_at')) for c in due_cards)} 天"
        )
    else:
        lines.append("到期提醒：今天没有到期的卡")
    return lines


def time_note() -> str:
    if not clock.is_simulated():
        return ""
    return f"[时间] 模拟时钟 {clock.now_iso()}（仅证明调度逻辑，不证明真实记忆保持）"


def print_cap_close(store: tempo.Store) -> None:
    limits = store.limits
    items = store.today_items()
    done = sum(1 for item in items if item.get("done"))
    next_due = store.due_cards()
    horizon = ""
    if next_due:
        soonest = min(next_due, key=lambda c: c.get("due_at") or "")
        horizon = f"下次到期：{tempo.date_of(soonest.get('due_at'))}（{soonest.get('id')}）"
    else:
        skills = [s for s in store.skills.get("skills", []) if s.get("due_at")]
        if skills:
            soonest = min(skills, key=lambda s: s.get("due_at") or "")
            horizon = f"下次技能复测：{tempo.date_of(soonest.get('due_at'))}（{soonest.get('id')}）"
    print(
        f"今日已排 {len(items)}/{limits.get('max_items_per_session', 2)} 项（完成 {done} 项）"
        f" · 预算 {store.today_budget()} 分钟（已用 {store.today_used()}，剩 {store.today_remaining()}）。"
    )
    print("今天不再排新活动——这不是欠账：到期的卡明天仍在队列里。")
    if horizon:
        print(horizon)
    print("现在可以 pause 结束并保存；想提前清到期卡可以显式 review；或明天直接 start。")


def print_budget_close(store: tempo.Store) -> None:
    print(
        f"今日预算已用完：{store.today_budget()} 分钟（已用 {store.today_used()}，剩 {store.today_remaining()}）。"
    )
    print("不再排新活动；可以 pause 收尾，或改天再来（到期队列会保留）。")


def print_decision(store: tempo.Store, decision: dict, budget: int, *, show_table: bool = True) -> None:
    if show_table:
        print("候选（按两级选择 + 组内打分，输入只有 state + 预算 + 时钟）：")
        print(tempo.render_candidate_table(decision.get("top") or [], limit=5))
    print(f"为什么是它：{decision.get('reason_line')}")
    plan = decision.get("plan") or []
    if len(plan) > 1:
        parts = [f"{i + 1}) {c['activity_type']}·{c.get('skill') or '-'}（{c['minutes']} 分钟）" for i, c in enumerate(plan)]
        print("本次计划（≤{} 项）：{}".format(store.limits.get("max_items_per_session", 2), " → ".join(parts)))
    print(f"本次可用 {budget} 分钟；活动上限 20 分钟。")


# --------------------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------------------


def cmd_init(argv: list[str]) -> int:
    opts, positional = parse_flags(
        argv,
        {
            "goal": True,
            "minutes-per-week": True,
            "template": True,
            "dir": True,
            "name": True,
            "learner": True,
            "self-report": True,
        },
    )
    if positional:
        raise UsageError(f"init 不认识的位置参数：{' '.join(positional)}")
    template_id = (opts.get("template") or "agent-dev").strip()
    if template_id not in ("agent-dev", "email"):
        raise UsageError("--template 只能是 agent-dev 或 email")
    root = Path(opts["dir"]).expanduser().resolve() if opts.get("dir") else Path.cwd().resolve()
    existing_meta = root / ".learnark" / "project.json"
    if existing_meta.exists():
        try:
            existing = json.loads(existing_meta.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}
        if existing.get("template_id") and existing.get("template_id") != template_id:
            raise UsageError(
                f"项目已存在且模板是 {existing.get('template_id')}；不要用 --template {template_id} 覆盖已有状态。"
            )
    goal = (opts.get("goal") or "").strip()
    if not goal and not existing_meta.exists():
        raise UsageError('首次 init 必须给 --goal "…"')
    minutes_per_week = None
    if opts.get("minutes-per-week"):
        try:
            minutes_per_week = int(opts["minutes-per-week"])
        except ValueError as exc:
            raise UsageError("--minutes-per-week 必须是整数") from exc
        if minutes_per_week <= 0:
            raise UsageError("--minutes-per-week 必须大于 0")
    if not goal:
        goal = json.loads(existing_meta.read_text(encoding="utf-8")).get("goal", "学习目标")
    result = tempo.init_project(
        root,
        goal=goal,
        template_id=template_id,
        minutes_per_week=minutes_per_week,
        name=opts.get("name"),
        learner=opts.get("learner"),
        self_report=opts.get("self-report"),
    )
    meta = result["meta"]
    print(("已创建" if result["created"] else "已存在，沿用已有状态（幂等）") + f" Tempo 项目：{result['root']}")
    print(
        kv_block(
            [
                ("目标", meta.get("goal")),
                ("模板", meta.get("template_id")),
                ("导师", ", ".join(meta.get("mentors") or [])),
                ("技能", f"{result['skill_count']} 个"),
                ("卡片", f"{result['card_count']} 张（今天到期 2 张，其余分散到未来几天）"),
                ("每周预算", f"{meta.get('minutes_per_week')} 分钟"),
                ("每次默认", f"{meta.get('minutes_default')} 分钟"),
            ]
        )
    )
    if result.get("git_created"):
        print(f"git: {'、'.join(result['git_created'])}")
    if time_note():
        print(time_note() + "；种子卡的 due_at 由该时钟写入")
    commit = result.get("commit") or {}
    if commit.get("committed"):
        print(f"git: 已提交 {commit.get('sha')}（本地）")
    print('下一步：python learn.py start --minutes 20   （或 start "今天只有二十分钟"）')
    return EXIT_OK


def cmd_start(argv: list[str]) -> int:
    minutes_arg = None
    text_parts: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--minutes":
            if index + 1 >= len(argv):
                raise UsageError("--minutes 需要一个整数")
            try:
                minutes_arg = int(argv[index + 1])
            except ValueError as exc:
                raise UsageError("--minutes 必须是整数") from exc
            index += 2
            continue
        if arg.startswith("--minutes="):
            try:
                minutes_arg = int(arg.split("=", 1)[1])
            except ValueError as exc:
                raise UsageError("--minutes 必须是整数") from exc
            index += 1
            continue
        if arg.startswith("--"):
            raise UsageError(f"start 不认识参数 {arg}")
        text_parts.append(arg)
        index += 1
    if minutes_arg is not None and not 1 <= minutes_arg <= 240:
        raise UsageError("--minutes 必须是 1–240 的整数")
    offline = _OFFLINE
    root = resolve_root(_PROJECT)
    store = load_store(root, offline)
    now = tempo.now_iso()
    day = tempo.prepare_day(store, now)
    text = " ".join(text_parts).strip()
    today_date = tempo.date_of(now)
    same_day = store.schedule.get("today", {}).get("date") == today_date
    explicit = minutes_arg is not None or bool(text)
    if explicit:
        parsed, source, hint = tempo.budget_for_start(minutes_arg, text or None, store.minutes_default())
    elif same_day and store.budget_source() in ("flag", "text", "say"):
        # Do NOT silently rewrite the day's budget: keep what the learner stated.
        parsed = tempo.BudgetParse(
            store.today_budget(),
            "carry",
            store.today_budget(),
            "本次没有新的分钟数",
        )
        source, hint = "carry", parsed.note
    else:
        parsed, source, hint = tempo.budget_for_start(None, None, store.minutes_default())
    note = parsed.note or hint
    had_prior_session = bool(store.schedule.get("last_activity"))
    prior_mentor = store.meta.get("mentor")
    print_repairs(store)
    print(f"== Tempo · {store.meta.get('goal')} ==")
    for line in recovery_lines(store):
        print(line)
    if time_note():
        print(time_note())
    if not store.meta.get("diagnosed"):
        print("[诊断] 首次进入：先用到期卡自测校准等级；自述（“我学过”）不计等级，只看行为证据。")
    print_day_notes(day)
    prev_session = store.schedule.get("current_session")
    prev_activity = (prev_session or {}).get("activity") or {}
    prev_item = next(
        (item for item in store.today_items() if item.get("activity_id") == prev_activity.get("activity_id")),
        None,
    )
    if prev_session and prev_item and not prev_item.get("done"):
        planned = int(prev_activity.get("minutes") or prev_item.get("minutes") or 0)
        elapsed = tempo._elapsed_minutes(prev_session.get("started_at"), now)
        store.append(
            "activity_replaced",
            {
                "session": prev_session.get("id"),
                "activity_id": prev_activity.get("activity_id"),
                "activity_type": prev_activity.get("activity_type"),
                "skill": prev_activity.get("skill"),
                "planned_min": planned,
                "elapsed_min": elapsed,
                "reason": "start-before-completion",
            },
            dedupe_key=f"replace:{prev_session.get('id')}:{prev_activity.get('activity_id')}",
        )
        print_unfinished(store)
    if store.cap_reached():
        print(
            f"[预算] 今日已排满，保留今日预算 {store.today_budget()} 分钟"
            f"（已用 {store.today_used()}，剩余 {store.today_remaining()}）；不追加新的分钟数。"
        )
        print_cap_close(store)
        print("想追加一次核心块：先 pause 收尾，下一次 start 会优先核心写作块；今天不再加排新项。")
        store.save()
        return EXIT_OK
    apply_budget(store, parsed, source)
    if source == "carry":
        budget_line = (
            f"沿用今天已定 {store.today_budget()} 分钟 · 已用 {store.today_used()} · 剩余 {store.today_remaining()}"
        )
    elif source == "default":
        budget_line = (
            f"默认 {store.today_budget()} 分钟 · 已用 {store.today_used()} · 剩余 {store.today_remaining()}"
        )
    else:
        budget_line = (
            f"本次 {parsed.minutes} 分钟 · 已用 {store.today_used()} · 剩余 {store.today_remaining()}"
            f"（今日累计 {store.today_budget()}）"
        )
    print("[预算] " + budget_line + (f"；{note}" if note else ""))
    if tempo._llm_mode() == "mock":
        print("离线模式：导师为脚本导师，输出带 [离线脚本导师]，不代表真实教学质量。")
    else:
        print("导师模式：真实 API（密钥只从环境变量读取）。")

    # a file the learner dropped in counts as an artifact submission, even without a new say
    for line in tempo.acknowledge_pending_artifact(store, now):
        print(f"[产物] {line}")
    limits = store.limits
    min_activity = int(limits.get("min_activity", 5))
    entry_budget = store.today_remaining()
    if entry_budget < min_activity:
        print_budget_close(store)
        store.save()
        return EXIT_OK

    requested_override = store.meta.get("mentor_override")
    preview = tempo.load_preview(store, entry_budget)
    if preview is None:
        planned = tempo.plan_decision(
            store,
            minutes=entry_budget,
            max_items=int(limits.get("max_items_per_session", 2)),
        )
        if planned.get("fallback"):
            print(
                f"[预算] 今日剩余 {entry_budget} 分钟，但同模板/技能已覆盖，没有合适的新活动；"
                "保留预算，下次 start 重新调度。"
            )
            store.save()
            return EXIT_OK
        preview = planned
    core_ids, core_info = tempo.core_block_priority(store, now, entry_budget)
    planned_ids = {activity.get("activity_id") for activity in (preview.get("plan") or [])}
    if core_info and core_info["activity_id"] not in planned_ids:
        store.append(
            "core_block_deferred",
            {
                **core_info,
                "available_minutes": entry_budget,
                "reason": "core-block-does-not-fit-budget",
            },
            dedupe_key=f"coredefer:{tempo.date_of(now)}:{core_info['step']}",
        )
        store.schedule["priority_block"] = core_info
        print(
            f"[核心块] 本次排不进 {core_info['minutes']} 分钟{tempo.activity_label(store.template_id, core_info['activity_type'])}；"
            f"下次先做它（约 {core_info['minutes']} 分钟）。"
        )
    elif core_info:
        store.schedule.pop("priority_block", None)
    entry = begin_entry(store, entry_budget, offline=offline, decision=preview)
    tempo.clear_preview(store)
    session = entry["session"]
    decision = entry["decision"]
    opening = entry["opening"]
    activity = entry["activity"]
    new_mentor = activity.get("mentor")
    print()
    print(f"本次导师：{tempo.mentor_label(new_mentor)}   会话：{session['id']}")
    if requested_override and new_mentor == requested_override:
        print(
            f"[导师] switch 指定 {tempo.mentor_label(requested_override)}：本次由它带"
            f"{tempo.activity_label(store.template_id, activity.get('activity_type'))}（{activity.get('minutes')} 分钟），优先于活动类型绑定。"
        )
    elif had_prior_session and prior_mentor and new_mentor and prior_mentor != new_mentor:
        print(
            f"[导师] {prior_mentor} → {new_mentor}：按活动类型绑定导师"
            f"（本次是{tempo.activity_label(store.template_id, activity.get('activity_type'))}），不是随机切换。"
        )
    if entry["mode"] == "api":
        actual = opening.get("model") or "-"
        configured = tempo._configured_model()
        print(f"[模型] 实际返回：{actual}" + (f"（配置：{configured}）" if actual != configured else ""))
    print_decision(store, decision, entry_budget)
    print()
    print(opening["text"])
    print()
    print(f"下一步：把你的回答用 say 交给导师，例如 python learn.py say \"…\"；做完了用 pause 收尾。")
    store.save()
    return EXIT_OK


def cmd_say(argv: list[str]) -> int:
    offline = _OFFLINE
    text = " ".join(argv).strip()
    if not text:
        raise UsageError('say 需要学习者原话，例如 say "三种停止条件是…"')
    if text == "-":
        text = sys.stdin.read().strip()
        if not text:
            raise UsageError("stdin 为空")
    root = resolve_root(_PROJECT)
    store = load_store(root, offline)
    day = tempo.prepare_day(store)
    print_repairs(store)
    print_day_notes(day)

    if time_note():
        print(time_note())

    session = store.schedule.get("current_session")
    activity = (session or {}).get("activity")
    if not session or not activity:
        print("[自动开始] 没有进行中的活动，先调度一个。")
        entry_budget = store.today_remaining() or store.minutes_default()
        if store.today_remaining() <= 0:
            apply_budget(store, tempo.BudgetParse(entry_budget, "", entry_budget, ""), "auto")
            entry_budget = store.today_remaining() or store.minutes_default()
        entry = begin_entry(store, entry_budget, offline=offline)
        session = entry["session"]
        activity = entry["activity"]
        print_decision(store, entry["decision"], entry_budget, show_table=False)
        print(f"（{tempo.activity_label(store.template_id, activity.get('activity_type'))} · {activity.get('minutes')} 分钟 · {session['id']}）")

    parsed = tempo.parse_budget_text(text)
    if parsed.parsed:
        store.append(
            "budget_ignored_in_answer",
            {
                "session": session["id"],
                "matched": parsed.matched,
                "minutes": parsed.minutes,
                "reason": "say-is-answer-not-a-budget-command",
            },
            dedupe_key=f"budgetignored:{session['id']}:{tempo.sha(text, 12)}",
        )
        print(
            f"[预算] 回答里的“{parsed.matched}”只是作答内容，不改今日预算；"
            "要追加时间请用 start --minutes N。"
        )

    previous_mentor = ""
    for message in reversed(session.get("messages") or []):
        if message.get("role") == "mentor":
            previous_mentor = message.get("text", "")
            break

    llm = tempo.llm_handle(store, offline=offline)
    mode = "mock" if getattr(llm, "mode", "api") == "mock" else "api"
    model_used = ""
    turn_index = tempo.count_session_turns(store, session["id"])
    # Content-addressed turn key: re-running the same `say` command in the same
    # session is a replay, not a new turn; a different sentence is a new turn.
    dedupe_key = f"say:{session['id']}:{tempo.sha(text, 12)}"
    existing_turn = next((event for event in store.events("turn") if event.get("dedupe_key") == dedupe_key), None)

    if existing_turn is not None:
        payload = existing_turn.get("payload") or {}
        visible = payload.get("visible") or ""
        raw = payload.get("raw") or ""
        updates = payload.get("updates")
        error = payload.get("update_error") or ""
        turn_index = int(payload.get("turn_index", turn_index))
        previous_mentor = payload.get("previous_mentor", previous_mentor)
        print("[重复执行] 这一轮已记录，未重复计数。")
        replay = True
    else:
        replay = False
        print("导师模式：真实 API" if mode == "api" else "导师模式：离线脚本导师（mock）")
        try:
            turn = mentor_core.run_turn(
                llm,
                system=tempo.mentor_system_prompt(store, session["mentor"], activity),
                context=tempo.mentor_context(store, session, activity),
                user=text,
                transcript=session.get("messages") or [],
                max_tokens=1200,
            )
        except LearnError as exc:
            warn(f"learn: 导师调用失败：{exc}")
            return EXIT_ENV
        visible, raw, updates, error = turn.text, turn.raw, turn.updates, turn.update_error
        if mode == "mock" and ("[MOCK MENTOR]" in visible or "offline scripted mentor" in visible):
            visible = (
                "（离线脚本导师没有匹配到这句话，本轮不记录证据。"
                "可以按 start 里的题目回答，或换一句更具体的说法。）"
            )
        model_used = turn.model or getattr(llm, "model", "")
        if updates is None and not error:
            # one silent repair attempt; the learner never sees protocol internals
            repaired_updates, repair_raw, repair_error = tempo.repair_missing_update(
                llm,
                system=tempo.mentor_system_prompt(store, session["mentor"], activity),
                context=tempo.mentor_context(store, session, activity),
                previous_raw=raw,
                learner_text=text,
            )
            store.append(
                "mentor_update_retried",
                {
                    "session": session["id"],
                    "turn_index": turn_index,
                    "ok": repaired_updates is not None,
                    "error": repair_error,
                    "silent": True,
                },
                dedupe_key=f"retry:{session['id']}:{tempo.sha(text, 12)}",
            )
            if repaired_updates is not None:
                updates = repaired_updates
                error = ""
        store.meta["last_model"] = model_used or "mock"
        store.touch("meta")
        store.append(
            "turn",
            {
                "session": session["id"],
                "mentor": session["mentor"],
                "activity_id": activity.get("activity_id"),
                "activity_type": activity.get("activity_type"),
                "skill": activity.get("skill"),
                "help_level": (updates or {}).get("help_level"),
                "attempt": (updates or {}).get("attempt"),
                "next": (updates or {}).get("next"),
                "visible": visible,
                "raw": raw,
                "updates": updates,
                "update_error": error,
                "mode": mode,
                "offline": offline,
                "turn_index": turn_index,
                "learner": text,
                "previous_mentor": previous_mentor,
            },
            dedupe_key=dedupe_key,
        )

    result = tempo.apply_turn(
        store,
        session,
        activity,
        text,
        raw,
        updates,
        error,
        turn_index,
        mode,
        visible=visible,
        previous_mentor=previous_mentor,
    )
    prefix = "[离线脚本导师] " if mode == "mock" else ""
    print()
    print(prefix + (visible or "（导师没有返回正文）"))
    print()
    print("—— 本轮记录 ——")
    internal_markers = ("导师用了活动别名", "导师回填的", "导师 skill_signal", "导师上报活动", "leech")
    learner_notes = [
        note for note in (result.get("notes") or []) if not any(marker in note for marker in internal_markers)
    ]
    if result.get("invalid"):
        print("这一轮没有形成可记录的证据，已跳过（不计分、不影响已有记录）。可以换个说法再答一次。")
    else:
        evidence = result.get("evidence") or {}
        help_labels = {0: "独立完成", 1: "小提示", 2: "分步引导", 3: "代做"}
        evidence_labels = {"observed": "观察记录", "verified": "独立复现", "self_report": "自述", "none": "无"}
        if result.get("attempt_kind") == "question":
            print("这一轮是提问/求助：按“无尝试”记录（不升级、不建卡；下一步以 status 为准）。")
        elif result.get("result") == "partial":
            print("这一轮部分正确：按 partial 记录（不升级、不建卡）；补齐缺的部分再答一次。")
        elif result.get("result") == "conflict":
            print("导师文字与机器块判定不一致：本轮不记对错、不升级、不建卡，等下一轮清晰判定。")
        else:
            verdict = "判对" if result.get("correct") else "未判对"
            print(
                f"提示级别 {result.get('help_level')}（{help_labels.get(result.get('help_level'), '未知')}）"
                f" · 本题{verdict}"
                f" · 证据：{evidence_labels.get(evidence.get('level'), evidence.get('level'))}"
                + ("（受助完成，只算接触）" if evidence.get("assisted") else "")
            )
        for note in learner_notes:
            print(f"- {note}")
        if result.get("next"):
            print(f"- 导师建议（只是建议、不排课；下一步以 status 为准）：{result['next']}")
        print(f"- 活动完成：{'是' if result.get('completed') else '否（仍在进行中）'}")
        if mode == "api" and model_used:
            configured = tempo._configured_model()
            print(f"- 实际模型：{model_used}" + (f"（配置：{configured}）" if model_used != configured else ""))
    records = [
        f"help_level: {result.get('help_level')}",
        f"attempt: correct={result.get('correct')} kind={result.get('attempt_kind')} result={result.get('result')} (activity {activity.get('activity_id')})",
        f"evidence: {(result.get('evidence') or {}).get('level')} assisted={(result.get('evidence') or {}).get('assisted')}",
        f"flags: echoed={result.get('echoed')} text_conflict={result.get('text_conflict')} time_boxed={result.get('time_boxed')}",
        f"next: {result.get('next') or ''}",
    ]
    for note in learner_notes:
        records.append(f"note: {note}")
    if model_used:
        records.append(f"model: {model_used}")
    if not replay:
        tempo.append_session_turn(store, session, text, visible or "（空）", records)
    if not store.meta.get("diagnosed") and result.get("evidence"):
        store.meta["diagnosed"] = True
        store.touch("meta")
    store.save()
    return EXIT_OK


def cmd_status(argv: list[str]) -> int:
    opts, positional = parse_flags(argv, {"json": False})
    if positional:
        raise UsageError(f"status 不认识的位置参数：{' '.join(positional)}")
    root = resolve_root(_PROJECT)
    store = load_store(root, _OFFLINE, reconcile=False)
    payload = tempo.status_payload(store)
    if opts.get("json"):
        emit_json(payload)
        return EXIT_OK
    print(f"== {payload['project'].get('goal')} ==")
    model_info = payload.get("model") or {}
    print(
        kv_block(
            [
                ("项目", f"{payload['project'].get('slug')} · 模板 {payload['project'].get('template_id')}"),
                ("版本", f"{payload['variant']} {payload['version']} / core {payload['core_version']}"),
                ("导师", f"{payload.get('mentor')}（可 switch {', '.join(payload.get('mentors') or [])}）"),
                ("时间", payload["now"] + ("（模拟，仅证明调度逻辑）" if payload.get("simulated") else "（真实）")),
                (
                    "模式",
                    ("离线脚本导师" if payload.get("offline") else "真实 API")
                    + (
                        f" · 配置模型 {model_info.get('configured')} / 上次实际 {model_info.get('last') or '未记录'}"
                        if not payload.get("offline")
                        else ""
                    ),
                ),
                (
                    "今日",
                    f"{payload['today'].get('date')} · 预算 {payload['today'].get('minutes_budget')} 分钟（累计）"
                    f" · 已用 {payload['today'].get('minutes_used')} · 剩余 {payload['today'].get('remaining_minutes')} 分钟"
                    f" · 已排 {payload['today'].get('items_started')}/{payload['today'].get('max_items')} 项"
                    f"（完成 {payload['today'].get('items_done')} 项）",
                ),
                (
                    "到期",
                    f"{payload['due'].get('cards')} 张卡（最久逾期 {payload['due'].get('max_overdue_days')} 天）"
                    f" · {payload['due'].get('skills')} 个技能",
                ),
            ]
        )
    )
    if payload.get("mentor_override"):
        print(
            f"导师覆盖：{payload['mentor_override']}（下次 start 生效；用掉或再次 switch 后清除）"
        )
    if payload.get("pending_artifact"):
        pending = payload["pending_artifact"]
        print(
            f"待确认产物：{pending.get('path')}（{'已落盘，运行 start/say/pause 会确认完成' if pending.get('exists') else '尚未落盘'}）"
        )
    elif (payload.get("today") or {}).get("cap_reached"):
        print("今日已排满 2 项上限：下面的“下一步”是下次的建议，不是今天没做完的事。")
    last_turn = payload.get("last_turn") or {}
    if last_turn:
        help_labels = {0: "独立完成", 1: "小提示", 2: "分步引导", 3: "代做"}
        last_result = last_turn.get("result") or last_turn.get("attempt_kind")
        if last_result == "question":
            verdict = "提问/无尝试"
        elif last_result == "partial":
            verdict = "部分正确（不计）"
        elif last_result == "conflict":
            verdict = "判定冲突（不计）"
        else:
            verdict = "判对" if last_turn.get("correct") else "未判对"
        print(
            f"上次帮助：提示级别 {last_turn.get('help_level')}（{help_labels.get(last_turn.get('help_level'), '未知')}）"
            f" · {verdict} · 证据类型 {last_turn.get('evidence_kind') or last_turn.get('attempt_kind')}"
            + (" · 受助" if last_turn.get("assisted") else " · 独立")
            + (" · 复述导师例子" if last_turn.get("echoed") else "")
        )
    unfinished = payload.get("unfinished") or []
    if unfinished:
        print(
            "未完成："
            + "、".join(f"{item.get('activity_type')} · {item.get('skill') or '-'}（{item.get('minutes')} 分钟）" for item in unfinished)
        )
    print()
    print("技能（平表：等级/证据/上次帮助/到期/错误标签；没有先修边）：")
    rows = []
    for skill in payload.get("skills") or []:
        rows.append(
            [
                skill["id"],
                f"L{skill['level']}",
                skill.get("evidence_level") or "-",
                "-" if skill.get("last_help_level") is None else f"L{skill['last_help_level']}",
                tempo.date_of(skill.get("due_at")) or "-",
                str(skill.get("overdue_days") or 0),
                str(skill.get("lapses") or 0),
                "、".join(skill.get("wrong_tags") or []) or "-",
            ]
        )
    print(table(rows, ["技能", "等级", "证据", "上次帮助", "到期", "逾期", "lapses", "错误标签"]))
    print()
    last = payload.get("last_activity") or {}
    if last:
        print(f"上次活动：{last.get('activity_type')} · {last.get('skill') or '-'}（{tempo.fmt_at(last.get('at'))}）")
    last_session = payload.get("last_session") or {}
    if last_session:
        print(f"会话：{last_session.get('id')} · {last_session.get('path')} · {last_session.get('turns')} 轮")
    if payload.get("handoff"):
        print(f"交接：{payload['handoff'].get('path')} · 下一步：{payload['handoff'].get('next') or '-'}")
    if payload.get("recovery"):
        print("恢复：" + "；".join(payload["recovery"]))
    block = payload.get("block") or {}
    if block:
        print(
            f"本周块：{block.get('id')} · {block.get('goal')} · 步骤 {block.get('steps_done')}/{block.get('steps_total')}"
        )
    print()
    nxt = payload.get("next") or {}
    when = "现在" if nxt.get("when") == "now" else "下次"
    if nxt.get("activity_type"):
        print(
            f"下一步（{when}）：{nxt.get('activity_type')} · {nxt.get('skill') or '-'}"
            f"（{nxt.get('minutes')} 分钟，Tier {nxt.get('tier')}；{nxt.get('activity_id')}）"
        )
    else:
        print(f"下一步（{when}）：暂时没有具体活动")
    print(f"  理由：{nxt.get('reason')}")
    if nxt.get("when") != "now":
        today_info = payload.get("today") or {}
        if today_info.get("cap_reached"):
            print("  说明：今日已排满 2 项上限，这是下次进入时的建议。")
        elif nxt.get("minutes") and (today_info.get("remaining_minutes") or 0) < int(nxt["minutes"]):
            print(
                f"  说明：今日剩余 {today_info.get('remaining_minutes')} 分钟，不足下一项（约 {nxt['minutes']} 分钟）；"
                "这是下次进入时的建议。"
            )
        else:
            print("  说明：今日剩余时间够，但同一活动模板/技能今天已覆盖；这是下次进入时的建议。")
    print()
    sync = payload.get("sync") or {}
    print(
        "同步：written={} committed={} pushed={}（state={}）".format(
            "yes" if sync.get("written") else "no",
            "yes" if sync.get("committed") else "no",
            "yes" if sync.get("pushed") else "no",
            sync.get("state"),
        )
    )
    if not sync.get("remote"):
        print("  无远程：真实 GitHub 同步未验证；本地记录已保存。")
    if sync.get("diverged"):
        print(
            f"  ⚠ 本地与远程已分叉（ahead {sync.get('ahead')} / behind {sync.get('behind')}）；"
            "journal-only 冲突可用 sync --recover，状态文件冲突需人工保留一侧；不要 force push。"
        )
        if sync.get("unmerged"):
            print("  未合并文件：" + "、".join(sync.get("unmerged") or []))
    print(f"记录：journal {payload['journal'].get('events')} 条事件，最后一次 {payload['journal'].get('last_at')}")
    return EXIT_OK


def cmd_pause(argv: list[str]) -> int:
    opts, positional = parse_flags(argv, {"note": True})
    if positional:
        raise UsageError(f"pause 不认识的位置参数：{' '.join(positional)}")
    root = resolve_root(_PROJECT)
    store = load_store(root, _OFFLINE)
    day = tempo.prepare_day(store)
    print_day_notes(day)
    for line in tempo.acknowledge_pending_artifact(store):
        print(f"[产物] {line}")
    session = store.schedule.get("current_session")
    note = opts.get("note") or ""
    handoff = tempo.write_handoff(store, reason="pause", note=note)
    if session:
        activity = session.get("activity") or {}
        last_turn = store.schedule.get("last_turn") or {}
        completed = (
            last_turn.get("activity_id") == activity.get("activity_id")
            and last_turn.get("correct") is True
            and not last_turn.get("time_boxed")
        )
        if activity and not completed:
            store.schedule["resume_activity"] = {
                "activity_id": activity.get("activity_id"),
                "activity_type": activity.get("activity_type"),
                "skill": activity.get("skill"),
                "card_ids": list(activity.get("card_ids") or []),
                "minutes": activity.get("minutes"),
                "at": tempo.now_iso(),
            }
        tempo.append_session_note(
            store,
            session,
            [
                f"pause：{note or '结束本次学习'}",
                f"handoff：{handoff['path'].relative_to(store.root).as_posix()}",
            ],
        )
        tempo._mark_item_done(store, (session.get("activity") or {}).get("activity_id") or "")
        store.append(
            "pause",
            {
                "session": session["id"],
                "note": note,
                "handoff": str(handoff["path"].relative_to(store.root)).replace("\\", "/"),
            },
            dedupe_key=f"pause:{session['id']}:{tempo.count_session_turns(store, session['id'])}",
        )
        store.schedule["current_session"] = None
        store.touch("schedule")
    store.save()
    print(f"已保存交接：{handoff['path']}")
    print(handoff["text"].strip())
    report = sync_git(store)
    store.save()
    print()
    print_sync(report)
    print()
    nxt = handoff["summary"].get("next_step") or "下次 start 会按到期优先重新调度。"
    print(f"下次开始：{nxt}")
    print("恢复方式：新进程/new session 直接 python learn.py start（只依赖项目文件）。")
    if report.get("state") == "conflict":
        return EXIT_STATE
    return EXIT_OK


def cmd_switch(argv: list[str]) -> int:
    _, positional = parse_flags(argv, {})
    if len(positional) != 1:
        raise UsageError("switch 需要一个导师 id")
    target = positional[0].strip()
    root = resolve_root(_PROJECT)
    store = load_store(root, _OFFLINE)
    mentors = store.mentor_ids()
    if target not in mentors:
        raise UsageError(f"未知导师 {target!r}；可选：{', '.join(mentors)}")
    current_mentor = store.meta.get("mentor") or mentors[0]
    if target == current_mentor and not store.schedule.get("current_session"):
        store.meta["mentor_override"] = target
        store.touch("meta")
        store.save()
        print(f"当前导师已经是 {target}；已设为下次 start 的指定导师。")
        return EXIT_OK
    session = store.schedule.get("current_session")
    handoff = tempo.write_handoff(
        store,
        reason="switch",
        note=f"{current_mentor} → {target}",
        mentor_from=current_mentor,
        mentor_to=target,
    )
    store.append(
        "mentor_switch",
        {
            "from": current_mentor,
            "to": target,
            "session": (session or {}).get("id"),
            "reason": "learner-request",
            "handoff": str(handoff["path"].relative_to(store.root)).replace("\\", "/"),
        },
        dedupe_key=f"switch:{current_mentor}:{target}:{tempo.date_of(tempo.now_iso())}",
    )
    if session:
        tempo.append_session_note(store, session, [f"switch：{current_mentor} → {target}（活动在切换点结束）"])
        tempo._mark_item_done(store, (session.get("activity") or {}).get("activity_id") or "")
        store.schedule["current_session"] = None
    store.meta["mentor"] = target
    store.meta["mentor_override"] = target
    store.touch("schedule", "meta")
    store.save()
    print(f"已切换导师：{current_mentor} → {target}")
    print(f"交接已写：{handoff['path']}")
    print("保留：目标、技能等级、到期队列、卡片、本周块；不保留旧会话正文作为上下文（只读 handoff 摘要）。")
    print(f"下次 start 会优先由 {target} 带：若调度器选的活动类型不匹配，会换成 {target} 能带的等价活动；用掉或再次 switch 后清除。")
    return EXIT_OK


def cmd_due(argv: list[str]) -> int:
    opts, positional = parse_flags(argv, {"json": False})
    if positional:
        raise UsageError(f"due 不认识的位置参数：{' '.join(positional)}")
    root = resolve_root(_PROJECT)
    store = load_store(root, _OFFLINE)
    day = tempo.prepare_day(store)
    store.save()
    cards = store.due_cards()
    skills = store.due_skills()
    payload = {
        "date": tempo.today_str(),
        "simulated": clock.is_simulated(),
        "cards": [
            {
                "id": card["id"],
                "skill": card.get("skill"),
                "front": card.get("front"),
                "due_at": card.get("due_at"),
                "overdue_days": tempo.overdue_days(card.get("due_at")),
                "step": card.get("step"),
                "lapses": card.get("lapses"),
                "leech": bool(card.get("leech")),
            }
            for card in cards
        ],
        "skills": [
            {
                "id": skill["id"],
                "level": skill.get("level"),
                "due_at": skill.get("due_at"),
                "overdue_days": tempo.overdue_days(skill.get("due_at")),
                "lapses": skill.get("lapses"),
            }
            for skill in skills
        ],
        "session_cap": int(store.limits.get("due_cards_per_session", 3)),
        "backlog_cap": int(store.limits.get("backlog_cap", 12)),
    }
    if opts.get("json"):
        emit_json(payload)
        return EXIT_OK
    print_day_notes(day)
    print(f"今天到期（{payload['date']}{'，模拟时间' if payload['simulated'] else ''}）：")
    if not cards and not skills:
        print("  没有到期项。想学就 start，系统会排新内容或本周块。")
        return EXIT_OK
    rows = []
    for card in cards:
        rows.append(
            [
                "卡",
                card["id"],
                str(card.get("skill")),
                str(card.get("front") or "")[:34],
                tempo.date_of(card.get("due_at")),
                f"{tempo.overdue_days(card.get('due_at'))} 天",
                f"step {card.get('step')}",
                "leech" if card.get("leech") else "",
            ]
        )
    for skill in skills:
        rows.append(
            [
                "技能",
                skill["id"],
                str(skill.get("title") or "")[:20],
                "到期技能复测",
                tempo.date_of(skill.get("due_at")),
                f"{tempo.overdue_days(skill.get('due_at'))} 天",
                f"L{skill.get('level')}",
                "",
            ]
        )
    print(table(rows, ["类型", "id", "技能/标题", "内容", "到期", "逾期", "状态", "标记"]))
    print()
    print(f"本次最多清 {payload['session_cap']} 张卡（不会一次全推给你）；积压上限 {payload['backlog_cap']} 张，超出会折叠 +3 天。")
    print("要现在清到期：python learn.py review")
    return EXIT_OK


def cmd_plan(argv: list[str]) -> int:
    opts, positional = parse_flags(argv, {"json": False, "minutes": True})
    if positional:
        raise UsageError(f"plan 不认识的位置参数：{' '.join(positional)}")
    root = resolve_root(_PROJECT)
    store = load_store(root, _OFFLINE)
    day = tempo.prepare_day(store)
    min_activity = int(store.limits.get("min_activity", 5))
    remaining = store.today_remaining()
    exhausted = store.cap_reached() or remaining < min_activity
    if opts.get("minutes"):
        try:
            stated = int(opts["minutes"])
        except ValueError as exc:
            raise UsageError("--minutes 必须是整数") from exc
        budget = int(tempo._clamp_budget(stated, "--minutes").minutes)
        exhausted = False
        decision = tempo.plan_decision(store, minutes=budget, max_items=3)
    elif exhausted:
        budget = store.minutes_default()
        decision = tempo.plan_decision(store, minutes=budget, max_items=3, ignore_today=True)
    else:
        budget = remaining
        decision = tempo.plan_decision(store, minutes=budget, max_items=3)
        if decision.get("fallback"):
            exhausted = True
            budget = store.minutes_default()
            decision = tempo.plan_decision(store, minutes=budget, max_items=3, ignore_today=True)
    fallback = bool(decision.get("fallback"))
    if opts.get("json"):
        emit_json(
            {
                "date": tempo.today_str(),
                "budget": budget,
                "budget_total": store.today_budget(),
                "used": store.today_used(),
                "remaining": remaining,
                "for": "next_session" if exhausted else "today",
                "items": (
                    []
                    if fallback
                    else [
                        {
                            "activity_id": candidate["activity_id"],
                            "activity_type": candidate["activity_type"],
                            "skill": candidate.get("skill"),
                            "minutes": candidate.get("minutes"),
                            "tier": candidate.get("tier"),
                        }
                        for candidate in decision.get("plan") or []
                    ]
                ),
                "reason": (
                    "今天可用的活动模板/技能已覆盖或预算不足；下次 start 会先清到期卡。"
                    if fallback
                    else decision.get("reason_line")
                ),
                "done_today": sum(1 for item in store.today_items() if item.get("done")),
                "planned_today": len(store.today_items()),
            }
        )
        return EXIT_OK
    heading = "下次建议" if exhausted else "今天建议"
    print_day_notes(day)
    print(
        f"{heading}（{'具体可用' if exhausted else '可用'} {budget} 分钟，最多 3 项；只给今天，不显示欠账总数）"
        + (
            f"——今日已排 {len(store.today_items())}/{store.limits.get('max_items_per_session', 2)} 项、"
            f"剩 {remaining} 分钟"
            if exhausted
            else ""
        )
    )
    if not decision.get("plan") or decision.get("fallback"):
        if decision.get("fallback"):
            print("今天没有可排的新活动（同日模板/技能已覆盖或预算不足）；下次 start 会优先清到期卡。")
        else:
            print("  没有可排的活动；先 init 或在目标里补技能。")
        store.save()
        return EXIT_OK
    rows = []
    for index, candidate in enumerate(decision.get("plan") or [], 1):
        row = next((r for r in decision.get("rows") or [] if r["activity_id"] == candidate["activity_id"]), {})
        reason = row.get("reason", "")
        if exhausted and row.get("status") == "chosen":
            reason = "下次第一项"
        rows.append(
            [
                str(index),
                candidate["activity_type"],
                str(candidate.get("skill") or "-"),
                f"{candidate.get('minutes')} 分钟",
                f"{row.get('score', 0):.3f}",
                row.get("main_label", ""),
                reason,
            ]
        )
    print(table(rows, ["#", "活动", "技能", "时长", "分数", "主因子", "理由"]))
    print()
    if exhausted:
        print("今天已排满或预算不足：以上是下次进入后的建议，不是今天的欠账。")
    else:
        print(
            f"今天已排 {len(store.today_items())} 项（完成 {sum(1 for item in store.today_items() if item.get('done'))}）"
            f" · 预算 {store.today_budget()}，已用 {store.today_used()}，剩 {remaining}；"
            f"开始一个：python learn.py start --minutes {budget}"
        )
    store.save()
    return EXIT_OK


def cmd_review(argv: list[str]) -> int:
    minutes_arg = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--minutes" and index + 1 < len(argv):
            try:
                minutes_arg = int(argv[index + 1])
            except ValueError as exc:
                raise UsageError("--minutes 必须是整数") from exc
            index += 2
            continue
        raise UsageError(f"review 不认识参数 {arg}")
    root = resolve_root(_PROJECT)
    store = load_store(root, _OFFLINE)
    day = tempo.prepare_day(store)
    print_day_notes(day)
    for line in tempo.acknowledge_pending_artifact(store):
        print(f"[产物] {line}")
    min_activity = int(store.limits.get("min_activity", 5))
    if minutes_arg is not None:
        parsed = tempo._clamp_budget(minutes_arg, "--minutes")
        apply_budget(store, parsed, "review")
    budget = store.today_remaining()
    if budget < min_activity:
        print(
            f"今日预算已用完（预算 {store.today_budget()}，已用 {store.today_used()}，剩 {budget} 分钟），"
            "没有时间清到期卡。可以 pause 收尾，或用 review --minutes 5 追加 5 分钟。"
        )
        store.save()
        return EXIT_OK
    decision = tempo.plan_decision(store, minutes=budget, max_items=1, allow_repeat=True, force_due=True)
    chosen = decision.get("chosen") or {}
    if decision.get("fallback") or (chosen.get("source") not in ("due_card", "due_skill")):
        print(f"今天没有到期项（可用 {budget} 分钟）。")
        print("显式 review 只清到期组；想学新内容或本周块用 python learn.py start。")
        store.save()
        return EXIT_OK
    print(f"== 强制到期复习（可用 {budget} 分钟；今日预算 {store.today_budget()}，已用 {store.today_used()}）==")
    for line in recovery_lines(store):
        print(line)
    if time_note():
        print(time_note())
    print_decision(store, decision, budget, show_table=False)
    entry = begin_entry(store, budget, offline=_OFFLINE, forced="review", max_items=1, decision=decision)
    print()
    print(f"本次导师：{tempo.mentor_label(entry['activity'].get('mentor'))}   会话：{entry['session']['id']}")
    print(entry["opening"]["text"])
    print()
    print("把回答用 say 交给导师；完成后 pause 收尾。")
    store.save()
    return EXIT_OK


def cmd_skills(argv: list[str]) -> int:
    opts, positional = parse_flags(argv, {"json": False})
    if positional:
        raise UsageError(f"skills 不认识的位置参数：{' '.join(positional)}")
    root = resolve_root(_PROJECT)
    store = load_store(root, _OFFLINE)
    skills = store.skills.get("skills", [])
    cards = store.cards.get("cards", [])
    payload = {
        "skills": [
            {
                "id": skill["id"],
                "title": skill.get("title"),
                "level": int(skill.get("level") or 0),
                "level_reason": skill.get("level_reason"),
                "evidence_level": skill.get("evidence_level"),
                "due_at": skill.get("due_at"),
                "overdue_days": tempo.overdue_days(skill.get("due_at")),
                "lapses": int(skill.get("lapses") or 0),
                "wrong_tags": skill.get("wrong_tags") or [],
                "block_artifact": skill.get("block_artifact_path") or "",
                "delayed_retest_due_at": skill.get("delayed_retest_due_at"),
            }
            for skill in skills
        ],
        "cards": {
            "total": len(cards),
            "due": len(store.due_cards()),
            "leech": sum(1 for card in cards if card.get("leech")),
            "needs_rewrite": sum(1 for card in cards if card.get("needs_rewrite")),
        },
        "simulated": clock.is_simulated(),
    }
    if opts.get("json"):
        emit_json(payload)
        return EXIT_OK
    print("技能（平表：等级 / 到期 / 错误标签；没有先修关系）：")
    rows = []
    for skill in skills:
        rows.append(
            [
                skill["id"],
                f"L{skill.get('level')}",
                skill.get("evidence_level") or "-",
                tempo.date_of(skill.get("due_at")) or "-",
                f"{tempo.overdue_days(skill.get('due_at'))} 天",
                str(skill.get("lapses") or 0),
                "、".join(skill.get("wrong_tags") or [])[:30] or "-",
                "有产物" if skill.get("block_artifact_path") else "-",
            ]
        )
    print(table(rows, ["技能", "等级", "证据", "到期", "逾期", "lapses", "错误标签", "块产物"]))
    print()
    print(
        f"卡片：{payload['cards']['total']} 张 · 到期 {payload['cards']['due']} 张 · leech {payload['cards']['leech']} 张"
        f" · 待改写 {payload['cards']['needs_rewrite']} 张"
    )
    print("L3 规则：只能由“块产物 + ≥7 天延迟复测”授予；纯卡练习最高 L2。")
    return EXIT_OK


def cmd_sync(argv: list[str]) -> int:
    opts, positional = parse_flags(argv, {"message": True, "recover": False})
    if positional:
        raise UsageError(f"sync 不认识的位置参数：{' '.join(positional)}")
    root = resolve_root(_PROJECT)
    store = load_store(root, _OFFLINE)
    store.save(force=False)
    recover = bool(opts.get("recover"))
    report = sync_git(store, opts.get("message"), recover=recover)
    store.save()
    print_sync(report)
    if report.get("state") == "conflict":
        return EXIT_STATE
    return EXIT_OK


def cmd_doctor(argv: list[str]) -> int:
    _, positional = parse_flags(argv, {})
    if positional:
        raise UsageError(f"doctor 不认识的位置参数：{' '.join(positional)}")
    root = resolve_root(_PROJECT)
    store = load_store(root, _OFFLINE, reconcile=False)
    report = tempo.doctor_report(store)
    print(f"doctor · {store.root}")
    for check in report["checks"]:
        mark = {"ok": "ok  ", "warning": "warn", "problem": "FAIL"}.get(check["status"], check["status"])
        print(f"  [{mark}] {check['id']}: {check['detail']}")
    print()
    print(f"结论：{report['ok']} 项正常，{report['warnings']} 项警告，{report['problems']} 项问题。")
    if report["problems"]:
        print("修复建议：先看上面 FAIL 项；状态损坏会尝试从 .bak 恢复，去重索引损坏可用 status 触发重建。")
        return EXIT_STATE
    if report["simulated"]:
        print("注意：当前为模拟时钟（LEARNARK_NOW），只证明调度逻辑，不证明真实时间下的记忆保持。")
    return EXIT_OK


def cmd_export(argv: list[str]) -> int:
    opts, positional = parse_flags(argv, {"out": True})
    if positional:
        raise UsageError(f"export 不认识的位置参数：{' '.join(positional)}")
    out_path = opts.get("out")
    if not out_path:
        raise UsageError("export 需要 --out FILE")
    root = resolve_root(_PROJECT)
    store = load_store(root, _OFFLINE)
    text = tempo.build_export(store)
    target = Path(out_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    from learncore.fsutil import atomic_write_text

    atomic_write_text(target, text)
    print(f"已导出学习档案：{target.resolve()}（{len(text.encode('utf-8'))} 字节）")
    print("不含 API 密钥；离线/模拟记录已标注。")
    return EXIT_OK


def cmd_version(argv: list[str]) -> int:
    from learncore import CORE_VERSION

    print(f"{tempo.VARIANT_ID} {tempo.VARIANT_VERSION} · learncore {CORE_VERSION} · schema {tempo.SCHEMA_VERSION}")
    return EXIT_OK


COMMANDS = {
    "init": cmd_init,
    "start": cmd_start,
    "say": cmd_say,
    "status": cmd_status,
    "pause": cmd_pause,
    "switch": cmd_switch,
    "due": cmd_due,
    "plan": cmd_plan,
    "review": cmd_review,
    "skills": cmd_skills,
    "sync": cmd_sync,
    "doctor": cmd_doctor,
    "export": cmd_export,
    "version": cmd_version,
}

_PROJECT: str | None = None
_OFFLINE = False

#: Every command that touches an existing project is serialised with one advisory
#: lock. Per-document locks alone let two whole commands interleave their loads and
#: saves (a start could be overwritten by a concurrent say, losing today's item).
LOCKED_COMMANDS = set(COMMANDS) - {"init"}


def handler(argv: list[str]) -> int:
    global _PROJECT, _OFFLINE
    rest, project, offline = split_globals(argv)
    _PROJECT, _OFFLINE = project, offline
    if offline:
        os.environ["LEARNARK_LLM"] = "mock"
    if not rest or rest[0] in ("help", "-h", "--help"):
        print(USAGE)
        return EXIT_OK
    command, args = rest[0], rest[1:]
    if command not in COMMANDS:
        warn(f"learn: 未知命令 {command!r}")
        warn(USAGE)
        return EXIT_USAGE
    try:
        if command in LOCKED_COMMANDS:
            try:
                root: Path | None = resolve_root(_PROJECT)
            except LearnError:
                root = None
            if root is not None:
                with file_lock(root / ".learnark" / "project.lock", timeout=lock_timeout()):
                    return COMMANDS[command](args)
        return COMMANDS[command](args)
    except UsageError as exc:
        warn(f"learn: {exc}")
        warn("用 python learn.py help 查看命令。")
        return EXIT_USAGE
    except LockTimeout as exc:
        warn(
            "learn: 另一个进程正在写这个项目，等待锁超时；本次没有写入任何状态。"
            " 请稍后重试（同一项目的写命令是串行的）。"
        )
        warn(f"learn: lock detail: {exc}")
        return EXIT_STATE
    except StaleWrite as exc:
        warn(
            "learn: 状态已被另一个进程更新，本次写入已被拒绝（没有覆盖任何数据）。"
            " 请重跑同一命令，它会基于最新状态。"
        )
        warn(f"learn: stale write detail: {exc}")
        return EXIT_STATE


if __name__ == "__main__":
    raise SystemExit(cli_main(handler))
