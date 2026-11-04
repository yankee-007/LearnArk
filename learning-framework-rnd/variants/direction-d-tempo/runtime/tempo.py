"""Tempo (direction D) runtime: budget parsing, deterministic scheduling, SRS, evidence.

The module is deliberately pure where it matters:

* ``parse_budget`` turns free text into minutes with regexes only (no LLM, no I/O);
* ``select_activities`` turns ``(candidates, minutes, today-facts)`` into a ranked
  decision with no randomness, no clock and no journal access, so D-S1/D-S2/D-S3
  can be asserted byte-for-byte;
* everything that writes goes through ``Store`` (atomic documents + append-only
  journal), and every write carries a stable ``dedupe_key``.

The scheduler is authoritative. Mentors may *suggest* (``next``) but the runtime
records the suggestion and keeps its own schedule; levels only move on evidence.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

from learncore import clock
from learncore.events import Journal
from learncore.fsutil import (
    LearnError,
    StateCorrupt,
    atomic_write_text,
    file_lock,
    load_json_state,
    read_json,
    sha256_text,
    write_json,
)
from learncore.store import Document

VARIANT_ID = "direction-d-tempo"
VARIANT_VERSION = "0.2.6"
SCHEMA_VERSION = 1

# --------------------------------------------------------------------------------------
# Constants of the direction design
# --------------------------------------------------------------------------------------

ACTIVITY_TYPES = ("recall_card", "concept_block", "explain_back", "code_kata", "writing_block", "quiz", "transfer_task")

#: canonical duration per activity (design §4); block steps may override within range
ACTIVITY_MINUTES = {
    "recall_card": 5,
    "concept_block": 10,
    "explain_back": 8,
    "code_kata": 15,
    "writing_block": 15,
    "quiz": 6,
    "transfer_task": 15,
}

ACTIVITY_MENTOR = {
    "recall_card": "trainer",
    "concept_block": "coach",
    "explain_back": "coach",
    "code_kata": "trainer",
    "writing_block": "trainer",
    "quiz": "examiner",
    "transfer_task": "examiner",
}

#: activities that can produce the weekly block deliverable (and therefore may
#: declare a required artifact; concepts/recall/quizzes do not produce files)
PRODUCE_ACTIVITIES = ("code_kata", "writing_block", "transfer_task")

ACTIVITY_LABEL = {
    "agent-dev": {
        "recall_card": "记忆卡",
        "concept_block": "概念块",
        "explain_back": "回述",
        "code_kata": "编程 kata",
        "writing_block": "写作块",
        "quiz": "小测",
        "transfer_task": "迁移任务",
    },
    "email": {
        "recall_card": "句式卡",
        "concept_block": "要点讲解",
        "explain_back": "回述",
        "code_kata": "写作操练",
        "writing_block": "写作块",
        "quiz": "小测",
        "transfer_task": "整封邮件",
    },
}

MENTOR_LABEL = {
    "coach": "coach · 概念与回述导师",
    "trainer": "trainer · 高频练习导师",
    "examiner": "examiner · 考核导师",
}

MENTOR_ORDER = ("coach", "trainer", "examiner")

GRADE_POLICY = {
    "again": {"step_delta": -2, "ease_delta": -0.20, "due": "next_day"},
    "hard": {"step_delta": 0, "ease_delta": -0.05, "due": "half_interval"},
    "good": {"step_delta": 1, "ease_delta": 0.15, "due": "interval"},
    "easy": {"step_delta": 2, "ease_delta": 0.15, "due": "interval"},
}
GRADES = tuple(GRADE_POLICY)

LADDER_DAYS = (1, 2, 4, 8, 15, 30, 60)
EASE_RANGE = (0.85, 1.60)
INTERVAL_RANGE = (1, 90)

#: score = 0.40U + 0.20W + 0.15P + 0.20F + 0.05N - 0.35R   (design §5)
WEIGHTS = {"U": 0.40, "W": 0.20, "P": 0.15, "F": 0.20, "N": 0.05, "R": -0.35}
FACTOR_NAMES = {
    "U": "到期紧急度",
    "W": "薄弱度",
    "P": "计划推进",
    "F": "时长匹配",
    "N": "新鲜度",
    "R": "重复惩罚",
}

DEFAULT_LIMITS = {
    "min_activity": 5,
    "max_activity": 20,
    "max_items_per_session": 2,
    "due_cards_per_session": 3,
    "backlog_cap": 12,
    "close_out_reserve": 2,
}

LIMIT_KEYS_FROM_TEMPLATE = {
    "min_activity_minutes": "min_activity",
    "max_activity_minutes": "max_activity",
    "max_items_per_session": "max_items_per_session",
    "due_cards_per_session": "due_cards_per_session",
    "backlog_cap": "backlog_cap",
    "close_out_reserve_minutes": "close_out_reserve",
}

#: weekly project block plans (design §8: 30-60 min block split into 3 steps)
BLOCK_PLANS = {
    "agent-dev": [
        {
            "goal": "给现有脚本加一个 weather 工具，并让每次调用进入 trace",
            "deliverable": "artifacts/weather-tool.py",
            "steps": [
                ("tool-contract", "concept_block", 10),
                ("tool-contract", "code_kata", 18),
                ("observability", "explain_back", 10),
            ],
        },
        {
            "goal": "实现一个带轮次上限与停止条件的 Agent 循环",
            "deliverable": "artifacts/agent-loop.py",
            "steps": [
                ("agent-loop", "concept_block", 12),
                ("agent-loop", "code_kata", 18),
                ("tool-calling", "explain_back", 10),
            ],
        },
        {
            "goal": "为 20 条 FAQ 的检索问答补上引用与拒答",
            "deliverable": "artifacts/rag-grounding.md",
            "steps": [
                ("rag-retrieval", "concept_block", 12),
                ("grounding", "code_kata", 15),
                ("grounding", "explain_back", 10),
            ],
        },
        {
            "goal": "为检索问答写 10 条回归用例与基线指标",
            "deliverable": "artifacts/eval-cases.json",
            "steps": [
                ("eval-harness", "concept_block", 10),
                ("eval-harness", "quiz", 8),
                ("guardrails", "transfer_task", 15),
            ],
        },
    ],
    "email": [
        {
            "goal": "写一封 3 句邮件，向合作方要资料并给周五期限",
            "deliverable": "artifacts/email-request.md",
            "steps": [
                ("subject-line", "concept_block", 8),
                ("ask-clarity", "writing_block", 15),
                ("opening-purpose", "explain_back", 8),
            ],
        },
        {
            "goal": "拒绝对方的延期请求，并给两个替代时间",
            "deliverable": "artifacts/email-refusal.md",
            "steps": [
                ("tone-register", "concept_block", 8),
                ("tone-register", "writing_block", 15),
                ("language-accuracy", "explain_back", 8),
            ],
        },
        {
            "goal": "把 6 句长邮件压到 3 句，保留请求与期限",
            "deliverable": "artifacts/email-short.md",
            "steps": [
                ("structure-clarity", "concept_block", 8),
                ("structure-clarity", "writing_block", 12),
                ("language-accuracy", "quiz", 8),
            ],
        },
    ],
}

KIND_LABELS = {
    "due_card": "到期卡",
    "due_skill": "技能复测",
    "block_step": "本周块",
    "weak_new": "薄弱/新内容",
}

# --------------------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------------------


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def sha(text: str, n: int = 16) -> str:
    return sha256_text(text or "")[:n]


def date_of(iso: str | None) -> str:
    """Local calendar date of an ISO timestamp (used for all day-level comparisons)."""
    if not iso:
        return ""
    return str(iso)[:10]


def now_iso() -> str:
    return clock.now_iso()


def today_str() -> str:
    return clock.today()


def is_due(due_at: str | None, now: str | None = None) -> bool:
    if not due_at:
        return False
    return date_of(due_at) <= date_of(now or now_iso())


def overdue_days(due_at: str | None, now: str | None = None) -> int:
    if not due_at:
        return 0
    ref = date_of(now or now_iso())
    try:
        return max(0, (date.fromisoformat(ref) - date.fromisoformat(date_of(due_at))).days)
    except ValueError:
        return 0


def week_key(now: str | None = None) -> str:
    d = date.fromisoformat(date_of(now or now_iso()))
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_start(now: str | None = None) -> str:
    d = date.fromisoformat(date_of(now or now_iso()))
    monday = d.fromordinal(d.toordinal() - d.weekday())
    return monday.isoformat()


def days_between(a: str, b: str) -> float:
    try:
        return clock.days_between(a, b)
    except (ValueError, TypeError):
        return 0.0


def activity_label(template_id: str, activity_type: str) -> str:
    return ACTIVITY_LABEL.get(template_id, ACTIVITY_LABEL["agent-dev"]).get(activity_type, activity_type)


def mentor_label(mentor_id: str) -> str:
    return MENTOR_LABEL.get(mentor_id, mentor_id)


def fmt_minutes(minutes: int) -> str:
    return f"{int(minutes)} 分钟"


def fmt_at(iso: str | None) -> str:
    """Display an ISO timestamp as ``YYYY-MM-DD HH:MM`` (local to the recorded offset)."""
    if not iso:
        return "-"
    text = str(iso)
    if len(text) >= 16 and text[10] in "T ":
        return f"{text[:10]} {text[11:16]}"
    return text


# --------------------------------------------------------------------------------------
# budget parsing (regex only; design §3 / D-S4)
# --------------------------------------------------------------------------------------

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

_HOUR_RE = re.compile(r"(?P<n>[一二三四五六七八九十两\d]{1,3})\s*个?\s*(?:小时|钟头|hours?|hrs?)", re.I)
_MIN_CN_RE = re.compile(r"(?P<n>[一二三四五六七八九十两]{1,4})\s*分钟")
_MIN_CN_SHORT_RE = re.compile(r"(?P<n>[一二三四五六七八九十两]{1,4})\s*分(?!钟)")
_MIN_AR_RE = re.compile(r"(?P<n>\d{1,3})\s*(?:分钟|min(?:ute)?s?|m(?!s))", re.I)
_MIN_BARE_RE = re.compile(r"^\s*(?P<n>\d{1,3})\s*$")
_QUARTER_RE = re.compile(r"(?:一|1)?个?刻钟")
_HALF_RE = re.compile(r"半\s*个?\s*(?:小时|钟头)")
_AWHILE_RE = re.compile(r"一\s*会儿|一会儿|几分钟|稍等|等一下|没多少时间|没多少空")
_CN_HOUR_WORDS = {"一个": 60, "一小时": 60, "两小时": 120, "二小时": 120}


class BudgetParse:
    """Result of parsing a free-text time budget."""

    def __init__(self, minutes: int | None, matched: str = "", raw: int | None = None, note: str = ""):
        self.minutes = minutes
        self.matched = matched
        self.raw = raw
        self.note = note
        self.clamped = minutes is not None and raw is not None and minutes != raw

    @property
    def parsed(self) -> bool:
        return self.minutes is not None

    def as_dict(self) -> dict:
        return {
            "minutes": self.minutes,
            "matched": self.matched,
            "raw": self.raw,
            "note": self.note,
            "clamped": self.clamped,
            "parsed": self.parsed,
        }


def cn_number(text: str) -> int | None:
    """Parse Chinese numerals 1-99 as used for minutes ('二十', '二十五', '十五')."""
    text = (text or "").strip()
    if not text:
        return None
    if all(ch in _CN_DIGITS for ch in text):
        if len(text) == 1:
            return _CN_DIGITS[text]
        return None
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        if left and left not in _CN_DIGITS:
            return None
        if right and right not in _CN_DIGITS:
            return None
        return tens * 10 + ones
    return None


def _clamp_budget(raw: int, matched: str) -> BudgetParse:
    if raw < 5:
        return BudgetParse(5, matched, raw, f"按最少 5 分钟安排（原 {raw} 分钟）")
    if raw > 45:
        return BudgetParse(45, matched, raw, f"按 45 分钟上限安排（原 {raw} 分钟）")
    return BudgetParse(raw, matched, raw, "")


def parse_budget_text(text: str) -> BudgetParse:
    """Extract a minute budget from a learner sentence. Never calls an LLM."""
    raw_text = text or ""
    if not raw_text.strip():
        return BudgetParse(None)

    m = _HOUR_RE.search(raw_text)
    if m:
        token = m.group("n")
        hours = cn_number(token) if not token.isdigit() else int(token)
        if hours:
            value = int(hours) * 60
            note = "按 45 分钟上限安排（单次上限）" if value > 45 else ""
            return BudgetParse(45 if value > 45 else value, m.group(0), value, note)

    m = _QUARTER_RE.search(raw_text)
    if m:
        return BudgetParse(15, m.group(0), 15, "")

    m = _HALF_RE.search(raw_text)
    if m:
        return BudgetParse(30, m.group(0), 30, "")

    m = _MIN_AR_RE.search(raw_text)
    if m:
        return _clamp_budget(int(m.group("n")), m.group(0))

    m = _MIN_CN_RE.search(raw_text)
    if m:
        value = cn_number(m.group("n"))
        if value:
            return _clamp_budget(int(value), m.group(0))

    m = _MIN_CN_SHORT_RE.search(raw_text)
    if m:
        value = cn_number(m.group("n"))
        if value:
            return _clamp_budget(int(value), m.group(0))

    m = _AWHILE_RE.search(raw_text)
    if m:
        return BudgetParse(10, m.group(0), 10, "按 10 分钟安排")

    m = _MIN_BARE_RE.match(raw_text)
    if m:
        return _clamp_budget(int(m.group("n")), m.group(0))

    return BudgetParse(None)


def budget_for_start(minutes_arg: int | None, text: str | None, default: int = 20) -> tuple[BudgetParse, str, str]:
    """Return (parse, source, note) for ``start``. Falls back to 20 with a hint."""
    if minutes_arg is not None:
        parsed = _clamp_budget(int(minutes_arg), f"--minutes {minutes_arg}")
        parsed.matched = f"--minutes {minutes_arg}"
        return parsed, "flag", parsed.note
    if text:
        parsed = parse_budget_text(text)
        if parsed.parsed:
            return parsed, "text", parsed.note
        fallback = BudgetParse(default, "", default, f"没看懂时间，按默认 {default} 分钟安排；可以直接说“只有二十分钟”")
        return fallback, "default", fallback.note
    return BudgetParse(default, "", default, ""), "default", ""


# --------------------------------------------------------------------------------------
# templates / initial state
# --------------------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"```json\s*\n(?P<body>.*?)```", re.DOTALL)


def variant_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_template(template_id: str) -> dict:
    path = variant_root() / "templates" / f"{template_id}.md"
    if not path.exists():
        raise LearnError(f"unknown template '{template_id}': {path} not found")
    match = _JSON_BLOCK_RE.search(path.read_text(encoding="utf-8"))
    if not match:
        raise LearnError(f"template {path} has no ```json payload")
    try:
        payload = json.loads(match.group("body"))
    except json.JSONDecodeError as exc:
        raise LearnError(f"template {path} payload is not valid JSON: {exc}") from exc
    if payload.get("template_id") != template_id:
        raise LearnError(f"template {path} declares template_id={payload.get('template_id')!r}")
    return payload


def normalize_limits(template: dict) -> dict:
    limits = dict(DEFAULT_LIMITS)
    raw = template.get("limits") or {}
    for key, target in LIMIT_KEYS_FROM_TEMPLATE.items():
        if key in raw:
            limits[target] = int(raw[key])
    return limits


def seed_skills(template: dict, now: str) -> list[dict]:
    out = []
    for item in template.get("skills", []):
        out.append(
            {
                "id": item["id"],
                "title": item.get("title", item["id"]),
                "tags": list(item.get("tags") or []),
                "level": 0,
                "level_reason": "未接触；自述不计等级，只按行为证据校准",
                "evidence_level": "self_report",
                "evidence_refs": [],
                "last_review_at": None,
                "last_review_date": None,
                "due_at": None,
                "stability_days": 1.0,
                "lapses": 0,
                "consecutive_failures": 0,
                "wrong_tags": [],
                "block_id": None,
                "block_artifact_at": None,
                "block_artifact_path": "",
                "delayed_retest_due_at": None,
                "last_verified_at": None,
                "last_level_up_date": None,
            }
        )
    return out


def seed_cards(template: dict, now: str) -> list[dict]:
    out = []
    for index, item in enumerate(template.get("cards", [])):
        # diagnose with a small due set, not the whole deck on day one
        due_at = now if index < 2 else clock.add_days(now, min(index, 10))
        out.append(
            {
                "id": item["id"],
                "skill": item["skill"],
                "kind": item.get("kind", "recall"),
                "front": item["front"],
                "back": item["back"],
                "tags": list(item.get("tags") or []),
                "source_event": "init:template",
                "step": int(item.get("step", 0)),
                "interval_days": int(LADDER_DAYS[clamp(int(item.get("step", 0)), 0, len(LADDER_DAYS) - 1)]),
                "ease": float(item.get("ease", 1.0)),
                "due_at": due_at,
                "last_review_at": None,
                "lapses": 0,
                "consecutive_lapses": 0,
                "leech": False,
                "needs_rewrite": False,
                "created_at": now,
            }
        )
    return out


def planned_block(template_id: str, now: str) -> dict:
    plans = BLOCK_PLANS.get(template_id) or BLOCK_PLANS["agent-dev"]
    iso = date.fromisoformat(date_of(now))
    ordinal = iso.isocalendar().year * 53 + iso.isocalendar().week
    plan = plans[ordinal % len(plans)]
    week = week_key(now)
    return {
        "id": f"block-{template_id}-{week}",
        "week": week,
        "week_start": week_start(now),
        "goal": plan["goal"],
        "deliverable": plan["deliverable"],
        "artifact_path": "",
        "created_at": now,
        "steps": [
            {
                "skill": skill,
                "activity_type": activity_type,
                "minutes": minutes,
                "done": False,
                "evidence_ref": "",
                "artifact": "",
                # only the step that actually produces the deliverable requires it
                "required_artifact": plan["deliverable"] if activity_type in PRODUCE_ACTIVITIES else "",
            }
            for skill, activity_type, minutes in plan["steps"]
        ],
    }


def current_block(blocks: list[dict], now: str) -> dict | None:
    week = week_key(now)
    for block in blocks:
        if block.get("week") == week:
            return block
    return None


def ensure_block(store: "Store", now: str) -> dict | None:
    blocks = store.blocks.setdefault("blocks", [])
    block = current_block(blocks, now)
    if block is not None:
        # migrate blocks created before required artifacts existed
        changed = False
        for step in block.get("steps", []):
            if "required_artifact" not in step:
                step["required_artifact"] = (
                    block.get("deliverable", "") if step.get("activity_type") in PRODUCE_ACTIVITIES else ""
                )
                changed = True
        if changed:
            store.touch("blocks")
        return block
    block = planned_block(store.meta["template_id"], now)
    if store.meta["template_id"] not in BLOCK_PLANS:
        block = planned_block("agent-dev", now)
    blocks.append(block)
    store.touch("blocks")
    return block


# --------------------------------------------------------------------------------------
# project store
# --------------------------------------------------------------------------------------


def _schedule_default() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "minutes_default": 20,
        "limits": dict(DEFAULT_LIMITS),
        "today": {
            "date": "",
            "minutes_budget": 20,
            "minutes_used": 0,
            "minutes_left": 20,
            "budget_source": "default",
            "items": [],
        },
        "plan": [],
        "last_activity": None,
        "recent": [],
        "current_session": None,
        "updated_at": None,
    }


def _skills_default() -> dict:
    return {"schema_version": SCHEMA_VERSION, "skills": []}


def _cards_default() -> dict:
    return {"schema_version": SCHEMA_VERSION, "cards": []}


def _blocks_default() -> dict:
    return {"schema_version": SCHEMA_VERSION, "blocks": []}


class Store:
    """A loaded Tempo project. Call :meth:`load` before use."""

    def __init__(self, root: str | Path, *, offline: bool = False):
        self.root = Path(root).resolve()
        self.offline = offline
        meta_path = self.root / ".learnark" / "project.json"
        if not meta_path.exists():
            raise LearnError(
                f"{self.root} is not a Tempo project (missing .learnark/project.json). "
                "Run 'init' first, or pass --project pointing at the project folder."
            )
        # A corrupt project.json must be reported, not silently swapped: the backup
        # path is the same one the state documents use, and the repair is surfaced
        # in status/doctor output through ``Store.repairs``.
        meta, meta_repaired, meta_note = load_json_state(meta_path, None)
        self._meta_repair = meta_note if meta_repaired else ""
        if not isinstance(meta, dict):
            raise LearnError(
                f"{meta_path} 不是 JSON 对象（project.json 损坏且没有可用 .bak）。"
                " 请从备份恢复该文件，或用 init 重建项目；本次没有写入任何状态。"
            )
        self.meta = meta
        state = self.root / ".learnark" / "state"
        self._docs = {
            "schedule": Document(state / "schedule.json", _schedule_default),
            "skills": Document(state / "skills.json", _skills_default),
            "cards": Document(state / "cards.json", _cards_default),
            "blocks": Document(state / "blocks.json", _blocks_default),
        }
        self.journal = Journal(
            self.root / ".learnark" / "journal" / "events.jsonl",
            self.root / ".learnark" / "journal" / "dedupe.json",
        )
        self.repairs: list[str] = []
        self._dirty: set[str] = set()
        #: versions observed when each document was read; ``save`` uses them as the
        #: CAS expectation so a writer that loaded stale state cannot overwrite a
        #: newer snapshot (journal remains authoritative).
        self._versions: dict[str, int | None] = {}
        self.schedule: dict = {}
        self.skills: dict = {}
        self.cards: dict = {}
        self.blocks: dict = {}
        self._loaded = False

    # -- load / save -----------------------------------------------------
    def load(self) -> "Store":
        if self._meta_repair:
            self.repairs.append(self._meta_repair + "（project.json 已按 .bak 重写，请核对目标/模板）")
        for name in ("schedule", "skills", "cards", "blocks"):
            try:
                value = self._docs[name].load()
            except ValueError:
                value = self._recover_non_object(name)
            setattr(self, name, value)
            self._versions[name] = int(value.get("version", 0) or 0)
            note = self._docs[name].repair_note()
            if note:
                self.repairs.append(note)
        self._ensure_defaults()
        self._loaded = True
        return self

    def _recover_non_object(self, name: str) -> dict:
        """Heal a state file that parses as JSON but is not an object.

        ``Document.load`` only repairs *unparsable* files from ``.bak``; a file like
        ``[]`` or ``"x"`` would otherwise surface as a generic exit-4 crash. Try the
        documented backup path first, then fail as a state error (exit 3).
        """
        doc = self._docs[name]
        bak = doc.path.with_name(doc.path.name + ".bak")
        if bak.exists():
            try:
                value = read_json(bak)
            except (StateCorrupt, OSError, ValueError):
                value = None
            if isinstance(value, dict):
                value.setdefault("version", 0)
                write_json(doc.path, value)
                self.repairs.append(f"{doc.path.name} 不是 JSON 对象：已从 .bak 恢复（请核对是否少了最后一次写入）")
                return value
        raise LearnError(
            f"{doc.path.name} 不是 JSON 对象（内容损坏且没有可用 .bak）。"
            " 不要手改状态文件：请从备份恢复，或删除该文件后由下一次命令按默认状态重建；本次未写入任何内容。"
        )

    def _ensure_defaults(self) -> None:
        self.schedule.setdefault("schema_version", SCHEMA_VERSION)
        for key, value in _schedule_default().items():
            if key not in self.schedule:
                self.schedule[key] = value
        self.schedule.setdefault("today", {"date": "", "minutes_budget": 20, "minutes_left": 20, "items": []})
        for key, value in {
            "date": "",
            "minutes_budget": 20,
            "minutes_used": 0,
            "minutes_left": 20,
            "budget_source": "default",
            "items": [],
        }.items():
            self.schedule["today"].setdefault(key, value)
        if self.schedule["today"].get("minutes_used") is None:
            self.schedule["today"]["minutes_used"] = 0
        self.skills.setdefault("skills", [])
        self.cards.setdefault("cards", [])
        self.blocks.setdefault("blocks", [])
        self.meta.setdefault("schema_version", SCHEMA_VERSION)
        self.meta.setdefault("limits", dict(DEFAULT_LIMITS))
        self.meta.setdefault("minutes_default", 20)
        self.meta.setdefault("minutes_per_week", 600)
        self.meta.setdefault("mentor", "coach")
        self.meta.setdefault("diagnosed", False)

    def touch(self, *names: str) -> None:
        self._dirty.update(names)

    def save(self, *, force: bool = False) -> list[str]:
        """Persist only the documents that were touched (or all with ``force``).

        Each document is written with the version observed at ``load`` time, so a
        stale writer gets :class:`StaleWrite` instead of silently replacing newer
        learning state (shared requirement §7). ``LEARNARK_LOCK_TIMEOUT`` is *not*
        used here: CAS must fail immediately.
        """
        saved = []
        for name in ("schedule", "skills", "cards", "blocks"):
            if force or name in self._dirty:
                expected = self._versions.get(name)
                payload = self._docs[name].save(getattr(self, name), expected_version=expected)
                self._versions[name] = int(payload.get("version", 0) or 0)
                saved.append(name)
        if force or "meta" in self._dirty:
            self.meta["updated_at"] = now_iso()
            write_json(self.root / ".learnark" / "project.json", self.meta, backup=True)
            saved.append("meta")
        self._dirty.clear()
        return saved

    # -- lookups ---------------------------------------------------------
    @property
    def limits(self) -> dict:
        return self.meta.get("limits") or dict(DEFAULT_LIMITS)

    @property
    def template_id(self) -> str:
        return self.meta.get("template_id", "agent-dev")

    def skill(self, skill_id: str) -> dict | None:
        for item in self.skills.get("skills", []):
            if item.get("id") == skill_id:
                return item
        return None

    def card(self, card_id: str) -> dict | None:
        for item in self.cards.get("cards", []):
            if item.get("id") == card_id:
                return item
        return None

    def block(self, block_id: str | None) -> dict | None:
        if not block_id:
            return None
        for item in self.blocks.get("blocks", []):
            if item.get("id") == block_id:
                return item
        return None

    def skill_ids(self) -> set[str]:
        return {item["id"] for item in self.skills.get("skills", [])}

    def mentor_ids(self) -> list[str]:
        mentors = self.meta.get("mentors") or list(MENTOR_ORDER)
        return [m for m in mentors if m in MENTOR_LABEL] or list(MENTOR_ORDER)

    def minutes_default(self) -> int:
        return int(self.meta.get("minutes_default") or self.schedule.get("minutes_default") or 20)

    # -- journal helpers -------------------------------------------------
    def repair_journal_tail(self) -> str:
        """Drop a torn final line before appending, so a crash cannot poison the log.

        The repair rewrites the append-only journal, so it must hold the *journal*
        lock: without it, an event appended by another process between our read and
        write would be silently discarded (regression covered by the reliability
        suite). Truncation is in place (no replace) so a concurrent reader never
        loses the file handle.
        """
        path = self.journal.path
        if not path.exists():
            return ""
        with file_lock(self.journal.lock_path):
            try:
                raw = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return ""
            if not raw or raw.endswith("\n"):
                return ""
            lines = raw.splitlines()
            last = lines[-1].strip() if lines else ""
            valid = False
            if last:
                try:
                    json.loads(last)
                    valid = True
                except ValueError:
                    valid = False
            if valid:
                with path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                return ""
            keep = raw[: raw.rfind("\n") + 1] if "\n" in raw else ""
            data = keep.encode("utf-8")
            with path.open("r+b") as handle:
                handle.truncate(len(data))
                handle.flush()
                os.fsync(handle.fileno())
            return "journal 尾部半行（中断残留）已丢弃，其它事件保留"

    def append(self, kind: str, payload: dict | None = None, *, dedupe_key: str | None = None, actor: str = "runtime"):
        repaired = self.repair_journal_tail()
        if repaired:
            self.journal.append("journal_repaired", {"note": repaired}, actor="system")
        event = self.journal.append(kind, payload or {}, dedupe_key=dedupe_key, actor=actor)
        return event

    def events(self, *kinds: str) -> list[dict]:
        if not kinds:
            return self.journal.all()
        return self.journal.of_kind(*kinds)

    # -- derived facts ---------------------------------------------------
    def today_items(self) -> list[dict]:
        today = self.schedule["today"]
        return list(today.get("items") or [])

    def today_templates(self) -> set[str]:
        return {item.get("activity_type") for item in self.today_items() if item.get("activity_type")}

    def today_skills(self) -> set[str]:
        return {item.get("skill") for item in self.today_items() if item.get("skill")}

    # -- budget accounting (one source of truth: budget - started minutes) --
    def today_budget(self) -> int:
        return int(self.schedule.get("today", {}).get("minutes_budget") or self.minutes_default())

    def today_used(self) -> int:
        return sum(int(item.get("minutes") or 0) for item in self.today_items())

    def today_remaining(self) -> int:
        return max(0, self.today_budget() - self.today_used())

    def budget_source(self) -> str:
        return str(self.schedule.get("today", {}).get("budget_source") or "default")

    def cap_reached(self) -> bool:
        return len(self.today_items()) >= int(self.limits.get("max_items_per_session", 2))

    def refresh_budget_fields(self) -> None:
        today = self.schedule["today"]
        today["minutes_used"] = self.today_used()
        today["minutes_left"] = max(0, int(today.get("minutes_budget") or 0) - today["minutes_used"])
        self.touch("schedule")

    def last_skill(self) -> str | None:
        recent = self.schedule.get("recent") or []
        if recent:
            return recent[-1].get("skill")
        last = self.schedule.get("last_activity") or {}
        return last.get("skill")

    def errors_last_7d(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        cutoff = clock.add_days(now_iso(), -7)
        for event in self.events("attempt"):
            payload = event.get("payload") or {}
            if payload.get("correct") is False and str(event.get("at", "")) >= cutoff:
                skill = payload.get("skill")
                if skill:
                    counts[skill] = counts.get(skill, 0) + 1
        return counts

    def due_cards(self) -> list[dict]:
        cards = [c for c in self.cards.get("cards", []) if is_due(c.get("due_at"))]
        cards.sort(key=lambda c: (-overdue_days(c.get("due_at")), c.get("due_at") or "", c.get("id") or ""))
        return cards

    def due_skills(self) -> list[dict]:
        skills = [s for s in self.skills.get("skills", []) if is_due(s.get("due_at"))]
        skills.sort(key=lambda s: (-overdue_days(s.get("due_at")), s.get("due_at") or "", s.get("id") or ""))
        return skills


# --------------------------------------------------------------------------------------
# SRS: cards
# --------------------------------------------------------------------------------------


def interval_for(step: int, ease: float) -> int:
    step = int(clamp(step, 0, len(LADDER_DAYS) - 1))
    value = int(round(LADDER_DAYS[step] * float(ease)))
    return int(clamp(value, *INTERVAL_RANGE))


def grade_card(card: dict, grade: str, now: str) -> dict:
    """Apply one review grade to ``card`` in place; returns the change record."""
    if grade not in GRADE_POLICY:
        raise LearnError(f"unknown grade {grade!r}; expected one of {GRADES}")
    policy = GRADE_POLICY[grade]
    step_before = int(card.get("step", 0))
    ease = clamp(float(card.get("ease", 1.0)) + policy["ease_delta"], *EASE_RANGE)
    step_after = int(clamp(step_before + policy["step_delta"], 0, len(LADDER_DAYS) - 1))
    if policy["due"] == "next_day":
        interval = 1
        card["lapses"] = int(card.get("lapses", 0)) + 1
        card["consecutive_lapses"] = int(card.get("consecutive_lapses", 0)) + 1
    else:
        if policy["due"] == "half_interval":
            interval = max(1, int(round(interval_for(step_after, ease) / 2.0)))
        else:
            interval = interval_for(step_after, ease)
        card["consecutive_lapses"] = 0
    new_leech = False
    if int(card.get("consecutive_lapses", 0)) >= 2 and not card.get("leech"):
        card["leech"] = True
        card["needs_rewrite"] = True
        new_leech = True
    card["step"] = step_after
    card["ease"] = round(ease, 4)
    card["interval_days"] = interval
    card["due_at"] = clock.add_days(now, interval)
    card["last_review_at"] = now
    card["last_grade"] = grade
    return {
        "grade": grade,
        "step_before": step_before,
        "step": step_after,
        "ease": card["ease"],
        "interval_days": interval,
        "due_at": card["due_at"],
        "lapses": card.get("lapses", 0),
        "leech": card.get("leech", False),
        "new_leech": new_leech,
    }


def fold_backlog(cards: list[dict], now: str, cap: int = 12, protected: set[str] | None = None) -> list[dict]:
    """Fold the oldest overdue cards +3 days, never the unfinished current card."""
    protect = protected or set()
    overdue = [c for c in cards if is_due(c.get("due_at"), now)]
    overdue.sort(key=lambda c: (c.get("due_at") or "", c.get("id") or ""))
    folded = []
    while len(overdue) > int(cap):
        index = next((i for i, card in enumerate(overdue) if card.get("id") not in protect), None)
        if index is None:
            break
        card = overdue.pop(index)
        card["due_at"] = clock.add_days(card["due_at"], 3)
        card["backlog_folds"] = int(card.get("backlog_folds", 0)) + 1
        folded.append(card)
    return folded


def weekly_card_cap(minutes_per_week: float) -> int:
    return int(clamp(round(float(minutes_per_week) / 45.0), 5, 40))


def cards_created_this_week(cards: list[dict], now: str) -> list[dict]:
    start = week_start(now)
    out = []
    for card in cards:
        if card.get("source_event") == "init:template":
            continue
        created = date_of(card.get("created_at"))
        if created and created >= start:
            out.append(card)
    return out


# --------------------------------------------------------------------------------------
# Scheduler: candidate scoring and selection (pure)
# --------------------------------------------------------------------------------------


def candidate_score(candidate: dict, budget: int) -> dict:
    """Return factor values and the weighted score. Pure function of the candidate."""
    overdue = float(candidate.get("overdue_days") or 0)
    due = bool(candidate.get("due"))
    level = int(candidate.get("level") or 0)
    errors = int(candidate.get("errors_7d") or 0)
    minutes = int(candidate.get("minutes") or 0)
    budget = max(1, int(budget))

    u = 0.25 + 0.75 * min(1.0, overdue / 3.0) if due else 0.0
    w = max(0.0, min(1.0, (3 - level) / 3.0 + 0.2 * errors))
    p = float(candidate.get("plan_progress") or 0.0)
    f = min(minutes, budget) / float(max(minutes, budget))
    n = 1.0 if candidate.get("new") else 0.0
    if candidate.get("recent_skill"):
        r = 1.0
    elif candidate.get("today_template"):
        r = 0.5
    else:
        r = 0.0

    score = WEIGHTS["U"] * u + WEIGHTS["W"] * w + WEIGHTS["P"] * p + WEIGHTS["F"] * f + WEIGHTS["N"] * n + WEIGHTS["R"] * r
    factors = {"U": round(u, 4), "W": round(w, 4), "P": round(p, 4), "F": round(f, 4), "N": round(n, 4), "R": round(r, 4)}
    contributions = {key: abs(WEIGHTS[key]) * factors[key] for key in ("U", "W", "P", "F", "N")}
    main = max(contributions, key=lambda key: (contributions[key], key))
    return {"score": round(score, 6), "factors": factors, "main_factor": main, "main_label": FACTOR_NAMES[main]}


def _reject_reason(
    candidate: dict,
    remaining: int,
    used_templates: set[str],
    used_skills: set[str],
    *,
    allow_repeat: bool,
    min_activity: int,
) -> str:
    minutes = int(candidate.get("minutes") or 0)
    if minutes < int(min_activity):
        return f"{minutes} 分钟低于最短活动 {min_activity} 分钟"
    if minutes > remaining:
        return f"{minutes} 分钟活动本次放不下（剩余 {remaining} 分钟）；下次（约 {minutes} 分钟）"
    if candidate.get("leech") and remaining < 10:
        return "leech 卡需 ≥10 分钟预算，本次先跳过"
    if not allow_repeat:
        if candidate.get("template") in used_templates:
            return "今天已做该活动模板"
        if candidate.get("skill") in used_skills:
            return "同一技能当天已练过（显式 review 除外）"
    return ""


def _rank_key(candidate: dict, budget: int):
    scored = candidate_score(candidate, budget)
    return (-scored["score"], candidate.get("due_at") or "", candidate.get("activity_id") or "")


def select_activities(
    candidates: list[dict],
    budget: int,
    *,
    max_items: int = 2,
    allow_repeat: bool = False,
    force_due: bool = False,
    min_activity: int = 5,
    today_templates: set[str] | None = None,
    today_skills: set[str] | None = None,
    due_cards_cap: int = 3,
    priority_ids: set[str] | None = None,
) -> dict:
    """Deterministic two-level selection (design §5).

    Tier 1 due group -> Tier 2 weekly block step -> Tier 3 weak/new content.
    The first item follows tier order. Follow-ups first try the weekly block
    step (so the block is not starved), then the lowest tier with capacity.
    """
    pool = [dict(c) for c in candidates]
    budget = max(1, int(budget))
    used_templates = set(today_templates or ())
    used_skills = set(today_skills or ())
    due_in_group = 0
    chosen: list[dict] = []
    rows: list[dict] = []
    remaining = budget
    chosen_tier = None
    fallback = False

    if force_due:
        # explicit `review`: only the due tier, same-day repeat filters relaxed
        pool = [c for c in pool if int(c.get("tier", 3)) == 1]

    # ---- first item: core deliverable block first, then strict tier order
    first = None
    if priority_ids:
        priority_pool = []
        for candidate in pool:
            if candidate.get("activity_id") not in priority_ids:
                continue
            reason = _reject_reason(
                candidate, remaining, used_templates, used_skills, allow_repeat=allow_repeat, min_activity=min_activity
            )
            if reason:
                candidate["_reject"] = reason
            else:
                priority_pool.append(candidate)
        if priority_pool:
            first = sorted(priority_pool, key=lambda c: _rank_key(c, remaining))[0]
            first["_priority"] = True
            chosen_tier = 0
    if first is None:
        for tier in (1, 2, 3):
            tier_candidates = [c for c in pool if int(c.get("tier", 3)) == tier]
            eligible = []
            for candidate in tier_candidates:
                if tier == 1 and candidate.get("source") == "due_card" and due_in_group >= int(due_cards_cap):
                    candidate["_reject"] = f"单次到期卡上限 {due_cards_cap} 张"
                    continue
                reason = _reject_reason(
                    candidate, remaining, used_templates, used_skills, allow_repeat=allow_repeat, min_activity=min_activity
                )
                if reason:
                    candidate["_reject"] = reason
                else:
                    eligible.append(candidate)
            if eligible:
                first = sorted(eligible, key=lambda c: _rank_key(c, remaining))[0]
                chosen_tier = tier
                break

    if first is None:
        fallback = True
        first = {
            "activity_id": "fallback-recall",
            "activity_type": "recall_card",
            "template": "recall_card",
            "skill": None,
            "skill_title": "（无候选）",
            "minutes": min(5, budget),
            "mentor": "trainer",
            "tier": 3,
            "source": "fallback",
            "due": False,
            "due_at": None,
            "overdue_days": 0,
            "level": 0,
            "new": True,
            "errors_7d": 0,
            "plan_progress": 0.0,
            "leech": False,
            "label": "候选为空：回落 5 分钟卡自测",
            "task": "候选集为空，先用 5 分钟抽一张最简单的卡，保持节奏。",
        }
        chosen.append(first)
        remaining -= int(first.get("minutes") or 0)
    else:
        chosen.append(first)
        remaining -= int(first.get("minutes") or 0)
        used_templates.add(first.get("template"))
        if first.get("skill"):
            used_skills.add(first.get("skill"))
        if first.get("source") == "due_card":
            due_in_group += 1

    # ---- follow-ups -----------------------------------------------------
    while first is not None and len(chosen) < int(max_items) and remaining >= int(min_activity):
        nxt = None
        # 1) weekly block step (keeps the 30-60 min weekly block from starving)
        block_pool = [
            c
            for c in pool
            if int(c.get("tier", 3)) == 2 and c not in chosen and (chosen_tier or 3) <= 2
        ]
        nxt = _best_eligible(block_pool, remaining, used_templates, used_skills, allow_repeat, min_activity)
        # 2) otherwise the lowest tier with an eligible candidate (due first)
        if nxt is None:
            for tier in (1, 2, 3):
                tier_pool = [c for c in pool if int(c.get("tier", 3)) == tier and c not in chosen]
                nxt = _best_eligible(tier_pool, remaining, used_templates, used_skills, allow_repeat, min_activity)
                if nxt is not None:
                    break
        if nxt is None:
            break
        if nxt.get("source") == "due_card" and due_in_group >= int(due_cards_cap):
            break
        chosen.append(nxt)
        if nxt.get("source") == "due_card":
            due_in_group += 1
        remaining -= int(nxt.get("minutes") or 0)
        used_templates.add(nxt.get("template"))
        if nxt.get("skill"):
            used_skills.add(nxt.get("skill"))

    # ---- rows for the explanation table --------------------------------
    chosen_ids = {c["activity_id"] for c in chosen}
    plan_ids = [c["activity_id"] for c in chosen]
    if fallback:
        scored = candidate_score(first, budget)
        rows.append(
            {
                "activity_id": first["activity_id"],
                "activity_type": first["activity_type"],
                "skill": None,
                "skill_title": first.get("skill_title"),
                "minutes": first["minutes"],
                "tier": first["tier"],
                "source": first["source"],
                "status": "chosen",
                "reason": "候选为空：回落 5 分钟卡自测",
                "score": scored["score"],
                "factors": scored["factors"],
                "main_factor": scored["main_factor"],
                "main_label": scored["main_label"],
                "label": first.get("label", ""),
            }
        )
    for candidate in pool:
        if candidate["activity_id"] in chosen_ids:
            status = "chosen" if candidate is chosen[0] else "plan"
            reason = "本次活动" if status == "chosen" else "计划内的下一项"
        elif chosen_tier is not None and int(candidate.get("tier", 3)) > int(chosen_tier):
            status = "not_entered"
            reason = f"tier {int(candidate.get('tier', 3))} 未进入：{('到期组非空' if chosen_tier == 1 else 'tier 1 已选中')}"
        else:
            reject = candidate.get("_reject", "")
            if not reject:
                reject = _reject_reason(
                    candidate, budget, today_templates or set(), today_skills or set(), allow_repeat=allow_repeat, min_activity=min_activity
                )
            status = "rejected" if reject else "eligible"
            reason = reject or "可做但未入选（分数较低）"
        # one remaining-minutes source: candidate text quotes the entry budget, not a loop counter
        reason = re.sub(r"本次放不下（剩余 \d+ 分钟）", f"本次放不下（可用 {budget} 分钟）", reason)
        scored = candidate_score(candidate, budget)
        row = {
            "activity_id": candidate["activity_id"],
            "activity_type": candidate["activity_type"],
            "skill": candidate.get("skill"),
            "skill_title": candidate.get("skill_title"),
            "minutes": int(candidate.get("minutes") or 0),
            "tier": int(candidate.get("tier", 3)),
            "source": candidate.get("source"),
            "status": status,
            "reason": reason,
            "score": scored["score"],
            "factors": scored["factors"],
            "main_factor": scored["main_factor"],
            "main_label": scored["main_label"],
            "label": candidate.get("label", ""),
        }
        rows.append(row)

    rows.sort(key=lambda r: (0 if r["status"] == "chosen" else 1 if r["status"] == "plan" else 2, -r["score"], r["activity_id"]))
    top = [r for r in rows if r["status"] in ("chosen", "plan")]
    top += [r for r in rows if r["status"] not in ("chosen", "plan")][: max(1, 4 - len(top))]

    reason_line = build_reason_line(chosen, budget, rows, fallback)
    return {
        "budget": budget,
        "chosen": chosen[0] if chosen else None,
        "plan": chosen,
        "plan_ids": plan_ids,
        "rows": rows,
        "top": top[:3],
        "reason_line": reason_line,
        "fallback": fallback,
        "tier_used": chosen_tier,
        "remaining": remaining,
    }


def _best_eligible(
    pool: list[dict],
    remaining: int,
    used_templates: set[str],
    used_skills: set[str],
    allow_repeat: bool,
    min_activity: int,
) -> dict | None:
    eligible = []
    for candidate in pool:
        reason = _reject_reason(candidate, remaining, used_templates, used_skills, allow_repeat=allow_repeat, min_activity=min_activity)
        if reason:
            candidate["_reject"] = reason
        else:
            eligible.append(candidate)
    if not eligible:
        return None
    return sorted(eligible, key=lambda c: _rank_key(c, remaining))[0]


def build_reason_line(chosen: list[dict], budget: int, rows: list[dict], fallback: bool) -> str:
    if fallback or not chosen:
        return "候选集为空：回落一次 5 分钟卡自测，只为保持节奏，不算欠账。"
    first = chosen[0]
    parts: list[str] = []
    if first.get("_priority"):
        parts.append("核心可交付块优先：先保证本周写作/产出步骤，到期卡让位")
    elif first.get("source") == "due_card":
        overdue = int(first.get("overdue_days") or 0)
        parts.append(f"到期组：该卡逾期 {overdue} 天，先清到期")
    elif first.get("source") == "due_skill":
        parts.append(f"到期组：技能 {first.get('skill')} 到期复测")
    elif first.get("source") == "block_step":
        parts.append("到期组已清空，进入本周块步骤")
    else:
        parts.append("到期组与块步骤都已清空，做薄弱/新内容")
    parts.append(f"选 {first.get('minutes')} 分钟的{first.get('label') or first.get('activity_type')}，预算 {budget} 分钟内能完整做完")
    if len(chosen) > 1:
        parts.append(f"计划共 {len(chosen)} 项，剩余 {budget - sum(int(c.get('minutes') or 0) for c in chosen)} 分钟")
    else:
        rest = [r for r in rows if r["status"] in ("rejected", "not_entered")][:2]
        if rest:
            parts.append("未入选：" + "；".join(f"{r['activity_id']}（{r['reason']}）" for r in rest))
    return "；".join(parts) + "。"


def render_candidate_table(rows: list[dict], limit: int = 5) -> str:
    headers = ["#", "活动", "技能", "时长", "层级", "总分", "主因子", "状态/理由"]
    table = []
    for index, row in enumerate(rows[:limit], 1):
        status = {
            "chosen": "选中",
            "plan": "计划",
            "eligible": "备选",
            "rejected": "排除",
            "not_entered": "未进入",
        }.get(row["status"], row["status"])
        table.append(
            [
                str(index),
                str(row["activity_id"]),
                str(row.get("skill") or "-"),
                f"{row['minutes']}m",
                f"T{row['tier']}",
                f"{row['score']:.3f}",
                row["main_label"],
                f"{status}：{row['reason']}",
            ]
        )
    from learncore.cli import table as cli_table

    return cli_table(table, headers)


# --------------------------------------------------------------------------------------
# candidate construction from real state
# --------------------------------------------------------------------------------------


def candidate(
    *,
    activity_id: str,
    activity_type: str,
    skill: str | None,
    skill_title: str,
    skill_level: int,
    minutes: int,
    tier: int,
    source: str,
    template_id: str,
    label: str,
    task: str,
    due_at: str | None = None,
    overdue: int = 0,
    new: bool = False,
    errors_7d: int = 0,
    plan_progress: float = 0.0,
    leech: bool = False,
    card_id: str | None = None,
    card_ids: list[str] | None = None,
    block_id: str | None = None,
    step_index: int | None = None,
    recent_skill: bool = False,
    today_template: bool = False,
    requires_artifact: str = "",
) -> dict:
    return {
        "activity_id": activity_id,
        "activity_type": activity_type,
        "template": activity_type,
        "skill": skill,
        "skill_title": skill_title,
        "level": int(skill_level),
        "minutes": int(minutes),
        "mentor": ACTIVITY_MENTOR.get(activity_type, "coach"),
        "tier": int(tier),
        "source": source,
        "due": bool(due_at) and overdue >= 0,
        "due_at": due_at,
        "overdue_days": int(overdue),
        "new": bool(new),
        "errors_7d": int(errors_7d),
        "plan_progress": float(plan_progress),
        "leech": bool(leech),
        "card_id": card_id,
        "card_ids": card_ids or ([card_id] if card_id else []),
        "block_id": block_id,
        "step_index": step_index,
        "recent_skill": bool(recent_skill),
        "today_template": bool(today_template),
        "label": label,
        "task": task,
        "template_id": template_id,
        "requires_artifact": requires_artifact or "",
        "artifact_path": requires_artifact or "",
    }


def _activity_for_skill(skill: dict, cards: list[dict], now: str) -> str:
    level = int(skill.get("level") or 0)
    has_cards = any(card.get("skill") == skill.get("id") for card in cards)
    if level <= 0:
        return "concept_block"
    if level == 1:
        return "recall_card" if has_cards else "concept_block"
    if level == 2:
        return "quiz"
    return "transfer_task"


def build_candidates(store: Store, now: str | None = None) -> list[dict]:
    """Turn project state into scheduler candidates (tier 1/2/3)."""
    now = now or now_iso()
    skills = store.skills.get("skills", [])
    cards = store.cards.get("cards", [])
    skills_by_id = {s["id"]: s for s in skills}
    errors_7d = store.errors_last_7d()
    recent_skill = store.last_skill()
    today_templates = store.today_templates()
    today_skills = store.today_skills()
    due_limit = int(store.limits.get("due_cards_per_session", 3))

    candidates: list[dict] = []
    covered_skills: set[str] = set()
    due_cards = [c for c in cards if is_due(c.get("due_at"), now)]
    due_cards.sort(key=lambda c: (-overdue_days(c.get("due_at"), now), c.get("due_at") or "", c.get("id") or ""))

    # ---- Tier 1: due cards (max 3 per session) -------------------------
    for card in due_cards[:due_limit]:
        skill = skills_by_id.get(card.get("skill"), {})
        overdue = overdue_days(card.get("due_at"), now)
        cards_for_skill = [c for c in due_cards if c.get("skill") == card.get("skill")][:3]
        if not cards_for_skill:
            cards_for_skill = [card]
        fronts = "；".join(f"「{c['front']}」" for c in cards_for_skill[:3])
        candidates.append(
            candidate(
                activity_id=f"recall-{card['id']}",
                activity_type="recall_card",
                skill=card.get("skill"),
                skill_title=skill.get("title", card.get("skill", "")),
                skill_level=int(skill.get("level") or 0),
                minutes=ACTIVITY_MINUTES["recall_card"],
                tier=1,
                source="due_card",
                template_id=store.template_id,
                due_at=card.get("due_at"),
                overdue=overdue,
                new=not skill.get("last_review_at"),
                errors_7d=errors_7d.get(card.get("skill"), 0),
                leech=bool(card.get("leech")),
                card_id=card["id"],
                card_ids=[c["id"] for c in cards_for_skill],
                recent_skill=recent_skill == card.get("skill"),
                today_template=("recall_card" in today_templates),
                label=f"到期卡（{card['kind']}）",
                task=f"先不看卡背，用一句话回答：{fronts}答错就留在队列里，结尾只给一句正解。",
            )
        )
        covered_skills.add(card.get("skill"))

    # ---- Tier 1: due skills without a due card -------------------------
    for skill in skills:
        if not is_due(skill.get("due_at"), now) or skill["id"] in covered_skills:
            continue
        activity_type = _activity_for_skill(skill, cards, now)
        minutes = ACTIVITY_MINUTES[activity_type]
        candidates.append(
            candidate(
                activity_id=f"retest-{skill['id']}",
                activity_type=activity_type,
                skill=skill["id"],
                skill_title=skill.get("title", skill["id"]),
                skill_level=int(skill.get("level") or 0),
                minutes=minutes,
                tier=1,
                source="due_skill",
                template_id=store.template_id,
                due_at=skill.get("due_at"),
                overdue=overdue_days(skill.get("due_at"), now),
                new=not skill.get("last_review_at"),
                errors_7d=errors_7d.get(skill["id"], 0),
                recent_skill=recent_skill == skill["id"],
                today_template=(activity_type in today_templates),
                label="到期技能复测",
                task=f"不看资料，独立完成一次「{skill.get('title', skill['id'])}」的复测；答完我再给判定。",
            )
        )
        covered_skills.add(skill["id"])

    # ---- Tier 2: current week's block steps ----------------------------
    block = current_block(store.blocks.get("blocks", []), now)
    if block:
        undone = [(i, step) for i, step in enumerate(block.get("steps", [])) if not step.get("done")]
        for position, (index, step) in enumerate(undone):
            skill = skills_by_id.get(step.get("skill"), {})
            activity_type = step.get("activity_type") or "concept_block"
            minutes = int(step.get("minutes") or ACTIVITY_MINUTES.get(activity_type, 10))
            required = step.get("required_artifact")
            if required is None:
                required = block.get("deliverable", "") if activity_type in PRODUCE_ACTIVITIES else ""
            if activity_type in PRODUCE_ACTIVITIES:
                task = (
                    f"本周块：{block.get('goal')}。这一步只做「{step.get('skill')}」的最小可验证版本；"
                    f"完成标准是把产物写到 {block.get('deliverable')}（未落盘不算完成）。"
                )
            else:
                task = f"本周块：{block.get('goal')}。这一步只做「{step.get('skill')}」的最小概念/回述，不要求产物。"
            candidates.append(
                candidate(
                    activity_id=f"block-{block['week']}-step{index + 1}-{step.get('skill')}",
                    activity_type=activity_type,
                    skill=step.get("skill"),
                    skill_title=skill.get("title", step.get("skill", "")),
                    skill_level=int(skill.get("level") or 0),
                    minutes=minutes,
                    tier=2,
                    source="block_step",
                    template_id=store.template_id,
                    new=not skill.get("last_review_at"),
                    errors_7d=errors_7d.get(step.get("skill"), 0),
                    plan_progress=1.0 if position == 0 else 0.5,
                    recent_skill=recent_skill == step.get("skill"),
                    today_template=(activity_type in today_templates),
                    block_id=block["id"],
                    step_index=index,
                    label=f"本周块第 {index + 1} 步",
                    task=task,
                    requires_artifact=required or "",
                )
            )
            covered_skills.add(step.get("skill"))

    # ---- Tier 3: weak / new content ------------------------------------
    for skill in skills:
        if skill["id"] in covered_skills:
            continue
        activity_type = _activity_for_skill(skill, cards, now)
        minutes = ACTIVITY_MINUTES[activity_type]
        level = int(skill.get("level") or 0)
        label = {0: "新内容", 1: "薄弱项", 2: "巩固", 3: "迁移"}.get(level, "薄弱项")
        candidates.append(
            candidate(
                activity_id=f"weak-{skill['id']}",
                activity_type=activity_type,
                skill=skill["id"],
                skill_title=skill.get("title", skill["id"]),
                skill_level=level,
                minutes=minutes,
                tier=3,
                source="weak_new",
                template_id=store.template_id,
                new=not skill.get("last_review_at"),
                errors_7d=errors_7d.get(skill["id"], 0),
                recent_skill=recent_skill == skill["id"],
                today_template=(activity_type in today_templates),
                label=label,
                task=f"用自己的话讲清「{skill.get('title', skill['id'])}」的最小要点，然后做一个可验证的小任务。",
            )
        )
    return candidates


# --------------------------------------------------------------------------------------
# project init
# --------------------------------------------------------------------------------------



def project_slug(root: Path, name: str | None = None) -> str:
    if name:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower() or "learnark"
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", root.name).strip("-").lower()
    return base or "learnark"


GENERATED_MARKER = "<!-- generated by learnark direction-d-tempo"

AGENTS_TEMPLATE = """# AGENTS.md — Tempo 学习项目

