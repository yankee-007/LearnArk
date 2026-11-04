"""Evidence rules, plan-authority enforcement, and private-notes upkeep.

Mentors never write mastery.  They emit a machine block; this module decides
what (if anything) becomes evidence.  The rules are intentionally small and
checkable (v0.2.2):

* self-report        -> recorded, never raises a level
* any non-examiner attempt -> ``practice_attempt`` + observed evidence only;
                        ``correct`` is stored as ``null`` and **never** raises a level
* coach/concept hl>=2 -> assisted, level unchanged
* examiner pass (hl=0, correct)   -> verified, +1 level (cap 4)
* examiner fail      -> -1 level with a reason and timestamp
* artifact paths are checked; missing files are marked 未核验, not referenced
"""

from __future__ import annotations

import re

from learncore import clock
from learncore.fsutil import atomic_write_text, sha256_text
from learncore.mentor import validate_updates

from . import SCHEMA_VERSION
from .const import HINT_KEYWORDS, LEVEL_LABELS, MAX_LEVEL, MENTORS, PLAN_OPS, REVIEW_EVERY
from .handoff import text_hash
from .planning import (
    advance_step,
    apply_plan_change,
    next_step,
    node_for,
    plan_hash,
    refresh_objective,
    validate_plan_change,
)

REVIEW_KINDS = ("recap", "decay_check", "transfer", "next_week")


