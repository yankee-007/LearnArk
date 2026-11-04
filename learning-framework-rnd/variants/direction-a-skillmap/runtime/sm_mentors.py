"""Mentor prompts, compact runtime context and turn execution.

The mentor is a language model; it never owns state.  This module only builds the
system/context pair described in ``design.md`` §6 and ``mentors/*.md``, runs one
turn through :func:`learncore.mentor.run_turn`, and labels offline output.
"""

from __future__ import annotations

import json
from pathlib import Path

from learncore import mentor as core_mentor
from learncore.events import Journal

import sm_model

OFFLINE_PREFIX = "[离线脚本导师]"

BUILTIN_PROMPTS = {
    "navigator": (
        "你是 SkillMap 的导航导师 navigator。你负责诊断、定位、解释为什么现在学这个节点、安排复习与交接。"
        "你不讲解细节、不判分、不把学习者自述当等级。每个结论必须给依据（先修未达 / 等级低 / 复习到期）。"
        "首次进入先做诊断，一题一题问；诊断只允许把节点置为 L0 或 L1。"
    ),
    "concept": (
        "你是 SkillMap 的概念导师 concept。你负责 explain 阶段：先给场景再给定义、给类比并说清失效边界、"
        "落到最小可运行例子、最后出一个微检查。你不给练习答案、不代写代码、不判等级。"
    ),
    "coach": (
        "你是 SkillMap 的操练导师 coach。你负责 drill 与 apply：先让学习者写再点评，每次只点一个最关键的问题，"
        "分级给提示，要求贴真实 PowerShell 输出；apply 结束必须给 artifacts/ 相对路径。你不直接改他的文件，"
        "不把 L2/L3 的帮助说成独立完成。"
    ),
    "examiner": (
        "你是 SkillMap 的考核导师 examiner。你负责 check：一次给全独立题与迁移题，零提示、零示例，"
        "只判通过／不通过／证据不足。你不给台阶、不说“你已经掌握了”。help_level 恒为 0。"
    ),
}

PROTOCOL_TEMPLATE = """
## 运行时协议（由 SkillMap runtime 注入，优先于上面的任何措辞）

- 项目目标：{goal}
- 地图与诊断规模：本模板共 **{node_count} 个节点**、诊断 **{probe_count} 题**；以这两个数字为准（agent-dev 是 12/5，email 是 6/3），不要说错。
- 当前节点：{node}（先修 {prereqs}，当前 L{level}，目标 L{target}）
- 当前阶段：{stage}（{stage_label}），唯一合法 activity_id：`{activity_id}`
- **本轮只能围绕 `{activity_id}` 出题/追问**：不要要求上一阶段的变式、补交或其它活动（例如 check 时不要再要 apply 的产物或变式）。
- 学习者自述只是待验证假设，不是证据；不要说“你已经掌握了”。
- 机器块字段：help_level 0–3、attempt.activity_id、attempt.correct（true/false/null）、
  probe（诊断轮填 {{"node": 锚点, "level": 0 或 1, "reason": "一句依据"}}，其它轮写 null）、
  misconception、next、mastery_delta、artifact。`activity_id` 必须是 `{example}` 这类
  `节点-阶段` 形式，或保留值 `diagnose` / `review` / `handoff`。
- 只有 correct=true 且 help_level<=1 才可能升级；help_level>=2 记为受助完成且最多到 L1；
  单轮最多 +1。等级由运行时判定，你不能直接改。
- 学习者还没有作答时，`attempt.correct` 写 null，不要替学习者编造答案。
- **context 里的 runtime_next 是运行时唯一权威的下一步**：正文不得宣布与它不同的节点、阶段或起点，
  也不要自行安排额外任务；学习者问“现在学什么”时照 runtime_next 回答。
- 正文是给学习者的：不要出现“机器块／claim／help_level／mentor_update／attempt／level_up”等内部术语，
  也不要贴 JSON 机器块。用“记录格式／证据／提示等级”这类白话表达。
- 不要评价学习者怎么调用 shell，也不要要求他“加引号／换引号／改用别的写法”；
  记录里引号丢失不是他的错，按原意理解他的代码。
{probe_rule}{extra}
"""