{marker} {version} -->
本目录是一个 LearnArk · Tempo 学习项目（方向 D：动态调度复习型），由运行时 `runtime/learn.py` 管理。
任何 DSH/Agent 进入本目录，先做这三件事，不要凭聊天记录猜状态：

1. 读状态：`python "{entry}" status --project "{root}"`（或读 `.learnark/project.json`、`.learnark/state/*.json`、`.learnark/handoff/latest.md`）。
2. 要开始学习就运行 `start`，不要自行决定学什么：调度器已按到期/预算/同日去重算好，输出里有 top3 候选与理由。
3. 学习者的回答必须通过 `say "原文"` 进入运行时；只有导师机器块（```learn-update```）里的 `attempt` 且 `help_level<=1` 才算证据。

硬规则：

- 调度器权威：导师的 `next` 只记为 `mentor_suggestion`，不得改活动、预算、到期日；`review` 是唯一显式覆盖。
- 不得声称“已掌握”：等级只由运行时按证据提升；L3 只能由“块产物 + ≥7 天延迟复测”授予，纯卡练习最高 L2。
- 不得手改 `.learnark/state/*.json`：写操作请走 CLI（原子写 + 幂等键），journal 是权威记录。
- 离线模式（`--offline` / `LEARNARK_LLM=mock`）的输出是脚本导师，不得当作真实 LLM 教学质量证据。
- 记录位置：`.learnark/journal/events.jsonl`（权威）、`sessions/*.md`（可读会话）、`artifacts/`（产物）。
- 未提交/未推送状态用 `sync` 查看 written/committed/pushed 三态，不要 force push。

