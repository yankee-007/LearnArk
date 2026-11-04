# Atelier 多导师工作室 · 产品设计

版本 0.1.0 · core 1.0.0 · 2026-11-04 · 目录 `variants/direction-c-atelier/`

## 1. 主张、学习者、非目标

**一句话主张**：把一次学习拆成五个职责不重叠的导师席位，每次换人必须留下一份机器可校验的交接单；学习者随时点名自己当下需要的那种帮助，不必重新解释自己是谁、学到哪。

**目标学习者**：已有零散经验（跟教程跑过、看视频能复述、两周就模糊）的自学者；每周 10–20 小时、单次常只有 20 分钟；需要不同形态的帮助（讲清概念 / 陪调试 / 被独立考一次 / 被复盘），最烦“换个窗口就从头讲一遍”。对应画像 P2、P3。

**非目标**：不做零基础保姆（首次只需一个入口即可，见 A/D）；不做作品集驱动（B）；不做多个真人在线——“多导师”是角色与会话，不是人；不做代码自动评分沙箱；不宣称真人长期学习收益。

## 2. 核心假设与替代解释

**H0**：职责分离 + 强制交接契约 → 连续性（重复教学减少、安排矛盾减少、单导师上下文负担降低），代价是切换与交接开销。

可证伪方式：同一目标跑两条路径——完整 Atelier 与消融版（合并 concept+coach，保留交接契约与 `next_step()`）——比较每 20 回合的重复教学次数、矛盾安排次数、每回合上下文字符数。

替代解释：
- **H1**：连续性其实来自“单一 `next_step()` + 紧凑共享状态”，与五个席位无关。若消融版指标持平，H0 被削弱。设计上先给 H1 让路：排程权归运行时，交接单的 `next` 只是建议。
- **H2**：收益来自“可点名”的控制感。用固定导师组对照。
- **H3**：只是措辞更专业。交换两位导师的提示词，若体验评分不变，则分工是文案撑起来的。

## 3. 流程

最小命令面照 `spec-core.md`；方向特有：`studio`、`plan`、`handoff [--last N|--check]`、`examine`、`review`。

### 3.1 首次进入
`init` → `start`。无 plan 时进入引导态：planner 先做 ≤4 轮诊断（一问目标 + 一个真实小任务），写 plan v1（week_goals、current_objective、steps、success_criteria、est_minutes），发 `plan_created`，再按 `next_step()` 移交。自述一律记 `self_report`，不升级能力。

### 3.2 一次 20 分钟会话（跨 coach → examiner → reviewer）
1. `start --minutes 20`：只打计划卡与 `next_step()` 结论（“coach，因 OL-7 阻塞未解”），不调模型。
2. coach 3 回合：读自身笔记 + 最新 handoff + plan + 最近 8 条投影事件；分级提示，第三回合 `help_level=1` 通过。
3. coach 写交接（to=examiner，why=“仅在一级提示下通过，需独立验证”），自动切换。
4. examiner 一道迁移题：只拿到 objective、success_criteria、任务去重表、上次 misconception，**拿不到 coach 的提示文本**。学习者独立答对 → `verdict=pass`，写 verified 证据。
5. `pause`：`since_review=4`，reviewer 做复盘与下周建议交 planner；planner 接受后改周目标并记 `plan_change`。

### 3.3 点名导师
- 显式：`switch coach`、`examine`（= 切 examiner 并开考）、`review`。
- 自然语言：`say "卡在报错了，找 coach"`。运行时用确定性关键词表（角色名 + 意图词）匹配，歧义追问一次，未命中按计划走。
- 与 `next_step()` 不一致**不阻止**，但打一行“偏离建议：计划当前指向 examiner，理由…”，记 `mentor_named{named_by:user}`；交接 why=“用户点名”。

## 4. 五导师职责表

| 导师 | 做 | 不做 | 何时被调用 | 输出到 |
| --- | --- | --- | --- | --- |
| planner | 目标澄清、周目标、steps 排序、时间预算取舍、批准 plan-change | 不代做练习、不判分、不讲解 | 首次进入、换周、有 plan-change 待批、`plan` | `state/studio.json` 的 plan、`state/mentors/planner.json`、`sessions/` |
| concept | 最小模型、类比、反例、一页总结 | 不排计划、不评分、不长陪调试 | 新 objective 首次接触、coach 报“概念缺口” | 私有笔记 `taught/avoid`、会话 |
| coach | 分级提示、调试、拆步、给可运行的最小下一步 | 不宣布掌握、不改计划、不替 examiner 判定 | 有练习 step、有阻塞 open loop、被点名 | 私有笔记、`attempt` 事件、`plan_change` 提案 |
| examiner | 迁移题/回忆题、判定、写 verified 证据 | 不给提示、不辅导、不复用做过的题 | 待独立验证的 open loop、`examine`、计划的 check step | `state/capability.json` 证据、`exam` 事件、会话 |
| reviewer | 复盘、遗忘检查、错因归类、下周建议 | 不重复教学、不改当前任务、不新判掌握 | `since_review≥4`、`pause`、周末、`review` | `state/reviews.json`、建议型 plan-change |

