"""SkillMap runtime engine: context, evidence rules, stage machine, diagnosis, SRS.

Everything that can change state lives here.  The rules are deliberately boring:
the mentor proposes, the runtime decides.  A learner level only moves when a
``correct=true`` attempt with ``help_level<=1`` is recorded, never twice for the
same answer in one session, and never by more than one step per turn.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from learncore import clock
from learncore import mentor as core_mentor
from learncore.fsutil import short_hash, sha256_text

import sm_model
import sm_mentors
import sm_state


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------
class Context:
    """Loaded project state plus the journal for one command invocation."""

    def __init__(self, root: str | Path, variant_dir: str | Path | None = None, llm=None):
        self.p = sm_state.Project(root, variant_dir)
        state = self.p.load()
        self.pj = state["project"]
        self.map = state["map"]
        self.plan = state["plan"]
        self.mem = state["memory"]
        self.repairs = list(state["repairs"])
        self.journal = self.p.journal
        # A torn journal tail must be repaired *before* the first append, or the
        # new event would be concatenated onto the fragment and corrupt the file.
        journal_note = sm_state.repair_journal_tail(self.p.journal_path)
        if journal_note:
            self.repairs.append(journal_note)
        self.template = self.pj.get("template") or sm_model.DEFAULT_TEMPLATE
        self.variant_dir = self.p.variant_dir
        self.curriculum = sm_model.load_curriculum(self.variant_dir, self.template)
        self.llm = llm
        self.mode = "mock" if getattr(llm, "mode", "") == "mock" else "api"
        self.today = clock.today()
        self.dirty: set[str] = set()
        self.drifts: list[dict] = []

    # -- documents -------------------------------------------------------
    def mark(self, *names: str) -> None:
        self.dirty.update(names)

    def save(self) -> None:
        if "project" in self.dirty:
            self.pj = self.p.save_project(self.pj)
        if "map" in self.dirty:
            self.map = self.p.save_map(self.map)
        if "plan" in self.dirty:
            self.plan = self.p.save_plan(self.plan)
        if "memory" in self.dirty:
            self.mem = self.p.save_memory(self.mem)
        self.dirty.clear()

    # -- journal ---------------------------------------------------------
    def event(self, kind: str, payload: dict | None = None, *, dedupe_key: str | None = None, actor: str = "runtime"):
        return self.journal.append(kind, payload or {}, dedupe_key=dedupe_key, actor=actor)

    # -- derived helpers -------------------------------------------------
    def refresh(self) -> list[dict]:
        self.drifts = sm_model.refresh_statuses(self.map, self.plan, self.today)
        if self.drifts:
            self.mark("map")
            for drift in self.drifts:
                self.event(
                    "map_status_drift",
                    drift,
                    dedupe_key=f"drift:{self.today}:{drift['node']}:{drift['cached']}>{drift['derived']}",
                )
        return self.drifts

    def index(self) -> dict[str, dict]:
        return sm_model.by_id(self.map)

    def node(self, node_id: str | None = None) -> dict | None:
        wanted = node_id or self.plan.get("current_node")
        if not wanted:
            return None
        return self.index().get(wanted)

    def diagnosis(self) -> dict:
        learner = self.pj.setdefault("learner", {})
        return learner.setdefault("diagnosis", {"status": "pending", "round": 0, "probes": [], "completed_at": None})

    def mode_name(self) -> str:
        if self.diagnosis().get("status") == "pending":
            return "diagnose"
        if self.plan.get("mode") == "review":
            return "review"
        return "stage"

    def stage_name(self) -> str:
        mode = self.mode_name()
        if mode == "diagnose":
            return "diagnose"
        if mode == "review":
            return "check"
        return self.plan.get("stage") or "explain"

    def mentor(self) -> str:
        mode = self.mode_name()
        stage = self.stage_name()
        base = "navigator" if mode == "diagnose" else sm_model.mentor_for_stage(stage)
        # On-demand switches (e.g. concept during apply) must win over the stage
        # default; only the *automatic* default is restricted to the stage set.
        allowed = sm_model.user_allowed("review" if mode == "review" else stage)
        override = self.plan.get("mentor_override")
        if override in allowed:
            return override
        return base

    def next_mentor(self) -> str:
        """Single authority for "who takes the next turn", used by status/handoff/plan."""
        if self.mode_name() == "diagnose":
            return "navigator"
        if self.node() is not None:
            return self.mentor()
        decision = sm_model.next_decision(self.map, self.plan, self.today, self.minutes(), estimated_minutes=self.activity_estimate())
        selected = decision.get("selected") or {}
        return selected.get("mentor") or "navigator"

    def allowed_mentors(self) -> tuple[str, ...]:
        return sm_model.user_allowed("review" if self.mode_name() == "review" else self.stage_name())

    def mentor_catalog(self) -> list[dict]:
        return sm_model.mentor_catalog("review" if self.mode_name() == "review" else self.stage_name())

    def activity_id(self) -> str:
        mode = self.mode_name()
        if mode == "diagnose":
            return "diagnose"
        if mode == "review":
            return "review"
        node = self.node()
        return sm_model.activity_for(node["id"], self.plan.get("stage") or "explain") if node else "diagnose"

    def help_cap(self) -> int:
        mode = self.mode_name()
        if mode in ("review",) or self.stage_name() == "check":
            return 0
        return 2

    def minutes(self) -> int | None:
        value = self.plan.get("minutes_budget")
        return int(value) if value else None

    def diagnosis_minutes(self) -> int:
        """Planned diagnosis time booked into this session (0 when already done)."""
        booked = self.plan.get("diagnosis_minutes")
        if booked is not None:
            return int(booked)
        if not self.minutes() or self.diagnosis().get("status") != "pending":
            return 0
        return sm_model.diagnosis_minutes(self.minutes(), len(self.diagnosis().get("probes") or []) or sm_model.total_probes(self.template))

    def activity_estimate(self) -> int:
        """Minutes the next activity may take, after diagnosis and reserve."""
        return sm_model.estimate_minutes(self.minutes(), diagnosis_spent=self.diagnosis_minutes())

    def budget_breakdown(self) -> dict:
        return sm_model.budget_breakdown(self.minutes(), self.diagnosis_minutes())

    def current_probe(self) -> dict | None:
        for probe in self.diagnosis().get("probes") or []:
            if probe.get("status") == "pending":
                return probe
        return None

    # -- session ---------------------------------------------------------
    def ensure_session(self) -> dict:
        if self.plan.get("session_active") and self.plan.get("session_id") and self.plan.get("session_file"):
            return {"session_id": self.plan["session_id"], "resumed": True}
        info = self.p.new_session(self.mentor())
        self.plan.update(info)
        self.plan["turn_index"] = 0
        self.plan["next_mentor"] = self.next_mentor()
        # Book the planned diagnosis time once, at session start; the activity
        # estimate then subtracts it so the whole session fits the budget.
        if self.diagnosis().get("status") == "pending" and self.minutes():
            probes = len(self.diagnosis().get("probes") or []) or sm_model.total_probes(self.template)
            self.plan["diagnosis_minutes"] = sm_model.diagnosis_minutes(self.minutes(), probes)
        else:
            self.plan["diagnosis_minutes"] = 0
        self.mark("plan")
        self.event(
            "session_started",
            {
                "session_id": info["session_id"],
                "mentor": info["session_mentor"],
                "activity_id": self.activity_id(),
                "minutes_budget": self.minutes(),
                "mode": self.mode_name(),
            },
            dedupe_key=f"session:{info['session_id']}",
        )
        return {"session_id": info["session_id"], "resumed": False}

    def transcript(self, limit: int = 6) -> list[dict]:
        return sm_mentors.transcript_from_journal(self.journal, self.plan.get("session_id"), limit)

    def previous_help_level(self, node_id: str) -> int | None:
        """Help level of the previous mentor turn on this node in this session.

        Used to stop a level claim right after an assisted turn: the answer may be
        correct, but it was scaffolded one turn earlier, so it cannot count as
        independent evidence.
        """
        events = self.journal.of_kind("mentor_turn")
        for event in reversed(events):
            payload = event.get("payload") or {}
            if payload.get("session_id") != self.plan.get("session_id"):
                continue
            activity = payload.get("activity_id") or ""
            if not activity.startswith(f"{node_id}-"):
                continue
            level = payload.get("help_level")
            return int(level) if isinstance(level, int) else None
        return None

    # -- context for the model -------------------------------------------
    def runtime_next(self) -> dict:
        """The authoritative next step, injected into every mentor context.

        Mentors must not invent a starting point; `start`, `status` and the
        mentor's prose all read from this one object.
        """
        if self.mode_name() == "diagnose":
            probe = self.current_probe()
            return {
                "status": "diagnosis",
                "node": probe["node"] if probe else None,
                "probe": probe["id"] if probe else None,
                "activity_id": "diagnose",
                "mentor": "navigator",
                "reason": "诊断尚未结束：只问当前这一题，不要宣布学习起点",
            }
        node = self.node()
        placement = self.plan.get("placement") or {}
        if node is not None:
            stage = self.plan.get("stage") or "explain"
            placed = placement.get("node") == node["id"]
            return {
                "status": "planned",
                "node": node["id"],
                "stage": stage,
                "activity_id": f"{node['id']}-{stage}",
                "mentor": self.mentor(),
                "source": "placement" if placed else "plan",
                "reason": placement.get("reason") if placed else "运行时已选好当前节点与阶段（next-v1）",
            }
        decision = sm_model.next_decision(self.map, self.plan, self.today, self.minutes(), estimated_minutes=self.activity_estimate())
        selected = decision.get("selected") or {}
        return {
            "status": "next" if selected else "empty",
            "node": selected.get("node"),
            "stage": selected.get("stage"),
            "activity_id": selected.get("activity_id"),
            "mentor": selected.get("mentor"),
            "source": "next-v1",
            "reason": "运行时尚未落定当前节点；以 runtime_next 为准",
        }

    def model_context(self) -> str:
        return sm_mentors.build_context(
            project=self.pj,
            map_doc=self.map,
            plan=self.plan,
            journal=self.journal,
            session_id=self.plan.get("session_id"),
            node=self.node(),
            stage=self.stage_name(),
            mode=self.mode_name(),
            curriculum=self.curriculum,
            minutes_budget=self.minutes(),
            review_due=sm_model.due_nodes(self.map, self.today),
            runtime_next=self.runtime_next(),
        )

    def system_prompt(self) -> str:
        return sm_mentors.system_prompt(
            variant_dir=self.variant_dir,
            mentor=self.mentor(),
            template=self.template,
            stage=self.stage_name(),
            mode=self.mode_name(),
            node=self.node(),
            goal=self.pj.get("goal"),
            activity_id=self.activity_id(),
            help_cap=self.help_cap(),
            probe=self.current_probe() if self.mode_name() == "diagnose" else None,
        )


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------
def _store_decision(ctx: Context, decision: dict) -> dict:
    ctx.plan["last_decision"] = {
        "computed_at": clock.now_iso(),
        "rule_version": sm_model.RULE_VERSION,
        "selected": (decision.get("selected") or {}).get("node"),
        "candidates": decision.get("candidates", []),
        "excluded": decision.get("excluded", []),
        "reasons": decision.get("reasons", []),
    }
    ctx.mark("plan")
    return decision


def decision_payload(ctx: Context) -> dict:
    return _store_decision(ctx, sm_model.next_decision(ctx.map, ctx.plan, ctx.today, ctx.minutes(), estimated_minutes=ctx.activity_estimate()))


def plan_next(ctx: Context, *, force_node: str | None = None) -> dict:
    """Select the next node/stage and put it in the plan.  Returns the decision."""
    if force_node:
        node = ctx.node(force_node)
        if node is None:
            raise sm_state.LearnError(f"unknown node {force_node}")
        index = ctx.index()
        if not sm_model.prereqs_ready(node, index) and not node.get("gate_override"):
            node["gate_override"] = True
            ctx.mark("map")
            ctx.event(
                "gate_override",
                {"node": node["id"], "unmet": sm_model.unmet_prereqs(node, index), "cap": 1},
                dedupe_key=f"gate_override:{node['id']}:{ctx.today}",
            )
        stage = sm_model.stage_for(node, ctx.plan)
        _set_current(ctx, node["id"], stage)
        return _store_decision(ctx, sm_model.next_decision(ctx.map, ctx.plan, ctx.today, ctx.minutes(), estimated_minutes=ctx.activity_estimate()))

    decision = decision_payload(ctx)
    selected = decision.get("selected")
    if not selected:
        ctx.plan["current_node"] = None
        ctx.plan["stage"] = None
        ctx.plan["stage_progress"] = {}
        ctx.mark("plan")
        return decision
    _set_current(ctx, selected["node"], selected["stage"])
    return decision


def _set_current(ctx: Context, node_id: str, stage: str) -> None:
    # A placement only applies to the node/stage it was computed for.
    ctx.plan.pop("placement", None)
    ctx.plan["current_node"] = node_id
    ctx.plan["stage"] = stage
    ctx.plan["stage_started_at"] = clock.now_iso()
    ctx.plan["stage_progress"] = sm_model.fresh_progress(node_id, stage)
    ctx.plan["stage_progress"]["level_at_start"] = int((ctx.node(node_id) or {}).get("level", 0))
    ctx.plan["mode"] = "stage"
    node = ctx.node(node_id)
    if node:
        ctx.plan["session_goal"] = f"{node_id} · {sm_model.stage_label(stage)}（{node_id}-{stage}）"
    # An override that the new stage does not accept is dropped.
    if ctx.plan.get("mentor_override") not in sm_model.user_allowed(stage):
        ctx.plan["mentor_override"] = None
    ctx.plan["next_mentor"] = ctx.next_mentor()
    ctx.mark("plan")
    ctx.event(
        "plan_selected",
        {"node": node_id, "stage": stage, "activity_id": f"{node_id}-{stage}", "mentor": ctx.next_mentor()},
        dedupe_key=f"plan_selected:{ctx.plan.get('session_id')}:{node_id}:{stage}",
    )


def set_stage(ctx: Context, stage: str) -> None:
    node = ctx.node()
    if not node:
        return
    placement = ctx.plan.get("placement") or {}
    if placement and (placement.get("node") != node["id"] or placement.get("stage") != stage):
        # The placement's promise ("skip explain/drill, start at apply") is served
        # once the node moves on; it must not linger as a reason.
        ctx.plan.pop("placement", None)
    ctx.plan["stage"] = stage
    ctx.plan["stage_progress"] = sm_model.fresh_progress(node["id"], stage)
    ctx.plan["stage_progress"]["level_at_start"] = int(node.get("level", 0))
    ctx.plan["stage_started_at"] = clock.now_iso()
    ctx.plan["session_goal"] = f"{node['id']} · {sm_model.stage_label(stage)}（{node['id']}-{stage}）"
    if ctx.plan.get("mentor_override") not in sm_model.user_allowed(stage):
        ctx.plan["mentor_override"] = None
    ctx.plan["next_mentor"] = ctx.next_mentor()
    ctx.mark("plan")
    ctx.event(
        "stage_changed",
        {"node": node["id"], "stage": stage, "activity_id": f"{node['id']}-{stage}", "mentor": ctx.next_mentor()},
        dedupe_key=f"stage_changed:{ctx.plan.get('session_id')}:{node['id']}:{stage}",
    )


# ---------------------------------------------------------------------------
# diagnosis
# ---------------------------------------------------------------------------
def ensure_probes(ctx: Context) -> None:
    diagnosis = ctx.diagnosis()
    if diagnosis.get("probes"):
        return
    diagnosis["probes"] = [
        {
            "id": probe["id"],
            "node": probe["node"],
            "question": probe["question"],
            "status": "pending",
            "answer_sha": None,
            "level_set": None,
            "correct": None,
            "help_level": None,
            "at": None,
        }
        for probe in sm_model.probe_defs(ctx.template)
    ]
    diagnosis["status"] = "pending"
    diagnosis["round"] = int(diagnosis.get("round") or 0) + 1
    diagnosis["completed_at"] = None
    ctx.plan["mode"] = "diagnose"
    ctx.plan["stage"] = "diagnose"
    ctx.plan["current_node"] = None
    ctx.plan["stage_progress"] = {}
    ctx.plan.pop("placement", None)
    ctx.mark("project", "plan")
    ctx.event(
        "diagnosis_started",
        {
            "round": diagnosis["round"],
            "probes": [probe["id"] for probe in diagnosis["probes"]],
            "anchors": [probe["node"] for probe in diagnosis["probes"]],
            "minutes_budget": ctx.minutes(),
        },
        dedupe_key=f"diagnosis_started:{diagnosis['round']}",
    )
    _defer_extra_probes(ctx)


def _defer_extra_probes(ctx: Context) -> None:
    """Short budget: keep at most N probes active, defer the rest (A: budget)."""
    limit = sm_model.probe_limit(ctx.minutes())
    if not limit:
        return
    probes = ctx.diagnosis().get("probes") or []
    if len(probes) <= limit:
        return
    deferred = probes[limit:]
    for probe in deferred:
        if probe.get("status") == "pending":
            probe["status"] = "deferred"
            probe["deferred_reason"] = "budget"
    diagnosis = ctx.diagnosis()
    ctx.mark("project")
    ctx.event(
        "diagnosis_deferred",
        {
            "round": diagnosis.get("round"),
            "budget": ctx.minutes(),
            "limit": limit,
            "deferred": [probe["id"] for probe in deferred],
            "nodes": [probe["node"] for probe in deferred],
            "reason": f"本次预算 {ctx.minutes()} 分钟 < {sm_model.SHORT_DIAGNOSIS_MINUTES} 分钟：只做 {limit} 题（约 {sm_model.diagnosis_minutes(ctx.minutes())} 分钟），其余延后",
        },
        dedupe_key=f"diagnosis_deferred:{diagnosis.get('round')}",
    )


def active_probes(ctx: Context) -> list[dict]:
    return [probe for probe in ctx.diagnosis().get("probes") or [] if probe.get("status") != "deferred"]


def deferred_probes(ctx: Context) -> list[dict]:
    return [probe for probe in ctx.diagnosis().get("probes") or [] if probe.get("status") == "deferred"]


def probe_index(ctx: Context, probe_id: str) -> int:
    for position, probe in enumerate(active_probes(ctx), start=1):
        if probe["id"] == probe_id:
            return position
    return 0


def probe_card(ctx: Context, probe: dict) -> str:
    position = probe_index(ctx, probe["id"])
    total = len(active_probes(ctx))
    lines = [
        f"—— 诊断探针 {position}/{total} · 锚点 {probe['node']} ——",
        probe["question"],
        "回答「不知道」或「跳过」也是合法答案；诊断只会把节点置为 L0/L1，不会给 L2 以上。",
    ]
    deferred = deferred_probes(ctx)
    if deferred:
        lines.append(
            f"（本次预算 {ctx.minutes()} 分钟：只做 {total} 题，其余 {len(deferred)} 题延后；想补齐可运行 `diagnose`）"
        )
    return "\n".join(lines)


def compute_placement(ctx: Context) -> dict | None:
    """A-S2 placement: start a probed node at ``apply`` when its prereqs are ready.

    Diagnosis may only assert L1 ("can restate"), which the map already treats as
    the explain exit condition.  To skip explain *and* drill the node must also
    have every prereq at the **availability gate L1** — a prereq still at L0
    blocks placement, exactly like it blocks ``next``.  When several probed nodes
    qualify, the most advanced one (highest cluster, then id) wins; the choice is
    deterministic so ``next --json`` stays byte-identical.
    """
    diagnosis = ctx.diagnosis()
    index = ctx.index()
    eligible: list[tuple[dict, dict]] = []
    for probe in diagnosis.get("probes") or []:
        if probe.get("status") != "done" or int(probe.get("level_set") or 0) < 1:
            continue
        node = index.get(probe.get("node"))
        if node is None or int(node.get("level", 0)) < 1:
            continue
        if not sm_model.prereqs_ready(node, index, sm_model.AVAILABILITY_GATE):
            continue
        eligible.append((node, probe))
    if not eligible:
        return None
    node, probe = max(eligible, key=lambda item: (int(item[0].get("cluster_index", 0)), item[0]["id"]))
    prereq_text = "、".join(f"{p} L{index[p]['level']}" for p in node.get("prereqs", [])) or "无先修"
    return {
        "node": node["id"],
        "level": int(node["level"]),
        "probe": probe["id"],
        "stage": "apply",
        "prereqs": prereq_text,
        "reason": (
            f"诊断定位：探针 {probe['id']} 把 {node['id']} 置为 L1（诊断上限），"
            f"其先修 {prereq_text} 均已 ≥L{sm_model.AVAILABILITY_GATE}，"
            f"因此跳过讲解与操练，直接进入应用（{node['id']}-apply）"
        ),
    }


def finish_diagnosis(ctx: Context, status: str = "done", *, end_reason: str | None = None) -> None:
    diagnosis = ctx.diagnosis()
    diagnosis["status"] = status
    diagnosis["completed_at"] = clock.now_iso()
    diagnosis["end_reason"] = end_reason or status
    levels = {probe["node"]: probe.get("level_set") for probe in diagnosis.get("probes") or []}
    ctx.mark("project")
    ctx.event(
        "diagnosis_done",
        {
            "status": status,
            "round": diagnosis.get("round"),
            "levels": levels,
            "end_reason": diagnosis["end_reason"],
            "skipped": [probe["id"] for probe in diagnosis.get("probes") or [] if probe.get("status") == "skipped"],
            "deferred": [probe["id"] for probe in diagnosis.get("probes") or [] if probe.get("status") == "deferred"],
        },
        dedupe_key=f"diagnosis_done:{diagnosis.get('round')}",
    )
    ctx.plan["mode"] = "stage"
    ctx.plan["stage"] = None
    ctx.plan["stage_progress"] = {}
    ctx.plan.pop("placement", None)
    ctx.mark("plan")
    # A skipped diagnosis still keeps every level earned so far, and may still
    # place the learner (round-05: "diagnose --skip then reset toward A1").
    placement = compute_placement(ctx)
    if not placement:
        return
    _set_current(ctx, placement["node"], placement["stage"])
    ctx.plan["placement"] = placement
    ctx.mark("plan")
    ctx.event(
        "placement_applied",
        {
            "node": placement["node"],
            "level": placement["level"],
            "probe": placement["probe"],
            "stage": placement["stage"],
            "reason": placement["reason"],
            "diagnosis_round": diagnosis.get("round"),
            "diagnosis_status": status,
        },
        dedupe_key=f"placement:{diagnosis.get('round')}:{placement['node']}",
    )
    _store_decision(ctx, sm_model.next_decision(ctx.map, ctx.plan, ctx.today, ctx.minutes(), estimated_minutes=ctx.activity_estimate()))


DIAGNOSIS_END_MENTOR_RE = re.compile(
    r"(诊断到此结束|诊断就到这里|结束诊断|跳过剩余|剩下.{0,8}题.{0,6}跳过|不再逐题|剩下的题不用答)"
)
DIAGNOSIS_END_LEARNER_RE = re.compile(
    r"(跳过诊断|跳过剩下|剩下的?题.{0,4}跳过|诊断到此|诊断先到这里|不做诊断|直接开始学习|直接进入学习)"
)


def diagnosis_end_signal(ctx: Context, text: str, turn) -> str | None:
    """Detect a dialogue-level decision to stop the diagnosis early."""
    if ctx.diagnosis().get("status") != "pending":
        return None
    update = getattr(turn, "updates", None) or {}
    if isinstance(update, dict) and update.get("diagnosis") == "skip":
        return "block"
    mentor_text = getattr(turn, "text", "") or ""
    if DIAGNOSIS_END_MENTOR_RE.search(mentor_text):
        return "mentor"
    if DIAGNOSIS_END_LEARNER_RE.search(text or ""):
        return "learner"
    return None


def finish_diagnosis_early(ctx: Context, reason: str) -> None:
    """Stop the diagnosis now: defer unanswered probes and keep earned levels."""
    diagnosis = ctx.diagnosis()
    deferred = []
    for probe in diagnosis.get("probes") or []:
        if probe.get("status") == "pending":
            probe["status"] = "deferred"
            probe["deferred_reason"] = f"dialogue_{reason}"
            deferred.append(probe["id"])
    ctx.mark("project")
    ctx.event(
        "diagnosis_skipped",
        {
            "round": diagnosis.get("round"),
            "reason": reason,
            "deferred": deferred,
            "kept_levels": {probe["node"]: probe.get("level_set") for probe in diagnosis.get("probes") or []},
        },
        dedupe_key=f"diagnosis_skipped:{diagnosis.get('round')}",
    )
    finish_diagnosis(ctx, "skipped", end_reason=f"dialogue_{reason}")


def apply_probe_answer(ctx: Context, text: str, turn, *, force_answer: bool = False) -> dict:
    """Record one probe answer, or keep the probe pending when it wasn't answered.

    The probe cursor must follow the *learner's* answer, not the mentor's prose:

    * ``skipped``  — the learner said “不知道/跳过”; record L0 and move on.
    * ``answered`` — the block judges this probe (``probe`` claim, or the legacy
      ``attempt.correct`` fallback); a ``probe`` claim for another anchor is
      rejected and never advances the cursor.
    * ``followup`` — the mentor asked an extra question instead of judging
      (no claim, ``correct: null``); the same probe stays pending and is re-asked.
    * ``rejected`` — a claim for the wrong anchor; logged, probe unchanged.

    A probe is never marked ``done`` with ``correct: null``.
    """
    diagnosis = ctx.diagnosis()
    probe = ctx.current_probe()
    if probe is None:
        return {"probe": None, "next": None, "level_set": None, "status": "none", "notes": []}
    index = ctx.index()
    node = index.get(probe["node"])
    answer_sha = sha256_text(text)[:16]
    skipped = sm_model.is_skip_answer(text)
    help_level = 0
    correct = None
    notes: list[str] = []
    claim = None
    claim_level = 0
    claim_reason = None

    if turn is not None and isinstance(turn.updates, dict):
        help_level = turn.updates.get("help_level") if isinstance(turn.updates.get("help_level"), int) else 0
        attempt = turn.updates.get("attempt") if isinstance(turn.updates.get("attempt"), dict) else {}
        correct = attempt.get("correct")
        raw_claim = turn.updates.get("probe")
        if isinstance(raw_claim, dict):
            claim = raw_claim
            claim_level = int(raw_claim.get("level") or 0)
            claim_reason = raw_claim.get("reason")

    if skipped:
        decision = "skipped"
        level_set = 0
    elif claim is not None and claim.get("node") != probe["node"]:
        # A declared anchor, but not the probe that is actually being asked:
        # record it and keep the cursor where it is (re-ask the same probe).
        ctx.event(
            "probe_claim_rejected",
            {
                "probe": probe["id"],
                "expected_node": probe["node"],
                "claimed_node": claim.get("node"),
                "reason": "probe claim does not match the current probe anchor",
            },
            dedupe_key=f"probe_claim_rejected:{diagnosis.get('round')}:{probe['id']}:{sha256_text(str(claim.get('node')))[:8]}",
        )
        ctx.event(
            "probe_deferred",
            {"probe": probe["id"], "node": probe["node"], "reason": "claim_for_another_anchor"},
            dedupe_key=f"probe_deferred:{diagnosis.get('round')}:{probe['id']}:{sha256_text(text)[:10]}",
        )
        notes.append(f"导师给的评级和当前这道题（{probe['node']}）不一致，已忽略；还是这道题，请继续回答。")
        return {"probe": probe, "next": probe, "level_set": None, "status": "rejected", "notes": notes}
    elif claim is not None:
        decision = "answered"
        level_set = claim_level
        correct = level_set == 1
    elif correct is not None:
        decision = "answered"
        level_set = 1 if (correct is True and int(help_level or 0) <= 1) else 0
    elif force_answer:
        # A reply whose record format was unusable: we cannot tell a judgement
        # from a follow-up, so consume it conservatively as L0 (never null).
        decision = "answered"
        level_set = 0
        correct = False
    else:
        # The mentor asked a follow-up instead of judging: the learner answered
        # *inside* this probe, so do not advance. The footer re-asks the probe.
        ctx.event(
            "probe_deferred",
            {"probe": probe["id"], "node": probe["node"], "reason": "mentor_followup_without_rating"},
            dedupe_key=f"probe_deferred:{diagnosis.get('round')}:{probe['id']}:{sha256_text(text)[:10]}",
        )
        notes.append(f"导师这轮是在追问，诊断进度不变；当前仍是第 {probe_index(ctx, probe['id'])} 题（{probe['node']}）。")
        return {"probe": probe, "next": probe, "level_set": None, "status": "followup", "notes": notes}

    if node is not None:
        old = int(node.get("level", 0))
        capped = min(max(old, level_set), 1) if old < 2 else old  # diagnosis may never exceed L1
        if capped != old:
            node["level"] = capped
            node["level_source"] = "diagnosis"
            node["updated_at"] = clock.now_iso()
            ctx.mark("map")
            ctx.event(
                "level_up",
                {
                    "node": node["id"],
                    "from": old,
                    "to": capped,
                    "reason": "diagnosis",
                    "cap": 1,
                    "event_kind": "diagnosis_probe",
                },
                dedupe_key=f"level_up:diagnosis:{diagnosis.get('round')}:{probe['id']}",
            )
            notes.append(f"{node['id']} 由诊断置为 L{capped}（诊断上限 L1）")
        elif level_set > old:
            ctx.event(
                "level_cap",
                {"node": node["id"], "requested": level_set, "current": old, "reason": "diagnosis_cap_or_existing_higher"},
                dedupe_key=f"level_cap:diagnosis:{diagnosis.get('round')}:{probe['id']}",
            )

    probe.update(
        {
            "status": "skipped" if decision == "skipped" else "done",
            "answer_sha": answer_sha,
            "level_set": level_set,
            "correct": correct,
            "help_level": int(help_level or 0),
            "probe_claim": claim,
            "claim_reason": claim_reason,
            "at": clock.now_iso(),
        }
    )
    if decision == "skipped":
        notes.append(f"第 {probe_index(ctx, probe['id'])} 题记为“不知道/跳过”，按 L0 起算，不扣分。")
    ctx.mark("project")
    ctx.event(
        "diagnosis_probe",
        {
            "probe": probe["id"],
            "round": diagnosis.get("round"),
            "node": probe["node"],
            "status": probe["status"],
            "answer_sha": answer_sha,
            "correct": correct,
            "help_level": int(help_level or 0),
            "level_set": level_set,
            "probe_claim": claim,
            "claim_reason": claim_reason,
        },
        dedupe_key=f"diagnosis_probe:{diagnosis.get('round')}:{probe['id']}",
    )
    remaining = [p for p in diagnosis.get("probes") or [] if p.get("status") == "pending"]
    if not remaining:
        finish_diagnosis(ctx, "done")
    return {
        "probe": probe,
        "next": (remaining[0] if remaining else None),
        "level_set": level_set,
        "status": "answered" if decision == "answered" else "skipped",
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# evidence rules
# ---------------------------------------------------------------------------
def validate_turn(ctx: Context, turn) -> tuple[bool, list[str]]:
    problems = list(core_mentor.validate_updates(turn.updates))
    if turn.update_error:
        problems.append(turn.update_error)
    if turn.updates is None:
        if not turn.update_error:
            problems.append("missing learn-update block")
        return False, problems
    if not isinstance(turn.updates, dict):
        return False, problems + ["learn-update must be a JSON object"]
    updates = turn.updates

    help_level = updates.get("help_level")
    if not isinstance(help_level, int) or isinstance(help_level, bool) or not 0 <= help_level <= 3:
        problems.append(f"help_level must be an int 0..3, got {help_level!r}")
    attempt = updates.get("attempt")
    if attempt is not None:
        if not isinstance(attempt, dict):
            problems.append("attempt must be an object")
        else:
            activity = attempt.get("activity_id")
            if not isinstance(activity, str) or not sm_model.valid_activity(activity):
                problems.append(
                    f"attempt.activity_id must be '<node>-<stage>' or diagnose|review|handoff, got {activity!r}"
                )
            correct = attempt.get("correct")
            if not (correct is True or correct is False or correct is None):
                problems.append(f"attempt.correct must be true, false or null, got {correct!r}")
    for key in ("misconception", "next", "artifact"):
        value = updates.get(key)
        if value is not None and not isinstance(value, str):
            problems.append(f"{key} must be a string or null")
    probe = updates.get("probe")
    if probe is not None:
        if not isinstance(probe, dict):
            problems.append("probe must be an object or null")
        else:
            anchors = {item["node"] for item in sm_model.probe_defs(ctx.template)}
            probe_node = probe.get("node")
            if not isinstance(probe_node, str) or probe_node not in anchors:
                problems.append(f"probe.node must be a declared anchor {sorted(anchors)}, got {probe_node!r}")
            probe_level = probe.get("level")
            if not isinstance(probe_level, int) or isinstance(probe_level, bool) or probe_level not in (0, 1):
                problems.append(f"probe.level must be 0 or 1, got {probe_level!r}")
            probe_reason = probe.get("reason")
            if probe_reason is not None and not isinstance(probe_reason, str):
                problems.append("probe.reason must be a string or null")
    diagnosis_field = updates.get("diagnosis")
    if diagnosis_field is not None and diagnosis_field not in ("skip", "done"):
        problems.append(f"diagnosis must be 'skip', 'done' or null, got {diagnosis_field!r}")
    mastery = updates.get("mastery_delta")
    if mastery is not None and (not isinstance(mastery, int) or isinstance(mastery, bool)):
        problems.append("mastery_delta must be an integer")
    return (not problems), problems


def record_invalid(ctx: Context, turn, problems: list[str], mentor: str, activity: str | None = None) -> dict:
    event = ctx.event(
        "mentor_update_invalid",
        {
            "mentor": mentor,
            "session_id": ctx.plan.get("session_id"),
            "raw_sha256": sha256_text(turn.raw or "")[:16],
            "problems": problems,
            "activity_id": activity or ctx.activity_id(),
        },
        dedupe_key=f"invalid:{ctx.plan.get('session_id')}:{ctx.plan.get('turn_index')}:{sha256_text(turn.raw or '')[:10]}",
    )
    return {"event": event, "problems": problems}


def _artifact(ctx: Context, artifact: str | None) -> dict:
    info = ctx.p.artifact_info(artifact)
    return info or {"path": None, "exists": False, "sha256": None, "error": "artifact missing"}


def _cap_for(node: dict, index: dict) -> tuple[int, str]:
    cap = int(node.get("target_level", 3))
    if node.get("gate_override") and sm_model.unmet_prereqs(node, index):
        return min(cap, 1), "gate_override"
    return cap, "target_level"


def promote(
    ctx: Context,
    node: dict,
    target: int,
    *,
    reason: str,
    source: str,
    activity_id: str,
    help_level: int,
    correct: bool,
    artifact: dict | None = None,
    assisted: bool = False,
) -> dict:
    """Raise one level at most, honouring gate_override and the per-turn cap."""
    index = ctx.index()
    cap, cap_reason = _cap_for(node, index)
    old = int(node.get("level", 0))
    wanted = min(int(target), cap)
    new = min(wanted, old + 1)
    if new <= old:
        if wanted > old:
            ctx.event(
                "level_cap",
                {
                    "node": node["id"],
                    "requested": int(target),
                    "current": old,
                    "cap": cap,
                    "reason": cap_reason if cap < int(target) else "single_turn_plus_one",
                },
                dedupe_key=f"level_cap:{ctx.plan.get('session_id')}:{node['id']}:{old}:{int(target)}",
            )
        return {"changed": False, "from": old, "to": old, "cap": cap}
    if int(target) > old + 1:
        ctx.event(
            "level_cap",
            {"node": node["id"], "requested": int(target), "current": old, "cap": old + 1, "reason": "single_turn_plus_one"},
            dedupe_key=f"level_cap:delta:{ctx.plan.get('session_id')}:{node['id']}:{old}:{int(target)}",
        )
    node["level"] = new
    node["level_source"] = source
    node["updated_at"] = clock.now_iso()
    evidence = {
        "event_id": None,
        "kind": "attempt",
        "activity_id": activity_id,
        "help_level": help_level,
        "correct": True,
        "source": source,
        "assisted": bool(assisted),
        "artifact": (artifact or {}).get("path"),
        "artifact_sha256": (artifact or {}).get("sha256"),
        "at": clock.now_iso(),
    }
    event = ctx.event(
        "level_up",
        {
            "node": node["id"],
            "from": old,
            "to": new,
            "reason": reason,
            "source": source,
            "assisted": bool(assisted),
            "activity_id": activity_id,
            "help_level": help_level,
            "artifact": evidence["artifact"],
            "artifact_sha256": evidence["artifact_sha256"],
        },
        dedupe_key=f"level_up:{ctx.plan.get('session_id')}:{activity_id}:{old}>{new}",
    )
    evidence["event_id"] = (event or {}).get("id")
    node.setdefault("evidence", []).append(evidence)
    ctx.mark("map")
    return {"changed": True, "from": old, "to": new, "cap": cap, "event": event}


def _add_misconception(ctx: Context, node: dict, label: str, stage: str) -> None:
    label = (label or "").strip()
    if not label:
        return
    entry = {"label": label, "stage": stage, "at": clock.now_iso()}
    node.setdefault("misconceptions", []).append(entry)
    ctx.mark("map")
    ctx.event(
        "misconception",
        {"node": node["id"], "label": label, "stage": stage},
        dedupe_key=f"misconception:{ctx.plan.get('session_id')}:{node['id']}:{sha256_text(label)[:10]}",
    )


def _advance_stage(ctx: Context) -> str | None:
    progress = ctx.plan.setdefault("stage_progress", {})
    stage = progress.get("stage")
    nxt = sm_model.next_stage(stage)
    if nxt:
        set_stage(ctx, nxt)
        return nxt
    return None


def _finish_node(ctx: Context, node: dict, stage: str, progress: dict) -> None:
    ctx.plan["current_node"] = None
    ctx.plan["stage"] = None
    ctx.plan["stage_progress"] = {}
    ctx.plan["mode"] = "stage"
    ctx.mark("plan")
    index = ctx.index()
    unlocked = [
        other["id"]
        for other in ctx.map["nodes"]
        if node["id"] in other.get("prereqs", []) and sm_model.prereqs_ready(other, index)
    ]
    for other_id in unlocked:
        ctx.event(
            "node_unlocked",
            {"node": other_id, "because": node["id"], "level": int(node.get("level", 0))},
            dedupe_key=f"node_unlocked:{other_id}:{node['id']}:{int(node.get('level', 0))}",
        )
    ctx.event(
        "node_completed",
        {"node": node["id"], "stage": stage, "level": int(node.get("level", 0)), "unlocked": unlocked},
        dedupe_key=f"node_completed:{ctx.plan.get('session_id')}:{node['id']}:{int(node.get('level', 0))}",
    )


def _stage_pass(
    ctx: Context, node: dict, stage: str, progress: dict, update: dict, answer_sha: str, *, assisted_carry: bool = False
) -> dict:
    result = {"passed": False, "level": None, "next_stage": None}
    help_level = int(update.get("help_level") or 0)
    activity = f"{node['id']}-{stage}"
    # After an assisted turn, a level claim may only reach L1 and is labelled as
    # assisted; apply/check cannot pass on a merely scaffolded answer at all.
    if assisted_carry and stage in ("apply", "check"):
        result["assisted_blocked"] = True
        return result
    if stage == "explain":
        result["passed"] = True
        promo = promote(
            ctx,
            node,
            1,
            reason="after_assisted" if assisted_carry else "explain_passed",
            source="assisted_carryover" if assisted_carry else "explain",
            activity_id=activity,
            help_level=help_level,
            correct=True,
            assisted=assisted_carry,
        )
        result["level"] = promo
    elif stage == "drill":
        progress["drill_streak"] = int(progress.get("drill_streak", 0)) + 1
        if progress["drill_streak"] >= 2:
            result["passed"] = True
    elif stage == "apply":
        artifact = _artifact(ctx, update.get("artifact"))
        if not artifact["exists"]:
            ctx.event(
                "artifact_missing",
                {"node": node["id"], "activity_id": activity, "artifact": update.get("artifact"), "error": artifact.get("error")},
                dedupe_key=f"artifact_missing:{ctx.plan.get('session_id')}:{activity}:{sha256_text(str(update.get('artifact')))}",
            )
            result["artifact_missing"] = True
            return result
        progress["apply_artifact"] = artifact["path"]
        progress["apply_correct"] = int(progress.get("apply_correct", 0)) + 1
        result["passed"] = True
        promo = promote(
            ctx,
            node,
            2,
            reason="apply_passed",
            source="verified",
            activity_id=activity,
            help_level=help_level,
            correct=True,
            artifact=artifact,
        )
        result["level"] = promo
        result["artifact"] = artifact
    elif stage == "check":
        progress["check_correct"] = int(progress.get("check_correct", 0)) + 1
        result["passed"] = True
        promo = promote(ctx, node, 3, reason="check_passed", source="check", activity_id=activity, help_level=help_level, correct=True)
        result["level"] = promo
        result["review"] = sm_model.schedule_after_check(node, ctx.today, interval_index=2)
        return result
    if result["passed"]:
        progress["passed"] = True
        ctx.mark("plan")
        ctx.event(
            "stage_passed",
            {
                "node": node["id"],
                "stage": stage,
                "activity_id": activity,
                "help_level": help_level,
                "answer_sha": answer_sha,
                "level": int(node.get("level", 0)),
            },
            dedupe_key=f"stage_passed:{ctx.plan.get('session_id')}:{activity}:{answer_sha}",
        )
    return result


_PASS_CLAIM_RE = re.compile(r"(通过|过关|答对|过了|做对)")
_NEG_PREFIX_RE = re.compile(r"(没|未|不|尚未|没有)$")


def claims_pass(text: str) -> bool:
    """True when a mentor reply verbally claims a pass (not a negation)."""
    text = (text or "").strip()
    if not text:
        return False
    for match in _PASS_CLAIM_RE.finditer(text):
        prefix = text[max(0, match.start() - 3) : match.start()].strip()
        if _NEG_PREFIX_RE.search(prefix):
            continue
        return True
    return False


def _verdict_conflict(ctx: Context, node: dict, stage: str, activity: str, turn, update: dict, outcome: Outcome) -> None:
    """A verbal pass without a matching correct attempt is a protocol conflict."""
    ctx.event(
        "mentor_verdict_conflict",
        {
            "node": node["id"],
            "stage": stage,
            "activity_id": activity,
            "claimed": "pass",
            "correct": (update.get("attempt") or {}).get("correct") if isinstance(update.get("attempt"), dict) else None,
            "help_level": update.get("help_level"),
            "raw_sha256": sha256_text(getattr(turn, "raw", "") or "")[:16],
        },
        dedupe_key=f"verdict_conflict:{ctx.plan.get('session_id')}:{activity}:{sha256_text(getattr(turn, 'raw', '') or '')[:10]}",
    )
    outcome.notes.append("导师说这一轮“过了”，但运行时没有记录到通过的证据；以状态为准，本轮不升级。")


def _stage_fail(ctx: Context, node: dict, stage: str, progress: dict, update: dict) -> dict:
    result = {"passed": False, "regressed": None}
    if stage == "drill":
        progress["drill_streak"] = 0
    elif stage == "apply":
        progress["apply_correct"] = int(progress.get("apply_correct", 0))
    elif stage == "explain":
        progress["explain_turns"] = int(progress.get("explain_turns", 0)) + 1
        if progress["explain_turns"] >= 4:
            index = ctx.index()
            unmet = sm_model.unmet_prereqs(node, index)
            target = None
            if unmet:
                target = min(unmet, key=lambda item: (index[item[0]]["cluster_index"], item[0]))[0]
            ctx.event(
                "prereq_gap",
                {"node": node["id"], "unmet": unmet, "fallback": target, "turns": progress["explain_turns"]},
                dedupe_key=f"prereq_gap:{ctx.plan.get('session_id')}:{node['id']}",
            )
            if target:
                set_stage(ctx, "explain")
                ctx.plan["current_node"] = target
                ctx.plan["stage"] = "explain"
                ctx.plan["stage_progress"] = sm_model.fresh_progress(target, "explain")
                ctx.mark("plan")
                result["regressed"] = target
    elif stage == "check":
        progress["check_correct"] = 0
        label = (update.get("misconception") or "").strip()
        if label:
            same = [item for item in node.get("misconceptions", []) if item.get("label") == label]
            # ``_apply_stage`` already appended this turn's label, so >= 2 means
            # the same error cause happened twice (design §5).
            if len(same) >= 2:
                review = node.setdefault("review", {})
                review["lapses"] = int(review.get("lapses", 0)) + 1
                ctx.mark("map")
                ctx.event(
                    "level_down",
                    {"node": node["id"], "from": int(node.get("level", 0)), "to": max(0, int(node.get("level", 0)) - 1), "reason": "same_misconception_twice", "lapses": review["lapses"]},
                    dedupe_key=f"decay:{ctx.plan.get('session_id')}:{node['id']}:{sha256_text(label)[:8]}",
                )
                node["level"] = max(0, int(node.get("level", 0)) - 1)
                node["level_source"] = "decayed"
        set_stage(ctx, "explain")
        result["regressed"] = node["id"]
        ctx.event(
            "stage_regressed",
            {"node": node["id"], "stage": "check", "to": "explain", "misconception": label},
            dedupe_key=f"stage_regressed:{ctx.plan.get('session_id')}:{node['id']}:{sha256_text(label)[:8]}",
        )
    return result


# ---------------------------------------------------------------------------
# turn processing
# ---------------------------------------------------------------------------
@dataclass
class Outcome:
    ok: bool = True
    exit_code: int = 0
    reply: str = ""
    record: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    evidence_applied: bool = False
    invalid: bool = False
    voided: bool = False
    node_completed: bool = False
    diagnosis_finished: bool = False


def process_turn(ctx: Context, text: str, turn, *, answer_sha: str | None = None) -> Outcome:
    """Validate one mentor turn and apply the direction's evidence rules."""
    ctx.plan["turn_index"] = int(ctx.plan.get("turn_index", 0)) + 1
    ctx.mark("plan")
    # Capture *before* processing: finishing a diagnosis or a stage changes the
    # current activity, and the turn must be labelled with the activity the
    # learner actually answered (off-by-one bug from round-03/04).
    mentor = ctx.mentor()
    activity = ctx.activity_id()
    outcome = Outcome(reply=sm_mentors.render_reply(turn.text, ctx.mode))
    if getattr(turn, "repaired", False):
        # Silent repair: log it for evidence, never surface it to the learner.
        ctx.event(
            "mentor_update_retried",
            {
                "session_id": ctx.plan.get("session_id"),
                "turn_index": int(ctx.plan.get("turn_index", 0)),
                "mentor": mentor,
                "reason": "missing learn-update block on first reply",
                "retries": 1,
            },
            dedupe_key=f"retried:{ctx.plan.get('session_id')}:{ctx.plan.get('turn_index')}",
        )
    answer_sha = answer_sha or sha256_text(text)[:16]

    ok, problems = validate_turn(ctx, turn)
    if not ok:
        outcome.ok = False
        outcome.invalid = True
        record_invalid(ctx, turn, problems, mentor)
        outcome.notes.append("导师这轮的记录格式不完整，本轮按“无证据”处理（细节已写入日志）。")
        if ctx.mode_name() == "diagnose":
            # A broken reply must not stall the diagnosis: the probe is consumed
            # as an answer, but it can only count as L0 (no evidence).
            applied = apply_probe_answer(ctx, text, None, force_answer=True)
            status = applied.get("status")
            outcome.evidence_applied = status in ("answered", "skipped")
            outcome.diagnosis_finished = ctx.diagnosis().get("status") != "pending"
            if applied.get("probe") and status in ("answered", "skipped"):
                probe = applied["probe"]
                outcome.record.append(f"诊断：第 {probe_index(ctx, probe['id'])} 题已记录（按 L0 起算）")
        _record_turn_event(ctx, text, turn, mentor, activity, outcome, updates=None)
        _update_help_profile(ctx, turn)
        return outcome

    update = turn.updates or {}
    help_level = int(update.get("help_level") or 0)

    # examiner must never help: the whole turn is voided, not silently adjusted.
    if mentor == "examiner" and help_level >= 1:
        outcome.ok = False
        outcome.voided = True
        ctx.event(
            "examiner_help_violation",
            {
                "mentor": "examiner",
                "help_level": help_level,
                "activity_id": activity,
                "raw_sha256": sha256_text(turn.raw or "")[:16],
            },
            dedupe_key=f"examiner_violation:{ctx.plan.get('session_id')}:{ctx.plan.get('turn_index')}",
        )
        outcome.notes.append(
            f"检查阶段必须零提示，本轮导师给了提示（提示等级 {help_level}）→ 这一轮作废，不计任何证据。"
        )
        _record_turn_event(ctx, text, turn, mentor, activity, outcome, updates=None)
        return outcome

    mode = ctx.mode_name()
    if mode == "diagnose":
        applied = apply_probe_answer(ctx, text, turn)
        status = applied.get("status")
        probe = applied.get("probe")
        outcome.evidence_applied = status in ("answered", "skipped")
        outcome.diagnosis_finished = ctx.diagnosis().get("status") != "pending"
        outcome.notes.extend(applied.get("notes") or [])
        if probe and status in ("answered", "skipped"):
            position = probe_index(ctx, probe["id"])
            if status == "skipped":
                outcome.record.append(f"诊断：第 {position} 题记为跳过（按 L0 起算）")
            else:
                outcome.record.append(f"诊断：第 {position} 题已记录（{probe['node']} 评为 L{probe['level_set']}）")
            if applied.get("level_set"):
                outcome.record.append(f"等级：{probe['node']} L0 → L{probe['level_set']}（诊断上限，最多 L1）")
        signal = diagnosis_end_signal(ctx, text, turn)
        if signal:
            finish_diagnosis_early(ctx, signal)
            outcome.diagnosis_finished = True
            outcome.record.append("诊断：按对话提前结束（已获得的等级与定位保留）")
            outcome.notes.append("诊断提前结束：没答的题不再追问，想补齐可再运行 `diagnose`。")
        _record_turn_event(ctx, text, turn, mentor, activity, outcome, updates=update)
        _update_help_profile(ctx, turn)
        return outcome

    if mode == "review":
        _apply_review(ctx, turn, update, outcome, answer_sha)
        _record_turn_event(ctx, text, turn, mentor, activity, outcome, updates=update)
        _update_help_profile(ctx, turn)
        return outcome

    _apply_stage(ctx, turn, update, outcome, answer_sha, text)
    _record_turn_event(ctx, text, turn, mentor, activity, outcome, updates=update)
    _update_help_profile(ctx, turn)
    return outcome


