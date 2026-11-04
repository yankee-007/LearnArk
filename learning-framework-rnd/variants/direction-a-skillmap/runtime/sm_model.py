"""SkillMap domain model (direction A).

Pure functions and constants: the competency map, derived node status, the
``next-v1`` ordering, spaced-repetition arithmetic and the read-only curriculum
loader.  No files are written from here; everything is deterministic given the
input documents so that ``next --json`` is byte-identical for identical state.

Authoritative sources:
* ``design.md`` §4 (map), §5 (stages), §7 (state model + next-v1), §8 (SRS).
* ``templates/agent-dev.md`` §2 and ``templates/email.md`` §2 (node tables).
* ``curriculum/*.md`` (teaching seeds, parsed lazily by :func:`load_curriculum`).
"""

from __future__ import annotations

import re
from pathlib import Path

SCHEMA_VERSION = 1
RULE_VERSION = "next-v1"
#: Availability gate: a node becomes selectable once **every prereq is >= L1**.
#: L1 only means "can restate", so a successor may start; it is *not* mastery.
AVAILABILITY_GATE = 1
#: Mastery gate (design §4): a prereq at L2 is independently applied.  Used for
#: documentation and for the `level_cap`/placement copy, never to hide work from
#: a learner whose prereq reached L1 through evidence.
MASTERY_GATE = 2
#: Kept for backward-compatible state files written before v0.1.1 (map["gate"]).
GATE = AVAILABILITY_GATE
REVIEW_INTERVALS = [1, 3, 7, 16, 35]
MAX_REVIEW_PER_SESSION = 2
#: Sessions at or below this many minutes do one review node only.
SHORT_SESSION_MINUTES = 20
#: Below this end-to-end budget a session runs at most 2 probes (~3 minutes)
#: and defers the rest, so the learner still gets a closable activity.
SHORT_DIAGNOSIS_MINUTES = 30
SHORT_DIAGNOSIS_PROBES = 2
MIN_ACTIVITY_MINUTES = 5
#: Time reserved at the end of a session for handoff / review of the answer.
SESSION_RESERVE_MINUTES = 2
#: Planning estimate per probe (a probe is one short Q&A, not a lesson).
DIAGNOSIS_MINUTES_PER_PROBE = 1.5

STAGES = ("explain", "drill", "apply", "check")
STAGE_MENTORS = {
    "explain": "concept",
    "drill": "coach",
    "apply": "coach",
    "check": "examiner",
}
STAGE_LABELS = {"explain": "讲解", "drill": "操练", "apply": "应用", "check": "检查"}
MENTORS = ("navigator", "concept", "coach", "examiner")
MENTOR_LABELS = {
    "navigator": "导航导师",
    "concept": "概念导师",
    "coach": "操练导师",
    "examiner": "考核导师",
}
#: Which mentors the user may switch to while a stage owns the session.
#: ``navigator`` is always allowed: it owns diagnosis, review and handoff.
#: ``concept`` is allowed **on demand** in every learning stage (a learner may
#: always ask for an explanation again); the switch is recorded as
#: ``on_demand_switch`` so evidence still shows who was teaching.
STAGE_ALLOWED = {
    "diagnose": ("navigator",),
    "explain": ("navigator", "concept"),
    "drill": ("navigator", "coach"),
    "apply": ("navigator", "coach"),
    "check": ("navigator", "examiner"),
    "review": ("navigator", "examiner"),
}
ON_DEMAND_MENTORS = ("concept",)
MENTOR_REASONS = {
    "navigator": "定位、复习安排与交接",
    "concept": "讲解与类比（随时可按需要求）",
    "coach": "操练与应用辅导（drill/apply 默认）",
    "examiner": "检查与迁移题（零提示）",
}
ACTIVITY_RE = re.compile(r"^(?P<node>[A-Z]\d)-(?P<stage>explain|drill|apply|check)$")
RESERVED_ACTIVITIES = ("diagnose", "review", "handoff")
SKIP_ANSWERS = {
    "",
    "?",
    "？",
    "不知道",
    "不懂",
    "不会",
    "不清楚",
    "跳过",
    "先跳过",
    "skip",
    "unknown",
    "pass",
    "idk",
}

