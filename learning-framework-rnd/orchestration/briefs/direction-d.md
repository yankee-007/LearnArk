# 方向 D 简令 — Tempo（动态调度复习型）

> 给研发子 Agent 的输入。完整约束以 `shared/requirements.md`、`shared/spec-core.md`、`shared/acceptance.md` 为准。
> 目录：`variants/direction-d-tempo/`

## 1. 产品主张

面向碎片时间：每次进入先问“今天有多少分钟”（可一句话给出），调度器从微活动池里选一个 5–20 分钟的活动，优先到期复习与薄弱点，尽量少让用户做决定。适合“每天只有二十分钟、经常中断”的学习者。

假设：低决策负担 + 间隔复习能提高坚持率与保持率；代价是缺少大块项目深度（需要用“周项目块”补）。

## 2. 与别方向的实质区别（必须可观察）

- 时间是第一输入：`start --minutes 20`（默认 20；可一句话“只有二十分钟”解析）。
- 有可解释的调度打分（到期度、薄弱度、计划推进、时长匹配、最近重复惩罚），并显示候选与理由。
- 有真正的到期队列（SRS），`due` 可查看；遗忘卡来自错误与误解。
- 活动是 5–20 分钟的微单元，没有长课程表；同一天两次短会话不重复同一活动。

## 3. 导师角色（≥3，活动绑定）

| id | 职责 |
| --- | --- |
| coach | 讲解/回述/应用类活动，给最小提示 |
| trainer | 回忆卡、kata、快速练习（高节奏、少解释） |
| examiner | 小测与迁移检查，不给提示 |

调度由运行时负责，导师不得自行改计划；`start` 输出“为什么选这个”。

## 4. 命令面

最小命令面 + 方向特有：

- `start [--minutes N]`：调度并开始一个活动。
- `due`：到期队列（含过期天数）。
- `plan`：今日/本周建议（≤3 项），不制造欠账焦虑。
- `review`：进入到期复习（等同选择到期活动）。
- `skills`：技能/卡片状态（等级、下次到期、错误标签）。

## 5. 状态模型（建议）

`.learnark/state/schedule.json`：`{schema_version, minutes_default, last_activity_id, last_activity_at, today:{date,minutes_left,items[]}, updated_at}`

`.learnark/state/skills.json`：`[{id,title,tags[],level,stability,last_review,due_at,lapses,evidence[]}]`

`.learnark/state/cards.json`：`[{id,skill,front,back,source_event,due_at,interval,ease,lapses}]`（遗忘卡/误解卡）

## 6. 调度算法（必须实现且可解释）

候选 = 到期复习 ∪ 计划项 ∪ 薄弱技能 ∪ 新增概念；打分 = w1·到期紧急度 + w2·薄弱度 + w3·计划推进 + w4·时长匹配 − w5·最近重复。输出 top 3 + 选中理由。不同 `--minutes` 必须可能改变选择（要有测试）。

## 7. 方向特有验收（至少 3 项）

- **D-S1 预算生效**：`--minutes 5/20/45` 在构造的候选集下选择不同活动（确定性测试）。
- **D-S2 到期优先**：到期复习分数高于新内容（可解释输出 + 测试）。
- **D-S3 不重复**：同一天两次短会话不选同一活动（除非用户显式要求）。
- **D-S4 低负担**：默认参数下，用户只输入一句话即可开始，无需读文档。

## 8. 主要风险

过度碎片化、缺少作品深度；SRS 参数不合理导致复习轰炸；LLM 输出与调度冲突（运行时以调度为准）。

## 9. 交付物

同 A。`templates/agent-dev.md` 定义技能集、微活动类型与卡片种子；`templates/email.md` 定义写作微技能与卡片。
