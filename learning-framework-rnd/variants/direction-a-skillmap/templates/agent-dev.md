---
template: agent-dev
schema_version: 1
title: "Agent 开发"
default_goal: "能独立设计与实现最小可用 Agent：调用、工具、循环、记忆、评测"
default_minutes_per_week: 600
level_scale: 3
prereq_gate: 1
mastery_gate: 2
stages: [explain, drill, apply, check]
mentors: [navigator, concept, coach, examiner]
review_intervals: [1, 3, 7, 16, 35]
---

# 模板 · agent-dev

供 `learn.py init --goal ... --template agent-dev` 读取：生成 `map.json` 节点、`project.json` 默认值，并把诊断/阶段/证据规则注入运行时。

## 1. 目标默认值
- `goal`（可被 `--goal` 覆盖）：`能独立设计与实现最小可用 Agent：调用、工具、循环、记忆、评测`
- `minutes_per_week`：600（10 小时，可 600–1200；`--minutes-per-week` 可覆盖）；单次 20 分钟只承诺推进**一个阶段**，不承诺一个节点。
- 学习者画像：接触过 Python 与 HTTP API、借助 AI 做过 RAG；**自述不等于能力**，一律先按“待验证假设”处理。
- 非目标：不做零基础 Python 系统课；不做自由聊天；每条导师输出必须挂在某节点的某阶段活动上。

## 2. 节点清单（12 节点 / 5 簇）

| id | title | cluster | prereqs | target_level |
| --- | --- | --- | --- | --- |
| A1 | Python 数据结构与异常 | foundation | （无） | 3 |
| A2 | HTTP/API 与 JSON 边界 | foundation | A1 | 3 |
| B1 | 消息结构与角色 | llm | A2 | 3 |
| B2 | 结构化输出与解析 | llm | B1 | 3 |
| B3 | 超时/限流/重试 | llm | B2 | 3 |
| C1 | 工具 schema 定义 | tools | B1 | 3 |
| C2 | 调用往返 | tools | C1, B2 | 3 |
| C3 | Agent 循环与终止 | tools | C2, B3 | 3 |
| C4 | 错误处理与幂等 | tools | C3 | 3 |
| D1 | 会话记忆与上下文预算 | memory | C3 | 3 |
| D2 | RAG 边界 | memory | D1, C2 | 3 |
| E1 | 评测集与回归 | evaluation | C3, C4 | 3 |

- `prereq_gate=1`（可用门槛）：先修全部 ≥L1 就解锁后继；`mastery_gate=2`：只有 L2 才代表先修已被独立应用，用于证据陈述而非隐藏任务。`target_level` 统一 3（= 独立迁移），达到即移出候选。
- `gate_override=true` 允许强制进入被锁节点，但等级上限锁 L1，且 `next` 必须说明“已越过先修门槛”。
- 活动 id 规则：`<node_id>-<stage>`，例如 `C3-apply`；诊断/复习/交接用保留值 `diagnose`、`review`、`handoff`。

## 3. 阶段说明

| stage | 进入条件 | 导师 | 学习者产出 | 退出（通过） | 不通过 / 超时 |
| --- | --- | --- | --- | --- | --- |
| explain | 先修全 ≥L1（可用门槛）且本节点 ≤L1 | concept | 用自己的话复述 ≥2 个要点 + 答 1 个“为什么” | 复述通过且 help_level≤1 | ≤4 轮 / 8 分钟；仍不行写 `prereq_gap`，退回最低未达标先修 |
| drill | explain 通过 | coach | 2 道同类操练 | 连续 2 题在 help_level≤1 下正确 | 拆成两步降难度，最多 2 次；10 分钟超时写 `stage_timeout` |
| apply | drill 通过 | coach | `artifacts/` 下可运行产物 | 产物可跑 + 1 道变式 + help_level≤1 | `help_level≥2` 记 `assisted_completion` 并回 drill（最多 2 次） |
| check | apply 通过 | examiner | 独立题 + 迁移题答案与真实输出 | 两题都对且 help_level=0 | 写 `misconception`；同一错因连续 2 次 → `status=decayed` 并插 explain |

跨会话续段允许：一次会话只完成一个阶段即算达标，`pause` 写清断点。

## 4. 首次诊断

`diagnosis.status` 初始 `pending`，`start` 自动切 navigator。5 题约 6 分钟，可跳过（跳过记 `skipped`，全部节点按 L0 起）。

