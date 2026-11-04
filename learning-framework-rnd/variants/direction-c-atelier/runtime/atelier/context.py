"""Per-mentor context builders.

Each builder is deliberately narrow: no complete journal, no full past
sessions, no other mentor's private notes.  The examiner builder goes further
and never opens ``state/mentors/coach.json`` or ``state/mentors/concept.json``;
its ``sources`` list is the reconciliation evidence for that guarantee.
"""

from __future__ import annotations

from learncore import clock

from .const import (
    CONTEXT_LIMIT,
    HANDOFF_CONTEXT_LIMIT,
    LEVEL_LABELS,
    MENTORS,
    MENTOR_LABELS,
    PROJECTION_KINDS,
    format_weekly_scope,
)
from .state import Paths, journal


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _goal_block(project: dict) -> str:
    goal = _truncate(project.get("goal") or "（未填写目标）", 300)
    constraints = "；".join(str(item) for item in project.get("constraints", [])[:3])
    learner = project.get("learner") or {}
    minutes = learner.get("minutes_per_week") or "?"
    lines = [f"目标：{goal}", f"周可用时间：约 {format_weekly_scope(learner)}"]
    if constraints:
        lines.append(f"约束：{_truncate(constraints, 300)}")
    return "## 目标与约束\n" + "\n".join(lines)


def _plan_block(plan: dict) -> str:
    objective = plan.get("current_objective") or {}
    week_goal = next(
        (goal for goal in plan.get("week_goals", []) if int(goal.get("week") or 0) == int(objective.get("week") or 1)),
        None,
    )
    ordered = sorted([step for step in plan.get("steps", []) if step.get("status") != "removed"], key=lambda s: int(s.get("n") or 0))
    index = next((i for i, step in enumerate(ordered) if step.get("step_id") == objective.get("id")), None)
    neighbours = []
    if index is not None:
        for offset in (-1, 0, 1):
            pos = index + offset
            if 0 <= pos < len(ordered):
                step = ordered[pos]
                neighbours.append(f"{step.get('status', 'todo')}: {step.get('step_id')} {step.get('text', '')}")
    criteria = "；".join(str(item) for item in objective.get("success_criteria", []) if item)
    lines = [
        f"计划 {plan.get('plan_id')} v{plan.get('version')}（权威：planner，其他导师只读）",
        f"本周目标：{week_goal.get('text') if week_goal else '未设定'}",
        f"当前目标：{objective.get('id')} {objective.get('text', '')}",
        f"成功标准：{criteria or '未设定'}；预计 {objective.get('est_minutes', 20)} 分钟",
        "相邻步骤：" + ("｜".join(neighbours) or "无"),
    ]
    return "## 计划\n" + "\n".join(lines)


def _capability_block(capability: dict) -> str:
    nodes = sorted(capability.get("nodes", []), key=lambda node: int(node.get("level") or 0), reverse=True)
    lines = []
    for node in nodes[:5]:
        level = int(node.get("level") or 0)
        lines.append(
            f"- {node.get('label') or node.get('id')}：{LEVEL_LABELS.get(level, level)}（证据 {len(node.get('evidence') or [])} 条）"
        )
    if not lines:
        lines.append("- 暂无能力节点证据（一律按未验证处理）")
    for node in nodes:
        last_fail = node.get("last_fail") or {}
        if last_fail.get("misconception"):
            lines.append(f"- 最近错因：{_truncate(last_fail['misconception'], 100)}（{last_fail.get('at', '')}）")
            break
    return "## 能力证据（运行时判定，你不得直接改写）\n" + "\n".join(lines)


def _handoff_block(payload: dict | None, *, examiner: bool) -> str:
    if not payload:
        return ""
    lines = [
        f"最新交接 {payload.get('handoff_id')}：{payload.get('from')} → {payload.get('to')}"
        + ("（degraded，字段由运行时补齐）" if payload.get("degraded") else ""),
    ]
    if not examiner:
        lines.append(f"为什么换人：{_truncate(payload.get('why') or '', 160)}")
        lines.append("已知：" + "；".join(payload.get("known") or [])[:400])
        if payload.get("what_tried"):
            lines.append("做过：" + "；".join(payload.get("what_tried") or [])[:300])
    else:
        # The examiner receives verifiable facts and open obligations only; the
        # leaving mentor's hint history and do-not-redo wording stay out.
        lines.append("已知：" + "；".join(payload.get("known") or [])[:400])
    loops = []
    for loop in payload.get("open_loops") or []:
        if loop.get("status") == "closed" or loop.get("id") == "OL-0":
            continue
        flag = "阻塞" if loop.get("blocking") else "一般"
        loops.append(f"{loop.get('id')}[{flag}] {loop.get('text')}（owner={loop.get('owner')} due={loop.get('due')}）")
    if loops:
        lines.append("未决：" + "；".join(loops)[:400])
    lines.append(f"交接建议的下一步：{_truncate(payload.get('next') or '', 200)}（以运行时排程为准）")
    return "## 上一手交接\n" + "\n".join(lines)