命令速查：`start [--minutes N]`、`say "…"`、`due`、`plan`、`review`、`skills`、`status [--json]`、`pause`、`switch <coach|trainer|examiner>`、`sync`、`doctor`、`export --out FILE`。
"""

README_TEMPLATE = """# {goal}

{marker} {version} -->
这是 LearnArk · Tempo（方向 D：动态调度复习型）项目。每次进入只回答“今天有多少分钟”。

## 现在输入什么

```powershell
python "{entry}" start --project "{root}"
```

默认 20 分钟。也可以一句话给预算：

```powershell
python "{entry}" start "今天只有二十分钟" --project "{root}"
python "{entry}" say "只有一刻钟" --project "{root}"
python "{entry}" due --project "{root}"
```

## 一天怎么用

1. `start`——系统选一个 5–20 分钟的活动，并说明为什么是它。
2. 跟着导师做完，用 `say "你的回答"` 继续；`pause` 结束并存档。
3. 明天直接 `start`，到期卡与本周块会自动排进来。

## 记录与恢复

- 权威记录：`.learnark/journal/events.jsonl`；快照：`.learnark/state/*.json`；会话：`sessions/`；产物：`artifacts/`。
- 换机器/干净克隆后直接 `start`，状态只依赖这些文件。
- `sync` 显示 written / committed / pushed 三态；没有远程时只到 committed。
- 离线：加 `--offline`，导师为脚本导师（输出带 `[离线脚本导师]`），不代表真实教学质量。

## 不要做

