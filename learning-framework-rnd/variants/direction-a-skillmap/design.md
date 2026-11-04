# SkillMap 能力地图路径型 — 产品设计 v0.1.0

> 面向教学设计师与实现工程师：本文定义必须实现的行为。命令面、状态目录、`learncore` 用法见 `shared/spec-core.md`，本文只增加方向逻辑。

## 1. 一句话主张 / 目标学习者 / 非目标

**一句话主张**：把「学 Agent 开发」做成一张 12 节点、带先修关系的能力地图；首次进入用 5 个探测问题定位，之后每次只在「先修就绪 + 未掌握 + 复习到期」的节点上按讲解→操练→应用→检查四段推进，等级只由运行时证据规则决定，不由导师话术决定。

**目标学习者**：接触过 Python 与 HTTP API、用 AI 攒过 RAG，但说不清自己哪会哪不会的人；怕漏基础、中断后想立刻定位的人；每周 10–20 小时、单次可能只有 20 分钟。对应画像 P1、P2、P3。

**非目标**：不做零基础 Python 系统课（A1 只做诊断与缺口提示）；不做自由聊天（每条导师输出必须挂在某节点的某阶段活动上）；不做账号、云、移动端、后台定时唤醒；不做排行榜与证书；一个项目同时只有一个主题。

## 2. 核心假设与替代解释

| ID | 假设 | 可检验观察 | 判为「假设错了」与替代解释 |
| --- | --- | --- | --- |
| H1 | 显式地图 + 可解释 `next` 减少迷路与重复 | S1/S5 不再追问「我该学什么」；S3 第二段首个活动 = 中断前未完成阶段 | S1 12 轮内无真实尝试，或 S5 两次短会话重复同一活动 → 不是地图无用，是**阶段粒度**不对，先改切分，不删地图 |
| H2 | 诊断能改变路径 | 自述同为「懂 Agent」的 P1、P2 首个 `activity_id` 不同，前 3 个 session_goal 覆盖节点差 ≥2 | 首活动相同或差异仅在措辞 → 诊断测的是记忆不是行为，换行为题（找 bug、判错误），不加题 |
| H3 | 只有独立通过才升级 | 注入 `help_level=2` 且正确的尝试，等级不变 | 学习者因门槛 3 轮无进展（`stuck`）→ 不是门槛过严，是缺中间档活动，补 drill 变式，不降门槛 |
| H4 | 先修门控防「悬空掌握」 | 先修未达 **L1（可用门槛）** 的后继节点不出现在 `next`，并给出排除原因；L1 只代表可以开始，要声明先修「掌握」仍需 L2 证据 | 被手动改 map 绕过 → 记为设计外使用，`doctor` 报警但不支持 |
| H5 | 启动开销可承受 | 首次进入 ≤4 次往返、≤8 分钟；首个真实尝试在第 5 轮内 | 诊断 >8 分钟或跳过率 >1/3 → 压到 3 题并允许「我不知道」 |

## 3. 完整学习流程

**首次进入**：`init --goal "Agent 开发" --template agent-dev` 建项目与 `.learnark/`、生成 `AGENTS.md`；`start` 读到 `diagnosis.status=pending` 自动切 navigator。导师 3 句开场（复述目标、一句话说明 12 节点地图、诊断 5 题约 6 分钟可跳过）。学习者只需回「开始」或「我只有 20 分钟」。

**诊断**：navigator 问 5 题——Q1 用自己话描述 tool call 的一来一回（B1）；Q2 读 4 行伪代码（`i += 0`）说明为什么停不下来（C2）；Q3 RAG 与会话记忆的区别（D2）；Q4 超时的 HTTP 调用怎么处理（A2）；Q5 给一个小任务设计最小评测（E1）。题面的唯一权威是运行时逐题给出的原文（同时出现在 `mentors/navigator.md` 与控制台页脚），导师正文必须照抄，不得另写代码或换题。每题写 `diagnosis_probe`，「不知道/跳过」合法记为 `unknown`。**评级通过机器块 `probe{node, level, reason}` 进入地图**：只接受 level 0/1 与模板声明的锚点，正文里的评价不改变状态；**只允许置 L0 或 L1**。结束写 `diagnosis_done`，重算 status，首次输出 `next`。

