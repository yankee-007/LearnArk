# 方向 A 简令 — SkillMap（能力地图路径型）

> 给研发子 Agent 的输入。完整约束以 `shared/requirements.md`、`shared/spec-core.md`、`shared/acceptance.md` 为准。
> 目录：`variants/direction-a-skillmap/`

## 1. 产品主张

把学习目标拆成**带先修关系的能力地图**。首次进入做诊断定位，之后每次学习都在“未掌握 + 先修就绪 + 复习到期”的节点上，按 讲解 → 操练 → 应用 → 检查 四段推进。适合“不知道从哪学、怕漏基础、离开后想定位”的学习者。

假设：显式地图能减少迷路和重复，先修检查能避免“看似学会其实悬空”；代价是前期地图/诊断开销。

## 2. 与别方向的实质区别（必须可观察）

- 有持久的能力地图（节点 + prereq + 等级 + 证据），不是任务列表或活动池。
- 首次进入必做诊断（≥3 个探测问题），诊断结果改变第一个学习任务。
- 四段活动有明确的进入条件；**只有** 独立（help_level ≤ 1）通过 apply/check 才提升等级。
- 先修未达标记的节点不出现在可选下一步（除非用户显式选择）。

## 3. 导师角色（≥4，阶段绑定）

| id | 职责 | 何时出现 |
| --- | --- | --- |
| navigator | 诊断、定位、解释为什么学这个节点、复习安排 | 首次进入、阶段切换、复习 |
| concept | 概念讲解、类比、检查理解 | explain 阶段 |
| coach | 操练与应用辅导、分级提示 | drill / apply 阶段 |
| examiner | 检查与迁移题、判定证据、不给提示 | check 阶段 |

导师由运行时按阶段自动切换（也允许用户 `switch`）。每次切换写 handoff（从谁到谁、为什么、未决事项）。

## 4. 命令面

最小命令面（见 spec-core）+ 方向特有：

- `map [--json]`：能力地图进度（节点、等级、先修、状态、下次复习）。
- `next`：解释下一个节点与理由（先修/薄弱/到期）。
- `diagnose`：重新诊断（可选，用于自述变化）。
- `review`：到期复习队列，进入检查活动。

## 5. 状态模型（建议，不强制）

`.learnark/state/map.json`：`{schema_version, nodes:[{id,title,cluster,prereqs[],level,target_level,evidence:[{event_id,kind,help_level,at}],review_due,status}], updated_at}`

`.learnark/state/plan.json`：`{current_node, stage, stage_started_at, session_goal, next_candidates:[...]}`

会话/事件：`journal/events.jsonl`（诊断、尝试、等级变化、复习、切换、同步）。

## 6. 下一步算法（必须实现且可解释）

候选节点 = 先修全部 ≥ 门槛 且 status != mastered；排序键：复习到期 > 当前节点未完成阶段 > 等级低 > 目标覆盖优先级。输出必须说明理由。

## 7. 方向特有验收（至少 3 项）

- **A-S1 先修门控**：前置节点未达标时，后续节点不会出现在 `next`，且说明原因。
- **A-S2 诊断生效**：诊断结论不同的学习者，首个活动不同（用两个模拟档案验证）。
- **A-S3 证据门槛**：help_level ≥ 2 的通过不提升等级；help_level ≤ 1 的独立通过才提升，且每轮最多 +1。
- **A-S4 复习调度**：到期节点进入 `review` 队列，未到期不打扰。

## 8. 主要风险

地图过细导致负担；诊断题目本身偏难/偏易；等级判定被导师话术带偏（必须靠运行时证据规则）。

## 9. 交付物

`design.md`、`version-manifest.json`、`START_HERE.md`、`mentors/*.md`、`curriculum/*`、`templates/{agent-dev,email}.md`、`runtime/`（含 vendored `learncore`）、`tests/`、`examples/`、`issues.md`（可空，后续轮次写）。

`version-manifest.json` 至少：

```json
{"id":"direction-a-skillmap","name":"SkillMap 能力地图","version":"0.1.0","core_version":"1.0.0","entry":"runtime/learn.py","schema_version":1,"mentors":["navigator","concept","coach","examiner"],"built_at":"...","known_limits":["..."]}
```
