# Tempo · 动态调度复习型 — 产品设计 v0.1.0

## 1. 一句话主张 / 学习者 / 非目标

学习者只说一句“今天只有二十分钟”，系统在 1 次交互内给出**做什么、为什么是它、做完记住了什么**。调度由确定性打分器负责，导师只负责教。

目标学习者：P3/Mia 型——每周 10–20 小时但散落在 10–25 分钟碎片里，常中断返学，最怕“每次进入都要先规划”。非目标：需要连续 2 小时作品冲刺的人（用 Forge）、要课程目录与证书的人、要后台推送与手机提醒的人（本方向不做）。

## 2. 核心假设与替代解释

H1：把每次进入的决策压到 ≤1 次（只给分钟数），并按到期优先调度，能同时提高完成率与保持率。

可测指标：会话完成率（完成活动数/开始数）≥0.80；延迟回忆通过率（`due_at+7±1` 天首次复测中 correct 且 `help_level≤1`）≥0.70；每次进入的决策数 ≤1（只输入分钟数）；单次会话平均命令数 ≤3。

替代解释与排除法：
- **新奇效应**：观测量第 1、3、6 周，第 3 周回落 >25% 视为不成立。
- **自选择**：P1（基础弱）/P2（能复述不会做）分桶报告，不合并成一个平均数。
- **活动质量而非调度**：消融组 D-ablate 用同一活动池、固定文件顺序调度；若两组完成率差 <10 个百分点，则“调度”不是原因。
- **碎片损害深度**：单独统计迁移题与块产物评分，不用坚持率掩盖深度缺失。

## 3. 完整流程

1. **一句话开始**：`python learn.py start` 等价 `--minutes 20`；也可 `start "今天只有二十分钟"` 或先 `say "只有一刻钟"`。解析纯正则、不调用 LLM：`20分钟/二十分钟/20min`→20；`一刻钟`→15；`半小时`→30；`一小时`→45（上限，回显“按 45 分钟安排”）；`一会儿/几分钟`→10；无法解析→20 并给一句提示。允许区间 5–45，越界夹取并回显，写入 `today.minutes_budget`。
2. **调度并解释**：打印 top3 候选表（活动、技能、时长、总分、主因子）与一句理由：“3 张卡已过期 2 天，先用 5 分钟清到期；剩余预算够 15 分钟”。
3. **5–20 分钟微活动**：单活动硬上限 20 分钟；单次会话最多 2 个活动（到期组可 3 张 5 分钟卡）；每活动推荐 3–6 轮师生往返。
4. **记录证据**：结束即写 `activity_completed` 事件（activity_id、skill、correct、help_level、evidence_level、duration_min、dedupe_key=`session:activity`），再更新 skills/cards。
5. **下一项或结束**：剩余预算 ≥ 下一活动最短时长且未达 2 项上限 → 给“再来一个 8 分钟小测 / 现在结束”二选一；否则进入收尾，打印下次到期日与一句下一步。
6. **到期提醒**：无后台服务。`start/status/due/plan` 显示“到期 3 张，最久过期 2 天”，重开即提醒；`plan` 只给 ≤3 项，不显示欠账总数以免焦虑。

## 4. 活动类型库

| id | 导师 | 时长 | 证据 | 可升级 | 说明 |
| --- | --- | --- | --- | --- | --- |
| recall_card | trainer | 5–6 | observed | 可（help≤1） | 记忆卡自测 1–3 张 |
| concept_block | coach | 10–12 | observed | 可（复述命中 ≥2/3 要点） | 讲解 + 回述 |
| explain_back | coach | 8–10 | observed→verified | 可（rubric ≥3/4 项） | 费曼式讲解，需评分表 |
| code_kata | trainer | 12–18 | verified | 可（产物 + 复测） | 一段可运行代码 |
| quiz | examiner | 6–8 | verified | 可（零提示） | 3 题小测 |
| transfer_task | examiner | 15–20 | verified | 可（跨场景） | 新情境迁移 |