**探针游标（v0.2.2）**：游标跟着**学习者对当前题的作答**走，不跟导师的正文走。导师只是追问/举例、还没判定对错时，机器块 `probe` 与 `attempt.correct` 都写 null → 运行时记 `probe_deferred`，**题号不变、页脚重问同一题**，绝不把追问的答案算到下一题。`probe` claim 的 `node` 必须等于**当前正在问的锚点**，否则记 `probe_claim_rejected` 且不推进游标。任何 `done` 的探针都必须带明确判断（`correct` 为 true/false），不允许 `correct=null` 却标 `done`。

**诊断定位（placement）**：`diagnosis_done` 后，若某个被探针置为 L1 的锚点节点，其**全部先修也已 ≥L1（可用门槛）**，则直接把它设为 `current_node`、`stage=apply`（跳过 explain/drill，因为 L1 已等价于 explain 通过），写 `placement_applied{node, level, probe, reason}`，并在 `next` 的第 2 条理由里给出定位原因。多个节点同时满足时取簇序号最大、再按 id 排序的那个（确定性）；**有任一先修停在 L0 的节点不参与定位**。诊断本身仍然不得置 L2 以上。

**节点推进**：`next`/`start` 打印选中节点、3 条理由、预计时长；运行时按阶段自动切导师；学习者作答或交产物；每轮 `say` 落会话与事件。

**预算（v0.2.4，端到端）**：本次 `--minutes` 是整场预算，不是单个任务的上限。会话开始时记账 `plan.diagnosis_minutes`（<30 分钟只排 2 个探针 ≈ 3 分钟，否则按 1.5 分钟/题），活动时长 = `min(基准 20/45, budget - 诊断 - 收尾 2)`，任务卡/mentor context/`status`/`next`/handoff 都用这一套并显示算式（“诊断 3 + 活动 15 + 收尾 2”）。10 分钟会话只剩一个 5 分钟的小活动；不允许“诊断 6 分钟 + 20 分钟讲解”这种超预算组合。余额不足时 `diagnosis_deferred` 会写明哪些题延后。

**对话级提前结束诊断（v0.2.4）**：导师正文说“诊断到此结束/剩下几题跳过”、学习者说“跳过诊断”、或机器块写 `"diagnosis": "skip"` 时，运行时立即结束诊断：未答探针标 `deferred`（`diagnosis_skipped`），已答对的等级与已算出的定位保留，`diagnosis.end_reason` 记录来源；不会再显示“下一步 Q3”。只有学习者主动 `diagnose` 才重新出题。

**写作产物（v0.2.4）**：email 模板的 apply 接受 `.md`/`.txt`；学习者正文就是产物，运行时自动存成 `artifacts/w*-apply-<时间>.md` 并写 `artifact_autosaved`，不再要求额外一轮补文件。任务卡会提前写明产物路径与接受格式。

**检查**：examiner 出 1 道独立应用题 + 1 道未见过措辞的迁移题，零提示，`help_level` 强制 0。通过 → 等级 +1（单轮最多 +1）并排复习；不通过 → 写 `misconception`，回 apply 或 drill。

**复习**：`review` 列出 `due ≤ today` 的节点，每会话最多 2 个（短时 1 个），每节点 1 道 ≤5 分钟 check；通过 → 间隔进一档，失败 → 降 1 级、间隔退 2 档、`lapses+1`。

**中断恢复**：任意时刻 `pause` 写 handoff（停在哪个节点哪个阶段第几次提交、试过什么、哪里不稳、下一步、未决问题）并 sync。新进程 `start` 只读项目文件，输出形如「上次停在 C2 的 apply，第 1 次提交未通过；今天续做 apply 变式 2，约 15 分钟」。

## 4. 能力地图

12 节点 5 簇（`←` 表示先修）：A1 Python 数据结构与异常`←∅`；A2 HTTP/API 与 JSON 边界`←A1`；B1 消息结构与角色`←A2`；B2 结构化输出与解析`←B1`；B3 超时/限流/重试`←B2`；C1 工具 schema`←B1`；C2 调用往返`←C1,B2`；C3 Agent 循环与终止`←C2,B3`；C4 错误处理与幂等`←C3`；D1 会话记忆与上下文预算`←C3`；D2 RAG 边界（何时不该检索）`←D1,C2`；E1 评测集与回归`←C3,C4`。

