"""Generated project documents: README.md (learner) and AGENTS.md (any agent)."""

from __future__ import annotations

from learncore import clock

from . import VARIANT_NAME, VARIANT_VERSION
from .const import MENTOR_LABELS, MENTORS
from .templates import VARIANT_ROOT


def _entry_block(command: str) -> str:
    root = str(VARIANT_ROOT)
    return (
        "```powershell\n"
        f'$LA = "{root}"   # 指向本仓库的 direction-c-atelier 目录\n'
        f'python "$LA\\runtime\\learn.py" {command}\n'
        "```\n"
        "> 如果 `learn.cmd` 已在 PATH，也可以直接 `learn.cmd " + command + "`。"
    )


def _safe_email_goal(project: dict) -> str:
    goal = str(project.get("goal") or "英文工作邮件写作")
    banned = ("agent", "json", "help_level", "tool call", "工具调用")
    return "英文工作邮件写作" if any(word in goal.lower() for word in banned) else goal


def readme_text(project: dict, plan: dict) -> str:
    is_email = (project.get("template") or "") == "email"
    goal = _safe_email_goal(project) if is_email else (project.get("goal") or "（目标待填写）")
    objective = (plan.get("current_objective") or {}).get("text") or "先由 planner 定计划"
    example = (
        'say "帮我把这封邮件改到 150 词，只保留一个诉求"'
        if is_email
        else 'say "我卡在工具调用的报错上"'
    )
    lines = [
        f"# {project.get('template_title') or '学习项目'}",
        "",
        f"**目标**：{goal}",
        "",
        "## 现在输入什么",
        "",
        "在 PowerShell 里执行下面两行（本文件夹就是项目根）：",
        "",
        _entry_block("start"),
        "",
        f"它会告诉你：上次停在哪、计划当前是哪一步（{objective}）、这一轮该找哪位导师。",
        "第一次进入时 planner 会先用几个问题校准起点，自述不算能力。",
        "",
        "## 三条最常用命令",
        "",
        "```powershell",
        f'python "$LA\\runtime\\learn.py" {example}   # 说话、得到回复、自动记录',
        f'python "$LA\\runtime\\learn.py" switch coach                   # 点名换导师（会写交接单）',
        f'python "$LA\\runtime\\learn.py" pause                          # 结束本次：写交接、保存、本地提交',
        "```",
        "",
        "## 你的记录在哪里",
        "",
        "- `.learnark/`：目标、计划、能力证据、五份导师私有笔记、交接单、事件日志。",
        "- `sessions/`：每次会话的师生原文与帮助等级。",
        "- `artifacts/`：练习产物与导出档案。",
        "- 换电脑或换会话：只靠这些文件恢复，不靠聊天记录。",
        "",
        "## 五位导师",
        "",
    ]
    for mentor in MENTORS:
        lines.append(f"- **{MENTOR_LABELS[mentor]}**")
    lines += [
        "",
        "## 离线模式",
        "",
        "`--offline` 会用脚本导师跑通流程，输出以 `[离线脚本导师]` 开头；它不代表真实教学质量，",
        "记录里也会标 `synthetic`。真实使用请设置 `DEEPSEEK_API_KEY`。",
        "",
        f"## 版本",
        "",
        f"{VARIANT_NAME} {VARIANT_VERSION}（schema 1） · 生成于 {clock.now_iso(timespec='minutes')}",
        "",
        "> 完成/掌握不是导师说的，是运行时按帮助等级与 examiner 判定写入的。",
        "",
    ]
    return "\n".join(lines)