- 不要手改状态 JSON；不要绕过 `say` 直接写“我学会了”；不要 force push。
"""


def write_project_docs(store: Store) -> None:
    entry = str(variant_root() / "runtime" / "learn.py")
    root = str(store.root)
    version = f"v{VARIANT_VERSION} · core {read_core_version()}"
    agents = AGENTS_TEMPLATE.format(marker=GENERATED_MARKER, version=version, entry=entry, root=root)
    readme = README_TEMPLATE.format(
        marker=GENERATED_MARKER, version=version, entry=entry, root=root, goal=store.meta.get("goal", "学习目标")
    )
    for name, content in (("AGENTS.md", agents), ("README.md", readme)):
        path = store.root / name
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if not existing or GENERATED_MARKER in existing:
            atomic_write_text(path, content)


def read_core_version() -> str:
    path = Path(__file__).resolve().parent / "CORE_VERSION"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def init_project(
    root: str | Path,
    *,
    goal: str,
    template_id: str = "agent-dev",
    minutes_per_week: int | None = None,
    name: str | None = None,
    learner: str | None = None,
    self_report: str | None = None,
) -> dict:
    root = Path(root).resolve()
    template = load_template(template_id)
    meta_path = root / ".learnark" / "project.json"
    existing = read_json(meta_path, None) if meta_path.exists() else None
    created = existing is None
    now = now_iso()
    self_report_text = (self_report or "").strip()

    for sub in (".learnark/state", ".learnark/journal", ".learnark/handoff", "sessions", "artifacts"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    if created:
        weekly = int(minutes_per_week if minutes_per_week is not None else template.get("minutes_per_week", 600))
        meta = {
            "schema_version": SCHEMA_VERSION,
            "variant": VARIANT_ID,
            "variant_version": VARIANT_VERSION,
            "core_version": read_core_version(),
            "slug": project_slug(root, name),
            "goal": goal.strip() or template.get("goal_default", "学习目标"),
            "template_id": template_id,
            "created_at": now,
            "minutes_per_week": weekly,
            "minutes_default": int(template.get("minutes_default", 20)),
            "limits": normalize_limits(template),
            "mentors": list(template.get("mentors") or MENTOR_ORDER),
            "learner": {
                "name": learner or "学习者",
                # no invented biography: only what the learner actually said (or passes via --self-report)
                "self_report": [self_report_text] if self_report_text else [],
                "note": (
                    f"学习者自述（未经证据校准）：{self_report_text}"
                    if self_report_text
                    else "尚未记录学习者自述；只按行为证据校准（可随时用 init --self-report 补充原话）"
                ),
                "evidence_policy": "self_report < observed < verified",
            },
            "mentor": (template.get("mentors") or list(MENTOR_ORDER))[0],
            "diagnosed": False,
        }
        write_json(meta_path, meta, backup=True)
    else:
        meta = existing
        if self_report_text:
            learner_meta = meta.setdefault("learner", {})
            reports = list(learner_meta.get("self_report") or [])
            if self_report_text not in reports:
                reports.append(self_report_text)
            learner_meta["self_report"] = reports
            learner_meta["note"] = "学习者自述（未经证据校准）：" + "；".join(reports)
            write_json(meta_path, meta, backup=True)

    store = Store(root)
    store.load()
    if not store.skills.get("skills"):
        store.skills = {"schema_version": SCHEMA_VERSION, "skills": seed_skills(template, now)}
        store.touch("skills")
    if not store.cards.get("cards"):
        store.cards = {"schema_version": SCHEMA_VERSION, "cards": seed_cards(template, now)}
        store.touch("cards")
        cards = store.cards["cards"]
        today_cards = sum(1 for card in cards if card.get("due_at") == now)
        store.append(
            "initial_cards_spread",
            {
                "total": len(cards),
                "today": today_cards,
                "future": len(cards) - today_cards,
                "policy": "first 2 due today; rest +1..+10 days",
            },
            dedupe_key=f"spread:{meta['slug']}",
        )
    if not store.schedule.get("today", {}).get("date"):
        store.schedule["today"] = {
            "date": today_str(),
            "minutes_budget": int(meta["minutes_default"]),
            "minutes_left": int(meta["minutes_default"]),
            "items": [],
        }
        store.touch("schedule")
    if not store.blocks.get("blocks"):
        ensure_block(store, now)

    write_project_docs(store)
    if created:
        store.append(
            "project_initialized",
            {
                "goal": meta["goal"],
                "template_id": template_id,
                "minutes_per_week": meta["minutes_per_week"],
                "cards": len(store.cards.get("cards", [])),
                "skills": len(store.skills.get("skills", [])),
                "learner_note": meta["learner"]["note"],
            },
            dedupe_key=f"init:{meta['slug']}",
        )
    store.save()

    from learncore.sync import GitSync, ensure_git_identity

    # core 1.0.2 writes .gitignore (locks/usage/sync-log) and .gitattributes (* -text)
    sync = GitSync(
        root,
        include=[".learnark", "sessions", "artifacts", "AGENTS.md", "README.md", ".gitignore", ".gitattributes"],
    )
    git_created = []
    try:
        git_created = sync.ensure_repository()
    except LearnError:
        git_created = []
    try:
        ensure_git_identity(root)
        commit = sync.commit(f"learnark({meta['slug']}): init {template_id}")
    except LearnError:
        commit = {"committed": False}
    return {
        "root": root,
        "created": created,
        "meta": meta,
        "card_count": len(store.cards.get("cards", [])),
        "skill_count": len(store.skills.get("skills", [])),
        "git_created": git_created,
        "commit": commit,
        "repaired": store.repairs,
    }


# --------------------------------------------------------------------------------------
# sessions and handoff
# --------------------------------------------------------------------------------------


def session_path(root: Path, session_id: str) -> Path:
    return root / "sessions" / f"{session_id}.md"


def new_session_id(store: Store, mentor: str) -> str:
    base = f"{clock.stamp_for_filename()}-{mentor}"
    candidate = base
    index = 2
    while session_path(store.root, candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def session_header(store: Store, session: dict, activity: dict, budget: int, forced: str = "") -> str:
    now = now_iso()
    simulated = "模拟时间（LEARNARK_NOW=" + str(clock.now().isoformat(timespec="seconds")) + "；仅证明调度逻辑）" if clock.is_simulated() else "真实时间"
    lines = [
        f"# {date_of(now)} {str(now)[11:16]} — Tempo · {session['mentor']}",
        f"- session: {session['id']}  mentor: {session['mentor']}  activity: {activity['activity_id']} ({activity['activity_type']})",
        f"- learner: {store.meta.get('learner', {}).get('name', '学习者')}  goal: {store.meta.get('goal', '')}  offline: {str(store.offline).lower()}",
        f"- budget: {budget} 分钟  skill: {activity.get('skill') or '-'} (L{activity.get('level', 0)})  tier: {activity.get('tier')}"
        + (f"  forced: {forced}" if forced else ""),
        f"- time: {simulated}",
        "",
    ]
    return "\n".join(lines)


def open_session(store: Store, activity: dict, budget: int, opening: str, *, forced: str = "", mode: str = "mock") -> dict:
    mentor = activity.get("mentor") or "coach"
    session_id = new_session_id(store, mentor)
    path = session_path(store.root, session_id)
    session = {
        "id": session_id,
        "mentor": mentor,
        "path": str(path.relative_to(store.root)).replace("\\", "/"),
        "started_at": now_iso(),
        "budget": int(budget),
        "activity": activity,
        "offline": store.offline,
        "mode": mode,
        "turns": 0,
        "messages": [{"role": "mentor", "text": opening, "at": now_iso(), "opening": True}],
        "forced": forced,
    }
    text = session_header(store, session, activity, budget, forced=forced) + "## 导师（开场）\n" + opening.strip() + "\n"
    atomic_write_text(path, text)
    store.schedule["current_session"] = session
    store.meta["mentor"] = mentor
    override = str(store.meta.get("mentor_override") or "")
    if override and mentor == override:
        store.meta.pop("mentor_override", None)
        store.append(
            "mentor_override_used",
            {
                "mentor": mentor,
                "activity_id": activity["activity_id"],
                "activity_type": activity.get("activity_type"),
                "session": session_id,
                "reason": "explicit-switch-honored",
            },
            dedupe_key=f"overrideused:{session_id}",
        )
    resume = store.schedule.get("resume_activity") or {}
    if resume and (
        resume.get("activity_id") == activity.get("activity_id")
        or set(resume.get("card_ids") or []) & set(activity.get("card_ids") or [])
    ):
        store.schedule.pop("resume_activity", None)
        store.append(
            "resume_activity_used",
            {"session": session_id, "activity_id": activity.get("activity_id"), "skill": activity.get("skill")},
            dedupe_key=f"resumeused:{session_id}",
        )
    store.touch("meta", "schedule")
    store.schedule["last_activity"] = {
        "id": activity["activity_id"],
        "activity_type": activity["activity_type"],
        "skill": activity.get("skill"),
        "at": now_iso(),
        "session": session_id,
    }
    recent = store.schedule.setdefault("recent", [])
    recent.append(
        {
            "skill": activity.get("skill"),
            "activity_id": activity["activity_id"],
            "activity_type": activity["activity_type"],
            "at": now_iso(),
        }
    )
    del recent[:-20]
    item = {
        "activity_id": activity["activity_id"],
        "activity_type": activity["activity_type"],
        "skill": activity.get("skill"),
        "started_at": now_iso(),
        "done": False,
        "session": session_id,
        "mentor": mentor,
        "minutes": activity.get("minutes"),
    }
    store.schedule["today"].setdefault("items", []).append(item)
    store.refresh_budget_fields()
    store.touch("schedule")
    store.append(
        "session_opened",
        {
            "session": session_id,
            "mentor": mentor,
            "activity_id": activity["activity_id"],
            "activity_type": activity["activity_type"],
            "skill": activity.get("skill"),
            "minutes": activity.get("minutes"),
            "budget": budget,
            "forced": forced or None,
            "mode": mode,
        },
        dedupe_key=f"session:{session_id}",
    )
    return session


def append_session_turn(store: Store, session: dict, learner_text: str, mentor_text: str, records: list[str]) -> None:
    path = store.root / session["path"]
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    block = ["", "## 学习者", learner_text.strip(), "", "## 导师", mentor_text.strip(), "", "## 记录"]
    block += [f"- {line}" for line in records] or ["- （无）"]
    atomic_write_text(path, existing.rstrip() + "\n" + "\n".join(block) + "\n")
    session.setdefault("messages", []).append({"role": "learner", "text": learner_text.strip(), "at": now_iso()})
    session["messages"].append({"role": "mentor", "text": mentor_text.strip(), "at": now_iso()})
    del session["messages"][:-16]
    session["turns"] = int(session.get("turns", 0)) + 1
    store.touch("schedule")


def append_session_note(store: Store, session: dict, lines: list[str]) -> None:
    """Append a non-turn note (pause/switch footer) to the session markdown."""
    path = store.root / session.get("path", "")
    if not path.exists():
        return
    existing = path.read_text(encoding="utf-8")
    block = ["", "## 收尾"] + [f"- {line}" for line in lines]
    atomic_write_text(path, existing.rstrip() + "\n" + "\n".join(block) + "\n")


def count_session_turns(store: Store, session_id: str) -> int:
    return sum(1 for event in store.events("turn") if (event.get("payload") or {}).get("session") == session_id)


def handoff_summary(store: Store) -> dict:
    schedule = store.schedule
    due_cards = store.due_cards()
    due_skills = store.due_skills()
    last = schedule.get("last_activity") or {}
    current = schedule.get("current_session") or {}
    unstable = [
        skill
        for skill in store.skills.get("skills", [])
        if int(skill.get("lapses") or 0) > 0 or (skill.get("wrong_tags") and int(skill.get("level") or 0) <= 1)
    ][:3]
    next_step = ""
    remaining = store.today_remaining()
    min_activity = int(store.limits.get("min_activity", 5))
    exhausted = store.cap_reached() or remaining < min_activity
    planning_budget = remaining if not exhausted else store.minutes_default()
    try:
        decision = plan_decision(store, minutes=planning_budget, max_items=1, ignore_today=exhausted)
        if (decision.get("fallback") or not decision.get("chosen")) and not exhausted:
            decision = plan_decision(store, minutes=store.minutes_default(), max_items=1, ignore_today=True)
        if decision.get("fallback") or not decision.get("chosen"):
            next_step = "下次 start 重新调度（到期优先）"
        else:
            chosen = decision["chosen"]
            next_step = (
                f"{chosen['activity_type']} · {chosen.get('skill') or '-'}"
                f"（{chosen['minutes']} 分钟，{'下次' if exhausted else '现在'}；{chosen.get('activity_id')}）"
            )
    except LearnError:
        next_step = ""
    unfinished = [
        {
            "activity_id": item.get("activity_id"),
            "activity_type": item.get("activity_type"),
            "skill": item.get("skill"),
            "minutes": item.get("minutes"),
        }
        for item in store.today_items()
        if not item.get("done")
    ]
    artifacts = [
        (event.get("payload") or {}).get("path")
        for event in store.events("artifact_acknowledged", "block_artifact")
        if (event.get("payload") or {}).get("path")
    ]
    open_questions = [f"{s['id']} 的错误标签：{'、'.join(s.get('wrong_tags') or [])}" for s in unstable if s.get("wrong_tags")]
    messages = (current or {}).get("messages") or []
    if messages and messages[-1].get("role") == "mentor":
        mentor_text = messages[-1].get("text") or ""
        if "？" in mentor_text or "?" in mentor_text:
            last_sentence = ""
            for piece in re.split(r"(?<=[。！？?])", mentor_text):
                if "？" in piece or "?" in piece:
                    last_sentence = piece.strip()
            if last_sentence:
                open_questions.append(f"导师追问：{last_sentence[:160]}")
    handoff = store.root / ".learnark" / "handoff" / "latest.md"
    previous_next = ""
    if handoff.exists():
        text = handoff.read_text(encoding="utf-8")
        match = re.search(r"- 下一步：(?P<v>.+)", text)
        if match:
            previous_next = match.group("v").strip()
    return {
        "generated_at": now_iso(),
        "mentor": current.get("mentor") or store.meta.get("mentor"),
        "session": current.get("id"),
        "last_activity": last,
        "budget": schedule.get("today", {}).get("minutes_budget"),
        "budget_used": store.today_used(),
        "budget_remaining": remaining,
        "items_today": len(store.today_items()),
        "due_cards": len(due_cards),
        "due_skills": len(due_skills),
        "due_max_overdue": max([overdue_days(c.get("due_at")) for c in due_cards] or [0]),
        "unstable": unstable,
        "next_step": next_step,
        "unfinished": unfinished,
        "previous_next": previous_next,
        "artifact": artifacts[-1] if artifacts else "",
        "pending_artifact": str((current or {}).get("artifact_pending") or ""),
        "open_questions": open_questions,
    }


def write_handoff(store: Store, *, reason: str, note: str = "", mentor_from: str | None = None, mentor_to: str | None = None) -> dict:
    summary = handoff_summary(store)
    summary.update({"reason": reason, "note": note, "mentor_from": mentor_from, "mentor_to": mentor_to})
    lines = [
        f"# 交接 · {date_of(summary['generated_at'])} {str(summary['generated_at'])[11:16]}",
        "",
        f"- 原因：{reason}" + (f"（{note}）" if note else ""),
        f"- 导师：{mentor_from or summary['mentor']}" + (f" → {mentor_to}" if mentor_to else ""),
        f"- 会话：{summary.get('session') or '-'}",
        f"- 上次停在哪：{summary['last_activity'].get('activity_type') or '-'} · {summary['last_activity'].get('skill') or '-'}"
        f"（{fmt_at(summary['last_activity'].get('at'))}）",
        f"- 试过什么：今天已排 {summary['items_today']} 项，预算 {summary['budget']} 分钟"
        f"（已用 {summary.get('budget_used', 0)}，剩 {summary.get('budget_remaining', 0)}）；到期卡 {summary['due_cards']} 张"
        f"（最久逾期 {summary['due_max_overdue']} 天）",
        f"- 哪里不稳："
        + ("、".join(f"{s['id']}（L{s.get('level', 0)}，lapses {s.get('lapses', 0)}）" for s in summary["unstable"]) or "暂无记录"),
        f"- 产物：{summary.get('artifact') or '无'}"
        + (f"；待补 {summary['pending_artifact']}" if summary.get("pending_artifact") else ""),
        f"- 未完成："
        + ("、".join(f"{u['activity_type']} · {u.get('skill') or '-'}（{u.get('minutes')} 分钟）" for u in summary.get("unfinished") or []) or "无"),
        f"- 下一步：{summary['next_step'] or summary['previous_next'] or '下次 start 重新调度（到期优先）'}",
        f"- 未决问题："
        + ("；".join(summary["open_questions"]) or "无"),
        "",
        f"生成时间：{summary['generated_at']}（{'模拟时间' if clock.is_simulated() else '真实时间'}）",
        "",
    ]
    path = store.root / ".learnark" / "handoff" / "latest.md"
    atomic_write_text(path, "\n".join(lines))
    store.append(
        "handoff",
        {
            "reason": reason,
            "note": note,
            "session": summary.get("session"),
            "mentor_from": mentor_from,
            "mentor_to": mentor_to,
            "next": summary["next_step"],
            "path": str(path.relative_to(store.root)).replace("\\", "/"),
        },
        dedupe_key=f"handoff:{summary.get('session') or 'none'}:{reason}:{count_session_turns(store, summary.get('session') or '')}",
    )
    return {"path": path, "summary": summary, "text": path.read_text(encoding="utf-8")}


# --------------------------------------------------------------------------------------
# scheduling entry points
# --------------------------------------------------------------------------------------


def prepare_day(store: Store, now: str | None = None) -> dict:
    """Reset/roll the day, fold backlog, apply decay, promote queued cards."""
    now = now or now_iso()
    today = date_of(now)
    schedule = store.schedule
    if schedule.get("today", {}).get("date") != today:
        schedule["today"] = {
            "date": today,
            "minutes_budget": store.minutes_default(),
            "minutes_used": 0,
            "minutes_left": store.minutes_default(),
            "budget_source": "default",
            "items": [],
        }
        schedule["plan"] = []
        store.touch("schedule")

    notes: list[str] = []
    previous_session = schedule.get("current_session")
    current = schedule.get("current_session")
    if current and date_of(current.get("started_at")) != today:
        schedule["current_session"] = None
        store.touch("schedule")
        notes.append("新的一天：上一次会话已结束，今天重新调度")
    # backlog fold (design §6) -- never fold the unfinished current card
    protected: set[str] = set()
    current_activity = (previous_session or {}).get("activity") or {}
    for card_id in current_activity.get("card_ids") or []:
        protected.add(str(card_id))
    current_aid = str(current_activity.get("activity_id") or "")
    if current_aid.startswith("recall-"):
        protected.add(current_aid.replace("recall-", "", 1))
    resume = schedule.get("resume_activity") or {}
    for card_id in resume.get("card_ids") or []:
        protected.add(str(card_id))
    resume_aid = str(resume.get("activity_id") or "")
    if resume_aid.startswith("recall-"):
        protected.add(resume_aid.replace("recall-", "", 1))
    folded = fold_backlog(
        store.cards.get("cards", []),
        now,
        int(store.limits.get("backlog_cap", 12)),
        protected=protected,
    )
    if folded:
        store.touch("cards")
        for card in folded:
            store.append(
                "backlog_folded",
                {
                    "card": card["id"],
                    "skill": card.get("skill"),
                    "due_at": card.get("due_at"),
                    "folds": card.get("backlog_folds", 1),
                    "reason": "积压超过 12 张，最旧卡折叠 +3 天",
                },
                dedupe_key=f"backlog:{card['id']}:{date_of(card['due_at'])}",
            )
        notes.append(f"今天到期的卡超过 {store.limits.get('backlog_cap', 12)} 张：最旧的 {len(folded)} 张已顺延 3 天（仍是到期卡，不是欠账）。")

    # overdue decay (design §9): due_at older than 2x interval -> level -1, once per episode
    for skill in store.skills.get("skills", []):
        due_at = skill.get("due_at")
        if not due_at:
            continue
        overdue = overdue_days(due_at, now)
        stability = float(skill.get("stability_days") or 1.0)
        if overdue > 2 * max(1.0, stability) and skill.get("decay_marked_for") != due_at:
            if int(skill.get("level") or 0) > 0:
                old = int(skill["level"])
                skill["level"] = old - 1
                skill["level_reason"] = f"逾期 {overdue} 天未复习，按规则降 1 级（{old}→{old - 1}）"
                skill["evidence_refs"] = (skill.get("evidence_refs") or [])[-20:]
                store.touch("skills")
                store.append(
                    "decayed",
                    {"skill": skill["id"], "reason": "overdue", "overdue_days": overdue, "from": old, "to": old - 1},
                    dedupe_key=f"decay:{skill['id']}:{due_at}",
                )
                notes.append(f"{skill['id']} 逾期 {overdue} 天，已降 1 级（遗忘会真实发生）")
            skill["decay_marked_for"] = due_at
            store.touch("skills")

    # promote queued cards when the weekly cap allows
    promoted = promote_queued_cards(store, now)
    if promoted:
        notes.append(f"本周卡量回到上限内，补建 {len(promoted)} 张排队卡")
    used_now = store.today_used()
    today_state = schedule.get("today", {})
    if today_state.get("minutes_used") != used_now or today_state.get("minutes_left") != max(
        0, int(today_state.get("minutes_budget") or 0) - used_now
    ):
        store.refresh_budget_fields()
    return {"notes": notes, "folded": len(folded), "promoted": len(promoted)}


def promote_queued_cards(store: Store, now: str) -> list[dict]:
    queued_events = [e for e in store.events("card_queued") if not e.get("payload", {}).get("promoted")]
    if not queued_events:
        return []
    cap = weekly_card_cap(store.meta.get("minutes_per_week", 600))
    used = len(cards_created_this_week(store.cards.get("cards", []), now))
    promoted = []
    existing_ids = {c["id"] for c in store.cards.get("cards", [])}
    for event in queued_events:
        if used >= cap:
            break
        payload = event.get("payload") or {}
        card = payload.get("card") or {}
        if not card or card.get("id") in existing_ids:
            continue
        card = dict(card)
        card.setdefault("step", 0)
        card.setdefault("ease", 1.0)
        card.setdefault("interval_days", 1)
        card.setdefault("due_at", now)
        card.setdefault("last_review_at", None)
        card.setdefault("lapses", 0)
        card.setdefault("consecutive_lapses", 0)
        card.setdefault("leech", False)
        card.setdefault("needs_rewrite", False)
        card["source_event"] = event.get("id", "")
        card["created_at"] = now
        store.cards.setdefault("cards", []).append(card)
        store.touch("cards")
        used += 1
        promoted.append(card)
        store.append(
            "card_promoted",
            {"card": card["id"], "skill": card.get("skill"), "source_event": event.get("id")},
            dedupe_key=f"promote:{card['id']}",
        )
    return promoted


def core_block_priority(store: Store, now: str, minutes: int) -> tuple[set[str], dict | None]:
    """The writing deliverable of the current block is the email-template core."""
    if store.template_id != "email":
        return set(), None
    block = current_block(store.blocks.get("blocks", []), now)
    if not block:
        return set(), None
    for index, step in enumerate(block.get("steps", [])):
        if step.get("done"):
            continue
        activity_type = step.get("activity_type") or "concept_block"
        if activity_type not in PRODUCE_ACTIVITIES:
            continue
        planned = int(step.get("minutes") or ACTIVITY_MINUTES.get(activity_type, 10))
        info = {
            "block": block["id"],
            "step": index,
            "activity_id": f"block-{block['week']}-step{index + 1}-{step.get('skill')}",
            "activity_type": activity_type,
            "skill": step.get("skill"),
            "minutes": planned,
            "goal": block.get("goal"),
        }
        return ({info["activity_id"]} if planned <= minutes else set()), info
    return set(), None


def plan_decision(
    store: Store,
    minutes: int,
    *,
    max_items: int = 2,
    allow_repeat: bool = False,
    force_due: bool = False,
    now: str | None = None,
    ignore_today: bool = False,
) -> dict:
    """Schedule for now (``ignore_today=False``) or for the next session.

    ``ignore_today`` drops the same-day repeat filters so that a *next-session*
    suggestion can be concrete (a real card/skill), not a placeholder.
    """
    now = now or now_iso()
    candidates = build_candidates(store, now)
    priority_ids, _ = core_block_priority(store, now, minutes)
    resume = store.schedule.get("resume_activity") or {}
    if resume.get("activity_id"):
        priority_ids = set(priority_ids) | {str(resume["activity_id"])}
    decision = select_activities(
        candidates,
        minutes,
        max_items=max_items,
        allow_repeat=allow_repeat,
        force_due=force_due,
        min_activity=int(store.limits.get("min_activity", 5)),
        today_templates=set() if ignore_today else store.today_templates(),
        today_skills=set() if ignore_today else store.today_skills(),
        due_cards_cap=int(store.limits.get("due_cards_per_session", 3)),
        priority_ids=priority_ids if not force_due else None,
    )
    override = str(store.meta.get("mentor_override") or "")
    if override in MENTOR_ORDER:
        chosen = decision.get("chosen") or {}
        if chosen.get("mentor") != override:
            activity = _override_activity(store, chosen, override, minutes)
            if activity is not None:
                label = activity_label(store.template_id, activity["activity_type"])
                reason = (
                    f"导师覆盖：上次 switch 指定 {mentor_label(override)}；"
                    f"本次由 {mentor_label(override)} 带{label}（{activity['minutes']} 分钟），优先于活动类型绑定。"
                )
                row = {
                    "activity_id": activity["activity_id"],
                    "activity_type": activity["activity_type"],
                    "skill": activity.get("skill"),
                    "minutes": activity["minutes"],
                    "tier": 0,
                    "source": "mentor-override",
                    "score": 1.0,
                    "factors": {},
                    "status": "chosen",
                    "main_label": "导师覆盖",
                    "reason": f"switch 指定 {override}",
                }
                return {
                    "chosen": activity,
                    "plan": [activity],
                    "plan_ids": [activity["activity_id"]],
                    "rows": [row],
                    "top": [],
                    "tier_used": 0,
                    "fallback": False,
                    "reason_line": reason,
                }
    return decision


def _override_activity(store: Store, chosen: dict, override: str, minutes: int) -> dict | None:
    """Build the activity type the switched mentor can actually lead."""
    skill = store.skill(chosen.get("skill")) if chosen.get("skill") else None
    if skill is None:
        due = store.due_skills()
        skill = due[0] if due else None
    if skill is None:
        skills = store.skills.get("skills", [])
        skill = min(skills, key=lambda item: (int(item.get("level") or 0), item["id"])) if skills else None
    if skill is None:
        return None
    if override == "examiner":
        activity_type, activity_minutes = ("quiz", 6) if minutes >= 6 else ("recall_card", 5)
    elif override == "coach":
        if minutes >= 10:
            activity_type, activity_minutes = "concept_block", 10
        elif minutes >= 8:
            activity_type, activity_minutes = "explain_back", 8
        else:
            activity_type, activity_minutes = "recall_card", 5
    else:
        activity_type, activity_minutes = "recall_card", 5
    label = activity_label(store.template_id, activity_type)
    return {
        "activity_id": f"override-{override}-{skill['id']}-{activity_minutes}",
        "activity_type": activity_type,
        "template": activity_type,
        "skill": skill["id"],
        "skill_title": skill.get("title"),
        "level": int(skill.get("level") or 0),
        "minutes": activity_minutes,
        "mentor": override,
        "tier": 0,
        "source": "mentor-override",
        "due": False,
        "due_at": None,
        "overdue_days": 0,
        "new": False,
        "errors_7d": 0,
        "plan_progress": 0.0,
        "leech": False,
        "card_id": None,
        "card_ids": [],
        "block_id": None,
        "step_index": None,
        "recent_skill": False,
        "today_template": False,
        "label": label,
        "task": f"按 {mentor_label(override)} 的方式完成一次{label}",
        "template_id": store.template_id,
        "requires_artifact": "",
        "artifact_path": "",
    }


def decision_signature(store: Store) -> str:
    return "|".join(
        [
            today_str(),
            str(len(store.today_items())),
            str(store.today_budget()),
            str(store.today_used()),
            str(len(store.events())),
        ]
    )


def decision_id(decision: dict, budget: int) -> str:
    raw = json.dumps(
        {
            "chosen": (decision.get("chosen") or {}).get("activity_id"),
            "plan": decision.get("plan_ids") or [(c.get("activity_id")) for c in decision.get("plan") or []],
            "budget": int(budget),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha(raw, 12)


def _slim_decision(decision: dict) -> dict:
    return {
        "chosen": decision.get("chosen") or {},
        "plan": decision.get("plan") or [],
        "plan_ids": decision.get("plan_ids") or [],
        "rows": decision.get("rows") or [],
        "top": decision.get("top") or [],
        "tier_used": decision.get("tier_used"),
        "fallback": bool(decision.get("fallback")),
        "reason_line": decision.get("reason_line"),
    }


def preview_path(store: Store) -> Path:
    return store.root / ".learnark" / "tmp" / "next-decision.json"


def save_preview(store: Store, decision: dict, budget: int, when: str) -> str:
    path = preview_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    did = decision_id(decision, budget)
    atomic_write_text(
        path,
        json.dumps(
            {
                "id": did,
                "signature": decision_signature(store),
                "budget": int(budget),
                "when": when,
                "decision": _slim_decision(decision),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return did


def load_preview(store: Store, budget: int) -> dict | None:
    path = preview_path(store)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if payload.get("signature") != decision_signature(store):
        return None
    if int(payload.get("budget") or 0) != int(budget):
        return None
    decision = payload.get("decision")
    return decision if isinstance(decision, dict) and decision.get("chosen") else None


def clear_preview(store: Store) -> None:
    try:
        preview_path(store).unlink()
    except OSError:
        pass


def record_schedule_decision(store: Store, session_id: str, decision: dict, budget: int, *, forced: str = "", entry: int = 0) -> dict:
    payload = {
        "session": session_id,
        "entry": entry,
        "decision_id": decision_id(decision, budget),
        "budget": budget,
        "chosen": (decision.get("chosen") or {}).get("activity_id"),
        "chosen_type": (decision.get("chosen") or {}).get("activity_type"),
        "chosen_skill": (decision.get("chosen") or {}).get("skill"),
        "plan": decision.get("plan_ids") or [],
        "tier": decision.get("tier_used"),
        "fallback": decision.get("fallback"),
        "forced": forced or None,
        "reason": decision.get("reason_line"),
        "candidates": [
            {
                "activity_id": row["activity_id"],
                "activity_type": row["activity_type"],
                "skill": row.get("skill"),
                "minutes": row["minutes"],
                "tier": row["tier"],
                "source": row.get("source"),
                "score": row["score"],
                "factors": row["factors"],
                "status": row["status"],
                "reason": row["reason"],
            }
            for row in decision.get("rows", [])
        ],
    }
    return store.append("schedule_decision", payload, dedupe_key=f"schedule:{session_id}:{entry}") or {}


def minutes_left_today(store: Store, budget: int) -> int:
    """Remaining minutes for *this entry*: budget minus the current session's activity."""
    current = store.schedule.get("current_session") or {}
    used = 0
    if current:
        used = int((current.get("activity") or {}).get("minutes") or 0)
    return max(0, int(budget) - used)


# --------------------------------------------------------------------------------------
# mentor prompt / context / openings
# --------------------------------------------------------------------------------------


def repair_missing_update(llm, *, system: str, context: str, previous_raw: str, learner_text: str = ""):
    """Ask the mentor once for the machine block it forgot; return (updates, raw, error)."""
    from learncore import mentor as mentor_core

    prompt = (
        "（运行时）你上一条回复缺少 learn-update 机器块，本轮无法记录证据。\n\n"
        f"学习者原话：\n{learner_text}\n\n你上一条回复：\n{previous_raw}\n\n"
        "请只输出那个机器块：以 ```learn-update 开头、JSON 对象、以 ``` 结束；不要重复正文，不要解释。"
        "attempt.correct 必须与你上一条回复的实际判定一致（你说了“对/正确”就填 true），"
        "help_level 填你上一条回复实际给出的最高帮助等级。"
    )
    try:
        turn = mentor_core.run_turn(
            llm,
            system=system,
            context=context,
            user=prompt,
            transcript=[],
            max_tokens=500,
            temperature=0.2,
        )
    except LearnError as exc:
        return None, "", f"补机器块失败：{exc}"
    return turn.updates, turn.raw, turn.update_error


