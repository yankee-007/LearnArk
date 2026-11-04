# 方向 B 简令 — Forge（任务作品驱动型）

> 给研发子 Agent 的输入。完整约束以 `shared/requirements.md`、`shared/spec-core.md`、`shared/acceptance.md` 为准。
> 目录：`variants/direction-b-forge/`

## 1. 产品主张

不先排课程，而是围绕**可交付作品**组织学习：给出里程碑与 rubric，学习者先做，暴露缺口，再由导师补概念。适合“有动力做东西、讨厌先学理论”的学习者。

假设：作品驱动能提高开始率与迁移；代价是基础薄弱者可能挫败，需要有“缺口微课”兜底。

## 2. 与别方向的实质区别（必须可观察）

- 没有能力地图/课程表；首页是当前**里程碑任务**与 rubric。
- 学习活动由作品提交触发：`artifact` → `review`（rubric 评分）→ 缺口卡 → 微课。
- 里程碑只有在“作品存在 + rubric 达标 + 学习者能解释设计”三者同时满足时才通过。
- 下一步由 rubric 缺口和里程碑状态决定，而不是知识图谱。

## 3. 导师角色（≥3，模式绑定）

| id | 职责 | 模式 |
| --- | --- | --- |
| coach | 任务拆解、卡点辅导、示范与逐步放手 | 默认 |
| critic | 严格评审作品，按 rubric 打分并给可执行修改项 | review |
| guide | 针对缺口卡讲最小必要概念 | 缺口微课 |

用户可 `switch`；`review` 由运行时切到 critic，结束后回到 coach 并写 handoff。

## 4. 命令面

最小命令面 + 方向特有：

- `task`：当前里程碑、任务说明、rubric、状态。
- `artifact add PATH|--note TEXT`：登记作品（复制进 `artifacts/`、记录 hash/size）；重复登记同 hash 不重复计分。
- `artifact list`
- `review [artifact-id]`：切到 critic 评审，输出 rubric 分数与缺口卡。
- `gap [--all]`：缺口列表；`gap learn <id>` 让 guide 讲最小概念。
- `milestones`：里程碑全景与状态。

## 5. 状态模型（建议）

`.learnark/state/brief.json`：`{schema_version, milestones:[{id,title,deliverable,rubric:[{dim,criteria,weight,threshold}],status,artifact_ids[],review:{scores,passed,notes,at}}], current_milestone, updated_at}`

`.learnark/state/artifacts.json`：`[{id, path, sha256, size, submitted_at, milestone}]`

`.learnark/state/gaps.json`：`[{id, dim, note, status(open/learning/closed), source_review}]`

## 6. 下一步算法（必须实现且可解释）

1. 当前里程碑无作品 → 继续做任务；
2. 有新作品未评审 → review；
3. rubric 未达标 → 缺口卡按权重排序，进入 gap 微课；
4. rubric 达标但未解释设计 → defense 提问；
5. 全部满足 → 里程碑通过，进入下一个。

## 7. 方向特有验收（至少 3 项）

- **B-S1 作品门控**：无作品或 rubric 不达标时，里程碑不能变为 passed；尝试作弊（只说“我做完了”）必须被拒绝。
- **B-S2 评分驱动**：rubric 低分维度直接决定下一步微课主题。
- **B-S3 重复提交幂等**：同一作品（同 sha256）重复提交/评审不重复计分。
- **B-S4 防御性解释**：学习者无法解释设计时，不能记为独立完成。

## 8. 主要风险

基础薄弱者直接做任务会挫败；rubric 主观导致评分不稳定；LLM 评分虚高（运行时需 clamp 与证据校验）。

## 9. 交付物

同 A（`design.md`、`version-manifest.json`、`START_HERE.md`、`mentors/`、`curriculum/`、`templates/`、`runtime/`、`tests/`、`examples/`）。
`templates/agent-dev.md` 给 3 个里程碑与 rubric；`templates/email.md` 改为“写 3 封不同场景邮件 + 修改说明”的作品集。
