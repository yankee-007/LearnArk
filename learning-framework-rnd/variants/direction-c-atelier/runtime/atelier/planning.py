"""Plan building, schedule authority (``next_step``), and plan-change execution.

Only the planner may make a plan change take effect.  Everything else in the
runtime treats ``studio.plan`` as read-only, which is what makes the authority
checkable: the stored ``plan.hash`` can only change together with a
``plan_change_applied`` event.
"""

from __future__ import annotations

import json
import re

from learncore import clock
from learncore.fsutil import sha256_text

from . import SCHEMA_VERSION
from .const import MENTORS, PLAN_OPS, REVIEW_EVERY


def build_plan(template: dict, minutes_per_week: int | None = None) -> dict:
    steps = []
    for row in template["steps"]:
        steps.append(
            {
                "n": int(row.get("n") or len(steps) + 1),
                "week": int(row.get("week") or 1),
                "step_id": row["step_id"],
                "text": row.get("text", ""),
                "mentor": row.get("mentor") or "coach",
                "activity_id": row.get("activity_id", ""),
                "evidence": row.get("evidence", ""),
                "status": "todo",
                "evidence_log": [],
            }
        )
    weeks: dict[int, list[str]] = {}
    for module in template.get("modules", []):
        weeks.setdefault(int(module.get("week") or 1), []).append(module.get("title") or module.get("module_id", ""))
    week_goals = []
    for week in sorted({int(step["week"]) for step in steps} | set(weeks)):
        titles = "；".join(title for title in weeks.get(week, []) if title)
        text = f"第 {week} 周：{titles}" if titles else f"第 {week} 周：完成本周步骤"
        week_goals.append(
            {
                "id": f"wg{week}",
                "week": week,
                "text": text,
                "due": clock.add_days(clock.today(), 7 * (week - 1) + 6),
                "status": "open",
            }
        )
    plan = {
        "schema_version": SCHEMA_VERSION,
        "plan_id": template.get("plan_id", "plan-v1"),
        "version": 1,
        "authority": "planner",
        "week_goals": week_goals,
        "current_objective": {},
        "steps": steps,
        "minutes_per_week": int(minutes_per_week or template.get("minutes_per_week_default", 12)),
    }
    refresh_objective(plan)
    plan["hash"] = plan_hash(plan)
    return plan


def _authority_view(plan: dict) -> dict:
    """The part of the plan that only the planner may change.

    Step *status* and ``current_objective`` are runtime scheduling state, not
    authoring state: they advance as a consequence of evidence.  Excluding them
    from the hash keeps ``doctor --plan`` meaningful (a silent edit of steps,
    weeks, or objectives is still caught).
    """
    return {
        "plan_id": plan.get("plan_id"),
        "version": plan.get("version"),
        "minutes_per_week": plan.get("minutes_per_week"),
        "week_goals": [
            {"id": goal.get("id"), "week": goal.get("week"), "text": goal.get("text"), "due": goal.get("due")}
            for goal in plan.get("week_goals", [])
        ],
        "steps": [
            {
                "n": step.get("n"),
                "week": step.get("week"),
                "step_id": step.get("step_id"),
                "text": step.get("text"),
                "mentor": step.get("mentor"),
                "activity_id": step.get("activity_id"),
            }
            for step in plan.get("steps", [])
        ],
    }


def plan_hash(plan: dict) -> str:
    return sha256_text(json.dumps(_authority_view(plan), ensure_ascii=False, sort_keys=True))


def stamp_hash(plan: dict) -> str:
    plan["hash"] = plan_hash(plan)
    return plan["hash"]


def active_steps(plan: dict) -> list[dict]:
    return [step for step in plan.get("steps", []) if step.get("status") != "removed"]


def first_active_step(plan: dict) -> dict | None:
    active = active_steps(plan)
    ordered = sorted(active, key=lambda step: int(step.get("n") or 0))
    return ordered[0] if ordered else None


def refresh_objective(plan: dict) -> dict:
    """Derive ``current_objective`` from the earliest unfinished step."""
    ordered = sorted(active_steps(plan), key=lambda step: int(step.get("n") or 0))
    for step in ordered:
        if step.get("status") != "done":
            plan["current_objective"] = {
                "id": step.get("step_id"),
                "text": step.get("text", ""),
                "activity_id": step.get("activity_id", ""),
                "success_criteria": [step.get("evidence")] if step.get("evidence") else [],
                "est_minutes": 20,
                "week": step.get("week", 1),
            }
            return plan["current_objective"]
    plan["current_objective"] = {
        "id": "review-and-transfer",
        "text": "全部步骤已完成：进入复盘、遗忘检查与跨主题迁移",
        "activity_id": "",
        "success_criteria": ["reviewer 复盘通过", "examiner 复测通过"],
        "est_minutes": 20,
        "week": 9,
    }
    return plan["current_objective"]