def _notes_block(notes: dict, mentor: str) -> str:
    lines = [f"（仅 {mentor} 可见）"]
    for line in notes.get("notes") or []:
        lines.append(line if line.startswith("- ") else f"- {line}")
    taught = notes.get("taught") or []
    if taught:
        lines.append("讲过的（最近 5 条）：")
        for item in taught[-5:]:
            lines.append(f"- {item.get('item')}（{item.get('activity_id') or 'n/a'}，depth={item.get('depth')}）")
    avoid = notes.get("avoid") or []
    if avoid:
        lines.append("避免：")
        for item in avoid[-5:]:
            lines.append(f"- {item}")
    if notes.get("next_suggestion"):
        lines.append(f"上次留给自己的下一步：{_truncate(notes['next_suggestion'], 120)}")
    return "## 你的私有笔记\n" + "\n".join(lines)


def _dnr_block(payload: dict | None, studio: dict) -> str:
    entries = []
    if payload:
        entries.extend(payload.get("do_not_redo") or [])
    for item in (studio.get("dedupe") or {}).get("do_not_redo", []):
        text = item.get("text") if isinstance(item, dict) else str(item)
        if text and text not in entries:
            entries.append(text)
    if not entries:
        return ""
    return "## 去重表：不要重做\n" + "\n".join(f"- {_truncate(item, 120)}" for item in entries[:6])


def _examiner_dedupe_block(studio: dict) -> str:
    dedupe = studio.get("dedupe") or {}
    used = list(dedupe.get("activity_ids", {}).keys())
    analogies = dedupe.get("analogy_hashes", {})
    lines = ["已用过的活动（不要再出同一道题）：" + ("、".join(used[-10:]) or "无")]
    if analogies:
        labels = [entry.get("label", "") for entry in list(analogies.values())[-5:] if isinstance(entry, dict)]
        if labels:
            lines.append("已用过的类比（换一个表征）：" + "；".join(labels))
    return "## 去重表：不要重复出题\n" + "\n".join(lines)


def _project_events(paths: Paths, mentor: str) -> list[str]:
    lines: list[str] = []
    events = [event for event in journal(paths).all() if event.get("kind") in PROJECTION_KINDS]
    for event in events[-8:]:
        payload = event.get("payload") or {}
        kind = event.get("kind")
        bits = [f"#{event.get('seq')}", str(kind)]
        if payload.get("mentor"):
            bits.append(f"mentor={payload['mentor']}")
        if payload.get("activity_id"):
            bits.append(f"activity={payload['activity_id']}")
        if payload.get("help_level") is not None:
            bits.append(f"hl={payload['help_level']}")
        if payload.get("correct") is not None:
            bits.append("correct=" + ("true" if payload.get("correct") else "false"))
        if payload.get("result"):
            bits.append(f"result={payload['result']}")
        if kind == "handoff":
            bits.append(f"{payload.get('from')}→{payload.get('to')}")
        lines.append(_truncate(" ".join(bits), 120))
    return lines


def build_context(
    paths: Paths,
    project: dict,
    studio: dict,
    capability: dict,
    mentor: str,
    handoff_payload: dict | None,
) -> dict:
    """Return ``{text, chars, sources, excluded, handoff_id}`` for one turn."""
    plan = studio.get("plan") or {}
    examiner = mentor == "examiner"
    blocks: list[tuple[str, str]] = []
    sources: list[str] = []

    goal = _goal_block(project)
    blocks.append(("project.goal", goal))
    sources.append("project.goal")

    plan_block = _plan_block(plan)
    blocks.append(("studio.plan", plan_block))
    sources.append("studio.plan")

    from .planning import next_step

    scheduler = next_step(studio, capability)
    command = "learn.cmd examine" if scheduler.get("kind") == "pending_exam" else (
        f"learn.cmd switch {scheduler['mentor']}" if scheduler["mentor"] != studio.get("current_mentor") else 'learn.cmd say "..."'
    )
    schedule_block = (
        "## 运行时排程（权威，优先于交接建议）\n"
        f"由 {MENTOR_LABELS.get(scheduler['mentor'], scheduler['mentor'])} 接续：{scheduler['reason']}\n"
        f"下一次命令：{command}"
    )
    blocks.append(("studio.next_step", schedule_block))
    sources.append("studio.next_step")

    cap_block = _capability_block(capability)
    blocks.append(("capability.nodes", cap_block))
    sources.append("capability.nodes")

    if handoff_payload:
        handoff_block = _truncate(_handoff_block(handoff_payload, examiner=examiner), HANDOFF_CONTEXT_LIMIT)
        if handoff_block:
            blocks.append(("handoff/latest", handoff_block))
            sources.append("handoff/latest")

    if examiner:
        blocks.append(("plan/used_activities", _examiner_dedupe_block(studio)))
        sources.append("plan/used_activities")
        sources.append("capability.last_misconception")
    else:
        dnr = _dnr_block(handoff_payload, studio)
        if dnr:
            blocks.append(("handoff/do_not_redo", dnr))
            sources.append("handoff/do_not_redo")

    from .state import notes_doc

    notes, _ = _load_notes(notes_doc(paths, mentor))
    notes_block = _notes_block(notes, mentor)
    blocks.append((f"state/mentors/{mentor}.json", notes_block))
    sources.append(f"state/mentors/{mentor}.json")

    event_lines = _project_events(paths, mentor)
    if event_lines:
        blocks.append(("events/projection", "## 最近共同事件（运行时投影，不含全文）\n" + "\n".join(f"- {line}" for line in event_lines)))
        sources.append("events/projection")

    excluded = [f"state/mentors/{other}.json" for other in MENTORS if other != mentor]
    if examiner:
        # explicit audit trail for C-S1 / examiner isolation
        excluded += ["journal/full", "sessions/full-text", "handoff/what_tried", "handoff/do_not_redo"]

    text = "\n\n".join(block for _, block in blocks)
    # Budget trimming order: events -> notes -> handoff detail.
    while len(text) > CONTEXT_LIMIT and "events/projection" in sources:
        blocks = [block for block in blocks if block[0] != "events/projection"]
        sources.remove("events/projection")
        text = "\n\n".join(block for _, block in blocks)
    while len(text) > CONTEXT_LIMIT and f"state/mentors/{mentor}.json" in sources:
        blocks = [block for block in blocks if block[0] != f"state/mentors/{mentor}.json"]
        sources.remove(f"state/mentors/{mentor}.json")
        text = "\n\n".join(block for _, block in blocks)
    if len(text) > CONTEXT_LIMIT:
        text = text[: CONTEXT_LIMIT - 1] + "…"

    return {
        "text": text,
        "chars": len(text),
        "sources": sources,
        "excluded": excluded,
        "handoff_id": (handoff_payload or {}).get("handoff_id"),
        "mentor": mentor,
        "built_at": clock.now_iso(),
    }


