"""The handoff contract: compose, validate, persist, and audit.

The machine block at the end of each handoff file is authoritative.  The header
is a human summary only; a field that exists solely in the header counts as
missing, exactly as ``protocols/handoff.md`` demands.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from learncore import clock
from learncore.fsutil import atomic_write_text, read_text, sha256_text

from . import SCHEMA_VERSION
from .const import (
    HANDOFF_CONTENT_FIELDS,
    HANDOFF_LIMITS,
    HANDOFF_REQUIRED_FIELDS,
    MENTOR_LABELS,
    MENTORS,
)
from .state import Paths, journal

_BLOCK_RE = re.compile(r"```handoff[ \t]*\r?\n(?P<body>.*?)```", re.DOTALL | re.IGNORECASE)
_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_text(text: str) -> str:
    return _PUNCT_RE.sub("", (text or "").lower())


def text_hash(text: str) -> str:
    return sha256_text(normalize_text(text))


def _short(value, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    cut = max(1, limit - 1)
    window = text[:cut]
    best = max(window.rfind(marker) for marker in ("。", "！", "？", "；", "，", "、", " ", "\n", ". ", "; "))
    if best >= max(20, cut // 2):
        return text[: best + 1].rstrip() + "…"
    return window.rstrip() + "…"


def latest_handoff_payload(paths: Paths) -> dict | None:
    events = journal(paths).of_kind("handoff")
    return events[-1].get("payload") if events else None


def latest_handoff_event(paths: Paths) -> dict | None:
    events = journal(paths).of_kind("handoff")
    return events[-1] if events else None


def next_handoff_id(paths: Paths) -> str:
    highest = 0
    for event in journal(paths).of_kind("handoff"):
        raw = str((event.get("payload") or {}).get("handoff_id") or "")
        match = re.search(r"(\d+)$", raw)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"H-{highest + 1:04d}"


# -- composition ----------------------------------------------------------
def compose_known(project: dict, plan: dict, capability: dict) -> list[str]:
    """Facts only: what the runtime has actually observed."""
    known: list[str] = []
    nodes = sorted(
        capability.get("nodes", []),
        key=lambda node: (node.get("updated_at") or "", node.get("id") or ""),
        reverse=True,
    )
    for node in nodes:
        level = int(node.get("level") or 0)
        if level >= 4:
            known.append(_short(f"独立验证：{node.get('label') or node.get('id')}", 120))
        elif level == 3:
            known.append(_short(f"练习中做对过：{node.get('label') or node.get('id')}", 120))
        if len(known) >= 3:
            break
    for node in nodes:
        last_fail = node.get("last_fail") or {}
        if last_fail.get("misconception"):
            known.append(_short(f"上次卡点：{last_fail['misconception']}", 120))
            break
    objective = plan.get("current_objective") or {}
    if objective.get("text") and len(known) < 4:
        known.append(_short(f"当前目标（未完成）：{objective['text']}", 120))
    if not known:
        goal = project.get("goal") or "学习目标"
        known.append(_short(f"尚无行为证据，只有目标：{goal}", 120))
    return known[: HANDOFF_LIMITS["known"][0]]


def compose_do_not_redo(studio: dict) -> list[str]:
    """Only explicit statements recorded in the journal; empty is acceptable."""
    entries: list[str] = []
    for item in (studio.get("dedupe") or {}).get("do_not_redo", []):
        if isinstance(item, dict):
            source = item.get("source")
            # Never inject legacy template anti-patterns as if the learner said them.
            if source == "template" or (source is None and not item.get("event_id")):
                continue
            text = item.get("text")
        else:
            text = str(item)
        if text and str(text).strip():
            entries.append(_short(text, 120))
    seen: set[str] = set()
    unique: list[str] = []
    for entry in entries:
        key = text_hash(entry)
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique[:12]


def _previous_attempt_entries(paths: Paths, current_session_id: str | None) -> list[str]:
    """Last few attempts from earlier sessions, so a new mentor does not re-teach."""
    entries: list[str] = []
    events = []
    for event in journal(paths).all():
        if event.get("kind") != "mentor_turn":
            continue
        payload = event.get("payload") or {}
        if current_session_id and payload.get("session_id") == current_session_id:
            continue
        attempt = payload.get("attempt") or {}
        activity = attempt.get("activity_id") if isinstance(attempt, dict) else None
        if activity:
            events.append((event, payload, activity))
    for event, payload, activity in events[-3:]:
        attempt = payload.get("attempt") or {}
        if attempt.get("correct") is True:
            outcome = "通过"
        elif attempt.get("correct") is False:
            outcome = "未通过"
        else:
            claimed = attempt.get("claimed_correct")
            outcome = "自称对（未核验）" if claimed is True else ("未通过" if claimed is False else "未判定")
        help_level = payload.get("help_level")
        stamp = str(payload.get("session_id") or "")[-15:]
        entries.append(f"上次会话 {stamp}：{activity}（{outcome}，帮助等级 {help_level}）")
    return entries


def compose_what_tried(paths: Paths, session: dict | None, studio: dict) -> list[str]:
    """Compose from earlier sessions + the current session, never from imagination."""
    current_entries: list[str] = []
    rounds = 0
    learner_text = ""
    for turn in (session or {}).get("turns", []):
        if turn.get("role") == "learner":
            rounds += 1
            learner_text = str(turn.get("text") or "").strip()
            continue
        if turn.get("role") != "mentor":
            continue
        attempt = turn.get("attempt") or {}
        help_level = turn.get("help_level")
        activity = attempt.get("activity_id") if isinstance(attempt, dict) else None
        if activity:
            if attempt.get("correct") is True:
                outcome = "通过"
            elif attempt.get("correct") is False:
                outcome = "未通过"
            else:
                claimed = attempt.get("claimed_correct")
                outcome = "自称对（未核验）" if claimed is True else ("未通过" if claimed is False else "未判定")
            current_entries.append(f"本轮第 {rounds} 轮：{activity}（{outcome}，帮助等级 {help_level}）")
        elif learner_text:
            current_entries.append(f"本轮第 {rounds} 轮：学习者提交「{_short(learner_text, 40)}」，导师回复（帮助等级 {help_level}）")
        if len(current_entries) >= 12:
            break
    previous = _previous_attempt_entries(paths, (session or {}).get("session_id"))
    entries = previous + current_entries
    if not entries:
        entries.append("本次交接前没有记录到尝试或产物（尚无导师回合；见会话记录）")
    return entries[:12]


def _normalize_loop(raw, index: int, default_owner: str) -> dict | None:
    if isinstance(raw, str):
        text = raw.strip()
        return {
            "id": f"OL-{index}",
            "owner": default_owner,
            "due": clock.add_days(clock.now_iso(), 1)[:10],
            "text": text,
            "blocking": False,
            "status": "open",
        }
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "").strip()
    if not text:
        return None
    owner = raw.get("owner") if raw.get("owner") in MENTORS else default_owner
    due = raw.get("due")
    if not isinstance(due, str) or not due.strip():
        due = clock.add_days(clock.now_iso(), 1)[:10]
    return {
        "id": str(raw.get("id") or f"OL-{index}"),
        "owner": owner,
        "due": due[:10],
        "text": text,
        "blocking": bool(raw.get("blocking")),
        "status": str(raw.get("status") or "open"),
    }


def compose_open_loops(studio: dict, capability: dict, mentor_to: str) -> list[dict]:
    loops: list[dict] = []
    for mentor in MENTORS:
        for loop in (studio.get("mentors", {}).get(mentor, {}) or {}).get("open_loops", []):
            if loop.get("status", "open") != "closed":
                loops.append(dict(loop))
    pending = capability.get("pending_exam") or {}
    if pending.get("status") in ("open", "requested", "reask", "pending"):
        loops.append(
            {
                "id": "OL-exam",
                "owner": "examiner",
                "due": clock.add_days(clock.now_iso(), 1)[:10],
                "text": f"完成独立考核：{pending.get('label') or pending.get('node_id') or '当前目标'}",
                "blocking": True,
                "status": "open",
            }
        )
    objective = (studio.get("plan") or {}).get("current_objective") or {}
    if objective.get("text"):
        ns = planner_next(studio, capability)
        loops.append(
            {
                "id": "OL-objective",
                "owner": ns["mentor"] if ns.get("mentor") in MENTORS else mentor_to,
                "due": clock.add_days(clock.now_iso(), 1)[:10],
                "text": f"完成 {objective.get('id')}：{_short(objective.get('text'), 100)}",
                "blocking": bool(ns.get("kind") == "pending_exam"),
                "status": "open",
            }
        )
    seen: set[str] = set()
    unique: list[dict] = []
    for loop in loops:
        key = str(loop.get("id"))
        if key in seen:
            continue
        seen.add(key)
        if loop.get("owner") not in MENTORS:
            loop["owner"] = mentor_to
        unique.append(loop)
    if not unique:
        unique.append(
            {
                "id": "OL-continue",
                "owner": mentor_to,
                "due": clock.add_days(clock.now_iso(), 1)[:10],
                "text": "按计划继续当前目标（尚无具体未决项）",
                "blocking": False,
                "status": "open",
            }
        )
    return unique[: HANDOFF_LIMITS["open_loops"][0]]


def compose_next(studio: dict, capability: dict) -> str:
    ns = planner_next(studio, capability)
    label = MENTOR_LABELS.get(ns.get("mentor"), ns.get("mentor"))
    action = ns.get("action") or ns.get("reason", "")
    estimate = ns.get("est_minutes")
    suffix = f"（约 {estimate} 分钟）" if estimate else ""
    return _short(f"由 {label} 接续：{action}{suffix}；{ns.get('reason', '')}", HANDOFF_LIMITS["next"][1])


def _proposal_nonempty(proposal: dict, field: str) -> bool:
    value = proposal.get(field)
    if field in ("what_tried", "open_loops"):
        return isinstance(value, list) and len(value) > 0
    if field == "why":
        return isinstance(value, str) and bool(value.strip())
    if field == "next":
        return isinstance(value, str) and bool(value.strip())
    return bool(value)


def compose_payload(
    *,
    paths: Paths,
    project: dict,
    plan: dict,
    studio: dict,
    capability: dict,
    mentor_from: str,
    mentor_to: str,
    proposal: dict | None,
    session: dict | None = None,
    why_override: str | None = None,
    note: str = "",
    fill_missing: bool = False,
    require_proposal: bool = False,
    default_why: str = "用户点名",
) -> dict:
    """Assemble a handoff.

    v0.2.1 contract: the runtime composes ``known/what_tried/open_loops/next/
    do_not_redo`` from journal, session, and plan.  A mentor proposal is only a
    source for ``why``.  ``require_proposal`` (explicit ``switch --strict``)
    additionally requires the mentor to have proposed the four content fields,
    which keeps the C-S2 strict-contract test meaningful.
    """
    proposal = proposal if isinstance(proposal, dict) else {}
    missing: list[str] = []
    filled: list[str] = []
    truncated: list[str] = []

    if require_proposal:
        for field in ("why", "what_tried", "open_loops", "next"):
            if not _proposal_nonempty(proposal, field):
                missing.append(field)
    if not require_proposal or not missing:
        why = why_override or str(proposal.get("why") or "").strip() or default_why
    else:
        why = why_override or str(proposal.get("why") or "").strip() or default_why
    if not why:
        missing.append("why")

    known = compose_known(project, plan, capability)
    what_tried = compose_what_tried(paths, session, studio)
    if note:
        what_tried.append(_short(f"学习者备注：{note}", 120))
    do_not_redo = compose_do_not_redo(studio)
    loops = compose_open_loops(studio, capability, mentor_to)
    nxt = compose_next(studio, capability)

    if missing and fill_missing:
        filled = list(dict.fromkeys(missing))
        missing = []
        if not why:
            why = why_override or f"{default_why}（运行时补齐，degraded）"
        if "what_tried" in filled and not what_tried:
            what_tried = ["本次交接前没有记录到尝试或产物（运行时补齐，degraded）"]
        if "open_loops" in filled and not loops:
            loops = [
                {
                    "id": "OL-continue",
                    "owner": mentor_to,
                    "due": clock.add_days(clock.now_iso(), 1)[:10],
                    "text": "按计划继续当前目标（运行时补齐，degraded）",
                    "blocking": False,
                    "status": "open",
                }
            ]
        if "next" in filled and not nxt:
            nxt = f"由 {MENTOR_LABELS.get(mentor_to, mentor_to)} 接续（运行时补齐，degraded）"

    if len(known) > HANDOFF_LIMITS["known"][0]:
        known = known[: HANDOFF_LIMITS["known"][0]]
        truncated.append("known")
    known = [_short(item, HANDOFF_LIMITS["known"][1]) for item in known]
    if len(what_tried) > HANDOFF_LIMITS["what_tried"][0]:
        what_tried = what_tried[: HANDOFF_LIMITS["what_tried"][0]]
        truncated.append("what_tried")
    shortened = any(len(item) > HANDOFF_LIMITS["what_tried"][1] for item in what_tried)
    what_tried = [_short(item, HANDOFF_LIMITS["what_tried"][1]) for item in what_tried]
    if shortened and "what_tried" not in truncated:
        truncated.append("what_tried")
    if len(do_not_redo) > HANDOFF_LIMITS["do_not_redo"][0]:
        do_not_redo = do_not_redo[: HANDOFF_LIMITS["do_not_redo"][0]]
        truncated.append("do_not_redo")
    if len(loops) > HANDOFF_LIMITS["open_loops"][0]:
        loops = loops[: HANDOFF_LIMITS["open_loops"][0]]
        truncated.append("open_loops")
    nxt = _short(nxt, HANDOFF_LIMITS["next"][1])
    why = _short(why, HANDOFF_LIMITS["why"][1])
    ns = planner_next(studio, capability)

    payload = {
        "handoff_id": next_handoff_id(paths),
        "schema_version": SCHEMA_VERSION,
        "from": mentor_from,
        "to": mentor_to,
        "why": why,
        "known": known,
        "what_tried": what_tried,
        "do_not_redo": do_not_redo,
        "open_loops": loops,
        "next": nxt,
        "created_at": clock.now_iso(),
        "plan_snapshot": int(plan.get("version") or 1),
        "session_id": (session or {}).get("session_id"),
        "next_step": {"mentor": ns["mentor"], "reason": ns["reason"], "kind": ns["kind"]},
        "degraded": bool(filled),
        "filled": filled,
        "strict": bool(require_proposal),
    }
    if note:
        payload["note"] = _short(note, 200)
    return {
        "payload": payload,
        "missing": missing,
        "filled": filled,
        "truncated": truncated,
        "raw_sha256": sha256_text(json.dumps(proposal, ensure_ascii=False, sort_keys=True)),
    }


def planner_next(studio: dict, capability: dict) -> dict:
    from .planning import next_step

    return next_step(studio, capability)


# -- validation -----------------------------------------------------------
def validate_payload(payload: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be an object"]
    for field in HANDOFF_REQUIRED_FIELDS:
        if field not in payload:
            problems.append(f"missing {field}")
    if problems:
        return problems
    if not isinstance(payload.get("handoff_id"), str) or not payload["handoff_id"].strip():
        problems.append("handoff_id must be a non-empty string")
    if payload.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version must be {SCHEMA_VERSION}")
    for field in ("from", "to"):
        if payload.get(field) not in MENTORS:
            problems.append(f"{field} must be one of {', '.join(MENTORS)}")
    if payload.get("from") == payload.get("to"):
        # self handoffs are legal (pause), anything else is a real switch
        pass
    try:
        datetime.fromisoformat(str(payload.get("created_at", "")).replace("Z", "+00:00"))
    except ValueError:
        problems.append("created_at must be an ISO-8601 timestamp")
    for field in ("known", "what_tried"):
        value = payload.get(field)
        if not isinstance(value, list) or not value:
            problems.append(f"{field} must be a non-empty list")
        else:
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    problems.append(f"{field} items must be non-empty strings")
                    break
    dnr = payload.get("do_not_redo")
    if not isinstance(dnr, list):
        problems.append("do_not_redo must be a list (empty is allowed)")
    else:
        for item in dnr:
            if not isinstance(item, str) or not item.strip():
                problems.append("do_not_redo items must be non-empty strings")
                break
    loops = payload.get("open_loops")
    if not isinstance(loops, list) or not loops:
        problems.append("open_loops must be a non-empty list")
    else:
        for loop in loops:
            if not isinstance(loop, dict):
                problems.append("open_loops items must be objects")
                break
            for key in ("id", "owner", "text"):
                if not str(loop.get(key) or "").strip():
                    problems.append(f"open_loops item missing {key}")
                    break
            if loop.get("owner") not in MENTORS:
                problems.append("open_loops owner must be a mentor id")
                break
    for field in ("why", "next"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{field} must be a non-empty string")
    if isinstance(payload.get("next"), str) and len(payload["next"]) > HANDOFF_LIMITS["next"][1]:
        problems.append("next is over the 200 character limit")
    if not isinstance(payload.get("degraded"), bool):
        problems.append("degraded must be a boolean")
    return problems


# -- writing --------------------------------------------------------------
def render(payload: dict) -> str:
    def bullets(items, empty="（无）"):
        if not items:
            return [empty]
        return [f"- {item}" for item in items]

    loops = payload.get("open_loops") or []
    loop_lines = []
    for loop in loops:
        flag = "阻塞" if loop.get("blocking") else "一般"
        loop_lines.append(
            f"- {loop.get('id')} [{flag}] owner={loop.get('owner')} due={loop.get('due')} {loop.get('text')}"
        )
    same = payload.get("from") == payload.get("to")
    lines = [
        f"# 会话交接（{payload.get('from')} 收工）" if same else f"# 交接 {payload.get('from')} → {payload.get('to')}",
        "",
        f"- handoff_id: {payload.get('handoff_id')}",
        f"- from: {payload.get('from')}",
        f"- to: {payload.get('to')}",
        f"- created_at: {payload.get('created_at')}",
        f"- plan_snapshot: {payload.get('plan_snapshot')}",
        f"- degraded: {'true' if payload.get('degraded') else 'false'}",
        "",
        "## 为什么现在交接",
        payload.get("why") or "",
        "",
        "## 已知（运行时从事件合成）",
        *bullets(payload.get("known")),
        "",
        "## 做过什么（来自会话与事件）",
        *bullets(payload.get("what_tried")),
        "",
        "## 不要重做（只收明确说过的）",
        *bullets(payload.get("do_not_redo")),
        "",
        "## 未决",
        *(loop_lines or ["（无）"]),
        "",
        "## 下一步",
        payload.get("next") or "",
        "",
        "> 机器块是权威；上面的 YAML 摘要仅供人读。",
        "",
        "```handoff",
        json.dumps(payload, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def write_handoff(paths: Paths, payload: dict) -> dict:
    paths.handoff_dir.mkdir(parents=True, exist_ok=True)
    stamp = clock.now().strftime("%Y%m%dT%H%M%S")
    name = f"{stamp}-{payload['from']}-to-{payload['to']}.md"
    path = paths.handoff_dir / name
    if path.exists():
        path = paths.handoff_dir / f"{stamp}-{payload['from']}-to-{payload['to']}-{payload['handoff_id']}.md"
    text = render(payload)
    atomic_write_text(path, text)
    atomic_write_text(paths.latest_handoff, text)
    event = journal(paths).append(
        "handoff",
        payload,
        dedupe_key=f"handoff:{payload['handoff_id']}",
        actor=payload.get("from", "runtime"),
    )
    return {"path": path, "latest": paths.latest_handoff, "event": event, "file": str(path.relative_to(paths.root))}


def update_state_after_handoff(studio: dict, payload: dict) -> None:
    """Apply the handoff consequences to studio (open loops, last id, proposal)."""
    studio["last_handoff_id"] = payload["handoff_id"]
    studio["updated_at"] = clock.now_iso()
    from_mentor = payload.get("from")
    to_mentor = payload.get("to")
    mentors = studio.setdefault("mentors", {})
    loops = payload.get("open_loops") or []
    # Closed/runtime-placeholder loops never enter scheduling.
    for loop in loops:
        if loop.get("status") == "closed" or loop.get("id") == "OL-0":
            continue
        owner = loop.get("owner") if loop.get("owner") in MENTORS else to_mentor
        bucket = mentors.setdefault(owner, {}).setdefault("open_loops", [])
        existing = next((item for item in bucket if item.get("id") == loop.get("id")), None)
        if existing:
            existing.update(loop)
        else:
            bucket.append(dict(loop))
    # A handoff discharges the leaving mentor's own pending obligations.
    if from_mentor in mentors and from_mentor != to_mentor:
        mentors[from_mentor]["open_loops"] = [
            loop for loop in mentors[from_mentor].get("open_loops", []) if loop.get("owner") == from_mentor
        ]
        mentors[from_mentor]["last_handoff_proposal"] = None
    if to_mentor in mentors:
        mentors[to_mentor]["last_active"] = clock.now_iso()


def mark_loops_closed(studio: dict, closed_ids: list[str]) -> list[str]:
    closed = []
    for mentor in MENTORS:
        for loop in studio.get("mentors", {}).get(mentor, {}).get("open_loops", []):
            if loop.get("id") in closed_ids and loop.get("status") != "closed":
                loop["status"] = "closed"
                closed.append(loop["id"])
    return closed


# -- auditing -------------------------------------------------------------
def parse_file(path) -> tuple[dict | None, str]:
    try:
        text = read_text(path)
    except OSError as exc:
        return None, f"unreadable: {exc}"
    match = _BLOCK_RE.search(text)
    if not match:
        return None, "缺少 ```handoff 机器块"
    try:
        payload = json.loads(match.group("body"))
    except json.JSONDecodeError as exc:
        return None, f"handoff 机器块不是合法 JSON：{exc}"
    if not isinstance(payload, dict):
        return None, "handoff 机器块必须是 JSON 对象"
    return payload, ""


def handoff_files(paths: Paths) -> list:
    if not paths.handoff_dir.exists():
        return []
    return sorted(path for path in paths.handoff_dir.glob("*.md") if path.name != "latest.md")


def check_all(paths: Paths) -> list[dict]:
    results = []
    for path in handoff_files(paths):
        payload, error = parse_file(path)
        problems = [error] if error else validate_payload(payload)
        results.append(
            {
                "file": str(path.relative_to(paths.root)),
                "handoff_id": (payload or {}).get("handoff_id", ""),
                "from": (payload or {}).get("from", ""),
                "to": (payload or {}).get("to", ""),
                "ok": not problems,
                "problems": problems,
            }
        )
    return results


def stale_days(paths: Paths) -> float | None:
    event = latest_handoff_event(paths)
    if not event:
        return None
    try:
        return clock.days_between(event["at"], clock.now_iso())
    except (ValueError, KeyError):
        return None
