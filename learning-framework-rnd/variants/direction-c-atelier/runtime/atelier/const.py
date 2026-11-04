"""Fixed vocabulary for the Atelier studio."""

from __future__ import annotations

MENTORS: tuple[str, ...] = ("planner", "concept", "coach", "examiner", "reviewer")


def format_weekly(minutes) -> str:
    """Render minutes-per-week as hours (v0.2.3 fixes the 60x unit bug)."""
    try:
        value = float(minutes)
    except (TypeError, ValueError):
        return "? 小时"
    hours = value / 60.0
    if abs(hours - round(hours)) < 0.01:
        return f"{int(round(hours))} 小时"
    return f"{hours:.1f} 小时"


def format_weekly_scope(scope: dict) -> str:
    """Render a learner/project/plan scope, including an explicit weekly range."""
    scope = scope or {}
    pair = scope.get("weekly_range_minutes")
    if isinstance(pair, (list, tuple)) and len(pair) == 2:
        try:
            low, high = float(pair[0]) / 60.0, float(pair[1]) / 60.0
            return f"{low:g}–{high:g} 小时"
        except (TypeError, ValueError):
            pass
    return format_weekly(scope.get("minutes_per_week"))


MENTOR_LABELS = {
    "planner": "策划导师 planner",
    "concept": "概念导师 concept",
    "coach": "练习导师 coach",
    "examiner": "考核导师 examiner",
    "reviewer": "复盘导师 reviewer",
}
MENTOR_DUTIES = {
    "planner": "目标澄清 / 周目标 / 排序 / 时间预算",
    "concept": "最小模型 / 类比 / 反例 / 复述",
    "coach": "分级提示 / 调试 / 拆步",
    "examiner": "迁移题 / 判定 / verified 证据",
    "reviewer": "复盘 / 遗忘检查 / 下周建议",
}

# Capability levels.  Only the runtime decides these; mentor text never does.
LEVEL_LABELS = {
    0: "未验证",
    1: "自述接触",
    2: "受助接触",
    3: "练习观察",
    4: "独立验证",
    5: "稳定保持",
}
MAX_LEVEL = 5

# Journal kinds that count as shared evidence for the projection.
PROJECTION_KINDS = (
    "mentor_turn",
    "attempt",
    "practice_attempt",
    "assisted",
    "capability_upgrade",
    "capability_decay",
    "misconception_observed",
    "mentor_verdict_conflict",
    "handoff",
    "plan_change_applied",
    "review",
    "exam",
    "exam_requested",
    "hint_refused",
    "authority_violation",
    "examiner_help_violation",
)

HANDOFF_CONTENT_FIELDS = ("why", "known", "what_tried", "do_not_redo", "open_loops", "next")
HANDOFF_PROTOCOL_FIELDS = ("handoff_id", "schema_version", "from", "to", "created_at")
HANDOFF_REQUIRED_FIELDS = HANDOFF_PROTOCOL_FIELDS + HANDOFF_CONTENT_FIELDS

HANDOFF_LIMITS = {
    "known": (5, 120),
    "what_tried": (5, 120),
    "do_not_redo": (6, 120),
    "open_loops": (5, 200),
    "next": (1, 200),
    "why": (1, 400),
}

CONTEXT_LIMIT = 6000
HANDOFF_CONTEXT_LIMIT = 1200
HANDOFF_STALE_DAYS = 7
REVIEW_EVERY = 4

PLAN_OPS = (
    "add_step",
    "replace_step",
    "remove_step",
    "reorder",
    "replan_week",
    "defer_step",
    "none",
)

HINT_KEYWORDS = (
    "给点提示",
    "给个提示",
    "提示一下",
    "给点线索",
    "直接给答案",
    "给我答案",
    "帮我写",
    "帮我做",
    "你先讲讲",
    "解释一下这题",
    "hint",
)

MENTOR_NAME_WORDS = {
    "planner": ("planner", "策划导师", "策划", "计划导师"),
    "concept": ("concept", "概念导师", "概念", "讲解"),
    "coach": ("coach", "练习导师", "教练", "陪练", "卡住", "报错"),
    "examiner": ("examiner", "考核导师", "考官", "考核", "考我", "考一次"),
    "reviewer": ("reviewer", "复盘导师", "复盘", "回顾"),
}

NAMED_INTENT_WORDS = {
    "examiner": ("考我", "考考我", "考核", "考一次"),
    "reviewer": ("复盘", "回顾"),
    "planner": ("排计划", "定计划", "改计划", "排个计划"),
    "concept": ("讲概念", "讲解一下", "讲明白"),
    "coach": ("卡住了", "又报错", "陪我调", "找教练"),
}

# Which mentor turns may legally raise which evidence source.
SOURCE_CAP = {"self_report": 1, "assisted": 2, "observed": 3, "verified": 4}