## 5. 交接契约

文件 `.learnark/handoff/<YYYYMMDDTHHMMSS>-<from>-to-<to>.md`（时间戳去冒号，保证 Windows 合法；同秒冲突以 `handoff_id` 为准），正文末尾一个 fenced `handoff` 块；同 payload 作为 `handoff` 事件入 journal（`dedupe_key=handoff_id`）；`latest.md` 为最新一份渲染副本。`protocols/handoff.md` 里的 YAML 头只作人读摘要、不参与校验：`what_tried` 与 `handoff_id` 必须出现在机器块内，只写在 YAML 头里视为缺字段。可选的 `plan_snapshot` 写入时须等于当前 `plan.version`，不符记 `handoff_stale_plan`。

```handoff
{"handoff_id":"H-0012","schema_version":1,"from":"coach","to":"examiner",
 "why":"仅在一级提示下通过，需独立验证",
 "known":["能写出 tool schema","知道结果要回注 messages"],
 "what_tried":["node-2-apply 两次，第二次 help_level=1 通过"],
 "do_not_redo":["不再讲“函数+参数+结果回注”三段式","不再布置 node-2-apply"],
 "open_loops":[{"id":"OL-7","owner":"examiner","due":"2026-11-05","text":"独立完成一次迁移题","blocking":true}],
 "next":"换场景考一次","created_at":"2026-11-04T20:12:00+08:00"}
```

必填 9+2：`from/to/why/known/what_tried/do_not_redo/open_loops/next/created_at` 加 `handoff_id`、`schema_version`。

运行时行为（不是建议）：
- 结构字段 `handoff_id/from/to/created_at/schema_version` 由运行时从命令与时钟写入，不接受模型值。
- 内容字段缺失、空、类型错 → 默认 **strict**：不写文件、不换导师、退出码 3，列出缺项，记 `handoff_invalid{missing,raw_sha256}`。`--fill-missing` 从状态补齐（known←objective+最近 attempt，do_not_redo←最近 3 条 taught，open_loops←未关闭项，next←`next_step()`），标 `degraded:true` 并记 `handoff_degraded`。
- 容量上限：known/what_tried ≤5 条×120 字，`do_not_redo` 注入 ≤6 条（可存 12 条，超出归档且不再注入），open_loops ≤5 条，next ≤200 字；超限截断并记 `handoff_truncated`（上下文预算优先于完整性）。
- `to` 非法 → 退出码 2 并列出 5 个可选；`pause` 也写 from=to=self 的交接。
- `do_not_redo` 进去重表（归一化哈希）。新导师首个任务或类比命中 → 重新生成一次；仍命中记 `repeat_detected`，要求换表征。

## 6. 状态模型（`schema_version: 1`）

- `project.json`：goal、template、constraints、learner、schema_version（core 定义）。
- `state/studio.json`：`schema_version`、`updated_at`、`current_mentor`、`plan{plan_id, version, authority:"planner", week_goals[{id,text,due,status}], current_objective{id,text,activity_id,success_criteria,est_minutes}, steps[{n,mentor,activity_id,status,evidence[]}], minutes_per_week}`、`plan_changes[{id,by,op,week,step_id,detail,reason,status,at,before_hash,after_hash}]`、`mentors{id:{last_active,notes_path,open_loops[],turns}}`、`last_handoff_id`、`review_counter{since_review,every:4}`。
- `state/mentors/<id>.json`：`schema_version`、`mentor`、`taught[{item,activity_id,at,depth}]`、`avoid[]`、`conclusions[{text,basis_event,confidence}]`、`style`、`next_suggestion`、`turns`。**只有本人读**。
- `state/capability.json`（共享，运行时写）：`schema_version`、`nodes[{id,label,level,evidence[{event_id,source,help_level,artifact,at}],last_fail{misconception,at},review_due,decay_reason}]`、`self_reports[]`、`pending_exam{node_id,requested_by,status}`。
- `state/reviews.json`：`schema_version`、`reviews[{review_id,at,by,covered_nodes,retention{node:ok|weak|lost},resurfaced[],recommendation{mentor,week_goal},accepted_by_planner}]`。
- journal 追加种类：`plan_created`、`plan_change`、`handoff`、`authority_violation`、`context_manifest`、`exam`、`review`。