def mentor_system_prompt(store: Store, mentor: str, activity: dict) -> str:
    path = variant_root() / "mentors" / f"{mentor}.md"
    base = path.read_text(encoding="utf-8") if path.exists() else f"你是 Tempo 的 {mentor} 导师。"
    addendum = f"""
## 运行时约束（Tempo v{VARIANT_VERSION}，调度器权威）

- 本轮已由调度器选定：活动 `{activity.get('activity_id')}` · {activity.get('activity_type')} · {activity.get('minutes')} 分钟 · 技能 `{activity.get('skill')}`。
- 你只教这一个活动；不得新增活动、延长预算、更改到期日或计划，不得承诺加课。
- 正文用中文；结尾恰好一个 ```learn-update``` 机器块，块后不得再有正文。
- 扩展字段仅允许 `card`（对象或 ≤3 条数组）与 `skill_signal`（≤1 条）；`next` 只是建议，调度器可以且经常不采纳。
- 绝不能声称学习者“已掌握”；等级由运行时按证据判定。`help_level` 按本轮实际给到的最高提示级别填写。
- 学习者自述（“我懂了”“我学过”）不是证据，不得据此判 correct=true。
- 正文可以很短，但结尾必须恰好有一个 ```learn-update``` 块；缺块的本轮视为无效、无法记录证据。
"""
    from learncore.mentor import UPDATE_HELP

    return base.strip() + "\n" + addendum + "\n" + UPDATE_HELP


def mentor_context(store: Store, session: dict, activity: dict) -> str:
    schedule = store.schedule
    today = schedule.get("today", {})
    skill = store.skill(activity.get("skill") or "")
    due_cards = store.due_cards()
    due_line = (
        f"到期卡 {len(due_cards)} 张，最久逾期 {max([overdue_days(c.get('due_at')) for c in due_cards] or [0])} 天"
        if due_cards
        else "没有到期卡"
    )
    recent_events = store.events("attempt", "level_change", "card_reviewed")[-3:]
    recent_bits = []
    for event in recent_events:
        payload = event.get("payload") or {}
        recent_bits.append(
            f"{date_of(event.get('at'))} {event.get('kind')}"
            + (f"({payload.get('skill')})" if payload.get("skill") else "")
        )
    skills = store.skills.get("skills", [])
    skill_bits = "、".join(f"{s['id']}=L{s.get('level', 0)}" for s in skills[:8])
    handoff_path = store.root / ".learnark" / "handoff" / "latest.md"
    handoff_next = ""
    if handoff_path.exists():
        match = re.search(r"- 下一步：(?P<v>.+)", handoff_path.read_text(encoding="utf-8"))
        if match:
            handoff_next = match.group("v").strip()
    level_reason = (skill or {}).get("level_reason", "未接触")
    learner = store.meta.get("learner", {})
    self_reports = learner.get("self_report") or []
    learner_line = f"{learner.get('name', '学习者')}（{learner.get('note', '') or '还没有记录自述'}）"
    if self_reports:
        learner_line += "；学习者原话：" + "；".join(str(item) for item in self_reports[:3])
    artifact_line = "无产物要求"
    required = str(activity.get("requires_artifact") or session.get("artifact_pending") or "")
    if required:
        exists = (store.root / required).exists()
        artifact_line = f"{required}（{'已落盘，待运行时确认' if exists else '未落盘；未确认前不得记完成'}）"
    return "\n".join(
        [
            f"目标：{store.meta.get('goal', '')}",
            f"学习者：{learner_line}",
            f"模板/导师：{store.template_id} · {session.get('mentor')}",
            f"当前活动：{activity.get('activity_id')} · {activity.get('activity_type')} · {activity.get('minutes')} 分钟"
            f" · 技能 {activity.get('skill')}（{activity.get('skill_title')}，L{activity.get('level')}）",
            f"技能等级：{activity.get('skill_title')} 当前 L{(skill or {}).get('level', 0)}；等级依据：{level_reason}",
            f"预算：本次 {session.get('budget')} 分钟；今日已用 {store.today_used()} / 预算 {store.today_budget()} 分钟；{due_line}",
            f"产物：{artifact_line}",
            f"技能平表：{skill_bits}",
            f"最近记录：{'；'.join(recent_bits) or '无'}",
            f"上次交接下一步：{handoff_next or '无'}",
            f"本轮任务：{activity.get('task')}",
            "提醒：这是碎片化微活动，一次只解一个卡点；剩余时间少就立即收尾。",
            "提醒：正文末尾必须恰好有一个 ```learn-update``` 机器块；没有块=本轮无效、无法记录证据。",
        ]
    )


def card_backs(store: Store, activity: dict) -> str:
    cards = []
    for card_id in activity.get("card_ids") or []:
        card = store.card(card_id)
        if card:
            cards.append(f"{card['id']}｜{card['front']}｜{card['back']}")
    return "\n".join(cards)


def local_opening(store: Store, activity: dict, decision: dict, budget: int) -> str:
    """Deterministic opening used in offline mode (and as a safety net)."""
    amount = activity.get("minutes") or 0
    title = activity.get("skill_title") or activity.get("skill") or "当前技能"
    label = activity_label(store.template_id, activity.get("activity_type", ""))
    backs = card_backs(store, activity)
    lines = [
        f"[离线脚本导师] {mentor_label(activity.get('mentor', 'coach'))} 的开场"
        "（本地模板生成；离线模式不代表真实教学质量）",
        f"活动：{label}（{activity.get('activity_id')}）· {amount} 分钟 · 技能 {activity.get('skill')}（{title}，L{activity.get('level', 0)}）",
        f"为什么是它：{decision.get('reason_line') or '到期优先。'}",
        "完成规则：判对且达到完成标准才算完成；只答一部分记 partial，活动保持开放。",
    ]
    activity_type = activity.get("activity_type")
    if activity_type == "recall_card" and backs:
        lines.append("开始之前不要看卡背。第一张：" + (backs.split("\n")[0].split("｜")[1] if "｜" in backs.split("\n")[0] else activity.get("task")))
        lines.append("规则：一次一题，答完我记对错与 help_level；答错留在队列里，不追进度。")
    elif activity_type == "concept_block":
        lines.append(f"开始：先用一句话说出你对「{title}」的理解；我给一个最小例子，然后你用自己的话复述。")
        lines.append("规则：讲解本身不算证据；只有你独立复述正确并 help_level ≤1 才 +1 级。")
    elif activity_type == "explain_back":
        lines.append(f"开始：用 3–5 句讲清「{title}」：是什么、为什么、什么情况下不适用。")
        lines.append("规则：按 准确/完整/因果/边界 四项看，≥3 项通过；我只指出一个缺口。")
    elif activity_type in ("code_kata", "writing_block"):
        if store.template_id == "email":
            lines.append("开始：写一封 3–5 句的英文邮件，先写出来，我只按 rubric 判，不代写。")
        else:
            lines.append(f"开始：{activity.get('task')} 先说明输入输出与验收点，再贴代码或报错。")
        lines.append("规则：停住 2 分钟才给 L1 线索；有可复现产物才可能记 verified。")
    elif activity_type == "quiz":
        lines.append(f"开始：3 道题，零提示，围绕「{title}」的边界与常见误解；全对才记 correct。")
        lines.append("规则：索要提示会被拒绝并记 help_level 0；可以要求我澄清题干一次。")
    elif activity_type == "transfer_task":
        lines.append(f"开始：{activity.get('task')} 先写验收标准，再产出可复现结果。")
        lines.append("规则：迁移任务只判不教；L3 需要块产物 + ≥7 天延迟复测，本次不会直接授予。")
    else:
        lines.append(f"开始：{activity.get('task')}")
    lines.append(f"本次预算 {budget} 分钟；剩余不到 2 分钟我会直接收尾，不临时加题。")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# mentor update validation and evidence
# --------------------------------------------------------------------------------------


def validate_direction_update(updates: dict, store: Store) -> tuple[list[str], list[str], list[str]]:
    """Return ``(core_problems, extension_problems, clamp_notes)``."""
    core: list[str] = []
    ext: list[str] = []
    notes: list[str] = []
    if not isinstance(updates, dict):
        return ["机器块必须是 JSON 对象"], [], []
    help_level = updates.get("help_level")
    if not isinstance(help_level, int) or isinstance(help_level, bool) or not 0 <= help_level <= 3:
        core.append(f"help_level 必须是 0–3 的整数，收到 {help_level!r}")
    attempt = updates.get("attempt")
    if not isinstance(attempt, dict):
        core.append("attempt 必须是对象")
    else:
        if not isinstance(attempt.get("activity_id"), str) or not attempt.get("activity_id", "").strip():
            core.append("attempt.activity_id 缺失")
        if not isinstance(attempt.get("correct"), bool):
            core.append("attempt.correct 必须是布尔值")
    if not isinstance(updates.get("next"), str) or not updates.get("next", "").strip():
        core.append("next 缺失或不是字符串")
    mastery = updates.get("mastery_delta", 0)
    if not isinstance(mastery, int) or isinstance(mastery, bool):
        core.append(f"mastery_delta 必须是整数，收到 {mastery!r}")
    elif mastery < 0 or mastery > 1:
        notes.append(f"mastery_delta={mastery} 越界，按上限 +1 处理")
    artifact = updates.get("artifact")
    if artifact is not None and (not isinstance(artifact, str) or len(artifact) > 300):
        ext.append("artifact 必须是不超过 300 字的路径字符串")

    card_updates = updates.get("card")
    if card_updates is not None:
        items = card_updates if isinstance(card_updates, list) else [card_updates]
        if not isinstance(card_updates, (dict, list)):
            ext.append("card 必须是对象或数组")
        elif len(items) > 3:
            ext.append(f"card 单轮最多 3 条，收到 {len(items)} 条")
        else:
            for index, item in enumerate(items):
                ext.extend(validate_card_update(item, store, index))

    signal = updates.get("skill_signal")
    if signal is not None:
        if isinstance(signal, list):
            ext.append("skill_signal 单轮最多 1 条")
        elif not isinstance(signal, dict):
            ext.append("skill_signal 必须是对象")
        else:
            if signal.get("skill") not in store.skill_ids():
                ext.append(f"skill_signal.skill 未知：{signal.get('skill')!r}")
            if not isinstance(signal.get("level_hint"), int) or isinstance(signal.get("level_hint"), bool) or not 0 <= signal.get(
                "level_hint"
            ) <= 3:
                ext.append("skill_signal.level_hint 必须是 0–3 的整数")
            if signal.get("basis") not in ("independent", "hinted", "assisted", "failed", "forgot"):
                ext.append(f"skill_signal.basis 非法：{signal.get('basis')!r}")
    return core, ext, notes


_TAG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_card_update(item: dict, store: Store, index: int = 0) -> list[str]:
    prefix = f"card[{index}]"
    if not isinstance(item, dict):
        return [f"{prefix} 必须是对象"]
    problems = []
    op = item.get("op")
    if op == "create":
        if item.get("skill") not in store.skill_ids():
            problems.append(f"{prefix}.skill 未知：{item.get('skill')!r}")
        if item.get("kind") not in ("recall", "misconception"):
            problems.append(f"{prefix}.kind 必须是 recall 或 misconception")
        for field, limit in (("front", 120), ("back", 200)):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{prefix}.{field} 缺失")
            elif len(value) > limit:
                problems.append(f"{prefix}.{field} 超过 {limit} 字")
        tags = item.get("tags")
        if not isinstance(tags, list) or not 1 <= len(tags) <= 5 or not all(isinstance(t, str) and _TAG_RE.match(t) for t in tags):
            problems.append(f"{prefix}.tags 必须是 1–5 个 kebab-case 标签")
    elif op == "review":
        if not isinstance(item.get("id"), str) or not item.get("id"):
            problems.append(f"{prefix}.id 缺失")
        if item.get("grade") not in GRADES:
            problems.append(f"{prefix}.grade 必须是 {GRADES} 之一")
    else:
        problems.append(f"{prefix}.op 必须是 create 或 review")
    return problems


def looks_like_writing_submission(text: str) -> bool:
    """An email draft in the learner's turn (not the scheduled concept work)."""
    body = text or ""
    greeting = re.search(r"(?im)^\s*(hi|dear|hello)\b", body)
    closing = re.search(r"(?i)(thanks|regards|best regards|sincerely|best,)", body)
    subject = re.search(r"(?im)^\s*subject\s*:", body)
    return bool(subject or (greeting and closing))


def _block_result(attempt: dict, block_correct: bool) -> str:
    raw = str(attempt.get("result") or attempt.get("outcome") or "").strip().lower()
    if raw.startswith("partial") or attempt.get("partial") is True:
        return "partial"
    return "correct" if block_correct else "failed"


