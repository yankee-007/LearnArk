"""CLI commands for the Atelier variant.

Design rules enforced here (not in prompts):
* the runtime writes the handoff structure fields; mentors only propose content;
* only a planner ``status:"apply"`` plan change reaches ``studio.plan``;
* the examiner session is isolated and can never raise a level while helping;
* every mentor turn writes a ``context_manifest`` so context cost is auditable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from pathlib import Path

from learncore import clock, cli
from learncore.events import Journal, new_id
from learncore.fsutil import (
    LearnError,
    LockTimeout,
    StaleWrite,
    append_jsonl,
    atomic_write_text,
    file_lock,
    read_text,
    sha256_text,
    write_json,
)
from learncore.llm import LLMError, LLMUnavailable, MockLLM, from_env
from learncore.mentor import run_turn
from learncore.store import Document
from learncore.sync import GitSync, default_sync_message, ensure_git_identity

from . import SCHEMA_VERSION, VARIANT_ID, VARIANT_NAME, VARIANT_VERSION
from .assets import agents_text, readme_text
from .const import (
    CONTEXT_LIMIT,
    HANDOFF_LIMITS,
    HINT_KEYWORDS,
    MENTOR_DUTIES,
    MENTOR_LABELS,
    MENTOR_NAME_WORDS,
    MENTORS,
    NAMED_INTENT_WORDS,
    REVIEW_EVERY,
    format_weekly,
    format_weekly_scope,
)
from .context import build_context, system_prompt
from .evidence import (
    apply_evidence,
    apply_plan_update,
    approve_plan_change,
    collect_explicit_do_not_redo,
    detect_exam_request,
    detect_learner_do_not_redo,
    detect_repeats,
    detect_verdict_conflict,
    diagnosis_handoff_target,
    hint_requested,
    new_exam,
    record_do_not_redo,
    record_misconceptions,
    record_review,
    summarize_levels,
    update_notes,
    validate_update,
)
from .handoff import (
    check_all,
    compose_payload,
    latest_handoff_event,
    latest_handoff_payload,
    parse_file,
    update_state_after_handoff,
    validate_payload,
    write_handoff,
)
from .planning import build_plan, next_step, plan_hash
from .recovery import recover_with_preference
from .timeparse import estimate_minutes, parse_learner_time
from .state import (
    Paths,
    capability_doc,
    default_session,
    get_plan,
    journal,
    load_with_repair,
    notes_doc,
    open_paths,
    project_doc,
    project_lock,
    reviews_doc,
    session_doc,
    studio_doc,
)
from .templates import FIXTURE, TemplateError, parse_template

EXIT_USAGE = 2
EXIT_STATE = 3
EXIT_ENV = 4

SYNC_INCLUDE = [".learnark", "sessions", "artifacts", "AGENTS.md", "README.md", ".gitignore", ".gitattributes"]

HELP_LABELS = {0: "独立作答（无提示）", 1: "小提示", 2: "分步引导", 3: "基本代做", None: "未标注"}


class UsageError(LearnError):
    """Bad arguments that argparse cannot express (exit code 2)."""


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------
def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def _print_offline(mode: str) -> None:
    if mode == "mock":
        print("[离线脚本导师] （脚本回复，不是真实模型；仅用于跑通流程，不作为教学证据）")


def _load_all(paths: Paths) -> dict:
    project_document = project_doc(paths)
    studio_document = studio_doc(paths)
    capability_document = capability_doc(paths)
    reviews_document = reviews_doc(paths)
    session_document = session_doc(paths)
    project, project_note = load_with_repair(project_document)
    studio, studio_note = load_with_repair(studio_document)
    capability, cap_note = load_with_repair(capability_document)
    reviews, reviews_note = load_with_repair(reviews_document)
    session, session_note = load_with_repair(session_document)
    repairs = [note for note in (project_note, studio_note, cap_note, reviews_note, session_note) if note]
    return {
        "docs": {
            "project": project_document,
            "studio": studio_document,
            "capability": capability_document,
            "reviews": reviews_document,
            "session": session_document,
        },
        "project": project,
        "studio": studio,
        "capability": capability,
        "reviews": reviews,
        "session": session,
        "repairs": repairs,
    }


def _save(doc: Document, data: dict) -> dict:
    saved = doc.save(data, expected_version=int(data.get("version") or 0))
    # Keep the in-memory copy CAS-consistent so a second save in the same
    # command does not look like an outdated writer.
    data["version"] = saved.get("version", int(data.get("version") or 0) + 1)
    return saved


def _save_notes(paths: Paths, notes: dict, mentor: str) -> None:
    doc = notes_doc(paths, mentor)
    _save(doc, notes)


def _journal(paths: Paths) -> Journal:
    return journal(paths)


def _log_sync(paths: Paths, payload: dict) -> None:
    """Write the detailed report outside the journal (ignored by git)."""
    try:
        append_jsonl(paths.learnark / "sync-log.jsonl", {"at": clock.now_iso(), **payload})
    except OSError:
        pass


def _append(journal_obj: Journal, specs: list[dict], actor: str = "runtime") -> list[dict]:
    written = []
    for spec in specs:
        event = journal_obj.append(
            spec["kind"],
            spec.get("payload") or {},
            dedupe_key=spec.get("dedupe_key"),
            actor=spec.get("actor", actor),
        )
        if event:
            written.append(event)
    return written


def _resolve_llm(paths: Paths, offline: bool):
    if offline:
        os.environ["LEARNARK_LLM"] = "mock"
    mode = (os.environ.get("LEARNARK_LLM") or "auto").strip().lower()
    if not os.environ.get("LEARNARK_MOCK_SCRIPT") and mode == "mock" and FIXTURE.exists():
        os.environ["LEARNARK_MOCK_SCRIPT"] = str(FIXTURE)
    llm = from_env(usage_file=paths.usage_path)
    if isinstance(llm, MockLLM) and not offline:
        _warn("提示：没有可用的 API key，本次使用离线脚本导师（输出带 [离线脚本导师]）。")
    return llm


def _mode_of(llm) -> str:
    return "mock" if isinstance(llm, MockLLM) else "api"


def _mentor_list() -> str:
    return "、".join(f"{mentor}({MENTOR_LABELS[mentor]})" for mentor in MENTORS)


def _session_file(paths: Paths, mentor: str) -> Path:
    stamp = clock.stamp_for_filename()
    path = paths.sessions_dir / f"{stamp}-{mentor}.md"
    counter = 2
    while path.exists():
        path = paths.sessions_dir / f"{stamp}-{mentor}-{counter}.md"
        counter += 1
    return path


def _begin_session(paths: Paths, studio: dict, mentor: str, offline: bool, session: dict) -> dict:
    """Start a fresh session for ``mentor`` (ending any previous one)."""
    if session.get("session_id") and session.get("mentor") != mentor:
        session["ended_at"] = clock.now_iso()
    new = default_session()
    new["version"] = int(session.get("version") or 0)
    stamp = clock.now().strftime("%Y%m%dT%H%M%S")
    new.update(
        {
            "session_id": f"S-{stamp}-{mentor}",
            "mentor": mentor,
            "started_at": clock.now_iso(),
            "offline": offline,
            "path": str(_session_file(paths, mentor).relative_to(paths.root)),
        }
    )
    return new


def _render_session(paths: Paths, project: dict, session: dict) -> str:
    mentor = session.get("mentor") or "planner"
    started = (session.get("started_at") or clock.now_iso())[:16].replace("T", " ")
    lines = [
        f"# {started} — Atelier · {MENTOR_LABELS.get(mentor, mentor)}",
        f"- session: {session.get('session_id')}",
        f"- mentor: {mentor}",
        f"- learner: {(project.get('learner') or {}).get('name', 'learner')}  goal: {project.get('goal') or ''}",
        f"- offline: {'true（脚本导师，非真实教学证据）' if session.get('offline') else 'false'}",
        "",
    ]
    learner_turn = 0
    pending = None
    for turn in session.get("turns", []):
        if turn.get("role") == "learner":
            learner_turn += 1
            pending = turn
            lines += [f"## 第 {learner_turn} 轮", "", "### 学习者", "", turn.get("text", ""), ""]
        else:
            lines += [
                f"### 导师（help_level={turn.get('help_level')}, mode={turn.get('mode')}, chars={turn.get('context_chars')}）",
                "",
                turn.get("text", ""),
                "",
                "### 记录",
                f"- help_level: {turn.get('help_level')}",
                f"- attempt: {turn.get('attempt')}",
                f"- next: {turn.get('next')}",
                f"- events: {', '.join(turn.get('event_ids') or [])}",
                "",
            ]
    if session.get("ended_at"):
        lines += [f"## 会话结束 {session['ended_at']}", ""]
    return "\n".join(lines)


def _write_session(paths: Paths, project: dict, session: dict) -> None:
    rel = session.get("path")
    if not rel:
        return
    path = paths.root / rel
    atomic_write_text(path, _render_session(paths, project, session))


# ---------------------------------------------------------------------------
# named-mentor detection (deterministic keyword table)
# ---------------------------------------------------------------------------
def _mentions(text: str) -> list[tuple[str, str]]:
    low = (text or "").lower()
    found: list[tuple[str, str]] = []
    for mentor in MENTORS:
        for match in re.finditer(rf"(?<![a-z]){re.escape(mentor)}(?![a-z])", low):
            found.append((mentor, text[match.start() : match.end()]))
    for mentor, words in MENTOR_NAME_WORDS.items():
        for word in words:
            if word.lower() == mentor:
                continue
            if word and word in text:
                found.append((mentor, word))
    seen = set()
    unique = []
    for mentor, word in found:
        key = (mentor, word.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append((mentor, word))
    return unique


def _explicit_request(text: str, word: str) -> bool:
    """A switch requires a direct request, not a narrative mention."""
    low = text.lower()
    needle = word.lower()
    start = 0
    before_words = ("让", "找", "请", "叫", "换到", "切换到", "交给", "派", "用", "我要")
    after_words = ("来", "考", "讲", "带", "接", "帮我", "陪我", "上场", "接手", "考我", "考一次", "讲解")
    while True:
        index = low.find(needle, start)
        if index < 0:
            return False
        before = text[max(0, index - 8) : index].rstrip()
        after = text[index + len(needle) : index + len(needle) + 8].lstrip()
        if any(before.endswith(marker) for marker in before_words):
            return True
        if any(after.startswith(marker) for marker in after_words):
            return True
        start = index + 1


def detect_named_mentor(text: str, current: str) -> dict:
    """Return ``mentor`` only for a direct request; plain mentions never switch."""
    mentions = _mentions(text)
    if mentions:
        requested = [mentor for mentor, word in mentions if mentor != current and _explicit_request(text, word)]
        if len(set(requested)) > 1:
            return {"ambiguous": sorted(set(requested))}
        if requested:
            return {"mentor": requested[0]}
        return {"mentioned": sorted({mentor for mentor, _word in mentions})}
    intent = [
        mentor
        for mentor, words in NAMED_INTENT_WORDS.items()
        if any(word in text for word in words)
    ]
    if len(intent) > 1:
        return {"ambiguous": intent}
    if len(intent) == 1 and intent[0] != current:
        return {"mentor": intent[0]}
    return {}


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------
def cmd_init(args) -> int:
    template_name = args.template or "agent-dev"
    try:
        template = parse_template(template_name)
    except TemplateError as exc:
        raise UsageError(str(exc)) from exc
    root = Path(args.dir).expanduser().resolve() if args.dir else Path.cwd().resolve()
    root.mkdir(parents=True, exist_ok=True)
    paths = Paths(root)
    existing = (root / ".learnark" / "project.json").exists()
    paths.ensure_dirs()

    if existing:
        project_document = project_doc(paths)
        project = project_document.load()
        if not (root / "README.md").exists():
            atomic_write_text(root / "README.md", readme_text(project, get_plan(studio_doc(paths).load())))
        if not (root / "AGENTS.md").exists():
            atomic_write_text(root / "AGENTS.md", agents_text(project))
        print(f"已初始化，复用现有项目：{root}")
        print("下一步：learn.cmd start")
        return 0

    slug = (args.name or root.name or "learnark").strip().replace(" ", "-")
    # --minutes-per-week is minutes; template defaults are expressed in hours.
    minutes = args.minutes_per_week if args.minutes_per_week and args.minutes_per_week > 0 else int(template["minutes_per_week_default"]) * 60
    project = {
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "goal": args.goal or template["goal_default"],
        "template": template["name"],
        "template_title": template["title"],
        "constraints": template["constraints"],
        "learner": {
            "name": "learner",
            "minutes_per_week": int(minutes),
            "minutes_unit": "minutes",
            "self_reports": [],
            "profile": "自述经历只作线索，能力由行为证据校准。",
        },
        "template_modules": template["modules"],
        "diagnostics": template["probes"],
        "variant": {"id": VARIANT_ID, "version": VARIANT_VERSION, "core_version": _core_version()},
        "created_at": clock.now_iso(),
        "updated_at": clock.now_iso(),
    }
    plan = build_plan(template, minutes)
    studio = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": clock.now_iso(),
        "current_mentor": template["default_mentor"],
        "plan": plan,
        "plan_changes": [],
        "mentors": {
            mentor: {
                "last_active": None,
                "notes_path": f".learnark/state/mentors/{mentor}.json",
                "open_loops": [],
                "turns": 0,
                "last_handoff_proposal": None,
            }
            for mentor in MENTORS
        },
        "last_handoff_id": None,
        "review_counter": {"since_review": 0, "every": REVIEW_EVERY},
        "dedupe": {
            "activity_ids": {},
            "analogy_hashes": {},
            # Template anti-patterns are guidance, not this learner's statements.
            # do_not_redo starts empty and only records explicit statements.
            "do_not_redo": [],
        },
        "flags": {"plan_state": "seeded", "force_new_representation": None, "exam_reask": False},
    }
    capability = {
        "schema_version": SCHEMA_VERSION,
        "nodes": [
            {
                "id": module["module_id"],
                "label": module["title"] or module["module_id"],
                "level": 0,
                "evidence": [],
                "last_fail": None,
                "review_due": None,
                "decay_reason": None,
            }
            for module in template["modules"]
        ],
        "self_reports": [],
        "pending_exam": None,
    }
    reviews = {"schema_version": SCHEMA_VERSION, "reviews": []}

    project_document = project_doc(paths)
    _save(project_document, project)
    _save(studio_doc(paths), studio)
    _save(capability_doc(paths), capability)
    _save(reviews_doc(paths), reviews)
    _save(session_doc(paths), default_session())
    for mentor in MENTORS:
        _save(notes_doc(paths, mentor), {"schema_version": SCHEMA_VERSION, "mentor": mentor, "notes": [], "taught": [], "avoid": [], "conclusions": [], "style": "", "next_suggestion": "", "turns": 0})

    atomic_write_text(root / "README.md", readme_text(project, plan))
    atomic_write_text(root / "AGENTS.md", agents_text(project))

    jour = _journal(paths)
    jour.append(
        "project_created",
        {
            "slug": slug,
            "goal": project["goal"],
            "template": template["name"],
            "minutes_per_week": int(minutes),
            "variant": VARIANT_ID,
        },
        dedupe_key=f"project:{slug}",
    )
    jour.append(
        "plan_created",
        {
            "plan_id": plan["plan_id"],
            "version": plan["version"],
            "steps": len(plan["steps"]),
            "authority": "planner",
            "template": template["name"],
            "hash": plan["hash"],
        },
        dedupe_key=f"plan_created:{slug}:{plan['version']}",
    )

    git = GitSync(root, include=SYNC_INCLUDE)
    if git.available():
        try:
            if git.is_repo() and git.repo_root().resolve() != root.resolve():
                # Keep each learning project an independent repository even when
                # the user initialises it inside a larger repo.
                git.run("init", "-q")
                _warn("提示：项目位于另一个 git 仓库内，已为它单独初始化一个仓库，避免把学习记录混进父仓库。")
            git.ensure_repository()
            ensure_git_identity(root)
            git.commit(f"learn({slug}): initial project skeleton")
        except LearnError as exc:
            _warn(f"提示：git 初始化未完成（{exc}）；学习记录已写入磁盘。")
    else:
        _warn("提示：未安装 git，记录仍会写入磁盘，但无法本地提交/推送。")

    print(f"已创建 Atelier 学习项目：{root}")
    print(f"目标：{project['goal']}")
    print(f"模板：{template['title']}（{template['name']}） · 每周约 {format_weekly(minutes)} · 计划 {plan['plan_id']} v{plan['version']}（{len(plan['steps'])} 步）")
    print("")
    print("下一步：")
    print("  1) learn.cmd start          # 看计划、上次停在哪、该找哪位导师")
    print('  2) learn.cmd say "..."      # 开始对话')
    print("  没有 API key 时加 --offline 走脚本导师（会明确标注）。")
    return 0


def _core_version() -> str:
    try:
        from learncore import CORE_VERSION

        return CORE_VERSION
    except Exception:  # pragma: no cover
        return "unknown"


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------
def _open_session_on_start(paths: Paths, project: dict, studio: dict, session: dict, offline: bool) -> tuple[dict, bool]:
    """Open a session pointer at most once; never write handoffs or studio state."""
    if session.get("session_id") and not session.get("ended_at"):
        return session, False
    mentor = studio.get("current_mentor") or "planner"
    fresh = _begin_session(paths, studio, mentor, offline, session)
    _save(session_doc(paths), fresh)
    _journal(paths).append(
        "session_opened",
        {"session_id": fresh.get("session_id"), "mentor": mentor, "at": fresh.get("started_at")},
        dedupe_key=f"session_opened:{fresh.get('session_id')}",
    )
    git = GitSync(paths.root, include=SYNC_INCLUDE)
    if git.available() and git.is_repo():
        try:
            ensure_git_identity(paths.root)
            git.commit(f"learn({project.get('slug') or 'learnark'}): open session")
        except LearnError as exc:
            _warn(f"提示：打开会话已写入文件，但 git 提交失败：{exc}")
    return fresh, True


def cmd_start(args) -> int:
    paths = open_paths(args.project)
    state = _load_all(paths)
    for note in state["repairs"]:
        _warn(f"提示：{note}")
    project = state["project"]
    studio = state["studio"]
    capability = state["capability"]
    session = state["session"]

    if not get_plan(studio).get("steps"):
        print("这个项目还没有计划。先运行：learn.cmd init --goal \"...\"")
        return EXIT_STATE

    session, _opened = _open_session_on_start(paths, project, studio, session, args.offline)
    if args.minutes:
        session["budget_minutes"] = int(args.minutes)
        session.setdefault("started_at", clock.now_iso())
        _save(session_doc(paths), session)
        git_session = GitSync(paths.root, include=SYNC_INCLUDE)
        if git_session.available() and git_session.is_repo():
            try:
                ensure_git_identity(paths.root)
                git_session.commit(f"learn({project.get('slug') or 'learnark'}): set session budget")
            except LearnError:
                pass

    plan = get_plan(studio)
    objective = plan.get("current_objective") or {}
    handoff = latest_handoff_event(paths)
    payload = handoff.get("payload") if handoff else None
    decision = next_step(studio, capability)
    minutes = args.minutes
    total = len([step for step in plan.get("steps", []) if step.get("status") != "removed"])
    done = len([step for step in plan.get("steps", []) if step.get("status") == "done"])
    current_mentor = studio.get("current_mentor") or "planner"

    print(f"== {VARIANT_NAME} · {project.get('template_title') or project.get('template')} ==")
    print(f"目标：{project.get('goal') or '（未填写）'} · 每周约 {format_weekly_scope(project.get('learner') or {})}")
    print("")
    print(f"计划：{plan.get('plan_id')} v{plan.get('version')}（权威：planner） · 进度 {done}/{total} 步")
    objective_line = f"  · 当前目标：{objective.get('id')} {objective.get('text')}"
    if minutes:
        objective_line += f"（本次按 {minutes} 分钟裁剪，只做一个活动）"
    print(objective_line)
    session_clock = _session_clock(session)
    if session_clock["budget"]:
        print(f"  · 本次剩余 {session_clock['remaining']} 分钟（已用 {session_clock['elapsed']}/{session_clock['budget']}，还有 {session_clock['remaining']} 分钟可用）")
    print("")
    if payload:
        age = clock.human_age(payload.get("created_at"))
        open_loops = [loop for loop in payload.get("open_loops") or [] if loop.get("status") != "closed"]
        blocking = [loop for loop in open_loops if loop.get("blocking")]
        print(
            f"上次停在哪：{payload.get('handoff_id')} {payload.get('from')}→{payload.get('to')}（{age}）"
            f" · 未决 {len(open_loops)} 条" + (f"，其中阻塞 {len(blocking)} 条" if blocking else "")
        )
        print(f"  · 交接说的下一步：{payload.get('next')}")
    elif session.get("turns"):
        print(f"上次停在哪：会话 {session.get('session_id')}（{clock.human_age(session.get('started_at'))}，{len(session.get('turns', [])) // 2} 轮）")
    else:
        print("上次停在哪：尚无学习记录（首次进入）")

    print("")
    print(f"这一轮该找谁：{MENTOR_LABELS.get(decision['mentor'], decision['mentor'])}")
    print(f"  · 为什么：{decision['reason']}")
    if decision.get("action"):
        print(f"  · 下一步：{decision['action']}（约 {decision.get('est_minutes', 20)} 分钟）")
    if capability.get("pending_exam") and decision["mentor"] == "examiner":
        pending = capability["pending_exam"]
        questions = pending.get("questions") or []
        index = int(pending.get("current_index") or 0)
        current_q = questions[index] if index < len(questions) else pending.get("activity_id")
        print(f"  · 考核未完成：还剩 {len(pending.get('remaining_questions') or questions)} 题；下一题 {current_q}（直接 examine 继续）")
    elif decision["mentor"] != current_mentor:
        print(f"  · 当前会话导师是 {current_mentor}；切换会先写一份交接：learn.cmd switch {decision['mentor']}")
    elif decision["mentor"] == "planner" and (studio.get("flags") or {}).get("plan_state") in ("seeded", "diagnosing"):
        probes = project.get("diagnostics") or []
        asked = (studio.get("flags") or {}).get("probes_asked") or []
        remaining = [probe for probe in probes if probe.get("probe_id") not in asked]
        print(f"  · 首次诊断（至少问 2 道；还需 {max(0, 2 - len(asked))} 道，答不出具体动作一律记 self_report）：")
        for probe in remaining[:3]:
            print(f"    - {probe.get('probe_id')}：{probe.get('question')}（诊断题，不提供参考答案）")
    print("")
    print("输入：")
    if capability.get("pending_exam") and decision["mentor"] == "examiner":
        print("  learn.cmd examine")
    elif decision["mentor"] == current_mentor:
        print('  learn.cmd say "..."')
    else:
        print(f"  learn.cmd switch {decision['mentor']}   # 然后 say")
    if decision["mentor"] == "examiner" and decision.get("kind") != "pending_exam":
        print("  或直接：learn.cmd examine")
    print("")
    if (os.environ.get("LEARNARK_LLM") or "").lower() == "mock" or args.offline:
        print("模式：离线脚本导师（输出带 [离线脚本导师]，仅证明流程，不代表教学质量）")
    return 0


# ---------------------------------------------------------------------------
# turn execution
# ---------------------------------------------------------------------------
def _parse_mentor_turn(turn, mentor: str) -> tuple[dict, list[str]]:
    update = turn.updates
    problems: list[str] = []
    if turn.update_error:
        problems.append(turn.update_error)
    if update is None and not turn.update_error:
        problems.append("missing learn-update machine block")
    if isinstance(update, dict):
        problems.extend(validate_update(update, mentor))
    return (update if isinstance(update, dict) and not problems else {}), problems


def perform_turn(
    paths: Paths,
    project: dict,
    studio: dict,
    capability: dict,
    session: dict,
    llm,
    mentor: str,
    text: str,
    offline: bool,
    attempt_id: str = "",
) -> dict:
    jour = _journal(paths)
    session_id = session.get("session_id") or "S-unknown"
    turn_index = int(session.get("turn_index") or 0) + 1
    text_sha = sha256_text(text)[:16]
    payload_handoff = latest_handoff_payload(paths)
    context = build_context(paths, project, studio, capability, mentor, payload_handoff)
    system = system_prompt(mentor)
    flags = studio.get("flags") or {}
    force = flags.get("force_new_representation") or {}
    if force.get("mentor") == mentor:
        system += (
            "\n\n## 运行时提醒\n上一轮命中了 do_not_redo（"
            + str(force.get("activity_id") or force.get("analogy") or "")
            + "）。本轮必须换一个表征或换一道题，不要原样重复。"
        )
    if flags.get("exam_reask") and mentor == "examiner":
        system += "\n\n## 运行时提醒\n上一考核回合出现了 help_level>0，判定作废。本轮只记录学习者自己的话，不要提示，不要计入证据。"

    transcript = [turn for turn in session.get("turns", []) if turn.get("text")]
    first_turn = run_turn(llm, system=system, context=context["text"], user=text, transcript=transcript, max_tokens=1500)
    turn = first_turn
    update, problems = _parse_mentor_turn(first_turn, mentor)
    first_raw = first_turn.raw or ""
    retried = False
    if problems:
        retried = True
        # One silent repair attempt: ask only for a well-formed machine block,
        # then record the retry.  The learner never sees "机器块" jargon.
        repair_note = (
            "\n\n## 机器块修复（只补格式）\n"
            "你上一条回复没有给出可解析的 learn-update 机器块。请保持教学内容，"
            "在回复最末尾补一个合法机器块；不要解释这条提醒。"
        )
        second_turn = run_turn(
            llm,
            system=system + repair_note,
            context=context["text"],
            user=text,
            transcript=transcript,
            max_tokens=1500,
        )
        second_update, second_problems = _parse_mentor_turn(second_turn, mentor)
        jour.append(
            "mentor_update_retried",
            {
                "mentor": mentor,
                "session_id": session_id,
                "turn": turn_index,
                "attempt_id": attempt_id,
                "first_reasons": problems[:3],
                "first_raw_sha256": sha256_text(first_raw),
                "repaired": not second_problems,
            },
            dedupe_key=f"retry:{session_id}:{turn_index}:{attempt_id}",
        )
        if not second_problems:
            turn = second_turn
            update = second_update
            problems = []
        else:
            # Keep the mentor's real first reply; only the machine block is lost.
            turn = first_turn if (first_turn.text or "").strip() else second_turn
            update = {}
            problems = second_problems
    mode = turn.mode or _mode_of(llm)
    synthetic = mode == "mock"
    visible = (turn.text or "").strip()
    recorded_attempt = update.get("attempt")
    if mentor != "examiner" and isinstance(recorded_attempt, dict):
        # Practice mentors may claim correctness, but the record stores it as a
        # claim; only examiner sessions can set correct=true.
        recorded_attempt = dict(recorded_attempt)
        recorded_attempt["claimed_correct"] = recorded_attempt.get("correct")
        recorded_attempt["correct"] = None

    turn_event = jour.append(
        "mentor_turn",
        {
            "mentor": mentor,
            "session_id": session_id,
            "turn": turn_index,
            "attempt_id": attempt_id,
            "text_sha": text_sha,
            "help_level": update.get("help_level"),
            "attempt": recorded_attempt,
            "next": update.get("next"),
            "mode": mode,
            "model": turn.model,
            "synthetic": synthetic,
            "chars": context["chars"],
            "verdict": bool(update.get("verdict")),
            "plan_change": (update.get("plan_change") or {}).get("status") if isinstance(update.get("plan_change"), dict) else None,
            "handoff_proposal": bool(update.get("handoff")),
            "invalid": bool(problems),
        },
        dedupe_key=f"turn:{session_id}:{turn_index}:{text_sha}",
    )
    turn_event_id = (turn_event or {}).get("id", f"ev-missing-{turn_index}")
    jour.append(
        "context_manifest",
        {
            "mentor": mentor,
            "chars": context["chars"],
            "sources": context["sources"],
            "excluded": context["excluded"],
            "handoff_id": context["handoff_id"],
            "session_id": session_id,
            "turn": turn_index,
            "synthetic": synthetic,
        },
        dedupe_key=f"ctx:{session_id}:{turn_index}",
    )
    if problems:
        jour.append(
            "mentor_update_invalid",
            {
                "mentor": mentor,
                "raw_sha256": sha256_text(turn.raw or ""),
                "first_raw_sha256": sha256_text(first_raw),
                "problems": problems,
                "retried": retried,
                "mode": mode,
                "synthetic": synthetic,
            },
            dedupe_key=f"invalid:{session_id}:{turn_index}:{sha256_text(turn.raw or '')[:12]}",
        )

    warnings: list[str] = []
    if problems:
        warnings.append("本轮没有形成可记录的证据（不影响继续学习）")

    if mentor == "examiner" and hint_requested(text):
        jour.append(
            "hint_refused",
            {"mentor": mentor, "session_id": session_id, "turn": turn_index, "text_sha": sha256_text(text)[:16]},
            dedupe_key=f"hint:{session_id}:{turn_index}",
        )
        warnings.append("考核回合不给提示；本次判定只依据你自己的原话。")

    plan_events: list[dict] = []
    evidence_events: list[dict] = []
    repeat_events: list[dict] = []
    misconception_events: list[dict] = []
    summary: dict = {}
    duplicate_attempt = False
    verdict_conflict = False
    diagnosis_target = None
    attempt = update.get("attempt") or {}
    activity = attempt.get("activity_id") if isinstance(attempt, dict) else None
    if update and isinstance(update.get("handoff"), dict):
        proposal = dict(update["handoff"])
        proposal["at"] = clock.now_iso()
        studio.setdefault("mentors", {}).setdefault(mentor, {})["last_handoff_proposal"] = proposal
    if update:
        repeat_events = detect_repeats(studio, mentor, update)
        plan_update = apply_plan_update(studio, update, mentor)
        plan_events = plan_update["events"]
        verdict_conflict = detect_verdict_conflict(visible, update, mentor)
        if verdict_conflict:
            jour.append(
                "mentor_verdict_conflict",
                {
                    "mentor": mentor,
                    "activity_id": activity,
                    "detail": "导师文本含纠正，但机器块把尝试判为 correct；按未通过/无证据处理",
                    "text_excerpt": visible[:160],
                },
                dedupe_key=f"conflict:{session_id}:{turn_index}",
            )
            warnings.append("导师的判定与正文纠正冲突，本轮不计为答对。")
        if activity:
            attempt_key = f"attempt:{activity}:{sha256_text(text)[:16]}"
            duplicate_attempt = jour.has(attempt_key)
            if duplicate_attempt:
                jour.append(
                    "attempt_duplicate",
                    {"mentor": mentor, "activity_id": activity, "session_id": session_id},
                    dedupe_key=f"duplicate:{attempt_key}",
                )
                warnings.append("同一答案已记录过，本次不重复计分。")
        if not duplicate_attempt:
            evidence = apply_evidence(
                paths=paths,
                project=project,
                plan=studio.setdefault("plan", {}),
                studio=studio,
                capability=capability,
                mentor=mentor,
                update=update,
                turn_event_id=turn_event_id,
                learner_text=text,
                mode=mode,
                verdict_conflict=verdict_conflict,
            )
            evidence_events = evidence["events"]
            summary = evidence["summary"]
            for index, spec in enumerate(evidence_events):
                if spec["kind"] in ("attempt", "practice_attempt") and activity:
                    spec["dedupe_key"] = f"attempt:{activity}:{sha256_text(text)[:16]}"
                else:
                    spec["dedupe_key"] = f"{spec['kind']}:{session_id}:{turn_index}:{index}"
            misconception_events, _nodes = record_misconceptions(
                project, studio["plan"], capability, mentor, update, visible, turn_event_id
            )
            if misconception_events:
                jour.append(
                    "misconception_observed_batch",
                    {
                        "mentor": mentor,
                        "nodes": [event["payload"]["node"] for event in misconception_events],
                        "count": len(misconception_events),
                    },
                    dedupe_key=f"misconceptions:{session_id}:{turn_index}",
                )
            if mentor in ("coach", "concept") and not capability.get("pending_exam") and detect_exam_request(visible, update):
                exam = new_exam(project, studio["plan"], capability, requested_by=mentor, activity=activity)
                jour.append(
                    "exam_requested",
                    {
                        "mentor": mentor,
                        "node_id": exam["node_id"],
                        "activity_id": exam["activity_id"],
                        "status": exam["status"],
                    },
                    dedupe_key=f"exam_requested:{session_id}:{turn_index}",
                )
                summary["exam_requested"] = exam
            if mentor == "planner" and misconception_events and not (isinstance(update.get("handoff"), dict) and update["handoff"].get("auto")):
                diagnosis_target = diagnosis_handoff_target(visible, update)
    else:
        plan_update = {"summary": {}}

    _append(jour, plan_events + repeat_events + evidence_events + misconception_events)
    promised_loop = _record_promised_next(
        studio,
        capability,
        update,
        visible,
        mentor,
        jour,
        attempt_id=attempt_id,
        session_id=session_id,
        turn=turn_index,
        plan_applied=(plan_update.get("summary") or {}).get("status") == "applied",
    )

    explicit_dnr = [(item, "learner") for item in detect_learner_do_not_redo(text)]
    if update:
        explicit_dnr += collect_explicit_do_not_redo(update)
    if explicit_dnr:
        recorded = record_do_not_redo(studio, mentor, explicit_dnr, event_id=turn_event_id)
        if recorded:
            jour.append(
                "do_not_redo_recorded",
                {
                    "mentor": mentor,
                    "items": [entry["text"] for entry in recorded],
                    "sources": [entry["source"] for entry in recorded],
                },
                dedupe_key=f"dnr:{session_id}:{turn_index}",
            )

    if "examiner_help" in (summary.get("violations") or []):
        warnings.append("考核回合出现 help_level>0：本轮判定作废，请重新作答（只记录你的原话，不计证据）。")

    notes = state_notes = load_with_repair(notes_doc(paths, mentor))[0]
    notes = update_notes(notes, mentor, update, turn=turn_index, synthetic=synthetic)
    _save(notes_doc(paths, mentor), notes)

    reviews = load_with_repair(reviews_doc(paths))[0]
    review_entry = {}
    if update.get("review_note") is not None and mentor == "reviewer":
        review_entry = record_review(reviews, studio, update, mentor=mentor, session_id=session_id, turn_event_id=turn_event_id)
        if review_entry:
            _save(reviews_doc(paths), reviews)
            jour.append(
                "review",
                {
                    "review_id": review_entry["review_id"],
                    "topic": (update.get("review_note") or {}).get("topic_id"),
                    "kind": (update.get("review_note") or {}).get("kind"),
                    "confidence": (update.get("review_note") or {}).get("confidence"),
                    "mentor": mentor,
                },
                dedupe_key=f"review:{review_entry['review_id']}",
            )

    studio.setdefault("mentors", {}).setdefault(mentor, {})
    studio["mentors"][mentor]["turns"] = int(studio["mentors"][mentor].get("turns") or 0) + 1
    studio["mentors"][mentor]["last_active"] = clock.now_iso()
    studio["updated_at"] = clock.now_iso()
    if mentor == "planner":
        asked = _probe_coverage(studio, project, visible)
        declared = isinstance(update.get("handoff"), dict) or (update.get("plan_change") or {}).get("op") not in (None, "none")
        studio.setdefault("flags", {})["plan_state"] = "confirmed" if (len(asked) >= 2 or declared) else "diagnosing"
        jour.append(
            "probe_coverage",
            {"asked": asked, "plan_state": studio["flags"]["plan_state"], "declared_plan": bool(declared)},
            dedupe_key=f"probes:{session_id}:{turn_index}",
        )
    counter = studio.setdefault("review_counter", {"since_review": 0, "every": REVIEW_EVERY})
    counter["since_review"] = int(counter.get("since_review") or 0) + 1
    if mentor == "reviewer" and review_entry:
        counter["since_review"] = 0
    if force.get("mentor") == mentor:
        studio["flags"]["force_new_representation"] = None
    if mentor == "examiner" and not warnings:
        studio["flags"]["exam_reask"] = False
    studio["flags"]["last_next_step"] = next_step(studio, capability)
    runtime_next = studio["flags"]["last_next_step"]
    # Do NOT re-stamp plan.hash here: a silent external edit must stay visible to
    # `doctor --plan` until a real plan_change records the before/after hashes.

    session["turns"].append({"role": "learner", "text": text, "at": clock.now_iso(), "text_sha": text_sha, "attempt_id": attempt_id})
    session["turns"].append(
        {
            "role": "mentor",
            "text": visible,
            "at": clock.now_iso(),
            "text_sha": text_sha,
            "attempt_id": attempt_id,
            "mentor": mentor,
            "help_level": update.get("help_level"),
            "attempt": recorded_attempt,
            "next": update.get("next"),
            "mode": mode,
            "context_chars": context["chars"],
            "event_ids": [turn_event_id],
            "invalid": bool(problems),
        }
    )
    session["turn_index"] = turn_index
    session["offline"] = synthetic
    _write_session(paths, project, session)

    return {
        "visible": visible,
        "mode": mode,
        "synthetic": synthetic,
        "update": update,
        "problems": problems,
        "warnings": warnings,
        "summary": summary,
        "context": context,
        "turn_index": turn_index,
        "event_id": turn_event_id,
        "duplicate": duplicate_attempt,
        "review": review_entry,
        "plan_summary": plan_update.get("summary") or {},
        "verdict_conflict": verdict_conflict,
        "evidence_conflict": verdict_conflict,
        "diagnosis_target": diagnosis_target,
        "exam_requested": summary.get("exam_requested"),
        "promised_loop": promised_loop,
        "next": runtime_next,
        "session": session,
    }


# ---------------------------------------------------------------------------
# say
# ---------------------------------------------------------------------------
def _session_has_turn(session: dict, text: str) -> bool:
    if (session or {}).get("ended_at"):
        return False
    sha = sha256_text(text)[:16]
    return any(
        turn.get("role") == "mentor" and turn.get("text_sha") == sha
        for turn in (session or {}).get("turns", [])
    )


def _record_handoff_rejected(jour: Journal, *, attempt_id: str, source: str, from_mentor: str, target: str, reason: str, missing=None) -> None:
    jour.append(
        "handoff_rejected",
        {
            "attempt_id": attempt_id,
            "source": source,
            "from": from_mentor,
            "to": target,
            "reason": reason,
            "missing": missing or [],
        },
        dedupe_key=f"handoff_rejected:{attempt_id}:{source}",
    )


def _apply_learner_time(paths: Paths, project: dict, studio: dict, session: dict, info: dict, jour: Journal, attempt_id: str) -> str:
    """Persist explicit learner time into project/plan/session (v0.2.4)."""
    if not info:
        return ""
    changed = []
    learner = project.setdefault("learner", {})
    plan = studio.setdefault("plan", {})
    if info.get("weekly_minutes"):
        minutes = int(info["weekly_minutes"])
        learner["minutes_per_week"] = minutes
        learner["minutes_unit"] = "minutes"
        if info.get("weekly_range_minutes"):
            learner["weekly_range_minutes"] = list(info["weekly_range_minutes"])
            plan["weekly_range_minutes"] = list(info["weekly_range_minutes"])
        plan["minutes_per_week"] = minutes
        plan["updated_at"] = clock.now_iso()
        try:
            plan["hash"] = plan_hash(plan)
        except Exception:
            pass
        changed.append(f"每周 {format_weekly_scope(learner)}（计划按 {format_weekly(minutes)}/周）")
    if info.get("today_minutes"):
        session["budget_minutes"] = int(info["today_minutes"])
        if not session.get("started_at"):
            session["started_at"] = clock.now_iso()
        changed.append(f"今天 {session['budget_minutes']} 分钟")
    if not changed:
        return ""
    _save(project_doc(paths), project)
    _save(studio_doc(paths), studio)
    _save(session_doc(paths), session)
    jour.append(
        "learner_time_recorded",
        {
            "attempt_id": attempt_id,
            "weekly_minutes": learner.get("minutes_per_week"),
            "weekly_range_minutes": learner.get("weekly_range_minutes"),
            "today_minutes": session.get("budget_minutes"),
        },
        dedupe_key=f"learner_time:{attempt_id}",
    )
    return "已记录你的时间：" + "；".join(changed) + "。"


def _session_clock(session: dict) -> dict:
    budget = session.get("budget_minutes")
    started = session.get("started_at")
    if not budget or not started:
        return {"budget": None, "elapsed": None, "remaining": None}
    try:
        elapsed = max(0.0, clock.days_between(started, clock.now_iso()) * 24 * 60)
    except Exception:
        return {"budget": int(budget), "elapsed": None, "remaining": None}
    return {
        "budget": int(budget),
        "elapsed": int(round(elapsed)),
        "remaining": max(0, int(round(budget - elapsed))),
    }


_PROBE_HINTS = {
    "probe-d1": ("工具调用失败", "第一步", "原始返回", "日志"),
    "probe-d2": ("检索", "记忆"),
    "probe-d3": ("改好了", "变好了", "用例", "回放"),
    "probe-e1": ("主题行", "英文主题"),
    "probe-e2": ("样例邮件", "最该先删", "删"),
}


def _probe_coverage(studio: dict, project: dict, text: str) -> list[str]:
    flags = studio.setdefault("flags", {})
    asked = [item for item in (flags.get("probes_asked") or []) if item]
    for probe in project.get("diagnostics") or []:
        probe_id = str(probe.get("probe_id") or "")
        question = str(probe.get("question") or "")
        if not probe_id or probe_id in asked:
            continue
        if probe_id and probe_id in text:
            asked.append(probe_id)
            continue
        if question and question in text:
            asked.append(probe_id)
            continue
        if any(hint in text for hint in _PROBE_HINTS.get(probe_id, ())):
            asked.append(probe_id)
    flags["probes_asked"] = asked[-6:]
    return flags["probes_asked"]


def _record_promised_next(
    studio: dict,
    capability: dict,
    update: dict,
    visible: str,
    current: str,
    jour: Journal,
    *,
    attempt_id: str,
    session_id: str,
    turn: int,
    plan_applied: bool,
) -> dict | None:
    """Turn a mentor-promised next activity into a blocking open loop (v0.2.4)."""
    if capability.get("pending_exam") or plan_applied:
        return None
    promised = str(update.get("next") or "").strip()
    handoff = update.get("handoff") if isinstance(update.get("handoff"), dict) else {}
    promised = (promised + " " + str(handoff.get("next") or "")).strip()
    if not promised or not any(marker in promised for marker in ("下一轮", "下一题", "明天", "十分钟", "分钟")):
        return None
    target = None
    for mentor in MENTORS:
        if mentor in promised.lower() or MENTOR_LABELS.get(mentor, "###").split()[0] in promised:
            target = mentor
            break
    if not target or target == "examiner":
        return None
    activity = None
    match = re.search(r"\b((?:w\d|em)-[a-z0-9-]+)\b", promised, re.IGNORECASE)
    if match:
        activity = match.group(1)
    est = estimate_minutes(promised, 10)
    text = promised[:120]
    loops = studio.setdefault("mentors", {}).setdefault(target, {}).setdefault("open_loops", [])
    if any(loop.get("text") == text and loop.get("status", "open") != "closed" for loop in loops):
        return None
    loop = {
        "id": f"OL-next-{sha256_text(text)[:6]}",
        "owner": target,
        "due": clock.add_days(clock.now_iso(), 1)[:10],
        "text": text,
        "blocking": True,
        "status": "open",
        "activity_id": activity,
        "est_minutes": est,
        "source_event": attempt_id,
        "from": current,
    }
    loops.append(loop)
    jour.append(
        "mentor_next_observed",
        {"attempt_id": attempt_id, "from": current, "to": target, "open_loop": loop["id"], "text": text, "est_minutes": est},
        dedupe_key=f"promised_next:{session_id}:{turn}",
    )
    return loop


def cmd_say(args) -> int:
    paths = open_paths(args.project)
    state = _load_all(paths)
    project = state["project"]
    studio = state["studio"]
    capability = state["capability"]
    session = state["session"]
    text = sys.stdin.read() if args.text == "-" else args.text
    text = (text or "").strip()
    if not text:
        raise UsageError("say 需要一句话；也可以用 say - 从 stdin 读取。")
    jour = _journal(paths)
    attempt_id = new_id("say")
    current = studio.get("current_mentor") or "planner"

    decision = detect_named_mentor(text, current)
    named = decision.get("mentor")
    ambiguous = decision.get("ambiguous") or []
    mentioned = decision.get("mentioned") or []
    duplicate = _session_has_turn(session, text)
    jour.append(
        "say_attempt",
        {
            "attempt_id": attempt_id,
            "text_sha": sha256_text(text)[:16],
            "chars": len(text),
            "mentor": current,
            "session_id": session.get("session_id"),
            "named": named,
            "ambiguous": ambiguous,
            "mentioned": mentioned,
            "duplicate": bool(duplicate),
        },
    )
    if mentioned:
        jour.append(
            "mentor_mentioned",
            {"attempt_id": attempt_id, "mentors": mentioned, "action": "no_switch"},
            dedupe_key=f"mentioned:{attempt_id}",
        )
    if ambiguous:
        names = "、".join(MENTOR_LABELS.get(mentor, mentor) for mentor in ambiguous)
        jour.append(
            "mentor_named_ambiguous",
            {"attempt_id": attempt_id, "text": text[:80], "candidates": ambiguous},
            dedupe_key=f"ambiguous:{attempt_id}",
        )
        print(f"你一句话里同时提到了 {names}。我一次只换一位：请明确说「找 <导师>」，或用 learn.cmd switch <导师>。")
        return EXIT_USAGE

    if named and named != current:
        result = _do_switch(
            paths,
            project,
            studio,
            capability,
            session,
            named,
            why_override="用户点名",
            fill_missing=False,
            source="say",
            default_why="用户点名",
        )
        if result["code"] == 0:
            state = _load_all(paths)
            project, studio, capability, session = state["project"], state["studio"], state["capability"], state["session"]
            current = named
            duplicate = False
        else:
            _record_handoff_rejected(
                jour,
                attempt_id=attempt_id,
                source="say_named",
                from_mentor=current,
                target=named,
                reason=result.get("reason") or "交接未完成",
                missing=result.get("missing"),
            )
            print(f"（换导师没有成功：{result.get('reason')}；这次先由当前导师继续，你的消息不会丢。）")

    if duplicate:
        print("已记录（同一会话里相同输入不会重复计数）。")
        print(f"导师：{MENTOR_LABELS.get(current, current)}；如需继续请换一句话。")
        clock_info = _session_clock(session)
        if clock_info.get("budget"):
            if clock_info["remaining"] > 0:
                print(f"时间：本次剩余 {clock_info['remaining']} 分钟（已用 {clock_info['elapsed']}/{clock_info['budget']}）")
            else:
                print(f"时间：本次预算已到（已用 {clock_info['elapsed']}/{clock_info['budget']}）；不会自动结束，可 pause 或继续。")
        return 0

    if session.get("mentor") != current or session.get("ended_at") or not session.get("session_id"):
        session = _begin_session(paths, studio, current, args.offline, session)
        _save(session_doc(paths), session)

    time_info = parse_learner_time(text)
    confirmation = _apply_learner_time(paths, project, studio, session, time_info, jour, attempt_id)
    if confirmation:
        print(confirmation)

    llm = _resolve_llm(paths, args.offline)
    print(f"== {MENTOR_LABELS.get(current, current)} ==")
    result = perform_turn(paths, project, studio, capability, session, llm, current, text, args.offline, attempt_id=attempt_id)
    _print_reply(result)
    _save(studio_doc(paths), studio)
    _save(capability_doc(paths), capability)
    studio_session = session_doc(paths)
    _save(studio_session, session)
    _print_footer(result)

    auto_enabled = not getattr(args, "no_auto", False)
    proposal = result["update"].get("handoff")
    if auto_enabled and isinstance(proposal, dict) and proposal.get("auto"):
        target = proposal.get("to_hint") or proposal.get("to")
        if target not in MENTORS:
            _record_handoff_rejected(
                jour,
                attempt_id=attempt_id,
                source="say_auto",
                from_mentor=current,
                target=str(target or ""),
                reason="导师建议自动交接，但没有给出有效目标",
                missing=["to_hint"],
            )
            print("（导师建议自动换人，但没给出有效目标；这次留在当前导师，你的消息已保存。）")
        elif target != current:
            result_switch = _do_switch(
                paths,
                project,
                studio,
                capability,
                session,
                target,
                why_override=str(proposal.get("why") or "") or None,
                fill_missing=False,
                source="auto",
                default_why="自动交接",
            )
            if result_switch["code"] == 0:
                print(f"\n[自动交接] 已切换到 {MENTOR_LABELS.get(target, target)}。")
            else:
                _record_handoff_rejected(
                    jour,
                    attempt_id=attempt_id,
                    source="say_auto",
                    from_mentor=current,
                    target=target,
                    reason=result_switch.get("reason") or "交接未完成",
                    missing=result_switch.get("missing"),
                )
                print(f"（自动交接没完成：{result_switch.get('reason')}；已留在当前导师，你的消息已保存。）")
    elif auto_enabled and result.get("diagnosis_target"):
        target = result["diagnosis_target"]
        jour.append(
            "diagnosis_handoff_requested",
            {
                "attempt_id": attempt_id,
                "mentor": current,
                "to": target,
                "reason": "planner 诊断出需要讲解/陪练的误解，运行时执行交接",
            },
            dedupe_key=f"diagnosis:{attempt_id}",
        )
        result_switch = _do_switch(
            paths,
            project,
            studio,
            capability,
            session,
            target,
            why_override=f"诊断发现需要讲解/陪练的误解，转 {MENTOR_LABELS.get(target, target)}",
            fill_missing=False,
            source="diagnosis",
            default_why="诊断转交",
        )
        if result_switch["code"] == 0:
            print(f"\n[诊断转交] 已切换到 {MENTOR_LABELS.get(target, target)}，你的学习记录已带过去。")
        else:
            _record_handoff_rejected(
                jour,
                attempt_id=attempt_id,
                source="diagnosis",
                from_mentor=current,
                target=target,
                reason=result_switch.get("reason") or "交接未完成",
                missing=result_switch.get("missing"),
            )
    return 0


def _print_reply(result: dict) -> None:
    prefix = "[离线脚本导师] " if result["mode"] == "mock" else ""
    print(prefix + result["visible"])
    for warning in result["warnings"]:
        print(f"! {warning}")


def _print_footer(result: dict) -> None:
    update = result["update"] or {}
    bits = [f"帮助等级：{HELP_LABELS.get(update.get('help_level'), '未标注')}"]
    attempt = update.get("attempt") or {}
    if attempt.get("activity_id"):
        outcome = "对" if attempt.get("correct") is True else ("错" if attempt.get("correct") is False else "未判定")
        bits.append(f"尝试：{attempt['activity_id']}（{outcome}）")
    if update.get("next"):
        bits.append(f"下一步：{str(update['next'])[:80]}")
    print("")
    print("本轮记录：" + " ｜ ".join(bits))
    summary = result.get("summary") or {}
    for upgrade in summary.get("upgraded") or []:
        print(f"能力记录：{upgrade['node']} 现在为 {upgrade['to']} 级（来源 {upgrade['source']}）")
    for violation in summary.get("violations") or []:
        print("安全拦截：本轮有一项越界请求被拒绝（已记录，未改状态）。")
    if result.get("duplicate"):
        print("去重：同一答案不重复计分。")
    plan_summary = result.get("plan_summary") or {}
    if plan_summary.get("status") == "proposed":
        print("计划：变更已记录，生效计划不变，等 planner 批准。")
    elif plan_summary.get("status") == "applied":
        print("计划：已按 planner 的变更更新。")
    elif plan_summary.get("status") == "noop":
        print("计划：本轮无需改动。")
    elif plan_summary.get("status") == "rejected":
        print("计划：本轮计划变更被拒绝（见 journal 的 plan_change_rejected）。")
    if result.get("exam_requested"):
        print("下一步：learn.cmd examine（独立验证已排入）")
    ns = result.get("next") or {}
    if ns.get("action"):
        print(f"运行时下一步：{ns['action']}（约 {ns.get('est_minutes', 20)} 分钟，{MENTOR_LABELS.get(ns.get('mentor'), ns.get('mentor'))}）")
    session_clock = _session_clock(result.get("session") or {})
    if session_clock.get("budget"):
        if session_clock["remaining"] > 0:
            print(f"时间：本次剩余 {session_clock['remaining']} 分钟（已用 {session_clock['elapsed']}/{session_clock['budget']}，还有 {session_clock['remaining']} 分钟可用）")
        else:
            print(f"时间：本次预算已到（已用 {session_clock['elapsed']}/{session_clock['budget']}）；不会自动结束，可 pause 或继续。")
    if (result.get("summary") or {}).get("practice"):
        print("证据：本轮只记录为练习观察，能力等级不变（独立验证由 examiner 判定）。")
    print(f"本轮上下文：{result['context']['chars']} 字符")


# ---------------------------------------------------------------------------
# switch / examine / review
# ---------------------------------------------------------------------------
def _do_switch(
    paths: Paths,
    project: dict,
    studio: dict,
    capability: dict,
    session: dict,
    target: str,
    *,
    why_override: str | None,
    fill_missing: bool,
    source: str,
    note: str = "",
    strict: bool = False,
    default_why: str = "用户点名",
) -> dict:
    """Attempt a switch.  Returns a report dict; never raises for a bad handoff."""
    if target not in MENTORS:
        return {"code": EXIT_USAGE, "reason": f"未知导师 {target!r}", "missing": [], "payload": None}
    current = studio.get("current_mentor") or "planner"
    plan = get_plan(studio)
    if target == current:
        print(f"当前已经是 {MENTOR_LABELS.get(target, target)}；如需结束会话用 learn.cmd pause。")
        return {"code": 0, "noop": True, "payload": None, "missing": [], "composed": {}}
    proposal = (studio.get("mentors", {}).get(current, {}) or {}).get("last_handoff_proposal")
    composed = compose_payload(
        paths=paths,
        project=project,
        plan=plan,
        studio=studio,
        capability=capability,
        mentor_from=current,
        mentor_to=target,
        proposal=proposal,
        session=session,
        why_override=why_override,
        note=note,
        fill_missing=fill_missing,
        require_proposal=strict,
        default_why=default_why,
    )
    payload = composed["payload"]
    jour = _journal(paths)
    if composed["missing"]:
        jour.append(
            "handoff_invalid",
            {
                "missing": composed["missing"],
                "raw_sha256": composed["raw_sha256"],
                "from": current,
                "to": target,
                "source": source,
                "strict": bool(strict),
            },
            dedupe_key=f"handoff_invalid:{source}:{current}:{target}:{composed['raw_sha256'][:12]}:{','.join(sorted(composed['missing']))}",
        )
        return {
            "code": EXIT_STATE,
            "reason": f"缺 {', '.join(composed['missing'])}",
            "missing": composed["missing"],
            "payload": payload,
            "composed": composed,
        }
    structure = validate_payload(payload)
    if structure:
        jour.append(
            "handoff_invalid",
            {"missing": [], "problems": structure, "from": current, "to": target, "source": source},
            dedupe_key=f"handoff_invalid:structure:{source}:{current}:{target}:{payload['handoff_id']}",
        )
        return {
            "code": EXIT_STATE,
            "reason": "；".join(structure),
            "missing": [],
            "payload": payload,
            "composed": composed,
        }
    if composed["truncated"]:
        jour.append("handoff_truncated", {"fields": composed["truncated"], "handoff_id": payload["handoff_id"]})
    written = write_handoff(paths, payload)
    if composed["filled"]:
        jour.append(
            "handoff_degraded",
            {"handoff_id": payload["handoff_id"], "filled": composed["filled"], "cause": "fill_missing"},
        )
    ns = next_step(studio, capability)
    if ns["mentor"] != target:
        jour.append(
            "handoff_next_overridden",
            {
                "handoff_id": payload["handoff_id"],
                "proposal_next": payload.get("next"),
                "runtime_next": ns["reason"],
            },
        )
    update_state_after_handoff(studio, payload)
    studio["current_mentor"] = target
    studio["updated_at"] = clock.now_iso()
    jour.append(
        "mentor_switch",
        {"from": current, "to": target, "handoff_id": payload["handoff_id"], "source": source},
        dedupe_key=f"switch:{payload['handoff_id']}",
    )
    if source in ("say", "examine", "review"):
        jour.append(
            "mentor_named",
            {"mentor": target, "from": current, "named_by": "user", "source": source},
            dedupe_key=f"named:{payload['handoff_id']}",
        )
    session = _begin_session(paths, studio, target, session.get("offline") or False, session)
    _save(session_doc(paths), session)
    _save(studio_doc(paths), studio)
    print(f"已切换到 {MENTOR_LABELS.get(target, target)}（交接单 {payload['handoff_id']} 已保存）。")
    if composed["filled"]:
        print(f"提示：交接里 {', '.join(composed['filled'])} 由运行时按记录补齐（已记 handoff_degraded）。")
    if ns["mentor"] != target:
        print(f"计划本身建议下一轮找 {MENTOR_LABELS.get(ns['mentor'], ns['mentor'])}（{ns['reason']}）。")
    print('下一步：直接说话即可（learn.cmd say "..."），或 learn.cmd status 看状态。')
    return {
        "code": 0,
        "payload": payload,
        "composed": composed,
        "written": written,
        "missing": [],
        "filled": composed["filled"],
    }


def cmd_switch(args) -> int:
    paths = open_paths(args.project)
    state = _load_all(paths)
    target = (args.mentor or "").strip().lower()
    if target not in MENTORS:
        suggestions = [mentor for mentor in MENTORS if mentor.startswith(target)] if target else []
        hint = f"；你是不是想找：{', '.join(suggestions)}" if suggestions else ""
        raise UsageError(f"未知导师 {args.mentor!r}；可选：{_mentor_list()}{hint}")
    result = _do_switch(
        paths,
        state["project"],
        state["studio"],
        state["capability"],
        state["session"],
        target,
        why_override=args.why,
        fill_missing=args.fill_missing,
        source="switch",
        strict=args.strict,
        default_why="用户点名",
    )
    if result["code"] == EXIT_STATE:
        print(f"这次换人没有完成：{result['reason']}。当前导师、计划和学习记录都没有变。")
        print(f"如需按导师提案严格检查，去掉 --strict 即可正常切换；强制补齐用：learn.cmd switch {target} --fill-missing")
    return result["code"]


def cmd_examine(args) -> int:
    paths = open_paths(args.project)
    state = _load_all(paths)
    project = state["project"]
    studio = state["studio"]
    capability = state["capability"]
    session = state["session"]
    current = studio.get("current_mentor") or "planner"
    pending = capability.get("pending_exam") or {}
    repeated_examine = (
        current == "examiner"
        and bool(pending)
        and pending.get("opened_session") == session.get("session_id")
        and int(pending.get("opened_turn") or 0) == int(session.get("turn_index") or 0)
    )
    if current != "examiner":
        result = _do_switch(
            paths,
            project,
            studio,
            capability,
            session,
            "examiner",
            why_override="用户点名：开考",
            fill_missing=args.fill_missing,
            source="examine",
            default_why="用户点名：开考",
        )
        if result["code"] != 0:
            print(f"开考没有开始：{result.get('reason')}。当前导师和学习记录没有变。")
            return result["code"]
        state = _load_all(paths)
        project, studio, capability, session = state["project"], state["studio"], state["capability"], state["session"]
        current = "examiner"
    elif repeated_examine:
        # Same command, same session, no new turn: do not stack another handoff.
        print(f"考核已在进行中（{pending.get('node_id')}）；本次不重复写交接。")
    else:
        # examine is a handoff trigger even when the examiner is already seated
        self_result = _self_handoff(
            paths,
            project,
            studio,
            capability,
            session=session,
            why="开考：继续由 examiner 做独立考核",
            fill_missing=args.fill_missing,
            source="examine",
            default_why="用户点名：开考",
        )
        if self_result["code"] != 0:
            print(f"开考没有开始：{self_result.get('reason')}。当前记录没有变。")
            return self_result["code"]
    plan = get_plan(studio)
    objective = plan.get("current_objective") or {}
    activity = args.activity or objective.get("activity_id") or objective.get("id")
    exam = new_exam(project, plan, capability, requested_by=current, activity=activity)
    exam["opened_session"] = session.get("session_id")
    exam["opened_turn"] = int(session.get("turn_index") or 0)
    jour = _journal(paths)
    jour.append(
        "exam_started",
        {
            "node_id": exam["node_id"],
            "activity_id": activity,
            "requested_by": current,
            "criteria": objective.get("success_criteria", []),
        },
        dedupe_key=f"exam_started:{exam['node_id']}:{exam['at']}",
    )
    _save(capability_doc(paths), capability)
    _save(studio_doc(paths), studio)
    print(f"已进入考核：{MENTOR_LABELS['examiner']}")
    print(f"考核范围：{objective.get('id')} {objective.get('text')}")
    questions = exam.get("questions") or []
    index = int(exam.get("current_index") or 0)
    if questions:
        current_question = questions[index] if index < len(questions) else questions[-1]
        print(f"当前题目：第 {index + 1}/{len(questions)} 题 {current_question}（做完继续 examine/say，直到 3 题）")
    print(f"成功标准：{'；'.join(objective.get('success_criteria') or ['按计划步骤判定'])}")
    print("规则：只记录你自己的话；给提示或让我讲解，本次判定作废（运行时强制）。")
    print("开始：learn.cmd say \"<你的回答>\"；答不出来就说「跳过」，记 pending。")
    return 0


def cmd_review(args) -> int:
    paths = open_paths(args.project)
    state = _load_all(paths)
    project = state["project"]
    studio = state["studio"]
    capability = state["capability"]
    session = state["session"]
    current = studio.get("current_mentor") or "planner"
    already = current == "reviewer"
    if not already:
        result = _do_switch(
            paths,
            project,
            studio,
            capability,
            session,
            "reviewer",
            why_override=args.why if args.why is not None else "用户点名：请求复盘",
            fill_missing=args.fill_missing,
            source="review",
            default_why="用户点名：请求复盘",
        )
        if result["code"] != 0:
            print(f"复盘没有开始：{result.get('reason')}。当前记录没有变。")
            return result["code"]
        state = _load_all(paths)
        project, studio, capability, session = state["project"], state["studio"], state["capability"], state["session"]
    if session.get("mentor") != "reviewer" or session.get("ended_at") or not session.get("session_id"):
        session = _begin_session(paths, studio, "reviewer", args.offline, session)
        _save(session_doc(paths), session)
    llm = _resolve_llm(paths, args.offline)
    print(f"== {MENTOR_LABELS['reviewer']} · 复盘 ==")
    result = perform_turn(
        paths,
        project,
        studio,
        capability,
        session,
        llm,
        "reviewer",
        "帮我复盘",
        args.offline,
        attempt_id=new_id("review"),
    )
    _print_reply(result)
    _save(studio_doc(paths), studio)
    _save(capability_doc(paths), capability)
    _save(session_doc(paths), session)
    _print_footer(result)
    if already:
        handoff_result = _self_handoff(
            paths,
            project,
            studio,
            capability,
            session=session,
            why="复盘结束，继续留在 reviewer 会话",
            fill_missing=args.fill_missing,
            source="review",
            default_why="用户点名：复盘结束",
        )
        if handoff_result["code"] == 0:
            _save(studio_doc(paths), studio)
            print(f"（已在 reviewer 会话，补写自交接 {handoff_result['payload']['handoff_id']}。）")
    review = result.get("review") or {}
    if review:
        print("")
        print(f"复盘已保存：{review['review_id']}；建议交给 {review['recommendation']['mentor']}。")
        print("用 learn.cmd plan 查看 reviewer 的建议型 plan_change（需 planner 批准）。")
    return 0


# ---------------------------------------------------------------------------
# pause
# ---------------------------------------------------------------------------
def _self_handoff(
    paths: Paths,
    project: dict,
    studio: dict,
    capability: dict,
    *,
    session: dict | None = None,
    note: str = "",
    fill_missing: bool = False,
    why: str | None = None,
    source: str = "pause",
    default_why: str = "会话结束",
) -> dict:
    """Write a from=to=self handoff.  Returns ``{code, payload, composed, written}``."""
    current = studio.get("current_mentor") or "planner"
    proposal = (studio.get("mentors", {}).get(current, {}) or {}).get("last_handoff_proposal")
    composed = compose_payload(
        paths=paths,
        project=project,
        plan=get_plan(studio),
        studio=studio,
        capability=capability,
        mentor_from=current,
        mentor_to=current,
        proposal=proposal,
        session=session,
        why_override=why,
        note=note,
        fill_missing=fill_missing,
        default_why=default_why,
    )
    payload = composed["payload"]
    jour = _journal(paths)
    if composed["missing"]:
        jour.append(
            "handoff_invalid",
            {
                "missing": composed["missing"],
                "raw_sha256": composed["raw_sha256"],
                "from": current,
                "to": current,
                "source": source,
            },
            dedupe_key=f"handoff_invalid:{source}:{composed['raw_sha256'][:12]}:{','.join(sorted(composed['missing']))}",
        )
        return {
            "code": EXIT_STATE,
            "reason": f"缺 {', '.join(composed['missing'])}",
            "missing": composed["missing"],
            "payload": payload,
            "composed": composed,
            "written": None,
        }
    structure = validate_payload(payload)
    if structure:
        jour.append(
            "handoff_invalid",
            {"missing": [], "problems": structure, "from": current, "to": current, "source": source},
            dedupe_key=f"handoff_invalid:structure:{source}:{payload['handoff_id']}",
        )
        return {
            "code": EXIT_STATE,
            "reason": "；".join(structure),
            "missing": [],
            "payload": payload,
            "composed": composed,
            "written": None,
        }
    if composed["truncated"]:
        jour.append("handoff_truncated", {"fields": composed["truncated"], "handoff_id": payload["handoff_id"]})
    written = write_handoff(paths, payload)
    if composed["filled"]:
        jour.append(
            "handoff_degraded",
            {
                "handoff_id": payload["handoff_id"],
                "filled": composed["filled"],
                "cause": "fill_missing",
            },
        )
    update_state_after_handoff(studio, payload)
    return {"code": 0, "payload": payload, "composed": composed, "written": written}


def cmd_pause(args) -> int:
    paths = open_paths(args.project)
    state = _load_all(paths)
    project = state["project"]
    studio = state["studio"]
    capability = state["capability"]
    session = state["session"]
    current = studio.get("current_mentor") or "planner"
    if not (session.get("turns") or []):
        # No mentor turn means there is nothing to hand off.  Do not create an
        # empty self-handoff or an empty session transcript (v0.2.4).
        session["ended_at"] = clock.now_iso()
        _save(session_doc(paths), session)
        _journal(paths).append(
            "pause_no_handoff",
            {"session_id": session.get("session_id"), "mentor": current, "reason": "empty_session"},
            dedupe_key=f"pause_no_handoff:{session.get('session_id')}",
        )
        _journal(paths).append(
            "sync",
            {"source": "pause", "phase": "requested", "handoff_id": None},
            dedupe_key=f"sync:pause:empty:{session.get('session_id')}",
        )
        ensure_git_identity(paths.root)
        git = GitSync(paths.root, include=SYNC_INCLUDE)
        if git.is_repo():
            git.ensure_repository()
        report = git.sync(default_sync_message(project.get("slug") or "learnark", "pause"))
        _log_sync(paths, {"source": "pause", "empty_session": True, **report.as_dict()})
        print("本次没有导师回合，未写交接；上次交接保持不变。")
        print(f"git：{report.headline()}；remote={report.remote or '（无）'}")
        ns = next_step(studio, capability)
        print(f"下次继续：learn.cmd start（建议找 {MENTOR_LABELS.get(ns['mentor'], ns['mentor'])}）。")
        if report.state in ("conflict", "commit-failed"):
            return EXIT_STATE
        return 0
    latest = latest_handoff_payload(paths)
    if (
        session.get("ended_at")
        and latest
        and latest.get("session_id")
        and latest.get("session_id") == session.get("session_id")
        and latest.get("from") == current
        and latest.get("to") == current
    ):
        # Retrying `pause` (e.g. after a terminal timeout) must not stack a
        # second identical handoff on the same finished session.
        print(f"本次会话已经保存过交接：{latest.get('handoff_id')}；不重复写交接。")
        print("学习记录都在，下次用 learn.cmd start 继续。")
        return 0
    # A pause must never block saving progress: when the mentor has proposed
    # nothing at all we compose and log a degraded self-handoff; an *incomplete*
    # proposal is still rejected strictly (exit 3) unless --fill-missing.
    result = _self_handoff(
        paths,
        project,
        studio,
        capability,
        session=session,
        note=args.note or "",
        fill_missing=args.fill_missing,
        source="pause",
        default_why="会话结束：保存进度",
    )
    composed = result["composed"]
    payload = result["payload"]
    if result["code"] != 0:
        print(f"这次保存没有完成：{result.get('reason')}。你已有的记录没有丢，可以稍后重试。")
        return result["code"]
    written = result["written"]
    session["ended_at"] = clock.now_iso()
    _write_session(paths, project, session)
    _save(session_doc(paths), session)
    _save(studio_doc(paths), studio)
    _journal(paths).append("session_end", {"session_id": session.get("session_id"), "mentor": current, "handoff_id": payload["handoff_id"]})
    _journal(paths).append(
        "sync",
        {"source": "pause", "phase": "requested", "handoff_id": payload["handoff_id"]},
        dedupe_key=f"sync:pause:{payload['handoff_id']}",
    )

    ensure_git_identity(paths.root)
    git = GitSync(paths.root, include=SYNC_INCLUDE)
    if git.is_repo():
        git.ensure_repository()
    report = git.sync(default_sync_message(project.get("slug") or "learnark", "pause"))
    _log_sync(paths, {"source": "pause", **report.as_dict()})
    print(f"已保存：{written['file']}")
    if composed["filled"]:
        print(f"提示：交接里 {', '.join(composed['filled'])} 由运行时按记录补齐（已记 handoff_degraded）。")
    print(f"交接：{payload['handoff_id']}（{current} 收工）")
    print(f"git：{report.headline()}；remote={report.remote or '（无）'}")
    if report.recovery:
        print(f"提示：{report.recovery}")
    ns = next_step(studio, capability)
    print("")
    print(f"下次继续：learn.cmd start（会从 {payload['handoff_id']} 恢复）")
    if capability.get("pending_exam") and ns["mentor"] == "examiner":
        print("下一轮建议直接开考：learn.cmd examine（有待独立验证的目标）")
    elif ns["mentor"] == current:
        print(f"下一轮仍由 {MENTOR_LABELS.get(ns['mentor'], ns['mentor'])} 接续：{ns['reason']}")
    else:
        print(f"建议下一轮找 {MENTOR_LABELS.get(ns['mentor'], ns['mentor'])}：{ns['reason']}")
    if report.state in ("conflict", "commit-failed"):
        print("git 未完成：学习记录已保存，但同步需要人工处理（见上面的 recovery 提示）。")
        return EXIT_STATE
    return 0


# ---------------------------------------------------------------------------
# status / studio / plan / handoff
# ---------------------------------------------------------------------------
def _status_payload(paths: Paths, state: dict) -> dict:
    project = state["project"]
    studio = state["studio"]
    capability = state["capability"]
    plan = get_plan(studio)
    decision = next_step(studio, capability)
    handoff_event = latest_handoff_event(paths)
    payload = handoff_event.get("payload") if handoff_event else None
    session = state["session"]
    jour = _journal(paths)
    synthetic = sum(1 for event in jour.of_kind("mentor_turn") if (event.get("payload") or {}).get("synthetic"))
    git = GitSync(paths.root, include=SYNC_INCLUDE)
    git_status = git.status() if git.is_repo() else {"is_repo": False}
    objective = plan.get("current_objective") or {}
    open_loops = []
    for mentor in MENTORS:
        for loop in (studio.get("mentors", {}).get(mentor, {}) or {}).get("open_loops", []):
            if loop.get("status", "open") != "closed":
                open_loops.append(loop)
    recent_turns = [
        {
            "mentor": (event.get("payload") or {}).get("mentor"),
            "help_level": (event.get("payload") or {}).get("help_level"),
            "help_level_label": HELP_LABELS.get((event.get("payload") or {}).get("help_level"), "未标注"),
            "attempt_id": (event.get("payload") or {}).get("attempt_id"),
            "invalid": (event.get("payload") or {}).get("invalid"),
            "at": event.get("at"),
        }
        for event in jour.of_kind("mentor_turn")[-5:]
    ]
    weaknesses = []
    for node in capability.get("nodes", []):
        fail = node.get("last_fail") or {}
        if fail.get("misconception"):
            weaknesses.append(
                {
                    "node": node.get("id"),
                    "label": node.get("label"),
                    "misconception": fail.get("misconception"),
                    "at": fail.get("at"),
                    "source_event": fail.get("source_event"),
                    "source": fail.get("source"),
                }
            )
    return {
        "variant": {"id": VARIANT_ID, "version": VARIANT_VERSION, "core_version": _core_version(), "schema_version": SCHEMA_VERSION},
        "project": {"slug": project.get("slug"), "goal": project.get("goal"), "template": project.get("template"), "path": str(paths.root)},
        "current_mentor": studio.get("current_mentor"),
        "plan": {
            "plan_id": plan.get("plan_id"),
            "version": plan.get("version"),
            "authority": plan.get("authority"),
            "hash": plan.get("hash"),
            "objective": objective,
            "steps_total": len([step for step in plan.get("steps", []) if step.get("status") != "removed"]),
            "steps_done": len([step for step in plan.get("steps", []) if step.get("status") == "done"]),
            "next_step": decision,
            "pending_changes": [change for change in studio.get("plan_changes", []) if change.get("status") == "proposed"],
        },
        "capability": {
            "nodes": summarize_levels(capability),
            "pending_exam": capability.get("pending_exam"),
            "weaknesses": weaknesses,
        },
        "weaknesses": weaknesses,
        "recent_turns": recent_turns,
        "last_turn": recent_turns[-1] if recent_turns else None,
        "open_loops": open_loops,
        "last_session": {
            "id": session.get("session_id"),
            "mentor": session.get("mentor"),
            "at": session.get("started_at"),
            "turns": len(session.get("turns", [])) // 2,
            "ended": bool(session.get("ended_at")),
        },
        "last_handoff": {
            "id": (payload or {}).get("handoff_id"),
            "from": (payload or {}).get("from"),
            "to": (payload or {}).get("to"),
            "at": (payload or {}).get("created_at"),
            "degraded": (payload or {}).get("degraded"),
            "next": (payload or {}).get("next"),
        }
        if payload
        else None,
        "review_counter": studio.get("review_counter"),
        "mentors": [
            {
                "id": mentor,
                "label": MENTOR_LABELS[mentor],
                "turns": int((studio.get("mentors", {}).get(mentor, {}) or {}).get("turns") or 0),
                "last_active": (studio.get("mentors", {}).get(mentor, {}) or {}).get("last_active"),
                "open_loops": len(
                    [loop for loop in (studio.get("mentors", {}).get(mentor, {}) or {}).get("open_loops", []) if loop.get("status", "open") != "closed"]
                ),
                "duty": MENTOR_DUTIES[mentor],
            }
            for mentor in MENTORS
        ],
        "sync": {
            "is_repo": bool(git_status.get("is_repo")),
            "branch": git_status.get("branch", ""),
            "remote": git_status.get("remote", ""),
            "dirty": not git_status.get("clean", True) if git_status.get("is_repo") else None,
            "ahead": git_status.get("ahead"),
            "behind": git_status.get("behind"),
            "unmerged": git_status.get("unmerged") or [],
            "diverged": bool(git_status.get("diverged")),
        },
        "offline_last_turn": (session.get("offline") if session.get("offline") is not None else None),
        "synthetic_turns": synthetic,
        "next": {
            "mentor": decision["mentor"],
            "reason": decision["reason"],
            "action": decision.get("action"),
            "est_minutes": decision.get("est_minutes"),
            "activity_id": decision.get("activity_id"),
            "question_id": decision.get("question_id"),
            "command": (
                "learn.cmd examine"
                if decision["mentor"] == "examiner" and capability.get("pending_exam")
                else (
                    f"learn.cmd switch {decision['mentor']}"
                    if decision["mentor"] != studio.get("current_mentor")
                    else 'learn.cmd say "..."'
                )
            ),
        },
        "where": (
            f"上次停在 {payload.get('handoff_id')}（{payload.get('from')}→{payload.get('to')}）"
            if payload
            else ("尚无学习记录（首次进入）" if not session.get("turns") else f"会话 {session.get('session_id')} 进行中")
        ),
    }


def cmd_status(args) -> int:
    paths = open_paths(args.project)
    state = _load_all(paths)
    for note in state["repairs"]:
        _warn(f"提示：{note}")
    payload = _status_payload(paths, state)
    if args.json:
        payload["recovered"] = state["repairs"]
        cli.emit_json(payload)
        return 0
    project = payload["project"]
    plan = payload["plan"]
    print(f"{VARIANT_NAME} · {project.get('slug')} · 模板 {project.get('template')}")
    print(f"目标：{project.get('goal')}")
    print(f"当前导师：{payload['current_mentor']} ｜ 计划 v{plan['version']} ｜ 进度 {plan['steps_done']}/{plan['steps_total']}")
    print(f"{payload['where']}")
    if payload["last_handoff"]:
        handoff = payload["last_handoff"]
        print(f"交接：{handoff['id']} {handoff['from']}→{handoff['to']}（{clock.human_age(handoff['at'])}，degraded={handoff['degraded']}）")
    last_turn = payload.get("last_turn")
    if last_turn:
        print(f"最近回合：{last_turn.get('mentor')} ｜ 帮助等级：{last_turn.get('help_level_label')}")
        if last_turn.get("invalid"):
            print("  ! 上一回合没有形成可记录证据；原文已保留，可继续。")
    print("")
    print("能力：")
    if payload["capability"]["nodes"]:
        for node in payload["capability"]["nodes"][:8]:
            print(f"  - {node['label']}：{node['level_label']}（证据 {node['evidence']} 条）")
    else:
        print("  - 暂无（未经证据校准）")
    verified = [node for node in payload["capability"]["nodes"] if node["level"] >= 4]
    print(f"  独立验证的节点：{len(verified)} 个；合成回合（离线）：{payload['synthetic_turns']}")
    print("薄弱/误解：")
    if payload.get("weaknesses"):
        for weakness in payload["weaknesses"][:5]:
            print(
                f"  - {weakness['label']}（{weakness['node']}）：{weakness['misconception']}"
                f"（来源 {weakness.get('source_event') or 'n/a'}，{weakness.get('at') or ''}）"
            )
    else:
        print("  - 暂无已记录的误解（不代表不会，只是还没有证据）")
    if payload["open_loops"]:
        print("未决：")
        for loop in payload["open_loops"][:5]:
            print(f"  - {loop.get('id')} [{'阻塞' if loop.get('blocking') else '一般'}] {loop.get('text')}（owner={loop.get('owner')}）")
    else:
        print("未决：无")
    pending = plan["pending_changes"]
    if pending:
        ids = "、".join(str(change.get("id")) for change in pending[:3])
        print(f"待批计划变更：{len(pending)} 条（{ids}；learn.cmd plan 查看）")
    print("")
    print(f"下一步：{payload['next']['command']}")
    print(f"  · 导师：{MENTOR_LABELS.get(payload['next']['mentor'], payload['next']['mentor'])}")
    print(f"  · 理由：{payload['next']['reason']}")
    if payload["next"].get("action"):
        print(f"  · 动作：{payload['next']['action']}（约 {payload['next'].get('est_minutes', 20)} 分钟）")
    if payload["next"].get("question_id"):
        print(f"  · 下一题：{payload['next']['question_id']}")
    sync = payload["sync"]
    if sync["is_repo"]:
        print(
            f"git：branch={sync['branch'] or '?'} remote={sync['remote'] or '（无）'} "
            f"dirty={sync['dirty']} diverged={sync['diverged']} unmerged={len(sync['unmerged'])}"
        )
        for path in sync["unmerged"][:5]:
            print(f"  ! 冲突文件：{path}")
        if sync["diverged"]:
            print("恢复：learn.cmd sync --recover --prefer local|remote（默认拒绝，需显式选择）")
    else:
        print("git：不是仓库（learn.cmd sync 会尝试初始化）")
    if payload["synthetic_turns"]:
        print("注意：存在离线脚本回合（synthetic），不能当作真实教学效果证据。")
    return 0


def cmd_studio(args) -> int:
    paths = open_paths(args.project)
    state = _load_all(paths)
    studio = state["studio"]
    capability = state["capability"]
    plan = get_plan(studio)
    jour = _journal(paths)
    decision = next_step(studio, capability)
    print(f"== Atelier 工作室 · 当前 {MENTOR_LABELS.get(studio.get('current_mentor'), '?')} ==")
    print(f"计划 {plan.get('plan_id')} v{plan.get('version')} ｜ 目标：{plan.get('current_objective', {}).get('text')}")
    print("")
    headers = ["导师", "职责", "回合", "最近活动", "未决", "状态"]
    rows = []
    for mentor in MENTORS:
        data = (studio.get("mentors", {}) or {}).get(mentor, {}) or {}
        loops = [loop for loop in data.get("open_loops", []) if loop.get("status", "open") != "closed"]
        status = "← 当前" if mentor == studio.get("current_mentor") else ("建议" if mentor == decision["mentor"] else "")
        rows.append(
            [
                f"{mentor}/{MENTOR_LABELS[mentor].split(' ')[0]}",
                MENTOR_DUTIES[mentor],
                str(data.get("turns") or 0),
                clock.human_age(data.get("last_active")) if data.get("last_active") else "未使用",
                str(len(loops)),
                status,
            ]
        )
    print(cli.table(rows, headers))
    print("")
    handoff = latest_handoff_event(paths)
    if handoff:
        payload = handoff["payload"]
        age = clock.human_age(payload.get("created_at"))
        print(f"最新交接：{payload.get('handoff_id')} {payload.get('from')}→{payload.get('to')}（{age}）")
        print(f"  why：{payload.get('why')}")
        print(f"  next：{payload.get('next')}")
        print(f"  文件：{paths.latest_handoff.relative_to(paths.root)}")
    else:
        print("最新交接：尚无")
    print("")
    proposed = [change for change in studio.get("plan_changes", []) if change.get("status") == "proposed"]
    applied = [change for change in studio.get("plan_changes", []) if change.get("status") in ("applied", "noop")]
    print(f"计划变更：applied {len(applied)} 条，proposed {len(proposed)} 条")
    for change in proposed[-3:]:
        print(f"  - {change['id']} by {change['by']} op={change['op']} step={change.get('step_id')}（待 planner）")
    if args.json:
        cli.emit_json(
            {
                "current_mentor": studio.get("current_mentor"),
                "mentors": [
                    {
                        "id": mentor,
                        "turns": int(((studio.get("mentors", {}).get(mentor, {}) or {}).get("turns")) or 0),
                        "last_active": ((studio.get("mentors", {}).get(mentor, {}) or {}).get("last_active")),
                        "open_loops": [
                            loop
                            for loop in ((studio.get("mentors", {}).get(mentor, {}) or {}).get("open_loops", []))
                            if loop.get("status", "open") != "closed"
                        ],
                        "proposal": bool((studio.get("mentors", {}).get(mentor, {}) or {}).get("last_handoff_proposal")),
                    }
                    for mentor in MENTORS
                ],
                "plan": {"version": plan.get("version"), "pending_changes": proposed},
                "handoff": (handoff or {}).get("payload"),
                "next_step": decision,
            }
        )
    return 0


def cmd_plan(args) -> int:
    paths = open_paths(args.project)
    if args.approve or args.reject:
        doc = studio_doc(paths)
        studio = doc.load()
        change_id = args.approve or args.reject
        result = approve_plan_change(studio, change_id, approve=bool(args.approve))
        if not result.get("ok"):
            print(f"未应用：{result.get('reason')}")
            return EXIT_STATE
        _append(_journal(paths), result.get("events") or [])
        _save(doc, studio)
        print(f"计划变更 {change_id} 已{'批准' if args.approve else '拒绝'}（planner 权威）。")
        if result.get("summary", {}).get("status") == "applied":
            print(f"计划版本：v{get_plan(studio)['version']}")
        return 0

    state = _load_all(paths)
    studio = state["studio"]
    plan = get_plan(studio)
    current_hash = plan_hash(plan)
    stored = plan.get("hash")
    consistent = stored == current_hash
    if args.check:
        print(f"plan.hash={stored}")
        print(f"recomputed={current_hash}")
        print(f"一致：{consistent}")
        if not consistent:
            _journal(paths).append(
                "plan_authority_violation",
                {"kind": "silent_plan_change", "stored": stored, "recomputed": current_hash},
            )
            return EXIT_STATE
        return 0
    if args.json:
        cli.emit_json(
            {
                "plan": plan,
                "plan_changes": studio.get("plan_changes", []),
                "hash_consistent": consistent,
                "authority": "planner",
            }
        )
        return 0
    objective = plan.get("current_objective") or {}
    print(f"计划 {plan.get('plan_id')} v{plan.get('version')}（权威：planner，hash={plan.get('hash')}）")
    print(f"每周 {format_weekly_scope(plan)} ｜ 当前目标：{objective.get('id')} {objective.get('text')}")
    print(f"成功标准：{'；'.join(objective.get('success_criteria') or []) or '未设定'}")
    print("")
    print("周目标：")
    for goal in plan.get("week_goals", []):
        week = int(goal.get("week") or 0)
        week_steps = [step for step in plan.get("steps", []) if int(step.get("week") or 0) == week and step.get("status") != "removed"]
        week_done = len([step for step in week_steps if step.get("status") == "done"])
        print(
            f"  - 第 {week} 周（{goal.get('status')}，{week_done}/{len(week_steps)} 步完成）："
            f"{goal.get('text')}  due={goal.get('due')}"
        )
    print("")
    print("步骤：")
    rows = []
    for step in plan.get("steps", []):
        rows.append(
            [
                str(step.get("n")),
                f"w{step.get('week')}",
                step.get("step_id"),
                step.get("mentor"),
                step.get("activity_id") or "-",
                step.get("status"),
                "evidence" if step.get("evidence_log") else "",
            ]
        )
    print(cli.table(rows, ["#", "周", "step_id", "导师", "activity", "状态", "证据"]))
    proposed = [change for change in studio.get("plan_changes", []) if change.get("status") == "proposed"]
    if proposed:
        print("")
        print("待批准（只有 planner 能让它生效）：")
        for change in proposed:
            detail = change.get("detail") or change.get("reason") or f"{change.get('op')} {change.get('step_id') or ''}".strip()
            print(f"  - {change['id']} by {change['by']} op={change['op']} step={change.get('step_id') or '-'}：{detail}")
        first_id = proposed[0]["id"]
        print(f"  批准：learn.cmd plan --approve {first_id} ｜ 拒绝：learn.cmd plan --reject {first_id}")
    applied = [change for change in studio.get("plan_changes", []) if change.get("status") in ("applied", "noop")]
    if applied:
        print("")
        print("已生效：")
        for change in applied[-5:]:
            print(f"  - {change['id']} by {change['by']} op={change['op']} v{change.get('plan_version')} {change.get('before_hash', '')[:8]}→{change.get('after_hash', '')[:8]}")
    print("")
    print(f"计划哈希一致：{consistent}" + ("" if consistent else "（不一致：跑 doctor --plan 定位）"))
    return 0


def cmd_handoff(args) -> int:
    paths = open_paths(args.project)
    if args.check:
        results = check_all(paths)
        problems = [result for result in results if not result["ok"]]
        print(f"检查 {len(results)} 份交接：{'全部通过' if not problems else str(len(problems)) + ' 份有问题'}")
        for result in results:
            mark = "ok " if result["ok"] else "FAIL"
            print(f"  [{mark}] {result['file']} {result['handoff_id']} {result['from']}→{result['to']}")
            for problem in result["problems"]:
                print(f"        - {problem}")
        return 0 if not problems else EXIT_STATE
    if args.last:
        from .handoff import handoff_files

        files = handoff_files(paths)[-args.last :]
        if not files:
            print("还没有交接文件。")
            return 0
        for path in files:
            payload, error = parse_file(path)
            if error:
                print(f"  [损坏] {path.name}：{error}")
                continue
            print(
                f"  {payload.get('handoff_id')} {payload.get('created_at')} "
                f"{payload.get('from')}→{payload.get('to')} degraded={payload.get('degraded')} :: {path.name}"
            )
        return 0
    event = latest_handoff_event(paths)
    if not event:
        print("还没有交接；pause / switch / examine / review 会写第一份。")
        return 0
    payload = event["payload"]
    print(f"{payload.get('handoff_id')}  {payload.get('from')} → {payload.get('to')}  {payload.get('created_at')}")
    print(f"degraded={payload.get('degraded')}  plan_snapshot=v{payload.get('plan_snapshot')}")
    print(f"文件：{paths.latest_handoff.relative_to(paths.root)}（年龄 {clock.human_age(payload.get('created_at'))}）")
    print("")
    print(f"为什么：{payload.get('why')}")
    print("已知：" + "；".join(payload.get("known") or []))
    print("做过：" + "；".join(payload.get("what_tried") or []))
    print("不要重做：" + ("；".join(payload.get("do_not_redo") or []) or "（没有明确记录，空是正常的）"))
    for loop in payload.get("open_loops") or []:
        print(f"未决：{loop.get('id')} [{'阻塞' if loop.get('blocking') else '一般'}] {loop.get('text')}（owner={loop.get('owner')} due={loop.get('due')}）")
    print(f"下一步：{payload.get('next')}")
    results = check_all(paths)
    print(f"历史交接 {len(results)} 份，校验 {'通过' if all(item['ok'] for item in results) else '有问题'}（learn.cmd handoff --check 查看）")
    return 0


# ---------------------------------------------------------------------------
# sync / doctor / export
# ---------------------------------------------------------------------------
def cmd_sync(args) -> int:
    paths = open_paths(args.project)
    project, _ = load_with_repair(project_doc(paths))
    git = GitSync(paths.root, include=SYNC_INCLUDE)
    if not git.available():
        print("没有可用的 git，学习记录已在磁盘上（written=yes, committed=no, pushed=no）。")
        return EXIT_ENV
    if not git.is_repo():
        git.ensure_repository()
    else:
        # Ensure .gitattributes / ignore rules exist even in older projects.
        git.ensure_repository()
    ensure_git_identity(paths.root)
    message = args.message or default_sync_message(project.get("slug") or "learnark", args.note or "")
    recover = bool(getattr(args, "recover", False))
    prefer = getattr(args, "prefer", None)
    sync_id = new_id("sync")
    refuses = recover and prefer not in ("local", "remote")
    if not refuses:
        _journal(paths).append(
            "sync_recover" if recover else "sync",
            {
                "source": "recover" if recover else "sync",
                "phase": "requested",
                "message": message,
                "prefer": prefer,
                "branch": git.branch(),
                "remote": git.remote_url() if git.remotes() else "",
            },
            dedupe_key=f"sync_request:{sync_id}",
        )
        if recover:
            _journal(paths).append(
                "recover_choice",
                {"sync_id": sync_id, "prefer": prefer, "chosen": prefer or "", "branch": git.branch()},
                dedupe_key=f"recover_choice:{sync_id}",
            )
    if recover:
        report, info = recover_with_preference(git, prefer, message)
    else:
        info = {}
        report = git.sync(message)
    status = git.status() if git.is_repo() else {"is_repo": False}
    print(f"git state: {report.state}" + ("（recover）" if recover else ""))
    print(f"written={'yes' if report.written else 'no'}  committed={'yes' if report.committed else 'no'}  pushed={'yes' if report.pushed else 'no'}")
    print(f"branch={report.branch or '-'} sha={report.sha or '-'} remote={report.remote or '（无）'}")
    if recover:
        print(f"恢复选择：{prefer or '未指定（拒绝写入）'}")
        if prefer == "local":
            print("保留本机 state；被覆盖的远程文件：" + ("、".join(info.get("lost_remote") or []) or "（无）"))
        elif prefer == "remote":
            print("采用远程 state；被覆盖的本机文件：" + ("、".join(info.get("lost_local") or []) or "（无）"))
        if info.get("merged_events"):
            print(f"journal 并集：{info['merged_events']} 条事件")
    unmerged = status.get("unmerged") or []
    diverged = bool(status.get("diverged"))
    print(f"diverged={'yes' if diverged else 'no'}  unmerged={len(unmerged)}")
    if unmerged:
        for path in unmerged:
            print(f"  ! 冲突文件：{path}")
    if report.files:
        print(f"files={len(report.files)}")
    if report.state == "conflict" and report.detail:
        try:
            detail = json.loads(report.detail)
        except (ValueError, TypeError):
            detail = {}
        blocking = detail.get("blocking") or detail.get("unmerged") or []
        if blocking:
            print("冲突文件（未自动合并）：")
            for path in blocking:
                print(f"  ! {path}")
    if report.recovery:
        print(f"提示：{report.recovery}")
    _log_sync(paths, {"source": "recover" if recover else "sync", "prefer": prefer, **report.as_dict()})
    if report.state in ("conflict", "commit-failed", "no-repository"):
        return EXIT_STATE
    if report.state in ("push-failed", "no-git"):
        return EXIT_ENV
    return 0


def cmd_doctor(args) -> int:
    paths = open_paths(args.project)
    jour = _journal(paths)
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "", hint: str = "", info: bool = False):
        checks.append({"name": name, "ok": ok, "detail": detail, "hint": hint, "info": info})

    # project
    try:
        project, project_note = load_with_repair(project_doc(paths))
        add("project_readable", bool(project.get("goal")), f"goal={'set' if project.get('goal') else 'missing'} schema={project.get('schema_version')}")
        if project_note:
            add("project_recovered", True, project_note, info=True)
    except LearnError as exc:
        project = {}
        add("project_readable", False, str(exc), "从 .bak 或备份恢复 .learnark/project.json")

    # journal
    try:
        integrity = jour.integrity()
        add("journal_integrity", not integrity["problems"], "；".join(integrity["problems"]) or f"{integrity['events']} events")
    except LearnError as exc:
        integrity = {"events": 0}
        add("journal_integrity", False, str(exc), "日志损坏：保留副本并从 .bak / git 历史恢复")
    try:
        with file_lock(jour.lock_path, timeout=0.2):
            pass
        add("journal_lock", True, "无其他进程持锁")
    except LockTimeout:
        add("journal_lock", False, "另一个进程正持有 journal 锁", "等它结束再跑；不要在写操作中途杀进程")

    # dedupe index
    try:
        index = json.loads(paths.dedupe_path.read_text(encoding="utf-8")) if paths.dedupe_path.exists() else {}
        journal_keys = {event.get("dedupe_key") for event in jour.all() if event.get("dedupe_key")}
        stale = [key for key in index if key not in journal_keys]
        if stale or not isinstance(index, dict):
            rebuilt = {event["dedupe_key"]: event.get("id") for event in jour.all() if event.get("dedupe_key")}
            write_json(paths.dedupe_path, rebuilt)
            jour.append("dedupe_rebuilt", {"removed": len(stale), "keys": len(rebuilt)})
            add("dedupe_index", True, f"已从 journal 重建（移除 {len(stale)} 条过期键）", info=True)
        else:
            add("dedupe_index", True, f"{len(index)} 条键与 journal 一致")
    except (ValueError, OSError) as exc:
        add("dedupe_index", False, f"去重索引不可读：{exc}", "删除 .learnark/journal/dedupe.json 后重建")

    # locks / temp files
    stale_locks = list(paths.learnark.glob("*.lock")) + list(paths.state_dir.glob("*.lock")) + list((paths.learnark / "journal").glob("*.lock"))
    add("lock_files", True, f"{len(stale_locks)} 个锁文件（无持有者）", info=True)
    temp_files = list(paths.learnark.rglob("*.tmp"))
    add("temp_files", not temp_files, f"{len(temp_files)} 个临时文件残留", "可安全删除 .tmp 文件")

    # git
    git = GitSync(paths.root, include=SYNC_INCLUDE)
    if git.available():
        if git.is_repo():
            status = git.status()
            unmerged = status.get("unmerged") or []
            diverged = bool(status.get("diverged"))
            add(
                "git",
                not (diverged or unmerged),
                f"branch={status.get('branch')} remote={status.get('remote') or '（无）'} "
                f"changed={len(status.get('changed') or [])} diverged={diverged} unmerged={len(unmerged)}",
                "远程与本地分叉：先 learn.cmd sync --recover --prefer local|remote；快照冲突需人工选择，不要 force push"
                if diverged
                else "无远程时只能本地提交（written/committed），真实 GitHub 同步未验证",
                info=not status.get("remote") and not diverged,
            )
            try:
                repo_root = git.repo_root().resolve()
            except LearnError:
                repo_root = paths.root
            add(
                "git_isolation",
                repo_root == paths.root.resolve(),
                f"repo_root={repo_root}",
                "项目嵌在更大的 git 仓库里：学习记录可能被父仓库一起提交，建议独立 init 或移出",
            )
        else:
            add("git", False, "项目不是 git 仓库", "运行 learn.cmd sync 会初始化仓库")
    else:
        add("git", False, "未安装 git", "安装 git 后可本地提交；学习记录不受影响")

    # llm configuration
    mode = (os.environ.get("LEARNARK_LLM") or "auto").strip().lower()
    has_key = bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LEARNARK_API_KEY"))
    offline = mode == "mock" or (mode == "auto" and not has_key)
    add("llm", True, f"mode={'offline/mock' if offline else 'api'} key={'yes' if has_key else 'no'}", "离线模式只证明流程；真实教学质量需 API key" if offline else "", info=offline)

    # plan authority
    plan_ok = True
    if not args.plan or args.plan:
        studio = None
        studio_note = ""
        try:
            studio, studio_note = load_with_repair(studio_doc(paths))
        except LearnError as exc:
            # doctor must report the damage, not abort before printing checks.
            add(
                "studio_readable",
                False,
                str(exc),
                "从 .bak 或 git 历史恢复 .learnark/state/studio.json；不要手写补全",
            )
        if studio_note:
            add("studio_recovered", True, studio_note, info=True)
        plan = get_plan(studio or {})
        if studio is None:
            pass
        elif plan.get("steps"):
            recomputed = plan_hash(plan)
            stored = plan.get("hash")
            plan_ok = stored == recomputed
            add(
                "plan_authority",
                plan_ok,
                f"stored={stored} recomputed={recomputed}" if not plan_ok else f"plan v{plan.get('version')} hash 一致",
                "计划哈希与快照不符：可能有人绕过 plan_change 改了计划；用 git diff 定位并回滚",
            )
            applied_events = len(jour.of_kind("plan_change_applied"))
            applied_records = len([change for change in studio.get("plan_changes", []) if change.get("status") == "applied"])
            add("plan_consistency", applied_records <= applied_events + 1, f"records={applied_records} events={applied_events}")
            objective = plan.get("current_objective") or {}
            step_ids = {step.get("step_id") for step in plan.get("steps", [])}
            if objective.get("id") and objective["id"] not in step_ids and objective["id"] != "review-and-transfer":
                add("current_objective", False, f"current_objective {objective['id']} 不在 plan.steps 中", "用 plan 命令检查；必要时让 planner 重排")
            else:
                add("current_objective", True, f"{objective.get('id')}")
        else:
            add("plan_authority", False, "没有计划", "运行 init 建计划")
        # handoffs
        results = check_all(paths)
        bad = [result for result in results if not result["ok"]]
        add(
            "handoffs",
            not bad,
            f"{len(results)} 份，问题 {len(bad)} 份" + ("；".join(f"{item['file']}: {'; '.join(item['problems'])}" for item in bad[:2]) if bad else ""),
            "修复/重写不合规的交接；不要编辑历史文件，追加新的",
        )
        latest = latest_handoff_event(paths)
        turns = sum(int((mentor or {}).get("turns") or 0) for mentor in ((studio or {}).get("mentors") or {}).values())
        if turns > 0 and not latest:
            add("handoff_present", False, "已有导师回合但没有交接", "运行 learn.cmd pause 补一份")
        if latest:
            handoff_files = {path.name for path in paths.handoff_dir.glob("*.md")}
            if latest["payload"].get("handoff_id"):
                add("handoff_event", True, f"latest={latest['payload'].get('handoff_id')}")
        # notes
        for mentor in MENTORS:
            try:
                notes, note_note = load_with_repair(notes_doc(paths, mentor))
            except LearnError as exc:
                add(f"notes_{mentor}", False, f"不可读：{exc}", "从 .bak 恢复，或重新 init 该导师笔记")
                continue
            too_many = len(notes.get("notes") or []) > 8
            add(
                f"notes_{mentor}",
                not too_many,
                f"{len(notes.get('notes') or [])}/8 行",
                "私有笔记超过 8 行：合并最旧的两行",
            )
        # snapshots vs journal
        turns_events = len(jour.of_kind("mentor_turn"))
        add("journal_markers", turns_events > 0, f"mentor_turn={turns_events}", info=turns_events == 0)
        snapshot_turns = sum(int((mentor or {}).get("turns") or 0) for mentor in ((studio or {}).get("mentors") or {}).values())
        if studio is not None and turns_events != snapshot_turns:
            add(
                "snapshot_drift",
                False,
                f"journal mentor_turn={turns_events} vs studio.mentors.turns={snapshot_turns}",
                "journal 是权威：先备份，再从 git 历史恢复 studio.json，或重跑一次会话补齐快照；不要删除 journal",
            )
        elif studio is not None:
            add("snapshot_drift", True, f"journal/studio turns agree ({turns_events})")
        synthetic = sum(1 for event in jour.of_kind("mentor_turn") if (event.get("payload") or {}).get("synthetic"))
        add("evidence_honesty", True, f"synthetic turns={synthetic}", "离线回合不能当作真实教学证据" if synthetic else "", info=bool(synthetic))

    if args.plan:
        keep = {
            "plan_authority",
            "plan_consistency",
            "current_objective",
            "studio_recovered",
            "studio_readable",
            "snapshot_drift",
            "handoffs",
            "handoff_present",
            "handoff_event",
        }
        checks = [check for check in checks if check["name"] in keep]
    problems = [check for check in checks if not check["ok"] and not check.get("info")]
    errors = problems
    print(f"== doctor · {paths.root} ==")
    for check in checks:
        mark = "ok " if check["ok"] else ("info" if check.get("info") else "FAIL")
        suffix = "" if check["ok"] else f"  <- {check['hint']}"
        print(f"[{mark}] {check['name']}：{check['detail']}{suffix}")
    print("")
    if errors:
        print(f"发现 {len(errors)} 个问题。修复后重跑 learn.cmd doctor。")
        return EXIT_STATE
    print("未发现问题。")
    return 0


def cmd_export(args) -> int:
    paths = open_paths(args.project)
    state = _load_all(paths)
    project = state["project"]
    studio = state["studio"]
    capability = state["capability"]
    reviews = state["reviews"]
    plan = get_plan(studio)
    jour = _journal(paths)
    decision = next_step(studio, capability)
    handoff_event = latest_handoff_event(paths)
    payload = handoff_event["payload"] if handoff_event else None
    synthetic = sum(1 for event in jour.of_kind("mentor_turn") if (event.get("payload") or {}).get("synthetic"))
    lines = [
        "# 学习档案（Atelier 导出）",
        "",
        f"- 导出时间：{clock.now_iso()}",
        f"- 版本：{VARIANT_NAME} {VARIANT_VERSION} · core {_core_version()} · schema {SCHEMA_VERSION}",
        f"- 项目：{project.get('slug')} ｜ 模板：{project.get('template')}",
        f"- 目标：{project.get('goal')}",
        f"- 周投入：约 {format_weekly_scope(project.get('learner') or {})}",
        "",
        "> 离线/合成说明：" + (
            f"本档案包含 {synthetic} 个脚本导师回合（synthetic），只证明系统行为，**不构成真实教学效果证据**。"
            if synthetic
            else "本档案没有脚本导师回合。"
        ),
        "",
        "## 计划",
        "",
        f"{plan.get('plan_id')} v{plan.get('version')}（权威：planner）",
        f"当前目标：{(plan.get('current_objective') or {}).get('id')} {(plan.get('current_objective') or {}).get('text')}",
        "",
        "| # | 周 | step_id | 导师 | activity | 状态 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for step in plan.get("steps", []):
        lines.append(
            f"| {step.get('n')} | {step.get('week')} | {step.get('step_id')} | {step.get('mentor')} | {step.get('activity_id') or '-'} | {step.get('status')} |"
        )
    lines += ["", "### 周目标", ""]
    for goal in plan.get("week_goals", []):
        lines.append(f"- 第 {goal.get('week')} 周（{goal.get('status')}）：{goal.get('text')}  due={goal.get('due')}")
    lines += ["", "## 能力证据（运行时判定）", ""]
    nodes = summarize_levels(capability)
    if nodes:
        lines += ["| 能力节点 | 等级 | 证据数 | 最近错因 |", "| --- | --- | --- | --- |"]
        for node in nodes:
            fail = (node.get("last_fail") or {}).get("misconception") or ""
            lines.append(f"| {node['label']}（{node['id']}） | {node['level']} {node['level_label']} | {node['evidence']} | {fail} |")
    else:
        lines.append("（暂无）")
    lines += ["", "### 证据明细", ""]
    any_evidence = False
    for node in capability.get("nodes", []):
        for entry in node.get("evidence", []):
            any_evidence = True
            lines.append(
                f"- {node['id']}：source={entry.get('source')} help_level={entry.get('help_level')} "
                f"event={entry.get('event_id')} synthetic={entry.get('synthetic')} at={entry.get('at')}"
            )
    if not any_evidence:
        lines.append("（暂无逐条证据）")
    lines += ["", "## 最近交接", ""]
    if payload:
        lines += [
            f"- {payload.get('handoff_id')} {payload.get('from')} → {payload.get('to')}（{payload.get('created_at')}，degraded={payload.get('degraded')}）",
            f"- why：{payload.get('why')}",
            f"- next：{payload.get('next')}",
            f"- 已知：{'；'.join(payload.get('known') or [])}",
            f"- 不要重做：{'；'.join(payload.get('do_not_redo') or [])}",
        ]
    else:
        lines.append("（尚无交接）")
    lines += ["", "## 会话记录", ""]
    sessions = sorted(paths.sessions_dir.glob("*.md")) if paths.sessions_dir.exists() else []
    if sessions:
        for session_file in sessions[-12:]:
            text = read_text(session_file).strip().splitlines()
            title = text[0] if text else session_file.name
            lines.append(f"- `{session_file.relative_to(paths.root)}`：{title}")
    else:
        lines.append("（暂无）")
    lines += ["", "## 计划变更", ""]
    changes = studio.get("plan_changes") or []
    if changes:
        for change in changes:
            lines.append(
                f"- {change.get('id')} by {change.get('by')} op={change.get('op')} status={change.get('status')} "
                f"v{change.get('plan_version')} {str(change.get('before_hash'))[:8]}→{str(change.get('after_hash'))[:8]}"
            )
    else:
        lines.append("（暂无）")
    lines += ["", "## 复盘", ""]
    if reviews.get("reviews"):
        for review in reviews["reviews"]:
            lines.append(
                f"- {review.get('review_id')} {review.get('at')} kind={review.get('kind')} gap={review.get('gap')} "
                f"confidence={review.get('confidence')} suggest={review.get('suggest') or (review.get('recommendation') or {}).get('week_goal')}"
            )
    else:
        lines.append("（暂无）")
    lines += [
        "",
        "## 下一步",
        "",
        f"- 建议导师：{MENTOR_LABELS.get(decision['mentor'], decision['mentor'])}",
        f"- 理由：{decision['reason']}",
        f"- 命令：{'learn.cmd switch ' + decision['mentor'] if decision['mentor'] != studio.get('current_mentor') else 'learn.cmd say \"...\"'}",
        "",
        "## 记录位置",
        "",
        "- 事件流：`.learnark/journal/events.jsonl`",
        "- 计划与导师：`.learnark/state/studio.json`",
        "- 能力证据：`.learnark/state/capability.json`",
        "- 交接：`.learnark/handoff/`",
        "- 会话：`sessions/`",
        "",
    ]
    out = Path(args.out) if args.out else paths.artifacts_dir / f"export-{clock.stamp_for_filename()}.md"
    out = out.expanduser()
    if not out.is_absolute():
        out = paths.root / out
    atomic_write_text(out, "\n".join(lines))
    _journal(paths).append("export", {"path": str(out), "synthetic_turns": synthetic})
    print(f"已导出学习档案：{out}")
    if synthetic:
        print(f"注意：包含 {synthetic} 个离线脚本回合（synthetic），不代表真实教学效果。")
    return 0


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------
def _common(parser: argparse.ArgumentParser, *, project: bool = True, offline: bool = True) -> None:
    if project:
        parser.add_argument("--project", default=None, help="项目路径（默认从 cwd 向上找 .learnark/）")
    if offline:
        parser.add_argument("--offline", action="store_true", help="离线脚本导师（等于 LEARNARK_LLM=mock）")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="learn", description=f"{VARIANT_NAME} {VARIANT_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="建立学习项目")
    init.add_argument("--goal", default="", help="学习目标")
    init.add_argument("--minutes-per-week", type=int, default=0, dest="minutes_per_week")
    init.add_argument("--template", default="agent-dev", choices=["agent-dev", "email"])
    init.add_argument("--dir", default="", help="项目目录（默认当前目录）")
    init.add_argument("--name", default="", help="项目 slug")
    init.set_defaults(func=cmd_init)

    start = sub.add_parser("start", help="一句话入口：恢复并给出下一步")
    _common(start)
    start.add_argument("--minutes", type=int, default=0, help="本次可用分钟数")
    start.set_defaults(func=cmd_start)

    say = sub.add_parser("say", help="学习者发言")
    _common(say)
    say.add_argument("text", help="学习者原话；用 - 从 stdin 读取")
    say.add_argument("--auto", action="store_true", help="兼容旧参数；自动交接默认开启，用 --no-auto 关闭")
    say.add_argument("--no-auto", action="store_true", dest="no_auto", help="禁止提案中的 auto 标记触发自动交接")
    say.set_defaults(func=cmd_say)

    status = sub.add_parser("status", help="当前状态")
    _common(status)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    pause = sub.add_parser("pause", help="结束本次学习：写交接 + 保存 + 同步")
    _common(pause)
    pause.add_argument("--note", default="")
    pause.add_argument("--fill-missing", action="store_true", dest="fill_missing")
    pause.set_defaults(func=cmd_pause)

    switch = sub.add_parser("switch", help="切换导师（写交接契约）")
    _common(switch)
    switch.add_argument("mentor")
    switch.add_argument("--why", default=None)
    switch.add_argument("--fill-missing", action="store_true", dest="fill_missing")
    switch.add_argument(
        "--strict",
        action="store_true",
        help="要求导师提案包含 why/what_tried/open_loops/next（C-S2 契约测试用）；默认由运行时从记录合成交接",
    )
    switch.set_defaults(func=cmd_switch)

    studio = sub.add_parser("studio", help="五导师工作室视图")
    _common(studio)
    studio.add_argument("--json", action="store_true")
    studio.set_defaults(func=cmd_studio)

    handoff = sub.add_parser("handoff", help="查看/校验交接")
    _common(handoff)
    handoff.add_argument("--last", type=int, default=0)
    handoff.add_argument("--check", action="store_true")
    handoff.set_defaults(func=cmd_handoff)

    plan = sub.add_parser("plan", help="计划与计划变更")
    _common(plan)
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--check", action="store_true")
    plan.add_argument("--approve", default="")
    plan.add_argument("--reject", default="")
    plan.set_defaults(func=cmd_plan)

    examine = sub.add_parser("examine", help="切 examiner 并开考")
    _common(examine)
    examine.add_argument("--activity", default="")
    examine.add_argument("--fill-missing", action="store_true", dest="fill_missing")
    examine.set_defaults(func=cmd_examine)

    review = sub.add_parser("review", help="reviewer 复盘（不是 review 队列）")
    _common(review)
    review.add_argument("--why", default=None)
    review.add_argument("--fill-missing", action="store_true", dest="fill_missing")
    review.set_defaults(func=cmd_review)

    sync = sub.add_parser("sync", help="git 同步")
    _common(sync)
    sync.add_argument("--message", default="")
    sync.add_argument("--note", default="")
    sync.add_argument(
        "--recover",
        action="store_true",
        help="恢复分叉：journal 按事件 id 并集合并；state 冲突必须配 --prefer",
    )
    sync.add_argument(
        "--prefer",
        choices=("local", "remote"),
        default=None,
        help="恢复时 state/snapshot 冲突保留哪一边（默认拒绝，需显式选择）",
    )
    sync.set_defaults(func=cmd_sync)

    doctor = sub.add_parser("doctor", help="自检")
    _common(doctor)
    doctor.add_argument("--plan", action="store_true", help="只检查计划权威")
    doctor.set_defaults(func=cmd_doctor)

    export = sub.add_parser("export", help="导出学习档案")
    _common(export, offline=False)
    export.add_argument("--out", default="")
    export.set_defaults(func=cmd_export)

    return parser


# Commands that read-modify-write project state must hold the cross-process
# project lock for their whole run.  `status` / `studio` / `handoff` stay
# lock-free so a learner can always inspect a project while another command is
# writing; `plan` only locks when it decides a change.
LOCKED_COMMANDS = frozenset({"start", "say", "switch", "examine", "review", "pause", "sync", "doctor", "export"})


def _needs_project_lock(args) -> bool:
    if args.command in LOCKED_COMMANDS:
        return True
    if args.command == "plan":
        return bool(getattr(args, "approve", None) or getattr(args, "reject", None))
    return False


def main(argv: list[str] | None = None) -> int:
    cli.setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if _needs_project_lock(args):
            paths = open_paths(getattr(args, "project", None))
            with project_lock(paths):
                return int(args.func(args) or 0)
        return int(args.func(args) or 0)
    except UsageError as exc:
        _warn(f"learn: {exc}")
        return EXIT_USAGE
    except (LLMUnavailable, LLMError) as exc:
        _warn(f"learn: LLM 不可用：{exc}")
        return EXIT_ENV
    except (LockTimeout, StaleWrite) as exc:
        _warn(f"learn: 状态被并发修改：{exc}（没有覆盖任何内容，请重跑）")
        return EXIT_STATE
    except LearnError as exc:
        _warn(f"learn: {exc}")
        return EXIT_STATE
    except KeyboardInterrupt:
        _warn("learn: 已中断；写入是原子的，没有半写状态。")
        return 130
    except Exception as exc:  # pragma: no cover - defensive
        if os.environ.get("LEARNARK_DEBUG"):
            traceback.print_exc()
        _warn(f"learn: 未预期的错误：{type(exc).__name__}: {exc}")
        return EXIT_ENV