能力写入矩阵（运行时判定，不靠提示词）：

| 来源 | help_level | 可写最高等级 |
| --- | --- | --- |
| coach / concept 正确 | 0–1 | `observed`（练习证据） |
| coach / concept 正确 | ≥2 | 只记“受助完成”，不升级 |
| 学习者自述 | — | `self_report`，不升级 |
| examiner 迁移通过 | 0 | `verified`，单轮 ≤ +1 |
| examiner 复测失败 | 0 | 降级并写原因与时间 |

**examiner 独立性由运行时强制**：① 其上下文构造器完全不打开 `state/mentors/coach.json`，`context_manifest.sources` 可对账；② 该会话出现任何 `help_level>0` 的 update 即丢弃并记 `authority_violation`；③ 会话内一旦有 `help_level≥2` 的回合，verdict 强制降为 `insufficient_evidence`；④ `pass` 必须附 `exam{task_id,criteria[],verdict,evidence_event_ids[]}`，证据事件须在本会话内且 `help_level=0`；⑤ `verified` 只有 examiner 会话的运行时路径可写，coach 的 `mastery_delta` 一律落为 observed。

## 7. 计划权威与 plan-change

- 只有 planner 能令 `plan_change` 生效（`status:"apply"`、`by:"planner"`）。其他导师只能在其 `learn-update` 里提 `status:"proposed"`；proposed 期间**生效计划不变**，在 `plan`/`studio` 可见，planner 下一会话批准或拒绝，记 before/after 哈希。
- 合法 `op`：`add_step|replace_step|remove_step|reorder|replan_week|defer_step|none`；新增用 `new:<slug>`；每轮最多一条且必须带 `reason`。coach 不得删改 week_goals 文本、不得下调 success_criteria；越界 → `plan_change_rejected{reason}`。
- 非 planner 写 `status:"apply"`、`by` 与实际导师不符、update 里出现 `plan_patch`，或运行时发现 plan 哈希变化却无同期 `plan_change` → `plan_authority_violation`：回滚快照、记事件、`doctor` 报告。
- **静默改计划的定义**：`plan.version` 或 `steps` 哈希变化且无对应 `plan_change` 事件 → 由 `doctor --plan` 检出。

## 8. 记忆与上下文预算

共享事实（所有导师只读）：目标/约束、plan、capability、open loops、最近评审结论。私有笔记（仅本人可读）：讲过的类比、措辞偏好、未成熟猜想。
每回合上下文 = 目标摘要(≤300 字) + 当前 objective 与相邻 step + 相关能力节点(≤5) + 最新 handoff(≤1200 字) + 自身笔记 `taught` 末 5 条与 `avoid` + 最近 **8 条投影后**共享事件（kind/mentor/activity/help_level/结果，每条 ≤120 字）。硬上限 6000 字符，超限按“事件 → 笔记 → handoff 细节”顺序裁剪。永不读：完整 journal、他人私有笔记、历史会话全文、完整能力历史。每回合写 `context_manifest{mentor,chars,sources[],handoff_id}` 供验收对账。

避免重复教学：`do_not_redo` + 已做对的 activity_id + 最近 5 个用过的类比哈希，构成去重表；命中即换表征而非重讲。
避免矛盾安排：唯一排程者是 `next_step()`（阻塞 open loop → 待验证 exam → in_progress step → 下一 todo → `since_review≥4` → reviewer → planner），交接的 `next` 与之冲突时以运行时间为准并记 `handoff_next_overridden`。

## 9. 与 A / B / D 的实质区别

- **vs A**：没有全局先修地图；steps 只是当前计划内的顺序，planner 可重排，不存在“节点未解锁”。
- **vs B**：不以作品或 rubric 过关推进；artifact 可选，推进凭 examiner 对 objective 的判定。
- **vs D**：没有时间预算打分与到期队列；`--minutes` 只裁剪本回合活动大小，不重排队列。
- 可观察差异：`studio` 命令、`state/mentors/*.json` 五个文件、`handoff/` 目录、`context_manifest` 事件只在本方向存在；`switch` 在此处带契约校验与 plan 权限检查，在 A/B/D 只是薄封装。

## 10. 方向特有验收