def apply_turn(
    store: Store,
    session: dict,
    activity: dict,
    learner_text: str,
    raw: str,
    updates: dict | None,
    update_error: str,
    turn_index: int,
    mode: str,
    *,
    visible: str = "",
    previous_mentor: str = "",
) -> dict:
    """Validate a mentor machine block and apply it according to evidence rules."""
    now = now_iso()
    today = date_of(now)
    sid = session["id"]
    mentor = session["mentor"]
    scheduled_aid = activity["activity_id"]
    out: dict = {
        "invalid": False,
        "problems": [],
        "evidence": None,
        "level_changes": [],
        "cards": [],
        "conflict": False,
        "hint_leak": False,
        "notes": [],
        "signal": None,
        "completed": False,
        "help_level": None,
        "correct": None,
        "next": "",
        "echoed": False,
        "text_conflict": False,
        "attempt_kind": "answer",
        "result": "failed",
        "partial": False,
        "off_activity": False,
        "routed_skill": None,
        "time_boxed": False,
    }
    raw_sha = sha(raw, 32)

    if updates is None:
        store.append(
            "mentor_update_missing",
            {"session": sid, "mentor": mentor, "raw_sha256": raw_sha, "reason": update_error or "导师回复缺少 learn-update 机器块"},
            dedupe_key=f"missing:{sid}:{turn_index}",
        )
        out["invalid"] = True
        out["problems"].append(update_error or "导师回复缺少 learn-update 机器块")
        return out

    core, ext, clamps = validate_direction_update(updates, store)
    if core:
        store.append(
            "mentor_update_invalid",
            {
                "session": sid,
                "mentor": mentor,
                "raw_sha256": raw_sha,
                "problems": core,
                "scope": "core",
                "excerpt": raw[:400],
            },
            dedupe_key=f"invalid:{sid}:{turn_index}",
        )
        out["invalid"] = True
        out["problems"] = core
        return out
    if ext:
        store.append(
            "mentor_update_invalid",
            {"session": sid, "mentor": mentor, "raw_sha256": raw_sha, "problems": ext, "scope": "extension"},
            dedupe_key=f"invalid_ext:{sid}:{turn_index}",
        )
        out["problems"] += ext
    if clamps:
        store.append(
            "mentor_update_clamped",
            {"session": sid, "clamps": clamps, "mastery_delta": updates.get("mastery_delta")},
            dedupe_key=f"clamped:{sid}:{turn_index}",
        )
        out["notes"] += clamps

    help_level = int(updates["help_level"])
    attempt = updates["attempt"]
    block_correct = bool(attempt["correct"])
    correct = block_correct
    reported_aid = str(attempt["activity_id"]).strip()
    next_text = str(updates.get("next") or "").strip()
    mastery = int(updates.get("mastery_delta", 0) or 0)
    mastery = 1 if mastery >= 1 else 0

    # ---- v0.2.2: an answer that repeats the mentor's example is not independent
    echo = echoes_example(learner_text, previous_mentor)
    if echo["echoed"]:
        out["echoed"] = True
        help_level = max(help_level, 2)
    # ---- v0.2.2: a question/request is not an attempt at all
    question_turn = looks_like_question(learner_text)
    if question_turn:
        out["attempt_kind"] = "question"
        out["result"] = "question"
    # ---- v0.2.2: mentor prose vs machine block must not contradict silently
    verdict_in_text = prose_verdict(visible)
    block_result = _block_result(attempt, block_correct)
    learner_partial = learner_partial_signal(learner_text)
    turn_result = "correct" if block_correct else "failed"
    if not question_turn:
        if block_result == "partial":
            turn_result = "partial"
        elif block_correct:
            if verdict_in_text is False:
                turn_result = "conflict"
                out["text_conflict"] = True
        elif verdict_in_text is True:
            turn_result = "conflict"
            out["text_conflict"] = True
        elif learner_partial:
            turn_result = "partial"
    out["result"] = turn_result
    out["partial"] = turn_result == "partial"
    if not question_turn and turn_result in ("partial", "conflict"):
        correct = None
    out.update({"help_level": help_level, "correct": None if question_turn else correct, "next": next_text})

    # ---- mentor may not change the schedule -----------------------------
    conflict_reason = ""
    if reported_aid != scheduled_aid:
        if _activity_alias_matches(reported_aid, activity.get("activity_type")):
            store.append(
                "mentor_activity_alias",
                {
                    "session": sid,
                    "scheduled": scheduled_aid,
                    "reported": reported_aid,
                    "activity_type": activity.get("activity_type"),
                    "action": "treat-as-same-activity",
                },
                dedupe_key=f"alias:{sid}:{turn_index}",
            )
            out["notes"].append(f"导师用了活动别名 {reported_aid}（类型一致），按已调度 {scheduled_aid} 记证据")
        else:
            conflict_reason = f"导师上报活动 {reported_aid} ≠ 已调度 {scheduled_aid}"
    plan_override = _next_tries_to_change_plan(next_text)
    if plan_override:
        conflict_reason = (conflict_reason + "；" if conflict_reason else "") + plan_override
    if conflict_reason:
        store.append(
            "mentor_schedule_conflict",
            {
                "session": sid,
                "scheduled": scheduled_aid,
                "reported": reported_aid,
                "next": next_text,
                "reason": conflict_reason,
                "decision": "keep-schedule",
            },
            dedupe_key=f"conflict:{sid}:{turn_index}",
        )
        out["conflict"] = True
        out["notes"].append(conflict_reason + "；已按调度执行")

    store.append(
        "mentor_suggestion",
        {"session": sid, "activity_id": scheduled_aid, "next": next_text, "accepted": False},
        dedupe_key=f"suggestion:{sid}:{turn_index}",
    )

    # ---- v0.2.2: a pure question/request records no attempt -----------------
    if question_turn:
        answer_sha = sha(learner_text, 12)
        attempt_key = f"attempt:{sid}:{scheduled_aid}:{answer_sha}"
        store.append(
            "turn_without_attempt",
            {
                "session": sid,
                "activity_id": scheduled_aid,
                "skill": activity.get("skill"),
                "block_correct": block_correct,
                "help_level": help_level,
                "reason": "learner asked a question / requested help instead of answering",
            },
            dedupe_key=f"noattempt:{sid}:{turn_index}",
        )
        store.append(
            "attempt",
            {
                "session": sid,
                "mentor": mentor,
                "activity_id": scheduled_aid,
                "reported_activity_id": reported_aid,
                "activity_type": activity.get("activity_type"),
                "skill": activity.get("skill"),
                "correct": None,
                "attempt_kind": "question",
                "result": "question",
                "help_level": help_level,
                "evidence_level": "none",
                "assisted": False,
                "artifact": "",
                "misconception": updates.get("misconception"),
                "mode": mode,
                "answer_sha": answer_sha,
            },
            dedupe_key=attempt_key,
        )
        out["correct"] = None
        out["evidence"] = {"level": "none", "assisted": False, "help_level": help_level, "correct": None, "artifact": ""}
        out["notes"].append("这一轮是提问/求助，没有作答：按“无尝试”记录（不升级、不建卡）。")
        skill = store.skill(activity.get("skill") or "")
        if skill is not None:
            skill["last_help_level"] = help_level
            skill["last_evidence_kind"] = "none"
            store.touch("skills")
        store.schedule["last_turn"] = {
            "activity_id": scheduled_aid,
            "skill": activity.get("skill"),
            "help_level": help_level,
            "correct": None,
            "attempt_kind": "question",
            "result": "question",
            "evidence_kind": "none",
            "assisted": False,
            "echoed": False,
            "text_conflict": out["text_conflict"],
            "at": now,
        }
        store.touch("schedule")
        return out

    # ---- v0.2.2: echo / contradictory prose are logged, block wins ----------
    if out["echoed"]:
        store.append(
            "echoed_example",
            {
                "session": sid,
                "activity_id": scheduled_aid,
                "skill": activity.get("skill"),
                "coverage": echo["coverage"],
                "threshold": echo["threshold"],
                "help_level": help_level,
                "action": "force-help-level>=2-no-independent-credit",
            },
            dedupe_key=f"echo:{sid}:{turn_index}",
        )
        out["notes"].append(
            f"回答与导师刚给的例子重合度 {echo['coverage']:.0%}：按“复述/受助”记录（help_level≥2），不算独立完成。"
        )
    if out["text_conflict"]:
        store.append(
            "mentor_text_conflict",
            {
                "session": sid,
                "activity_id": scheduled_aid,
                "prose_verdict": verdict_in_text,
                "block_correct": block_correct,
                "decision": "no-evidence",
            },
            dedupe_key=f"textconflict:{sid}:{turn_index}",
        )
        out["notes"].append("导师文字与机器块判定不一致：本轮不记对错、不升级、不建卡，等下一轮清晰判定。")
    if out["result"] == "partial":
        store.append(
            "turn_partial",
            {
                "session": sid,
                "activity_id": scheduled_aid,
                "skill": activity.get("skill"),
                "prose_verdict": verdict_in_text,
                "block_correct": block_correct,
                "decision": "partial-no-credit",
            },
            dedupe_key=f"partial:{sid}:{turn_index}",
        )
        out["notes"].append("部分正确：按 partial 记录（不升级、不建卡）；补齐缺的部分后再答一次。")

    # ---- time-box close-out is recorded even for partial/conflict turns
    if not correct and time_boxed_signal(visible):
        planned = int(activity.get("minutes") or 0)
        elapsed = _elapsed_minutes(session.get("started_at"), now)
        explicit_stop = learner_stop_signal(learner_text)
        real_elapsed = planned > 0 and elapsed >= 0.6 * planned
        if real_elapsed or explicit_stop:
            store.append(
                "time_boxed_incomplete",
                {
                    "session": sid,
                    "activity_id": scheduled_aid,
                    "skill": activity.get("skill"),
                    "planned_min": planned,
                    "elapsed_min": elapsed,
                    "reason": "mentor-time-box" if real_elapsed else "learner-stop",
                    "mentor_signal": visible[:120],
                },
                dedupe_key=f"timebox:{sid}:{scheduled_aid}",
            )
            out["time_boxed"] = True
            out["notes"].append(
                f"本轮时间到但活动未完成（计划 {planned} 分钟，实际约 {elapsed:g} 分钟）：已记录 time_boxed_incomplete，下次会先回到它。"
            )
        else:
            store.append(
                "time_box_ignored",
                {
                    "session": sid,
                    "activity_id": scheduled_aid,
                    "planned_min": planned,
                    "elapsed_min": elapsed,
                    "mentor_signal": visible[:120],
                    "reason": "mentor-claimed-time-box-before-60%-elapsed",
                },
                dedupe_key=f"timeboxignored:{sid}:{scheduled_aid}",
            )
            out["notes"].append(
                f"导师说时间到，但实际只过约 {elapsed:g}/{planned} 分钟（<60%）：按未到时间处理，活动保持开放。"
            )

    # ---- partial/conflict: record the outcome, never evidence or cards ------
    if out["result"] in ("partial", "conflict"):
        answer_sha = sha(learner_text, 12)
        attempt_key = f"attempt:{sid}:{scheduled_aid}:{answer_sha}"
        assisted = help_level >= 2 or out["echoed"]
        store.append(
            "attempt",
            {
                "session": sid,
                "mentor": mentor,
                "activity_id": scheduled_aid,
                "reported_activity_id": reported_aid,
                "activity_type": activity.get("activity_type"),
                "skill": activity.get("skill"),
                "correct": None,
                "attempt_kind": out["result"],
                "result": out["result"],
                "help_level": help_level,
                "evidence_level": "none",
                "assisted": assisted,
                "echoed": out["echoed"],
                "text_conflict": out["text_conflict"],
                "time_boxed": out["time_boxed"],
                "artifact": "",
                "misconception": updates.get("misconception"),
                "mode": mode,
                "answer_sha": answer_sha,
            },
            dedupe_key=attempt_key,
        )
        out["correct"] = None
        out["evidence"] = {
            "level": "none",
            "assisted": assisted,
            "help_level": help_level,
            "correct": None,
            "artifact": "",
            "result": out["result"],
        }
        skill = store.skill(activity.get("skill") or "")
        if skill is not None:
            skill["last_help_level"] = help_level
            skill["last_evidence_kind"] = out["result"]
            store.touch("skills")
        store.schedule["last_turn"] = {
            "activity_id": scheduled_aid,
            "skill": activity.get("skill"),
            "help_level": help_level,
            "correct": None,
            "attempt_kind": out["result"],
            "result": out["result"],
            "evidence_kind": out["result"],
            "assisted": assisted,
            "echoed": out["echoed"],
            "text_conflict": out["text_conflict"],
            "time_boxed": out["time_boxed"],
            "at": now,
        }
        store.touch("schedule")
        return out

    # ---- a writing review inside a concept/recall session is writing evidence
    scheduled_type = activity.get("activity_type")
    if scheduled_type in ("concept_block", "explain_back", "recall_card", "quiz") and looks_like_writing_submission(learner_text):
        routed = ""
        for candidate_skill in ("language-accuracy", "structure-clarity"):
            if store.skill(candidate_skill):
                routed = candidate_skill
                break
        routed = routed or (activity.get("skill") or "")
        assisted = help_level >= 2 or out["echoed"]
        answer_sha = sha(learner_text, 12)
        store.append(
            "off_activity_writing_review",
            {
                "session": sid,
                "scheduled_activity": scheduled_aid,
                "scheduled_type": scheduled_type,
                "scheduled_skill": activity.get("skill"),
                "routed_skill": routed,
                "result": turn_result,
                "reason": "writing-draft-in-non-writing-activity",
            },
            dedupe_key=f"writingreview:{sid}:{turn_index}",
        )
        store.append(
            "attempt",
            {
                "session": sid,
                "mentor": mentor,
                "activity_id": scheduled_aid,
                "reported_activity_id": reported_aid,
                "activity_type": "writing_review",
                "skill": routed,
                "correct": correct,
                "attempt_kind": "answer",
                "result": turn_result,
                "help_level": help_level,
                "evidence_level": "observed",
                "assisted": assisted,
                "echoed": out["echoed"],
                "text_conflict": False,
                "time_boxed": False,
                "artifact": "",
                "misconception": updates.get("misconception"),
                "mode": mode,
                "answer_sha": answer_sha,
            },
            dedupe_key=f"attempt:{sid}:{scheduled_aid}:{answer_sha}",
        )
        out["off_activity"] = True
        out["routed_skill"] = routed
        out["correct"] = correct
        out["completed"] = False
        out["evidence"] = {
            "level": "observed",
            "assisted": assisted,
            "help_level": help_level,
            "correct": correct,
            "artifact": "",
            "routed_skill": routed,
        }
        out["notes"].append(
            f"这是写作评审，按写作技能 {routed} 记 observed 证据；不计入当前 {scheduled_type} 活动，也不升级/建卡。"
        )
        skill = store.skill(routed)
        if skill is not None:
            skill["last_review_at"] = now
            skill["last_review_date"] = today
            skill["last_help_level"] = help_level
            skill["last_evidence_kind"] = "writing_review"
            skill["evidence_level"] = _max_evidence(skill.get("evidence_level"), "observed")
            store.touch("skills")
        store.schedule["last_turn"] = {
            "activity_id": scheduled_aid,
            "skill": routed,
            "help_level": help_level,
            "correct": correct,
            "attempt_kind": "answer",
            "result": turn_result,
            "evidence_kind": "writing_review",
            "assisted": assisted,
            "echoed": out["echoed"],
            "text_conflict": False,
            "time_boxed": False,
            "at": now,
        }
        store.touch("schedule")
        return out

    # ---- examiner must not hint ----------------------------------------
    hint_leak = mentor == "examiner" and help_level > 0
    if hint_leak:
        store.append(
            "examiner_hint_leak",
            {"session": sid, "mentor": mentor, "activity_id": scheduled_aid, "help_level": help_level, "action": "downgrade-to-observed"},
            dedupe_key=f"hintleak:{sid}:{turn_index}",
        )
        out["hint_leak"] = True
        out["notes"].append(f"examiner 给了 help_level={help_level} 的提示：已记 examiner_hint_leak，本次证据降为 observed")

    # ---- evidence level -------------------------------------------------
    artifact = str(updates.get("artifact") or "").strip()
    assisted = help_level >= 2 or hint_leak or out["echoed"]
    if out["echoed"]:
        help_level = max(help_level, 2)
        out["help_level"] = help_level
    activity_type = activity.get("activity_type")
    if assisted:
        evidence_level = "observed"
    elif correct and activity_type in ("code_kata", "writing_block", "transfer_task"):
        evidence_level = "verified" if (help_level == 0 and artifact) else "observed"
    elif correct and activity_type == "quiz":
        evidence_level = "verified" if help_level == 0 else "observed"
    elif correct:
        evidence_level = "observed"
    else:
        evidence_level = "observed"
    out["evidence"] = {
        "level": evidence_level,
        "assisted": assisted,
        "help_level": help_level,
        "correct": correct,
        "artifact": artifact,
        "echoed": out["echoed"],
        "text_conflict": out["text_conflict"],
    }

    answer_sha = sha(learner_text, 12)
    # Scoped to this activity instance (session + activity + answer): a replay of the
    # same command is idempotent, while a later session may legitimately review the
    # same card again and count a new lapse.
    attempt_key = f"attempt:{sid}:{scheduled_aid}:{answer_sha}"
    attempt_event = store.append(
        "attempt",
        {
            "session": sid,
            "mentor": mentor,
            "activity_id": scheduled_aid,
            "reported_activity_id": reported_aid,
            "activity_type": activity_type,
            "skill": activity.get("skill"),
            "correct": correct,
            "attempt_kind": "answer",
            "result": turn_result,
            "help_level": help_level,
            "evidence_level": evidence_level,
            "assisted": assisted,
            "echoed": out["echoed"],
            "echo_coverage": echo["coverage"],
            "text_conflict": out["text_conflict"],
            "artifact": artifact,
            "misconception": updates.get("misconception"),
            "mode": mode,
            "answer_sha": answer_sha,
        },
        dedupe_key=attempt_key,
    )
    if attempt_event is None:
        # A replayed answer can still close an artifact-gated activity once the file exists.
        required = str(activity.get("requires_artifact") or "")
        if required and session.get("artifact_pending") and (store.root / required).exists():
            store.append(
                "artifact_acknowledged",
                {"session": sid, "activity_id": scheduled_aid, "skill": activity.get("skill"), "path": required, "via": "replay-file-detected"},
                dedupe_key=f"artifactack:{sid}:{scheduled_aid}:detected",
            )
            _complete_activity(
                store,
                session,
                activity,
                artifact=required,
                evidence_level="observed",
                help_level=help_level,
                now=now,
                out=out,
                attempt_event=None,
                via="artifact",
            )
            out["notes"].append(f"已确认产物：{required}；活动完成。")
        out["notes"].append("本轮尝试已记录（同一活动同一答案不重复计数）")
        return out

    # ---- skill bookkeeping ---------------------------------------------
    skill = store.skill(activity.get("skill") or "")
    if skill is not None:
        skill["last_review_at"] = now
        skill["last_review_date"] = today
        skill["last_help_level"] = help_level
        skill["last_evidence_kind"] = (
            "echo"
            if out["echoed"]
            else "assisted"
            if assisted
            else "independent"
            if correct
            else "failed"
        )
        skill["evidence_level"] = _max_evidence(skill.get("evidence_level"), evidence_level)
        if evidence_level == "verified":
            skill["last_verified_at"] = now
        if correct:
            skill["consecutive_failures"] = 0
        else:
            skill["consecutive_failures"] = int(skill.get("consecutive_failures") or 0) + 1
            misconception = str(updates.get("misconception") or "").strip()
            if misconception:
                wrong = skill.setdefault("wrong_tags", [])
                if misconception[:40] not in wrong:
                    wrong.append(misconception[:40])
                    del wrong[5:]
        store.touch("skills")

    # ---- L3 gate: block artifact + >=7 day delayed retest --------------
    l3_ready = _l3_ready(skill, evidence_level, now) if skill else False
    if l3_ready and int(skill.get("level") or 0) < 3:
        old_level = int(skill.get("level") or 0)
        artifact_at = skill.get("block_artifact_at")
        elapsed = round(days_between(artifact_at, now), 1)
        skill["level"] = 3
        skill["level_reason"] = f"块产物 + {elapsed} 天延迟复测通过（L3 仅此路径）"
        skill["last_level_up_date"] = today
        refs = skill.setdefault("evidence_refs", [])
        refs.append({"event": (attempt_event or {}).get("id"), "kind": "l3_granted", "at": now, "artifact": skill.get("block_artifact_path", "")})
        store.append(
            "l3_granted",
            {
                "skill": skill["id"],
                "artifact": skill.get("block_artifact_path"),
                "artifact_at": artifact_at,
                "retest_at": now,
                "days": elapsed,
                "activity_id": scheduled_aid,
                "evidence_level": evidence_level,
            },
            dedupe_key=f"l3:{skill['id']}:{today}",
        )
        out["level_changes"].append(
            {"skill": skill["id"], "from": old_level, "to": 3, "reason": "块产物 + ≥7 天延迟复测", "event": (attempt_event or {}).get("id")}
        )
        out["notes"].append(f"{skill['id']} 满足块产物 + {elapsed} 天延迟复测，授予 L3（纯卡练习永远到不了这里）")

    # ---- +1 level (evidence constrained; the mentor never decides) ------
    upgrade_allowed = correct and help_level <= 1 and not hint_leak
    if skill is not None and upgrade_allowed and int(skill.get("level") or 0) < 3:
        last_up = skill.get("last_level_up_date")
        if last_up == today:
            out["notes"].append(f"{skill['id']} 今天已升过一级（同一技能每天最多 +1）")
        else:
            cap = 2  # pure practice caps at L2; L3 only through the gate above
            old = int(skill.get("level") or 0)
            new_level = min(old + 1, cap)
            if new_level > old:
                skill["level"] = new_level
                skill["level_reason"] = (
                    f"{activity_type} 独立完成（help_level={help_level}, evidence={evidence_level}）；"
                    + ("纯卡练习封顶 L2" if cap == 2 else "")
                )
                skill["last_level_up_date"] = today
                skill.setdefault("evidence_refs", []).append(
                    {"event": (attempt_event or {}).get("id"), "kind": "level_up", "at": now, "activity": scheduled_aid}
                )
                if len(skill["evidence_refs"]) > 20:
                    del skill["evidence_refs"][:-20]
                store.append(
                    "level_change",
                    {
                        "skill": skill["id"],
                        "from": old,
                        "to": new_level,
                        "reason": "independent-correct",
                        "help_level": help_level,
                        "evidence_level": evidence_level,
                        "activity_id": scheduled_aid,
                        "mastery_delta": int(updates.get("mastery_delta", 1) or 0),
                    },
                    dedupe_key=f"level:{attempt_key}",
                )
                out["level_changes"].append({"skill": skill["id"], "from": old, "to": new_level, "reason": "独立完成 +1"})
                out["notes"].append(f"{skill['id']} L{old}→L{new_level}（正确 + help_level≤1；每天最多 +1）")
                store.touch("skills")
            else:
                out["notes"].append(f"{skill['id']} 已在当前证据允许的上限 L{old}；L3 需块产物 + ≥7 天延迟复测")

    # ---- card updates ---------------------------------------------------
    card_updates = updates.get("card")
    items = [] if not card_updates else (card_updates if isinstance(card_updates, list) else [card_updates])
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        if validate_card_update(item, store):
            continue
        if item.get("op") == "create":
            _apply_card_create(store, item, activity, attempt_key, now, out)
        else:
            _apply_card_review(store, item, attempt_key, now, out, activity, assisted=assisted)

    # ---- signal extension (suggestion only) ----------------------------
    signal = updates.get("skill_signal")
    if isinstance(signal, dict):
        store.append(
            "skill_signal",
            {
                "skill": signal.get("skill"),
                "level_hint": signal.get("level_hint"),
                "basis": signal.get("basis"),
                "help_level": help_level,
                "accepted": False,
                "note": "运行时不接受导师直接定级，等级只按证据计算",
            },
            dedupe_key=f"signal:{attempt_key}",
        )
        out["signal"] = signal
        if int(signal.get("level_hint") or 0) > int((skill or {}).get("level") or 0):
            out["notes"].append("导师 skill_signal 高于当前等级：只记录，不采纳（等级由证据决定）")

    # ---- consecutive failures -> level -1 + misconception card ---------
    if skill is not None and not correct and int(skill.get("consecutive_failures") or 0) >= 2:
        if int(skill.get("level") or 0) > 0 and not out["level_changes"]:
            old = int(skill["level"])
            skill["level"] = old - 1
            skill["level_reason"] = f"连续 2 次失败，按规则降 1 级（{old}→{old - 1}）"
            skill["consecutive_failures"] = 0
            store.append(
                "decayed",
                {"skill": skill["id"], "reason": "consecutive_errors", "from": old, "to": old - 1},
                dedupe_key=f"decay2:{skill['id']}:{today}",
            )
            out["level_changes"].append({"skill": skill["id"], "from": old, "to": old - 1, "reason": "连续 2 次失败"})
            out["notes"].append(f"{skill['id']} 连续 2 次失败：降 1 级（原因已记录）")
            store.touch("skills")
        misconception = str(updates.get("misconception") or "").strip()
        if misconception:
            _auto_misconception_card(store, skill, misconception, activity, attempt_key, now, out)

    # ---- activity completion (artifact-gated when declared) ------------
    required_artifact = str(activity.get("requires_artifact") or "").strip()
    submitted = str(updates.get("artifact") or "").strip()
    accepted_artifact = ""
    if required_artifact:
        for candidate_path in (submitted, required_artifact):
            if candidate_path and (store.root / candidate_path).exists():
                accepted_artifact = candidate_path
                break
        if correct and not accepted_artifact:
            store.append(
                "artifact_required",
                {
                    "session": sid,
                    "activity_id": scheduled_aid,
                    "skill": activity.get("skill"),
                    "path": required_artifact,
                    "declared": submitted or None,
                    "reason": "活动声明了完成产物，但文件还不存在",
                },
                dedupe_key=f"artifactreq:{sid}:{scheduled_aid}",
            )
            session["artifact_pending"] = required_artifact
            store.touch("schedule")
            out["artifact_required"] = required_artifact
            out["completed"] = False
            out["notes"].append(
                f"完成标准还差产物：{required_artifact}（文件还没落盘）。写好后再 say 一次，或直接 pause/start，我会确认完成。"
            )
    else:
        accepted_artifact = submitted

    if accepted_artifact != artifact:
        out["evidence"] = dict(out.get("evidence") or {})
        out["evidence"]["artifact"] = accepted_artifact

    if correct and not out.get("artifact_required"):
        if required_artifact and accepted_artifact:
            store.append(
                "artifact_acknowledged",
                {
                    "session": sid,
                    "activity_id": scheduled_aid,
                    "skill": activity.get("skill"),
                    "path": accepted_artifact,
                    "via": "turn",
                },
                dedupe_key=f"artifactack:{sid}:{scheduled_aid}",
            )
        _complete_activity(
            store,
            session,
            activity,
            artifact=accepted_artifact,
            evidence_level=evidence_level,
            help_level=help_level,
            now=now,
            out=out,
            attempt_event=attempt_event,
            via="turn",
        )

    if skill is not None:
        store.touch("skills")
    if out["cards"]:
        store.touch("cards")
    store.schedule["last_turn"] = {
        "activity_id": scheduled_aid,
        "skill": activity.get("skill"),
        "help_level": help_level,
        "correct": correct,
        "attempt_kind": "answer",
        "result": turn_result,
        "evidence_kind": (
            "echo" if out["echoed"] else "assisted" if assisted else "independent" if correct else "failed"
        ),
        "assisted": assisted,
        "echoed": out["echoed"],
        "text_conflict": out["text_conflict"],
        "time_boxed": out["time_boxed"],
        "at": now,
    }
    store.touch("schedule")
    return out


def _max_evidence(current: str | None, new: str) -> str:
    order = {"self_report": 0, "observed": 1, "verified": 2}
    return new if order.get(new, 0) > order.get(current or "self_report", 0) else (current or "self_report")


# --------------------------------------------------------------------------------------
# turn text analysis: echo / question / verdict / time-box (design v0.2.2)
# --------------------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[\s，。！？、,.!?;；:：\"'“”‘’()（）\[\]【】<>《》·…—\-_/\\|]+")
#: generic bigrams that should not count as "echoing" on their own
_CJK_STOP_BIGRAMS = {
    "就是", "这个", "那个", "可以", "什么", "怎么", "我们", "你们", "一个", "不是", "如果",
    "因为", "所以", "然后", "现在", "这样", "那样", "需要", "应该", "已经", "一定", "其实",
    "知道", "理解", "答案", "问题", "方法", "步骤", "例子", "时候", "东西", "还是", "或者",
    "但是", "而且", "没有", "只有", "自己", "一下", "一些", "有点", "比较", "非常", "真的",
}


def normalize_text(text: str) -> str:
    return _PUNCT_RE.sub("", (text or "").lower())


def text_bigrams(text: str) -> set[str]:
    normalized = normalize_text(text)
    return {normalized[index : index + 2] for index in range(max(0, len(normalized) - 1))}


def echo_coverage(learner_text: str, mentor_text: str) -> tuple[float, int, int]:
    """Fraction of the learner's content bigrams that already appear in the mentor text."""
    learner = text_bigrams(learner_text) - _CJK_STOP_BIGRAMS
    mentor = text_bigrams(mentor_text) - _CJK_STOP_BIGRAMS
    if len(learner) < 6:
        return 0.0, len(learner), len(mentor)
    return len(learner & mentor) / len(learner), len(learner), len(mentor)


def echoes_example(learner_text: str, mentor_text: str, *, threshold: float = 0.72) -> dict:
    """True when the learner's answer closely repeats the mentor's preceding example."""
    if len(normalize_text(learner_text)) < 12 or len(normalize_text(mentor_text or "")) < 12:
        return {"echoed": False, "coverage": 0.0, "threshold": threshold}
    coverage, learner_size, mentor_size = echo_coverage(learner_text, mentor_text)
    echoed = learner_size >= 6 and mentor_size >= 6 and coverage >= threshold
    return {
        "echoed": echoed,
        "coverage": round(coverage, 4),
        "threshold": threshold,
        "learner_bigrams": learner_size,
        "mentor_bigrams": mentor_size,
    }


_QUESTION_RE = re.compile(r"[?？]")
#: declarations that contain a request-looking phrase must stay answers
_ANSWER_CONTENT_RE = re.compile(r"(我只记得|我的理解|大概是|应该是|因为|所以|停止条件|四个阶段|定义|是指|就是|先做|再看|最后)")
_REQUEST_START_RE = re.compile(r"^(那|请|麻烦|你|能不能|可以|帮我|给我|直接给我|告诉我|别绕了)")


def looks_like_question(text: str) -> bool:
    """A *pure* request/question is not an attempt.

    A substantive answer can contain request-looking words ("直接给最终答案")
    or a rhetorical question mark; classifying those as questions silently
    erased real evidence. Only short, content-free asks count.
    """
    stripped = (text or "").strip()
    normalized = normalize_text(stripped)
    if not normalized:
        return False
    if len(normalized) > 36:
        return False
    if stripped.endswith(("吗", "呢")) and len(normalized) <= 24:
        return True
    if _QUESTION_RE.search(stripped) and len(normalized) <= 28 and not _ANSWER_CONTENT_RE.search(stripped):
        return True
    if _REQUEST_START_RE.match(stripped) and len(normalized) <= 24:
        return True
    return False


_POS_VERDICT_RE = re.compile(r"(?:^|[。！!？?\n])\s*(对|正确|答对|没错|是的|完全正确|基本正确)(?:[。，,.！!\s]|$)")
_NEG_VERDICT_RE = re.compile(r"(不对|答错|未判对|没答对|不准确|理解错|说错|不完整|漏了|漏掉|缺了)")


def prose_verdict(text: str) -> bool | None:
    """Best-effort read of the mentor's visible verdict (None when ambiguous).

    Only an explicit update field or the learner's own self-assessment can
    produce ``partial``; the word "部分" in mentor prose must not downgrade a
    correct answer.
    """
    body = text or ""
    positive = bool(_POS_VERDICT_RE.search(body))
    negative = bool(_NEG_VERDICT_RE.search(body))
    if positive and not negative:
        return True
    if negative and not positive:
        return False
    return None


_PARTIAL_SELF_RE = re.compile(r"(我只记得|只答出|只写出?了?|没答全|没写完|只完成一半|只做了一半|不太确定|只记得)")


def learner_partial_signal(text: str) -> bool:
    """Partial is allowed only when the learner explicitly says it is incomplete."""
    return bool(_PARTIAL_SELF_RE.search(text or ""))



_TIME_BOX_MARKERS = ("时间到", "时间到了", "到时间了", "时间用完", "时间不够", "本次到此为止", "到此收尾")
_LEARNER_STOP_MARKERS = ("我不练了", "先到这里", "我要走了", "没有时间了", "时间不够了", "先停", "结束吧", "收尾吧")


def time_boxed_signal(text: str) -> bool:
    body = text or ""
    return any(marker in body for marker in _TIME_BOX_MARKERS)


def learner_stop_signal(text: str) -> bool:
    body = text or ""
    return any(marker in body for marker in _LEARNER_STOP_MARKERS)