def _record_turn_event(ctx: Context, text: str, turn, mentor: str, activity: str, outcome: Outcome, updates: dict | None) -> None:
    update = updates or {}
    attempt = update.get("attempt") if isinstance(update.get("attempt"), dict) else {}
    ctx.event(
        "mentor_turn",
        {
            "session_id": ctx.plan.get("session_id"),
            "turn_index": int(ctx.plan.get("turn_index", 0)),
            "mentor": mentor,
            "activity_id": activity,
            "mode": ctx.mode_name(),
            "help_level": update.get("help_level"),
            "correct": attempt.get("correct"),
            "misconception": update.get("misconception"),
            "next": update.get("next"),
            "learner_text": text,
            "mentor_text": turn.text,
            "offline": ctx.mode == "mock",
            "repaired": bool(getattr(turn, "repaired", False)),
            "invalid": outcome.invalid,
            "voided": outcome.voided,
        },
        dedupe_key=f"say:{ctx.plan.get('session_id')}:{ctx.plan.get('turn_index')}",
    )


def _update_help_profile(ctx: Context, turn) -> None:
    profile = ctx.mem.setdefault("help_profile", {"avg_help_level": None, "independent_rate": None, "turns": 0, "trend": "flat"})
    turns = int(profile.get("turns") or 0) + 1
    level = None
    if turn.updates:
        level = turn.updates.get("help_level")
    if isinstance(level, int):
        previous = profile.get("avg_help_level")
        profile["avg_help_level"] = round(level if previous is None else (float(previous) * (turns - 1) + level) / turns, 3)
        independent = profile.get("independent_count")
        independent = int(independent or 0) + (1 if level == 0 else 0)
        profile["independent_count"] = independent
        profile["independent_rate"] = round(independent / turns, 3)
    profile["turns"] = turns
    ctx.mark("memory")