def find_step(plan: dict, *, step_id: str | None = None, activity_id: str | None = None) -> dict | None:
    for step in plan.get("steps", []):
        if step_id and step.get("step_id") == step_id:
            return step
        if activity_id and step.get("activity_id") == activity_id:
            return step
        if activity_id and step.get("step_id") == activity_id:
            return step
    return None


def module_for(project: dict, activity_id: str | None) -> dict | None:
    if not activity_id:
        return None
    for module in project.get("template_modules", []):
        if activity_id in (module.get("activity_ids") or []) or activity_id == module.get("exam_id"):
            return module
    return None


def node_for(project: dict, plan: dict, activity_id: str | None) -> tuple[str, str]:
    """Map an activity id to a capability node ``(id, label)``."""
    step = find_step(plan, activity_id=activity_id)
    if step:
        return step.get("step_id") or activity_id, step.get("text") or activity_id
    module = module_for(project, activity_id)
    if module:
        return module.get("module_id"), module.get("title") or module.get("module_id")
    objective = plan.get("current_objective") or {}
    if objective.get("id") and objective.get("id") != "review-and-transfer":
        # Exam tasks and ad-hoc probes attach to the objective under test rather
        # than creating a brand-new node for every question id.
        return objective["id"], objective.get("text") or activity_id or "当前目标"
    if activity_id:
        return activity_id, activity_id
    return "general", "当前目标"


def _estimate(text: str, default: int = 20) -> int:
    match = re.search(r"(\d+)\s*分钟", text or "")
    if match:
        return max(1, min(120, int(match.group(1))))
    if "十分钟" in (text or ""):
        return 10
    if "半小时" in (text or ""):
        return 30
    return default


def next_step(studio: dict, capability: dict) -> dict:
    """The single scheduler.  Handoff ``next`` is only a suggestion."""
    plan = studio.get("plan") or {}
    flags = studio.get("flags") or {}
    mentors = studio.get("mentors") or {}

    if not plan.get("steps"):
        return {"mentor": "planner", "kind": "no_plan", "reason": "还没有计划：planner 先做目标澄清并建计划", "step_id": None, "activity_id": None, "action": "先定目标与计划", "est_minutes": 10}

    for mentor in MENTORS:
        for loop in mentors.get(mentor, {}).get("open_loops", []):
            if loop.get("blocking") and loop.get("status", "open") != "closed":
                owner = loop.get("owner") if loop.get("owner") in MENTORS else mentor
                return {
                    "mentor": owner,
                    "kind": "blocking_open_loop",
                    "reason": f"阻塞未决项 {loop.get('id')}：{loop.get('text', '')}",
                    "step_id": None,
                    "activity_id": loop.get("activity_id"),
                    "action": loop.get("text", ""),
                    "est_minutes": int(loop.get("est_minutes") or _estimate(loop.get("text", ""), 10)),
                    "open_loop": loop.get("id"),
                }

    if flags.get("plan_state") in ("empty", "seeded", "diagnosing"):
        return {
            "mentor": "planner",
            "kind": "first_contact",
            "reason": "首次进入：planner 用 ≤4 轮诊断确认目标与周时长，再按计划移交",
            "step_id": None,
            "activity_id": None,
            "action": "用诊断题确认目标与周时长（至少 2 道）",
            "est_minutes": 10,
        }

    pending = capability.get("pending_exam") or {}
    if pending.get("status") in ("open", "requested", "reask", "in_progress", "pending"):
        questions = pending.get("questions") or []
        index = int(pending.get("current_index") or 0)
        current = questions[index] if index < len(questions) else (pending.get("activity_id") or "")
        return {
            "mentor": "examiner",
            "kind": "pending_exam",
            "reason": f"待独立验证 {pending.get('node_id')}：第 {index + 1}/{len(questions) or 3} 题 {current}",
            "step_id": pending.get("step_id"),
            "activity_id": current or pending.get("activity_id"),
            "action": f"独立考核第 {index + 1} 题：{current}",
            "est_minutes": 10,
            "question_id": current,
        }

    ordered = sorted(active_steps(plan), key=lambda step: int(step.get("n") or 0))
    for step in ordered:
        if step.get("status") == "in_progress":
            return {
                "mentor": step.get("mentor") if step.get("mentor") in MENTORS else "coach",
                "kind": "in_progress_step",
                "reason": f"进行中的步骤 {step.get('step_id')}：{step.get('text', '')}",
                "step_id": step.get("step_id"),
                "activity_id": step.get("activity_id"),
                "action": step.get("text", ""),
                "est_minutes": _estimate(str(step.get("text") or ""), 20),
            }
    for step in ordered:
        if step.get("status") == "todo":
            return {
                "mentor": step.get("mentor") if step.get("mentor") in MENTORS else "coach",
                "kind": "next_todo_step",
                "reason": f"计划下一步 {step.get('step_id')}：{step.get('text', '')}",
                "step_id": step.get("step_id"),
                "activity_id": step.get("activity_id"),
                "action": step.get("text", ""),
                "est_minutes": _estimate(str(step.get("text") or ""), 20),
            }

    since_review = int((studio.get("review_counter") or {}).get("since_review", 0))
    every = int((studio.get("review_counter") or {}).get("every", REVIEW_EVERY) or REVIEW_EVERY)
    if since_review >= every:
        return {
            "mentor": "reviewer",
            "kind": "review_due",
            "reason": f"距上次复盘已有 {since_review} 次回合：reviewer 做遗忘检查与下周建议",
            "step_id": None,
            "activity_id": None,
            "action": "复盘与遗忘检查",
            "est_minutes": 10,
        }
    return {
        "mentor": "planner",
        "kind": "planner_review",
        "reason": "所有计划步骤已完成/暂缓：planner 决定是否换周或重排",
        "step_id": None,
        "activity_id": None,
        "action": "决定是否换周或重排计划",
        "est_minutes": 10,
    }