**先修门槛（v0.1.1 起）**：**可用门槛** `prereq_gate=1` —— 先修全部 ≥L1 就可以出现在 `next`，因为 L1 只表示「能复述」，不足以支撑后继节点的独立应用判定；**掌握门槛** `mastery_gate=2` —— 只有 L2 才代表该先修已被独立应用，用于证据陈述与展示，不用来隐藏任务。`gate_override` 只对「仍有先修停在 L0」的节点有意义，且等级上限锁 L1。`map.json` 的 `gate` 字段记录可用门槛（1），`mastery_gate` 记录 2。

**等级 0–3**：L0 未接触（无事件或只有自述）；L1 接触（explain 复述通过 + ≥1 次 `help_level≥2` 的完成，能说不能做）；L2 独立应用（apply 在 `help_level≤1` 下通过含 1 道变式，且有 `artifacts/` 产物或可复现命令）；L3 独立迁移（check 迁移题 `help_level=0` 通过，且 ≥7 天后复测再通过一次）。

**证据要求**：每条升级对应一条 `evidence{event_id, kind, activity_id, help_level, correct, source, artifact, at}`；`source=verified` 必须有产物路径与 `file_sha256` 校验，删除产物 → `doctor` 报 `artifact_missing`，等级退回 L1。

## 5. 四段活动

| 阶段 | 进入条件 | 退出（通过） | 不通过 / 超时 |
| --- | --- | --- | --- |
| explain | 先修全部 ≥L1（可用门槛）且本节点 ≤L1（或复习降级后） | 用自己的话复述 ≥2 个要点 + 答对 1 个「为什么」 | 换类比重讲 1 次（≤4 轮/8 分钟）；仍不行 → 判为先修缺口，退回最低未达标先修节点并写 `prereq_gap` |
| drill | explain 通过 | 连续 2 题同类操练在 `help_level≤1` 下正确 | 拆成两步降难度，最多 2 次；10 分钟超时写 `stage_timeout` 并保存断点 |
| apply | drill 通过 | 提交 1 个可运行/可检查产物，`help_level≤1`，并通过 1 道变式 | `help_level≥2` → 记 `assisted_completion` 并回 drill，最多 2 次；产物不可运行 → 最小定位提示后重试 1 次 |
| check | apply 通过 | 独立题 + 迁移题均由 examiner 判、`help_level=0`、两题都对 | 写 `misconception` 按错因回 apply/drill；同一错因连续 2 次 → `status=decayed` 并插 explain |

跨会话续段允许：一次 20 分钟会话只承诺推进**一个阶段**，不承诺一个节点。

## 6. 导师分工与切换规则

| 导师 | 职责 | 出现时机 | 禁止 |
| --- | --- | --- | --- |
| navigator | 诊断、定位、解释为什么学这个节点、复习与切换安排 | 首次进入、阶段切换、复习 | 不讲解细节、不判分 |
| concept | 讲解、类比、检查理解 | explain | 不给练习答案、不判等级 |
| coach | 操练与应用辅导、分级提示、看产物 | drill / apply | 不擅自给最终答案（`help_level=3` 仅在用户明确要求时，且该次记为受助完成） |
| examiner | 出独立题与迁移题、判定、不给提示 | check | `help_level` 恒 0 |

**切换规则**：运行时按阶段自动切——explain→concept、drill/apply→coach、check→examiner、交接与复习→navigator。每次切换写 `handoff`（from、to、reason、unresolved、context_digest）并进入下一导师上下文。用户 `switch` 只能切到当前阶段允许的角色集；切到不允许的（如 check 阶段切 coach）→ 退出码 2，提示「检查阶段不接受提示」。examiner 返回 `help_level≥1` → 拒绝应用该轮、记 `examiner_help_violation`、作废重出题。

**runtime_next（v0.2.2）**：每次导师上下文的开头注入 `runtime_next{status,node,stage,activity_id,mentor,source,reason}`，它是运行时**唯一权威**的下一步。导师正文不得宣布与它不同的起点/阶段/节点，也不得自行安排额外任务；`start` 的任务卡、`status` 的“当前/下一步”和 `next` 都读同一来源，三者必须一致。