def _apply_stage(ctx: Context, turn, update: dict, outcome: Outcome, answer_sha: str, text: str = "") -> None:
    node = ctx.node()
    if node is None:
        outcome.notes.append("当前没有选中节点，本轮不应用证据。先运行 `start` 或 `next`。")
        return
    stage = ctx.plan.get("stage") or "explain"
    progress = ctx.plan.setdefault("stage_progress", sm_model.fresh_progress(node["id"], stage))
    attempt = update.get("attempt") if isinstance(update.get("attempt"), dict) else {}
    activity = attempt.get("activity_id") if attempt.get("activity_id") else f"{node['id']}-{stage}"
    resolved_node, resolved_stage = sm_model.parse_activity(activity)
    current_activity = f"{node['id']}-{stage}"

    if resolved_node is None or resolved_stage is None:
        ctx.event(
            "activity_mismatch",
            {"node": node["id"], "stage": stage, "activity_id": activity, "reason": "reserved_or_unknown_activity"},
            dedupe_key=f"activity_mismatch:{ctx.plan.get('session_id')}:{ctx.plan.get('turn_index')}",
        )
        outcome.notes.append("导师给的活动编号和当前阶段对不上，本轮只记录对话。")
        return

    if resolved_stage != stage:
        ctx.event(
            "stage_gate_violation",
            {"node": node["id"], "stage": stage, "activity_id": activity, "expected": current_activity},
            dedupe_key=f"stage_gate:{ctx.plan.get('session_id')}:{ctx.plan.get('turn_index')}",
        )
        outcome.ok = False
        outcome.exit_code = 2
        outcome.notes.append(
            f"跳过阶段被拒绝：现在是 {sm_model.stage_label(stage)}，提交的却是 {sm_model.stage_label(resolved_stage)}（{activity}）。\n"
            f"可以先做两件事：① 继续 {current_activity}；② 用 `switch {ctx.allowed_mentors()[-1]}` 换到本阶段允许的导师后重做。\n"
            "本轮不计入尝试记录。"
        )
        return

    if resolved_node != node["id"]:
        ctx.event(
            "activity_mismatch",
            {"node": node["id"], "stage": stage, "activity_id": activity},
            dedupe_key=f"activity_mismatch:{ctx.plan.get('session_id')}:{ctx.plan.get('turn_index')}",
        )
        outcome.notes.append("导师给的活动不属于当前节点，本轮只记录对话。")
        return

    misconception = (update.get("misconception") or "").strip()
    if misconception:
        _add_misconception(ctx, node, misconception, stage)
        outcome.record.append(f"错因：{misconception}")
    if update.get("next"):
        outcome.record.append(f"下一步：{update['next']}")

    correct = attempt.get("correct")
    help_level = int(update.get("help_level") or 0)
    if stage == "check" and correct is not True and claims_pass(getattr(turn, "text", "")):
        _verdict_conflict(ctx, node, stage, activity, turn, update, outcome)
    if correct is None:
        outcome.notes.append("本轮没有作答，只记录对话，不产生能力证据。")
        return

    # check is the one stage with a hard zero-help rule, whoever holds it.
    if stage == "check" and help_level >= 1:
        ctx.event(
            "check_help_violation",
            {"node": node["id"], "help_level": help_level, "activity_id": activity, "mentor": ctx.mentor()},
            dedupe_key=f"check_help_violation:{ctx.plan.get('session_id')}:{ctx.plan.get('turn_index')}",
        )
        outcome.notes.append(
            f"检查阶段必须零提示，本轮给了提示（提示等级 {help_level}）→ 本轮不计证据，也不升级。"
        )
        return

    # Writing templates: the submitted text *is* the artifact.  Save it rather
    # than spending another learner turn asking for a file (round-06).
    if stage == "apply" and correct is True and help_level <= 1 and not update.get("artifact") and ctx.template == "email":
        saved = ctx.p.autosave_artifact(text, node_id=node["id"], stage="apply")
        if saved:
            update = dict(update, artifact=saved)
            ctx.event(
                "artifact_autosaved",
                {"node": node["id"], "activity_id": activity, "artifact": saved, "reason": "writing artifact saved from the learner's message"},
                dedupe_key=f"artifact_autosaved:{ctx.plan.get('session_id')}:{activity}:{answer_sha}",
            )
            outcome.record.append(f"产物：已把本轮文本存为 {saved}")

    # An apply submission without a real artifact is not evidence at all: check it
    # before recording the attempt so the learner can retry after fixing the file.
    if stage == "apply" and correct is True and help_level <= 1:
        artifact = _artifact(ctx, update.get("artifact"))
        if not artifact["exists"]:
            ctx.event(
                "artifact_missing",
                {"node": node["id"], "activity_id": activity, "artifact": update.get("artifact"), "error": artifact.get("error")},
                dedupe_key=f"artifact_missing:{ctx.plan.get('session_id')}:{activity}:{sha256_text(str(update.get('artifact')))}",
            )
            hint = (
                "把这一版邮件存成 `artifacts/*.md` 或 `.txt`，下一轮说明文件路径即可"
                if ctx.template == "email"
                else "把可运行文件放进 `artifacts/`，下一轮说明文件路径即可"
            )
            outcome.notes.append(
                f"应用还没通过：没有找到可核验的产物。{hint}（本轮不计入尝试，可以原样重试）。"
            )
            return

    # A correct answer right after an assisted turn is still scaffolded: it may
    # only support L1 and is never presented as independent evidence.
    previous_help = ctx.previous_help_level(node["id"]) if (correct is True and help_level <= 1) else None
    assisted_carry = previous_help is not None and previous_help >= 2

    # idempotency: the same answer for the same activity in one session counts once
    dedupe = f"attempt:{ctx.plan.get('session_id')}:{activity}:{answer_sha}"
    attempt_event = ctx.event(
        "attempt",
        {
            "node": node["id"],
            "stage": stage,
            "activity_id": activity,
            "help_level": help_level,
            "correct": bool(correct),
            "assisted_context": assisted_carry,
            "answer_sha": answer_sha,
            "source": "observed",
        },
        dedupe_key=dedupe,
    )
    if attempt_event is None:
        outcome.notes.append("这个答案已经记录过，不会重复计数。")
        return
    outcome.evidence_applied = True
    if assisted_carry:
        ctx.event(
            "assisted_carryover",
            {
                "node": node["id"],
                "stage": stage,
                "activity_id": activity,
                "previous_help_level": previous_help,
                "capped_to": 1,
                "attempt_event": attempt_event.get("id"),
            },
            dedupe_key=f"assisted_carry:{attempt_event.get('id')}",
        )

    if correct is True and help_level >= 2:
        ctx.event(
            "assisted_completion",
            {
                "node": node["id"],
                "stage": stage,
                "activity_id": activity,
                "help_level": help_level,
                "cap": 1,
                "attempt_event": attempt_event.get("id"),
            },
            dedupe_key=f"assisted:{attempt_event.get('id')}",
        )
        outcome.record.append(f"受助完成：本轮提示等级 {help_level}，只记录接触过，不升级。")
        return

    if correct is True:
        result = _stage_pass(ctx, node, stage, progress, update, answer_sha, assisted_carry=assisted_carry)
        if result.get("artifact_missing"):
            outcome.notes.append("应用未通过：没有找到可核验的产物，本轮不计入通过。")
            return
        if result.get("assisted_blocked"):
            outcome.record.append("本轮是受助后的确认：不计为独立通过，阶段不前进。")
            outcome.notes.append("上一轮刚给过完整提示，这一次只算练习；下一轮同类题独立做对才算通过。")
            return
        if result["passed"]:
            outcome.record.append(f"阶段通过：{sm_model.stage_label(stage)}（{activity}）")
            promo = result.get("level")
            if promo and promo.get("changed"):
                label = "受助后，不计为独立" if assisted_carry else "独立通过"
                outcome.record.append(f"等级：{node['id']} L{promo['from']} → L{promo['to']}（{label}）")
            nxt = _advance_stage(ctx)
            if nxt is None and stage == "check":
                _finish_node(ctx, node, stage, progress)
                outcome.node_completed = True
        elif stage == "drill":
            outcome.record.append(f"drill 进度：连续正确 {progress.get('drill_streak', 0)}/2")
        return

    result = _stage_fail(ctx, node, stage, progress, update)
    outcome.record.append(f"本次未通过：{activity}")
    if result.get("regressed"):
        outcome.notes.append(f"退回 {result['regressed']} 的讲解（同一错因或先修缺口）。")