FINAL_REMINDER = """
## 最后一条硬规则（每轮都适用）
回复的最后必须是一个 ```learn-update 代码块（内含一个 JSON 对象），正文不要重复它，
块后不要再写任何文字。先写完教学正文，再写这个块；缺少它 = 本轮证据作废。
"""

EXAMINER_EXTRA = "- 本阶段是 check：help_level 必须为 0。返回 >=1 会被运行时作废并记 examiner_help_violation。\n"
REVIEW_EXTRA = "- 本轮是复习（review）：零提示、一题、≤5 分钟；通过则复习间隔前进一档。\n"
DIAGNOSIS_EXTRA = "- 本轮是诊断探针：只允许把锚点节点置为 L0 或 L1，绝不允许 L2 以上。\n"
EXPLAIN_EXTRA = "- explain 退出条件：用自己的话复述 ≥2 个要点 + 答对 1 个“为什么”。限 4 轮 / 8 分钟。\n"
DRILL_EXTRA = "- drill 退出条件：连续 2 题同类操练在 help_level≤1 下正确。\n"
APPLY_EXTRA = "- apply 退出条件：一个可检查的产物（写进 `artifact`）+ help_level≤1 + 1 道变式。\n"
#: Cross-topic guard: the email template must never leak software-engineering
#: scenarios (round-06 found API/auth/integration check questions).
EMAIL_TOPIC_EXTRA = (
    "- 本主题是**英文工作邮件写作**：题目、示例、反馈只用写作场景（邮件、语气、结构、主题行、清晰度），"
    "不要出现代码、API、接口、认证、联调、部署、Agent、编程、可运行文件等软件工程语汇；"
    "apply/check 的产物是 `artifacts/*.md` 或 `.txt` 文本稿。\n"
)


def prompt_path(variant_dir: str | Path, mentor: str) -> Path:
    return Path(variant_dir) / "mentors" / f"{mentor}.md"


def base_prompt(variant_dir: str | Path, mentor: str) -> str:
    path = prompt_path(variant_dir, mentor)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if not text:
        text = BUILTIN_PROMPTS.get(mentor, BUILTIN_PROMPTS["navigator"])
    return text


def extra_for(stage: str, mode: str, help_cap: int | None) -> str:
    if mode == "diagnose":
        return DIAGNOSIS_EXTRA
    if mode == "review":
        return REVIEW_EXTRA
    if stage == "check":
        return EXAMINER_EXTRA
    extra = {"explain": EXPLAIN_EXTRA, "drill": DRILL_EXTRA, "apply": APPLY_EXTRA}.get(stage, "")
    if help_cap is not None:
        extra += f"- 本阶段建议提示上限：help_level≤{help_cap}（超过即记为受助完成，不升等级）。\n"
    return extra