**导师发现与按需切换（v0.2.3）**：`status` 与 `start` 任务卡必须列出当前阶段可切换的导师及一句职责说明；`concept` 在任何学习阶段都可按需切换（写 `on_demand_switch`，不改变阶段），拒绝时退出码 2 并按名字列出全部可选项与理由。`Context.next_mentor()` 是“下一位导师”的唯一权威：诊断→navigator；有当前节点→当前阶段导师（含 override）；否则取 `next` 选中项的导师。`status`、`handoff.to`、`plan.next_mentor`、下一次 `start` 全部读它。

## 7. 状态模型与下一步算法

`project.json`（core）：`schema_version, slug, goal, template, minutes_per_week, learner{name, self_report[], diagnosis{status:pending|done|skipped, probes[], completed_at}}, constraints, created_at`。

`state/map.json`：`schema_version=1, nodes[{id,title,cluster,prereqs[],level:0-3,level_source,gate_override,evidence[],review{interval_index:0-4,due,lapses,last_review_at},status,misconceptions[],updated_at}], updated_at`。

`state/plan.json`：`schema_version=1, current_node, stage, stage_started_at, session_id, minutes_budget, session_goal, open_questions[], placement{node,level,probe,stage,prereqs,reason}|null, last_decision{computed_at, rule_version:"next-v1", candidates[], excluded[], reasons[]}`。

`state/memory.json`：`schema_version=1, preferences{preferred_minutes, prefers_examples}, traits_observed[{key,count,node,last_at}], help_profile{avg_help_level, independent_rate, trend}, updated_at`。

`status` 为派生字段不单独存：level=3→`mastered`；`due≤today` 且 level≥1→`review_due`；`lapses≥2`→`decayed`；先修未全 ≥L1（可用门槛）→`locked`；等于 current_node→`in_progress`；否则 `available`。读时重算，缓存不一致写 `map_status_drift`。

**next-v1**：候选 = 先修全部 ≥L1（可用门槛）且 level<3 的节点；`gate_override` 可进入但等级上限锁 L1；诊断定位（placement）写入 `plan.placement`，选中它时第 2 条理由改用定位原因。排序键（升序）：`(复习到期 0/1, 当前节点阶段未完成 0/1, level, cluster_index, node_id)`。输出必须含选中节点 + 3 条来自上述键的可读理由 + 被排除的 ≥2 个节点及原因（如「C3：先修 C2 为 L0，低于门槛 L1」）+ 预计时长；同一状态两次调用字节级一致。

**同步与恢复（v0.2.3）**：`status`/`status --json` 暴露 `sync{state,ahead,behind,unmerged,diverged}`；`diverged`（ahead>0 且 behind>0）或存在未合并文件即视为失败状态，`doctor` 同样失败。`sync` 先 fetch 判断分叉，**不得盲目 rebase 或反复堆提交**；`sync --recover` 走 core 的 `GitSync.recover()`：按事件 id 合并 journal、重建去重索引、保留本地状态快照，非 journal 冲突中止并输出真实文件列表；任何情况下都不 force push。冲突/恢复失败退出码 3。

## 8. 记忆设计

**三级来源**：`self_report` 只存 `learner.self_report[]`，最多生成「待验证假设」，永不影响等级；`observed` 是 journal 中的 attempt、复述与 help_level；`verified` 是 apply/check 通过 + 产物路径 + 至少一次 ≥7 天后的复测通过。自述不得自动升级。

**help_level 规则**：0 无提示；1 单句方向提示；2 分步拆解或伪代码；3 给答案或代写。只有 `correct=true 且 help_level≤1` 计入升级；`≥2` 一律记 `assisted_completion`，最多推进到 L1；check 阶段强制 0。

**受助余波（v0.2.2）**：若同一节点/会话的**上一轮**导师回合 `help_level≥2`，那么紧接着这一轮即使 `help_level≤1` 且答对，也只算「受助后的确认」：写 `assisted_carryover`，升级理由记为 `after_assisted`、`level_up.assisted=true`，等级最多到 L1；apply/check 这一轮不能通过（避免「刚给完整代码，下一轮就独立掌握」）。`status` 的 `help` 摘要必须显示 `last_help_level`、独立通过次数、受助完成次数与最近一次等级变化是否受助；帮助等级不得只藏在事件里。