#: Node tables mirror ``templates/<template>.md`` §2 exactly (ids, titles,
#: clusters, prereqs, target level).  ``init`` writes them into ``map.json``.
TEMPLATES: dict[str, dict] = {
    "agent-dev": {
        "title": "Agent 开发",
        "default_goal": "能独立设计与实现最小可用 Agent：调用、工具、循环、记忆、评测",
        "default_minutes_per_week": 600,
        "clusters": ["foundation", "llm", "tools", "memory", "evaluation"],
        "nodes": [
            ("A1", "Python 数据结构与异常", "foundation", [], 3),
            ("A2", "HTTP/API 与 JSON 边界", "foundation", ["A1"], 3),
            ("B1", "消息结构与角色", "llm", ["A2"], 3),
            ("B2", "结构化输出与解析", "llm", ["B1"], 3),
            ("B3", "超时/限流/重试", "llm", ["B2"], 3),
            ("C1", "工具 schema 定义", "tools", ["B1"], 3),
            ("C2", "调用往返", "tools", ["C1", "B2"], 3),
            ("C3", "Agent 循环与终止", "tools", ["C2", "B3"], 3),
            ("C4", "错误处理与幂等", "tools", ["C3"], 3),
            ("D1", "会话记忆与上下文预算", "memory", ["C3"], 3),
            ("D2", "RAG 边界（何时不该检索）", "memory", ["D1", "C2"], 3),
            ("E1", "评测集与回归", "evaluation", ["C3", "C4"], 3),
        ],
        "probes": [
            ("Q1", "B1", "用自己的话讲一次 tool call 的一来一回：模型输出什么？你的代码做什么？结果怎么回到模型那里？"),
            ("Q2", "C2", "读出这段伪代码里终止条件的 bug，并说明它为什么停不下来：\n      i = 0\n      while i < 5:\n          call_tool()\n          i += 0"),
            ("Q3", "D2", "RAG 与会话记忆的区别是什么？各自解决什么问题、什么时候会失效？"),
            ("Q4", "A2", "一次 HTTP 调用超时了，你会怎么处理？请说到异常类型、超时分层与是否重试。"),
            ("Q5", "E1", "给一个只做加法的小工具任务设计最小评测：用例从哪来、怎么判定通过。"),
        ],
    },
    "email": {
        "title": "英文工作邮件写作",
        "default_goal": "能在常见工作场景写出结构清楚、语气得体、可直接发送的英文邮件",
        "default_minutes_per_week": 180,
        "clusters": ["drafting", "voice", "fit"],
        "nodes": [
            ("W1", "结构与请求", "drafting", [], 3),
            ("W6", "主题行与首句", "drafting", ["W1"], 2),
            ("W2", "语气与关系", "voice", ["W1"], 3),
            ("W3", "清晰度与简洁", "voice", ["W2"], 3),
            ("W4", "场景适配", "fit", ["W3"], 3),
            ("W5", "修改与自查", "fit", ["W4"], 2),
        ],
        "probes": [
            ("Q1", "W2", "把 “Please provide the data today.” 改写成对上级的请求：保留紧迫感，但不失礼。"),
            (
                "Q2",
                "W1",
                "下面这封 6 句邮件把结论放在最后一句。指出结构问题，并给出你的改法。\n"
                "材料：\n"
                "    Hi Mark, sorry to bother you again about the launch.\n"
                "    We had a few delays on our side.\n"
                "    The design files came in later than expected.\n"
                "    I have attached the updated timeline.\n"
                "    The new target date is November 12.\n"
                "    Could you confirm by Friday whether that works? — Tina",
            ),
            ("Q3", "W4", "项目延期两周、需要对方批准新排期。列出这封邮件的 3 段大纲。"),
        ],
    },
}

DEFAULT_TEMPLATE = "agent-dev"


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------
def template_names() -> list[str]:
    return sorted(TEMPLATES)


def template_spec(name: str) -> dict:
    return TEMPLATES.get(name) or TEMPLATES[DEFAULT_TEMPLATE]


def is_known_template(name: str) -> bool:
    return name in TEMPLATES


def default_goal(template: str) -> str:
    return template_spec(template)["default_goal"]


def default_minutes_per_week(template: str) -> int:
    return int(template_spec(template)["default_minutes_per_week"])


def clusters(template: str) -> list[str]:
    return list(template_spec(template)["clusters"])


def cluster_index(template: str, cluster: str) -> int:
    order = clusters(template)
    return order.index(cluster) if cluster in order else len(order)