- **C-S1 职责分离**。mock 让 coach 回一个含 `mastery_delta:1, exam_verdict:"pass"` 的块：断言 `capability` 的 level 未变、有 `authority_violation`；再在 examiner 会话 `say "给个提示"`，断言回复为拒绝、该回合 `help_level=0`、有 `hint_refused`。
- **C-S2 交接完整**。mock 只输出 `known` → `switch coach` 退出码 3、`handoff/` 无新文件、`handoff_invalid.missing` 列出其余 5 个内容字段；`switch coach --fill-missing` 成功且 `degraded:true`；`handoff --check` 校验全部历史交接，退出码 0。
- **C-S3 不重复劳动**。concept 讲完写入 `do_not_redo`（含类比哈希）→ `switch coach`；断言 coach 首回合 `context_manifest.sources` 含 `handoff/do_not_redo`；同一 activity_id 不出现两次；若模型复用被标记类比，出现 `repeat_detected` 且下一回合换表征。
- **C-S4 计划一致**。coach 的 update 带 `plan_change{op:"reorder", status:"apply", by:"coach"}` → `plan.version` 不变 + `plan_authority_violation`；改成 `status:"proposed"` 后出现 `plan_changes` 记录且 `plan` 输出可见，planner 下次上下文含其哈希。
- **C-S5 上下文有界**。连做 30 回合，断言每回合 `context_manifest.chars ≤ 6000`、`sources` 不含 `journal_full` 与他人笔记路径；第 30 回合字符数 ≤ 第 5 回合 ×1.3。
- **C-S6 五席位与点名**。`studio` 列出 5 位导师、各自最近活动、未决事项；`say "现在让 examiner 考我"` 后 `current_mentor=examiner` 且新交接 why 含“用户点名”；`switch 魔法师` 退出码 2 并列出可选。

所有断言取自 `status --json`、journal 事件、文件三者，不采信模型自述；统一用 `LEARNARK_LLM=mock` + `LEARNARK_MOCK_SCRIPT` 复现。

## 11. 风险与可观察信号

| 风险 | 失败方式 | 可观察信号 |
| --- | --- | --- |
| 交接形式化 | 字段齐全但无人使用，切换后行为与上一导师无关 | `handoff_next_overridden` 占比高；注入 do_not_redo 后 `repeat_detected` 仍 >0；同一 objective 下 concept 与 coach 首轮词汇重叠 >0.8 |
| 重复教学 | 换人重讲同一类比或同一题 | 同一 activity_id 被布置两次；类比哈希二次命中；学习者句中出现“讲过了” |
| 职责越界 | coach 判掌握、examiner 给提示、planner 被绕过 | `authority_violation`/`hint_refused` 计数；plan 哈希变化缺 `plan_change` |
| 上下文成本 | prompt 膨胀，切换首轮是稳态的 3 倍 | `context_manifest.chars` 曲线；`handoff_truncated` 频次；`usage.jsonl` 每回合 token |
| 点名跳步 | 随意点名导致考核口径漂移 | objective 未完成即出现 reviewer 改周目标；exam 判定与 success_criteria 不一致 |

## 12. 八轮实验计划

| 轮 | 可检验假设 | 主要变更 | 场景 | 主证据 | 退出条件 |
| --- | --- | --- | --- | --- | --- |
| 1 | 五席位 + 契约能跑通一次闭环 | 骨架、handoff 落盘 | S1（P1） | 会话、handoff、start 输出 | 有 plan、有交接、`start` 返回 0 |
| 2 | 运行时拦截足以保住能力证据 | `authority_violation`、examiner 无提示 | S2（P2） | 事件 + capability 前后 | 越界被拦且等级不变 |
| 3 | strict 交接 + 去重表能阻止重复 | 契约校验、去重表 | S3（P3，双进程） | handoff 文件、`context_manifest` | 缺字段被拒；重复率 0 |
| 4 | 计划权威可执行、克隆可恢复 | `plan_change`、git 同步 | S4（P3） | plan 事件、克隆运行 | coach 无法静默改；克隆后 plan 一致 |
| 5 | 6000 字符预算在 30 回合成立 | 上下文裁剪、事件投影 | S5（P3，20 分钟） | `context_manifest` 曲线 | ≤6000 且增长 ≤1.3 |
| 6 | 换主题只换标准不换架构 | email 模板、写作 rubric | S6（P4） | 会话、评分标准 | 无编程残留；考的是写作标准 |
| 7 | 修缺陷不引回归 | 滞留问题修复 | S7 定向复测 | 复测报告 | 阻塞清零、相邻流程通过 |
| 8 | 新体验者仅凭入口可完成 | 收敛 | S8 全新上下文 | 体验报告、比较矩阵 | 10 轮内完成闭环 |

每轮必须有一个可证伪假设、一次真实独立体验、一次独立复测；只跑测试或只改文案不计轮次。