def _apply_review(ctx: Context, turn, update: dict, outcome: Outcome, answer_sha: str) -> None:
    node = ctx.node()
    if node is None:
        outcome.notes.append("复习队列为空，本轮不应用证据。")
        return
    attempt = update.get("attempt") if isinstance(update.get("attempt"), dict) else {}
    correct = attempt.get("correct")
    help_level = int(update.get("help_level") or 0)
    misconception = (update.get("misconception") or "").strip()
    if misconception:
        _add_misconception(ctx, node, misconception, "check")
        outcome.record.append(f"错因：{misconception}")
    if correct is not True and claims_pass(getattr(turn, "text", "")):
        _verdict_conflict(ctx, node, "check", "review", turn, update, outcome)
    if correct is None:
        outcome.notes.append("本轮没有作答，只记录对话。")
        return
    dedupe = f"attempt:{ctx.plan.get('session_id')}:review:{node['id']}:{answer_sha}"
    event = ctx.event(
        "attempt",
        {"node": node["id"], "stage": "review", "activity_id": "review", "help_level": help_level, "correct": bool(correct), "answer_sha": answer_sha, "source": "observed"},
        dedupe_key=dedupe,
    )
    if event is None:
        outcome.notes.append("这个答案已经记录过，不会重复计数。")
        return
    outcome.evidence_applied = True
    if correct is True and help_level == 0:
        info = sm_model.review_pass(node, ctx.today)
        last_upgrade = None
        for item in reversed(node.get("evidence") or []):
            if item.get("to") == 3 or item.get("source") == "check":
                last_upgrade = item.get("at")
                break
        retest = False
        if last_upgrade:
            try:
                retest = clock.days_between(last_upgrade, clock.now_iso()) >= 7
            except ValueError:
                retest = False
        ctx.event(
            "review_result",
            {"node": node["id"], "passed": True, "interval_index": info["interval_index"], "due": info["due"], "retest_confirmed": retest},
            dedupe_key=f"review:{ctx.plan.get('session_id')}:{node['id']}:{answer_sha}",
        )
        if retest:
            ctx.event("retest_confirmed", {"node": node["id"], "at": clock.now_iso()}, dedupe_key=f"retest:{node['id']}:{info['due']}")
        ctx.mark("map")
        outcome.record.append(f"review 通过：{node['id']} 间隔 +1 档 → 下次 {info['due']}（{info['interval_days']} 天）")
    else:
        old = int(node.get("level", 0))
        info = sm_model.review_fail(node, ctx.today)
        node["level"] = max(0, old - 1)
        node["level_source"] = "review_failed"
        node["updated_at"] = clock.now_iso()
        ctx.mark("map")
        ctx.event(
            "review_result",
            {"node": node["id"], "passed": False, "interval_index": info["interval_index"], "due": info["due"], "lapses": info["lapses"]},
            dedupe_key=f"review:{ctx.plan.get('session_id')}:{node['id']}:{answer_sha}",
        )
        ctx.event(
            "level_down",
            {"node": node["id"], "from": old, "to": node["level"], "reason": "review_failed", "lapses": info["lapses"], "at": clock.now_iso()},
            dedupe_key=f"level_down:review:{ctx.plan.get('session_id')}:{node['id']}",
        )
        outcome.record.append(f"review 失败：{node['id']} L{old} → L{node['level']}，间隔退到 {info['interval_days']} 天，lapses={info['lapses']}")

    queue = [item for item in (ctx.plan.get("review_queue") or []) if item != node["id"]]
    ctx.plan["review_queue"] = queue
    if queue:
        ctx.plan["current_node"] = queue[0]
        ctx.plan["stage"] = "check"
        ctx.plan["stage_progress"] = sm_model.fresh_progress(queue[0], "check")
        ctx.mark("plan")
    else:
        ctx.plan["mode"] = "stage"
        ctx.plan["current_node"] = None
        ctx.plan["stage"] = None
        ctx.plan["stage_progress"] = {}
        ctx.plan["mentor_override"] = None
        ctx.mark("plan")
        outcome.node_completed = False


