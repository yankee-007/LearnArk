"""导师协议层：组装 system/context/user，跑一轮，校验机器块。

LLM 只提议（rubric 分数、缺口主题、防御问答）；所有状态变更仍由运行时按
design.md §7–§8 计算。非法机器块一律记 ``mentor_update_invalid``，本轮按“无证据”处理。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from learncore import llm as llm_core
from learncore import mentor as mentor_core
from learncore.fsutil import sha256_text

import forge_logic as logic
import forge_state as state_mod

PROTOCOL = """你是 LearnArk · Forge（作品驱动学习框架）里的导师。运行时给你权威的项目状态摘要。
硬规则：
1. 你只提议，不写状态：通过与否、缺口开关、能力判定都由运行时按证据计算，你不得宣布“已通过/已掌握”。
2. 每轮末尾输出且只输出一个 ```learn-update 围栏块，块内是合法 JSON，正文不要复述块内容。
3. 不得编造没登记的作品、没发生的评审、没读过的文件；上下文里的「已登记作品集合」是权威，
   不得说其中任何文件“未登记/不存在/缺失”；上下文没有的信息就说不知道。
4. 用中文回答；先结论后一个可执行动作；不要列整门课。
5. 运行时下一步（runtime_next）是本轮唯一权威动作：不得另排任务、另开文件或让学习者先做别的事，
   也不要给任何与它不同的动作（例如它说 gap_learn，你不能让学习者先 review 或先改代码）。
   若你不同意，只能用一句话说明异议，然后仍按 runtime_next 继续；正文只给这一个动作。
6. 如果学习者消息明显被 shell 截断或无法解析（引号/花括号不配对、以反斜杠结尾、参数缺一半），
   先要求他把完整内容用 `say -` 从 stdin 或文件重发，不得据此断言错误原因，也不得把猜测写进 misconception。
7. 离线模式下你的回复来自脚本，不代表真实教学质量。"""

REVIEW_BLOCK_HELP = """本轮你是评审导师，机器块除通用字段外还必须包含：
- "rubric": 覆盖全部维度的列表，每项 {"dim","score"(1–4 整数),"note","evidence_line"(作品行号) 或 "evidence_path"(文件:行)}。
  不得增删维度，不得写 weight/threshold。score >= threshold 的维度必须带 evidence_line 或 evidence_path；
  没有证据时运行时会把它降到 threshold-1 并记 rubric_unevidenced（证据不足不能算达标）。
- "gap": 仅列低于阈值的维度，每项 {"dim","note"}。
- "defense": 未做防御提问时写 null；做过时写 {"questions":[{"qid","dim","question","answer","evidence_line","ok"}]}。
note 必须能指向文件/行号/一次实跑；没有证据按 1–2 分写清缺什么。
note 里不要写没有行号支撑的数量断言（例如“步数上限为 6”）：要么引用 evidence_line/evidence_path，要么省略；
否则运行时记 claim_without_evidence。"""

GUIDE_BLOCK_HELP = """本轮你是缺口微课导师，机器块里 "gap" 写 [{"dim","note"}] 更新该卡的 note；
不要写 rubric，不要关闭缺口。help_level 只记本轮微课的实际帮助强度（讲概念=2，给可粘贴代码=3，只指方向=1）。
注意：guide 微课是官方学习路径，不计入作品 assisted_level；assisted_level 只由 coach/critic 在作品产出过程中的帮助决定。
不要重复上一次讲解：上下文若带“上次这张卡的讲解”，换例子或直接说没有新内容；讲完只要求改一处并重新 review。"""

COACH_BLOCK_HELP = """本轮你是默认导师，机器块用通用字段即可；不得写 rubric 或通过结论。
help_level 按你本轮实际给出的帮助强度记（0 独立 / 1 小提示 / 2 分步 / 3 基本代做），宁高勿低。
如果你给了多步骨架、示例代码或近似答案，help_level 必须 >= 2；学习者明确要答案而你给了骨架/代码时记 3。
你给的学习帮助会计入下一次登记作品的 assisted_level；guide 微课不算。
动作必须服从 runtime_next；不要新建 runtime_next 之外的文件或任务。"""


def template_guidance(brief: dict) -> str:
    """Template-specific rules so a writing project never gets coding examples."""
    if brief.get("template") == "email":
        return (
            "当前模板：英文工作邮件（写作）。硬规则：\n"
            "- 所有示例必须是英文邮件片段或「before → after」句子对照；禁止 Python/代码块，"
            "不得出现 def、print、import、API、工具调用、agent 等编程内容。\n"
            "- 微课结构：一句概念 + 一个邮件句子/段落对照 + 一个常见坑 + 回到作品改一句。\n"
            "- 动作与验证用写作语言（读一遍、改一句、贴出改动），不要提运行/打印/部署；"
            "教练开场问「这封邮件现在能让收件人做什么、还差什么」，不要问跑通/API。\n"
            "- 覆盖 mentors/guide.md 里的代码块要求：邮件模板下用邮件句段的前后对照，不要代码块。\n"
            "- 防御提问针对邮件的句子与段落；不要要求代码行号，提「第几段/哪一句」。"
        )
    return (
        "当前模板：Agent 开发（编程）。示例可用 Python 片段；防御提问要绑定作品行号；不要讲写作模板。"
    )


def load_mentor_prompt(name: str) -> str:
    if name not in state_mod.MENTORS:
        raise state_mod.UsageError(f"未知导师 {name!r}；可选：{', '.join(state_mod.MENTORS)}")
    path = state_mod.MENTORS_DIR / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return f"# {name}\n（缺少导师协议文件，使用运行时内置规则）"


class MentorRuntime:
    """One mentor backend per command; offline is explicit and visible."""

    def __init__(self, project: state_mod.Project, *, offline: bool = False):
        self.project = project
        if offline:
            os.environ["LEARNARK_LLM"] = "mock"
        mode = (os.environ.get("LEARNARK_LLM") or "auto").strip().lower()
        if mode == "mock" and not os.environ.get("LEARNARK_MOCK_SCRIPT") and state_mod.MOCK_FIXTURE.is_file():
            os.environ["LEARNARK_MOCK_SCRIPT"] = str(state_mod.MOCK_FIXTURE)
        self.llm = llm_core.from_env(usage_file=project.learnark / "usage.jsonl")
        if isinstance(self.llm, llm_core.MockLLM):
            # Keep unmatched offline turns honest instead of looking like teaching.
            self.llm.fallback = (
                "[离线脚本导师] 这句话没有命中离线脚本，本轮只记录状态，不产生教学证据。"
                "（离线模式不代表真实教学质量）"
            )
        self.offline = getattr(self.llm, "mode", "") == "mock"

    @property
    def label(self) -> str:
        return "[离线脚本导师] " if self.offline else ""

    def describe(self) -> dict:
        info = self.llm.describe()
        info["offline"] = self.offline
        info["label"] = self.label.strip()
        return info

    # -- turn ------------------------------------------------------------
    def run(
        self,
        kind: str,
        state: state_mod.State,
        user: str,
        *,
        artifact: dict | None = None,
        gap: dict | None = None,
        extra_context: str = "",
        runtime_next: dict | None = None,
    ):
        system = self._system(kind, state.brief)
        context = compact_context(
            state,
            artifact=artifact,
            gap=gap,
            extra=extra_context,
            project=self.project,
            handoff=self.project.latest_handoff(),
            runtime_next=runtime_next,
            include_registered=True,
            include_registered_content=(kind == "critic"),
        )
        transcript = [
            {"role": "mentor" if t.get("role") not in ("learner", "user") else "learner", "text": t.get("text", "")}
            for t in state.session.get("turns", [])
        ]
        temperature = 0.2 if kind == "critic" else (0.4 if kind == "guide" else 0.5)
        return mentor_core.run_turn(
            self.llm,
            system=system,
            context=context,
            user=user,
            transcript=transcript,
            temperature=temperature,
            max_tokens=1500,
        )

    def _system(self, kind: str, brief: dict | None = None) -> str:
        extra = {"critic": REVIEW_BLOCK_HELP, "guide": GUIDE_BLOCK_HELP}.get(kind, COACH_BLOCK_HELP)
        parts = [PROTOCOL, load_mentor_prompt(kind), extra, template_guidance(brief or {})]
        if self.offline:
            parts.append("当前是离线脚本模式：输出会标注「[离线脚本导师]」，不要假装读过文件。")
        return "\n\n---\n\n".join(parts)


# --------------------------------------------------------------------------- #
# 上下文
# --------------------------------------------------------------------------- #
def _review_history(state: state_mod.State, mid: str, limit: int = 3) -> list[str]:
    rows = []
    for review in [r for r in state.reviews.get("items", []) if r.get("milestone") == mid][-limit:]:
        scores = " ".join(f"{d['dim']}={d['score']}" for d in review.get("rubric", []))
        rows.append(f"- {review.get('id')} {scores} weighted={review.get('weighted')} pass={review.get('threshold_pass')}")
    return rows


def artifact_text(project: state_mod.Project, artifact: dict, *, with_lines: bool = False, limit: int = 8000) -> str:
    if not artifact:
        return ""
    path = artifact.get("path")
    if not path:
        return ""
    text = state_mod.read_text_safe(project.root / path, limit=limit)
    if not with_lines:
        return text
    rows = []
    for index, line in enumerate(text.splitlines()[:140], start=1):
        rows.append(f"{index:>4}| {line}")
    return "\n".join(rows)


def compact_context(
    state: state_mod.State,
    *,
    artifact: dict | None = None,
    gap: dict | None = None,
    extra: str = "",
    project: state_mod.Project | None = None,
    handoff: dict | None = None,
    runtime_next: dict | None = None,
    include_registered: bool = False,
    include_registered_content: bool = False,
) -> str:
    brief = state.brief
    m = state.current
    lines: list[str] = []
    if runtime_next:
        ref = f"（{runtime_next.get('ref')}）" if runtime_next.get("ref") else ""
        action = runtime_next.get("action", "?")
        reason = runtime_next.get("reason", "")
        lines.append(f"runtime_next（权威，本轮唯一允许推进的动作）: {action}{ref} — {reason}")
        if runtime_next.get("note"):
            lines.append(f"本轮说明: {runtime_next['note']}")
    lines.append(
        f"目标: {brief.get('goal', '')}｜模板: {brief.get('template')}｜每周 {brief.get('minutes_per_week')} 小时"
    )
    profile = brief.get("start_profile")
    if isinstance(profile, dict) and profile.get("answers"):
        lines.append(f"起点档案（仅定起点，不是能力证据）: {json.dumps(profile.get('answers'), ensure_ascii=False)}")
    if m:
        lines.append(f"当前里程碑: {m['id']}「{m.get('title', '')}」 status={m.get('status')}")
        deliverable = m.get("deliverable") or {}
        lines.append(
            f"交付物: {deliverable.get('text', '')}（允许后缀 {', '.join(deliverable.get('allowed_ext', []))}，"
            f"≥{deliverable.get('min_bytes', 20)} 字节）"
        )
        rubric = "；".join(
            f"{d['dim']} weight={d['weight']} threshold={d['threshold']}（{d.get('criteria', '')}）"
            for d in m.get("rubric", [])
        )
        lines.append(f"rubric（只读）: {rubric}")
        heaviest = logic.heaviest_dims(m)
        if heaviest:
            lines.append(f"最重维度: {', '.join(heaviest)}（defense 中该维度那问必须通过）")
        history = _review_history(state, m["id"])
        lines.append("历史评审: " + ("\n  " + "\n  ".join(history) if history else "（无）"))
        open_g = logic.open_gaps(state.gaps, m["id"])
        if open_g:
            top = logic.order_gaps(state.gaps, brief, mid=m["id"])[:3]
            lines.append("未关缺口（按 weight×缺口排序）: " + "；".join(
                f"{g['gap_id']} {g['dim']} {g.get('score')}/{g.get('threshold')} w={logic.effective_weight(g)} status={g.get('status')}"
                for g in top
            ))
        else:
            lines.append("未关缺口: （无）")
    if artifact:
        reviewed = logic.review_for_artifact(state.reviews, artifact["id"])
        lines.append(
            f"当前作品: {artifact['id']} path={artifact.get('path')} sha256={artifact.get('sha256', '')[:12]} "
            f"size={artifact.get('size')} assisted_level={artifact.get('assisted_level')} "
            f"reviewed={'yes' if reviewed else 'no'}"
        )
        if project is not None:
            excerpt = artifact_text(project, artifact, with_lines=True)
            if excerpt:
                lines.append("作品内容（带行号，最多 140 行；引用时请写行号）:\n" + excerpt)
    if include_registered:
        registered = [
            item
            for item in state.artifacts.get("items", [])
            if item.get("milestone") == (m or {}).get("id")
        ]
        if registered:
            lines.append(
                "已登记作品集合（运行时登记，全部存在；不得称其中任何文件“未登记/缺失”）: "
                + "；".join(
                    f"{item['id']}={item.get('path')} sha256={str(item.get('sha256'))[:12]}" for item in registered
                )
            )
            if project is not None and include_registered_content:
                for other in registered:
                    if artifact and other.get("id") == artifact.get("id"):
                        continue
                    text = artifact_text(project, other, with_lines=False, limit=2200)
                    if text:
                        lines.append(f"--- 其他已登记文件 {other.get('path')}（内容片段）---\n{text[:2200]}")
    if gap:
        lines.append(
            f"缺口卡: {gap['gap_id']} dim={gap.get('dim')} score={gap.get('score')}/{gap.get('threshold')} "
            f"weight={gap.get('weight')} status={gap.get('status')} attempts={gap.get('attempts')}"
        )
        lines.append(f"缺口 note: {gap.get('note', '')}")
        if m:
            rule = logic.rubric_by_dim(m).get(gap.get("dim"))
            if rule:
                lines.append(f"该维 criteria: {rule.get('criteria', '')}")
    dfn = logic.pending_defense_for_milestone(state.defense, brief.get("current_milestone") or "")
    if dfn:
        lines.append(
            "待作答防御: "
            + "；".join(
                f"{q['qid']}[{q['dim']}] {q['question']} answer={'有' if q.get('answer') else '无'}"
                for q in dfn.get("questions", [])
            )
        )
    handoff = handoff if isinstance(handoff, dict) else {}
    if handoff:
        lines.append(
            f"最近 handoff: {handoff.get('from')} -> {handoff.get('to')} reason={handoff.get('reason')} "
            f"next={handoff.get('next') or ''} open_items={'; '.join(handoff.get('open_items') or [])}"
        )
    lines.append(f"本轮导师: {state.session.get('mentor')}")
    if extra:
        lines.append(extra)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 机器块校验
# --------------------------------------------------------------------------- #
def validate_block(turn, kind: str) -> tuple[dict | None, list[str]]:
    updates = turn.updates
    if updates is None:
        reason = turn.update_error or "导师没有给出 ```learn-update 机器块"
        return None, [reason]
    problems = list(mentor_core.validate_updates(updates))
    mentor_name = updates.get("mentor")
    if mentor_name is not None and mentor_name != kind:
        # Not fatal: the runtime decides who is speaking, not the block.
        pass
    return updates, problems