| 探针 | 题面（运行时原文，正文必须照抄） | 锚点节点 |
| --- | --- | --- |
| Q1 | 用自己的话讲一次 tool call 的一来一回：模型输出什么？你的代码做什么？结果怎么回到模型那里？ | B1 |
| Q2 | 读出这段伪代码里终止条件的 bug，并说明它为什么停不下来：`i = 0` / `while i < 5:` / `call_tool()` / `i += 0` | C2 |
| Q3 | RAG 与会话记忆的区别是什么？各自解决什么问题、什么时候会失效？ | D2 |
| Q4 | 一次 HTTP 调用超时了，你会怎么处理？请说到异常类型、超时分层与是否重试。 | A2 |
| Q5 | 给一个只做加法的小工具任务设计最小评测：用例从哪来、怎么判定通过。 | E1 |

- 题面的唯一权威是运行时（`sm_model` 的 `probes`，同时出现在 `mentors/navigator.md` 与每轮控制台页脚）；导师正文必须照抄，不得另写代码或换题。
- 机器块用 `probe: {"node": 锚点, "level": 0|1, "reason": "一句依据"}` 把评级写进地图；只写在正文里不会生效，`level` 只能是 0 或 1。
- 每题写 `diagnosis_probe` 事件；“不知道”是合法答案，记 `unknown`。
- **只允许置 L0 或 L1**，不得置 L2 以上；自述只进 `learner.self_report[]`，生成待验证假设。
- 结束写 `diagnosis_done`，重算 `status`，首次输出 `next`（含 3 条理由与被排除节点及原因）。
- **诊断定位**：若某锚点被探针置 L1、且其全部先修也 ≥L1（可用门槛），直接把它设为 `current_node`、`stage=apply`，写 `placement_applied{node,level,probe,reason}`；有先修仍为 L0 的节点不参与定位。

## 5. 等级与证据

| level | 含义 | 最低证据 |
| --- | --- | --- |
| L0 | 未接触 | 无事件，或只有自述 |
| L1 | 接触（能说不能做） | explain 复述通过 + ≥1 次 `help_level≥2` 的完成 |
| L2 | 独立应用 | apply 在 `help_level≤1` 下通过 + 变式 + `artifacts/` 产物 |
| L3 | 独立迁移 | check 迁移题 `help_level=0` 通过，且 ≥7 天后复测再通过 |

- `help_level`：0 无提示／1 单句方向／2 分步或伪代码／3 给答案或代写。
- 只有 `correct=true 且 help_level≤1` 计入升级；`≥2` 一律 `assisted_completion`，最多推到 L1；check 阶段强制 0。
- 单轮最多 +1，超出记 `level_cap`；升级必须能追到 `event_id` + 产物路径（`source=verified` 需 `file_sha256`）。
- 降级只发生在 review 失败或 `doctor` 发现产物缺失，需记 `reason`、`at`、`lapses`。

## 6. 复习

- 间隔 `[1, 3, 7, 16, 35]` 天，`interval_index` 0–4：通过 +1（封顶 4），失败 −2（下限 0），`due = today + interval[index]`。
- 每会话最多 2 个复习节点；20 分钟会话只做 1 个；复习走 check（1 题、≤5 分钟、零提示）。
- 幂等键 `sha256(session_id|activity_id|answer)`，重复提交不重复加分。

## 7. 导师与切换

- explain→concept；drill/apply→coach；check→examiner；诊断、阶段交接、复习→navigator。
- 每次切换写 `handoff`（from、to、reason、unresolved、context_digest），并注入下一导师上下文。
- examiner 返回 `help_level≥1` → 运行时拒收、记 `examiner_help_violation`、该轮作废重出题。

## 8. 运行约束

- Windows 优先，Python 3.14，**仅标准库**；密钥只从 `DEEPSEEK_API_KEY` / `LEARNARK_API_KEY` 读，不落盘、不打印。
- 所有产物写 `artifacts/`（相对路径入库）；会话写 `sessions/`；离线模式用 `LEARNARK_LLM=mock` 并标注“离线脚本导师”。
- 命令示例：`python -c "import sys;print(sys.version)"`；`if ($env:DEEPSEEK_API_KEY) {"set"} else {"missing"}`。

## 9. 内容文件索引

- 导师系统提示：`mentors/navigator.md`、`mentors/concept.md`、`mentors/coach.md`、`mentors/examiner.md`
- 节点教学内容：`curriculum/agent-dev.md`
- 离线脚本：`tests/fixtures/mentor_script.jsonl`