**等级增减**：L0→L1 需 explain 复述通过；L1→L2 需 apply(≤1) + 变式 + 产物；L2→L3 需 check(0) + 7 天后复测。单轮最多 +1，超出部分丢弃并写 `level_cap`。降级只发生在 review 失败或 `doctor` 发现产物缺失，必须记 `reason`、`at`、`lapses`。

**复习间隔** `[1,3,7,16,35]` 天：`interval_index` 0–4，通过 → +1（封顶 4），失败 → −2（下限 0），`due = today + interval[index]`。每会话最多 2 个复习节点，20 分钟会话 1 个。幂等键 `sha256(session_id|activity_id|answer)`，重复提交不重复加分。

## 9. 与方向 B/C/D 的实质区别

| 维度 | A SkillMap | B Forge | C Atelier | D Tempo |
| --- | --- | --- | --- | --- |
| 主数据结构 | `map.json`：节点 + prereqs + level + evidence | 里程碑 + rubric | 五导师会话 + handoff 契约 | 调度打分 + 到期队列 |
| 首次进入 | 5 题诊断后定位 | 选第一个可交付作品 | 五导师开场交接 | 询问时间预算 |
| 下一步 | 先修门控 + 5 键排序 | rubric 缺口 | 计划内由当前导师挑 | 打分函数 |
| 等级 | 0–3，只由 apply/check 独立通过改变 | rubric 分 | 会话进度 | 熟练度分 |
| 特有事件 | `node_unlocked` `level_up` `prereq_gap` `review_due` | `milestone_passed` `rubric_gap` | `mentor_switch` `handoff` | `budget_set` `due_skip` |

**为什么不是文案差异**：A 的 `next` 会因 `prereqs` 字段**拒绝**节点，B/C/D 的数据结构里没有 `prereqs`；A 的 `review` 是节点级 check 且受先修与等级影响，D 的到期是活动级打分；A-S1 是可断言的 gate 测试，B/C/D 写不出同一断言。删掉 `map.json`，A 无法启动，B/C/D 不受影响。

## 10. 方向特有验收项

| ID | 可观察行为 | 复现方法 | 证据 |
| --- | --- | --- | --- |
| A-S1 先修门控 | 先修未达 **L1 可用门槛** 的后继节点被 `next` 排除并给出原因；先修到 L1 即可开始，但升级仍按证据 | 新项目 `next --json` 的 `excluded` 必含「C3：先修 C2 为 L0，低于门槛 L1」；把 C2/B3 置 L1 后 C3 进入候选；任一先修仍为 L0 的节点（如 A1 L0 时的 A2）仍被排除；`gate_override` 节点两次独立通过仍停 L1 | `tests/run_tests.py::test_prereq_gate_excludes_locked_nodes`、`test_gate_l1_still_blocks_l0_prereq` |
| A-S2 诊断生效 | 不同诊断 → 首个活动不同；评级必须经 `probe` 机器块进入地图 | 同 template 建两项目：全对档案（5 题都判 L1）首个活动 `B1-apply`，B1/A2 等锚点为 L1 并写 `placement_applied{node:B1,level:1,probe:Q1}`；偏弱档案（只有 Q4→A2 答对）首个活动 `A1-explain`，因为 A2 的先修 A1 仍是 L0；只写正文不写 `probe` 时地图不变 | `tests/run_tests.py::test_placement_all_correct_profile`、`test_placement_mostly_wrong_profile`、`test_probe_claim_validation` |
| A-S3 证据门槛 | 受助完成不升级 | 注入 `help_level=2, correct=true` → 无 `level_up`、有 `assisted_completion`；注入 `help_level=1` → 恰好 1 条 `level_up`；同答案重复提交 → 无第二条 `level_up` | `experiments/round-2/` |
| A-S4 复习调度 | 未到期不打扰 | `LEARNARK_NOW` 设在 due 前，`review` 返回 0 个到期并给最近到期日，退出码 0；设到 due 当天 → 返回该节点并进 check | `experiments/round-8/` |
| A-S5 阶段门控 | 跳过阶段被拒 | explain 未退出时提交 apply 产物 → 退出码 2，输出当前阶段与 2 个可做动作，且不写 `attempt` | `experiments/round-1/` |
| A-S6 解释确定性 | 同一状态同一输出 | 连续两次 `next --json` 字节一致；`reasons` 引用的 level/due 与 `map --json` 完全一致 | `experiments/round-8/` |

