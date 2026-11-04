# 方向 C 简令 — Atelier（多导师工作室型）

> 给研发子 Agent 的输入。完整约束以 `shared/requirements.md`、`shared/spec-core.md`、`shared/acceptance.md` 为准。
> 目录：`variants/direction-c-atelier/`

## 1. 产品主张

把学习做成一个小型**工作室**：五个职责不同的导师各有会话与笔记，交接有契约。学习者说“我卡在报错了”可以点名找 coach，说“帮我定这周计划”找 planner。适合需要不同帮助形态、又怕换人后重复解释的学习者。

假设：明确分工 + 强制交接契约能提高连续性；代价是切换与交接开销，若契约不完整会变成互相推诿。

## 2. 与别方向的实质区别（必须可观察）

- 五导师各自独立会话目录与私有笔记；同一问题不同导师有不同职责边界。
- 每次切换产生结构化 handoff（含 do-not-redo、open loops、next），并注入下一导师上下文。
- planner 的计划是权威；coach 不得静默改计划（需要改必须写 plan-change 事件）。
- examiner 的判定独立于 coach，不能由 coach 自评通过。

## 3. 导师角色（固定 5 个）

| id | 职责 | 不该做 |
| --- | --- | --- |
| planner | 目标澄清、周计划、节奏与取舍 | 不代做练习、不判分 |
| concept | 概念讲解、类比、最小模型 | 不安排长期计划、不评分 |
| coach | 练习辅导、调试、分级提示 | 不宣布掌握、不改计划 |
| examiner | 考核、迁移题、掌握判定 | 不给提示、不辅导 |
| reviewer | 复盘、遗忘检查、跨主题迁移、下周建议 | 不重复教学、不改当前任务 |

## 4. 命令面

最小命令面 + 方向特有：

- `studio`：导师列表 + 各自最近活动 + 未决事项 + 当前计划。
- `switch <mentor>`：切换并写 handoff（未知导师报错并列出）。
- `handoff [--last N]`：查看交接记录。
- `plan`：planner 的当前计划与进度。
- `examine`：请求 examiner 考核（切换并开始检查）。
- `review`：reviewer 复盘（不是复习队列，命名需在 START_HERE 说明）。

## 5. 状态模型（建议）

`.learnark/state/studio.json`：`{schema_version, plan:{week_goals[],current_objective,steps[]}, mentors:{id:{last_active,notes_path,open_loops[]}}, updated_at}`

`.learnark/state/mentors/<id>.json`：该导师的私有笔记（最近结论、已讲过什么、下一步建议）。

`.learnark/handoff/<timestamp>-<from>-to-<to>.md` + `latest.md`。

## 6. 下一步算法（必须实现且可解释）

由 planner 的 current_objective + 最近未决事项决定：若存在未通过考核 → examiner；若存在未关闭 open loop → 对应导师；否则按计划 steps 推进；每 N 轮建议 reviewer 复盘（N 可配，默认 4）。

## 7. 方向特有验收（至少 3 项）

- **C-S1 职责分离**：coach 不能宣布掌握；examiner 不给提示；越界请求被拒绝并转交。
- **C-S2 交接完整**：handoff 含 from/to/why/known/open loops/do-not-redo/next；缺失字段要报错。
- **C-S3 不重复劳动**：切换后新导师不重复已讲内容（do-not-redo 生效，有证据）。
- **C-S4 计划一致性**：coach 改动计划必须留下 plan-change 记录，planner 可见。

## 8. 主要风险

交接形式化（写了但没用）；五导师上下文重复/成本高（必须做紧凑摘要）；职责边界被 LLM 忽略（运行时与协议双重约束）。

## 9. 交付物

同 A。`templates/agent-dev.md` 定义五导师共用的主题种子；`templates/email.md` 同理。