def validate_plan_change(change, by: str, plan: dict) -> list[str]:
    """Return human-readable problems (empty means legal)."""
    problems: list[str] = []
    if not isinstance(change, dict):
        return ["plan_change must be an object"]
    op = change.get("op")
    if op not in PLAN_OPS:
        problems.append(f"op must be one of {', '.join(PLAN_OPS)}")
        return problems
    status = change.get("status", "proposed")
    if status not in ("apply", "proposed"):
        problems.append("status must be 'apply' or 'proposed'")
    if status == "apply" and by != "planner":
        problems.append(f"only planner may request status=apply (got by={by})")
    declared_by = change.get("by")
    if declared_by and declared_by != by:
        problems.append(f"by={declared_by!r} does not match the actual mentor {by!r}")
    if op == "none":
        return problems
    reason = change.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        problems.append("reason is required for a non-none plan change")
    week = change.get("week")
    if not isinstance(week, int) or not 1 <= week <= 8:
        problems.append("week must be an int in 1..8")
    step_id = change.get("step_id")
    if op == "add_step":
        if not isinstance(step_id, str) or not step_id.startswith("new:"):
            problems.append("add_step requires step_id 'new:<slug>'")
    elif op in ("replace_step", "remove_step", "defer_step", "reorder"):
        if not isinstance(step_id, str) or not step_id:
            problems.append(f"{op} requires step_id")
        elif step_id not in {step.get("step_id") for step in plan.get("steps", [])}:
            problems.append(f"step_id {step_id!r} does not exist in the plan")
    if op in ("replace_step", "replan_week") and not str(change.get("detail") or "").strip():
        problems.append(f"{op} requires detail")
    if by != "planner" and op in ("remove_step", "replan_week"):
        problems.append(f"{by} cannot {op}: only planner may remove steps or rewrite week goals")
    if by != "planner" and "success_criteria" in change:
        problems.append(f"{by} cannot change success_criteria: only planner may do that")
    return problems


def sanitize_completion_claims(text: str) -> tuple[str, bool]:
    """Mentor-authored plan text must not assert progress the runtime has not verified."""
    cleaned = text or ""
    changed = False
    for claim, replacement in (
        ("已完成", "进行中（待证据）"),
        ("完成了", "进行中（待证据）"),
        ("已学会", "练习中（待证据）"),
        ("已经掌握", "待验证"),
        ("已掌握", "待验证"),
    ):
        if claim in cleaned:
            cleaned = cleaned.replace(claim, replacement)
            changed = True
    return cleaned, changed