def probe_defs(template: str) -> list[dict]:
    return [
        {"id": pid, "node": node, "question": question}
        for pid, node, question in template_spec(template)["probes"]
    ]


def total_probes(template: str) -> int:
    return len(probe_defs(template))


# ---------------------------------------------------------------------------
# map construction
# ---------------------------------------------------------------------------
def new_node(node_id: str, title: str, cluster: str, prereqs: list[str], target: int, template: str) -> dict:
    return {
        "id": node_id,
        "title": title,
        "cluster": cluster,
        "cluster_index": cluster_index(template, cluster),
        "prereqs": list(prereqs),
        "level": 0,
        "target_level": int(target),
        "level_source": "initial",
        "gate_override": False,
        "evidence": [],
        "review": {"interval_index": 0, "due": None, "lapses": 0, "last_review_at": None},
        "status": "locked",
        "misconceptions": [],
        "updated_at": None,
    }


def new_map(template: str) -> dict:
    spec = template_spec(template)
    nodes = [new_node(nid, title, cluster, prereqs, target, template) for nid, title, cluster, prereqs, target in spec["nodes"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "template": template,
        "gate": GATE,
        "rule_version": RULE_VERSION,
        "review_intervals": list(REVIEW_INTERVALS),
        "nodes": nodes,
        "updated_at": None,
    }


def nodes_of(map_doc: dict) -> list[dict]:
    return list(map_doc.get("nodes") or [])


def by_id(map_doc: dict) -> dict[str, dict]:
    return {node["id"]: node for node in nodes_of(map_doc)}


def node_order(map_doc: dict) -> list[str]:
    return [node["id"] for node in nodes_of(map_doc)]


def ensure_map_shape(map_doc: dict, template: str) -> dict:
    """Rebuild missing nodes in place (a repaired or hand-edited map)."""
    if not nodes_of(map_doc):
        return new_map(template)
    known = {node.get("id") for node in map_doc["nodes"]}
    for nid, title, cluster, prereqs, target in template_spec(template)["nodes"]:
        if nid not in known:
            map_doc["nodes"].append(new_node(nid, title, cluster, prereqs, target, template))
    for node in map_doc["nodes"]:
        node.setdefault("prereqs", [])
        node.setdefault("level", 0)
        node.setdefault("target_level", 3)
        node.setdefault("cluster", "unsorted")
        node.setdefault("cluster_index", cluster_index(template, node.get("cluster", "")))
        node.setdefault("level_source", "initial")
        node.setdefault("gate_override", False)
        node.setdefault("evidence", [])
        node.setdefault("misconceptions", [])
        review = node.setdefault("review", {})
        review.setdefault("interval_index", 0)
        review.setdefault("due", None)
        review.setdefault("lapses", 0)
        review.setdefault("last_review_at", None)
    map_doc.setdefault("schema_version", SCHEMA_VERSION)
    # v0.1.1 lowered the *availability* gate from L2 to L1; old snapshots stored
    # gate=2.  Normalise on every load so the design, code and state agree.
    map_doc["gate"] = AVAILABILITY_GATE
    map_doc.setdefault("template", template)
    return map_doc


# ---------------------------------------------------------------------------
# derived status (design §7: computed at read time, never trusted from cache)
# ---------------------------------------------------------------------------
def prereqs_ready(node: dict, index: dict[str, dict], gate: int = GATE) -> bool:
    return all(index[p]["level"] >= gate for p in node.get("prereqs", []) if p in index)


def unmet_prereqs(node: dict, index: dict[str, dict], gate: int = GATE) -> list[tuple[str, int]]:
    return [(p, index[p]["level"]) for p in node.get("prereqs", []) if p in index and index[p]["level"] < gate]


def node_status(node: dict, index: dict[str, dict], current_node: str | None, today: str, gate: int = GATE) -> str:
    """``mastered`` > ``review_due`` > ``decayed`` > ``locked`` > ``in_progress`` > ``available``."""
    if int(node.get("level", 0)) >= 3:
        return "mastered"
    review = node.get("review") or {}
    due = review.get("due")
    if due and due <= today and int(node.get("level", 0)) >= 1:
        return "review_due"
    if int(review.get("lapses", 0)) >= 2:
        return "decayed"
    if not prereqs_ready(node, index, gate) and not node.get("gate_override"):
        return "locked"
    if current_node and node.get("id") == current_node:
        return "in_progress"
    return "available"


def refresh_statuses(map_doc: dict, plan: dict, today: str) -> list[dict]:
    """Recompute every node status.  Returns drift entries (cache was stale)."""
    index = by_id(map_doc)
    current = plan.get("current_node")
    drifts = []
    for node in nodes_of(map_doc):
        derived = node_status(node, index, current, today)
        cached = node.get("status")
        if cached is not None and cached != derived:
            drifts.append({"node": node["id"], "cached": cached, "derived": derived})
        node["status"] = derived
    return drifts


def status_counts(map_doc: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes_of(map_doc):
        status = node.get("status") or "available"
        counts[status] = counts.get(status, 0) + 1
    return counts


def level_counts(map_doc: dict) -> dict[str, int]:
    counts = {"L0": 0, "L1": 0, "L2": 0, "L3": 0}
    for node in nodes_of(map_doc):
        counts[f"L{int(node.get('level', 0))}"] = counts.get(f"L{int(node.get('level', 0))}", 0) + 1
    return counts


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------
def stage_for(node: dict, plan: dict) -> str:
    """First unfinished stage for a node, given the plan's live progress."""
    progress = plan.get("stage_progress") or {}
    if progress.get("node") == node.get("id") and not progress.get("passed", False):
        stage = progress.get("stage")
        if stage in STAGES:
            return stage
    level = int(node.get("level", 0))
    if level <= 0:
        return "explain"
    if level == 1:
        return "drill"
    return "check"


def stage_incomplete(plan: dict, node_id: str) -> bool:
    progress = plan.get("stage_progress") or {}
    return progress.get("node") == node_id and not progress.get("passed", False)


def fresh_progress(node_id: str, stage: str) -> dict:
    return {
        "node": node_id,
        "stage": stage,
        "passed": False,
        "explain_turns": 0,
        "explain_points": 0,
        "drill_streak": 0,
        "apply_artifact": None,
        "apply_correct": 0,
        "check_correct": 0,
        "started_at": None,
        "turn_count": 0,
    }


def next_stage(stage: str) -> str | None:
    try:
        index = STAGES.index(stage)
    except ValueError:
        return None
    return STAGES[index + 1] if index + 1 < len(STAGES) else None


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage)


def mentor_for_stage(stage: str) -> str:
    return STAGE_MENTORS.get(stage, "navigator")


def stage_allowed(stage: str) -> tuple[str, ...]:
    return STAGE_ALLOWED.get(stage, MENTORS)


# ---------------------------------------------------------------------------
# budget & mentors
# ---------------------------------------------------------------------------
def diagnosis_minutes(minutes_budget: int | None, probe_count: int | None = None) -> int:
    """Planned diagnosis time for this session (~1.5 min per probe)."""
    limit = probe_limit(minutes_budget)
    probes = limit if limit is not None else (probe_count if probe_count is not None else 5)
    return int(round(probes * DIAGNOSIS_MINUTES_PER_PROBE))


def estimate_minutes(minutes_budget: int | None, *, diagnosis_spent: int = 0) -> int:
    """Estimated minutes for one activity inside the **end-to-end** budget.

    A 20-minute session is not "6 minutes of diagnosis + a 20-minute lesson";
    the lesson gets ``budget - diagnosis - reserve`` so that everything the card
    promises fits in the session.  The old model always said "20 or 45".
    """
    if not minutes_budget:
        return 45
    budget = max(MIN_ACTIVITY_MINUTES, int(minutes_budget))
    base = 20 if budget <= SHORT_SESSION_MINUTES else 45
    remaining = budget - max(0, int(diagnosis_spent)) - SESSION_RESERVE_MINUTES
    return max(MIN_ACTIVITY_MINUTES, min(base, remaining))


def budget_breakdown(minutes_budget: int | None, diagnosis_spent: int | None = None) -> dict:
    """Card arithmetic: diagnosis + activity + reserve = budget."""
    if not minutes_budget:
        return {"budget": None, "diagnosis": 0, "activity": 45, "reserve": 0}
    spent = diagnosis_minutes(minutes_budget) if diagnosis_spent is None else max(0, int(diagnosis_spent))
    activity = estimate_minutes(minutes_budget, diagnosis_spent=spent)
    return {"budget": int(minutes_budget), "diagnosis": spent, "activity": activity, "reserve": SESSION_RESERVE_MINUTES}


def is_short_diagnosis(minutes_budget: int | None) -> bool:
    return bool(minutes_budget) and int(minutes_budget) < SHORT_DIAGNOSIS_MINUTES


def probe_limit(minutes_budget: int | None) -> int | None:
    """How many probes this session may ask (None = all of them).

    Below 30 minutes the diagnosis is capped at 2 probes (~3 min) so the learner
    still has time for a closable activity.
    """
    return SHORT_DIAGNOSIS_PROBES if is_short_diagnosis(minutes_budget) else None


def user_allowed(stage: str) -> tuple[str, ...]:
    """Mentors the learner may switch to in this stage (on-demand included)."""
    allowed = list(STAGE_ALLOWED.get(stage, MENTORS))
    if stage not in ("diagnose", "review"):
        for mentor in ON_DEMAND_MENTORS:
            if mentor not in allowed:
                allowed.append(mentor)
    return tuple(allowed)


def auto_allowed(stage: str) -> tuple[str, ...]:
    """Mentors the runtime itself may pick for a stage (no on-demand extras)."""
    return STAGE_ALLOWED.get(stage, MENTORS)


def mentor_reason(mentor: str) -> str:
    return MENTOR_REASONS.get(mentor, "")


def mentor_catalog(stage: str) -> list[dict]:
    """One-line discoverable list used by `status` and `start`."""
    current = auto_allowed(stage)[-1] if stage in STAGE_ALLOWED else "navigator"
    rows = []
    for mentor in user_allowed(stage):
        rows.append(
            {
                "id": mentor,
                "label": MENTOR_LABELS.get(mentor, mentor),
                "reason": mentor_reason(mentor),
                "default": mentor == current,
                "on_demand": mentor in ON_DEMAND_MENTORS and mentor not in auto_allowed(stage),
            }
        )
    return rows


def review_due_today(node: dict, today: str) -> bool:
    review = node.get("review") or {}
    due = review.get("due")
    return bool(due) and due <= today and int(node.get("level", 0)) >= 1


def due_nodes(map_doc: dict, today: str) -> list[dict]:
    due = [node for node in nodes_of(map_doc) if review_due_today(node, today)]
    due.sort(key=lambda n: ((n.get("review") or {}).get("due") or "", n.get("cluster_index", 0), n["id"]))
    return due


def sort_key(node: dict, plan: dict, today: str) -> tuple:
    """Ascending 5-key order: review_due, current-stage-incomplete, level, cluster, id."""
    due_rank = 0 if review_due_today(node, today) else 1
    current_rank = 0 if stage_incomplete(plan, node["id"]) else 1
    return (due_rank, current_rank, int(node.get("level", 0)), int(node.get("cluster_index", 0)), node["id"])


def _exclude_reason(node: dict, index: dict[str, dict], gate: int) -> str:
    level = int(node.get("level", 0))
    if level >= 3:
        return f"{node['id']}：已达 L3（mastered），目标完成"
    unmet = unmet_prereqs(node, index, gate)
    if unmet and not node.get("gate_override"):
        parts = "、".join(f"{pid} 为 L{pl}" for pid, pl in unmet)
        return f"{node['id']}：先修 {parts}，低于门槛 L{gate}"
    return f"{node['id']}：已被选为当前节点"


def next_decision(
    map_doc: dict,
    plan: dict,
    today: str,
    minutes_budget: int | None = None,
    *,
    estimated_minutes: int | None = None,
) -> dict:
    """Deterministic ``next-v1`` decision; contains no timestamps on purpose."""
    gate = int(map_doc.get("gate", GATE))
    index = by_id(map_doc)
    candidates: list[dict] = []
    excluded: list[dict] = []
    for node in nodes_of(map_doc):
        level = int(node.get("level", 0))
        if level >= 3:
            excluded.append({"node": node["id"], "title": node["title"], "level": level, "reason": _exclude_reason(node, index, gate)})
            continue
        if not prereqs_ready(node, index, gate) and not node.get("gate_override"):
            excluded.append({"node": node["id"], "title": node["title"], "level": level, "reason": _exclude_reason(node, index, gate)})
            continue
        candidates.append(node)

    candidates.sort(key=lambda n: sort_key(n, plan, today))
    selected = candidates[0] if candidates else None

    reasons: list[str] = []
    selected_payload = None
    if selected is not None:
        stage = stage_for(selected, plan)
        due = review_due_today(selected, today)
        review = selected.get("review") or {}
        current = plan.get("current_node")

        if due:
            reasons.append(f"复习到期优先：{selected['id']} 的复习日 {review.get('due')} 已到（due ≤ {today}），先做提取练习再学新内容")
        else:
            next_due = next_due_node(map_doc, today)
            reasons.append(
                f"无到期复习：队列里没有 due ≤ {today} 的节点"
                + (f"（最近到期 {next_due['id']} · {next_due['review']['due']}）" if next_due else "（尚无复习安排）")
            )

        placement = plan.get("placement") or {}
        placed_here = placement.get("node") == selected["id"] and placement.get("stage") == stage
        if stage_incomplete(plan, selected["id"]) and placed_here and placement.get("reason"):
            reasons.append(placement["reason"])
        elif stage_incomplete(plan, selected["id"]):
            reasons.append(f"阶段续做：上次停在 {selected['id']} 的 {stage_label(stage)}（{selected['id']}-{stage}），先收口再换节点")
        elif current and current != selected["id"]:
            reasons.append(f"切换节点：{current} 的当前阶段已完成，改推 {selected['id']} 的 {stage_label(stage)}")
        else:
            reasons.append(f"阶段起点：{selected['id']} 从 {stage_label(stage)}（{selected['id']}-{stage}）开始，未完成阶段优先")

        if unmet_prereqs(selected, index, gate) and selected.get("gate_override"):
            reasons.append(f"先修门槛预警：{selected['id']} 已越过先修门槛（等级上限锁 L1）")
        else:
            prereq_txt = "、".join(f"{p} L{index[p]['level']}" for p in selected.get("prereqs", [])) or "无先修"
            reasons.append(
                f"等级最低 + 簇顺序：{selected['id']} 当前 L{int(selected.get('level', 0))}（目标 L{selected.get('target_level', 3)}），"
                f"先修 {prereq_txt} 均已 ≥L{gate}；同为候选时按 {selected.get('cluster', '')} 簇第 {int(selected.get('cluster_index', 0)) + 1} 位、"
                f"节点 id {selected['id']} 排序"
            )

        selected_payload = {
            "node": selected["id"],
            "title": selected["title"],
            "cluster": selected["cluster"],
            "level": int(selected.get("level", 0)),
            "target_level": int(selected.get("target_level", 3)),
            "status": selected.get("status"),
            "stage": stage,
            "stage_label": stage_label(stage),
            "activity_id": f"{selected['id']}-{stage}",
            "mentor": mentor_for_stage(stage),
            "gate_override": bool(selected.get("gate_override")),
        }

    return {
        "rule_version": RULE_VERSION,
        "gate": gate,
        "today": today,
        "minutes_budget": int(minutes_budget or 0),
        "estimated_minutes": int(estimated_minutes) if estimated_minutes is not None else estimate_minutes(minutes_budget),
        "budget_breakdown": budget_breakdown(minutes_budget, plan.get("diagnosis_minutes")),
        "selected": selected_payload,
        "reasons": reasons,
        "placement": (plan.get("placement") or {}).get("node") and {
            key: (plan.get("placement") or {}).get(key) for key in ("node", "level", "probe", "stage", "reason")
        },
        "candidates": [
            {
                "node": node["id"],
                "level": int(node.get("level", 0)),
                "stage": stage_for(node, plan),
                "sort_key": list(sort_key(node, plan, today)),
            }
            for node in candidates
        ],
        "excluded": excluded,
        "review_due": [node["id"] for node in due_nodes(map_doc, today)],
    }


def next_due_node(map_doc: dict, today: str) -> dict | None:
    upcoming = [
        node
        for node in nodes_of(map_doc)
        if (node.get("review") or {}).get("due") and int(node.get("level", 0)) >= 1
    ]
    upcoming.sort(key=lambda n: (n["review"]["due"], n.get("cluster_index", 0), n["id"]))
    return upcoming[0] if upcoming else None


# ---------------------------------------------------------------------------
# spaced repetition (design §8)
# ---------------------------------------------------------------------------
def review_pass(node: dict, today: str) -> dict:
    review = node.setdefault("review", {"interval_index": 0, "due": None, "lapses": 0, "last_review_at": None})
    index = min(int(review.get("interval_index", 0)) + 1, len(REVIEW_INTERVALS) - 1)
    review["interval_index"] = index
    review["due"] = add_days(today, REVIEW_INTERVALS[index])
    review["last_review_at"] = today
    return {"interval_index": index, "due": review["due"], "interval_days": REVIEW_INTERVALS[index]}


def review_fail(node: dict, today: str) -> dict:
    review = node.setdefault("review", {"interval_index": 0, "due": None, "lapses": 0, "last_review_at": None})
    index = max(int(review.get("interval_index", 0)) - 2, 0)
    review["interval_index"] = index
    review["lapses"] = int(review.get("lapses", 0)) + 1
    review["due"] = add_days(today, REVIEW_INTERVALS[index])
    review["last_review_at"] = today
    return {"interval_index": index, "due": review["due"], "interval_days": REVIEW_INTERVALS[index], "lapses": review["lapses"]}


def schedule_after_check(node: dict, today: str, interval_index: int = 2) -> dict:
    review = node.setdefault("review", {"interval_index": 0, "due": None, "lapses": 0, "last_review_at": None})
    index = max(0, min(int(interval_index), len(REVIEW_INTERVALS) - 1))
    review["interval_index"] = index
    review["due"] = add_days(today, REVIEW_INTERVALS[index])
    review["last_review_at"] = today
    return {"interval_index": index, "due": review["due"], "interval_days": REVIEW_INTERVALS[index]}


def add_days(iso_date: str, days: int) -> str:
    from datetime import date, timedelta

    base = date.fromisoformat(iso_date[:10])
    return (base + timedelta(days=int(days))).isoformat()


# ---------------------------------------------------------------------------
# review selection
# ---------------------------------------------------------------------------
def review_limit(minutes_budget: int | None) -> int:
    if minutes_budget and int(minutes_budget) <= SHORT_SESSION_MINUTES:
        return 1
    return MAX_REVIEW_PER_SESSION


# ---------------------------------------------------------------------------
# answers / activity ids
# ---------------------------------------------------------------------------
def is_skip_answer(answer: str) -> bool:
    text = (answer or "").strip().strip("。.!！?？~ ")
    return text.lower() in SKIP_ANSWERS


def parse_activity(activity_id: str) -> tuple[str | None, str | None]:
    match = ACTIVITY_RE.match(activity_id or "")
    if match:
        return match.group("node"), match.group("stage")
    if activity_id in RESERVED_ACTIVITIES:
        return None, activity_id
    return None, None


def valid_activity(activity_id: str) -> bool:
    if not isinstance(activity_id, str) or not activity_id.strip():
        return False
    node, stage = parse_activity(activity_id.strip())
    return bool(node and stage) or activity_id.strip() in RESERVED_ACTIVITIES


def activity_for(node_id: str, stage: str) -> str:
    return f"{node_id}-{stage}"


# ---------------------------------------------------------------------------
# curriculum (read-only teaching seeds shipped next to the runtime)
# ---------------------------------------------------------------------------
_SECTION_RE = re.compile(r"^##\s+(?P<id>[A-Z]\d)\s+(?P<title>.+?)\s*$")
_BULLET_RE = re.compile(r"^-\s+\*\*(?P<key>[^*]+)\*\*[：:]\s*(?P<value>.+)$")
_KEY_MAP = {
    "要点": "points",
    "误解": "misconceptions",
    "drill": "drill",
    "apply": "apply",
    "check": "check",
    "评分": "scoring",
    "评价标准": "criteria",
    "示例任务": "task",
}


def curriculum_path(variant_dir: str | Path, template: str) -> Path:
    return Path(variant_dir) / "curriculum" / f"{template}.md"


def load_curriculum(variant_dir: str | Path, template: str) -> dict[str, dict]:
    """Parse ``curriculum/<template>.md`` into ``{node_id: {title, points, ...}}``.

    Missing or unreadable curriculum is not fatal: the runtime falls back to the
    node table so that a stripped checkout still runs.
    """
    path = curriculum_path(variant_dir, template)
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, dict] = {}
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        section = _SECTION_RE.match(line)
        if section:
            current = {"id": section.group("id"), "title": section.group("title").strip(), "raw": []}
            out[current["id"]] = current
            continue
        if line.startswith("## "):
            current = None
            continue
        if current is None:
            continue
        current["raw"].append(line)
        bullet = _BULLET_RE.match(line.strip())
        if bullet:
            key = _KEY_MAP.get(bullet.group("key").strip())
            if key:
                current[key] = bullet.group("value").strip()
    return out
