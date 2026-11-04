#!/usr/bin/env python3
"""Forge（direction-b-forge）CLI 入口。

作品驱动：不排课程，只给里程碑与 rubric；先交作品，按 rubric 打分，
低分维度即下一节微课。状态与判定全部由运行时按 design.md §7–§8 计算。

用法见 ``START_HERE.md``；``--offline`` 等价于 ``LEARNARK_LLM=mock``。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import learncore
from learncore import cli, clock
from learncore.fsutil import LearnError, StateCorrupt, atomic_write_text, sha256_text
from learncore.sync import GitSync, default_sync_message, ensure_git_identity, git_available

import forge_logic as logic
import forge_mentor as mentor_mod
import forge_state as fs

USAGE = """Forge 作品驱动 — 命令

  init --goal TEXT [--template agent-dev|email] [--minutes-per-week N] [--dir PATH] [--name SLUG]
       [--self-report "python=会一点,api=调用过"]  # 只记录学习者明说的内容，不预置
  start [--minutes N] [--ask] [--answers "能,做过,一次做完一个项目"]
  say TEXT|-                      学习者发言（- 从 stdin 读）
  status [--json]                 当前状态 + 下一步
  next [--json] [--minutes N]     纯函数计算的下一步（LLM 不能覆盖）
  task [--json]                   当前里程碑任务 + rubric
  artifact add PATH...|--note TEXT 登记作品（复制 + sha256 + assisted_level；可一次多个）
  artifact list [--json]
  review [ARTIFACT_ID]            切 critic 按 rubric 评审
  defend                          进入/查看防御性解释三问（用 say 作答）
  gap [--all] [--json]            缺口卡列表
  gap learn GAP_ID                切 guide 上缺口微课
  gap drop GAP_ID                 连续三次未过后记 stale（不算解决）
  milestones [--json]             里程碑全景
  pause [--note TEXT]             写 handoff、保存、git 同步
  switch coach|critic|guide       手动切换导师（写交接）
  sync [--message TEXT] [--recover]  written/committed/pushed 三态；--recover 并集合并 journal
  doctor [--json] [--rebuild]     自检（状态/journal/去重/git/LLM/证据链）
  export --out FILE               导出可读学习档案