def parse_score(raw) -> tuple[int, str]:
    """Clamp any proposed score into 1..4; unparseable means the lowest score, never higher."""
    if isinstance(raw, bool):
        return 1, "布尔值不是分数，按最低分 1 处理"
    if isinstance(raw, (int, float)):
        value = int(round(float(raw)))
        if value < 1:
            return 1, f"{raw} 低于 1 分，clamp 到 1"
        if value > 4:
            return 4, f"{raw} 高于 4 分，clamp 到 4"
        return value, ""
    if isinstance(raw, str):
        text = raw.strip()
        try:
            return parse_score(float(text))
        except ValueError:
            return 1, f"{raw!r} 不是 1–4 的数字，按最低分 1 处理（不因无法解析而抬高）"
    return 1, f"{type(raw).__name__} 不是分数，按最低分 1 处理"


def _evidence_ref(entry: dict) -> tuple[str, str]:
    """Return an explicit evidence reference for a rubric entry ('' when absent)."""
    line = entry.get("evidence_line")
    if isinstance(line, int) and not isinstance(line, bool) and line >= 1:
        return "evidence_line", str(line)
    if isinstance(line, str) and line.strip().isdigit():
        return "evidence_line", line.strip()
    for key in ("evidence_path", "evidence"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return "evidence_path", value.strip()
    note = str(entry.get("note") or "")
    if logic.has_line_evidence(note):
        return "note_line", note
    return "", ""


def validate_rubric(
    milestone: dict, updates: dict
) -> tuple[list[dict] | None, list[str], list[dict], list[dict]]:
    rubric = logic.rubric_by_dim(milestone)
    proposed = updates.get("rubric")
    clamped: list[dict] = []
    unevidenced: list[dict] = []
    problems: list[str] = []
    if proposed is None:
        return None, ["机器块缺少 rubric（必须覆盖全部维度）"], clamped, unevidenced
    if not isinstance(proposed, list) or not proposed:
        return None, ["rubric 必须是非空列表"], clamped, unevidenced
    seen: dict[str, dict] = {}
    for entry in proposed:
        if not isinstance(entry, dict):
            problems.append(f"rubric 条目必须是对象，收到 {type(entry).__name__}")
            continue
        dim = entry.get("dim")
        if not isinstance(dim, str) or not dim.strip():
            problems.append("rubric 条目缺少 dim")
            continue
        dim = dim.strip()
        if dim not in rubric:
            problems.append(f"新增维度 {dim!r}：rubric 只读，禁止增删维度")
            continue
        if dim in seen:
            problems.append(f"维度 {dim!r} 重复提交")
            continue
        for key in ("weight", "threshold"):
            if entry.get(key) is None:
                continue
            try:
                value = int(entry[key])
            except (TypeError, ValueError):
                problems.append(f"维度 {dim} 的 {key} 不是整数（只读字段）")
                continue
            if value != int(rubric[dim][key]):
                problems.append(f"维度 {dim} 的 {key} 被改为 {entry[key]}（rubric 只读）")
        score, why = parse_score(entry.get("score"))
        if why:
            clamped.append({"dim": dim, "from": entry.get("score"), "to": score, "why": why})
        note = entry.get("note")
        note = str(note).strip() if note is not None else ""
        threshold = int(rubric[dim]["threshold"])
        evidence_kind, evidence_ref = _evidence_ref(entry)
        if score >= threshold and not evidence_ref:
            # 证据不足不能算达标：降到 threshold-1（design: 无证据按 1–2 分）
            lowered = max(1, threshold - 1)
            unevidenced.append(
                {
                    "dim": dim,
                    "from": score,
                    "to": lowered,
                    "threshold": threshold,
                    "why": "score>=threshold 但缺少 evidence_line/evidence_path",
                }
            )
            score = lowered
        seen[dim] = {
            "dim": dim,
            "score": score,
            "note": note[:200],
            "evidence": ({"kind": evidence_kind, "ref": evidence_ref[:200]} if evidence_ref else None),
        }
    missing = [d["dim"] for d in milestone.get("rubric", []) if d["dim"] not in seen]
    if missing:
        problems.append("缺少维度: " + ", ".join(missing))
    if problems:
        return None, problems, clamped, unevidenced
    ordered = [seen[d["dim"]] for d in milestone.get("rubric", [])]
    return ordered, [], clamped, unevidenced


def validate_gap(updates: dict) -> tuple[list[dict], list[str]]:
    block = updates.get("gap")
    if block is None:
        return [], []
    if not isinstance(block, list):
        return [], ["gap 必须是列表"]
    out: list[dict] = []
    problems: list[str] = []
    for entry in block:
        if not isinstance(entry, dict) or not isinstance(entry.get("dim"), str):
            problems.append("gap 条目必须是 {dim, note} 对象")
            continue
        out.append({"dim": entry["dim"].strip(), "note": str(entry.get("note") or "")[:200]})
    return out, problems


def validate_defense(updates: dict) -> tuple[dict | None, list[str]]:
    block = updates.get("defense")
    if block is None:
        return None, []
    if not isinstance(block, dict) or not isinstance(block.get("questions"), list):
        return None, ["defense 必须是 {questions: [...]} 结构"]
    questions = []
    problems: list[str] = []
    for index, item in enumerate(block["questions"]):
        if not isinstance(item, dict):
            problems.append(f"defense.questions[{index}] 必须是对象")
            continue
        questions.append(
            {
                "qid": item.get("qid"),
                "dim": item.get("dim"),
                "question": item.get("question"),
                "answer": item.get("answer"),
                "evidence_line": item.get("evidence_line"),
                "ok": item.get("ok"),
            }
        )
    return {"questions": questions}, problems


def record_invalid(project: state_mod.Project, *, kind: str, turn, reasons: list[str], offline: bool) -> dict:
    raw = turn.raw if turn is not None else ""
    event = project.journal_append(
        "mentor_update_invalid",
        {
            "mentor": kind,
            "reasons": reasons,
            "raw_sha256": sha256_text(raw),
            "raw_excerpt": raw[:800],
            "offline": offline,
            "model": getattr(turn, "model", ""),
        },
        dedupe_key=None,
    )
    return event or {}


def record_missing(project: state_mod.Project, *, kind: str, turn, offline: bool) -> dict:
    raw = turn.raw if turn is not None else ""
    event = project.journal_append(
        "mentor_update_missing",
        {"mentor": kind, "raw_sha256": sha256_text(raw), "offline": offline, "detail": turn.update_error if turn else ""},
        dedupe_key=None,
    )
    return event or {}


def review_prompt(artifact: dict, milestone: dict, attempt: int = 1) -> str:
    return (
        f"review {artifact['id']}（{artifact.get('path')}，sha256 {artifact.get('sha256', '')[:12]}）"
        f"第 {attempt} 次评审：请按 {milestone['id']}「{milestone.get('title', '')}」的 rubric "
        f"评审已登记作品。逐维给 1–4 整数分与带证据的 note；每个达阈值的维度必须附 "
        f"evidence_line（作品行号）或 evidence_path（文件:行），没有证据请直接给到阈值以下。"
        f"gap 只列低于阈值的维度。"
    )


def defense_prompt(defense: dict) -> str:
    rows = "；".join(f"{q['qid']}（{q['dim']}）{q['question']}" for q in defense.get("questions", []))
    return (
        "defense：请核对学习者对三道防御问题的回答，逐题给出 answer 原话摘要、evidence_line（作品行号）"
        f"与 ok；答非所问或没有行号一律 ok=false。固定三问：{rows}"
    )


def gap_prompt(gap: dict, milestone: dict | None) -> str:
    title = (milestone or {}).get("title", "")
    return (
        f"gap learn {gap['gap_id']}：只讲 {gap.get('dim')} 这个维度的最小概念，并给一个 5–10 分钟微练习，"
        f"讲完把学习者送回作品改一处。当前里程碑 {title}。"
    )
