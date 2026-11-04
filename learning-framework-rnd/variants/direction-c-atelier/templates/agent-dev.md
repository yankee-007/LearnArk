# 模板 · agent-dev（`init --template agent-dev`）

本文件是 `init` 的结构化输入：首个 `## ` 之前形如 `key: value` 的行是模板字段（标题与说明行忽略），正文为表格；运行时用标准库解析后写入 `project.json` 与初始 `studio.json`。

template: agent-dev
schema_version: 1
title: Agent 开发 · 四周最小闭环
goal_default: 在 4 周内独立做出一个可运行、可评测的最小 Agent，并能说清它的边界
minutes_per_week_default: 12
first_session_minutes: 20
mentor_order: planner,concept,coach,examiner,reviewer
default_mentor: planner
plan_id: plan-v1

## 目标默认值

`goal_default` 可直接被 `--goal` 覆盖；`--minutes-per-week` 覆盖 `minutes_per_week_default`。若学习者周时长低于 4 小时，planner 首次会话必须把第 4 周标记为「可顺延」，不得压缩考核。

## 导师初始计划骨架

`steps` 顺序即默认推进顺序；`owner` 表示该步骤默认由谁带；`evidence` 是运行时判定「过没过」的依据。

| # | week | step_id | 内容 | owner | activity_id | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | `w1-agent-loop` | 说清 Agent 与单次问答的差别 | concept | — | 能复述四要素 |
| 2 | 1 | `w1-agent-loop-ex1` | 手写「模型→工具→观察→再决策」伪代码 | coach | `w1-agent-loop-ex1` | 伪代码含终止条件 |
| 3 | 1 | `w1-agent-loop-ex2` | 口述三种停止条件 | examiner | `w1-agent-loop-ex2` | exam-a 通过 |
| 4 | 2 | `w2-tools-ex1` | 工具 schema 与参数校验 | coach | `w2-tools-ex1` | 脏输入被拒 |
| 5 | 2 | `w2-tools-ex2` | 幂等重试与预算上限 | coach | `w2-tools-ex2` | 重放两次一条副作用 |
| 6 | 2 | `w2-tools-exam` | exam-b 判定 | examiner | `exam-b` | verdict=pass |
| 7 | 3 | `w3-memory` | 三种状态与「检索≠记忆」 | concept | — | 能指出坏在哪一步 |
| 8 | 3 | `w3-memory-ex1` | 三栏分类表 | coach | `w3-memory-ex1` | 每条有寿命与写入者 |
| 9 | 4 | `w4-eval-ex1` | 10 条用例 + 失败分类 | coach | `w4-eval-ex1` | 每类失败能定位到层 |
| 10 | 4 | `w4-eval-exam` | exam-c 判定 + 交付说明 | examiner | `exam-c` | verdict=pass 且有 README |

## 主题模块

| module_id | week | 标题 | 能力目标 | activity_ids | exam_id |
| --- | --- | --- | --- | --- | --- |
| `w1-agent-loop` | 1 | 循环与边界 | 循环四要素、三种终止条件、单轮成本 | `w1-agent-loop-ex1`,`w1-agent-loop-ex2` | `exam-a` |
| `w2-tools` | 2 | 工具与可靠性 | schema/校验、错误分层、幂等、预算 | `w2-tools-ex1`,`w2-tools-ex2` | `exam-b` |
| `w3-memory` | 3 | 状态与记忆 | 上下文/记忆/检索三者的寿命与写入 | `w3-memory-ex1` | `exam-c` |
| `w4-eval` | 4 | 评测与交付 | 评测集、失败分类、护栏、README | `w4-eval-ex1` | `exam-c` |

## 首次诊断（写入 handoff 的 known）

| probe_id | 问题 | 期望要点 | 判读 |
| --- | --- | --- | --- |
| `probe-d1` | 工具调用失败，第一步看什么 | 原始返回与日志 | 只会改提示词 → `self_report` |
| `probe-d2` | 检索与记忆差在哪 | 临时注入 vs 跨会话保留 | 只背名词 → `self_report` |
| `probe-d3` | 凭什么说改好了 | 固定用例/回放 | 「感觉顺了」→ `self_report` |

## do_not_redo 种子

- 2026-11-04：不要用「RAG 就是长期记忆」类比开场。
- 2026-11-04：不要用「框架三行代码搞定」制造虚假完成感。

## 约束默认值

- 仅标准库、可离线运行；产物写入 `artifacts/`，文件名带 `activity_id`。
- 每轮结束必须能回答「下一步做哪一个 step_id」。
- 对外部资料的引用不得替代自己的复述；引用过的一律记 `observed`，不记 `verified`。