共同规则：只有 `correct=true` 且 `help_level ≤1` 才能 +1 级；同一技能每天最多 +1 级；讲师讲解本身不计证据。

## 5. 调度打分函数

**候选来源**（去重按 skill，上限 40）：到期卡 `due_cards`（含逾期）、到期技能复测 `due_skills`、本周项目块下一步 `block_step`、薄弱与未接触技能 `weak_new`。

**硬过滤**：① 活动时长 ≤ 剩余预算；② 今天已做过的活动模板不重复；③ 同一技能当天已练过则排除（用户显式 `review` 除外）；④ `leech` 卡不出现在 <10 分钟预算中。

**两级选择（先组后分）**，保证“到期不被新内容挤掉”：
- Tier 1 到期组：`due_at ≤ today`，按逾期天数降序，单次最多 3 张；
- Tier 2 块步骤组：本周项目块的下一步；
- Tier 3 其余：薄弱、新内容。
仅在当前 tier 过滤后候选为空时进入下一 tier，理由中明写“到期组已清空”。

**组内打分**（各项归一化到 [0,1]，权重和 = 1.00）：
`score = 0.40·U + 0.20·W + 0.15·P + 0.20·F + 0.05·N − 0.35·R`
- U 到期紧急度 = `0.25 + 0.75·min(1, overdue_days/3)`（当天到期 0.25，逾期 3 天 = 1.0）；非到期恒 0。
- W 薄弱度 = `min(1, (3−level)/3 + 0.2·近7天该技能错误次数)`；level 0 得 1.0。
- P 计划推进 = 1.0（块下一步）/ 0.5（块内其他步骤）/ 0。
- F 时长匹配 = `min(活动时长, 剩余预算) / max(活动时长, 剩余预算)`；5 分钟活动配 20 分钟预算 = 0.25。
- N 新鲜度 = 1（从未练过）否则 0。
- R 最近重复惩罚 = 1.0（上次会话同技能）/ 0.5（今天同模板）/ 0。

同分按 `(due_at, activity_id)` 升序，输入只有 state + minutes + clock，无随机、无 LLM、无 I/O 依赖外部时间 → 可单元测试、可复现。**可解释性**：top3 每行标出权重最大的因子；未入选者给出拒绝理由（“20 分钟 kata 超出剩余 5 分钟”“今天已做该模板”）。

## 6. SRS 设计

- 两级：**技能**是能力单元（如 `tool_call_loop`，level 0–3），**卡**是最小可检索单元（记忆卡/误解卡），一技能 1–5 张卡。`skills` 输出平表：id、level、`due_at`、`lapses`、错误标签——**没有** `prereq`/层级列。
- 间隔阶梯 `[1,2,4,8,15,30,60]` 天：成功 → `step+1`，`interval = clamp(round(阶梯[step]×ease),1,90)`；`ease` 默认 1.00，成功 +0.15、失败 −0.20，夹取 [0.85,1.60]。
- **lapse**：答错（`correct=false`）→ `step = max(0, step−2)`、`ease−0.20`、`lapses+1`、`due_at = 次日`；连续 2 次 lapse 标 `leech` 且该技能 level −1，要求改写卡片正反面，且只在 ≥10 分钟预算出现。
- **到期队列**：`due` 按 `overdue_days` 降序输出技能与卡；每会话到期卡上限 3、积压上限 12，超出时最旧卡折叠 +3 天并记 `backlog_folded`；每周卡量上限 = `clamp(round(minutes_per_week/45), 5, 40)`（20 小时/周 ≈ 27 张，10 小时/周 ≈ 13 张），超出则新卡排队。
- **模拟时间测试**：一律 `learncore.clock` + `LEARNARK_NOW`，逐日推进 0/1/2/3/7/15/30 天断言 `due_at` 与 `step`；测试禁止手写固定日期充当 `due_at`（只能经 env 注入），事件自动带 `simulated:true`，报告标注“模拟时间，仅证明调度逻辑”。

## 7. 导师分工与调度器的关系