# ---------------------------------------------------------------------------
# handoff
# ---------------------------------------------------------------------------
def build_handoff(
    ctx: Context,
    *,
    from_mentor: str,
    to_mentor: str,
    reason: str,
    what_tried: list[str] | None = None,
    unresolved: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> dict:
    node = ctx.node()
    progress = ctx.plan.get("stage_progress") or {}
    tried = list(what_tried or [])
    if not tried:
        session_turns = sum(
            1
            for event in ctx.journal.of_kind("mentor_turn")
            if (event.get("payload") or {}).get("session_id") == ctx.plan.get("session_id")
        )
        if node:
            stage = ctx.plan.get("stage") or "explain"
            tried.append(
                f"本会话 {session_turns} 轮对话，停在 {node['id']} 的 {sm_model.stage_label(stage)}（{node['id']}-{stage}）"
            )
            if progress.get("drill_streak"):
                tried.append(f"drill 连续正确 {progress['drill_streak']}/2")
            if progress.get("apply_artifact"):
                tried.append(f"apply 产物 {progress['apply_artifact']}")
        elif session_turns:
            tried.append(f"本会话 {session_turns} 轮对话（诊断阶段）")
        if ctx.diagnosis().get("status") == "pending":
            done = sum(1 for p in ctx.diagnosis().get("probes") or [] if p.get("status") in ("done", "skipped"))
            total = len(ctx.diagnosis().get("probes") or []) or sm_model.total_probes(ctx.template)
            tried.append(f"诊断已完成 {done}/{total} 题")

    pending: list[str] = []
    for item in (unresolved if unresolved is not None else []):
        if item not in pending:
            pending.append(item)
    if unresolved is None:
        if ctx.diagnosis().get("status") == "pending":
            probe = ctx.current_probe()
            if probe:
                pending.append(f"诊断探针 {probe['id']}（锚点 {probe['node']}）还没回答")
        if node:
            seen_labels: set[str] = set()
            for item in (node.get("misconceptions") or [])[-4:]:
                label = item.get("label")
                if label in seen_labels:
                    continue
                seen_labels.add(label)
                pending.append(f"{node['id']} 未澄清的错因：{label}")
            if progress and not progress.get("passed"):
                note = f"{node['id']} 的 {sm_model.stage_label(ctx.plan.get('stage') or 'explain')} 阶段未收口"
                if note not in pending:
                    pending.append(note)
        if not pending:
            pending.append("无未决问题")

    steps = list(next_steps or [])
    if not steps:
        steps.append(next_action(ctx))

    return {
        "from": from_mentor,
        "to": to_mentor,
        "reason": reason,
        "at": clock.now_iso(),
        "slug": ctx.pj.get("slug"),
        "template": ctx.template,
        "node": node["id"] if node else None,
        "stage": ctx.plan.get("stage"),
        "activity_id": ctx.activity_id() if node else None,
        "what_tried": tried,
        "unresolved": pending,
        "next": steps,
        "context_digest": f"{ctx.pj.get('goal')} · L 分布 {sm_model.level_counts(ctx.map)}",
    }


def write_switch_handoff(ctx: Context, to_mentor: str, reason: str) -> dict:
    from_mentor = ctx.mentor()
    handoff = build_handoff(ctx, from_mentor=from_mentor, to_mentor=to_mentor, reason=reason)
    ctx.plan["last_handoff"] = handoff
    ctx.plan["mentor_override"] = to_mentor
    ctx.plan["next_mentor"] = to_mentor
    ctx.mark("plan")
    event = ctx.event(
        "handoff",
        dict(handoff, trigger="switch"),
        dedupe_key=f"handoff:switch:{ctx.plan.get('session_id')}:{from_mentor}->{to_mentor}:{ctx.plan.get('turn_index')}",
    )
    if event is not None:
        ctx.p.write_handoff(handoff)
    return {"handoff": handoff, "event": event}


def write_pause_handoff(ctx: Context, note: str = "") -> dict:
    from_mentor = ctx.mentor()
    # Single authority: whoever would take the next turn, not a fresh `next`
    # decision that ignores the current node/stage and any on-demand override.
    to_mentor = ctx.next_mentor()
    reason = "会话结束（pause）" + (f"：{note}" if note else "")
    handoff = build_handoff(ctx, from_mentor=from_mentor, to_mentor=to_mentor, reason=reason)
    ctx.plan["last_handoff"] = handoff
    ctx.plan["next_mentor"] = to_mentor
    ctx.mark("plan")
    key = f"pause:{ctx.plan.get('session_id')}:{handoff.get('node')}:{handoff.get('stage')}"
    event = ctx.event("handoff", dict(handoff, trigger="pause"), dedupe_key=key)
    if event is not None:
        ctx.p.write_handoff(handoff)
    return {"handoff": handoff, "event": event, "duplicate": event is None}


def next_action(ctx: Context) -> str:
    if ctx.diagnosis().get("status") == "pending":
        probe = ctx.current_probe()
        if probe:
            return f"回答诊断探针 {probe['id']}（锚点 {probe['node']}）；不会就回“不知道”"
        return "运行 `start` 继续诊断"
    node = ctx.node()
    if node:
        stage = ctx.plan.get("stage") or "explain"
        return f"继续 {node['id']} 的 {sm_model.stage_label(stage)}（{node['id']}-{stage}），约 {ctx.activity_estimate()} 分钟"
    due = sm_model.due_nodes(ctx.map, ctx.today)
    if due:
        return f"运行 `review`：{len(due)} 个节点到期（先做 {due[0]['id']}）"
    decision = sm_model.next_decision(ctx.map, ctx.plan, ctx.today, ctx.minutes(), estimated_minutes=ctx.activity_estimate())
    selected = decision.get("selected")
    if selected:
        return f"运行 `start`：下一个是 {selected['node']} 的 {sm_model.stage_label(selected['stage'])}（{selected['activity_id']}）"
    return "地图上没有可推进的节点：先跑 `review`，或检查先修等级"