# -- update block validation ---------------------------------------------
def validate_update(update: dict, mentor: str) -> list[str]:
    problems = list(validate_updates(update))
    help_level = update.get("help_level")
    if not isinstance(help_level, int) or not 0 <= help_level <= 3:
        problems.append("help_level is required (int 0..3)")
    attempt = update.get("attempt")
    if not isinstance(attempt, dict):
        problems.append("attempt must be an object")
    else:
        activity = attempt.get("activity_id")
        if activity is not None and not isinstance(activity, str):
            problems.append("attempt.activity_id must be a string or null")
        correct = attempt.get("correct")
        if correct is not None and not isinstance(correct, bool):
            problems.append("attempt.correct must be true/false/null")
    delta = update.get("mastery_delta", 0)
    if not isinstance(delta, int) or not 0 <= delta <= 1:
        problems.append("mastery_delta must be 0 or 1")
    plan_change = update.get("plan_change")
    if plan_change is not None and not isinstance(plan_change, dict):
        problems.append("plan_change must be an object")
    verdict = update.get("verdict")
    if verdict is not None:
        # A role violation (e.g. coach issuing verdicts) is a *runtime incident*,
        # not a malformed block: the block is still parsed, the field is dropped.
        problems.extend(_validate_verdict(verdict))
    review_note = update.get("review_note")
    if review_note is not None:
        problems.extend(_validate_review_note(review_note))
    handoff = update.get("handoff")
    if handoff is not None and not isinstance(handoff, dict):
        problems.append("handoff proposal must be an object")
    for field in ("do_not_redo",):
        value = update.get(field)
        if value is not None and (
            not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            problems.append("do_not_redo must be a list of non-empty strings")
    analogy = update.get("analogy")
    if analogy is not None and (not isinstance(analogy, str) or len(analogy) > 80):
        problems.append("analogy must be a short string (<=80 chars)")
    artifact = update.get("artifact")
    if artifact is not None and (not isinstance(artifact, str) or not artifact.strip()):
        problems.append("artifact must be a non-empty relative path string")
    return problems


def _validate_verdict(verdict: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(verdict, dict):
        return ["verdict must be an object"]
    if not isinstance(verdict.get("activity_id"), str) or not verdict["activity_id"].strip():
        problems.append("verdict.activity_id is required")
    if verdict.get("result") not in ("pass", "fail", "pending"):
        problems.append("verdict.result must be pass|fail|pending")
    basis = verdict.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        problems.append("verdict.basis must quote the learner verbatim (or '未作答')")
    rubric = verdict.get("rubric")
    if rubric is not None:
        if not isinstance(rubric, dict):
            problems.append("verdict.rubric must be an object")
        else:
            maximum = rubric.get("max")
            for key, value in rubric.items():
                if key == "max":
                    if not isinstance(value, int) or value <= 0:
                        problems.append("verdict.rubric.max must be a positive int")
                    continue
                if not isinstance(value, int) or value < 0:
                    problems.append(f"verdict.rubric.{key} must be a non-negative int")
                elif isinstance(maximum, int) and value > maximum:
                    problems.append(f"verdict.rubric.{key} exceeds max")
    return problems


def _validate_review_note(note: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(note, dict):
        return ["review_note must be an object"]
    if not isinstance(note.get("topic_id"), str) or not note["topic_id"].strip():
        problems.append("review_note.topic_id is required")
    if note.get("kind") not in REVIEW_KINDS:
        problems.append("review_note.kind must be one of " + ", ".join(REVIEW_KINDS))
    for field in ("evidence", "gap", "suggest"):
        if not isinstance(note.get(field), str) or not note[field].strip():
            problems.append(f"review_note.{field} is required")
    if note.get("confidence") not in ("observed", "inferred"):
        problems.append("review_note.confidence must be observed|inferred")
    return problems


# -- capability ------------------------------------------------------------
def ensure_node(capability: dict, node_id: str, label: str) -> dict:
    for node in capability.setdefault("nodes", []):
        if node.get("id") == node_id:
            if label and not node.get("label"):
                node["label"] = label
            return node
    node = {
        "id": node_id,
        "label": label or node_id,
        "level": 0,
        "evidence": [],
        "last_fail": None,
        "review_due": None,
        "decay_reason": None,
        "updated_at": clock.now_iso(),
    }
    capability["nodes"].append(node)
    return node


def record_evidence(
    node: dict,
    *,
    source: str,
    help_level: int | None,
    event_id: str,
    artifact: str | None,
    synthetic: bool,
    counts_for_level: bool,
    artifact_verified: bool = False,
    correct_claimed=None,
    conflict: bool = False,
) -> dict:
    entry = {
        "event_id": event_id,
        "source": source,
        "help_level": help_level,
        "artifact": artifact,
        "artifact_verified": bool(artifact_verified),
        "at": clock.now_iso(),
        "synthetic": bool(synthetic),
        "counts_for_level": bool(counts_for_level),
    }
    if correct_claimed is not None:
        entry["correct_claimed"] = correct_claimed
    if conflict:
        entry["conflict"] = True
    node.setdefault("evidence", []).append(entry)
    node["updated_at"] = entry["at"]
    return entry


def _artifact(paths, activity: str | None, declared: str | None = None) -> tuple[str | None, str | None]:
    """Return ``(existing_relative_path, expected_relative_path)``.

    Evidence must never point at a file that does not exist.  When the expected
    artifact is absent we return ``(None, expected)`` so the caller can record
    ``evidence_artifact_missing`` and mark the entry 未核验.
    """
    candidates: list[str] = []
    if isinstance(declared, str) and declared.strip():
        candidates.append(declared.strip().replace("\\", "/"))
    if activity:
        candidates.append(f"artifacts/{activity}.md")
    expected = candidates[0] if candidates else None
    for candidate in candidates:
        if (paths.root / candidate).is_file():
            return candidate, None
    return None, expected


def _artifact_event(activity: str | None, expected: str | None, node_id: str | None, event_id: str) -> dict | None:
    if not expected:
        return None
    return {
        "kind": "evidence_artifact_missing",
        "payload": {
            "activity_id": activity,
            "node_id": node_id,
            "expected": expected,
            "event_id": event_id,
            "detail": "产物不存在，证据标记为未核验",
        },
    }


def close_open_loops_on_pass(studio: dict, node_id: str | None, activity: str | None, event_id: str) -> list[dict]:
    """A verified milestone closes stale open loops that point at it."""
    events: list[dict] = []
    tokens = [token for token in (node_id, activity) if token]
    for mentor in MENTORS:
        for loop in (studio.get("mentors", {}).get(mentor, {}) or {}).get("open_loops", []):
            if loop.get("status", "open") == "closed":
                continue
            text = str(loop.get("text") or "")
            if tokens and any(token in text for token in tokens):
                loop["status"] = "closed"
                loop["closed_at"] = clock.now_iso()
                loop["closed_by_event"] = event_id
                events.append(
                    {
                        "kind": "open_loop_closed",
                        "payload": {"open_loop": loop.get("id"), "node_id": node_id, "activity_id": activity, "event_id": event_id},
                    }
                )
    return events


def apply_evidence(
    *,
    paths,
    project: dict,
    plan: dict,
    studio: dict,
    capability: dict,
    mentor: str,
    update: dict,
    turn_event_id: str,
    learner_text: str,
    mode: str,
    verdict_conflict: bool = False,
) -> dict:
    """Apply one turn's evidence.  Returns a summary + event specs."""
    synthetic = mode == "mock"
    help_level = int(update.get("help_level") or 0)
    attempt = update.get("attempt") or {}
    activity = attempt.get("activity_id") or None
    correct = attempt.get("correct")
    declared_artifact = update.get("artifact") if isinstance(update.get("artifact"), str) else None
    events: list[dict] = []
    summary: dict = {"upgraded": [], "violations": [], "exam": None, "assisted": False}

    node_id, label = node_for(project, plan, activity) if activity else (None, None)
    artifact, expected_artifact = _artifact(paths, activity, declared_artifact)
    if mentor != "examiner" and expected_artifact and not artifact:
        missing = _artifact_event(activity, expected_artifact, node_id, turn_event_id)
        if missing:
            events.append(missing)

    # --- examiner session -------------------------------------------------
    if mentor == "examiner":
        if help_level > 0:
            events.append(
                {
                    "kind": "examiner_help_violation",
                    "payload": {
                        "mentor": mentor,
                        "help_level": help_level,
                        "activity_id": activity,
                        "discarded_verdict": bool(update.get("verdict")),
                    },
                }
            )
            events.append(
                {
                    "kind": "authority_violation",
                    "payload": {
                        "kind": "examiner_help",
                        "mentor": mentor,
                        "detail": "examiner turn offered help; verdict discarded",
                        "requested_help_level": help_level,
                    },
                }
            )
            summary["violations"].append("examiner_help")
            if capability.get("pending_exam"):
                capability["pending_exam"]["status"] = "reask"
            studio.setdefault("flags", {})["exam_reask"] = True
            return {"events": events, "summary": summary}

        verdict = update.get("verdict")
        if not isinstance(verdict, dict):
            if activity:
                events.append(
                    {
                        "kind": "exam",
                        "payload": {
                            "task_id": activity,
                            "criteria": (plan.get("current_objective") or {}).get("success_criteria", []),
                            "verdict": "insufficient_evidence",
                            "evidence_event_ids": [],
                            "mentor": mentor,
                            "activity_id": activity,
                        },
                    }
                )
            return {"events": events, "summary": summary}

        result = verdict.get("result")
        task_id = verdict.get("activity_id")
        criteria = (plan.get("current_objective") or {}).get("success_criteria", [])
        exam_event = {
            "kind": "exam",
            "payload": {
                "task_id": task_id,
                "activity_id": activity or task_id,
                "criteria": criteria,
                "verdict": result,
                "basis": verdict.get("basis"),
                "rubric": verdict.get("rubric"),
                "help_level": help_level,
                "mentor": mentor,
                "evidence_event_ids": [turn_event_id],
                "synthetic": synthetic,
            },
        }

        if result == "pass":
            if correct is not True:
                exam_event["payload"]["verdict"] = "insufficient_evidence"
                events.append(exam_event)
                events.append(
                    {
                        "kind": "authority_violation",
                        "payload": {
                            "kind": "verdict_without_correct_attempt",
                            "mentor": mentor,
                            "detail": "pass requires attempt.correct=true",
                        },
                    }
                )
                summary["violations"].append("verdict_without_correct_attempt")
                return {"events": events, "summary": summary}
            if not node_id:
                node_id, label = "general", "当前目标"
            if not artifact:
                artifact = _exam_artifact(paths, activity or task_id, learner_text, update, verdict)
                expected_artifact = None
            node = ensure_node(capability, node_id, label)
            before = int(node.get("level") or 0)
            verified_count = sum(
                1 for entry in node.get("evidence", []) if entry.get("source") == "verified" and entry.get("counts_for_level")
            )
            ceiling = 5 if verified_count >= 1 else 4
            after = min(max(before + 1, 4), ceiling)
            if after > before:
                record_evidence(
                    node,
                    source="verified",
                    help_level=help_level,
                    event_id=turn_event_id,
                    artifact=artifact,
                    artifact_verified=bool(artifact),
                    synthetic=synthetic,
                    counts_for_level=True,
                )
                node["level"] = after
                node["last_verified_at"] = clock.now_iso()
                summary["upgraded"].append({"node": node_id, "from": before, "to": after, "source": "verified"})
                events.append(
                    {
                        "kind": "capability_upgrade",
                        "payload": {
                            "node": node_id,
                            "from": before,
                            "to": after,
                            "source": "verified",
                            "event_ids": [turn_event_id],
                            "synthetic": synthetic,
                        },
                    }
                )
                step_change = advance_step(plan, _step_id_for(plan, activity), event_id=turn_event_id, verified=True)
                if step_change:
                    events.append({"kind": "step_advanced", "payload": step_change})
            progress = _exam_progress(capability, task_id, "pass", turn_event_id)
            if progress:
                events.append(progress)
            closed = close_open_loops_on_pass(studio, node_id, activity or task_id, turn_event_id)
            events.extend(closed)
            exam_event["payload"]["node_id"] = node_id
            exam_event["payload"]["artifact"] = artifact
            exam_event["payload"]["artifact_verified"] = bool(artifact)
            events.append(exam_event)
            return {"events": events, "summary": summary}

        if result == "fail":
            if not artifact:
                artifact = _exam_artifact(paths, activity or task_id, learner_text, update, verdict)
                expected_artifact = None
            if node_id:
                node = ensure_node(capability, node_id, label)
                before = int(node.get("level") or 0)
                record_evidence(
                    node,
                    source="verified",
                    help_level=help_level,
                    event_id=turn_event_id,
                    artifact=artifact,
                    artifact_verified=bool(artifact),
                    synthetic=synthetic,
                    counts_for_level=False,
                )
                node["last_fail"] = {"misconception": update.get("misconception") or "复测未通过", "at": clock.now_iso()}
                node["review_due"] = clock.add_days(clock.now_iso(), 2)
                after = max(before - 1, 0)
                if after < before:
                    node["level"] = after
                    node["decay_reason"] = "examiner 复测失败：" + str(update.get("misconception") or "未说明")
                    summary["upgraded"].append({"node": node_id, "from": before, "to": after, "source": "verified_fail"})
                    events.append(
                        {
                            "kind": "capability_decay",
                            "payload": {
                                "node": node_id,
                                "from": before,
                                "to": after,
                                "reason": node["decay_reason"],
                                "at": clock.now_iso(),
                                "synthetic": synthetic,
                            },
                        }
                    )
                advance_step(plan, _step_id_for(plan, activity), event_id=turn_event_id, verified=False)
            progress = _exam_progress(capability, task_id, "fail", turn_event_id)
            if progress:
                events.append(progress)
            exam_event["payload"]["node_id"] = node_id
            exam_event["payload"]["artifact"] = artifact
            exam_event["payload"]["artifact_verified"] = bool(artifact)
            events.append(exam_event)
            return {"events": events, "summary": summary}

        # pending: the learner did not answer; keep the exam queue open
        pending = capability.get("pending_exam") or {}
        if pending:
            pending["status"] = "pending"
            pending["activity_id"] = pending.get("activity_id") or activity
        else:
            capability["pending_exam"] = {
                "node_id": node_id or "general",
                "requested_by": mentor,
                "status": "pending",
                "activity_id": activity,
                "questions": [activity or "exam-q1"],
                "remaining_questions": [activity or "exam-q1"],
                "answered": [],
                "current_index": 0,
                "total": 1,
                "at": clock.now_iso(),
            }
        exam_event["payload"]["node_id"] = node_id
        events.append(exam_event)
        return {"events": events, "summary": summary}

    # --- all other mentors -------------------------------------------------
    if update.get("verdict") is not None:
        events.append(
            {
                "kind": "authority_violation",
                "payload": {
                    "kind": "verdict_outside_examiner",
                    "mentor": mentor,
                    "detail": "only examiner sessions may issue verdicts",
                },
            }
        )
        summary["violations"].append("verdict_outside_examiner")
    if update.get("review_note") is not None and mentor != "reviewer":
        events.append(
            {
                "kind": "authority_violation",
                "payload": {
                    "kind": "review_note_outside_reviewer",
                    "mentor": mentor,
                    "detail": "only reviewer sessions may issue review_note",
                },
            }
        )
        summary["violations"].append("review_note_outside_reviewer")
    if int(update.get("mastery_delta") or 0) > 0:
        events.append(
            {
                "kind": "authority_violation",
                "payload": {
                    "kind": "mastery_delta_requested",
                    "mentor": mentor,
                    "detail": "mentor text cannot set mastery; runtime decides from evidence",
                    "requested_delta": int(update.get("mastery_delta") or 0),
                },
            }
        )
        summary["violations"].append("mastery_delta_requested")

    # --- practice-facing mentors: attempts are observations, never levels ----
    if activity:
        node = ensure_node(capability, node_id, label)
        events.append(
            {
                "kind": "practice_attempt",
                "payload": {
                    "mentor": mentor,
                    "activity_id": activity,
                    "correct": None,
                    "claimed_correct": correct,
                    "conflict": bool(verdict_conflict),
                    "help_level": help_level,
                    "node_id": node_id,
                    "synthetic": synthetic,
                },
            }
        )
        _remember_activity(studio, mentor, activity, None, help_level)
        record_evidence(
            node,
            source="observed",
            help_level=help_level,
            event_id=turn_event_id,
            artifact=artifact,
            artifact_verified=bool(artifact),
            synthetic=synthetic,
            counts_for_level=False,
            correct_claimed=correct,
            conflict=bool(verdict_conflict),
        )
        if verdict_conflict:
            node["last_fail"] = {
                "misconception": update.get("misconception") or "导师判定与正文纠正冲突",
                "at": clock.now_iso(),
                "source_event": turn_event_id,
                "source": "mentor_verdict_conflict",
            }
            node["review_due"] = clock.add_days(clock.now_iso(), 2)
        elif correct is False:
            node["last_fail"] = {
                "misconception": update.get("misconception") or "尝试未通过",
                "at": clock.now_iso(),
                "source_event": turn_event_id,
                "source": "practice_attempt",
            }
            node["review_due"] = clock.add_days(clock.now_iso(), 2)
        advance_step(plan, _step_id_for(plan, activity), event_id=turn_event_id, verified=False)
        summary["practice"] = True
        if help_level >= 2:
            events.append(
                {
                    "kind": "assisted",
                    "payload": {
                        "mentor": mentor,
                        "activity_id": activity,
                        "help_level": help_level,
                        "node_id": node_id,
                        "synthetic": synthetic,
                    },
                }
            )
            summary["assisted"] = True
        return {"events": events, "summary": summary}

    # No attempt: a learner claim is recorded as self-report, never as mastery.
    if detect_self_report(learner_text):
        capability.setdefault("self_reports", []).append(
            {"text": learner_text[:200], "at": clock.now_iso(), "event_id": turn_event_id, "synthetic": synthetic}
        )
        if node_id:
            node = ensure_node(capability, node_id, label)
            record_evidence(
                node,
                source="self_report",
                help_level=help_level,
                event_id=turn_event_id,
                artifact=None,
                synthetic=synthetic,
                counts_for_level=False,
            )
        events.append(
            {
                "kind": "self_report",
                "payload": {"mentor": mentor, "text": learner_text[:120], "synthetic": synthetic},
            }
        )
    return {"events": events, "summary": summary}


def detect_self_report(text: str) -> bool:
    markers = ("我做过", "我学过", "我会", "我用过", "我了解", "我接触过", "我之前", "我做过 RAG")
    return any(marker in (text or "") for marker in markers)


SKILL_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("w3-memory", ("记忆", "rag", "检索", "向量库", "遗忘", "跨会话", "长期")),
    ("w2-tools", ("参数", "重试", "幂等", "schema", "校验", "错误分层", "工具调用", "工具返回")),
    ("w4-eval", ("评测", "用例", "回放", "rubric", "指标", "护栏")),
    ("w1-agent-loop", ("循环", "终止", "停止条件", "再决策", "四要素", "观察", "工具结果", "用户消息")),
)

CORRECTION_MARKERS = (
    "不是",
    "而是",
    "纠正",
    "误解",
    "错误",
    "不准确",
    "需要改",
    "改成",
    "改宽",
    "补一句",
    "但",
    "不过",
    "缺",
    "区别",
    "不能",
    "更准确",
    "不知道",
    "混淆",
    "不等于",
    "当成",
    "其实",
)
PRAISE_MARKERS = ("都在点上", "抓住", "不错", "很好", "正确", "基本对", "说对了", "答对", "对，", "对。")

MISCONCEPTION_MARKERS = (
    "误解",
    "理解错",
    "混淆",
    "不准确",
    "错在",
    "纠正",
    "需要改",
    "需要纠正",
    "你把",
    "你写成",
    "你把它",
    "当成",
    "不等于",
    "不知道",
    "区别是",
    "其实是",
    "不对",
    "错了",
    "写错",
    "理解成",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    low = (text or "").lower()
    return any(marker.lower() in low for marker in markers)


def detect_verdict_conflict(text: str, update: dict, mentor: str) -> bool:
    """A mentor claiming correct while its own prose corrects the answer."""
    if mentor == "examiner":
        return False
    attempt = update.get("attempt") or {}
    if attempt.get("correct") is not True:
        return False
    return _contains_any(text, PRAISE_MARKERS) and _contains_any(text, CORRECTION_MARKERS)


LEARNER_ATTRIBUTION = (
    "你说",
    "你写",
    "你刚才",
    "你的回答",
    "你把它",
    "你把",
    "你这里",
    "这句",
    "你说的",
    "你上次说",
    "你当时说",
)


def extract_misconceptions(update: dict, text: str, mentor: str = "") -> list[tuple[str, str]]:
    """Only learner-attributed corrections (or planner diagnosis) become weaknesses."""
    items: list[tuple[str, str]] = []
    activity = (update.get("attempt") or {}).get("activity_id")
    attributed = _contains_any(text, LEARNER_ATTRIBUTION)
    planner_diagnosis = mentor == "planner" and _contains_any(text, ("误解", "需要纠正", "需要先讲清"))
    declared = update.get("misconception")
    if isinstance(declared, str) and declared.strip() and (activity or attributed or planner_diagnosis):
        items.append((declared.strip()[:200], "mentor_correction"))
    for sentence in re.split(r"[。！？!?\n]", text or ""):
        sentence = sentence.strip()
        if not sentence or len(sentence) < 6:
            continue
        skill_hits = [k for _, words in SKILL_KEYWORDS for k in words if k in sentence]
        if not skill_hits:
            continue
        if planner_diagnosis and _contains_any(sentence, ("误解", "错误", "需要纠正")):
            items.append((sentence[:200], "mentor_correction"))
        elif _contains_any(sentence, LEARNER_ATTRIBUTION) and _contains_any(sentence, MISCONCEPTION_MARKERS):
            items.append((sentence[:200], "mentor_correction"))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for sentence, source in items:
        key = text_hash(sentence)
        if key in seen:
            continue
        seen.add(key)
        unique.append((sentence, source))
    return unique[:2]


def skill_node_for(project: dict, plan: dict, activity: str | None, text: str) -> tuple[str, str]:
    module_ids = {module.get("module_id") for module in project.get("template_modules", [])}
    low = (text or "").lower()
    for module_id, keywords in SKILL_KEYWORDS:
        if module_id in module_ids and any(keyword in low for keyword in keywords):
            module = next((item for item in project["template_modules"] if item.get("module_id") == module_id), {})
            return module_id, module.get("title") or module_id
    return node_for(project, plan, activity)


def record_misconceptions(
    project: dict,
    plan: dict,
    capability: dict,
    mentor: str,
    update: dict,
    text: str,
    event_id: str,
) -> tuple[list[dict], list[dict]]:
    """Persist observed misconceptions as weaknesses with a source event."""
    events: list[dict] = []
    nodes: list[dict] = []
    for sentence, source in extract_misconceptions(update, text, mentor):
        node_id, label = skill_node_for(project, plan, (update.get("attempt") or {}).get("activity_id"), sentence)
        node = ensure_node(capability, node_id, label)
        node.setdefault("misconceptions", [])
        if any(text_hash(item.get("text", "")) == text_hash(sentence) for item in node["misconceptions"]):
            continue
        node["misconceptions"].append(
            {"text": sentence, "at": clock.now_iso(), "event_id": event_id, "mentor": mentor, "source": source}
        )
        node["misconceptions"] = node["misconceptions"][-10:]
        node["last_fail"] = {
            "misconception": sentence,
            "at": clock.now_iso(),
            "source_event": event_id,
            "source": source,
            "mentor": mentor,
        }
        node["review_due"] = clock.add_days(clock.now_iso(), 2)
        events.append(
            {
                "kind": "misconception_observed",
                "payload": {
                    "node": node_id,
                    "label": label,
                    "misconception": sentence,
                    "source": source,
                    "mentor": mentor,
                    "event_id": event_id,
                },
            }
        )
        nodes.append(node)
    return events, nodes


EXAM_DIRECT_MARKERS = ("独立题", "独立验证", "考一次", "考核", "考试", "检验一下")


def detect_exam_request(text: str, update: dict) -> bool:
    hay = (text or "") + " " + str(update.get("next") or "")
    if any(marker in hay for marker in EXAM_DIRECT_MARKERS):
        return True
    low = hay.lower()
    start = 0
    while True:
        index = low.find("examiner", start)
        if index < 0:
            return False
        window = hay[max(0, index - 12) : index + len("examiner") + 12]
        if any(word in window for word in ("等", "由", "找", "让", "请", "交给")):
            return True
        start = index + 1


def diagnosis_handoff_target(text: str, update: dict) -> str:
    hay = (text or "") + " " + str(update.get("next") or "")
    if any(word in hay for word in ("coach", "练习", "动手", "调试")):
        return "coach"
    if any(word in hay for word in ("concept", "讲解", "概念", "最小模型")):
        return "concept"
    if (update.get("attempt") or {}).get("activity_id"):
        return "coach"
    return "concept"


LEARNER_DNR_MARKERS = ("不要再讲", "别再讲", "讲过了", "不要重复", "跳过这个", "这个我会了", "已经会了")


def detect_learner_do_not_redo(text: str) -> list[str]:
    """Only an explicit learner statement becomes a do-not-redo entry."""
    raw = (text or "").strip()
    if not raw:
        return []
    if any(marker in raw for marker in LEARNER_DNR_MARKERS):
        return [f"学习者要求：{raw[:60]}"]
    return []


def collect_explicit_do_not_redo(update: dict) -> list[tuple[str, str]]:
    """Return ``(text, source)`` pairs explicitly stated by the mentor."""
    items: list[tuple[str, str]] = []
    for field in ("do_not_redo",):
        value = update.get(field)
        if isinstance(value, list):
            items.extend((str(item).strip(), "mentor_update") for item in value if str(item).strip())
    handoff = update.get("handoff")
    if isinstance(handoff, dict):
        value = handoff.get("do_not_redo")
        if isinstance(value, list):
            items.extend((str(item).strip(), "mentor_handoff") for item in value if str(item).strip())
    return items


def record_do_not_redo(studio: dict, mentor: str, items: list[tuple[str, str]], *, event_id: str) -> list[dict]:
    """Store explicit do-not-redo statements; never infer them from plan state."""
    bucket = studio.setdefault("dedupe", {}).setdefault("do_not_redo", [])
    # Drop legacy template rows: only explicit statements may survive.
    bucket[:] = [
        entry
        for entry in bucket
        if not (isinstance(entry, dict) and entry.get("source") == "template")
    ]
    existing = {str(entry.get("text") if isinstance(entry, dict) else entry) for entry in bucket}
    recorded = []
    for text, source in items:
        text = str(text or "").strip()
        if not text or text in existing:
            continue
        entry = {
            "text": text[:120],
            "at": clock.now_iso(),
            "source": source,
            "mentor": mentor,
            "event_id": event_id,
        }
        bucket.append(entry)
        existing.add(entry["text"])
        recorded.append(entry)
    if len(bucket) > 12:
        studio["dedupe"]["do_not_redo"] = bucket[-12:]
    return recorded


def _step_id_for(plan: dict, activity: str | None) -> str | None:
    if not activity:
        return (plan.get("current_objective") or {}).get("id")
    for step in plan.get("steps", []):
        if step.get("activity_id") == activity or step.get("step_id") == activity:
            return step.get("step_id")
    objective = plan.get("current_objective") or {}
    return objective.get("id")


def _remember_activity(studio: dict, mentor: str, activity: str, correct, help_level: int) -> None:
    dedupe = studio.setdefault("dedupe", {}).setdefault("activity_ids", {})
    existing = dedupe.get(activity)
    dedupe[activity] = {
        "mentor": mentor,
        "at": clock.now_iso(),
        "correct": correct,
        "help_level": help_level,
        "mentors": sorted({*(existing or {}).get("mentors", []), mentor}) if existing else [mentor],
    }


def detect_repeats(studio: dict, mentor: str, update: dict) -> list[dict]:
    """Return ``repeat_detected`` event specs for a duplicated task/analogy."""
    events: list[dict] = []
    activity = (update.get("attempt") or {}).get("activity_id")
    dedupe = studio.get("dedupe") or {}
    if activity:
        prior = (dedupe.get("activity_ids") or {}).get(activity)
        if prior and prior.get("mentor") != mentor:
            events.append(
                {
                    "kind": "repeat_detected",
                    "payload": {
                        "kind": "activity",
                        "activity_id": activity,
                        "mentor": mentor,
                        "previous_mentor": prior.get("mentor"),
                        "action": "重新生成一次；仍命中则换表征",
                    },
                }
            )
            studio.setdefault("flags", {})["force_new_representation"] = {"mentor": mentor, "activity_id": activity}
    analogy = update.get("analogy")
    if isinstance(analogy, str) and analogy.strip():
        hashes = studio.setdefault("dedupe", {}).setdefault("analogy_hashes", {})
        key = text_hash(analogy)
        if key in hashes:
            events.append(
                {
                    "kind": "repeat_detected",
                    "payload": {
                        "kind": "analogy",
                        "analogy": analogy,
                        "mentor": mentor,
                        "action": "换一个表征，不要原样重讲",
                    },
                }
            )
            studio["flags"]["force_new_representation"] = {"mentor": mentor, "analogy": analogy}
        else:
            hashes[key] = {"label": analogy[:80], "mentor": mentor, "at": clock.now_iso()}
            # keep only the five most recent analogies in the dedupe table
            if len(hashes) > 5:
                for stale in list(hashes.keys())[: len(hashes) - 5]:
                    hashes.pop(stale, None)
    return events


# -- plan authority --------------------------------------------------------
def apply_plan_update(studio: dict, update: dict, mentor: str) -> dict:
    """Apply or record a plan change.  Returns ``{events, summary}``."""
    events: list[dict] = []
    summary = {"status": None, "op": None}
    plan = studio.setdefault("plan", {})
    if "plan_patch" in update:
        events.append(
            {
                "kind": "plan_authority_violation",
                "payload": {
                    "mentor": mentor,
                    "kind": "plan_patch_in_update",
                    "detail": "use plan_change; raw plan patches are ignored",
                },
            }
        )
        return {"events": events, "summary": {"status": "rejected", "op": "plan_patch"}}
    change = update.get("plan_change")
    if change is None:
        return {"events": events, "summary": summary}
    if not isinstance(change, dict):
        events.append(
            {
                "kind": "plan_change_rejected",
                "payload": {"mentor": mentor, "reasons": ["plan_change must be an object"]},
            }
        )
        return {"events": events, "summary": {"status": "rejected", "op": None}}

    declared_by = change.get("by") or mentor
    status = change.get("status", "proposed")
    problems = validate_plan_change(change, mentor, plan)
    if declared_by != mentor:
        problems.append(f"by={declared_by!r} does not match the acting mentor {mentor!r}")
    if problems:
        events.append(
            {
                "kind": "plan_change_rejected",
                "payload": {
                    "mentor": mentor,
                    "op": change.get("op"),
                    "status": status,
                    "reasons": problems,
                },
            }
        )
        if status == "apply" or declared_by != mentor:
            events.append(
                {
                    "kind": "plan_authority_violation",
                    "payload": {
                        "mentor": mentor,
                        "op": change.get("op"),
                        "status": status,
                        "reasons": problems,
                    },
                }
            )
        return {"events": events, "summary": {"status": "rejected", "op": change.get("op")}}

    if status == "apply":
        if change.get("op") == "none":
            events.append(
                {
                    "kind": "plan_change",
                    "payload": {
                        "status": "noop",
                        "by": mentor,
                        "op": "none",
                        "reason": change.get("reason"),
                        "plan_version": int(plan.get("version") or 1),
                    },
                }
            )
            return {"events": events, "summary": {"status": "noop", "op": "none"}}
        if mentor != "planner":
            events.append(
                {
                    "kind": "plan_authority_violation",
                    "payload": {
                        "mentor": mentor,
                        "op": change.get("op"),
                        "status": status,
                        "detail": "only planner may apply a plan change",
                    },
                }
            )
            return {"events": events, "summary": {"status": "rejected", "op": change.get("op")}}
        result = apply_plan_change(plan, change)
        change_id = f"PC-{len(studio.get('plan_changes') or []) + 1:04d}"
        entry = {
            "id": change_id,
            "by": mentor,
            "op": result["op"],
            "week": change.get("week"),
            "step_id": change.get("step_id"),
            "detail": change.get("detail") or result.get("summary"),
            "reason": change.get("reason"),
            "status": "applied",
            "at": clock.now_iso(),
            "before_hash": result["before_hash"],
            "after_hash": result["after_hash"],
            "plan_version": int(plan.get("version") or 1),
        }
        studio.setdefault("plan_changes", []).append(entry)
        studio.setdefault("flags", {})["plan_state"] = "confirmed"
        summary = {"status": "applied", "op": result["op"], "change_id": change_id, "sanitized": result.get("sanitized", False)}
        if result.get("sanitized"):
            events.append(
                {
                    "kind": "plan_claim_sanitized",
                    "payload": {
                        "change_id": change_id,
                        "original_detail": change.get("detail"),
                        "reason": "计划文本声称已完成，但运行时没有 verified 证据；已改为进行中（待证据）",
                    },
                }
            )
        events.append(
            {
                "kind": "plan_change",
                "payload": {
                    "status": "applied",
                    "by": mentor,
                    "op": result["op"],
                    "detail": result["summary"],
                    "reason": change.get("reason"),
                    "before_hash": result["before_hash"],
                    "after_hash": result["after_hash"],
                    "plan_version": entry["plan_version"],
                    "change_id": change_id,
                    "sanitized": result.get("sanitized", False),
                },
            }
        )
        events.append(
            {
                "kind": "plan_change_applied",
                "payload": {
                    "change_id": change_id,
                    "by": mentor,
                    "op": result["op"],
                    "before_hash": result["before_hash"],
                    "after_hash": result["after_hash"],
                    "plan_version": entry["plan_version"],
                },
            }
        )
        return {"events": events, "summary": summary}

    # proposed: visible, but the effective plan is untouched.  "none" is not a
    # change at all, so it must not create an empty pending row.
    if change.get("op") == "none":
        events.append(
            {
                "kind": "plan_change",
                "payload": {
                    "status": "noop",
                    "by": mentor,
                    "op": "none",
                    "reason": change.get("reason"),
                    "plan_version": int(plan.get("version") or 1),
                    "detail": "提案为 op=none，未产生计划变更",
                },
            }
        )
        return {"events": events, "summary": {"status": "noop", "op": "none"}}
    change_id = f"PC-{len(studio.get('plan_changes') or []) + 1:04d}"
    entry = {
        "id": change_id,
        "by": mentor,
        "op": change.get("op"),
        "week": change.get("week"),
        "step_id": change.get("step_id"),
        "detail": change.get("detail"),
        "reason": change.get("reason"),
        "status": "proposed",
        "at": clock.now_iso(),
        "before_hash": plan_hash(plan),
        "after_hash": plan_hash(plan),
        "plan_version": int(plan.get("version") or 1),
    }
    studio.setdefault("plan_changes", []).append(entry)
    events.append(
        {
            "kind": "plan_change_proposed",
            "payload": {
                "change_id": change_id,
                "by": mentor,
                "op": change.get("op"),
                "step_id": change.get("step_id"),
                "reason": change.get("reason"),
                "plan_version": entry["plan_version"],
            },
        }
    )
    return {"events": events, "summary": {"status": "proposed", "op": change.get("op"), "change_id": change_id}}


def approve_plan_change(studio: dict, change_id: str, *, approve: bool) -> dict:
    entry = next((item for item in studio.get("plan_changes", []) if item.get("id") == change_id), None)
    if not entry:
        return {"ok": False, "reason": f"no plan change {change_id}"}
    if entry.get("status") != "proposed":
        return {"ok": False, "reason": f"{change_id} is already {entry.get('status')}"}
    plan = studio.setdefault("plan", {})
    if not approve:
        entry["status"] = "rejected"
        entry["decided_at"] = clock.now_iso()
        entry["decided_by"] = "planner"
        return {
            "ok": True,
            "events": [
                {
                    "kind": "plan_change_rejected",
                    "payload": {"change_id": change_id, "mentor": "planner", "reasons": ["planner declined"]},
                }
            ],
            "summary": {"status": "rejected", "change_id": change_id},
        }
    proposed = {
        "op": entry.get("op"),
        "week": entry.get("week"),
        "step_id": entry.get("step_id"),
        "detail": entry.get("detail"),
        "reason": entry.get("reason"),
        "status": "apply",
        "by": "planner",
    }
    problems = validate_plan_change(proposed, "planner", plan)
    if problems:
        entry["status"] = "rejected"
        entry["decided_at"] = clock.now_iso()
        entry["decided_by"] = "planner"
        return {
            "ok": False,
            "reason": "；".join(problems),
            "events": [
                {
                    "kind": "plan_change_rejected",
                    "payload": {"change_id": change_id, "mentor": "planner", "reasons": problems},
                }
            ],
        }
    result = apply_plan_change(plan, proposed)
    entry.update(
        {
            "status": "applied" if result["changed"] else "noop",
            "decided_at": clock.now_iso(),
            "decided_by": "planner",
            "before_hash": result["before_hash"],
            "after_hash": result["after_hash"],
            "plan_version": int(plan.get("version") or 1),
        }
    )
    studio.setdefault("flags", {})["plan_state"] = "confirmed"
    return {
        "ok": True,
        "events": [
            {
                "kind": "plan_change",
                "payload": {
                    "status": "applied" if result["changed"] else "noop",
                    "by": "planner",
                    "op": result["op"],
                    "before_hash": result["before_hash"],
                    "after_hash": result["after_hash"],
                    "plan_version": int(plan.get("version") or 1),
                    "change_id": change_id,
                    "approved_via": "plan command",
                },
            },
            {
                "kind": "plan_change_applied",
                "payload": {
                    "change_id": change_id,
                    "by": "planner",
                    "op": result["op"],
                    "before_hash": result["before_hash"],
                    "after_hash": result["after_hash"],
                    "plan_version": int(plan.get("version") or 1),
                },
            },
        ],
        "summary": {"status": "applied", "change_id": change_id, "op": result["op"]},
    }


# -- notes / reviews -------------------------------------------------------
def update_notes(notes: dict, mentor: str, update: dict, *, turn: int, synthetic: bool) -> dict:
    notes = notes or {}
    notes.setdefault("notes", [])
    notes.setdefault("taught", [])
    notes.setdefault("avoid", [])
    notes.setdefault("conclusions", [])
    notes["mentor"] = mentor
    notes["turns"] = int(notes.get("turns") or 0) + 1
    activity = (update.get("attempt") or {}).get("activity_id") or "turn"
    help_level = update.get("help_level")
    line = f"- {clock.now_iso(timespec='minutes')} {activity} hl={help_level} {str(update.get('next') or '')[:60]}"
    notes["notes"].append(line)
    while len(notes["notes"]) > 8:
        first = notes["notes"].pop(0)
        merged = first + "｜" + notes["notes"].pop(0)
        notes["notes"].insert(0, merged[:160])
    if update.get("next"):
        notes["next_suggestion"] = str(update["next"])[:200]
    if mentor in ("concept", "coach") or (help_level or 0) >= 2:
        notes["taught"].append(
            {
                "item": str(update.get("next") or update.get("misconception") or "本轮讲解")[:120],
                "activity_id": activity,
                "at": clock.now_iso(),
                "depth": help_level,
                "analogy": update.get("analogy"),
            }
        )
        notes["taught"] = notes["taught"][-30:]
    if update.get("misconception"):
        notes["avoid"].append(str(update["misconception"])[:120])
        notes["avoid"] = notes["avoid"][-20:]
    verdict = update.get("verdict")
    if mentor == "examiner" and isinstance(verdict, dict) and verdict.get("result") in ("pass", "fail"):
        notes["conclusions"].append(
            {
                "text": f"{verdict.get('activity_id')}: {verdict.get('result')} — {str(verdict.get('basis'))[:80]}",
                "basis_event": "session",
                "confidence": "observed",
            }
        )
        notes["conclusions"] = notes["conclusions"][-20:]
    return notes


def record_review(reviews: dict, studio: dict, update: dict, *, mentor: str, session_id: str, turn_event_id: str) -> dict:
    note = update.get("review_note")
    if not isinstance(note, dict):
        return {}
    reviews.setdefault("reviews", [])
    review_id = f"R-{len(reviews['reviews']) + 1:04d}"
    counter = studio.setdefault("review_counter", {"since_review": 0, "every": REVIEW_EVERY})
    previous = int(counter.get("since_review") or 0)
    counter["since_review"] = 0  # a finished review resets the cadence
    ns = next_step(studio, capability)
    counter["since_review"] = previous
    entry = {
        "review_id": review_id,
        "at": clock.now_iso(),
        "by": mentor,
        "session_id": session_id,
        "covered_nodes": [note.get("topic_id")],
        "retention": {},
        "resurfaced": [],
        "recommendation": {
            "mentor": ns.get("mentor") or "planner",
            "week_goal": note.get("suggest"),
        },
        "accepted_by_planner": False,
        "kind": note.get("kind"),
        "evidence": note.get("evidence"),
        "gap": note.get("gap"),
        "confidence": note.get("confidence"),
        "turn_event": turn_event_id,
    }
    reviews["reviews"].append(entry)
    studio.setdefault("review_counter", {"since_review": 0, "every": REVIEW_EVERY})["since_review"] = 0
    return entry


def hint_requested(text: str) -> bool:
    low = (text or "").lower()
    return any(word.lower() in low for word in HINT_KEYWORDS)


def node_id_for(project: dict, plan: dict, activity: str | None) -> str:
    return node_for(project, plan, activity)[0]


def summarize_levels(capability: dict) -> list[dict]:
    out = []
    for node in sorted(capability.get("nodes", []), key=lambda item: int(item.get("level") or 0), reverse=True):
        out.append(
            {
                "id": node.get("id"),
                "label": node.get("label"),
                "level": int(node.get("level") or 0),
                "level_label": LEVEL_LABELS.get(int(node.get("level") or 0), "?"),
                "evidence": len(node.get("evidence") or []),
                "last_fail": node.get("last_fail"),
            }
        )
    return out


def _exam_artifact(paths, activity: str | None, learner_text: str, update: dict, verdict: dict | None) -> str | None:
    """Write the examiner Q/A transcript so a verified level always has an artifact."""
    if not activity:
        return None
    safe = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in str(activity))[:80]
    rel = f"artifacts/{safe}.md"
    target = paths.root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    verdict = verdict or {}
    body = (
        f"# 考核记录：{activity}\n\n"
        f"- 时间：{clock.now_iso()}\n"
        f"- 判定：{verdict.get('result') or '未判定'}\n"
        f"- 依据：{verdict.get('basis') or update.get('basis') or '（导师未写依据）'}\n"
        f"- 评分口径：{verdict.get('rubric') or '（未提供）'}\n\n"
        "## 学习者回答\n\n"
        f"{learner_text.strip()}\n"
    )
    atomic_write_text(target, body)
    return rel


def _exam_progress(capability: dict, task_id: str | None, result: str, event_id: str) -> dict:
    """Record one answered question; keep the remaining queue open."""
    pending = capability.get("pending_exam") or {}
    if not pending:
        return {}
    questions = list(pending.get("questions") or [])
    remaining = list(pending.get("remaining_questions") or questions)
    answered = list(pending.get("answered") or [])
    question = task_id or (remaining[0] if remaining else pending.get("activity_id"))
    if question in remaining:
        remaining.remove(question)
    elif question and "-q" in str(question):
        # Examiner may use a different prefix (e.g. exam-em-w1-q1); adopt its ids
        # for the unanswered slots so the resumable queue shows real questions.
        prefix = str(question).rsplit("-q", 1)[0] + "-q"
        start = len(answered) + 1
        remaining = [f"{prefix}{index}" for index in range(start + 1, int(pending.get("total") or 3) + 1)]
        pending["questions"] = [item for item in (pending.get("questions") or []) if item not in remaining]
        pending["questions"] = [question] + remaining
    elif remaining:
        remaining.pop(0)
    answered.append({"question_id": question, "result": result, "at": clock.now_iso(), "event_id": event_id})
    pending["answered"] = answered
    pending["remaining_questions"] = remaining
    pending["current_index"] = len(answered)
    pending["activity_id"] = remaining[0] if remaining else question
    pending["status"] = "open" if remaining else "completed"
    if not remaining:
        capability["pending_exam"] = None
    return {
        "kind": "exam_progress",
        "payload": {
            "question_id": question,
            "result": result,
            "answered": len(answered),
            "remaining": remaining,
            "total": pending.get("total") or len(questions) or 3,
            "event_id": event_id,
        },
    }


def new_exam(project: dict, plan: dict, capability: dict, *, requested_by: str, activity: str | None) -> dict:
    existing = capability.get("pending_exam") or {}
    if existing.get("status") in ("open", "requested", "reask", "in_progress", "pending"):
        return existing
    node_id, label = node_for(project, plan, activity)
    questions = [f"{node_id}-q1", f"{node_id}-q2", f"{node_id}-q3"]
    capability["pending_exam"] = {
        "node_id": node_id,
        "label": label,
        "requested_by": requested_by,
        "status": "open",
        "activity_id": questions[0],
        "questions": questions,
        "remaining_questions": questions,
        "answered": [],
        "current_index": 0,
        "total": 3,
        "at": clock.now_iso(),
    }
    return capability["pending_exam"]


def refresh_plan_state(studio: dict) -> None:
    plan = studio.setdefault("plan", {})
    refresh_objective(plan)
    plan["hash"] = plan_hash(plan)


def plan_change_is_authoritative(plan: dict) -> bool:
    return plan.get("hash") == plan_hash(plan)


def clamp_level(level: int) -> int:
    return max(0, min(int(level or 0), MAX_LEVEL))


def review_due(capability: dict) -> list[str]:
    due = []
    now = clock.now_iso()
    for node in capability.get("nodes", []):
        when = node.get("review_due")
        if when and when <= now:
            due.append(node.get("id"))
    return due


def digest(text: str) -> str:
    return sha256_text(text or "")[:12]


def valid_mentor(value: str) -> bool:
    return value in MENTORS


def known_source_names() -> tuple[str, ...]:
    return tuple(f"state/mentors/{mentor}.json" for mentor in MENTORS) + ("handoff/do_not_redo", "plan/used_activities")


__all__ = [
    "apply_evidence",
    "apply_plan_update",
    "approve_plan_change",
    "detect_repeats",
    "detect_self_report",
    "hint_requested",
    "new_exam",
    "plan_change_is_authoritative",
    "record_review",
    "summarize_levels",
    "update_notes",
    "validate_update",
    "SCHEMA_VERSION",
]