def _load_notes(doc) -> tuple[dict, str]:
    from .state import load_with_repair

    return load_with_repair(doc)


UPDATE_CONTRACT = """
## 运行时附加约定（Atelier，优先级高于上面的风格建议）

1. 正文 2–6 句，先结论后理由；机器块只出现在回复最末尾，且只有一个。
2. 机器块格式固定：
```learn-update
{"help_level":0,"attempt":{"activity_id":null,"correct":null},"misconception":null,"next":"一句话","mastery_delta":0}
```
3. 可选扩展字段（按你的职责使用，越界会被运行时拒绝）：
   - `plan_change`: {"op":"add_step|replace_step|remove_step|reorder|replan_week|defer_step|none","week":1,"step_id":"…","detail":"…","reason":"…","status":"proposed","by":"<你的 id>"}
   - `verdict`: 只有 examiner 可用 {"activity_id":"…","result":"pass|fail|pending","basis":"学习者原话","rubric":{"correctness":0,"reasoning":0,"max":4,"pass_line":2}}
   - `review_note`: 只有 reviewer 可用 {"topic_id":"…","kind":"recap|decay_check|transfer|next_week","evidence":"已发生事件","gap":"…","suggest":"…","confidence":"observed|inferred"}
   - `analogy`: 本轮用到的类比短标签（3–8 词），用于去重
4. 交接提案 `handoff`（只在换人/结束时需要）：
   {"why":"为什么该换人","to_hint":"coach","auto":false}
   运行时从 journal / 会话 / 计划合成 known、what_tried、open_loops、next、do_not_redo；你只需要给 `why`。
   如果你希望本轮结束时自动换人，可写 {"why":"…","auto":true,"to_hint":"examiner"}；目标缺失时运行时会留在当前导师并记录 handoff_rejected，不会丢回合。
5. 计划权威：只有 planner 能 `status:"apply"`；其他导师只能 `proposed`。不要声称计划已被你改好。
6. 证据纪律：不要写"你已掌握"；`mastery_delta` 只是建议，运行时按 help_level/attempt/verdict 重新判定。
7. help_level：0 独立 / 1 小提示 / 2 分步引导 / 3 基本代做。
8. 不要输出 JSON 以外的解释性前后缀在机器块内；正文里不要复述机器块。
9. 不要声称某个步骤"已完成/已掌握"——进度由运行时按证据判定；计划文本里的这类断言会被改成"进行中（待证据）"。
10. 不要虚构上一轮的尝试、报错或产物。上下文没有给出的事实，就说"我不确定/请学习者复述"，不要补全成发生过的事。
11. planner 在诊断中发现需要讲解/陪练的误解时，必须在 `handoff` 里写 {"why":"…","auto":true,"to_hint":"concept" 或 "coach"}；运行时会据此交接。
"""


def system_prompt(mentor: str) -> str:
    from .templates import mentor_prompt

    return (mentor_prompt(mentor).strip() + "\n" + UPDATE_CONTRACT).strip()


def mentor_title(mentor: str) -> str:
    return MENTOR_LABELS.get(mentor, mentor)
