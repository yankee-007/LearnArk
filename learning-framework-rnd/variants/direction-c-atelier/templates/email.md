# 模板 · email（`init --template email`）

非编程迁移模板。首个 `## ` 之前形如 `key: value` 的行是模板字段（标题与说明行忽略），正文为表格；结构与另一个模板相同，内容与评分标准完全不同。

template: email
schema_version: 1
title: 英文工作邮件 · 四周写作工作坊
goal_default: 在 4 周内能独立写出 150 词以内、诉求单一、语气适配收件人的英文工作邮件
minutes_per_week_default: 3
first_session_minutes: 20
mentor_order: planner,concept,coach,examiner,reviewer
default_mentor: planner
plan_id: plan-e1

## 目标默认值

默认每周 3 小时（写作可短时高频）。`--minutes` 小于 20 时，planner 只排「读—改—比」三步，不新增写作任务；任何一次都必须产出可保存的文本，不接受「只在脑子里想」。

## 导师初始计划骨架

| # | week | step_id | 内容 | owner | activity_id | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | `em-w1-structure` | 主题行、首段、单一诉求 | concept | — | 能说出 BLUF 的含义 |
| 2 | 1 | `em-w1-rewrite` | 把 200 词坏邮件改到 120 词 | coach | `em-w1-structure` | 事实无损、诉求唯一 |
| 3 | 2 | `em-w2-request` | 写一封跨团队请求 | coach | `em-w2-request` | 有明确截止与回执方式 |
| 4 | 3 | `em-w3-decline` | 拒绝不合理截止，给两个替代 | coach | `em-w3-decline` | 有新时间与代价 |
| 5 | 3 | `em-w3-exam` | 改写题判定 | examiner | `exam-e1` | verdict=pass |
| 6 | 4 | `em-w4-followup` | 升级前的两次跟进 | coach | `em-w4-followup` | 不指责、标时间点 |
| 7 | 4 | `em-w4-exam` | 情境题判定 | examiner | `exam-e2` | verdict=pass |

## 主题模块

| module_id | week | 标题 | 能力目标 | activity_ids | exam_id |
| --- | --- | --- | --- | --- | --- |
| `em-w1-structure` | 1 | 结构与主题行 | 主题可检索、首段给结论、一信一诉求 | `em-w1-structure`,`em-w1-rewrite` | `exam-e1` |
| `em-w2-request` | 2 | 请求与状态同步 | 请求具体、截止明确、回执方式清楚 | `em-w2-request` | `exam-e1` |
| `em-w3-decline` | 3 | 拒绝与延期 | 不伤人地拒绝、延期给补救 | `em-w3-decline` | `exam-e1` |
| `em-w4-followup` | 4 | 跟进与升级 | 节奏化跟进、升级前提醒 | `em-w4-followup` | `exam-e2` |

## 首次诊断（写入 handoff 的 known）

| probe_id | 任务 | 判读 |
| --- | --- | --- |
| `probe-e1` | 把一句中文诉求写成英文主题行 | 只译字面 → `self_report`；含动作与时间 → `observed` |
| `probe-e2` | 指出一封样例邮件最该先删的一句 | 说得出「与诉求无关」→ `observed` |

## do_not_redo 种子

- 2026-11-04：不要用「模板套用」代替结构讲解；先讲读者与诉求。
- 2026-11-04：不要用中文思维逐句直译，句式重写优先。

## 约束默认值

- 产出保存为 `artifacts/em-<activity_id>.md`；每次至少留一版改前/改后对照。
- 评分只看收件人能否一次行动，不看词藻难度。
- 引用范文不构成独立完成，一律记 `observed`。