coach（讲解、回述、kata 辅导，给最小提示）、trainer（卡与 kata，高节奏少解释，默认零提示）、examiner（quiz、transfer，`help_level` 必须为 0）。`start` 按活动绑定导师并打印；`switch` 仅在活动结束后允许，写 handoff。

**导师不能改调度**：机器块里的 `next` 只作为 `mentor_suggestion` 落入 journal，不参与 tier 与组内排序；`mastery_delta` 上限 +1 且受 `help_level` 约束。出现“建议 ≠ 已调度”时记 `mentor_schedule_conflict` 并按调度执行；examiner 回复含提示则记 `examiner_hint_leak`，该次证据降为 observed。

## 8. 状态模型（schema_version = 1）

- `state/schedule.json`：`{schema_version, minutes_default:20, limits:{min_activity:5, max_items_per_session:2, due_cards_per_session:3, backlog_cap:12}, today:{date, minutes_budget, minutes_left, items:[{activity_id, skill, started_at, done}]}, last_activity:{id, skill, at}, recent:[{skill, activity_id, at}], updated_at}`
- `state/skills.json`：`{schema_version, skills:[{id, title, tags[], level, level_reason, evidence_refs[], last_review_at, due_at, stability_days, lapses, wrong_tags[], block_id}]}`
- `state/cards.json`：`{schema_version, cards:[{id, skill, kind:"recall"|"misconception", front, back, source_event, step, interval_days, ease, due_at, last_review_at, lapses, leech}]}`
- `state/blocks.json`：`{schema_version, blocks:[{id, week, goal, deliverable, artifact_path, steps:[{skill, activity_type, done, evidence_ref}]}]}`

**“下周项目块”补深度**：每周 1 个 30–60 分钟块（设计 15 + 实现 30 + 讲解 10），拆成 3 段跨 2–3 次会话；Tier 2 保证每周至少 2 次会话落在块内步骤；产物写 `artifacts/`。硬规则：**技能 L3 只能由“块产物 + ≥7 天延迟复测”共同授予，纯卡练习最高 L2**。

**恢复与并发**：状态读走 `Document`（CAS）+ journal 重建；干净克隆后 `start` 仅凭 `.learnark/` 恢复同日预算、`recent` 与 due 队列；写操作一律带幂等键，重复执行不翻倍；同步只提交项目白名单，报告 written/committed/pushed 三态。

## 9. 记忆设计

- 证据三级 `self_report < observed < verified`；自述只写档案，永不计入升级。
- 升级：`correct` 且 `help_level ≤1` → +1，每活动幂等键去重、每技能每天上限 +1；`help_level ≥2` 记“受助完成”，只算接触，该卡 `step` 回退 1（不计 lapse、不计错误）。
- 遗忘与降级：`due_at` 过期 > 2×interval 且未复习 → level −1，记 `decayed`（reason=`overdue`，带天数）；30 天无 verified 证据 → verified 降 observed；连续 2 次错误 → level −1 并自动生成误解卡。
- 所有等级变更必须带事件 ID + 产物路径，`status` 可回溯。

## 10. 与 A/B/C 的实质区别

- **对 A（SkillMap）**：A 的下一步 = 能力地图上“未掌握 + 先修就绪”的最低层节点，有显式先修边与路径图；D **没有地图**——`skills` 是平表，只有 level/due/wrong_tags，无先修边、无层级推进，下一步 = 组优先 + 打分的 top1，`plan` 只有 ≤3 项分数排序且输出无依赖字段。可观察：D 中同一技能会反复回流做延迟复测，A 中节点掌握即前进；D 的 `skills` 无 `prereq` 字段。
- **对 B（Forge）**：B 无课程表，由里程碑与 rubric 缺口驱动，无作品不通过；D 有队列无里程碑，产物只作证据，不设关卡。
- **对 C（Atelier）**：C 以五导师与 handoff 契约为骨架，planner 可改计划；D 只有 3 个活动绑定导师、交接较轻，且**调度器拒绝任何导师修改**（C 的 planner 可改）。
- 共同底线不删：多导师、持久记忆、恢复、Git 三态、跨主题（email 模板换成写作微技能与句式卡）。