def system_prompt(
    *,
    variant_dir: str | Path,
    mentor: str,
    template: str,
    stage: str,
    mode: str,
    node: dict | None,
    goal: str,
    activity_id: str,
    help_cap: int | None = None,
    probe: dict | None = None,
) -> str:
    base = base_prompt(variant_dir, mentor)
    node_id = node["id"] if node else "（诊断中）"
    node_title = node.get("title", "") if node else "尚未定位，先做诊断"
    prereqs = "、".join(node.get("prereqs", [])) if node else "（无）"
    probe_rule = ""
    if mode == "diagnose" and probe:
        probe_rule = (
            f"- 本轮诊断题（唯一合法题面，正文照抄，不要另写代码或换题）：{probe['question']}\n"
            f"- 只有判定了“学习者已回答本题”才写 probe：{{\"node\": \"{probe['node']}\", \"level\": 0 或 1, "
            f"\"reason\": \"一句依据\"}}；level 只能是 0 或 1，node 必须是本探针锚点 {probe['node']}。\n"
            "- 如果你这轮只是追问、举例或补充提示，还没判定对错，就把 probe 和 attempt.correct 都写 null："
            "运行时会保留同一题，下一轮继续问它。一次只问一题，不要跳到后面的题。\n"
        )
    protocol = PROTOCOL_TEMPLATE.format(
        goal=goal or sm_model.default_goal(template),
        node_count=len(sm_model.template_spec(template)["nodes"]),
        probe_count=sm_model.total_probes(template),
        node=f"{node_id} {node_title}".strip(),
        prereqs=prereqs or "无",
        level=int(node.get("level", 0)) if node else 0,
        target=int(node.get("target_level", 3)) if node else 3,
        stage=stage,
        stage_label=sm_model.stage_label(stage) if stage in sm_model.STAGE_LABELS else stage,
        activity_id=activity_id or "diagnose",
        example=f"{node_id}-{stage}" if node and stage in sm_model.STAGES else "diagnose",
        probe_rule=probe_rule,
        extra=(EMAIL_TOPIC_EXTRA if template == "email" else "") + extra_for(stage, mode, help_cap),
    )
    return base + "\n\n" + protocol.strip() + "\n\n" + core_mentor.UPDATE_HELP + "\n" + FINAL_REMINDER


def build_context(
    *,
    project: dict,
    map_doc: dict,
    plan: dict,
    journal: Journal,
    session_id: str | None,
    node: dict | None,
    stage: str,
    mode: str,
    curriculum: dict,
    minutes_budget: int | None,
    review_due: list[dict] | None = None,
    runtime_next: dict | None = None,
) -> str:
    lines: list[str] = []
    learner = project.get("learner") or {}
    lines.append(f"目标：{project.get('goal')}（template={project.get('template')}）")
    budget_note = ""
    if minutes_budget:
        breakdown = sm_model.budget_breakdown(minutes_budget, plan.get("diagnosis_minutes"))
        budget_note = (
            f"；本次预算 {minutes_budget} 分钟（诊断约 {breakdown['diagnosis']} + "
            f"活动约 {breakdown['activity']} + 收尾 {breakdown['reserve']}）；单个任务按 {breakdown['activity']} 分钟计，不要按 20/45 分钟排"
        )
        if int(minutes_budget) < sm_model.SHORT_DIAGNOSIS_MINUTES:
            budget_note += f"；短预算：本次最多 {sm_model.SHORT_DIAGNOSIS_PROBES} 个诊断探针，其余延后"
    lines.append(f"学习者：{learner.get('name', 'learner')}；每周预算 {project.get('minutes_per_week')} 分钟{budget_note or '；本次未指定时长'}")
    if runtime_next is not None:
        lines.append("")
        lines.append("## runtime_next（运行时结论，唯一权威；正文必须与它一致，不得宣布别的起点/下一步）")
        lines.append(json.dumps(runtime_next, ensure_ascii=False, sort_keys=True))

    diagnosis = learner.get("diagnosis") or {}
    if diagnosis.get("status") == "pending":
        probes = diagnosis.get("probes") or []
        done = sum(1 for probe in probes if probe.get("status") in ("done", "skipped"))
        lines.append(f"诊断进行中：{done}/{len(probes) or sm_model.total_probes(project.get('template', 'agent-dev'))} 题已答；本轮只问当前这一题。")
    elif diagnosis.get("status"):
        lines.append(f"诊断：{diagnosis.get('status')}（{diagnosis.get('completed_at') or '—'}）")

    if node:
        review = node.get("review") or {}
        lines.append(
            f"当前节点：{node['id']} {node['title']}；先修 {'、'.join(node.get('prereqs', [])) or '无'}；"
            f"L{int(node.get('level', 0))}/L{int(node.get('target_level', 3))}；状态 {node.get('status')}；"
            f"复习 index={review.get('interval_index')} due={review.get('due')}"
        )
        seed = curriculum.get(node["id"]) or {}
        if seed.get("points"):
            lines.append(f"节点要点：{seed['points']}")
        if seed.get("misconceptions"):
            lines.append(f"常见误解：{seed['misconceptions']}")
        if seed.get("drill"):
            lines.append(f"drill 种子：{seed['drill']}")
        if seed.get("apply"):
            lines.append(f"apply 种子：{seed['apply']}")
        if seed.get("check"):
            lines.append(f"check 种子：{seed['check']}")
        if node.get("misconceptions"):
            lines.append("本节点已记录错因：" + "；".join(item.get("label", "") for item in node["misconceptions"][-3:]))
    else:
        lines.append("当前节点：（诊断中，未选节点）")

    lines.append(f"阶段：{stage}（mode={mode}）")
    if plan.get("session_goal"):
        lines.append(f"本次会话目标：{plan['session_goal']}")
    if review_due:
        lines.append("到期复习：" + "、".join(f"{n['id']}(due {n['review']['due']})" for n in review_due[:3]))

    handoff = plan.get("last_handoff") or {}
    if handoff:
        lines.append(
            "最近交接：%s → %s，原因 %s；未决 %s；下一步 %s"
            % (
                handoff.get("from"),
                handoff.get("to"),
                handoff.get("reason"),
                "；".join(handoff.get("unresolved") or []) or "无",
                "；".join(handoff.get("next") or []) or "无",
            )
        )

    if journal.path.exists():
        recent = journal.all()[-4:]
        if recent:
            lines.append("最近事件：")
            for event in recent:
                payload = event.get("payload") or {}
                bits = [event.get("kind", "?")]
                for key in ("node", "stage", "activity_id", "correct", "help_level", "level"):
                    if key in payload:
                        bits.append(f"{key}={payload[key]}")
                lines.append("  - " + " ".join(str(bit) for bit in bits))
    return "\n".join(lines)