def _elapsed_minutes(started_at: str | None, now: str) -> float:
    if not started_at:
        return 0.0
    try:
        return round(max(0.0, clock.days_between(started_at, now) * 24 * 60), 1)
    except (ValueError, TypeError):
        return 0.0


def _next_tries_to_change_plan(next_text: str) -> str:
    """Mentor ``next`` may only suggest. Phrases that try to re-plan are conflicts."""
    if not next_text:
        return ""
    for phrase in ("直接学", "改成学", "换成", "先学别的", "加课", "另开一课", "跳过调度"):
        if phrase in next_text:
            return f"导师 next 试图改计划（{next_text[:40]}），调度器不采纳"
    return ""


_ACTIVITY_KEYWORDS = {
    "recall_card": ("recall",),
    "concept_block": ("concept",),
    "explain_back": ("explain",),
    "code_kata": ("kata", "code"),
    "writing_block": ("writing", "写作", "email-block", "draft"),
    "quiz": ("quiz",),
    "transfer_task": ("project-slice", "transfer", "slice"),
}


def _activity_alias_matches(reported: str, scheduled_type: str | None) -> bool:
    """A mentor may name an activity loosely (``recall-due-2cards``) but not swap its type."""
    if not reported or not scheduled_type:
        return False
    text = reported.lower()
    if scheduled_type == "writing_block" and text in ("kata", "writing", "writing_block", "writing-block"):
        return True
    keywords = _ACTIVITY_KEYWORDS.get(scheduled_type, ())
    if not any(keyword in text for keyword in keywords):
        return False
    for other_type, other_keywords in _ACTIVITY_KEYWORDS.items():
        if other_type == scheduled_type:
            continue
        if any(keyword in text for keyword in other_keywords):
            return False
    return True


def _l3_ready(skill: dict | None, evidence_level: str, now: str) -> bool:
    if not skill or evidence_level != "verified":
        return False
    artifact_at = skill.get("block_artifact_at")
    if not artifact_at:
        return False
    return days_between(artifact_at, now) >= 7.0 - 1e-9


def _find_card_by_front(store: Store, skill_id: str, front: str) -> dict | None:
    key = normalize_text(front)
    for card in store.cards.get("cards", []):
        if card.get("skill") == skill_id and normalize_text(card.get("front")) == key:
            return card
    return None


def _merge_card(
    store: Store,
    card: dict,
    attempt_key: str,
    *,
    back: str = "",
    tags: list[str] | None = None,
    source: str = "",
    out: dict,
) -> None:
    """Merge a duplicate (same skill + normalized front) instead of creating another card."""
    merge_key = f"card:merge:{card['id']}:{attempt_key}"
    if store.journal.has(merge_key):
        out["cards"].append({"op": "create", "id": card["id"], "merged": True, "duplicate": True})
        out["notes"].append(f"同题卡片已存在：{card['id']}（本轮已合并过，重复条目忽略）")
        return
    changed = False
    new_back = (back or "").strip()
    if new_back and new_back != card.get("back"):
        if not card.get("back"):
            card["back"] = new_back[:200]
            changed = True
        elif new_back not in card.get("back", ""):
            card["back"] = (card.get("back", "") + "；另一次：" + new_back)[:200]
            changed = True
    merged_tags = list(card.get("tags") or [])
    for tag in tags or []:
        if tag not in merged_tags and len(merged_tags) < 5:
            merged_tags.append(tag)
            changed = True
    card["tags"] = merged_tags
    card["merge_count"] = int(card.get("merge_count", 0)) + 1
    store.touch("cards")
    store.append(
        "card_merged",
        {
            "card": card["id"],
            "skill": card.get("skill"),
            "front": card.get("front"),
            "source": source,
            "attempt": attempt_key,
            "changed": changed,
            "merge_count": card["merge_count"],
        },
        dedupe_key=merge_key,
    )
    out["cards"].append({"op": "create", "id": card["id"], "merged": True})
    out["notes"].append(f"同题卡片已存在：{card['id']}（同 skill+front 合并，不重复建卡）")


def _apply_card_create(store: Store, item: dict, activity: dict, attempt_key: str, now: str, out: dict) -> None:
    skill_id = item["skill"]
    front = item["front"].strip()
    existing = _find_card_by_front(store, skill_id, front)
    if existing is not None:
        _merge_card(
            store,
            existing,
            attempt_key,
            back=item.get("back", ""),
            tags=list(item.get("tags") or []),
            source="mentor-card",
            out=out,
        )
        return
    card_id = f"card-{sha(skill_id + '|' + front, 6)}"
    if store.card(card_id):
        out["notes"].append(f"卡片已存在：{card_id}")
        return
    card = {
        "id": card_id,
        "skill": skill_id,
        "kind": item["kind"],
        "front": front,
        "back": item["back"].strip(),
        "tags": list(item["tags"]),
        "source_event": attempt_key,
        "step": 0,
        "interval_days": 1,
        "ease": 1.0,
        "due_at": now,
        "last_review_at": None,
        "lapses": 0,
        "consecutive_lapses": 0,
        "leech": False,
        "needs_rewrite": False,
        "created_at": now,
    }
    cap = weekly_card_cap(store.meta.get("minutes_per_week", 600))
    used = len(cards_created_this_week(store.cards.get("cards", []), now))
    if used >= cap:
        store.append(
            "card_queued",
            {"card": card, "cap": cap, "used": used, "reason": f"本周卡量已达上限 {cap} 张，新卡排队"},
            dedupe_key=f"queue:{card_id}:{week_key(now)}",
        )
        out["cards"].append({"op": "create", "id": card_id, "queued": True, "cap": cap})
        out["notes"].append(f"本周卡量上限 {cap} 张已满：card {card_id} 排队，下周自动补建")
        return
    store.cards.setdefault("cards", []).append(card)
    store.append(
        "card_created",
        {"card": card_id, "skill": skill_id, "kind": card["kind"], "front": card["front"], "source": attempt_key},
        dedupe_key=f"card:create:{card_id}",
    )
    out["cards"].append({"op": "create", "id": card_id, "queued": False})
    out["notes"].append(f"新卡已建：{card_id}（{skill_id}，下次到期今天）")


def _apply_card_review(
    store: Store,
    item: dict,
    attempt_key: str,
    now: str,
    out: dict,
    activity: dict,
    *,
    assisted: bool = False,
) -> None:
    card = store.card(item.get("id") or "")
    if card is None:
        store.append(
            "card_update_invalid",
            {"op": "review", "id": item.get("id"), "reason": "card id 不存在，已忽略"},
            dedupe_key=f"cardmiss:{item.get('id')}:{attempt_key}",
        )
        out["problems"].append(f"导师 review 了不存在的卡：{item.get('id')}")
        return
    # Grade *before* the event would be appended, so a duplicate review item in the
    # same turn (or a replayed turn that slipped past the attempt guard) must be
    # filtered here -- otherwise step/ease advance twice while only one event lands.
    review_key = f"card:review:{card['id']}:{attempt_key}"
    if store.journal.has(review_key):
        out["cards"].append({"op": "review", "id": card["id"], "duplicate": True})
        out["notes"].append(f"{card['id']} 本轮已记过一次复习：重复条目已忽略（step 不重复前进）")
        return
    mismatches = []
    for field in ("skill", "kind", "front", "back", "tags"):
        if field in item and item[field] not in (None, "") and item[field] != card.get(field):
            mismatches.append(field)
    if mismatches:
        store.append(
            "card_echo_mismatch",
            {"card": card["id"], "fields": mismatches, "action": "apply-by-id-using-stored-card"},
            dedupe_key=f"cardecho:{card['id']}:{attempt_key}",
        )
        out["notes"].append(f"导师回填的 {card['id']} 字段与库中不一致（{','.join(mismatches)}），按库中卡片判级")
    if item.get("grade") not in GRADES:
        out["problems"].append(f"非法 grade：{item.get('grade')!r}")
        return
    requested_grade = item["grade"]
    grade = requested_grade
    if assisted and grade in ("good", "easy"):
        # an assisted/echoed success must not advance the interval like a good recall
        grade = "hard"
    changes = grade_card(card, grade, now)
    if item.get("front") and item.get("front") != card.get("front") and card.get("needs_rewrite"):
        card["front"] = item["front"][:120]
        card["needs_rewrite"] = False
        out["notes"].append(f"{card['id']} 已按导师回填改写正反面，解除 leech 改写要求")
    store.append(
        "card_reviewed",
        {
            "card": card["id"],
            "skill": card.get("skill"),
            "grade": changes["grade"],
            "requested_grade": requested_grade,
            "assisted": assisted,
            "step": changes["step"],
            "ease": changes["ease"],
            "interval_days": changes["interval_days"],
            "due_at": changes["due_at"],
            "lapses": changes["lapses"],
            "leech": changes["leech"],
            "activity_id": activity.get("activity_id"),
        },
        dedupe_key=review_key,
    )
    out["cards"].append({"op": "review", "id": card["id"], **changes})
    out["notes"].append(
        f"{card['id']} 记 {changes['grade']}：step {changes['step_before']}→{changes['step']}，"
        f"间隔 {changes['interval_days']} 天（{date_of(changes['due_at'])} 到期）"
    )
    if changes.get("new_leech"):
        skill = store.skill(card.get("skill") or "")
        out["notes"].append(f"{card['id']} 连续 2 次 lapse，标记 leech 并进入改写；只在 ≥10 分钟预算出现")
        if skill is not None and int(skill.get("level") or 0) > 0:
            old = int(skill["level"])
            skill["level"] = old - 1
            skill["level_reason"] = f"leech 卡（连续 2 次 lapse），按规则降 1 级（{old}→{old - 1}）"
            store.append(
                "level_change",
                {"skill": skill["id"], "from": old, "to": old - 1, "reason": "leech", "card": card["id"]},
                dedupe_key=f"leech:{skill['id']}:{date_of(now)}",
            )
            out["level_changes"].append({"skill": skill["id"], "from": old, "to": old - 1, "reason": "leech"})
            out["notes"].append(f"{skill['id']} 因 leech 降 1 级（{old}→{old - 1}）")
            store.touch("skills")


def _auto_misconception_card(store: Store, skill: dict, misconception: str, activity: dict, attempt_key: str, now: str, out: dict) -> None:
    front = f"你上次把「{skill.get('title', skill['id'])}」误解成什么？"
    existing = _find_card_by_front(store, skill["id"], front)
    if existing is not None:
        existing["needs_rewrite"] = True
        _merge_card(
            store,
            existing,
            attempt_key,
            back=f"误解：{misconception[:160]}。回到 {activity.get('activity_id')} 的记录，重述正确做法后再复测。",
            tags=["misconception", "auto"],
            source="auto-misconception",
            out=out,
        )
        return
    card_id = f"card-{sha(skill['id'] + '|' + misconception, 6)}"
    if store.card(card_id):
        return
    card = {
        "id": card_id,
        "skill": skill["id"],
        "kind": "misconception",
        "front": front,
        "back": f"误解：{misconception[:160]}。回到 {activity.get('activity_id')} 的记录，重述正确做法后再复测。",
        "tags": ["misconception", "auto"],
        "source_event": attempt_key,
        "step": 0,
        "interval_days": 1,
        "ease": 1.0,
        "due_at": now,
        "last_review_at": None,
        "lapses": 0,
        "consecutive_lapses": 0,
        "leech": False,
        "needs_rewrite": True,
        "created_at": now,
    }
    cap = weekly_card_cap(store.meta.get("minutes_per_week", 600))
    if len(cards_created_this_week(store.cards.get("cards", []), now)) >= cap:
        store.append(
            "card_queued",
            {"card": card, "cap": cap, "reason": "连续 2 次失败自动生成的误解卡排队"},
            dedupe_key=f"queue:{card_id}:{week_key(now)}",
        )
        out["notes"].append(f"误解卡排队（本周卡量已满 {cap} 张）：{card_id}")
        return
    store.cards.setdefault("cards", []).append(card)
    store.append(
        "card_created",
        {"card": card_id, "skill": skill["id"], "kind": "misconception", "front": front, "auto": True},
        dedupe_key=f"card:create:{card_id}",
    )
    out["cards"].append({"op": "create", "id": card_id, "auto": True})
    out["notes"].append(f"连续 2 次失败：自动生成误解卡 {card_id}（正反面需改写）")


def _mark_item_done(store: Store, activity_id: str) -> None:
    for item in store.schedule.get("today", {}).get("items", []):
        if item.get("activity_id") == activity_id:
            item["done"] = True
    store.touch("schedule")


def _complete_activity(
    store: Store,
    session: dict,
    activity: dict,
    *,
    artifact: str,
    evidence_level: str,
    help_level: int,
    now: str,
    out: dict,
    attempt_event: dict | None,
    via: str = "turn",
) -> bool:
    """Record completion exactly once (idempotent) and update the item/block state."""
    sid = str(session.get("id") or "")
    aid = str(activity.get("activity_id") or "")
    event = store.append(
        "activity_completed",
        {
            "session": sid,
            "activity_id": aid,
            "activity_type": activity.get("activity_type"),
            "skill": activity.get("skill"),
            "correct": True,
            "help_level": help_level,
            "evidence_level": evidence_level,
            "duration_min": int(activity.get("minutes") or 0),
            "artifact": artifact,
            "via": via,
        },
        dedupe_key=f"activity:{sid}:{aid}:completed",
    )
    if event is None:
        out["completed"] = True
        session["artifact_pending"] = ""
        return False
    out["completed"] = True
    _mark_item_done(store, aid)
    schedule = store.schedule
    schedule["last_activity"] = {
        "id": aid,
        "activity_type": activity.get("activity_type"),
        "skill": activity.get("skill"),
        "at": now,
        "session": sid,
    }
    session["artifact_pending"] = ""
    store.touch("schedule")
    if activity.get("block_id"):
        _complete_block_step(store, activity, artifact, attempt_event, now, out)
        if artifact:
            _record_block_artifact(store, activity, artifact, attempt_event, now, out)
    return True


def acknowledge_pending_artifact(store: Store, now: str | None = None) -> list[str]:
    """If a completed attempt is waiting only for its declared artifact, accept the file."""
    now = now or now_iso()
    session = store.schedule.get("current_session")
    if not session:
        return []
    activity = session.get("activity") or {}
    required = str(session.get("artifact_pending") or "").strip()
    if not required or not (store.root / required).exists():
        return []
    sid = str(session.get("id") or "")
    aid = str(activity.get("activity_id") or "")
    store.append(
        "artifact_acknowledged",
        {"session": sid, "activity_id": aid, "skill": activity.get("skill"), "path": required, "via": "file-detected"},
        dedupe_key=f"artifactack:{sid}:{aid}:detected",
    )
    out: dict = {"cards": [], "notes": [], "level_changes": [], "completed": False}
    _complete_activity(
        store,
        session,
        activity,
        artifact=required,
        evidence_level="observed",
        help_level=0,
        now=now,
        out=out,
        attempt_event=None,
        via="artifact",
    )
    store.touch("schedule")
    return [f"已确认产物：{required}；活动完成。"] + list(out.get("notes") or [])


def _record_block_artifact(store: Store, activity: dict, artifact: str, attempt_event: dict | None, now: str, out: dict) -> None:
    block = store.block(activity.get("block_id"))
    if block is None:
        return
    if not (store.root / artifact).exists():
        store.append(
            "artifact_missing_file",
            {
                "skill": activity.get("skill"),
                "activity_id": activity.get("activity_id"),
                "artifact": artifact,
                "block_id": activity.get("block_id"),
                "reason": "导师或运行时声明了产物路径，但文件不存在；不计 L3 依据",
            },
            dedupe_key=f"artifactmiss:{activity.get('activity_id')}:{artifact}",
        )
        out["notes"].append(f"产物路径 {artifact} 尚未落盘，只记路径、不计 L3 依据。")
        return
    step_index = activity.get("step_index")
    if isinstance(step_index, int) and 0 <= step_index < len(block.get("steps", [])):
        step = block["steps"][step_index]
        step["artifact"] = artifact
        if not step.get("evidence_ref") and attempt_event:
            step["evidence_ref"] = attempt_event.get("id", "")
        block["artifact_path"] = block.get("artifact_path") or artifact
        store.touch("blocks")
    skill = store.skill(activity.get("skill") or "")
    if skill is None:
        return
    if skill.get("block_artifact_at") and skill.get("block_artifact_path") == artifact:
        return
    skill["block_artifact_at"] = now
    skill["block_artifact_path"] = artifact
    skill["delayed_retest_due_at"] = clock.add_days(now, 7)
    skill["block_id"] = activity.get("block_id")
    store.touch("skills")
    store.append(
        "block_artifact",
        {
            "skill": skill["id"],
            "artifact": artifact,
            "block_id": activity.get("block_id"),
            "activity_id": activity.get("activity_id"),
            "delayed_retest_due_at": skill["delayed_retest_due_at"],
            "note": "L3 需要此产物 + ≥7 天后的独立复测通过",
        },
        dedupe_key=f"artifact:{skill['id']}:{artifact}",
    )
    out["notes"].append(f"块产物已记：{artifact}；{date_of(skill['delayed_retest_due_at'])} 起可做延迟复测（L3 前提）")


def _complete_block_step(store: Store, activity: dict, artifact: str, attempt_event: dict | None, now: str, out: dict) -> None:
    block = store.block(activity.get("block_id"))
    if block is None:
        return
    step_index = activity.get("step_index")
    if not isinstance(step_index, int) or not 0 <= step_index < len(block.get("steps", [])):
        return
    step = block["steps"][step_index]
    step["done"] = True
    if attempt_event and not step.get("evidence_ref"):
        step["evidence_ref"] = attempt_event.get("id", "")
    store.touch("blocks")
    store.append(
        "block_step_done",
        {
            "block": block["id"],
            "step": step_index,
            "skill": step.get("skill"),
            "artifact": artifact,
            "evidence_ref": step.get("evidence_ref"),
            "note": "" if artifact else "无产物：只记步骤完成，不构成 L3 前提",
        },
        dedupe_key=f"blockstep:{block['id']}:{step_index}",
    )
    out["notes"].append(f"本周块第 {step_index + 1} 步完成" + ("（有产物）" if artifact else "（无产物，不计 L3 依据）"))


# --------------------------------------------------------------------------------------
# export / status / doctor
# --------------------------------------------------------------------------------------