## 11. 方向特有验收项

| ID | 断言 | 测试方法 |
| --- | --- | --- |
| D-S1 预算生效 | 不同 `--minutes` 选出不同活动 | fixture 6 候选（到期 5/15 分钟各一、块步骤 12 分钟、新内容 5/10/20 分钟）：`start --minutes 5` 选 recall_card，`--minutes 20` 选 15 分钟 kata；连跑 3 次输出逐字节一致 |
| D-S2 到期优先 | 到期组不被计划/新内容挤掉 | 1 张逾期 3 天卡（level 1）+ 1 个块步骤（P=1.0，tier2）+ 1 个 level 0 新技能（tier3）：选到期卡，`U=1.0`，理由含“到期组”，另两项标“tier 2/3 未进入” |
| D-S3 同日不重复 | 同日两次短会话不撞活动 | 同一 `LEARNARK_NOW` 日期 `start --minutes 10` 两次 → activity_id 与 skill 均不同；第三次输出“今日已完成 2 项”并收尾，退出码 0 |
| D-S4 一句话预算 | 自然语言预算正确落库 | `start "今天只有二十分钟"` → `minutes_budget=20`；`say "只有一刻钟"` → 15；`一小时` → 45 且含夹取提示；非法文本 → 20 |
| D-S5 SRS 可复现 | 间隔与 lapse 可验证 | 模拟时钟 0/1/3/7/15/30 天断言 `due_at` 序列；第 7 天 lapse → `step` 回退 2、`due=次日`；13 张积压 → 存在 `backlog_folded` 且队列 ≤3 |
| D-S6 导师不改调度 | 导师输出越权被拦 | 注入 `next:"直接学多 Agent"` + `mastery_delta:3`：调度不变、level 仅 +1、存在 `mentor_schedule_conflict` 事件 |

复测结论只能是 通过/失败/未测试，附版本、证据路径与复测日期；模拟时间证据必须标注。

## 12. 风险与失败方式

| 风险 | 可观察信号 | 处置 |
| --- | --- | --- |
| 过度碎片化 | 6 周后 L3 技能数 = 0；块完成率 <50% | Tier 2 权重上调；每周强制 2 次块步骤 |
| 复习轰炸 | 单会话到期卡 >6；积压 >12；首活动即退出 >30% | backlog 折叠；`leech` 移出短会话 |
| 调度与导师冲突 | `mentor_schedule_conflict` >0.5 次/会话 | 冻结导师 `next`，只降级为建议 |
| 候选为空 | 空候选率 >5% | 回落 5 分钟 recall_card 并显式说明原因 |
| 时钟异常 | `last_review_at > now` 或 due 全为负 | `doctor` 报 `clock_skew` 并夹取，不静默修 |

## 13. 8 轮实验计划（细则见 `experiments/PLAN.md`）

| 轮 | 可检验假设 / 变更 | 主证据 | 通过线 |
| --- | --- | --- | --- |
| 1 | 一句话开始 + 调度 + 1 个活动即可闭环 | S1 报告、D-S4 结果 | 解析 3/3 正确，会话完成率 ≥0.80 |
| 2 | 到期队列与到期优先可解释 | D-S2、D-S5、due 输出 | 到期选中率 100%（10 次构造） |
| 3 | 三导师切换不改调度 | S3 报告、handoff、冲突事件 | 无调度漂移，冲突事件有记录 |
| 4 | 干净克隆后 due 与最近重复仍生效 | S4 报告、克隆目录运行 | 恢复后同日不重复仍成立 |
| 5 | 预算改动显著改变选择（5/20/45） | D-S1、D-S3 | 5 与 20 必不同；45 允许同项但计划长度必须变 2 项 |
| 6 | email 模板完成 micro 闭环 | S6 报告 | 无编程残留，卡片为句式卡 |
| 7 | 积压折叠消除复习轰炸 | 积压/退出率对比 | 积压 >12 时不再增长 |
| 8 | L3 需块产物 + 延迟复测 | S8 报告、D-S6、比较矩阵 | 无纯卡练习获 L3 |