def transcript_from_journal(journal: Journal, session_id: str | None, limit: int = 6) -> list[dict]:
    if not session_id:
        return []
    turns: list[dict] = []
    for event in journal.all():
        if event.get("kind") != "mentor_turn":
            continue
        payload = event.get("payload") or {}
        if payload.get("session_id") != session_id:
            continue
        learner_text = payload.get("learner_text") or ""
        mentor_text = payload.get("mentor_text") or ""
        if learner_text:
            turns.append({"role": "learner", "text": learner_text})
        if mentor_text:
            turns.append({"role": "mentor", "text": mentor_text})
    return turns[-limit:]


REPAIR_PROMPT = (
    "（运行时提醒）你上一条回复缺少 learn-update 机器块，本轮将无法记录任何证据。"
    "不要重复教学内容，不要道歉，只输出那一个 ```learn-update 代码块。"
)


def turn(
    llm,
    *,
    system: str,
    context: str,
    user: str,
    transcript: list[dict] | None = None,
):
    """One mentor turn, with a single protocol-repair retry for live models.

    Offline/mock turns are never retried: the scripted mentor is deterministic by
    design and a retry would silently consume another scripted line.  For a real
    model, an omitted machine block would throw away a genuine learner answer, so
    we ask once, without repeating the lesson, for just the block.  If the repair
    also fails the caller still records ``mentor_update_invalid``.
    """
    result = core_mentor.run_turn(llm, system=system, context=context, user=user, transcript=transcript)
    if getattr(llm, "mode", "api") == "mock":
        return result
    if result.updates is not None or result.update_error:
        return result
    history = list(transcript or [])
    if result.text:
        history.append({"role": "mentor", "text": result.text})
    repaired = core_mentor.run_turn(llm, system=system, context=context, user=REPAIR_PROMPT, transcript=history)
    if repaired.updates is None:
        return result
    repaired.text = result.text
    setattr(repaired, "repaired", True)
    return repaired


def offline_prefix(mode: str) -> str:
    return OFFLINE_PREFIX if mode == "mock" else ""


def render_reply(text: str, mode: str) -> str:
    prefix = offline_prefix(mode)
    body = (text or "").strip()
    if not prefix:
        return body
    if body.startswith(prefix):
        return body
    return f"{prefix}\n{body}"