全局：--project PATH（默认向上找 .learnark/）、--offline（= LEARNARK_LLM=mock）
退出码：0 成功；2 用法错误；3 状态/冲突；4 环境/网络
"""

CLAIMS = ("做完了", "完成了", "写完了", "搞定了", "做好了", "弄完了", "交了", "done", "finished")
NEGATIONS = ("没做", "未完成", "没完成", "还没", "没有做完", "没写完", "不会", "没交")

QUESTIONNAIRES = {
    "agent-dev": [
        ("api", "能否自己跑通一次 DeepSeek API 调用？", ["能", "不确定", "没有"]),
        ("tools", "是否做过带工具调用的 Agent？", ["做过", "只是看过", "没有"]),
        ("mode", "这次想要什么？", ["二十分钟见到东西", "一次做完一个项目", "先搞清概念"]),
    ],
    "email": [
        ("writing", "你平时写英文工作邮件吗？", ["经常写", "偶尔写", "几乎不写"]),
        ("focus", "这次最想练哪类邮件？", ["道歉与补救", "跨部门请求", "拒绝并保住关系"]),
        ("mode", "这次想要什么？", ["20 分钟写一封", "一次写完三封", "先看范例再写"]),
    ],
}


def questionnaire_for(template_id: str) -> list[tuple[str, str, list[str]]]:
    return QUESTIONNAIRES.get(template_id, QUESTIONNAIRES["agent-dev"])


# --------------------------------------------------------------------------- #
# 参数
# --------------------------------------------------------------------------- #
def parse_globals(argv: list[str]) -> tuple[str | None, bool, list[str]]:
    project = None
    offline = False
    rest: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--project":
            index += 1
            if index >= len(argv):
                raise fs.UsageError("--project 需要一个路径")
            project = argv[index]
        elif arg.startswith("--project="):
            project = arg.split("=", 1)[1]
        elif arg == "--offline":
            offline = True
        else:
            rest.append(arg)
        index += 1
    return project, offline, rest


def parse_flags(argv: list[str], spec: dict[str, str]) -> tuple[dict, list[str]]:
    opts: dict = {}
    positional: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg.startswith("--"):
            key = arg.split("=", 1)[0]
            if key not in spec:
                raise fs.UsageError(f"未知参数 {key}")
            if spec[key] == "bool":
                opts[key] = True
            else:
                if "=" in arg:
                    value = arg.split("=", 1)[1]
                else:
                    index += 1
                    if index >= len(argv):
                        raise fs.UsageError(f"{key} 需要一个值")
                    value = argv[index]
                opts[key] = value
        else:
            positional.append(arg)
        index += 1
    return opts, positional


def _int(value, name: str, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise fs.UsageError(f"{name} 需要一个整数，收到 {value!r}") from exc


# --------------------------------------------------------------------------- #
# 共用
# --------------------------------------------------------------------------- #
def load(project: fs.Project) -> fs.State:
    return fs.load_state(project)


def save(project: fs.Project, state: fs.State, *names: str) -> None:
    state.save(project, *names)


def active_mentor(state: fs.State) -> str:
    name = state.session.get("mentor") or "coach"
    return name if name in fs.MENTORS else "coach"


def claim_open(project: fs.Project, mid: str | None) -> bool:
    last_claim = None
    last_artifact = None
    for event in project.journal.of_kind("claim_without_artifact", "artifact_added"):
        payload = event.get("payload") or {}
        if payload.get("milestone") != mid:
            continue
        if event.get("kind") == "claim_without_artifact":
            last_claim = int(event.get("seq", 0))
        else:
            last_artifact = int(event.get("seq", 0))
    return last_claim is not None and (last_artifact is None or last_claim > last_artifact)


def next_action(project: fs.Project, state: fs.State, minutes: int | None = None) -> dict:
    mid = state.brief.get("current_milestone")
    return logic.compute_next(
        state.brief,
        state.artifacts,
        state.reviews,
        state.defense,
        state.gaps,
        minutes=minutes,
        claim_open=claim_open(project, mid),
    )


def open_items(state: fs.State) -> list[str]:
    items = []
    mid = state.brief.get("current_milestone")
    for gap in logic.order_gaps(state.gaps, state.brief, mid=mid)[:5]:
        items.append(
            f"{gap['gap_id']} {gap['dim']} {gap.get('score')}/{gap.get('threshold')} ({gap.get('status')})"
        )
    pending = logic.pending_defense_for_milestone(state.defense, mid or "")
    if pending:
        items.append(f"待作答防御 {pending['id']}：{len(pending.get('questions', []))} 问")
    if not items:
        items.append(f"{mid} 尚无未决缺口；下一步 {next_action_safe(state)}")
    return items


def next_action_safe(state: fs.State) -> str:
    nxt = logic.compute_next(state.brief, state.artifacts, state.reviews, state.defense, state.gaps)
    return f"{nxt['action']}（{nxt.get('reason', '')[:60]}）"


def switch_mentor(
    project: fs.Project,
    state: fs.State,
    target: str,
    *,
    reason: str,
    ref: str = "",
    forced: bool = False,
    note: str = "",
) -> dict | None:
    if target not in fs.MENTORS:
        raise fs.UsageError(f"未知导师 {target!r}；可选：{', '.join(fs.MENTORS)}")
    prev = active_mentor(state)
    if prev == target:
        return None
    fs.ensure_session(project, state, prev)
    handoff = project.write_handoff(
        from_mentor=prev,
        to_mentor=target,
        reason=reason,
        open_items=open_items(state),
        ref=ref,
        next_step=next_action_safe(state),
        note=note,
        session_id=state.session.get("session_id") or "",
    )
    project.journal_append(
        "mentor_switch",
        {
            "from": prev,
            "to": target,
            "reason": reason,
            "forced": forced,
            "ref": ref,
            "session": state.session.get("session_id"),
        },
        dedupe_key=f"switch:{state.session.get('session_id')}:{prev}:{target}:{reason}:{ref}",
    )
    state.session["mentor"] = target
    switches = state.session.setdefault("switches", [])
    switches.append({"from": prev, "to": target, "reason": reason, "forced": forced, "at": fs.now_iso()})
    if len(switches) > 3:
        project.journal_append(
            "mentor_thrash",
            {"session": state.session.get("session_id"), "count": len(switches), "switches": switches[-4:]},
            dedupe_key=f"mentor_thrash:{state.session.get('session_id')}",
        )
    return handoff


def finalize(project: fs.Project, state: fs.State) -> list[dict]:
    """Apply every milestone whose artifact + rubric + defense are all complete."""
    transitions: list[dict] = []
    for _ in range(len(state.milestones) + 1):
        moved = False
        for milestone in state.milestones:
            if milestone.get("status") != "active":
                continue
            evidence = logic.evidence_complete(milestone, state.artifacts, state.reviews, state.defense)
            if not evidence["ok"]:
                continue
            artifact = evidence["artifact"]
            review = evidence["review"]
            defense = evidence["defense"]
            status = logic.pass_status(artifact)
            pass_evidence = {
                "artifact_id": artifact["id"],
                "artifact_ids": review.get("artifact_ids") or [artifact["id"]],
                "artifact_sha256": artifact["sha256"],
                "review_id": review["id"],
                "defense_id": defense["id"],
                "rubric_pass": True,
                "defense_ok": defense.get("ok_count"),
                "defense_heaviest_ok": defense.get("heaviest_ok"),
                "assisted_level": artifact.get("assisted_level", 0),
                "evidence_level": "verified" if status == "passed" else "observed",
            }
            event = project.journal_append(
                "milestone_passed",
                {"milestone": milestone["id"], "status": status, "pass_evidence": pass_evidence},
                dedupe_key=f"milestone_passed:{milestone['id']}",
            )
            if event:
                pass_evidence["event_id"] = event["id"]
            milestone["status"] = status
            milestone["passed_at"] = fs.now_iso()
            milestone["pass_evidence"] = pass_evidence
            nxt = logic.next_milestone(state.brief, milestone["id"])
            if nxt is not None:
                nxt["status"] = "active"
                state.brief["current_milestone"] = nxt["id"]
            else:
                state.brief["completed"] = True
                state.brief["completed_at"] = fs.now_iso()
            transitions.append({"id": milestone["id"], "status": status, "next": (nxt or {}).get("id")})
            moved = True
            break
        if not moved:
            break
    if transitions:
        state.brief["updated_at"] = fs.now_iso()
        save(project, state, "brief")
        for item in transitions:
            if not item.get("next"):
                continue
            project.journal_append(
                "milestone_activated",
                {"milestone": item.get("next"), "after": item["id"]},
                dedupe_key=f"milestone_activated:{item.get('next')}",
            )
    return transitions


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #
def parse_self_report(raw: str) -> dict:
    """Parse ``--self-report "python=会一点,api=调用过"`` into a dict.

    Only what the learner explicitly states is stored; nothing is pre-seeded.
    """
    entries: dict[str, str] = {}
    for part in re.split(r"[,，;；]", str(raw or "")):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise fs.UsageError('--self-report 需要 key=value，例如 "python=会一点,api=调用过"')
        key, value = part.split("=", 1)
        if not key.strip():
            raise fs.UsageError("--self-report 的 key 不能为空")
        entries[key.strip()] = value.strip()
    if not entries:
        raise fs.UsageError('--self-report 为空；例如 "python=会一点,api=调用过"')
    return entries


def _write_project_docs(project: fs.Project, state: fs.State) -> None:
    brief = state.brief
    profile = brief.get("start_profile")
    writing = brief.get("template") == "email"
    help_phrase = "多步示例/邮件片段" if writing else "多步骨架/代码"
    display = brief.get("display_name") or "Forge"
    title = brief.get("goal") if display != brief.get("goal") else f"Forge · {display}"
    lines = [
        f"# {title}",
        "",
        f"项目模板：`{brief.get('template')}`　每周预算：{brief.get('minutes_per_week')} 小时　"
        f"schema_version：{brief.get('schema_version')}",
        "",
        "## 现在输入什么",
        "",
        "```powershell",
        f'python "{HERE / "learn.py"}" start',
        "```",
        "",
        "没看到进度就运行 `status`；想直接看下一步就运行 `next`。",
        "",
        "## 这个项目怎么工作",
        "",
        "1. `task` 看当前里程碑的交付物与 rubric；",
        "2. 动手做，`artifact add PATH` 登记作品（复制进 `artifacts/`，记 sha256）；",
        "3. `review` 让 critic 按 rubric 打分；低分维度变成缺口卡；",
        "4. `gap learn GAP_ID` 让 guide 讲最小概念；改完重新登记 + `review`；",
        "5. 四维达标后 `defend` 回答三问；运行时三者齐备才算里程碑通过。",
        "",
        "## 记录在哪",
        "",
        "- `.learnark/`：项目状态、事件流 `journal/events.jsonl`、交接 `handoff/latest.md`；",
        "- `sessions/`：每次会话一份 Markdown；",
        "- `artifacts/`：登记过的作品副本（按 sha256 校验）。",
        "",
        "## 规则（运行时执行，导师不能改）",
        "",
        "- rubric 的维度、权重、阈值只读；导师改权重会被整次拒绝；",
        "- 分数只能是 1–4 整数，越界会被 clamp；达阈值的维度必须带 evidence_line/evidence_path，",
        "  否则运行时降到 threshold-1 并记 `rubric_unevidenced`；",
        "- 没有登记作品、没有 rubric、没有防御解释，里程碑不会通过；",
        "- 自述「我做完了」不算证据，只会写一条 `claim_without_artifact`；",
        "- 起点三问只在你回答时记录（`start --ask` 或 `--answers`）；`self_report` 只写你明说的内容",
        "  （`init --self-report`），不预置；",
        "- 导师漏写帮助等级时，运行时会按“要答案 + " + help_phrase + "”推断（`help_level_inferred`），",
        "  `status` 显示最近/最高帮助等级；",
        "- 导师动作必须服从 `next`；每轮回复后有一行 `▶ 唯一动作`，冲突会记 `mentor_next_conflict`；",
        "- `start --minutes` 会写入 `start_profile.slice_minutes`，后续 `next`/`review`/`defend` 都用它；",
        "- `artifact add` 可一次登记多个交付物；`guide` 的缺口微课是官方学习路径，不计入作品 `assisted_level`。",
        "- 长文本或被 shell 截断的消息用 `say -` 从 stdin 重发，导师不得据此猜错误原因。",
        "- git 分叉：`sync` 自动并集合并 journal（按 id 去重）；快照冲突退出 3 并列出文件，",
        "  手动入口 `sync --recover`；`.gitattributes` 的 `* -text` 保证克隆后 sha 不变。",
        "",
    ]
    if isinstance(profile, dict) and profile.get("answers"):
        lines.insert(3, f"起点档案（仅定起点，不是能力证据）：{json.dumps(profile.get('answers'), ensure_ascii=False)}")
        lines.insert(4, "")
    atomic_write_text(project.root / "README.md", "\n".join(lines) + "\n")

    agents = [
        "# AGENTS.md · 给 DSH / 其他 Agent 的入口说明",
        "",
        "这是一个 LearnArk · Forge（作品驱动）学习项目。开始任何操作前：",
        "",
        "1. 先运行 `start`（或 `status --json`）读取权威状态；不要凭聊天记录推断进度。",
        "2. 按导师协议继续：当前导师、当前里程碑、rubric、缺口卡、未决防御都在状态里。",
        "3. 不得凭空编造学习记录：作品只能由 `artifact add` 登记，分数只能由 `review` 写入，",
        "   里程碑通过只能由运行时在「作品 + rubric 达标 + defense 通过」后写入。",
        "",
        "## 命令",
        "",
        f'入口：`python "{HERE / "learn.py"}"`（Windows 可用 `learn.cmd`）。',
        "`start` / `say TEXT` / `task` / `artifact add PATH` / `review` / `defend` /",
        "`gap [--all]` / `gap learn ID` / `gap drop ID` / `next --json` / `status --json` /",
        "`pause` / `switch coach|critic|guide` / `milestones` / `sync` / `doctor` / `export --out FILE`。",
        "",
        "## 规则",
        "",
        "- rubric 维度/权重/阈值只读；非法评审写 `review_invalid` 且不落库。",
        "- 分数由运行时 clamp 到 1–4；缺维/多维/改权重整次拒绝。",
        "- 达阈值的维度必须带 `evidence_line`/`evidence_path`；缺失则降到 threshold-1 并记 `rubric_unevidenced`。",
        "- 自述完成不升级；`assisted_level` 只由 coach/critic 帮助决定，guide 微课不计；",
        "  `assisted_level >= 2` 的作品通过时记 `passed_assisted`。",
        "- 缺口卡只能由后续评审关闭；`gap drop` 只记 `stale`，不算解决。",
        "- 导师动作必须服从 `runtime_next`；界面上的「▶ 唯一动作」为准，冲突记 `mentor_next_conflict`。",
        "- 导师漏写 `help_level` 时按“要答案 + " + help_phrase + "”推断，记 `help_level_inferred`；`status` 显示最近/最高帮助。",
        "- 起点三问只在学习者回答时记录；`self_report` 只写学习者明说的内容。",
        "- `start --minutes` 持久化切片；`artifact add` 支持一次多个路径；长文本用 `say -`。",
        "- git 分叉：journal-only 冲突可 `sync --recover` 并集合并；快照冲突退出 3 并列出文件，不 force push。",
        "- 离线模式（`--offline` / `LEARNARK_LLM=mock`）的输出标注「[离线脚本导师]」，",
        "  不代表真实教学质量，也不得当作真实 LLM 证据。",
        "",
    ]
    atomic_write_text(project.root / "AGENTS.md", "\n".join(agents) + "\n")


def cmd_init(project_arg: str | None, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(
        args,
        {
            "--goal": "value",
            "--minutes-per-week": "value",
            "--template": "value",
            "--dir": "value",
            "--name": "value",
            "--self-report": "value",
            "--json": "bool",
        },
    )
    if positional:
        raise fs.UsageError(f"init 不接受位置参数 {positional!r}")
    target = Path(opts.get("--dir") or ".").expanduser()
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()
    template_id = str(opts.get("--template") or "agent-dev")
    template = fs.load_template(template_id)
    target.mkdir(parents=True, exist_ok=True)
    project = fs.Project.create(target)
    already = project.exists()
    created = False
    stated = parse_self_report(opts["--self-report"]) if opts.get("--self-report") else {}

    if already:
        state = load(project)
        project_doc = state.project
        brief = state.brief
        if opts.get("--template") and project_doc.get("template") not in (None, "", template_id):
            raise fs.ForgeError(
                f"{project.root} 已存在（模板 {project_doc.get('template')}），不能改成 {template_id}；"
                "换模板请 init 到新目录"
            )
        goal = str(
            opts.get("--goal")
            or project_doc.get("goal")
            or brief.get("goal")
            or template.get("goal_default")
        )
        minutes = _int(
            opts.get("--minutes-per-week"),
            "--minutes-per-week",
            int(
                project_doc.get("minutes_per_week")
                or brief.get("minutes_per_week")
                or template.get("minutes_per_week_default", 12)
            ),
        )
        project_doc.update({"goal": goal, "minutes_per_week": minutes, "updated_at": fs.now_iso()})
        brief.update({"goal": goal, "minutes_per_week": minutes, "updated_at": fs.now_iso()})
        if stated:
            profile_doc = project_doc.setdefault("learner_profile", {})
            profile_doc["id"] = profile_doc.get("id") or "P1"
            profile_doc["self_report"] = stated
            profile_doc["source"] = "learner_stated（只记录学习者明说的内容；自述不是能力证据）"
            profile_doc["recorded_at"] = fs.now_iso()
        save(project, state, "project", "brief")
    else:
        goal = str(opts.get("--goal") or template.get("goal_default") or "用作品学会一个主题")
        minutes = _int(
            opts.get("--minutes-per-week"),
            "--minutes-per-week",
            int(template.get("minutes_per_week_default", 12)),
        )
        slug = str(opts.get("--name") or fs.slugify(goal))
        project_doc = {
            "schema_version": fs.SCHEMA_VERSION,
            "slug": slug,
            "goal": goal,
            "template": template_id,
            "template_id": template_id,
            "constraints": list(template.get("constraints", [])),
            "minutes_per_week": minutes,
            "learner_profile": {
                "id": "P1",
                "source": (
                    "learner_stated（只记录学习者明说的内容；自述不是能力证据）"
                    if stated
                    else "none（尚未提供自述；用 init --self-report 或对话补充）"
                ),
                "self_report": stated,
            },
            "started": False,
            "created_at": fs.now_iso(),
            "updated_at": fs.now_iso(),
        }
        brief = fs.build_brief(template, goal=goal, minutes_per_week=minutes, slug=slug)
        state = fs.State(
            project=project_doc,
            brief=brief,
            artifacts={"schema_version": fs.SCHEMA_VERSION, "items": []},
            reviews={"schema_version": fs.SCHEMA_VERSION, "items": []},
            gaps={"schema_version": fs.SCHEMA_VERSION, "items": []},
            defense={"schema_version": fs.SCHEMA_VERSION, "items": []},
            session={"schema_version": fs.SCHEMA_VERSION, "mentor": "coach"},
        )
        save(project, state, "project", "brief", "artifacts", "reviews", "gaps", "defense")
        created = True

    _write_project_docs(project, state)

    git_note = ""
    if git_available():
        sync = GitSync(project.root, include=["."])
        try:
            created_files = sync.ensure_repository()
            ensure_git_identity(project.root)
            if created_files:
                git_note = "git: " + ", ".join(created_files)
        except LearnError as exc:
            git_note = f"git 初始化失败（不影响学习记录）：{exc}"
    else:
        git_note = "未找到 git：学习记录仍写盘，但 sync 无法提交"

    project.journal_append(
        "init",
        {
            "slug": state.project.get("slug"),
            "goal": state.brief.get("goal"),
            "template": state.brief.get("template"),
            "created": created,
            "offline": offline,
        },
        dedupe_key=f"init:{state.project.get('slug')}",
    )
    nxt = next_action(project, state)
    if opts.get("--json"):
        cli.emit_json(
            {
                "ok": True,
                "created": created,
                "reused": already,
                "project": str(project.root),
                "template": state.brief.get("template"),
                "goal": state.brief.get("goal"),
                "current_milestone": state.brief.get("current_milestone"),
                "next": nxt,
                "git": git_note,
            }
        )
        return 0
    print(f"{'已创建' if created else '已存在，已复用'}：{project.root}")
    print(
        f"目标：{state.brief.get('goal')}｜模板：{state.brief.get('template')}｜"
        f"每周 {state.brief.get('minutes_per_week')} 小时"
    )
    print(f"当前里程碑：{state.brief.get('current_milestone')}｜下一步：{nxt['action']}")
    print("入口：")
    print(f'  python "{HERE / "learn.py"}" start')
    if git_note:
        print(git_note)
    print("文档：README.md（1 分钟上手）、AGENTS.md（给 Agent 的规则）、START_HERE.md（版本入口）")
    return 0


# --------------------------------------------------------------------------- #
# 问答 / 开头
# --------------------------------------------------------------------------- #
def _last_model(project: fs.Project) -> str | None:
    for event in reversed(list(project.journal.of_kind("mentor_turn"))):
        model = (event.get("payload") or {}).get("model")
        if model:
            return str(model)
    return None


def _last_session_payload(
    project: fs.Project, state: fs.State, *, prefer_previous: bool = False
) -> dict | None:
    """Journal-derived last session summary; optionally skip a just-opened empty session."""
    counts: dict[str, dict] = {}
    for event in project.journal.of_kind("mentor_turn"):
        payload = event.get("payload") or {}
        session_id = payload.get("session")
        if not session_id:
            continue
        row = counts.setdefault(
            str(session_id),
            {"session_id": str(session_id), "mentor": payload.get("mentor"), "turns": 0, "at": event.get("at")},
        )
        row["turns"] += 1
        row["mentor"] = payload.get("mentor") or row["mentor"]
        row["at"] = event.get("at") or row["at"]
    if not counts:
        return None
    current = str(state.session.get("session_id") or "")
    ordered = list(counts.values())
    if prefer_previous and current in counts and counts[current]["turns"] <= 1 and len(counts) > 1:
        ordered = [row for row in ordered if row["session_id"] != current]
    return ordered[-1] if ordered else None


def _profile_from_answers(
    answers: dict[str, str], answered: bool, template_id: str, first_mid: str
) -> dict:
    mode = answers.get("mode", "")
    if template_id == "email":
        fast = (
            answers.get("writing") == "经常写"
            and answers.get("focus") == "拒绝并保住关系"
            and mode == "一次写完三封"
        )
        mapped = f"{first_mid}-second-half" if fast else f"{first_mid}-first"
        strict = "strict" if mode == "一次写完三封" else "standard"
        slice_minutes = 60 if mode == "一次写完三封" else 20
    else:
        fast = answers.get("api") == "能" and answers.get("tools") == "做过" and mode == "一次做完一个项目"
        mapped = f"{first_mid}-second-half" if fast else f"{first_mid}-first"
        strict = "strict" if mode == "一次做完一个项目" else "standard"
        slice_minutes = 60 if mode == "一次做完一个项目" else 20
    return {
        "answers": answers,
        "answered": answered,
        "mapped_start": mapped,
        "strictness": strict,
        "slice_minutes": slice_minutes,
        "recorded_at": fs.now_iso(),
        "note": "只用于定起点/严苛档/切片，不作能力证据",
    }


def collect_profile(opts: dict, template_id: str, first_mid: str) -> dict:
    questions = questionnaire_for(template_id)
    raw = opts.get("--answers")
    if raw:
        parts = [p.strip() for p in re.split(r"[,，;；]", str(raw)) if p.strip()]
        if len(parts) != len(questions):
            example = ",".join(options[0] for _, _, options in questions)
            raise fs.UsageError(f'--answers 需要 {len(questions)} 个值，例如 --answers "{example}"')
        answers = {key: parts[i] for i, (key, _, _) in enumerate(questions)}
    elif opts.get("--ask"):
        answers = {}
        print("首次进入：三个定位问题只用来定起点，不作能力证据；直接回车记「未回答」。")
        for key, question, options in questions:
            print(f"  {question}")
            for idx, option in enumerate(options, start=1):
                print(f"    {idx}) {option}")
            try:
                raw_answer = input("  选择编号（回车=未回答）：").strip()
            except EOFError:
                raw_answer = ""
            if raw_answer.isdigit() and 1 <= int(raw_answer) <= len(options):
                answers[key] = options[int(raw_answer) - 1]
            else:
                answers[key] = "未回答"
        return _profile_from_answers(answers, True, template_id, first_mid)
    else:
        # 非交互模式绝不阻塞 stdin：默认答案 + 明确标注未回答，并提示 --ask 补答。
        answers = {key: "未回答" for key, _, _ in questions}
        print("首次进入：三个定位问题（本次非交互，记录为「未回答」，可用 start --ask 补答）")
        for key, question, options in questions:
            print(f"  - {question} 可选：{' / '.join(options)}")
        profile = _profile_from_answers(answers, False, template_id, first_mid)
        profile["note"] = (
            "非交互模式：跳过定位问题，默认从第一个里程碑开始；可运行 start --ask 补答。只定起点，不作能力证据"
        )
        return profile
    return _profile_from_answers(answers, True, template_id, first_mid)


def _coach_opening_extra(state: fs.State, project: fs.Project) -> str:
    nxt = next_action(project, state)
    handoff = project.latest_handoff()
    bits = [f"运行时计算的下一步: {nxt['action']} —— {nxt.get('reason', '')}"]
    if handoff:
        bits.append(
            f"上次交接: {handoff.get('from')} -> {handoff.get('to')}（{handoff.get('reason')}），"
            f"未决: {'; '.join(handoff.get('open_items') or [])[:300]}"
        )
    bits.append("请用一句话接续，不要重排课程；只给今天一个可验证动作。")
    return "\n".join(bits)


def _record_turn(
    project: fs.Project,
    state: fs.State,
    *,
    mentor: str,
    turn_index: int,
    learner_text: str,
    mentor_text: str,
    payload: dict,
    record: dict | None,
    kind: str = "turn",
    activity: str = "",
) -> None:
    project.journal_append(
        "learner_say",
        {"session": state.session.get("session_id"), "turn": turn_index, "text": learner_text, "mentor": mentor},
        dedupe_key=f"say_learner:{state.session.get('session_id')}:{turn_index}",
    )
    project.journal_append(
        "mentor_turn",
        {
            "session": state.session.get("session_id"),
            "turn": turn_index,
            "mentor": mentor,
            "text": mentor_text,
            "offline": payload.get("offline", False),
            "help_level": payload.get("help_level"),
            "attempt": payload.get("attempt"),
            "misconception": payload.get("misconception"),
            "next": payload.get("next"),
            "runtime_next": payload.get("runtime_next"),
            "help_level_inferred": payload.get("help_level_inferred", False),
            "model": payload.get("model"),
        },
        dedupe_key=f"say:{state.session.get('session_id')}:{turn_index}",
    )
    fs.append_session_turn(
        project,
        state,
        learner_text=learner_text,
        mentor_text=mentor_text,
        mentor=mentor,
        record={**(record or {}), "runtime_next": payload.get("runtime_next")},
        activity=activity or "start",
        kind=kind,
    )
    state.session["turn_index"] = turn_index


# --------------------------------------------------------------------------- #
# start
# --------------------------------------------------------------------------- #
def cmd_start(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(
        args,
        {"--minutes": "value", "--ask": "bool", "--answers": "value", "--json": "bool", "--peek": "bool"},
    )
    if positional:
        raise fs.UsageError(f"start 不接受位置参数 {positional!r}")
    state = load(project)
    if not state.brief.get("milestones"):
        raise fs.ForgeError("brief.json 没有里程碑；请重新运行 init --template ...")
    template_id = str(state.brief.get("template") or "agent-dev")
    first_mid = state.brief["milestones"][0]["id"]
    first_entry = not state.brief.get("start_profile")
    explicit_profile = opts.get("--answers") is not None or bool(opts.get("--ask"))
    profile_default = (state.brief.get("start_profile") or {}).get("slice_minutes") or state.brief.get(
        "session_minutes_default"
    ) or 25
    minutes = _int(opts.get("--minutes"), "--minutes", int(profile_default))
    if opts.get("--peek"):
        # 只读：不建会话、不调用导师、不写任何状态
        nxt = next_action(project, state, minutes)
        task = logic.opening_task(state.brief, state.current, minutes)
        handoff = project.latest_handoff()
        if opts.get("--json"):
            cli.emit_json({"peek": True, "goal": state.brief.get("goal"), "milestone": state.brief.get("current_milestone"),
                           "status": (state.current or {}).get("status"), "task": task,
                           "next": nxt, "handoff": handoff,
                           "last_session": _last_session_payload(project, state, prefer_previous=True)})
            return 0
        print(f"Forge · {state.brief.get('goal')}（只读预览，未开始/未改状态）")
        print(f"当前里程碑：{state.brief.get('current_milestone')}｜status={(state.current or {}).get('status')}")
        print(f"本步任务（{task['task_id']}）：{task['text']}")
        print(authority_line(nxt))
        if handoff:
            print(f"上次交接：{handoff.get('from')} → {handoff.get('to')}（{handoff.get('reason')}）")
        return 0
    profile_recorded = None
    if first_entry or explicit_profile:
        profile_recorded = collect_profile(opts, template_id, first_mid)
        state.brief["start_profile"] = profile_recorded
        state.brief["updated_at"] = fs.now_iso()
        save(project, state, "brief")
    if opts.get("--minutes") is not None:
        # round-02 #3: --minutes must persist into start_profile, not only this turn
        profile = dict(state.brief.get("start_profile") or {})
        profile["slice_minutes"] = 20 if minutes <= 30 else 60
        profile["slice_source"] = "--minutes"
        profile["minutes_requested"] = minutes
        state.brief["start_profile"] = profile
        state.brief["updated_at"] = fs.now_iso()
        save(project, state, "brief")
        if profile_recorded is not None:
            profile_recordedupdate = {
                "slice_minutes": profile["slice_minutes"],
                "slice_source": profile["slice_source"],
                "minutes_requested": profile["minutes_requested"],
            }
            profile_recorded.update(profile_recordedupdate)
    state.project["started"] = True
    state.project["updated_at"] = fs.now_iso()
    transitions = finalize(project, state)
    previous = bool(state.artifacts.get("items")) or bool(state.reviews.get("items"))
    fresh = (not state.session.get("session_id")) or bool(state.session.get("ended_at"))
    fs.ensure_session(project, state, "coach")
    if profile_recorded is not None:
        project.journal_append(
            "start_profile_recorded",
            {
                "answers": profile_recorded.get("answers"),
                "answered": profile_recorded.get("answered"),
                "mapped_start": profile_recorded.get("mapped_start"),
                "strictness": profile_recorded.get("strictness"),
                "slice_minutes": profile_recorded.get("slice_minutes"),
                "slice_source": profile_recorded.get("slice_source"),
                "minutes_requested": profile_recorded.get("minutes_requested"),
                "explicit": explicit_profile,
                "session": state.session.get("session_id"),
            },
            dedupe_key="profile:"
            + sha256_text(
                json.dumps(profile_recorded.get("answers") or {}, ensure_ascii=False, sort_keys=True)
            )[:16],
        )
    start_task = logic.opening_task(state.brief, state.current, minutes)
    start_next = next_action(project, state, minutes)
    start_next.setdefault("task_id", start_task["task_id"])
    start_next.setdefault("task_text", start_task["text"])
    runtime = mentor_mod.MentorRuntime(project, offline=offline)
    mentor_text = ""
    record: dict = {}
    actual_model = None
    if fresh and int(state.session.get("turn_index", 0) or 0) == 0:
        greeting = "开始学习" if (first_entry and not previous) else "继续学习"
        turn = runtime.run(
            "coach",
            state,
            greeting,
            extra_context=_coach_opening_extra(state, project)
            + f"\n固定任务（{start_task['task_id']}）：{start_task['text']}",
            runtime_next=start_next,
        )
        actual_model = getattr(turn, "model", None) or runtime.llm.model
        updates, problems = mentor_mod.validate_block(turn, "coach")
        payload = {
            "offline": runtime.offline,
            "help_level": None,
            "runtime_next": start_next,
            "model": actual_model,
        }
        record = {"activity": "start", "offline": runtime.offline}
        if updates is None:
            mentor_mod.record_missing(project, kind="coach", turn=turn, offline=runtime.offline)
        elif problems:
            mentor_mod.record_invalid(project, kind="coach", turn=turn, reasons=problems, offline=runtime.offline)
        else:
            payload["help_level"] = updates.get("help_level")
            payload["attempt"] = updates.get("attempt")
            payload["misconception"] = updates.get("misconception")
            payload["next"] = updates.get("next")
            record.update(
                help_level=updates.get("help_level"),
                attempt=updates.get("attempt"),
                misconception=updates.get("misconception"),
                next=updates.get("next"),
            )
            _apply_help_and_attempt(project, state, "coach", 1, updates)
        mentor_text = runtime.label + turn.text
        _record_turn(
            project,
            state,
            mentor="coach",
            turn_index=1,
            learner_text=greeting,
            mentor_text=mentor_text,
            payload=payload,
            record=record,
            kind="start",
            activity="start",
        )
    save(project, state, "session", "project", "brief", "gaps")
    nxt = next_action(project, state, minutes)
    profile = state.brief.get("start_profile") or {}
    handoff = project.latest_handoff()

    if opts.get("--json"):
        cli.emit_json(
            {
                "started": True,
                "first_entry": first_entry,
                "profile": profile,
                "current_milestone": state.brief.get("current_milestone"),
                "milestone_status": (state.current or {}).get("status"),
                "next": nxt,
                "mentor": active_mentor(state),
                "offline": runtime.offline,
                "mentor_text": mentor_text,
                "handoff": handoff,
                "transitions": transitions,
            }
        )
        return 0

    current = state.current or {}
    print(f"Forge · {state.brief.get('goal')}")
    print(
        f"模板 {state.brief.get('template')}｜当前里程碑 {current.get('id')}「{current.get('title', '')}」"
        f" status={current.get('status')}｜每周 {state.brief.get('minutes_per_week')} 小时"
    )
    configured = getattr(runtime.llm, "model", None) or "?"
    observed = _last_model(project) or configured
    if runtime.offline:
        mode = "离线脚本导师（LEARNARK_LLM=mock，不代表真实教学质量）"
    elif observed != configured:
        mode = f"在线导师（配置 {configured} / 实际 {observed}）"
    else:
        mode = f"在线导师（{configured}）"
    print(f"模式：{mode}")
    if first_entry or explicit_profile:
        print(
            "起点档案（已记录）："
            + json.dumps(profile.get("answers"), ensure_ascii=False)
            + f" → {profile.get('mapped_start')}（{profile.get('strictness')}，"
            f"{profile.get('slice_minutes')} 分钟切片；只定起点，不作能力证据）"
        )
    if handoff:
        print(
            f"上次停在哪：{handoff.get('from')} → {handoff.get('to')}（{handoff.get('reason')}）"
            f"｜未决：{'; '.join(handoff.get('open_items') or [])[:200]}"
        )
    for item in transitions:
        print(f"[运行时] 里程碑 {item['id']} 通过（{item['status']}），已激活 {item.get('next') or '收尾'}")
    if mentor_text:
        print("")
        print(mentor_text)
    print("")
    print(authority_line(nxt))
    if nxt["action"] in ("do_task", "artifact_required"):
        fixed_task = logic.opening_task(state.brief, current, minutes)
        print(f"本步任务（{nxt.get('task_id') or fixed_task['task_id']}）：{nxt.get('task_text') or fixed_task['text']}")
    print(f"切片：{nxt.get('slice')} 分钟 — {nxt.get('slice_hint', '')}")
    deliverable = (current.get("deliverable") or {}).get("text", "")
    if deliverable:
        print(f"交付物：{deliverable}")
    print("登记作品：artifact add <PATH>；查看任务：task；查看下一步：next --json")
    return 0


# --------------------------------------------------------------------------- #
# say
# --------------------------------------------------------------------------- #
# -- 帮助等级推断（round-02 #1） ------------------------------------------- #
ASK_FOR_ANSWER = re.compile(
    r"(直接(给|把|写)|给我(答案|代码|完整|实现)|帮我写|完整(代码|实现)|给个?骨架|照(着|抄)|抄一遍|"
    r"别绕了|不想写|代写|答案给我|just\s+give\s+me)",
    re.IGNORECASE,
)
STEP_LINE = re.compile(r"(?m)^\s*(?:\d+[.、)）]|[一二三四五六七八九十]+[、.)）])")
INLINE_STEPS = re.compile(r"(?:[一二三四五六七八九十]+)[、，,]\s*\S")
INLINE_PLAN = re.compile(r"(?:按|分|下面|以下)\s*[两二三四五六七八九十\d]+\s*步")


def asks_for_answer(text: str) -> bool:
    return bool(ASK_FOR_ANSWER.search(text or ""))


def has_skeleton(text: str) -> bool:
    """Code block, numbered step lines, or an explicit inline plan (“按四步：一…二…”)."""
    body = text or ""
    if "```" in body:
        return True
    if len(STEP_LINE.findall(body)) >= 3:
        return True
    # 行内“一，…；二，…”只有配合“按/分 N 步”才算骨架，避免把“runnability 三、contract 三”当步骤
    return bool(INLINE_PLAN.search(body)) and len(INLINE_STEPS.findall(body)) >= 3


def infer_help_level(learner_text: str, mentor_text: str, updates: dict) -> tuple[int | None, dict | None]:
    """Infer the help actually given when the mentor forgot to declare it.

    - learner explicitly asked for the answer/skeleton + reply has a skeleton/code -> 3
    - reply has a multi-step skeleton/code without being asked -> 2
    Declared levels are never lowered, only raised to at least the inferred level.
    """
    declared = updates.get("help_level")
    if isinstance(declared, bool) or not isinstance(declared, int):
        declared = None
    if not has_skeleton(mentor_text):
        return declared, None
    asked = asks_for_answer(learner_text)
    target = 3 if asked else 2
    if declared is None or declared < target:
        return target, {
            "declared": declared,
            "inferred": target,
            "asked_for_answer": asked,
            "skeleton": True,
            "why": (
                "学习者明确要答案/代码，导师给了多步骨架或代码"
                if asked
                else "导师给了多步骨架或代码（分步引导），至少记 L2"
            ),
        }
    return declared, None


# -- 导师动作与 runtime_next 冲突（round-02 #2） --------------------------- #
_ACTION_CONFLICT = {
    "review": re.compile(
        r"(先|去|立即|马上|赶紧|接下来)[^。；\n]{0,10}review|重新\s*review|再\s*review",
        re.IGNORECASE,
    ),
    "gap_learn": re.compile(r"(先|去|立即|马上)[^。；\n]{0,10}(gap learn|微课)|gap learn\s+g-", re.IGNORECASE),
    "defend": re.compile(r"(先|去|立即|马上)[^。；\n]{0,10}(defend|防御)", re.IGNORECASE),
    "artifact_add": re.compile(
        r"(先|去|立即|马上)[^。；\n]{0,10}artifact add|重新\s*artifact add|回到作品",
        re.IGNORECASE,
    ),
}


def detect_next_conflict(runtime_next: dict | None, text: str, updates: dict) -> dict | None:
    """Detect a mentor instruction that names an action other than runtime_next."""
    action = (runtime_next or {}).get("action")
    if not action:
        return None
    structured = (updates or {}).get("action")
    if isinstance(structured, str) and structured and structured != action:
        return {"mentioned": structured, "source": "block.action"}
    # 只看导师正文：机器块的 next 天然描述“本轮之后做什么”，不算冲突
    haystack = text or ""
    for name, pattern in _ACTION_CONFLICT.items():
        if name == action:
            continue
        match = pattern.search(haystack)
        if match:
            return {"mentioned": name, "source": "text", "excerpt": match.group(0)[:120]}
    return None


def help_stats(project: fs.Project) -> dict:
    """Last / maximum help level actually recorded, plus how many were inferred."""
    last = None
    last_mentor = None
    last_turn = None
    best = 0
    best_mentor = None
    inferred = 0
    for event in project.journal.of_kind("mentor_turn"):
        payload = event.get("payload") or {}
        level = payload.get("help_level")
        if isinstance(level, int) and not isinstance(level, bool):
            last = level
            last_mentor = payload.get("mentor")
            last_turn = payload.get("turn")
            if level > best:
                best = level
                best_mentor = payload.get("mentor")
        if payload.get("help_level_inferred"):
            inferred += 1
    return {
        "last_help_level": last,
        "last_help_mentor": last_mentor,
        "last_help_turn": last_turn,
        "max_help_level": best if best else None,
        "max_help_mentor": best_mentor,
        "inferred_count": inferred,
    }


def authority_line(runtime_next: dict | None) -> str:
    runtime_next = runtime_next or {}
    ref = f"（{runtime_next.get('ref')}）" if runtime_next.get("ref") else ""
    reason = str(runtime_next.get("reason") or "").strip()
    line = f"▶ 唯一动作：{runtime_next.get('action', '?')}{ref}"
    return f"{line} — {reason}" if reason else line


# -- 评审 note 的“无依据断言”（round-03 #4） -------------------------------- #
_NUMERIC_CLAIM = re.compile(r"(上限|最多|不超过|cap|limit)[^。；\n]{0,8}\d+|\d+\s*步", re.IGNORECASE)
_DENIAL_CLAIM = re.compile(
    r"(没有|没|未|无)[^。；\n]{0,8}(看到|登记|找到|有)[^。；\n]{0,8}(作品|artifact|文件)",
    re.IGNORECASE,
)


def unsupported_numeric_claims(dims: list[dict]) -> list[dict]:
    """Rubric notes that assert a number (e.g. “6 步上限”) without any evidence ref."""
    claims: list[dict] = []
    for dim in dims:
        note = str(dim.get("note") or "")
        match = _NUMERIC_CLAIM.search(note)
        if not match:
            continue
        if dim.get("evidence") or logic.has_line_evidence(note):
            continue
        claims.append({"dim": dim.get("dim"), "claim": match.group(0)[:80], "note": note[:200]})
    return claims


def mentor_denies_registered_artifacts(text: str, registered: list[dict]) -> bool:
    """Coach/guide claims no artifact exists although the runtime has some."""
    if not registered:
        return False
    return bool(_DENIAL_CLAIM.search(text or ""))


def strip_unsupported_claims(dims: list[dict], claims: list[dict]) -> None:
    """Remove unsupported numeric claims from the visible rubric note (kept in the event)."""
    for claim in claims:
        dim = next((item for item in dims if item.get("dim") == claim.get("dim")), None)
        if dim is None:
            continue
        note = str(dim.get("note") or "")
        if not note:
            continue
        dim["raw_note"] = note
        dim["note"] = note.replace(claim.get("claim", ""), "（该数量断言缺行号证据，已省略）")[:200]


def is_completion_claim(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    if any(neg in lowered for neg in NEGATIONS):
        return False
    return any(claim in lowered for claim in CLAIMS)


def _apply_help_and_attempt(
    project: fs.Project,
    state: fs.State,
    mentor: str,
    turn_index: int,
    updates: dict,
    *,
    help_override: int | None = None,
    inference: dict | None = None,
) -> dict:
    """Record help level / attempt events; never turns self-report into mastery."""
    session_id = state.session.get("session_id")
    help_level = help_override if help_override is not None else updates.get("help_level")
    record: dict = {}
    if isinstance(help_level, int) and not isinstance(help_level, bool):
        record["help_level"] = help_level
    if inference:
        project.journal_append(
            "help_level_inferred",
            {
                "session": session_id,
                "turn": turn_index,
                "mentor": mentor,
                "declared": inference.get("declared"),
                "inferred": inference.get("inferred"),
                "asked_for_answer": inference.get("asked_for_answer"),
                "why": inference.get("why"),
            },
            dedupe_key=f"help_inferred:{session_id}:{turn_index}",
        )
        record["help_level_inferred"] = inference
    attempt = updates.get("attempt")
    if isinstance(attempt, dict) and attempt.get("activity_id"):
        record["attempt"] = attempt
        project.journal_append(
            "attempt",
            {
                "session": session_id,
                "turn": turn_index,
                "activity_id": attempt.get("activity_id"),
                "correct": bool(attempt.get("correct")),
                "help_level": help_level,
                "source": "observed",
            },
            dedupe_key=f"attempt:{session_id}:{turn_index}:{attempt.get('activity_id')}",
        )
        # 路径 (b)：微课 + 微练习，help_level<=1 且答对 -> 未在作品复验
        mid = state.brief.get("current_milestone")
        learning = [g for g in logic.open_gaps(state.gaps, mid) if g.get("status") == "learning"]
        if (
            attempt.get("correct")
            and isinstance(help_level, int)
            and help_level <= 1
            and learning
            and mentor in ("guide", "coach")
        ):
            touched = logic.mark_unverified_micro_practice(state.gaps, mid)
            for gap in touched:
                project.journal_append(
                    "gap_unverified",
                    {"gap_id": gap["gap_id"], "help_level": help_level, "session": session_id, "card": gap},
                    dedupe_key=f"gap_unverified:{gap['gap_id']}:{session_id}",
                )
            record["micro_practice"] = [g["gap_id"] for g in touched]
    if updates.get("misconception"):
        record["misconception"] = str(updates["misconception"])[:200]
        project.journal_append(
            "misconception",
            {"session": session_id, "turn": turn_index, "label": str(updates["misconception"])[:200]},
            dedupe_key=f"misconception:{session_id}:{turn_index}",
        )
    if updates.get("next"):
        record["next"] = str(updates["next"])[:300]
    return record


def _defense_materials(project: fs.Project, state: fs.State, milestone: dict) -> str:
    """Everything the learner actually received: fixed task + registered artifacts."""
    texts = [logic.opening_task(state.brief, milestone, None)["text"]]
    for item in logic.artifacts_for(state.artifacts, milestone["id"]):
        path = project.root / str(item.get("path") or "")
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(texts)


def _record_defense_unsupported(project: fs.Project, defense: dict) -> None:
    items = defense.get("unsupported_questions") or []
    if not items:
        return
    project.journal_append(
        "defense_question_unsupported",
        {
            "defense_id": defense.get("id"),
            "milestone": defense.get("milestone"),
            "questions": items,
            "policy": "模板问题提到学习者未收到的数字/事实 -> 替换为结合作品的问题，并记录",
        },
        dedupe_key=f"defense_unsupported:{defense.get('id')}",
    )


def _handle_defense(
    project: fs.Project,
    state: fs.State,
    updates: dict,
    *,
    turn_index: int,
) -> dict | None:
    block = updates.get("defense")
    if block is None:
        return None
    data, problems = mentor_mod.validate_defense(updates)
    if problems or data is None:
        mentor_mod.record_invalid(
            project,
            kind="critic",
            turn=type("T", (), {"raw": json.dumps(updates, ensure_ascii=False), "model": ""})(),
            reasons=problems or ["defense 结构非法"],
            offline=False,
        )
        return {"invalid": problems}
    milestone = state.current
    if milestone is None:
        return {"invalid": ["没有当前里程碑"]}
    mid = milestone["id"]
    artifact = logic.latest_artifact(state.artifacts, mid)
    if artifact is None:
        return {"invalid": ["没有登记作品，不能记录 defense"]}
    review = logic.review_for_artifact(state.reviews, artifact["id"])
    pending = logic.pending_defense_for_milestone(state.defense, mid)
    if pending is None or pending.get("artifact_id") != artifact["id"]:
        if review is None or not review.get("threshold_pass"):
            project.journal_append(
                "defense_rejected",
                {"milestone": mid, "reason": "rubric_not_passed", "session": state.session.get("session_id")},
                dedupe_key=f"defense_rejected:{artifact['id']}",
            )
            return {"rejected": "rubric 未达标，defense 只记录不判定"}
        pending = logic.build_defense(
            milestone,
            artifact,
            review,
            state.brief.get("defense_rules"),
            materials_text=_defense_materials(project, state, milestone),
        )
        state.add_item("defense", pending)
        _record_defense_unsupported(project, pending)
    text = mentor_mod.artifact_text(project, artifact)
    merged = logic.verify_defense_questions(milestone, data["questions"], text)
    result = logic.evaluate_defense(milestone, state.brief.get("defense_rules") or {}, merged)
    pending.update(
        {
            "questions": merged,
            "ok_count": result["ok_count"],
            "min_ok": result["min_ok"],
            "heaviest_dims": result["heaviest_dims"],
            "heaviest_ok": result["heaviest_ok"],
            "status": result["status"],
            "passed": result["passed"],
            "decided_by": "runtime",
            "source": "mentor",
            "at": fs.now_iso(),
            "attempts": int(pending.get("attempts", 0)) + 1,
            "session": state.session.get("session_id"),
        }
    )
    project.journal_append(
        "defense_recorded",
        {
            "defense_id": pending["id"],
            "milestone": mid,
            "artifact_id": artifact["id"],
            "ok_count": result["ok_count"],
            "status": result["status"],
            "passed": result["passed"],
            "heaviest_ok": result["heaviest_ok"],
            "attempts": pending["attempts"],
            "session": state.session.get("session_id"),
            # Full snapshot: defense_recorded is the only authoritative copy of the
            # answers once the state file write is interrupted.
            "defense": pending,
        },
        dedupe_key=f"defense:{pending['id']}:{pending['attempts']}",
    )
    return {"defense": pending, "result": result}


def cmd_say(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--json": "bool"})
    if not positional:
        raise fs.UsageError("say 需要一个参数：学习者原话（用 - 从 stdin 读）")
    text = positional[0]
    if text == "-":
        text = sys.stdin.read()
    text = text.strip()
    if not text:
        raise fs.UsageError("say 内容为空")
    state = load(project)
    milestone = state.current
    if milestone is None:
        raise fs.ForgeError("没有当前里程碑；运行 status 或 init")
    mid = milestone["id"]
    pending = logic.pending_defense_for_milestone(state.defense, mid)
    target = active_mentor(state)
    if pending and target != "critic":
        switch_mentor(project, state, "critic", reason="defense_answer", ref=pending["id"], forced=True)
        target = "critic"
    fs.ensure_session(project, state, target)
    session_id = state.session.get("session_id")
    turn_index = int(state.session.get("turn_index", 0) or 0) + 1

    replayed = None
    for event in project.journal.of_kind("mentor_turn"):
        if event.get("dedupe_key") == f"say:{session_id}:{turn_index}":
            replayed = event
            break
    if replayed:
        prefix = "[离线脚本导师] " if replayed["payload"].get("offline") else ""
        print(prefix + str(replayed["payload"].get("text", "")))
        print("（已记录：重复执行未重复计数）")
        return 0

    artifact = logic.latest_artifact(state.artifacts, mid)
    claimed = is_completion_claim(text) and artifact is None
    if claimed:
        project.journal_append(
            "claim_without_artifact",
            {
                "milestone": mid,
                "text": text,
                "source": fs.SELF_REPORT,
                "evidence": "none",
                "session": session_id,
                "turn": turn_index,
            },
            dedupe_key=f"claim:{session_id}:{turn_index}",
        )

    runtime = mentor_mod.MentorRuntime(project, offline=offline)
    turn_next = next_action(project, state)
    turn = runtime.run(target, state, text, artifact=artifact, runtime_next=turn_next)
    updates, problems = mentor_mod.validate_block(turn, target)
    payload = {"offline": runtime.offline, "help_level": None, "runtime_next": turn_next}
    record: dict = {"activity": milestone.get("activity_id"), "offline": runtime.offline}
    defense_result = None
    conflict = None
    if updates is None:
        mentor_mod.record_missing(project, kind=target, turn=turn, offline=runtime.offline)
    elif problems:
        mentor_mod.record_invalid(project, kind=target, turn=turn, reasons=problems, offline=runtime.offline)
    else:
        effective_help, inference = infer_help_level(text, turn.text, updates)
        payload.update(
            {
                "help_level": effective_help,
                "attempt": updates.get("attempt"),
                "misconception": updates.get("misconception"),
                "next": updates.get("next"),
            }
        )
        if inference:
            payload["help_level_inferred"] = True
        record.update(
            _apply_help_and_attempt(
                project,
                state,
                target,
                turn_index,
                updates,
                help_override=effective_help,
                inference=inference,
            )
        )
        conflict = detect_next_conflict(turn_next, turn.text, updates)
        if conflict:
            project.journal_append(
                "mentor_next_conflict",
                {
                    "session": session_id,
                    "turn": turn_index,
                    "mentor": target,
                    "runtime_action": turn_next.get("action"),
                    "runtime_ref": turn_next.get("ref"),
                    "mentioned": conflict.get("mentioned"),
                    "source": conflict.get("source"),
                    "excerpt": conflict.get("excerpt"),
                },
                dedupe_key=f"next_conflict:{session_id}:{turn_index}",
            )
            record["conflict"] = conflict
        if updates.get("rubric") is not None:
            project.journal_append(
                "rubric_proposal_ignored",
                {
                    "session": session_id,
                    "turn": turn_index,
                    "reason": "rubric 只能由 review 命令写入，say 不改状态",
                    "dims": [d.get("dim") for d in (updates.get("rubric") or []) if isinstance(d, dict)],
                },
                dedupe_key=f"rubric_ignored:{session_id}:{turn_index}",
            )
            record["ignored"] = "rubric 仅由 review 写入"
        if updates.get("defense") is not None:
            defense_result = _handle_defense(project, state, updates, turn_index=turn_index)

    mentor_text = runtime.label + turn.text
    _record_turn(
        project,
        state,
        mentor=target,
        turn_index=turn_index,
        learner_text=text,
        mentor_text=mentor_text,
        payload=payload,
        record=record,
        activity=milestone.get("activity_id", ""),
    )
    save(project, state, "session", "gaps", "defense", "brief")

    transitions = []
    if defense_result and defense_result.get("defense"):
        dfn = defense_result["defense"]
        if dfn.get("status") in ("passed", "failed"):
            if dfn.get("passed"):
                transitions = finalize(project, state)
            switch_mentor(
                project,
                state,
                "coach",
                reason="defense_passed" if dfn.get("passed") else "defense_failed",
                ref=dfn["id"],
            )
            save(project, state, "session", "brief")
    nxt = next_action(project, state)
    registered = [item for item in state.artifacts.get("items", []) if item.get("milestone") == mid]
    denial = mentor_denies_registered_artifacts(turn.text, registered)
    if denial:
        project.journal_append(
            "review_note_conflict",
            {
                "mentor": target,
                "source": "mentor_text",
                "denied": True,
                "registered_paths": [item.get("path") for item in registered],
                "excerpt": (turn.text or "")[:200],
                "session": session_id,
                "turn": turn_index,
            },
            dedupe_key=f"mentor_denied_artifacts:{session_id}:{turn_index}",
        )
    print(mentor_text)
    print("")
    print(authority_line(nxt))
    if denial:
        print(
            f"[运行时] 导师说没有登记作品，但运行时已有 {len(registered)} 件；"
            "已记 review_note_conflict，请以 artifact list 为准。"
        )
    if claimed:
        print("[运行时] 未登记作品：已写 claim_without_artifact 事件；本里程碑仍为 active，不会因这句话通过。")
        print("[运行时] 先 artifact add <PATH> 再 review。")
    if conflict:
        print(
            f"[运行时] 导师本轮提到 {conflict.get('mentioned')}，与唯一动作 {turn_next.get('action')} 冲突；"
            "已记 mentor_next_conflict，以运行时为准。"
        )
    if record.get("help_level_inferred"):
        info = record["help_level_inferred"]
        print(
            f"[运行时] 帮助等级按证据推断：{info.get('declared')} → L{info.get('inferred')}"
            f"（{info.get('why')}），已记 help_level_inferred。"
        )
    if defense_result:
        if defense_result.get("invalid"):
            print(f"[运行时] defense 结构非法，本轮无证据：{'; '.join(defense_result['invalid'])}")
        elif defense_result.get("rejected"):
            print(f"[运行时] {defense_result['rejected']}")
        elif defense_result.get("defense"):
            dfn = defense_result["defense"]
            print(
                f"[运行时] defense {dfn.get('ok_count')}/{len(dfn.get('questions', []))} 问通过；"
                f"最重维度 {'通过' if dfn.get('heaviest_ok') else '未通过'}；判定：{dfn.get('status')}"
            )
            for item in dfn.get("questions", []):
                if not item.get("ok"):
                    print(f"  - {item['qid']} 未通过（{item.get('check')}）")
    for item in transitions:
        print(f"[运行时] 里程碑 {item['id']} 通过（{item['status']}），已激活 {item.get('next') or '收尾'}")
    extra = ""
    if record.get("help_level") is not None:
        extra += f"｜help_level={record['help_level']}"
    if record.get("micro_practice"):
        extra += f"｜未在作品复验：{', '.join(record['micro_practice'])}"
    print(
        f"导师：{active_mentor(state)}｜{mid} status={(state.milestone(mid) or {}).get('status')}{extra}"
    )
    return 0

# --------------------------------------------------------------------------- #
# task / status / next
# --------------------------------------------------------------------------- #
def _rubric_rows(milestone: dict, review: dict | None) -> list[list[str]]:
    scores = {d["dim"]: d["score"] for d in (review or {}).get("rubric", [])}
    rows = []
    for dim in milestone.get("rubric", []):
        score = scores.get(dim["dim"])
        rows.append(
            [
                dim["dim"],
                str(dim["weight"]),
                str(dim["threshold"]),
                "-" if score is None else str(score),
                "达标"
                if score is not None and int(score) >= int(dim["threshold"])
                else ("未评" if score is None else "未达标"),
                dim.get("criteria", ""),
            ]
        )
    return rows


def cmd_task(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--json": "bool", "--minutes": "value"})
    if positional:
        raise fs.UsageError(f"task 不接受位置参数 {positional!r}")
    state = load(project)
    milestone = state.current
    if milestone is None:
        raise fs.ForgeError("没有当前里程碑")
    artifact = logic.latest_artifact(state.artifacts, milestone["id"])
    review = logic.review_for_artifact(state.reviews, artifact["id"]) if artifact else None
    nxt = next_action(project, state, _int(opts.get("--minutes"), "--minutes", None))
    fixed_task = logic.opening_task(state.brief, milestone, _int(opts.get("--minutes"), "--minutes", None))
    if opts.get("--json"):
        cli.emit_json(
            {
                "milestone": milestone["id"],
                "title": milestone.get("title"),
                "status": milestone.get("status"),
                "deliverable": milestone.get("deliverable"),
                "rubric": milestone.get("rubric"),
                "gate": milestone.get("gate"),
                "task": {**fixed_task, "fixed": True},
                "artifact": artifact,
                "review": review,
                "gaps": logic.order_gaps(state.gaps, state.brief, mid=milestone["id"]),
                "next": nxt,
            }
        )
        return 0
    deliverable = milestone.get("deliverable") or {}
    print(f"{milestone['id']}「{milestone.get('title')}」 status={milestone.get('status')}")
    print(f"本步任务（{fixed_task['task_id']}）：{fixed_task['text']}")
    print(f"交付物：{deliverable.get('text')}")
    print(
        f"允许后缀：{', '.join(deliverable.get('allowed_ext', []))}；"
        f"最小字节：{deliverable.get('min_bytes')}"
    )
    print("")
    print(cli.table(_rubric_rows(milestone, review), ["dim", "weight", "threshold", "score", "state", "criteria"]))
    print("")
    print(f"切片：{fixed_task['slice']} 分钟 — {fixed_task['slice_hint']}")
    if artifact:
        print(
            f"当前作品：{artifact['id']} {artifact.get('path')} sha={str(artifact.get('sha256'))[:12]} "
            f"assisted_level={artifact.get('assisted_level')}"
        )
        if review:
            print(f"最近评审：{review['id']} weighted={review.get('weighted')} 达阈值={review.get('threshold_pass')}")
    else:
        print("还没有登记作品：artifact add <PATH>")
    gaps = logic.order_gaps(state.gaps, state.brief, mid=milestone["id"])
    if gaps:
        print("未关缺口：")
        for gap in gaps[:5]:
            print(
                f"  - {gap['gap_id']} {gap['dim']} {gap.get('score')}/{gap.get('threshold')} "
                f"weight={logic.effective_weight(gap)} status={gap.get('status')}"
                + ("｜未在作品复验" if gap.get("unverified") else "")
            )
    print("")
    print(f"下一步：{nxt['action']}｜{nxt.get('reason', '')}")
    print(f"切片：{nxt.get('slice')} 分钟 — {nxt.get('slice_hint', '')}")
    return 0


def _status_payload(project: fs.Project, state: fs.State, offline: bool) -> dict:
    brief = state.brief
    current = state.current or {}
    mid = current.get("id")
    artifacts = state.artifacts.get("items", [])
    reviews = state.reviews.get("items", [])
    gaps = state.gaps.get("items", [])
    latest_review = reviews[-1] if reviews else None
    latest_for_current = logic.latest_review_for_milestone(state.reviews, mid) if mid else None
    latest_scores = {d["dim"]: d["score"] for d in (latest_review or {}).get("rubric", [])}
    latest_rubric = {
        dim["dim"]: dim for dim in (logic.get_milestone(brief, (latest_review or {}).get("milestone")) or {}).get("rubric", [])
    }
    strengths = [
        dim
        for dim, score in latest_scores.items()
        if int(score) >= int((latest_rubric.get(dim) or {}).get("threshold", 0))
    ]
    weaknesses = [
        dim
        for dim, score in latest_scores.items()
        if int(score) < int((latest_rubric.get(dim) or {}).get("threshold", 0))
    ]
    unverified_gaps = [g for g in gaps if g.get("status") == "unverified"]
    weaknesses += [str(g.get("dim")) for g in unverified_gaps if g.get("dim") not in weaknesses]
    defense = logic.defense_for_milestone(state.defense, mid) if mid else None
    try:
        git_status = GitSync(project.root, include=["."]).status()
    except (LearnError, OSError):
        git_status = {"is_repo": False}
    handoff = project.latest_handoff()
    milestones = []
    for milestone in brief.get("milestones", []):
        review = logic.latest_review_for_milestone(state.reviews, milestone["id"])
        scores = {d["dim"]: d["score"] for d in (review or {}).get("rubric", [])}
        dfn = logic.defense_for_milestone(state.defense, milestone["id"])
        milestones.append(
            {
                "id": milestone["id"],
                "title": milestone.get("title"),
                "status": milestone.get("status"),
                "deliverable": (milestone.get("deliverable") or {}).get("paths", []),
                "rubric": [
                    {
                        "dim": dim["dim"],
                        "weight": dim["weight"],
                        "threshold": dim["threshold"],
                        "score": scores.get(dim["dim"]),
                    }
                    for dim in milestone.get("rubric", [])
                ],
                "artifact_count": len(logic.artifacts_for(state.artifacts, milestone["id"])),
                "review_count": len([r for r in reviews if r.get("milestone") == milestone["id"]]),
                "latest_review": (
                    {
                        "id": review["id"],
                        "weighted": review.get("weighted"),
                        "threshold_pass": review.get("threshold_pass"),
                        "gap_dims": review.get("gap_dims", []),
                    }
                    if review
                    else None
                ),
                "defense": (
                    {
                        "id": dfn["id"],
                        "status": dfn.get("status"),
                        "passed": dfn.get("passed"),
                        "ok_count": dfn.get("ok_count"),
                    }
                    if dfn
                    else None
                ),
                "pass_evidence": milestone.get("pass_evidence") or {},
                "passed_at": milestone.get("passed_at"),
                "open_gaps": len(logic.open_gaps(state.gaps, milestone["id"])),
            }
        )
    nxt = next_action(project, state)
    _help = help_stats(project)
    current_session = (
        {
            "id": state.session.get("session_id"),
            "mentor": state.session.get("mentor"),
            "file": state.session.get("file"),
            "turns": state.session.get("turn_index"),
            "started_at": state.session.get("started_at"),
            "ended_at": state.session.get("ended_at"),
        }
        if state.session.get("session_id")
        else None
    )
    previous = _last_session_payload(project, state, prefer_previous=True)
    last_session = current_session
    current_session_payload = None
    if (
        previous
        and current_session
        and previous["session_id"] != current_session["id"]
        and int(current_session.get("turns") or 0) <= 1
    ):
        last_session = {
            "id": previous["session_id"],
            "mentor": previous.get("mentor"),
            "turns": previous.get("turns"),
            "started_at": previous.get("at"),
            "ended_at": None,
            "previous": True,
        }
        current_session_payload = current_session
    return {
        "schema_version": fs.SCHEMA_VERSION,
        "variant": fs.VARIANT_ID,
        "version": fs.VARIANT_VERSION,
        "core_version": learncore.CORE_VERSION,
        "offline": offline or (os.environ.get("LEARNARK_LLM", "").lower() == "mock"),
        "goal": brief.get("goal"),
        "template": brief.get("template"),
        "minutes_per_week": brief.get("minutes_per_week"),
        "status": current.get("status"),
        "current_milestone": mid,
        "milestones": milestones,
        "artifacts": {
            "count": len(artifacts),
            "items": [
                {
                    "id": item["id"],
                    "milestone": item.get("milestone"),
                    "path": item.get("path"),
                    "sha256": item.get("sha256"),
                    "size": item.get("size"),
                    "assisted_level": item.get("assisted_level"),
                    "supersedes": item.get("supersedes"),
                    "reviewed": logic.review_for_artifact(state.reviews, item["id"]) is not None,
                }
                for item in artifacts
            ],
        },
        "reviews": {
            "count": len(reviews),
            "latest": (
                {
                    "id": latest_review["id"],
                    "milestone": latest_review.get("milestone"),
                    "artifact_id": latest_review.get("artifact_id"),
                    "rubric": latest_review.get("rubric"),
                    "weighted": latest_review.get("weighted"),
                    "threshold_pass": latest_review.get("threshold_pass"),
                    "gap_dims": latest_review.get("gap_dims"),
                }
                if latest_review
                else None
            ),
            "latest_for_current": latest_for_current.get("id") if latest_for_current else None,
        },
        "capability": {
            "latest_review": latest_review.get("id") if latest_review else None,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "open_gap_dims": [g.get("dim") for g in logic.order_gaps(state.gaps, brief)],
            "unverified_dims": [g.get("dim") for g in unverified_gaps],
            "note": "强项/待补只来自最近一次评审分数与缺口，不是能力认证",
        },
        "gaps": {
            "open": [
                {
                    "gap_id": gap["gap_id"],
                    "dim": gap.get("dim"),
                    "score": gap.get("score"),
                    "threshold": gap.get("threshold"),
                    "weight": logic.effective_weight(gap),
                    "status": gap.get("status"),
                    "unverified": gap.get("unverified", False),
                    "source_review": gap.get("source_review"),
                }
                for gap in logic.order_gaps(state.gaps, brief)
            ],
            "stale": [
                {
                    "gap_id": gap["gap_id"],
                    "dim": gap.get("dim"),
                    "stale_drops": gap.get("stale_drops"),
                    "weight": logic.effective_weight(gap),
                }
                for gap in gaps
                if gap.get("status") == "stale"
            ],
            "unverified": [
                {
                    "gap_id": gap["gap_id"],
                    "dim": gap.get("dim"),
                    "score": gap.get("score"),
                    "threshold": gap.get("threshold"),
                    "source_review": gap.get("source_review"),
                }
                for gap in unverified_gaps
            ],
            "closed_count": len([g for g in gaps if g.get("status") == "closed"]),
        },
        "defense": (
            {
                "id": defense["id"],
                "status": defense.get("status"),
                "passed": defense.get("passed"),
                "ok_count": defense.get("ok_count"),
                "heaviest_ok": defense.get("heaviest_ok"),
            }
            if defense
            else None
        ),
        "next": nxt,
        "mentor": active_mentor(state),
        "started": bool(state.project.get("started")),
        "start_profile": brief.get("start_profile"),
        "learner_profile": state.project.get("learner_profile") or {},
        "claim_without_artifact": claim_open(project, mid),
        "last_session": last_session,
        "current_session": current_session_payload,
        "handoff": {key: handoff.get(key) for key in ("from", "to", "reason", "ref", "next", "at") if handoff},
        "sync": {
            "is_repo": bool(git_status.get("is_repo")),
            "branch": git_status.get("branch", ""),
            "remote": git_status.get("remote", ""),
            "clean": git_status.get("clean"),
            "changed": len(git_status.get("changed", []) or []),
            "ahead": git_status.get("ahead", 0),
            "behind": git_status.get("behind", 0),
            "unmerged": git_status.get("unmerged", []) or [],
            "diverged": bool(git_status.get("diverged")),
        },
        "updated_at": brief.get("updated_at"),
        "help": _help,
        "last_help_level": _help.get("last_help_level"),
        "max_help_level": _help.get("max_help_level"),
    }


def cmd_status(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--json": "bool"})
    if positional:
        raise fs.UsageError(f"status 不接受位置参数 {positional!r}")
    state = load(project)
    transitions = finalize(project, state)
    payload = _status_payload(project, state, offline)
    for note in project.repair_notes():
        cli.warn(f"[恢复] {note}")
    if opts.get("--json"):
        if transitions:
            payload["just_passed"] = transitions
        if project.repair_notes():
            payload["recovered"] = project.repair_notes()
        cli.emit_json(payload)
        return 0
    current = state.current or {}
    print(f"Forge · {payload['goal']}")
    print(
        f"模板 {payload['template']}｜里程碑 {payload['current_milestone']}「{current.get('title', '')}」"
        f" status={payload['status']}｜导师 {payload['mentor']}｜离线={'是' if payload['offline'] else '否'}"
    )
    if payload.get("start_profile"):
        profile = payload["start_profile"]
        print(
            f"起点档案：{json.dumps(profile.get('answers'), ensure_ascii=False)} → {profile.get('mapped_start')}"
            f"（{profile.get('strictness')}，{profile.get('slice_minutes')} 分钟切片；"
            f"answered={profile.get('answered')}）"
        )
    self_report = (payload.get("learner_profile") or {}).get("self_report") or {}
    if self_report:
        print(f"学习者自述（不是能力证据）：{json.dumps(self_report, ensure_ascii=False)}")
    help_info = payload.get("help") or {}
    if help_info.get("last_help_level") is not None:
        last_mentor = help_info.get("last_help_mentor") or "-"
        max_mentor = help_info.get("max_help_mentor") or "-"
        inferred = help_info.get("inferred_count") or 0
        print(
            f"帮助等级：最近 L{help_info.get('last_help_level')}（{last_mentor}）"
            f"｜最高 L{help_info.get('max_help_level')}（{max_mentor}）"
            + (f"｜推断 {inferred} 次" if inferred else "")
        )
    for item in transitions:
        print(f"[运行时] 里程碑 {item['id']} 通过（{item['status']}），已激活 {item.get('next') or '收尾'}")
    if payload["artifacts"]["count"]:
        last = payload["artifacts"]["items"][-1]
        print(
            f"作品：{payload['artifacts']['count']} 件｜最新 {last['id']} {last['path']} "
            f"sha={str(last['sha256'])[:12]} assisted_level={last['assisted_level']}"
        )
    else:
        print("作品：0 件（先 artifact add <PATH>）")
    if payload["reviews"]["latest"]:
        review = payload["reviews"]["latest"]
        scores = " ".join(f"{d['dim']}={d['score']}" for d in review.get("rubric", []))
        print(
            f"最近评审：{review['id']}（{review.get('milestone')}）{scores} "
            f"weighted={review['weighted']} 达阈值={review['threshold_pass']}"
        )
        cap = payload.get("capability") or {}
        print(
            f"强项：{', '.join(cap.get('strengths') or []) or '暂无'}｜"
            f"待补：{', '.join(cap.get('weaknesses') or []) or '暂无'}"
        )
    else:
        print("最近评审：无")
    if payload["defense"]:
        dfn = payload["defense"]
        print(
            f"防御：{dfn['id']} status={dfn['status']} ok={dfn.get('ok_count')} "
            f"最重维度={'过' if dfn.get('heaviest_ok') else '未过'}"
        )
    if payload["gaps"]["open"]:
        print("未关缺口（按 weight×缺口排序）：")
        for gap in payload["gaps"]["open"][:5]:
            print(
                f"  - {gap['gap_id']} {gap['dim']} {gap['score']}/{gap['threshold']} weight={gap['weight']} "
                f"status={gap['status']}" + ("｜未在作品复验" if gap["unverified"] else "")
            )
    if payload["gaps"]["stale"]:
        print("stale 缺口（不算解决）：" + ", ".join(g["gap_id"] for g in payload["gaps"]["stale"]))
    if payload["gaps"].get("unverified"):
        print(
            "达标但缺证据（unverified，不算开放缺口）："
            + ", ".join(f"{g['gap_id']}（{g['dim']}）" for g in payload["gaps"]["unverified"])
        )
    if payload.get("claim_without_artifact"):
        print("注意：有一次「完成声明」但没有登记作品（claim_without_artifact），不会被计为通过。")
    if payload.get("handoff"):
        handoff = payload["handoff"]
        print(
            f"最近交接：{handoff.get('from')} → {handoff.get('to')}（{handoff.get('reason')}）"
            f"｜{handoff.get('next') or ''}"
        )
    if payload.get("last_session"):
        session = payload["last_session"]
        state_text = (
            "，上一段" if session.get("previous") else ("，已结束" if session.get("ended_at") else "，进行中")
        )
        print(
            f"上次会话：{session.get('id')}（{session.get('mentor')}，{session.get('turns')} 轮）{state_text}"
        )
        if payload.get("current_session"):
            print(f"本次会话：{payload['current_session'].get('id')}（刚打开，尚未学习）")
    sync = payload["sync"]
    if sync["is_repo"]:
        print(
            f"git：branch={sync['branch'] or '-'} remote={sync['remote'] or '无'} "
            f"changed={sync['changed']} ahead={sync['ahead']} behind={sync['behind']}"
            + ("｜diverged=yes" if sync.get("diverged") else "")
        )
        if sync.get("unmerged"):
            print("  ⚠ 未合并文件：" + ", ".join(sync["unmerged"]))
        elif sync.get("diverged"):
            print("  ⚠ 本地与远程分叉：先 sync（journal 冲突可 sync --recover），快照冲突需人工选择")
    else:
        print("git：尚未初始化（运行 init 或 git init）")
    nxt = payload["next"]
    print("")
    print(f"下一步：{nxt['action']}｜{nxt.get('reason', '')}")
    if nxt.get("task_text") and nxt["action"] in ("do_task", "artifact_required"):
        print(f"本步任务（{nxt.get('task_id')}）：{nxt['task_text']}")
    print(f"切片：{nxt.get('slice')} 分钟 — {nxt.get('slice_hint', '')}")
    deliverable = (current.get("deliverable") or {}).get("text", "")
    if deliverable:
        print(f"当前交付物：{deliverable}")
    return 0


def cmd_next(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--json": "bool", "--minutes": "value"})
    if positional:
        raise fs.UsageError(f"next 不接受位置参数 {positional!r}")
    state = load(project)
    transitions = finalize(project, state)
    minutes = _int(opts.get("--minutes"), "--minutes", None)
    nxt = next_action(project, state, minutes)
    if transitions:
        last = transitions[-1]
        payload = {
            "schema_version": fs.SCHEMA_VERSION,
            "action": "milestone_passed",
            "reason": f"{last['id']} 作品 + rubric + defense 齐备，通过（{last['status']}）"
            + (f"，已激活 {last.get('next')}" if last.get("next") else "，全部里程碑完成"),
            "ref": last["id"],
            "milestone": last["id"],
            "passed_as": last["status"],
            "next_after": nxt,
            "state": {
                "current_milestone": state.brief.get("current_milestone"),
                "status": (state.current or {}).get("status"),
            },
        }
    else:
        payload = {
            "schema_version": fs.SCHEMA_VERSION,
            "action": nxt["action"],
            "reason": nxt.get("reason"),
            "ref": nxt.get("ref"),
            "milestone": nxt.get("milestone"),
            "minutes": nxt.get("minutes"),
            "slice": nxt.get("slice"),
            "slice_hint": nxt.get("slice_hint"),
            "dim": nxt.get("dim"),
            "score": nxt.get("score"),
            "threshold": nxt.get("threshold"),
            "weight": nxt.get("weight"),
            "artifacts": nxt.get("artifacts") or [],
            "task_id": nxt.get("task_id"),
            "task_text": nxt.get("task_text"),
            "state": {
                "current_milestone": state.brief.get("current_milestone"),
                "status": (state.current or {}).get("status"),
            },
        }
    if opts.get("--json"):
        cli.emit_json(payload)
        return 0
    print(f"下一步：{payload['action']}")
    print(f"原因：{payload.get('reason')}")
    if payload.get("dim"):
        print(
            f"缺口维度：{payload['dim']} {payload.get('score')}/{payload.get('threshold')} "
            f"weight={payload.get('weight')}"
        )
    print(f"切片：{payload.get('slice')} 分钟")
    if payload.get("task_text") and payload["action"] in ("do_task", "artifact_required"):
        print(f"本步任务（{payload.get('task_id')}）：{payload['task_text']}")
    current = state.current or {}
    deliverable = (current.get("deliverable") or {}).get("text", "")
    if deliverable and payload["action"] in ("do_task", "artifact_required"):
        print(f"交付物：{deliverable}")
    hints = {
        "do_task": "动作：写 / 改作品，完成后 artifact add <PATH> 登记",
        "artifact_required": "动作：先 artifact add <PATH>；没有作品不会评审，也不会通过",
        "review": "动作：learn review",
        "gap_learn": f"动作：learn gap learn {payload.get('ref')}",
        "defend": "动作：learn defend 看三问，再用 say 逐题回答（答案要引用行号）",
        "milestone_passed": "动作：status 查看新里程碑，再 task",
        "done": "动作：export --out 学习档案.md",
    }
    print(hints.get(payload["action"], ""))
    return 0


# --------------------------------------------------------------------------- #
# artifact
# --------------------------------------------------------------------------- #
def _artifact_assist_level(project: fs.Project) -> int:
    """Max coach/critic help since the previous artifact — *not* guide micro-lessons.

    ``guide`` lessons are the product's official learning path (design §6): they
    improve the gap card but must not mark the next artifact as assisted. Only
    coach/critic help while producing the artifact counts (issue round-01 #2).
    """
    last = -1
    events = project.journal.all()
    for index, event in enumerate(events):
        if event.get("kind") == "artifact_added":
            last = index
    best = 0
    for event in events[last + 1 :]:
        if event.get("kind") != "mentor_turn":
            continue
        payload = event.get("payload") or {}
        if payload.get("mentor") not in ("coach", "critic"):
            continue
        level = payload.get("help_level")
        if isinstance(level, int) and not isinstance(level, bool):
            best = max(best, level)
    return best


def _artifact_destination(project: fs.Project, brief: dict, milestone: dict, filename: str, sha: str) -> Path:
    base = project.root / str(brief.get("artifact_dir") or "artifacts") / milestone["id"]
    base.mkdir(parents=True, exist_ok=True)
    candidate = base / filename
    if candidate.exists():
        if fs.sha256_file(candidate) == sha:
            return candidate
        candidate = base / f"{candidate.stem}-{sha[:8]}{candidate.suffix}"
    return candidate


def cmd_artifact(project: fs.Project, args: list[str], offline: bool) -> int:
    if not args or args[0] not in ("add", "list"):
        raise fs.UsageError("用法：artifact add PATH|--note TEXT 或 artifact list [--json]")
    sub = args[0]
    rest = args[1:]
    if sub == "list":
        opts, positional = parse_flags(rest, {"--json": "bool"})
        if positional:
            raise fs.UsageError(f"artifact list 不接受位置参数 {positional!r}")
        state = load(project)
        items = state.artifacts.get("items", [])
        if opts.get("--json"):
            cli.emit_json({"schema_version": fs.SCHEMA_VERSION, "items": items})
            return 0
        if not items:
            print("还没有登记作品：artifact add <PATH>")
            return 0
        rows = []
        for item in items:
            review = logic.review_for_artifact(state.reviews, item["id"])
            rows.append(
                [
                    item["id"],
                    item.get("milestone", ""),
                    item.get("path", ""),
                    str(item.get("sha256", ""))[:12],
                    str(item.get("size", "")),
                    str(item.get("assisted_level", "")),
                    review["id"] if review else "-",
                ]
            )
        print(cli.table(rows, ["id", "milestone", "path", "sha256", "bytes", "assisted", "review"]))
        return 0

    opts, positional = parse_flags(rest, {"--note": "value", "--json": "bool"})
    note = opts.get("--note")
    state = load(project)
    milestone = state.current
    if milestone is None:
        raise fs.ForgeError("没有当前里程碑（全部里程碑已完成）")
    mid = milestone["id"]
    deliverable = milestone.get("deliverable") or {}
    allowed = [ext.lower() for ext in deliverable.get("allowed_ext") or fs.DEFAULT_ALLOWED_EXT]
    min_bytes = int(deliverable.get("min_bytes") or 20)

    if len(positional) > 1 and note:
        raise fs.UsageError("--note 只能配一个 PATH；多文件登记请去掉 --note，或分两次登记")
    sources: list[dict] = []
    if positional:
        for raw in positional:
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                candidate = (Path.cwd() / candidate).resolve()
            if not candidate.is_file():
                raise fs.UsageError(f"文件不存在或不是普通文件：{raw}")
            if candidate.suffix.lower() not in allowed:
                raise fs.UsageError(
                    f"后缀 {candidate.suffix or '(无)'} 不在本里程碑允许范围 {', '.join(allowed)} 内：{raw}"
                )
            data = candidate.read_bytes()
            if not data:
                raise fs.UsageError(f"空文件不算作品：{raw}")
            if len(data) < min_bytes:
                raise fs.UsageError(f"{raw} 只有 {len(data)} 字节，少于本里程碑要求的 {min_bytes} 字节")
            sources.append(
                {
                    "data": data,
                    "filename": candidate.name,
                    "source": str(candidate),
                    "kind": "file",
                    "sha": hashlib.sha256(data).hexdigest(),
                }
            )
    else:
        text = (note or "").strip()
        if not text:
            raise fs.UsageError("artifact add 需要 PATH 或 --note TEXT")
        data = text.encode("utf-8")
        if len(data) < min_bytes:
            raise fs.UsageError(f"note 只有 {len(data)} 字节，少于本里程碑要求的 {min_bytes} 字节")
        digest = hashlib.sha256(data).hexdigest()
        sources.append(
            {
                "data": data,
                "filename": f"note-{digest[:8]}.md",
                "source": "note",
                "kind": "note",
                "sha": digest,
            }
        )

    # «自上件以来最大 help_level» 必须在写入任何 artifact_added 事件之前算
    assisted = _artifact_assist_level(project)
    added: list[dict] = []
    skipped: list[dict] = []
    for src in sources:
        sha = src["sha"]
        duplicate = next(
            (
                item
                for item in state.artifacts.get("items", [])
                if item.get("milestone") == mid and item.get("sha256") == sha
            ),
            None,
        )
        if duplicate:
            skipped.append(
                {"id": duplicate["id"], "path": duplicate.get("path"), "sha256": sha, "reason": "duplicate"}
            )
            continue
        destination = _artifact_destination(project, state.brief, milestone, src["filename"], sha)
        event = project.journal_append(
            "artifact_added",
            {
                "milestone": mid,
                "sha256": sha,
                "size": len(src["data"]),
                "path": src["filename"],
                "dest": project.rel(destination),
                "source_path": src.get("source") if src.get("kind") == "file" else "",
                "assisted_level": assisted,
                "offline": offline,
            },
            dedupe_key=f"artifact:{mid}:{sha}",
        )
        if event is None:
            skipped.append({"sha256": sha, "reason": "deduped"})
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            fs.atomic_write_bytes(destination, src["data"])
        suffix = Path(src["filename"]).suffix.lower()
        same_suffix = [
            item
            for item in state.artifacts.get("items", [])
            if item.get("milestone") == mid
            and Path(str(item.get("path") or "")).suffix.lower() == suffix
        ]
        item = {
            "id": f"a-{mid}-{sha[:8]}",
            "milestone": mid,
            "path": project.rel(destination),
            "sha256": sha,
            "size": len(src["data"]),
            "assisted_level": assisted,
            "supersedes": same_suffix[-1]["id"] if same_suffix else None,
            "source": src["source"],
            "kind": src["kind"],
            "note": str(note or "")[:200],
            "added_at": fs.now_iso(),
            "event_id": event["id"],
        }
        state.add_item("artifacts", item)
        milestone.setdefault("artifact_ids", []).append(item["id"])
        added.append(item)
    state.brief["updated_at"] = fs.now_iso()
    save(project, state, "artifacts", "brief")
    nxt = next_action(project, state)

    if not added:
        print("已记录：这些文件都已登记过（同 sha256 不重复计分，不重复评审）")
        for item in skipped:
            print(f"  - {item.get('id') or item.get('sha256', '')[:12]} path={item.get('path') or '-'}")
        return 0
    if opts.get("--json"):
        cli.emit_json({"ok": True, "artifacts": added, "skipped": skipped, "next": nxt})
        return 0
    if len(added) == 1 and not skipped:
        item = added[0]
        print(f"已登记：{item['id']}")
        print(f"  path={item['path']} sha256={item['sha256'][:12]} size={item['size']} assisted_level={assisted}")
        if item.get("supersedes"):
            print(f"  取代：{item['supersedes']}（新 sha 需要重新评审）")
    else:
        print(f"已登记 {len(added)} 件（同一批共享 assisted_level={assisted}）：")
        for item in added:
            print(f"  - {item['id']} path={item['path']} sha256={item['sha256'][:12]} size={item['size']}")
        if skipped:
            print("跳过（已登记过）：" + ", ".join(item.get("id") or item.get("sha256", "")[:12] for item in skipped))
    if assisted >= 2:
        print(
            "  注意：本作品产出过程中用过 coach/critic 的分步或代做帮助（help_level>=2），"
            "即使通过也只记 passed_assisted；guide 微课不计入此值。"
        )
    print(f"下一步：{nxt['action']}｜{nxt.get('reason', '')}")
    print("评审：learn review")
    return 0


# --------------------------------------------------------------------------- #
# review
# --------------------------------------------------------------------------- #
def _gap_note_for(milestone: dict, dim: str, review_note: str, proposed: list[dict], extra: bool) -> str:
    for entry in proposed:
        if entry.get("dim") == dim and entry.get("note"):
            return entry["note"]
    if extra:
        return f"证据不足：note 未给行号/段落级证据（{review_note[:120]}）"
    rule = logic.rubric_by_dim(milestone).get(dim) or {}
    return (review_note or rule.get("criteria", ""))[:200]


def _print_review(review: dict, milestone: dict) -> None:
    print(
        f"评审对象：{review.get('artifact_id')}（本里程碑 {len(review.get('artifact_ids') or [])} 件："
        f"{', '.join(review.get('artifact_ids') or [])}）"
    )
    scores = {d["dim"]: d["score"] for d in review.get("rubric", [])}
    table_rows = []
    for dim in milestone.get("rubric", []):
        score = scores.get(dim["dim"])
        table_rows.append(
            [
                dim["dim"],
                str(dim["weight"]),
                str(dim["threshold"]),
                "-" if score is None else str(score),
                "达标" if score is not None and int(score) >= int(dim["threshold"]) else "未达标",
                next((d.get("note", "") for d in review.get("rubric", []) if d["dim"] == dim["dim"]), ""),
            ]
        )
    print(cli.table(table_rows, ["dim", "weight", "threshold", "score", "state", "note"]))
    print("")
    print(
        f"评审：{review['id']}｜加权 {review.get('weighted')}（仅用于排序，不用于通过判定）｜"
        f"达阈值={review.get('threshold_pass')}"
    )
    if review.get("clamped"):
        print("clamp：" + "；".join(f"{c['dim']} {c['from']}→{c['to']}（{c['why']}）" for c in review["clamped"]))
    if review.get("unevidenced"):
        print(
            "证据不足降分："
            + "；".join(
                f"{u['dim']} {u['from']}→{u['to']}（缺 evidence_line/evidence_path，threshold={u['threshold']}）"
                for u in review["unevidenced"]
            )
        )
    if review.get("gap_dims"):
        print("缺口维度：" + ", ".join(review["gap_dims"]))
    if review.get("extra_gap_dims"):
        print("证据不足另开卡：" + ", ".join(review["extra_gap_dims"]))


def _registered_missing_claims(dims: list[dict], registered: list[dict]) -> list[dict]:
    """Detect review notes that call a *registered* file missing (round-02 #4)."""
    missing_words = re.compile(r"(缺失|缺少|不存在|没有|无|未提供|没提供|missing|not\s*found)", re.IGNORECASE)
    conflicts: list[dict] = []
    for dim in dims:
        note = str(dim.get("note") or "")
        if not note:
            continue
        for item in registered:
            path = str(item.get("path") or "")
            name = Path(path).name
            if not name or name not in note:
                continue
            index = note.find(name)
            window = note[max(0, index - 16) : index + len(name) + 20]
            if missing_words.search(window):
                conflicts.append({"dim": dim.get("dim"), "path": path, "note": note[:200]})
    return conflicts


def cmd_review(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--json": "bool"})
    if len(positional) > 1:
        raise fs.UsageError("review 最多接受一个 artifact id")
    state = load(project)
    milestone = state.current
    if milestone is None:
        raise fs.ForgeError("没有当前里程碑")
    mid = milestone["id"]
    candidates = logic.artifacts_for(state.artifacts, mid)
    code_suffixes = {".py", ".js", ".ts", ".go", ".java", ".sh", ".rb", ".rs", ".sql"}
    if positional:
        artifact = next((a for a in state.artifacts.get("items", []) if a["id"] == positional[0]), None)
        if artifact is None:
            raise fs.UsageError(f"没有这个作品 id：{positional[0]}")
    else:
        uncovered = [a for a in candidates if logic.review_for_artifact(state.reviews, a["id"]) is None]
        pool = uncovered or candidates
        code = [a for a in pool if Path(str(a.get("path") or "")).suffix.lower() in code_suffixes]
        artifact = (code or pool)[-1] if pool else None
    if artifact is None:
        print(f"{mid} 还没有登记作品：先 artifact add <PATH>，没有作品不评审、不通过。")
        return cli.EXIT_STATE
    if artifact.get("milestone") != mid:
        print(f"作品 {artifact['id']} 属于 {artifact.get('milestone')}，当前里程碑是 {mid}")
        return cli.EXIT_STATE
    existing = logic.review_for_artifact(state.reviews, artifact["id"])
    if existing:
        print(f"已记录：{artifact['id']} 已由 {existing['id']} 评审过，同一 sha 不重复计分。")
        _print_review(existing, milestone)
        return 0

    previous_mentor = active_mentor(state)
    if previous_mentor != "critic":
        switch_mentor(project, state, "critic", reason="review", ref=artifact["id"], forced=True)
    runtime = mentor_mod.MentorRuntime(project, offline=offline)
    attempt = len([r for r in state.reviews.get("items", []) if r.get("milestone") == mid]) + 1
    turn = runtime.run(
        "critic",
        state,
        mentor_mod.review_prompt(artifact, milestone, attempt),
        artifact=artifact,
        runtime_next={
            "action": "review",
            "ref": artifact["id"],
            "reason": f"本轮由 review 触发（第 {attempt} 次评审）",
            "note": "评审后的下一步由运行时按分数计算；正文不要另排任务，只给逐维分数与修改项。",
        },
    )
    updates, problems = mentor_mod.validate_block(turn, "critic")
    dims: list[dict] | None = None
    clamped: list[dict] = []
    unevidenced: list[dict] = []
    gap_proposed: list[dict] = []
    defense_data: dict | None = None
    if updates is not None and not problems:
        dims, rubric_problems, clamped, unevidenced = mentor_mod.validate_rubric(milestone, updates)
        problems += rubric_problems
        gap_proposed, gap_problems = mentor_mod.validate_gap(updates)
        problems += gap_problems
        defense_data, defense_problems = mentor_mod.validate_defense(updates)
        problems += defense_problems
    if problems or dims is None:
        reasons = problems or ["评审缺少有效 rubric"]
        event = project.journal_append(
            "review_invalid",
            {
                "milestone": mid,
                "artifact_id": artifact["id"],
                "artifact_sha256": artifact.get("sha256"),
                "reasons": reasons,
                "raw_sha256": sha256_text(turn.raw),
                "raw_excerpt": (turn.raw or "")[:800],
                "offline": runtime.offline,
                "mentor": "critic",
            },
            dedupe_key=None,
        )
        if previous_mentor != "critic":
            switch_mentor(
                project,
                state,
                "coach",
                reason="review_invalid",
                ref=artifact["id"],
                note="评审被运行时拒绝，状态未改变",
            )
        save(project, state, "session")
        print("评审被拒绝（review_invalid）：")
        for reason in reasons:
            print(f"  - {reason}")
        print("状态未改变：没有写分数、没有改缺口。")
        if event:
            print(f"事件：{event['id']}")
        return cli.EXIT_STATE

    scored = logic.score_review(milestone, dims)
    rubric = logic.rubric_by_dim(milestone)
    low = [d["dim"] for d in dims if int(d["score"]) < int(rubric[d["dim"]]["threshold"])]
    unverified_dims = [d["dim"] for d in dims if d["dim"] not in low and logic.needs_extra_gap(milestone, d)]
    gap_dims = low
    registered = [
        item for item in state.artifacts.get("items", []) if item.get("milestone") == mid
    ]
    registered_ids = [item["id"] for item in registered]
    note_conflicts = _registered_missing_claims(dims, registered)
    unsupported_claims = unsupported_numeric_claims(dims)
    strip_unsupported_claims(dims, unsupported_claims)
    review_id = f"r-{mid}-{str(artifact.get('sha256', ''))[:8]}"
    review = {
        "id": review_id,
        "milestone": mid,
        "artifact_id": artifact["id"],
        "artifact_ids": registered_ids,
        "artifact_sha256": artifact.get("sha256"),
        "rubric": dims,
        "gap_dims": gap_dims,
        "unverified_dims": unverified_dims,
        "low_dims": low,
        "extra_gap_dims": unverified_dims,
        "clamped": clamped,
        "unevidenced": unevidenced,
        "claims_without_evidence": unsupported_claims,
        "registered_paths": [item.get("path") for item in registered],
        "conflicts": note_conflicts,
        "weighted": scored["weighted"],
        "threshold_pass": scored["threshold_pass"],
        "proposed_by": "llm",
        "validated_by": "runtime",
        "mentor": "critic",
        "model": turn.model,
        "offline": runtime.offline,
        "event_id": None,
        "at": fs.now_iso(),
    }
    event = project.journal_append(
        "review_recorded",
        {
            "review_id": review_id,
            "milestone": mid,
            "artifact_id": artifact["id"],
            "artifact_ids": registered_ids,
            "artifact_sha256": artifact.get("sha256"),
            "scores": {d["dim"]: d["score"] for d in dims},
            "threshold_pass": scored["threshold_pass"],
            "weighted": scored["weighted"],
            "clamped": len(clamped),
            "unevidenced": unevidenced,
            "claims_without_evidence": unsupported_claims,
            "registered_paths": [item.get("path") for item in registered],
            "conflicts": note_conflicts,
            "gap_dims": gap_dims,
            "unverified_dims": unverified_dims,
            "offline": runtime.offline,
            # Full snapshot so a crash between this event and reviews.json can be
            # replayed without asking the LLM to score the same artifact again.
            "review": review,
        },
        dedupe_key=f"review:{artifact['id']}",
    )
    if event is None:
        reloaded = load(project)
        existing = logic.review_for_artifact(reloaded.reviews, artifact["id"])
        print("已记录：该作品已评审（并发/重复调用），分数不重算。")
        if existing:
            _print_review(existing, reloaded.milestone(mid) or milestone)
        return 0
    review["event_id"] = event["id"]
    state.add_item("reviews", review)
    milestone.setdefault("review_ids", []).append(review_id)
    if unevidenced:
        project.journal_append(
            "rubric_unevidenced",
            {
                "review_id": review_id,
                "milestone": mid,
                "artifact_id": artifact["id"],
                "adjustments": unevidenced,
                "policy": "score>=threshold 且缺 evidence_line/evidence_path -> 降到 threshold-1（不拒绝整次评审）",
            },
            dedupe_key=f"rubric_unevidenced:{review_id}",
        )
    if note_conflicts:
        project.journal_append(
            "review_note_conflict",
            {
                "review_id": review_id,
                "milestone": mid,
                "artifact_id": artifact["id"],
                "conflicts": note_conflicts,
                "registered_paths": [item.get("path") for item in registered],
                "policy": "已登记路径存在；评审 note 不得声称其缺失，冲突只记录不静默",
            },
            dedupe_key=f"review_note_conflict:{review_id}",
        )
    if unsupported_claims:
        project.journal_append(
            "claim_without_evidence",
            {
                "review_id": review_id,
                "milestone": mid,
                "artifact_id": artifact["id"],
                "claims": unsupported_claims,
                "policy": "评审 note 中的数量断言（如步数上限）必须带 evidence_line/evidence_path；无依据只记录，并从可见 note 中省略",
            },
            dedupe_key=f"claim_without_evidence:{review_id}",
        )

    gap_changes: list[dict] = []
    for dim in dims:
        if dim["dim"] not in low and dim["dim"] not in unverified_dims:
            continue
        rule = rubric[dim["dim"]]
        extra = dim["dim"] in unverified_dims
        note = _gap_note_for(milestone, dim["dim"], dim.get("note", ""), gap_proposed, extra)
        change = logic.upsert_gap(
            state.gaps,
            milestone,
            dim["dim"],
            score=int(dim["score"]),
            threshold=int(rule["threshold"]),
            weight=int(rule["weight"]),
            note=note,
            review_id=review_id,
            artifact_sha=str(artifact.get("sha256")),
            extra=extra,
            status="unverified" if extra else "open",
        )
        gap_changes.append(change)
        card = change["card"]
        kind = (
            "gap_unverified"
            if extra
            else {"created": "gap_created", "updated": "gap_updated", "reopened": "gap_reopened"}.get(
                change["change"], "gap_updated"
            )
        )
        project.journal_append(
            kind,
            {
                "gap_id": card["gap_id"],
                "milestone": mid,
                "dim": card["dim"],
                "score": card["score"],
                "threshold": card["threshold"],
                "weight": card["weight"],
                "source_review": review_id,
                "extra_trigger": card.get("extra_trigger", False),
                "attempts": card.get("attempts"),
                "card": card,
            },
            dedupe_key=f"gap:{card['gap_id']}:{review_id}",
        )
    closed = logic.close_gaps_for_review(
        state.gaps,
        milestone,
        dims,
        review_id=review_id,
        artifact_sha=str(artifact.get("sha256")),
        skip_dims=tuple(unverified_dims),
    )
    for card in closed:
        project.journal_append(
            "gap_closed",
            {
                "gap_id": card["gap_id"],
                "milestone": mid,
                "dim": card["dim"],
                "closed_by": "review",
                "review_id": review_id,
                "artifact_sha256": artifact.get("sha256"),
                "card": card,
            },
            dedupe_key=f"gap_closed:{card['gap_id']}:{review_id}",
        )
    save(project, state, "reviews", "gaps", "brief")

    defense_result = None
    if defense_data is not None:
        defense_result = _handle_defense(project, state, updates or {}, turn_index=0)
        save(project, state, "defense")

    transitions: list[dict] = []
    if scored["threshold_pass"]:
        if defense_result and defense_result.get("defense", {}).get("passed"):
            transitions = finalize(project, state)
            switch_mentor(project, state, "coach", reason="review_passed", ref=review_id)
        elif defense_result and defense_result.get("defense"):
            switch_mentor(
                project,
                state,
                "coach",
                reason="defense_failed",
                ref=defense_result["defense"]["id"],
            )
        else:
            existing_defense = logic.defense_for_artifact(state.defense, artifact["id"])
            if existing_defense is not None and existing_defense.get("passed"):
                transitions = finalize(project, state)
                switch_mentor(project, state, "coach", reason="review_passed", ref=review_id)
            else:
                pending = existing_defense
                if pending is None:
                    pending = logic.build_defense(
                        milestone,
                        artifact,
                        review,
                        state.brief.get("defense_rules"),
                        materials_text=_defense_materials(project, state, milestone),
                    )
                    state.add_item("defense", pending)
                    _record_defense_unsupported(project, pending)
                    save(project, state, "defense")
                switch_mentor(project, state, "critic", reason="defense_pending", ref=pending["id"])
    else:
        switch_mentor(project, state, "coach", reason="review_failed", ref=review_id)
    save(project, state, "session", "brief")
    nxt = next_action(project, state)

    if opts.get("--json"):
        cli.emit_json(
            {
                "ok": True,
                "review": review,
                "gaps_created": [c["card"]["gap_id"] for c in gap_changes if c["change"] == "created"],
                "gaps_updated": [c["card"]["gap_id"] for c in gap_changes if c["change"] != "created"],
                "gaps_unverified": [
                    c["card"]["gap_id"] for c in gap_changes if c["card"].get("status") == "unverified"
                ],
                "gaps_closed": [c["gap_id"] for c in closed],
                "transitions": transitions,
                "next": nxt,
            }
        )
        return 0
    print(runtime.label + turn.text)
    print("")
    print(authority_line(nxt))
    _print_review(review, milestone)
    if note_conflicts:
        print(
            "[运行时] 评审 note 声称已登记文件缺失，已记 review_note_conflict："
            + "；".join(f"{c['dim']} → {c['path']}" for c in note_conflicts)
        )
    if unsupported_claims:
        print(
            "[运行时] 评审 note 的数量断言缺证据，已记 claim_without_evidence："
            + "；".join(f"{c['dim']}「{c['claim']}」" for c in unsupported_claims)
        )
    if gap_changes:
        open_cards = [c for c in gap_changes if c["card"].get("status") != "unverified"]
        unverified_cards = [c for c in gap_changes if c["card"].get("status") == "unverified"]
        if open_cards:
            print("缺口卡：" + "；".join(f"{c['card']['gap_id']}({c['change']})" for c in open_cards))
        if unverified_cards:
            print(
                "达标但缺证据（unverified，不算开放缺口）："
                + "；".join(f"{c['card']['gap_id']}({c['card']['dim']})" for c in unverified_cards)
            )
    if closed:
        print("本次关闭缺口：" + ", ".join(c["gap_id"] for c in closed) + "（复评达标）")
    for item in transitions:
        print(f"[运行时] 里程碑 {item['id']} 通过（{item['status']}），已激活 {item.get('next') or '收尾'}")
    if defense_result and defense_result.get("defense"):
        dfn = defense_result["defense"]
        print(
            f"[运行时] defense {dfn.get('ok_count')}/{len(dfn.get('questions', []))} 问通过；判定：{dfn.get('status')}"
        )
    elif scored["threshold_pass"] and not transitions:
        print("rubric 已达标：接下来做防御性解释三问（defend，然后用 say 逐题回答）。")
    return 0


# --------------------------------------------------------------------------- #
# defend
# --------------------------------------------------------------------------- #
def cmd_defend(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--json": "bool"})
    if positional:
        raise fs.UsageError(f"defend 不接受位置参数 {positional!r}")
    state = load(project)
    milestone = state.current
    if milestone is None:
        raise fs.ForgeError("没有当前里程碑")
    artifact = logic.latest_artifact(state.artifacts, milestone["id"])
    if artifact is None:
        print("没有登记作品，不能进入 defense：先 artifact add。")
        return cli.EXIT_STATE
    review = logic.review_for_artifact(state.reviews, artifact["id"])
    if review is None or not review.get("threshold_pass"):
        print("rubric 尚未达标，不能进入 defense：先 review，或 gap learn 补缺口。")
        return cli.EXIT_STATE
    defense = logic.defense_for_artifact(state.defense, artifact["id"])
    if defense is not None and defense.get("passed"):
        print(
            f"防御性解释已通过（{defense['id']}，{defense.get('ok_count')}/"
            f"{len(defense.get('questions', []))}）。"
        )
        return 0
    if defense is None:
        defense = logic.build_defense(
            milestone,
            artifact,
            review,
            state.brief.get("defense_rules"),
            materials_text=_defense_materials(project, state, milestone),
        )
        state.add_item("defense", defense)
        _record_defense_unsupported(project, defense)
    elif defense.get("status") == "failed":
        defense["questions"] = [
            {**q, "answer": None, "evidence_line": None, "ok": False, "mentor_ok": False, "check": "unanswered"}
            for q in defense.get("questions", [])
        ]
        defense["status"] = "pending"
        defense["passed"] = False
        defense["ok_count"] = 0
    if active_mentor(state) != "critic":
        switch_mentor(project, state, "critic", reason="defend", ref=defense["id"], forced=True)
    save(project, state, "defense", "session")
    payload = {
        "defense": defense,
        "instructions": "用 say 逐题回答；答案要引用作品具体行号（evidence_line），空话会被运行时判为未通过。",
    }
    if opts.get("--json"):
        cli.emit_json(payload)
        return 0
    print(f"防御性解释：{milestone['id']}「{milestone.get('title')}」共 {len(defense.get('questions', []))} 问")
    print("规则：三问中至少 2 问通过，且权重最大的维度那问必须通过；通过与否由运行时计算。")
    for question in defense.get("questions", []):
        print(f"  {question['qid']} [{question['dim']}] {question['question']}")
    print("")
    print("用 say 回答（可以一次答完），并给出作品具体行/段：")
    qs = defense.get("questions", [])
    example = "；".join(
        f"{q['qid']}：……（第 {n} 行）" for q, n in zip(qs, (1, 3, 5))
    )
    print(f'  say "{example}"')
    if defense.get("unsupported_questions"):
        print("[运行时] 已替换模板中引用未提供事实的问题，并记 defense_question_unsupported。")
    return 0


# --------------------------------------------------------------------------- #
# gap
# --------------------------------------------------------------------------- #
def _print_gaps(state: fs.State, show_all: bool) -> None:
    items = logic.order_gaps(state.gaps, state.brief, include_closed=show_all)
    if not items:
        print("没有缺口卡。先 review；缺口只由低于阈值的维度产生。")
        return
    rows = []
    for gap in items:
        rows.append(
            [
                gap["gap_id"],
                gap.get("milestone", ""),
                gap.get("dim", ""),
                f"{gap.get('score')}/{gap.get('threshold')}",
                str(logic.effective_weight(gap)),
                str(gap.get("status", "")),
                "未复验" if gap.get("unverified") else "",
                str(gap.get("attempts", "")),
                gap.get("source_review") or "",
            ]
        )
    print(
        cli.table(
            rows,
            ["gap_id", "milestone", "dim", "score/th", "weight", "status", "flag", "attempts", "source_review"],
        )
    )
    print("")
    print("排序：weight 降序 → (阈值−分) 降序 → 里程碑升序；stale 过的维度权重 ×0.6。")


def cmd_gap(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--all": "bool", "--json": "bool", "--force": "bool"})
    state = load(project)
    if positional and positional[0] == "learn":
        if len(positional) < 2:
            raise fs.UsageError("用法：gap learn GAP_ID")
        return _gap_learn(project, state, positional[1], offline, opts)
    if positional and positional[0] == "drop":
        if len(positional) < 2:
            raise fs.UsageError("用法：gap drop GAP_ID")
        return _gap_drop(project, state, positional[1], opts)
    if positional:
        raise fs.UsageError(f"未知 gap 子命令 {positional[0]!r}；可用 learn / drop")
    if opts.get("--json"):
        cli.emit_json(
            {
                "schema_version": fs.SCHEMA_VERSION,
                "items": logic.order_gaps(state.gaps, state.brief, include_closed=bool(opts.get("--all"))),
            }
        )
        return 0
    _print_gaps(state, bool(opts.get("--all")))
    return 0


def _gap_learn(project: fs.Project, state: fs.State, gap_id: str, offline: bool, opts: dict) -> int:
    gap = logic.gap_by_id(state.gaps, gap_id)
    if gap is None:
        raise fs.UsageError(f"没有这个缺口卡：{gap_id}")
    if gap.get("status") == "closed":
        print(f"{gap_id} 已关闭；不需要再上微课。")
        return 0
    if gap.get("status") == "unverified":
        print(f"{gap_id} 已达标，只缺行/段证据；补上证据后重新 review，不需要微课。")
        return 0
    if gap.get("status") == "stale":
        print(f"{gap_id} 已 drop（stale），不算解决；要重开请重新 review 该维度。")
        return cli.EXIT_STATE
    milestone = state.milestone(gap.get("milestone"))
    if milestone is None:
        raise fs.ForgeError(f"缺口卡指向不存在的里程碑 {gap.get('milestone')}")
    force = bool(opts.get("--force"))
    prior = str(gap.get("last_explanation") or "")
    artifact = logic.latest_artifact(state.artifacts, milestone["id"])
    prior_context = (
        "上次这张卡的讲解（不要逐字重复同一例子/同一答案；没有新内容就直接说没有新内容并让学习者先改一处）：\n"
        + prior[:900]
        if prior
        else ""
    )
    if gap.get("status") == "learning" and not force:
        # round-03 #1：同一张卡已上过微课且没有新的失败评审 -> 不重复讲
        runtime_next = next_action(project, state)
        context = mentor_mod.compact_context(
            state,
            artifact=artifact,
            gap=gap,
            extra=prior_context,
            project=project,
            handoff=project.latest_handoff(),
            runtime_next=runtime_next,
        )
        project.journal_append(
            "gap_repeat_suppressed",
            {
                "gap_id": gap_id,
                "milestone": milestone["id"],
                "dim": gap.get("dim"),
                "learn_count": gap.get("learn_count"),
                "prior_explanation": prior[:600],
                "context_has_prior": bool(prior and prior[:80] in context),
                "next": runtime_next.get("action"),
                "reason": "该卡已是 learning，且没有新的失败评审；先改作品再复评",
            },
            dedupe_key=f"gap_repeat:{gap_id}:{gap.get('learn_count')}",
        )
        print(f"{gap_id} 已上过微课（learn_count={gap.get('learn_count')}），不重复讲。")
        if prior:
            print("上次讲解摘要：" + prior[:300].replace("\n", " "))
        print("先按上次微课改一处，再 artifact add + review；确实需要重讲请用 gap learn --force。")
        print(authority_line(runtime_next))
        return 0
    previous_mentor = active_mentor(state)
    if previous_mentor != "guide":
        switch_mentor(project, state, "guide", reason="gap_learn", ref=gap_id, forced=True)
    fs.ensure_session(project, state, "guide")
    turn_index = int(state.session.get("turn_index", 0) or 0) + 1
    runtime = mentor_mod.MentorRuntime(project, offline=offline)
    turn = runtime.run(
        "guide",
        state,
        mentor_mod.gap_prompt(gap, milestone),
        artifact=artifact,
        gap=gap,
        extra_context=prior_context,
        runtime_next={
            "action": "gap_learn",
            "ref": gap_id,
            "reason": f"本轮只处理缺口 {gap_id}（{gap.get('dim')}）",
            "note": "讲完只要求学习者改一处并重新 artifact add + review；不要另开文件或另排任务。",
        },
    )
    updates, problems = mentor_mod.validate_block(turn, "guide")
    learn_count = int(gap.get("learn_count", 0)) + 1
    if updates is None:
        mentor_mod.record_missing(project, kind="guide", turn=turn, offline=runtime.offline)
    elif problems:
        mentor_mod.record_invalid(project, kind="guide", turn=turn, reasons=problems, offline=runtime.offline)
    else:
        notes, note_problems = mentor_mod.validate_gap(updates)
        if note_problems:
            mentor_mod.record_invalid(project, kind="guide", turn=turn, reasons=note_problems, offline=runtime.offline)
        else:
            if gap.get("status") == "open":
                gap["status"] = "learning"
            gap["learn_count"] = learn_count
            gap["learned_at"] = fs.now_iso()
            gap["covered_at"] = fs.now_iso()
            gap["guide_help_level"] = updates.get("help_level")
            gap["last_explanation"] = (runtime.label + turn.text)[:900]
            for entry in notes:
                if entry.get("dim") == gap.get("dim") and entry.get("note"):
                    gap["note"] = entry["note"][:200]
                    break
            gap["updated_at"] = fs.now_iso()
            project.journal_append(
                "gap_learned",
                {
                    "gap_id": gap_id,
                    "milestone": milestone["id"],
                    "dim": gap.get("dim"),
                    "help_level": updates.get("help_level"),
                    "learn_count": learn_count,
                    "prior_explanation_used": bool(prior),
                    "session": state.session.get("session_id"),
                    "card": gap,
                },
                dedupe_key=f"gap_learn:{gap_id}:{learn_count}",
            )
            _apply_help_and_attempt(project, state, "guide", turn_index, updates)
    mentor_text = runtime.label + turn.text
    _record_turn(
        project,
        state,
        mentor="guide",
        turn_index=turn_index,
        learner_text=f"gap learn {gap_id}",
        mentor_text=mentor_text,
        payload={
            "offline": runtime.offline,
            "help_level": (updates or {}).get("help_level"),
            "next": (updates or {}).get("next"),
        },
        record={
            "help_level": (updates or {}).get("help_level"),
            "next": (updates or {}).get("next"),
            "activity": f"gap-learn:{gap_id}",
            "offline": runtime.offline,
        },
        activity=f"gap-learn:{gap_id}",
    )
    save(project, state, "gaps", "session", "brief")
    if active_mentor(state) == "guide":
        switch_mentor(project, state, "coach", reason="gap_learned", ref=gap_id)
    save(project, state, "session")
    nxt = next_action(project, state)
    if opts.get("--json"):
        cli.emit_json({"ok": True, "gap": gap, "next": nxt})
        return 0
    print(mentor_text)
    print("")
    print(authority_line(nxt))
    print(
        f"缺口卡 {gap_id}：{gap.get('dim')} {gap.get('score')}/{gap.get('threshold')} → "
        f"status={gap.get('status')}（guide 只推进到 learning，关闭只能靠后续复评达标）"
    )
    print("微练习后如果独立完成（help_level<=1），该卡会标「未在作品复验」，但仍不算解决。")
    return 0


def _gap_drop(project: fs.Project, state: fs.State, gap_id: str, opts: dict) -> int:
    gap = logic.gap_by_id(state.gaps, gap_id)
    if gap is None:
        raise fs.UsageError(f"没有这个缺口卡：{gap_id}")
    result = logic.drop_gap(state.gaps, gap)
    if not result.get("ok"):
        if result.get("reason") == "already_stale":
            print(f"{gap_id} 已经是 stale。")
            return 0
        print(
            f"不能 drop：{gap_id} 只重开了 {result.get('attempts')} 次，"
            f"至少 {result.get('min_attempts')} 次仍未通过才允许记 stale。"
        )
        print("继续改作品后 review；不要用 drop 代替修改。")
        return cli.EXIT_STATE
    project.journal_append(
        "gap_dropped",
        {
            "gap_id": gap_id,
            "milestone": gap.get("milestone"),
            "dim": gap.get("dim"),
            "stale_drops": gap.get("stale_drops"),
            "effective_weight": logic.effective_weight(gap),
            "note": "stale 不算解决，doctor 会列出",
            "card": gap,
        },
        dedupe_key=f"gap_drop:{gap_id}:{gap.get('stale_drops')}",
    )
    save(project, state, "gaps")
    if opts.get("--json"):
        cli.emit_json({"ok": True, "gap": gap})
        return 0
    print(
        f"{gap_id} 记为 stale（不算解决）；该维度后续排序权重 ×0.6 → "
        f"{logic.effective_weight(gap)}；doctor 会列出。"
    )
    return 0


# --------------------------------------------------------------------------- #
# milestones
# --------------------------------------------------------------------------- #
def cmd_milestones(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--json": "bool"})
    if positional:
        raise fs.UsageError(f"milestones 不接受位置参数 {positional!r}")
    state = load(project)
    if opts.get("--json"):
        cli.emit_json(
            {
                "schema_version": fs.SCHEMA_VERSION,
                "current": state.brief.get("current_milestone"),
                "milestones": state.milestones,
            }
        )
        return 0
    rows = []
    for milestone in state.milestones:
        review = logic.latest_review_for_milestone(state.reviews, milestone["id"])
        defense = logic.defense_for_milestone(state.defense, milestone["id"])
        rows.append(
            [
                milestone["id"],
                milestone.get("title", ""),
                str(milestone.get("status", "")),
                str(len(logic.artifacts_for(state.artifacts, milestone["id"]))),
                str(len([r for r in state.reviews.get("items", []) if r.get("milestone") == milestone["id"]])),
                f"{review.get('weighted')}" if review else "-",
                (defense.get("status") if defense else "-"),
                (milestone.get("pass_evidence") or {}).get("evidence_level", "-"),
            ]
        )
    print(cli.table(rows, ["id", "title", "status", "artifacts", "reviews", "weighted", "defense", "evidence"]))
    print("")
    current = state.current or {}
    print(
        f"当前里程碑：{state.brief.get('current_milestone')}「{current.get('title', '')}」"
        f"status={current.get('status')}"
    )
    if state.brief.get("completed"):
        print("全部里程碑已通过：export --out 学习档案.md")
    return 0


# --------------------------------------------------------------------------- #
# pause / switch
# --------------------------------------------------------------------------- #
def cmd_pause(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--note": "value", "--json": "bool"})
    if positional:
        raise fs.UsageError(f"pause 不接受位置参数 {positional!r}")
    state = load(project)
    transitions = finalize(project, state)
    note = str(opts.get("--note") or "")
    if not state.session.get("session_id"):
        fs.ensure_session(project, state, active_mentor(state))
    session_id = state.session.get("session_id") or ""
    nxt = next_action(project, state)
    handoff = project.write_handoff(
        from_mentor=active_mentor(state),
        to_mentor="coach",
        reason="pause",
        open_items=open_items(state),
        ref=session_id,
        next_step=f"{nxt['action']}：{nxt.get('reason', '')}",
        note=note,
        session_id=session_id,
    )
    event = project.journal_append(
        "handoff",
        {
            "reason": "pause",
            "note": note,
            "session": session_id,
            "next": nxt["action"],
            "from": handoff.get("from"),
            "to": handoff.get("to"),
            "ref": handoff.get("ref"),
        },
        dedupe_key=f"pause:{session_id}:{sha256_text(note)[:12]}",
    )
    fs.close_session(project, state, note or "pause")
    state.session["mentor"] = "coach"
    state.brief["next"] = {"action": nxt["action"], "reason": nxt.get("reason"), "ref": nxt.get("ref")}
    state.brief["updated_at"] = fs.now_iso()
    save(project, state, "session", "brief")
    report = None
    if git_available():
        try:
            sync = GitSync(project.root, include=["."])
            _ensure_git_files(sync)
            report = sync.sync(default_sync_message(state.project.get("slug") or "forge", note))
        except LearnError as exc:
            cli.warn(f"sync 跳过：{exc}")
    if opts.get("--json"):
        cli.emit_json(
            {
                "ok": report is None or report.state != "conflict",
                "handoff": handoff,
                "event": event["id"] if event else None,
                "next": nxt,
                "transitions": transitions,
                "sync": report.as_dict() if report else None,
            }
        )
        return _sync_exit_code(report.state) if report else 0
    print(f"已暂停。交接写入 .learnark/handoff/latest.md（{session_id}）")
    print(f"未决事项：{'; '.join(handoff['open_items'])[:300]}")
    print(f"下次恢复：start（下一步 {nxt['action']}）")
    for item in transitions:
        print(f"[运行时] 里程碑 {item['id']} 通过（{item['status']}），已激活 {item.get('next') or '收尾'}")
    if report:
        print(report.headline())
        print(f"  remote={report.remote or '无远程（本地提交已保留，真实 GitHub 同步未验证）'}")
        if report.state == "conflict":
            files = _conflict_files(report)
            if files:
                print("  冲突文件：" + ", ".join(files))
            print(f"  恢复：{report.recovery or '本地与远程冲突，运行 sync 或 sync --recover'}")
    return _sync_exit_code(report.state) if report else 0


def cmd_switch(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--reason": "value", "--json": "bool"})
    if len(positional) != 1:
        raise fs.UsageError(f"用法：switch coach|critic|guide（可选：{', '.join(fs.MENTORS)}）")
    target = positional[0].strip().lower()
    if target not in fs.MENTORS:
        raise fs.UsageError(f"未知导师 {target!r}；可选：{', '.join(fs.MENTORS)}")
    state = load(project)
    fs.ensure_session(project, state, active_mentor(state))
    previous = active_mentor(state)
    if previous == target:
        print(f"已经是 {target} 导师，无需切换。")
        return 0
    handoff = switch_mentor(
        project,
        state,
        target,
        reason=str(opts.get("--reason") or "user_switch"),
        ref=f"user:{target}",
        forced=False,
    )
    save(project, state, "session", "brief")
    if opts.get("--json"):
        cli.emit_json({"ok": True, "from": previous, "to": target, "handoff": handoff})
        return 0
    print(f"已切换导师：{previous} → {target}")
    print(f"交接：.learnark/handoff/latest.md｜未决：{'; '.join((handoff or {}).get('open_items') or [])[:200]}")
    nxt = next_action(project, state)
    print(f"下一步：{nxt['action']}｜{nxt.get('reason', '')}")
    return 0


# --------------------------------------------------------------------------- #
# sync / doctor / export
# --------------------------------------------------------------------------- #
def _sync_exit_code(state: str) -> int:
    """0 success; 3 conflict (needs a human choice); 4 environment/network."""
    if state == "conflict":
        return cli.EXIT_STATE
    if state in ("commit-failed", "push-failed", "no-git"):
        return cli.EXIT_ENV
    return 0


def _ensure_git_files(sync: GitSync) -> list[str]:
    """Add .gitattributes/.gitignore to existing repos (old projects, round-04 #3)."""
    try:
        if sync.is_repo():
            return sync.ensure_repository()
    except LearnError:
        return []
    return []


def _conflict_files(report) -> list[str]:
    """Real conflicting paths from the recovery detail (blocking/unmerged lists)."""
    try:
        detail = json.loads(report.detail or "{}")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(detail, dict):
        return []
    files = detail.get("blocking") or detail.get("unmerged") or []
    return [str(item) for item in files]


def cmd_sync(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--message": "value", "--json": "bool", "--recover": "bool"})
    if positional:
        raise fs.UsageError(f"sync 不接受位置参数 {positional!r}")
    state = load(project)
    slug = state.project.get("slug") or "forge"
    message = str(opts.get("--message") or default_sync_message(slug))
    sync = GitSync(project.root, include=["."])
    added = _ensure_git_files(sync)
    recover = bool(opts.get("--recover"))
    report = sync.recover(message) if recover else sync.sync(message)
    unmerged = sync.unmerged_paths()
    conflict_files = unmerged or _conflict_files(report)
    diverged = bool(conflict_files) or (report.state == "conflict")
    project.journal_append(
        "sync",
        {
            "state": report.state,
            "recover": recover,
            "written": report.written,
            "committed": report.committed,
            "pushed": report.pushed,
            "sha": report.sha,
            "files": len(report.files),
            "remote": report.remote,
            "unmerged": conflict_files,
            "diverged": diverged,
            "git_files_added": added,
        },
        dedupe_key=f"sync:{report.sha}:{report.state}:{recover}",
    )
    if opts.get("--json"):
        payload = report.as_dict()
        payload.update(
            {
                "recover": recover,
                "unmerged": conflict_files,
                "diverged": diverged,
                "git_files_added": added,
            }
        )
        cli.emit_json(payload)
        return _sync_exit_code(report.state)
    print(report.headline())
    print(f"  written={'yes' if report.written else 'no'}（文件已落盘）")
    print(f"  committed={'yes' if report.committed else 'no'}" + (f"（{report.sha}）" if report.sha else ""))
    print(f"  pushed={'yes' if report.pushed else 'no'}")
    if recover:
        print("  recover=yes（journal 并集合并；快照冲突不会自动合并）")
    if added:
        print("  已补齐：" + ", ".join(added))
    if report.files:
        print(f"  本次提交 {len(report.files)} 个文件")
    print(f"  remote={report.remote or '无远程（本地提交已保留；真实 GitHub 同步未验证）'}")
    if conflict_files:
        print("  冲突文件：" + ", ".join(conflict_files))
    if report.recovery:
        print(f"  恢复：{report.recovery}")
    if report.detail:
        print(f"  详情：{report.detail[:400]}")
    return _sync_exit_code(report.state)


def _doctor_checks(project: fs.Project, state: fs.State, offline: bool) -> tuple[list[dict], list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    infos: list[dict] = []

    # 1. 状态文件
    try:
        for name in ("project", "brief", "artifacts", "reviews", "gaps", "defense", "session"):
            project.load(name)
        infos.append({"name": "状态文件", "detail": "7 个快照均可读"})
    except (StateCorrupt, ValueError, OSError) as exc:
        errors.append({"name": "状态文件", "detail": f"无法读取：{exc}"})
    # 2. schema / 模板
    for name in ("project", "brief", "artifacts", "reviews", "gaps", "defense"):
        version = getattr(state, name).get("schema_version")
        if version != fs.SCHEMA_VERSION:
            errors.append(
                {"name": f"schema_version[{name}]", "detail": f"期望 {fs.SCHEMA_VERSION}，实际 {version!r}"}
            )
    template = None
    try:
        template = fs.load_template(str(state.brief.get("template") or "agent-dev"))
    except LearnError as exc:
        errors.append({"name": "模板", "detail": f"无法读取模板：{exc}"})
    if template is not None:
        expected = {
            item["id"]: {d["dim"]: (int(d["weight"]), int(d["threshold"])) for d in item["rubric"]}
            for item in template["milestones"]
        }
        for milestone in state.milestones:
            actual = {d["dim"]: (int(d["weight"]), int(d["threshold"])) for d in milestone.get("rubric", [])}
            if milestone["id"] not in expected:
                errors.append({"name": f"rubric[{milestone['id']}]", "detail": "里程碑不在模板中"})
            elif expected[milestone["id"]] != actual:
                errors.append(
                    {"name": f"rubric[{milestone['id']}]", "detail": "维度/权重/阈值与模板不一致（rubric 只读）"}
                )
        if fs.rubric_signature(state.milestones) != state.brief.get("rubric_sha256"):
            errors.append({"name": "rubric_sha256", "detail": "brief 记录的 rubric 指纹与当前不一致（可能被改动）"})
    # 3. journal
    integrity = project.journal.integrity()
    if integrity["problems"]:
        for problem in integrity["problems"]:
            errors.append({"name": "journal", "detail": problem})
    else:
        infos.append({"name": "journal", "detail": f"{integrity['events']} 条事件，序号/ID/去重键一致"})
    # 4. 去重索引
    index_path = project.journal.index_path
    keys = {event.get("dedupe_key") for event in project.journal.all() if event.get("dedupe_key")}
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
        if not isinstance(index, dict):
            raise ValueError("not a dict")
        missing = sorted(keys - set(index))
        if missing:
            warnings.append({"name": "去重索引", "detail": f"{len(missing)} 个键缺失，可运行 doctor --rebuild 重建"})
        else:
            infos.append({"name": "去重索引", "detail": f"{len(index)} 个键，与 journal 一致"})
    except (ValueError, OSError) as exc:
        warnings.append({"name": "去重索引", "detail": f"损坏（{exc}），可从 journal 重建"})
    # 5. 锁
    lock_files = list(project.state_dir.glob("*.lock")) + list(project.journal_dir.glob("*.lock"))
    locks = [path.name for path in lock_files]
    infos.append({"name": "锁文件", "detail": ", ".join(locks) if locks else "无残留锁"})
    # 6. git
    sync = GitSync(project.root, include=["."])
    if not sync.available():
        warnings.append({"name": "git", "detail": "未安装 git：无法提交/推送，学习记录仍在本机"})
    elif not sync.is_repo():
        warnings.append({"name": "git", "detail": "项目不是 git 仓库：运行 git init 后 sync"})
    else:
        status = sync.status()
        remote = status.get("remote") or "无"
        infos.append(
            {
                "name": "git",
                "detail": f"branch={status.get('branch')} remote={remote} changed={len(status.get('changed', []))} "
                f"ahead={status.get('ahead')} behind={status.get('behind')} "
                f"diverged={'yes' if status.get('diverged') else 'no'}",
            }
        )
        if status.get("unmerged"):
            errors.append(
                {
                    "name": "git 冲突",
                    "detail": "未合并文件：" + ", ".join(status["unmerged"])
                    + "（先解决冲突；journal-only 可用 sync --recover）",
                }
            )
        elif status.get("diverged"):
            errors.append(
                {
                    "name": "git 分叉",
                    "detail": f"本地与远程分叉（ahead={status.get('ahead')} behind={status.get('behind')}）："
                    "运行 sync；journal-only 冲突可用 sync --recover，快照冲突需人工选择",
                }
            )
        if sync.rebase_in_progress():
            errors.append({"name": "git rebase", "detail": "有未完成的 rebase：git status 查看，或 sync --recover"})
        attributes = project.root / ".gitattributes"
        if not attributes.is_file():
            warnings.append(
                {"name": ".gitattributes", "detail": "缺少 `* -text`：克隆后作品 sha 可能因换行变化；运行 sync 或 init 会自动补上"}
            )
        if not status.get("remote"):
            warnings.append({"name": "git remote", "detail": "无远程：本地提交有效，跨设备同步未验证（不是错误）"})
    # 7. LLM 配置
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LEARNARK_API_KEY")
    mode = (os.environ.get("LEARNARK_LLM") or "auto").lower()
    if mode == "mock" or offline:
        infos.append({"name": "LLM", "detail": "离线脚本导师（LEARNARK_LLM=mock）；不代表真实教学质量"})
    elif key:
        infos.append({"name": "LLM", "detail": "已配置 API key（不写入项目文件）"})
    else:
        warnings.append({"name": "LLM", "detail": "未配置 DEEPSEEK_API_KEY：say/review 会失败；可用 --offline"})
    # 8. 缺口与证据链
    for gap in state.gaps.get("items", []):
        if gap.get("status") == "stale":
            warnings.append(
                {
                    "name": "stale 缺口",
                    "detail": f"{gap['gap_id']}（{gap.get('dim')}）不算解决，权重 {logic.effective_weight(gap)}",
                }
            )
        if gap.get("status") != "closed":
            continue
        if gap.get("closed_by") != "review":
            warnings.append({"name": "缺口关闭", "detail": f"{gap['gap_id']} closed_by={gap.get('closed_by')!r}"})
            continue
        source_sha = gap.get("source_artifact_sha")
        closed_sha = gap.get("closed_artifact_sha")
        if source_sha and closed_sha and source_sha == closed_sha:
            errors.append({"name": "缺口关闭", "detail": f"{gap['gap_id']} 未修改即关闭（复评 sha 与来源 sha 相同）"})
    unverified = [gap for gap in state.gaps.get("items", []) if gap.get("unverified")]
    if unverified:
        warnings.append(
            {
                "name": "未复验缺口",
                "detail": ", ".join(gap["gap_id"] for gap in unverified) + " 只降优先级，不算解决",
            }
        )
    # 9. 作品完整性
    for item in state.artifacts.get("items", []):
        path = project.root / str(item.get("path") or "")
        if not path.is_file():
            errors.append({"name": "作品文件", "detail": f"{item['id']} 缺失 {item.get('path')}"})
            continue
        if fs.sha256_file(path) != item.get("sha256"):
            errors.append({"name": "作品文件", "detail": f"{item['id']} sha256 与记录不一致（文件被改回或篡改）"})
    if state.artifacts.get("items"):
        infos.append({"name": "作品", "detail": f"{len(state.artifacts['items'])} 件，sha256 已校验"})
    # 9b. journal 与快照对账：事件已落盘但快照缺失时，自动恢复失败也必须可见。
    artifact_keys = {(item.get("milestone"), item.get("sha256")) for item in state.artifacts.get("items", [])}
    for event in project.journal.of_kind("artifact_added"):
        payload = event.get("payload") or {}
        key = (payload.get("milestone"), payload.get("sha256"))
        if key not in artifact_keys:
            errors.append(
                {
                    "name": "journal/作品",
                    "detail": f"{event.get('id')} 记录了 {key[0]} 作品 {str(key[1])[:12]}，"
                    "但 artifacts.json 没有且未能从磁盘恢复；运行 status 查看恢复说明",
                }
            )
    review_ids = {item.get("id") for item in state.reviews.get("items", [])}
    for event in project.journal.of_kind("review_recorded"):
        review_id = (event.get("payload") or {}).get("review_id")
        if review_id and review_id not in review_ids:
            errors.append(
                {
                    "name": "journal/评审",
                    "detail": f"{event.get('id')} 记录了评审 {review_id}，但 reviews.json 没有；"
                    "运行 status 触发自动恢复，或重新 review",
                }
            )
    defense_ids = {item.get("id") for item in state.defense.get("items", [])}
    for event in project.journal.of_kind("defense_recorded"):
        defense_id = (event.get("payload") or {}).get("defense_id")
        if defense_id and defense_id not in defense_ids:
            errors.append(
                {
                    "name": "journal/防御",
                    "detail": f"{event.get('id')} 记录了防御 {defense_id}，但 defense.json 没有；"
                    "运行 status 触发自动恢复",
                }
            )
    # 10. 防御
    for defense in state.defense.get("items", []):
        if defense.get("status") == "pending":
            warnings.append({"name": "defense", "detail": f"{defense['id']} 待作答（{defense.get('artifact_id')}）"})
        elif defense.get("status") == "failed":
            warnings.append({"name": "defense", "detail": f"{defense['id']} 未通过（{defense.get('ok_count')} 问）"})
    # 11. 版本
    if learncore.CORE_VERSION != fs.core_version():
        errors.append(
            {
                "name": "core 版本",
                "detail": f"runtime/CORE_VERSION={fs.core_version()} 与 learncore={learncore.CORE_VERSION} 不一致",
            }
        )
    else:
        infos.append({"name": "core", "detail": f"learncore {learncore.CORE_VERSION}（vendored）"})
    # 12. 结构
    if not state.milestones:
        errors.append({"name": "里程碑", "detail": "brief.json 没有里程碑"})
    else:
        active = [milestone for milestone in state.milestones if milestone.get("status") == "active"]
        passed = [
            milestone for milestone in state.milestones if milestone.get("status") in ("passed", "passed_assisted")
        ]
        if len(active) > 1:
            errors.append({"name": "里程碑", "detail": f"同时有 {len(active)} 个 active：{[m['id'] for m in active]}"})
        infos.append(
            {
                "name": "里程碑",
                "detail": f"{len(state.milestones)} 个（{len(passed)} 通过，{len(active)} 进行中），"
                f"当前 {state.brief.get('current_milestone')}",
            }
        )
    handoff = project.latest_handoff()
    infos.append(
        {
            "name": "交接",
            "detail": f"{handoff.get('from')} → {handoff.get('to')}（{handoff.get('reason')}）"
            if handoff
            else "还没有交接记录（pause/switch 会写）",
        }
    )
    return errors, warnings, infos


def cmd_doctor(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--json": "bool", "--rebuild": "bool"})
    if positional:
        raise fs.UsageError(f"doctor 不接受位置参数 {positional!r}")
    state = load(project)
    if opts.get("--rebuild"):
        keys = {event.get("dedupe_key") for event in project.journal.all() if event.get("dedupe_key")}
        fs.write_json(project.journal.index_path, {key: "" for key in sorted(keys)})
    errors, warnings, infos = _doctor_checks(project, state, offline)
    ok = not errors
    if opts.get("--json"):
        cli.emit_json(
            {
                "schema_version": fs.SCHEMA_VERSION,
                "ok": ok,
                "errors": errors,
                "warnings": warnings,
                "infos": infos,
                "next": next_action(project, state),
            }
        )
        return 0 if ok else cli.EXIT_STATE
    print("Forge doctor")
    for item in infos:
        print(f"  [ok]   {item['name']}：{item['detail']}")
    for item in warnings:
        print(f"  [warn] {item['name']}：{item['detail']}")
    for item in errors:
        print(f"  [FAIL] {item['name']}：{item['detail']}")
    print("")
    if errors:
        print(f"发现 {len(errors)} 个问题（退出码 3）。建议先修第一条；状态文件损坏会从 .bak 自动恢复。")
        return cli.EXIT_STATE
    print(f"自检通过：0 个错误，{len(warnings)} 个提示。下一步：{next_action(project, state)['action']}")
    return 0


def _five_tuple(gap: dict) -> str:
    review_id = gap.get("closed_by_review") or gap.get("source_review") or "-"
    source_sha = (gap.get("source_artifact_sha") or "")[:12]
    closed_sha = (gap.get("closed_artifact_sha") or "")[:12]
    return "\n".join(
        [
            f"- `{gap['gap_id']}`（{gap.get('dim')}）",
            f"  1. artifact：`{source_sha}`（来源评审 {gap.get('source_review')}）",
            f"  2. review：`{review_id}` 分数 {gap.get('score')}/{gap.get('threshold')}，"
            f"note：{str(gap.get('note', ''))[:120]}",
            f"  3. gap：证据 artifact `{source_sha}`，状态 {gap.get('status')}",
            f"  4. fix：新 sha `{closed_sha}`（来源 sha 必须不同，否则 doctor 报「未修改即关闭」）",
            f"  5. re-review：`{review_id}` 同维度达阈值 → closed_by={gap.get('closed_by')}",
        ]
    )


def cmd_export(project: fs.Project, args: list[str], offline: bool) -> int:
    opts, positional = parse_flags(args, {"--out": "value", "--json": "bool"})
    if not opts.get("--out"):
        raise fs.UsageError("export 需要 --out FILE")
    if positional:
        raise fs.UsageError(f"export 不接受位置参数 {positional!r}")
    state = load(project)
    finalize(project, state)
    out_path = Path(str(opts["--out"])).expanduser()
    if not out_path.is_absolute():
        out_path = (Path.cwd() / out_path).resolve()
    brief = state.brief
    lines = [
        f"# Forge 学习档案 · {brief.get('goal')}",
        "",
        f"- 版本：{fs.VARIANT_ID} {fs.VARIANT_VERSION}｜learncore {learncore.CORE_VERSION}｜"
        f"schema_version {fs.SCHEMA_VERSION}",
        f"- 模板：{brief.get('template')}｜每周预算：{brief.get('minutes_per_week')} 小时",
        f"- 导出时间：{fs.now_iso()}{'（模拟时钟）' if clock.is_simulated() else ''}",
        f"- 学习模式："
        f"{'离线脚本导师（不代表真实教学质量）' if (offline or os.environ.get('LEARNARK_LLM', '').lower() == 'mock') else '在线 LLM'}",
        "",
        "> 证据纪律：只有 `help_level <= 1` 的正确尝试可提升能力；自述不算证据；",
        "> 里程碑通过 = 作品（sha256）+ rubric 全维达阈值 + defense ≥2/3 且最重维度通过。",
        "",
        "## 里程碑",
        "",
        "| id | 里程碑 | 状态 | 作品数 | 评审数 | 通过证据（artifact / review / defense） |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for milestone in state.milestones:
        evidence = milestone.get("pass_evidence") or {}
        lines.append(
            f"| {milestone['id']} | {milestone.get('title', '')} | {milestone.get('status')} | "
            f"{len(logic.artifacts_for(state.artifacts, milestone['id']))} | "
            f"{len([r for r in state.reviews.get('items', []) if r.get('milestone') == milestone['id']])} | "
            f"{evidence.get('artifact_id', '-')} / {evidence.get('review_id', '-')} / "
            f"{evidence.get('defense_id', '-')} |"
        )
    lines += ["", "## Rubric 与最近分数", ""]
    for milestone in state.milestones:
        review = logic.latest_review_for_milestone(state.reviews, milestone["id"])
        scores = {d["dim"]: d["score"] for d in (review or {}).get("rubric", [])}
        lines.append(f"### {milestone['id']}「{milestone.get('title', '')}」")
        lines.append("")
        lines.append("| dim | weight | threshold | score | 达标 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for dim in milestone.get("rubric", []):
            score = scores.get(dim["dim"])
            label = "-" if score is None else ("达标" if int(score) >= int(dim["threshold"]) else "未达标")
            lines.append(
                f"| {dim['dim']} | {dim['weight']} | {dim['threshold']} | "
                f"{score if score is not None else '-'} | {label} |"
            )
        lines.append("")
    lines += [
        "## 作品",
        "",
        "| id | milestone | path | sha256 | bytes | assisted_level | supersedes |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in state.artifacts.get("items", []):
        lines.append(
            f"| {item['id']} | {item.get('milestone')} | {item.get('path')} | {str(item.get('sha256'))[:16]}… | "
            f"{item.get('size')} | {item.get('assisted_level')} | {item.get('supersedes') or '-'} |"
        )
    lines += ["", "## 评审", ""]
    if state.reviews.get("items"):
        lines += [
            "| review | artifact | 分数 | 加权 | 达阈值 | clamped |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for review in state.reviews["items"]:
            scores = " ".join(f"{d['dim']}={d['score']}" for d in review.get("rubric", []))
            lines.append(
                f"| {review['id']} | {review.get('artifact_id')} | {scores} | {review.get('weighted')} | "
                f"{review.get('threshold_pass')} | {len(review.get('clamped') or [])} |"
            )
    else:
        lines.append("（还没有评审）")
    lines += ["", "## 缺口卡", ""]
    if state.gaps.get("items"):
        lines += [
            "| gap_id | dim | score/threshold | weight | status | attempts | 未复验 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for gap in logic.order_gaps(state.gaps, brief, include_closed=True):
            lines.append(
                f"| {gap['gap_id']} | {gap.get('dim')} | {gap.get('score')}/{gap.get('threshold')} | "
                f"{logic.effective_weight(gap)} | {gap.get('status')} | {gap.get('attempts')} | "
                f"{'是' if gap.get('unverified') else ''} |"
            )
        lines += ["", "### 已解决缺口的五元组", ""]
        closed = [gap for gap in state.gaps["items"] if gap.get("status") == "closed"]
        if closed:
            for gap in closed:
                lines.append(_five_tuple(gap))
                lines.append("")
        else:
            lines += ["（还没有通过复评关闭的缺口）", ""]
    else:
        lines.append("（还没有缺口卡）")
    lines += ["", "## 防御性解释", ""]
    if state.defense.get("items"):
        for defense in state.defense["items"]:
            lines.append(
                f"- `{defense['id']}` {defense.get('milestone')} 状态 {defense.get('status')}，"
                f"{defense.get('ok_count')}/{len(defense.get('questions', []))} 通过"
                + ("（最重维度通过）" if defense.get("heaviest_ok") else "（最重维度未通过）")
            )
            for question in defense.get("questions", []):
                lines.append(
                    f"  - {question['qid']} [{question['dim']}] {question.get('question')} → "
                    f"{'通过' if question.get('ok') else '未通过'}"
                    + (f"（行 {question.get('evidence_line')}）" if question.get("evidence_line") else "")
                )
    else:
        lines.append("（还没有防御记录）")
    handoff = project.latest_handoff()
    lines += ["", "## 最近交接", ""]
    if handoff:
        lines += [
            f"- from: `{handoff.get('from')}`",
            f"- to: `{handoff.get('to')}`",
            f"- reason: {handoff.get('reason')}",
            f"- ref: `{handoff.get('ref')}`",
            f"- open_items: {'; '.join(handoff.get('open_items') or []) or '(无)'}",
            f"- next: {handoff.get('next') or ''}",
        ]
    else:
        lines.append("（还没有交接记录）")
    sessions = (
        sorted(path.name for path in project.sessions_dir.glob("*.md")) if project.sessions_dir.is_dir() else []
    )
    lines += ["", "## 会话记录", ""]
    lines += [f"- `sessions/{name}`" for name in sessions] if sessions else ["（还没有会话文件）"]
    lines += [
        "",
        "## 声明",
        "",
        "- 本档案由运行时根据 journal 与快照生成；不含 API key。",
        "- 若时间戳标记为模拟时钟，仅证明调度逻辑，不代表真实学习时长。",
        "- 离线脚本导师的输出不代表真实教学质量，也不能当作真实 LLM 证据。",
        "",
    ]
    atomic_write_text(out_path, "\n".join(lines) + "\n")
    if opts.get("--json"):
        cli.emit_json({"ok": True, "out": str(out_path), "bytes": out_path.stat().st_size})
        return 0
    print(f"已导出：{out_path}（{out_path.stat().st_size} 字节）")
    return 0


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #
HANDLERS = {
    "start": cmd_start,
    "say": cmd_say,
    "status": cmd_status,
    "next": cmd_next,
    "task": cmd_task,
    "artifact": cmd_artifact,
    "review": cmd_review,
    "defend": cmd_defend,
    "gap": cmd_gap,
    "milestones": cmd_milestones,
    "pause": cmd_pause,
    "switch": cmd_switch,
    "sync": cmd_sync,
    "doctor": cmd_doctor,
    "export": cmd_export,
}


def dispatch(project_arg: str | None, offline: bool, argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0 if argv else 2
    command = argv[0]
    rest = argv[1:]
    if command == "init":
        return cmd_init(project_arg, rest, offline)
    if command not in HANDLERS:
        cli.warn(f"learn: 未知命令 {command!r}\n")
        print(USAGE)
        return cli.EXIT_USAGE
    project = fs.Project.find(project_arg)
    project.require()
    # One writer per project at a time: commands touch journal + several snapshots,
    # and a per-file CAS alone can abort after the journal event is already durable.
    with project.write_lock():
        return HANDLERS[command](project, rest, offline)


def main(argv: list[str] | None = None) -> int:
    try:
        project_arg, offline, rest = parse_globals(list(sys.argv[1:] if argv is None else argv))
    except fs.UsageError as exc:
        cli.warn(f"learn: {exc}")
        return cli.EXIT_USAGE
    try:
        return dispatch(project_arg, offline, rest)
    except fs.UsageError as exc:
        cli.warn(f"learn: {exc}")
        return cli.EXIT_USAGE
    except fs.ForgeError as exc:
        cli.warn(f"learn: {exc}")
        return cli.EXIT_STATE


if __name__ == "__main__":
    sys.exit(cli.main(main))