def apply_plan_change(plan: dict, change: dict) -> dict:
    """Mutate ``plan`` in place.  Caller records the event/hashes."""
    before = plan_hash(plan)
    op = change["op"]
    detail = str(change.get("detail") or "").strip()
    step_id = change.get("step_id")
    week = int(change.get("week") or 1)
    summary = ""
    sanitized = False
    if op == "none":
        return {"op": op, "before_hash": before, "after_hash": before, "changed": False, "summary": "无需改动", "sanitized": False}
    if op == "add_step":
        steps = plan.setdefault("steps", [])
        next_n = max([int(step.get("n") or 0) for step in steps] + [0]) + 1
        new_id = step_id or f"new:step-{next_n}"
        steps.append(
            {
                "n": next_n,
                "week": week,
                "step_id": new_id,
                "text": detail or new_id,
                "mentor": change.get("mentor") if change.get("mentor") in MENTORS else "coach",
                "activity_id": change.get("activity_id") or new_id.replace("new:", ""),
                "evidence": change.get("evidence") or "按步骤说明完成",
                "status": "todo",
                "evidence_log": [],
            }
        )
        summary = f"新增步骤 {new_id}"
    elif op == "replace_step":
        step = find_step(plan, step_id=step_id)
        if step:
            cleaned, sanitized = sanitize_completion_claims(detail)
            step["text"] = cleaned or step.get("text", "")
            if change.get("activity_id"):
                step["activity_id"] = change["activity_id"]
            summary = f"替换步骤 {step_id} 的说明"
    elif op == "remove_step":
        step = find_step(plan, step_id=step_id)
        if step:
            step["status"] = "removed"
            summary = f"移除步骤 {step_id}"
    elif op == "defer_step":
        step = find_step(plan, step_id=step_id)
        if step:
            step["week"] = int(step.get("week") or week) + 1
            step["status"] = "todo"
            step["deferred_at"] = clock.now_iso()
            summary = f"顺延步骤 {step_id} 到第 {step['week']} 周"
    elif op == "reorder":
        steps = sorted(plan.get("steps", []), key=lambda item: int(item.get("n") or 0))
        index = next((i for i, item in enumerate(steps) if item.get("step_id") == step_id), None)
        if index is not None:
            target = None
            if detail.startswith("before:"):
                wanted = detail.split(":", 1)[1].strip()
                target = next((i for i, item in enumerate(steps) if item.get("step_id") == wanted), None)
            elif detail.startswith("to:"):
                try:
                    target = int(detail.split(":", 1)[1]) - 1
                except ValueError:
                    target = None
            if target is None:
                target = max(0, index - 1)
            item = steps.pop(index)
            steps.insert(max(0, min(target, len(steps))), item)
            for position, row in enumerate(steps, start=1):
                row["n"] = position
            summary = f"重排 {step_id} 到第 {steps.index(item) + 1} 位"
    elif op == "replan_week":
        cleaned, sanitized = sanitize_completion_claims(detail)
        goal = next((g for g in plan.get("week_goals", []) if int(g.get("week") or 0) == week), None)
        if goal is None:
            plan.setdefault("week_goals", []).append(
                {"id": f"wg{week}", "week": week, "text": cleaned, "due": clock.add_days(clock.today(), 7 * week), "status": "open"}
            )
        else:
            goal["text"] = cleaned
            goal["status"] = "open"
        summary = f"重排第 {week} 周目标"
    plan["version"] = int(plan.get("version") or 1) + 1
    refresh_objective(plan)
    after = plan_hash(plan)
    plan["hash"] = after
    return {
        "op": op,
        "before_hash": before,
        "after_hash": after,
        "changed": True,
        "summary": summary,
        "sanitized": bool(sanitized),
    }


def advance_step(plan: dict, step_id: str | None, *, event_id: str, verified: bool) -> dict | None:
    """Record scheduling progress for a step and refresh the objective."""
    step = find_step(plan, step_id=step_id) if step_id else None
    if not step:
        return None
    before = step.get("status")
    step.setdefault("evidence_log", []).append({"event_id": event_id, "verified": bool(verified), "at": clock.now_iso()})
    if verified:
        step["status"] = "done"
    elif before == "todo":
        step["status"] = "in_progress"
    refresh_objective(plan)
    return {"step_id": step.get("step_id"), "from": before, "to": step.get("status")}