def _email_agents_text(project: dict) -> str:
    lines = [
        "# 入口说明 · 给任何学习助手",
        "",
        f"这是一个 LearnArk Atelier 英文工作邮件学习项目（`{project.get('slug')}`）。你的工作是接续，不是重讲。",
        "",
        "## 第一步（必做）",
        "",
        "在项目根目录执行：",
        "",
        _entry_block("start"),
        "",
        "它只读计划并打开会话，告诉你：上次停在哪、当前计划版本与下一步、该用哪位导师。",
        "不要用聊天历史或记忆代替它；不要凭空编造学习记录。",
        "",
        "## 权威记录（按顺序）",
        "",
        "1. `.learnark/journal/events`：权威事件流，只追加。",
        "2. `.learnark/state/studio`：计划、当前导师、待批变更、未决项。",
        "3. `.learnark/state/capability`：能力证据，只能由运行时写入。",
        "4. `.learnark/handoff/latest.md`：上一手交接。",
        "5. `.learnark/state/mentors/<id>`：各导师私有笔记，只给本人读。",
        "",
        "## 规则",
        "",
        "- 只用 `learn.cmd` 的写命令（`say`/`switch`/`plan`/`examine`/`review`/`pause`），不要手改计划或事件流。",
        "- 计划权威属于 planner：只有 planner 能让计划变更生效；其他导师只能提案。",
        "- 证据纪律：帮助等级 2 及以上只算受助完成；只有 examiner 在无提示下判 pass 才写 verified。",
        "- 换导师/结束会写交接：known / what_tried / open_loops / next / do_not_redo 由运行时合成，导师只给 why。",
        "- 导师每轮要给出可解析的记录块；块非法时运行时不应用任何状态，并保留本轮原文。",
        "- 离线时输出以 [离线脚本导师] 开头，不能当作真实教学证据。",
        "",
        "## 常用命令",
        "",
        "```text",
        "start | say TEXT | status | pause --note TEXT",
        "switch MENTOR | examine | review",
        "studio | plan | handoff --check",
        "sync | doctor | export --out FILE",
        "```",
        "",
        "## 邮件练习",
        "",
        "- 先写主题行与第一段，把唯一诉求放在首句，原因退到第二句。",
        "- 反馈要指到具体句子或词，不重写整封代替学习者练习。",
        "- 写作产物放在 `artifacts/<活动>.md`，导出的档案也在 `artifacts/`。",
        "",
        f"项目目标：{_safe_email_goal(project)}",
        "",
    ]
    return "\n".join(lines)


def agents_text(project: dict) -> str:
    if (project.get("template") or "") == "email":
        return _email_agents_text(project)
    lines = [
        "# AGENTS.md · 给任何 DSH / Agent 的入口说明",
        "",
        f"这是一个 LearnArk Atelier 学习项目（`{project.get('slug')}`）。你（Agent）的工作是**接续**，不是重讲。",
        "",
        "## 第一步（必做）",
        "",
        "在项目根目录执行：",
        "",
        _entry_block("start"),
        "",
        "它只读项目文件，告诉你：上次停在哪、当前计划版本与下一步、该用哪位导师。",
        "**不要**用聊天历史或记忆代替它；不要凭空编造学习记录。",
        "",
        "## 状态文件（权威顺序）",
        "",
        "1. `.learnark/journal/events.jsonl` —— 权威事件流，只追加。",
        "2. `.learnark/state/studio.json` —— 计划、当前导师、待批计划变更、未决项。",
        "3. `.learnark/state/capability.json` —— 能力证据，**只能由运行时写入**。",
        "4. `.learnark/handoff/latest.md` —— 上一手交接（机器块权威）。",
        "5. `.learnark/state/mentors/<id>.json` —— 各自私有笔记，只给本人读。",
        "",
        "## 规则",
        "",
        "- 只用 `learn.cmd` 的写命令（`say`/`switch`/`plan`/`examine`/`review`/`pause`），不要手改 `studio.plan` 或 journal。",
        "- 计划权威属于 planner：只有 planner 能让 `plan_change` 生效；其他导师只能提案（proposed）。",
        "- 证据纪律：`help_level >= 2` 只算受助完成；只有 examiner 会话在 `help_level=0` 下的 `pass` 能写 verified。",
        "- 换导师/结束会写 handoff：`known/what_tried/open_loops/next/do_not_redo` 由运行时从 journal、会话和计划合成，导师只需给 `why`。",
        "- 导师每轮必须给 `learn-update` 机器块；块非法时运行时会记 `mentor_update_invalid` 且**不应用**任何状态。",
        "- 离线（`--offline` 或没有 key）时输出以 `[离线脚本导师]` 开头，不能当作真实教学证据。",
        "",
        "## 常用命令",
        "",
        "```text",
        "start | say TEXT | status [--json] | pause [--note TEXT]",
        "switch MENTOR [--fill-missing] | examine | review",
        "studio | plan [--json] | handoff [--last N|--check]",
        "sync | doctor | export --out FILE",
        "```",
        "",
        "## 交接契约",
        "",
        "文件 `.learnark/handoff/<YYYYMMDDTHHMMSS>-<from>-to-<to>.md`，末尾 ```handoff 机器块必填：",
        "`handoff_id/schema_version/from/to/why/known/what_tried/do_not_redo/open_loops/next/created_at`。",
        "`known/what_tried/open_loops/next/do_not_redo` 由运行时从 journal、会话与计划合成，导师只提供 `why`；",
        "`do_not_redo` 只收明确说过的条目，空列表是正常的。",
        "",
        f"项目目标：{project.get('goal') or '（未填写）'}",
        "",
    ]
    return "\n".join(lines)