## 11. 风险、代价与失败方式

| 风险 | 代价/表现 | 如何被观察到 |
| --- | --- | --- |
| 地图过细 | 12 节点 × 4 段 = 48 个活动，20 分钟只够一段 | `stage_timeout` 占会话 >30%；S5 未完成一个阶段 |
| 诊断偏松/偏难 | 早期等级虚高后大面积掉级；或全部从 A1 重学 | 前 3 个会话内 `level_down ≥2`；跳过诊断率 >1/3 |
| 判定被话术带偏 | 导师「安慰性通过」 | 同一答案 3 种措辞重复提交而 `correct` 变化 → 改用运行时答案键与产物离线执行 |
| 先修卡死 | P1 长期停在 A1 | 同节点连续 3 轮 level 不变 → `stuck`；对策拆节点，不降门槛 |
| 复习挤压新学 | 会话全用于复习 | 到期 >2 时会话中新节点推进数为 0 的占比 |
| 前期开销 | 首次进入有效学习时间降约 30% | 实测诊断 + 地图解释耗时与 S1 往返数 |

## 12. 8 轮实验计划

| 轮 | 验证假设 | 实现变更 | 场景/画像 | 预期证据 | 收敛判据 |
| --- | --- | --- | --- | --- | --- |
| 1 | H1 前半 + H5 | v0.1 闭环：`init/start/say/status/pause` + 12 节点地图 + 5 题诊断 + 可解释 `next` | S1 / P1 | S1 报告、journal、首个活动 | 12 轮内完成诊断 + 1 次真实尝试 + 保存，无阻塞 |
| 2 | H3 + 错误反馈 | `help_level` 校验、`assisted_completion`、examiner 零提示、错因入库 | S2 / P2 | help_level 事件、等级变化、错因记录 | 受助通过 0 次升级（≥2 例）、独立通过 1 次升级；P2 混淆进 map |
| 3 | H2 + 多导师 | 四导师自动切换、handoff 契约、恢复输出 | S3 / P3，加 P1、P2 诊断档案 | handoff 文件、切换前后 map 一致、首活动对比 | 切换后 0 条冲突安排；P1/P2 首活动不同且节点差 ≥2 |
| 4 | R4/R5 恢复与同步 | `sync` 三态、干净克隆定位、`doctor` 自检 | S4 / P3 | 克隆运行记录、`git log`、三态输出 | 克隆后 `start` 定位到同节点同阶段；三态与 git 实际一致 |
| 5 | H1 后半 + 短时 | `--minutes` 裁到「一次一阶段」、续段提示 | S5 / P3，加 P1 | S5 报告、阶段完成率 | 20 分钟完成 1 个阶段且 `pause` 给出明确下一步 |
| 6 | 跨主题不写死 | email 模板换成 6 节点写作地图 + 写作 rubric，沿用同一门槛 | S6 / P4 | 邮件项目 map、会话记录 | 写作节点证据不含代码产物；诊断题全为写作题 |
| 7 | 滞留问题 | 按 `issues.md` 修阻塞与重要项，不改阈值 | S7 定向复测 | 修复记录 + 独立复测 | 阻塞全关闭且有独立复测；启动/保存/恢复回归通过 |
| 8 | H4 + 复习全链 | `review` 队列、`[1,3,7,16,35]`、降级与 `decayed`、`stuck` 检测 | S8 新体验者 + S4/S5 回归 | S8 报告、A-S1–A-S6 结果 | S8 10 轮内完成闭环；A-S1–S6 全绿或有理由的不适用 |

全局收敛规则：任一假设被证伪即按第 2 节替代解释改实现，不调低判据；8 轮后仍失败者写入 `known_limits`。