def build_export(store: Store) -> str:
    from learncore import CORE_VERSION

    now = now_iso()
    meta = store.meta
    schedule = store.schedule
    lines = [
        f"# LearnArk · Tempo 学习档案 — {meta.get('goal', '')}",
        "",
        f"- 方向/版本：{VARIANT_ID} {VARIANT_VERSION} / core {CORE_VERSION} / schema {meta.get('schema_version')}",
        f"- 项目：{meta.get('slug')} · 模板 {meta.get('template_id')} · 建立 {meta.get('created_at')}",
        f"- 学习者：{meta.get('learner', {}).get('name')}（{meta.get('learner', {}).get('note')}）",
        f"- 导师：{', '.join(store.mentor_ids())}；当前 {meta.get('mentor')}",
        f"- 导出时间：{now}（{'模拟时间，仅证明调度逻辑' if clock.is_simulated() else '真实时间'}）",
        "",
        "## 能力与到期（技能平表，无先修关系）",
        "",
        "| 技能 | 等级 | 证据级别 | 上次帮助 | 上次证据类型 | 到期 | 逾期 | lapses | 错误标签 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for skill in store.skills.get("skills", []):
        lines.append(
            f"| {skill['id']} | L{skill.get('level', 0)} | {skill.get('evidence_level', '-')} | "
            f"{skill.get('last_help_level', '-')} | {skill.get('last_evidence_kind', '-')} | "
            f"{date_of(skill.get('due_at')) or '-'} | {overdue_days(skill.get('due_at'))} | "
            f"{skill.get('lapses', 0)} | {'、'.join(skill.get('wrong_tags') or []) or '-'} |"
        )
    lines += ["", "## 记忆卡", ""]
    for card in store.cards.get("cards", []):
        lines.append(
            f"- `{card['id']}` [{card.get('skill')}/{card.get('kind')}] step {card.get('step')} "
            f"· 到期 {date_of(card.get('due_at'))} · lapses {card.get('lapses', 0)}"
            + (" · **leech（需改写）**" if card.get("leech") else "")
        )
        lines.append(f"  - 正面：{card.get('front')}")
        lines.append(f"  - 背面：{card.get('back')}")
    lines += ["", "## 本周项目块", ""]
    for block in store.blocks.get("blocks", []):
        done = sum(1 for step in block.get("steps", []) if step.get("done"))
        lines.append(f"### {block.get('id')}（{block.get('week')}）{block.get('goal')}")
        lines.append(f"- 产物：{block.get('artifact_path') or block.get('deliverable') or '-'}")
        for index, step in enumerate(block.get("steps", []), 1):
            lines.append(
                f"- 第 {index} 步 {step.get('skill')} · {step.get('activity_type')} · {step.get('minutes')} 分钟"
                f" · {'已完成' if step.get('done') else '未完成'}"
                + (f" · 产物 {step.get('artifact')}" if step.get("artifact") else "")
            )
        lines.append(f"- 进度：{done}/{len(block.get('steps', []))}")
        lines.append("")
    lines += ["## 会话记录", ""]
    sessions = sorted((store.root / "sessions").glob("*.md"))
    for path in sessions:
        lines.append(f"- `{path.name}`（{path.stat().st_size} 字节）")
    if not sessions:
        lines.append("- 暂无")
    lines += ["", "## 最近事件（journal 权威记录，最近 30 条）", ""]
    for event in store.events()[-30:]:
        payload = event.get("payload") or {}
        summary_bits = []
        for key in ("skill", "activity_id", "help_level", "correct", "evidence_level", "reason", "next", "card"):
            if key in payload and payload[key] not in (None, "", []):
                value = str(payload[key])
                summary_bits.append(f"{key}={value[:60]}")
        lines.append(
            f"- {event.get('at')} `{event.get('kind')}`"
            + (" (simulated)" if event.get("simulated") else "")
            + (" — " + "; ".join(summary_bits) if summary_bits else "")
        )
    handoff = store.root / ".learnark" / "handoff" / "latest.md"
    if handoff.exists():
        lines += ["", "## 最近交接", "", handoff.read_text(encoding="utf-8").strip()]
    lines += [
        "",
        "## 说明",
        "",
        "- 等级只由运行时按证据提升；纯卡练习最高 L2，L3 需要块产物 + ≥7 天延迟复测。",
        "- 本档案不含 API 密钥；离线/模拟记录已标注，不能当作真人学习收益证据。",
        "",
        f"今日预算 {schedule.get('today', {}).get('minutes_budget')} 分钟；已开始 {len(store.today_items())} 项。",
    ]
    return "\n".join(lines) + "\n"


def git_snapshot(store: Store) -> dict:
    """Honest git report: written / committed / pushed / diverged, no force-push paths.

    Core 1.0.2 owns the porcelain parsing, journal union recovery and the
    ``unmerged``/``diverged`` status fields; the variant only presents them.
    """
    from learncore.sync import GitSync

    git = GitSync(
        store.root,
        include=[".learnark", "sessions", "artifacts", "AGENTS.md", "README.md", ".gitignore", ".gitattributes"],
    )
    if not git.available():
        return {"available": False, "is_repo": False, "state": "no-git", "written": True, "committed": False, "pushed": False}
    status = git.status()
    if not status.get("is_repo"):
        return {"available": True, "is_repo": False, "state": "no-repository", "written": True, "committed": False, "pushed": False}
    changed = list(status.get("changed") or [])
    blocked = list(status.get("blocked") or [])
    unmerged = list(status.get("unmerged") or [])
    true_changed = changed + blocked
    ahead = int(status.get("ahead") or 0)
    behind = int(status.get("behind") or 0)
    remote = status.get("remote") or ""
    diverged = bool(status.get("diverged")) or bool(unmerged)
    if unmerged or (ahead and behind):
        state = "conflict"
    elif true_changed:
        state = "written"
    elif ahead:
        state = "committed-local"
    elif remote and not ahead and not behind:
        state = "pushed"
    elif not remote:
        state = "no-remote"
    else:
        state = "clean"
    return {
        "available": True,
        "is_repo": True,
        "state": state,
        "written": True,
        "committed": state in ("committed-local", "pushed", "no-remote", "clean"),
        "pushed": bool(remote and not ahead and not behind and not true_changed and not unmerged and not diverged),
        "branch": status.get("branch"),
        "remote": remote,
        "upstream": git.has_upstream(),
        "changed": len(true_changed),
        "changed_paths": true_changed[:20],
        "blocked": blocked[:10],
        "ahead": ahead,
        "behind": behind,
        "unmerged": unmerged[:20],
        "diverged": diverged,
        "clean": not true_changed and not unmerged and not diverged,
    }


def git_state(store: Store) -> dict:
    return git_snapshot(store)


def status_payload(store: Store, decision: dict | None = None) -> dict:
    from learncore import CORE_VERSION

    now = now_iso()
    today = store.schedule.get("today", {})
    due_cards = store.due_cards()
    due_skills = store.due_skills()
    current = store.schedule.get("current_session") or {}
    handoff_path = store.root / ".learnark" / "handoff" / "latest.md"
    handoff = {}
    if handoff_path.exists():
        text = handoff_path.read_text(encoding="utf-8")
        handoff = {"path": str(handoff_path.relative_to(store.root)).replace("\\", "/"), "excerpt": text[:1200]}
        match = re.search(r"- 下一步：(?P<v>.+)", text)
        if match:
            handoff["next"] = match.group("v").strip()
    last_session = None
    if current:
        last_session = {
            "id": current.get("id"),
            "mentor": current.get("mentor"),
            "path": current.get("path"),
            "started_at": current.get("started_at"),
            "activity_id": (current.get("activity") or {}).get("activity_id"),
            "turns": current.get("turns", 0),
        }
    remaining = store.today_remaining()
    min_activity = int(store.limits.get("min_activity", 5))
    exhausted = store.cap_reached() or remaining < min_activity
    if decision is None:
        planning_budget = remaining if remaining >= min_activity else store.minutes_default()
        decision = plan_decision(
            store,
            minutes=planning_budget,
            max_items=int(store.limits.get("max_items_per_session", 2)),
        )
        if decision.get("fallback"):
            exhausted = True
    if exhausted or decision.get("fallback"):
        # concrete next-session suggestion: drop today's repeat filters, not a placeholder
        next_decision = plan_decision(
            store,
            minutes=store.minutes_default(),
            max_items=int(store.limits.get("max_items_per_session", 2)),
            ignore_today=True,
        )
        next_when = "next_session"
    else:
        next_decision = decision
        candidate = decision.get("chosen") or {}
        next_when = "now" if remaining >= int(candidate.get("minutes") or 0) else "next_session"
    chosen = next_decision.get("chosen") or {}
    if next_decision.get("fallback") or (not chosen.get("skill") and not chosen.get("activity_type")):
        next_info = {
            "activity_id": None,
            "activity_type": None,
            "skill": None,
            "skill_title": None,
            "minutes": None,
            "tier": None,
            "when": "next_session",
            "reason": "暂时没有可排的下一步；下次 start 重新调度（到期优先）。",
        }
    else:
        next_info = {
            "activity_id": chosen.get("activity_id"),
            "activity_type": chosen.get("activity_type"),
            "skill": chosen.get("skill"),
            "skill_title": chosen.get("skill_title"),
            "minutes": chosen.get("minutes"),
            "tier": chosen.get("tier"),
            "when": next_when,
            "reason": ("下次：" if next_when != "now" else "") + str(next_decision.get("reason_line") or ""),
        }
    preview_budget = locals().get("planning_budget") or remaining
    next_info["decision_id"] = decision_id(next_decision, preview_budget)
    if next_when == "now" and next_info.get("activity_id") and not current:
        save_preview(store, next_decision, preview_budget, "now")
    pending_artifact = str((current or {}).get("artifact_pending") or "")
    offline = bool(store.offline or _llm_mode() == "mock")
    return {
        "variant": VARIANT_ID,
        "version": VARIANT_VERSION,
        "core_version": CORE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "project": {
            "slug": store.meta.get("slug"),
            "goal": store.meta.get("goal"),
            "template_id": store.template_id,
            "path": str(store.root),
            "created_at": store.meta.get("created_at"),
            "minutes_per_week": store.meta.get("minutes_per_week"),
            "diagnosed": bool(store.meta.get("diagnosed")),
        },
        "learner": store.meta.get("learner", {}),
        "mentor": current.get("mentor") or store.meta.get("mentor"),
        "mentor_override": store.meta.get("mentor_override"),
        "mentors": store.mentor_ids(),
        "offline": offline,
        "simulated": clock.is_simulated(),
        "now": now,
        "model": {
            "configured": "mock" if offline else _configured_model(),
            "last": store.meta.get("last_model") or ("mock" if offline else None),
        },
        "today": {
            "date": today.get("date"),
            "minutes_budget": store.today_budget(),
            "minutes_used": store.today_used(),
            "remaining_minutes": remaining,
            "minutes_left": remaining,
            "budget_source": store.budget_source(),
            "items_started": len(store.today_items()),
            "items_done": sum(1 for item in store.today_items() if item.get("done")),
            "max_items": int(store.limits.get("max_items_per_session", 2)),
            "cap_reached": store.cap_reached(),
            "items": [
                {
                    "activity_id": item.get("activity_id"),
                    "activity_type": item.get("activity_type"),
                    "skill": item.get("skill"),
                    "done": bool(item.get("done")),
                    "minutes": item.get("minutes"),
                }
                for item in store.today_items()
            ],
        },
        "due": {
            "cards": len(due_cards),
            "skills": len(due_skills),
            "max_overdue_days": max([overdue_days(c.get("due_at")) for c in due_cards] or [0]),
            "cards_preview": [
                {
                    "id": card["id"],
                    "skill": card.get("skill"),
                    "front": card.get("front"),
                    "overdue_days": overdue_days(card.get("due_at")),
                    "leech": bool(card.get("leech")),
                }
                for card in due_cards[:5]
            ],
        },
        "skills": [
            {
                "id": skill["id"],
                "title": skill.get("title"),
                "level": int(skill.get("level") or 0),
                "evidence_level": skill.get("evidence_level"),
                "last_help_level": skill.get("last_help_level"),
                "last_evidence_kind": skill.get("last_evidence_kind"),
                "due_at": skill.get("due_at"),
                "overdue_days": overdue_days(skill.get("due_at")),
                "lapses": int(skill.get("lapses") or 0),
                "wrong_tags": skill.get("wrong_tags") or [],
                "block_artifact": skill.get("block_artifact_path") or "",
            }
            for skill in store.skills.get("skills", [])
        ],
        "last_turn": store.schedule.get("last_turn"),
        "unfinished": [
            {
                "activity_id": item.get("activity_id"),
                "activity_type": item.get("activity_type"),
                "skill": item.get("skill"),
                "minutes": item.get("minutes"),
            }
            for item in store.today_items()
            if not item.get("done")
        ],
        "next": next_info,
        "pending_artifact": {
            "path": pending_artifact,
            "exists": bool(pending_artifact) and (store.root / pending_artifact).exists(),
        }
        if pending_artifact
        else None,
        "last_activity": store.schedule.get("last_activity"),
        "last_session": last_session,
        "handoff": handoff,
        "block": _block_summary(store),
        "sync": git_state(store),
        "journal": {
            "events": len(store.events()),
            "last_at": (store.events()[-1].get("at") if store.events() else None),
        },
        "recovery": list(store.repairs),
    }


def _block_summary(store: Store) -> dict | None:
    block = current_block(store.blocks.get("blocks", []), now_iso())
    if not block:
        return None
    steps = block.get("steps", [])
    return {
        "id": block.get("id"),
        "week": block.get("week"),
        "goal": block.get("goal"),
        "deliverable": block.get("deliverable"),
        "artifact_path": block.get("artifact_path") or "",
        "steps_done": sum(1 for step in steps if step.get("done")),
        "steps_total": len(steps),
    }


def _llm_mode() -> str:
    import os

    mode = (os.environ.get("LEARNARK_LLM") or "auto").strip().lower()
    if mode == "mock":
        return "mock"
    if mode == "api":
        return "api"
    return "api" if (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LEARNARK_API_KEY")) else "mock"


def _configured_model() -> str:
    """Model name we *ask* for; the API may return a different concrete model."""
    import os

    return os.environ.get("LEARNARK_MODEL") or "deepseek-chat"


def doctor_report(store: Store) -> dict:
    from learncore import CORE_VERSION

    checks: list[dict] = []

    def add(check_id: str, status: str, detail: str):
        checks.append({"id": check_id, "status": status, "detail": detail})

    meta = store.meta
    if meta.get("goal") and meta.get("schema_version") == SCHEMA_VERSION:
        add("project", "ok", f"project.json 可读，目标：{meta.get('goal')}")
    else:
        add("project", "problem", "project.json 缺少 goal 或 schema_version 不匹配")

    if store.repairs:
        add("state_recovery", "warning", "；".join(store.repairs))
    else:
        add("state", "ok", "schedule/skills/cards/blocks 均可读")

    if store.skills.get("schema_version") != SCHEMA_VERSION or store.cards.get("schema_version") != SCHEMA_VERSION:
        add("schema", "problem", "状态文件 schema_version 与项目不一致")
    else:
        add("schema", "ok", f"schema_version={SCHEMA_VERSION}")

    integrity = store.journal.integrity()
    if integrity.get("problems"):
        add("journal", "problem", "；".join(integrity["problems"]))
    else:
        add("journal", "ok", f"{integrity.get('events', 0)} 条事件，seq 单调、id 唯一")

    index_path = store.journal.index_path
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            index = None
        if not isinstance(index, dict):
            add("dedupe_index", "problem", "journal/dedupe.json 损坏；删除后下一次写入会自动重建")
        else:
            journal_keys = {e.get("dedupe_key") for e in store.events() if e.get("dedupe_key")}
            missing = journal_keys - set(index)
            extra = set(index) - journal_keys
            if missing:
                add("dedupe_index", "problem", f"去重索引缺 {len(missing)} 个键（可重建，不会丢事件）")
            elif extra:
                add("dedupe_index", "warning", f"去重索引多 {len(extra)} 个键（中断残留，可重建）")
            else:
                add("dedupe_index", "ok", f"{len(index)} 个幂等键与日志一致")
    else:
        add("dedupe_index", "warning", "去重索引不存在；下一次写入会重建")

    tmp_files = list((store.root / ".learnark" / "state").glob("*.tmp")) + list((store.root / ".learnark" / "journal").glob("*.tmp"))
    if tmp_files:
        add("interrupted_writes", "warning", f"存在 {len(tmp_files)} 个 .tmp 残留（原子写中断的痕迹，可安全删除）")
    else:
        add("interrupted_writes", "ok", "无 .tmp 残留")
    lock_files = list((store.root / ".learnark").rglob("*.lock"))
    if lock_files:
        add("locks", "ok", f"{len(lock_files)} 个锁文件存在（这是正常残留，均已解锁；已在 .gitignore 中）")
    else:
        add("locks", "ok", "无锁文件")

    snapshot_cards = {card["id"] for card in store.cards.get("cards", [])}
    journal_cards = {
        (event.get("payload") or {}).get("card")
        for event in store.events("card_created")
        if (event.get("payload") or {}).get("card")
    }
    missing_cards = sorted(journal_cards - snapshot_cards)
    if missing_cards:
        add(
            "snapshot_journal",
            "problem",
            f"{len(missing_cards)} 张日志里创建过的卡片不在快照中（下一次写命令会自动补回）：{', '.join(missing_cards[:5])}",
        )
    else:
        add("snapshot_journal", "ok", "快照中的卡片与 journal 一致")

    snapshot = git_snapshot(store)
    if not snapshot.get("available"):
        add("git", "warning", "未检测到 git；学习记录已落盘但无法提交/推送")
    elif not snapshot.get("is_repo"):
        add("git", "problem", "项目不是 git 仓库；运行 init 或 git init 后 sync")
    else:
        changed_paths = list(snapshot.get("changed_paths") or [])
        remote = snapshot.get("remote") or ""
        if snapshot.get("diverged"):
            add(
                "git_divergence",
                "problem",
                f"本地与远程已分叉（ahead {snapshot.get('ahead')} / behind {snapshot.get('behind')}，"
                f"未合并文件：{'、'.join(snapshot.get('unmerged') or []) or '无'}）；"
                "journal-only 冲突用 sync --recover，状态文件冲突需人工保留一侧后再 sync；不要 force push。",
            )
        else:
            add("git_divergence", "ok", "本地与远程未分叉")
        if changed_paths:
            add("git", "warning", f"{len(changed_paths)} 个改动未提交；运行 sync。分支 {snapshot.get('branch')}")
        else:
            add("git", "ok", f"工作区干净；分支 {snapshot.get('branch') or '-'}；远程 {remote or '无（pushed 未验证）'}")
        skipped = list(snapshot.get("blocked") or [])
        if skipped:
            add(
                "git_policy",
                "warning",
                f"{len(skipped)} 个文件被同步策略跳过但未被 .gitignore 忽略（应加入忽略或手动处理）："
                + "、".join(skipped[:5]),
            )
        else:
            add("git_policy", "ok", "没有“未忽略但被跳过”的文件")

    mode = _llm_mode()
    if mode == "api":
        import os

        if os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LEARNARK_API_KEY"):
            add("llm", "ok", "API 模式，密钥仅从环境变量读取（未写入项目）")
        else:
            add("llm", "problem", "LEARNARK_LLM=api 但没有 DEEPSEEK_API_KEY；加 --offline 或配置密钥")
    else:
        add("llm", "ok", "离线脚本导师模式（mock）；输出不能当作真实教学质量证据")

    skew = []
    for skill in store.skills.get("skills", []):
        last = skill.get("last_review_at")
        if last and date_of(last) > date_of(now_iso()):
            skew.append(f"skill {skill['id']} last_review_at={last}")
    for card in store.cards.get("cards", []):
        last = card.get("last_review_at")
        if last and date_of(last) > date_of(now_iso()):
            skew.append(f"card {card['id']} last_review_at={last}")
    if skew:
        add("clock_skew", "problem", "记录时间晚于当前时间：" + "；".join(skew[:5]))
    else:
        add("clock_skew", "ok", "无未来时间戳" + ("（模拟时钟已启用）" if clock.is_simulated() else ""))

    core_file = variant_root() / "runtime" / "CORE_VERSION"
    core_pin = core_file.read_text(encoding="utf-8").strip() if core_file.exists() else ""
    if core_pin != CORE_VERSION:
        add("core_version", "problem", f"runtime/CORE_VERSION={core_pin!r} 与 learncore {CORE_VERSION} 不一致；重新 vendor")
    else:
        add("core_version", "ok", f"vendored learncore {CORE_VERSION} 与 pin 一致")

    current = store.schedule.get("current_session") or {}
    if current and not (store.root / current.get("path", "")).exists():
        add("session_file", "warning", f"当前会话文件缺失：{current.get('path')}")
    else:
        add("session_file", "ok", "当前会话文件存在" if current else "无进行中的会话")

    problems = [c for c in checks if c["status"] == "problem"]
    warnings = [c for c in checks if c["status"] == "warning"]
    return {
        "checks": checks,
        "problems": len(problems),
        "warnings": len(warnings),
        "ok": len([c for c in checks if c["status"] == "ok"]),
        "simulated": clock.is_simulated(),
    }


def journal_adapt(journal_keys: set, index_keys: set) -> set:
    """Compatibility shim kept for callers that imported the helper early."""
    return journal_keys


# --------------------------------------------------------------------------------------
# journal rebuild (partial, journal is authoritative)
# --------------------------------------------------------------------------------------


def reconcile(store: Store) -> list[str]:
    """Heal journal -> snapshot drift.

    The journal is authoritative (shared requirement §7): an interrupted process or
    a rejected stale write may leave events that the snapshot never absorbed. Repair
    is conservative -- a record is only replayed when the snapshot clearly does not
    reflect it yet -- and never appends duplicate learning events.
    """
    notes: list[str] = []
    existing = store.skill_ids()
    existing_cards = {c["id"] for c in store.cards.get("cards", [])}
    for event in store.events("card_created"):
        payload = event.get("payload") or {}
        card_id = payload.get("card")
        if not card_id or card_id in existing_cards:
            continue
        skill = payload.get("skill")
        if skill not in existing:
            continue
        card = {
            "id": card_id,
            "skill": skill,
            "kind": payload.get("kind", "recall"),
            "front": payload.get("front", ""),
            "back": payload.get("back", ""),
            "tags": payload.get("tags") or [],
            "source_event": event.get("id", ""),
            "step": 0,
            "interval_days": 1,
            "ease": 1.0,
            "due_at": event.get("at") or now_iso(),
            "last_review_at": None,
            "lapses": 0,
            "consecutive_lapses": 0,
            "leech": False,
            "needs_rewrite": False,
            "created_at": event.get("at") or now_iso(),
        }
        store.cards.setdefault("cards", []).append(card)
        existing_cards.add(card_id)
        store.touch("cards")
        notes.append(f"从日志补回卡片 {card_id}")

    # -- card reviews lost between the journal append and the snapshot save -----
    noted_cards: set[str] = set()
    for event in store.events("card_reviewed"):
        payload = event.get("payload") or {}
        card = store.card(payload.get("card") or "")
        if card is None or payload.get("step") is None:
            continue
        event_at = str(event.get("at") or "")
        last_at = str(card.get("last_review_at") or "")
        if event_at and last_at and event_at <= last_at:
            continue
        card["step"] = int(payload.get("step") or 0)
        card["ease"] = float(payload.get("ease") or 1.0)
        card["interval_days"] = int(payload.get("interval_days") or 1)
        card["due_at"] = payload.get("due_at") or card.get("due_at")
        card["lapses"] = int(payload.get("lapses") or 0)
        card["leech"] = bool(payload.get("leech"))
        if card["leech"]:
            card["needs_rewrite"] = True
        card["last_review_at"] = event_at
        card["last_grade"] = payload.get("grade") or card.get("last_grade")
        store.touch("cards")
        if card["id"] not in noted_cards:
            noted_cards.add(card["id"])
            notes.append(
                f"从 journal 补回卡片复习：{card['id']} step={card['step']}（{payload.get('grade') or '?'}，"
                "快照落后于事件，未重复计数）"
            )

    # -- level changes (level_change / decayed / l3_granted) --------------------
    for event in store.events("level_change", "decayed", "l3_granted"):
        payload = event.get("payload") or {}
        skill = store.skill(payload.get("skill") or "")
        if skill is None:
            continue
        to = payload.get("to", 3 if event.get("kind") == "l3_granted" else None)
        try:
            to = int(to)
        except (TypeError, ValueError):
            continue
        current = int(skill.get("level") or 0)
        if current == to:
            continue
        if "from" in payload:
            try:
                if current != int(payload["from"]):
                    continue
            except (TypeError, ValueError):
                continue
        elif current > to:  # l3_granted replay must never lower a level
            continue
        skill["level"] = to
        skill["level_reason"] = f"从 journal 补回：{event.get('kind')}（{payload.get('reason') or ''}）"
        if event.get("kind") == "level_change":
            skill["last_level_up_date"] = date_of(event.get("at"))
            refs = skill.setdefault("evidence_refs", [])
            refs.append({"event": event.get("id"), "kind": "level_up_replayed", "at": event.get("at")})
            del refs[:-20]
        store.touch("skills")
        notes.append(f"从 journal 补回等级变更：{skill['id']} L{current}→L{to}")

    # -- completion marks for activities started earlier today ------------------
    for event in store.events("activity_completed"):
        payload = event.get("payload") or {}
        activity_id = payload.get("activity_id")
        if not activity_id:
            continue
        for item in store.today_items():
            if item.get("activity_id") != activity_id or item.get("done"):
                continue
            started = str(item.get("started_at") or "")
            if started and str(event.get("at") or "") < started:
                continue
            item["done"] = True
            store.touch("schedule")
            notes.append(f"从 journal 补回活动完成标记：{activity_id}")

    if not store.meta.get("diagnosed") and store.events("attempt"):
        store.meta["diagnosed"] = True
        store.touch("meta")
        notes.append("诊断标记已按日志补回（diagnosed=true）")

    # -- a corrupt dedupe index is rebuilt (and persisted) by the next append ----
    index_path = store.journal.index_path
    index_invalid = False
    if index_path.exists():
        try:
            index_invalid = not isinstance(json.loads(index_path.read_text(encoding="utf-8")), dict)
        except (ValueError, OSError):
            index_invalid = True
    if index_invalid:
        store.append(
            "journal_index_rebuilt",
            {"reason": "dedupe.json 损坏，写入前按 journal 重建（事件未丢）"},
            dedupe_key=f"index:rebuild:{len(store.events())}:{date_of(now_iso())}",
        )
        notes.append("去重索引 dedupe.json 损坏：已按 journal 重建")
    return notes


def llm_handle(store: Store, *, offline: bool = False):
    """Build the mentor backend via learncore, honouring --offline."""
    import os

    from learncore import llm as llm_mod

    if offline:
        os.environ["LEARNARK_LLM"] = "mock"
    script = os.environ.get("LEARNARK_MOCK_SCRIPT")
    if not script:
        default = variant_root() / "tests" / "fixtures" / "mentor_script.jsonl"
        if default.exists():
            os.environ["LEARNARK_MOCK_SCRIPT"] = str(default)
    usage = store.root / ".learnark" / "usage.jsonl"
    return llm_mod.from_env(usage_file=usage)


def llm_label(model) -> str:
    mode = getattr(model, "mode", "api")
    if mode == "mock":
        return "离线脚本导师（mock）"
    return f"API 导师（{getattr(model, 'model', '?')}）"
