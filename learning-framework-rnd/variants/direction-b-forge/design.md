# Forge 作品驱动 — 产品设计

`direction-b-forge` 0.1.0｜core 1.0.0｜state schema_version 1

## 1 主张与边界

一句话：不排课程，只给里程碑与 rubric；先交作品，按 rubric 打分，低分维度即下一节微课。

目标学习者：自述有 Python/API 经验、想做出能跑的 Agent、接受作品被公开标准打分的自学者；每周 10–20 小时，单次可短至 20 分钟。

非目标：零基础编程（不教语法与调试）、考证、实时陪伴或代写、团队协作、账号云端、后台唤醒、移动端。

## 2 假设与替代解释

- H1：P1 从 `start` 到首次 `artifact add` ≤8 次往返，无需研发者介入。
- H2：10 次评审中，`next.action` 指向的缺口维度＝未达标维度里 weight 最高者，一致 ≥9 次。
- H3：无作品、同 sha 重复、未达阈值时，`milestone_passed` 恒为 0。
- H4：P2 无行号解释的 defense 通过率 ≤10%。

替代解释：H1 败而完成率不低 → 关键在任务颗粒度；H2 不一致 → rubric 维度太粗；H3 过但迁移复测败 → rubric 只测"能跑"；H4 分不开 → 提问太泛，须绑行号。

## 3 流程

1 **首次进入**：`start` 只问 3 个选择题，不做课程诊断、不测知识点：能否跑通 API 调用；是否做过带工具调用的 Agent；这次要"20 分钟见东西／一次做完一个项目／先搞清概念"。答案只进 `start_profile`，用于定起点（m1/m2）、严苛档、切片（20/60 分钟），**不作能力证据**。
2 **领任务**：`task` 给可交付物、rubric（维度/权重/阈值）、已有作品、上次最低分维度。
3 **动手**：coach 仅在卡住超 1 轮时提示：小提示→分步→示范。
4 **登记**：`artifact add PATH` 复制进 `artifacts/<milestone>/`，记 sha256/size；空文件、<20 字节、后缀不在 .py/.md/.json/.txt 内拒绝。
5 **评审**：`review` 自动切 critic 打 4 维分，校验裁剪后落 `reviews.json`。
6 **缺口微课**：低于阈值的维度出缺口卡，`gap learn` 切 guide 只讲该维最小概念 + 一个 5–10 分钟微练习。
7 **防御解释**：`defend` 由 coach 提 3 个绑定作品的问题，答案须引用具体行，运行时按行内容校验。
8 **通过**：有作品 + rubric 达标 + ≥2/3 解释通过（最重维度那问必过）。
9 **下一个**：激活 M2，未关缺口作"已知弱点"展示，不阻塞。

## 4 作品与里程碑（Agent 开发）

| 里程碑 | 可交付物 | rubric（权重/阈值，1–4 整数） |
| --- | --- | --- |
| M1 单轮工具调用 Agent（3–5h） | `m1/agent.py` + `docs/m1-design.md`；两工具、6 步上限、三类失败可读 | runnability 30/3、contract 30/3、robustness 20/3、explainability 20/2 |
| M2 带记忆与错误处理的多步 Agent（6–10h） | `m2/agent.py` + `m2/state/session.json` + `docs/m2-design.md`；原子落盘、滚动摘要、`--resume`、退避 3 次、副作用幂等 | runnability 25/3、contract 25/3、robustness 30/3、explainability 20/2 |
| M3 可评测的小项目（10–16h） | `m3/` + `eval/tasks.jsonl` ≥10 条（含 2 条边界或对抗）+ `logs/trajectories.jsonl` + `REPORT.md` + 3 分钟讲解 | runnability 20/3、contract 20/3、robustness 25/3、explainability 35/3 |

分数为 1–4 整数，0 与 5 非法（运行时 clamp）。通过＝作品存在 + 四维全 ≥阈值 + defense 3 问中 ≥2 通过且最重维度那问必过，写 `pass_evidence{artifact_id,review_id,defense_id}`，缺一不落 `passed`。权重与阈值只读模板，导师改动即整次拒绝；`explainability` 不接受自述，须附行号。邮件模板改 3 封场景邮件 + 修改说明，四维为目的/结构/语气/准确各 25、阈值 3。

## 5 缺口卡

由 `score < 阈值` 生成（`阈值 ≤ score` 不生成；`explainability` 达标但无行号仍生成）。

字段：`gap_id`、`milestone`、`dim`、`score`、`threshold`、`weight`、`note`（≤200 字修改项）、`evidence`（artifact + 行号区间）、`source_review`、`status`(open/learning/closed/stale)、`closed_by`、`attempts`。

排序：weight 降序 → `(阈值 − score)` 降序 → 里程碑升序；同 dim 连续 3 次 open 乘 0.6。

关闭：①后续评审该维 ≥阈值；②微课 + 微练习且 help_level ≤1（标"未在作品复验"）；③`gap drop` 记 stale，不算解决、doctor 必列。同 sha 同维不重复建卡。

## 6 导师与切换

coach（默认）拆任务、分级提示、逐步放手、提防御问题。critic（review）只打分与给修改项，须带行号，禁给完整代码，`mastery_delta` 恒 0。guide（gap）只讲当前卡概念 + 微练习，讲完回 coach。

`review` 与 `gap learn` 由运行时强制切换并写 handoff（from/to/reason/open_items/ref），结束回 coach；用户 `switch` 仅限三者，未知值报错列可选；同会话 >3 次记 `mentor_thrash`。新导师上下文必含当前里程碑、最近分数、open gap 前三、上次 handoff 的 next。

## 7 状态与下一步

`brief.json`（schema_version=1）：`goal`、`template`、`minutes_per_week`、`start_profile{answers,mapped_start,strictness,slice_minutes}`、`milestones[]{id,title,deliverable{paths,allowed_ext,min_bytes},rubric[]{dim,criteria,weight,threshold},status(locked|active|passed|passed_assisted|blocked),artifact_ids[],review_ids[],pass_evidence{},passed_at}`、`current_milestone`、`next{action,reason,ref}`、`updated_at`。

`artifacts.json`：`items[]{id,milestone,path,sha256,size,assisted_level,supersedes}`。`reviews.json`：`items[]{id,artifact_id,rubric[{dim,score,note}],gap_dims[],clamped[],proposed_by:"llm",validated_by:"runtime",event_id,at}`。`gaps.json`、`defense.json` 同带 schema_version 与 items。

LLM 只提议每维 1–4 整数分、note、gap 维度与 defense 判定；运行时负责维度集合比对（缺/多整次拒绝）、1–4 clamp、权重与阈值只读、通过判定、写事件。分数必须追到 `review_id` 与 `event_id`。

下一步（纯函数，`next --json` 可复现，LLM 不得覆盖）：①有完成声明无作品→`artifact_required`；②无作品→`do_task`（按 minutes 选 20/60 切片）；③有作品无评审→`review`；④任一维低于阈值→`gap_learn`（排序最高者）；⑤达标但 defense 未过→`defend`；⑥三者齐→通过并激活下一个；⑦全过→导出档案。

## 8 记忆与独立完成

链路：artifact(sha) → review → gap(行号) → fix(新 sha, supersedes) → re-review。`export` 输出五元组；doctor 校验 closed gap 的复评 sha 必须变，否则报"未修改即关闭"。

每次 `artifact add` 记自上件以来最大 help_level 为 `assisted_level`。verified＝达标 + `assisted_level ≤1` + defense ≥2/3；observed＝达标但 `assisted_level ≥2`，记 `passed_assisted`，不进独立完成统计；接触＝有评审未达标。自述永不升级。

## 9 与 A/C/D 的区别

A 有节点图与诊断题；Forge 的 `status --json` 只有 milestones/rubric/gaps，无 nodes/edges。C 有 5 个导师与 planner 周计划；Forge 只 3 个、由事件触发切换、无 planner。D 按时间预算调度活动；Forge 改 `--minutes` 只改切片，`next.action` 不变。判别事实：无 artifact 时 `milestone_passed`=0，每 gap 必有 `source_review`。

## 10 方向特有验收

| ID | 可观察行为 | 测试方法 |
| --- | --- | --- |
| B-S1 无作品拒绝 | `say "我做完了"` 后输出"未登记作品"、写 `claim_without_artifact`、里程碑仍 active、退出码 0 | init→start→say→`status --json` 断言 status=active 且有该事件 |
| B-S2 评分驱动 | mock 令 contract=2（阈值 3）、其余达阈值时，`next --json` 必为该维 `gap_learn` | 固定 mock → review → next 比对 dim |
| B-S3 幂等 | 同文件登记两次：artifacts 1 条、review 1 次、分数不重算 | 两次命令 + journal 计数 |
| B-S4 解释造假 | 三问全填"我理解了设计"判 failed，不得 passed | mock 答案 → defend → `status --json` |
| B-S5 clamp/拒绝 | 9、−3、"高"、缺维、新增维、改权重 → clamp 到 1–4；缺/多维或改权重整次拒绝并记 `review_invalid`，退出码 3 | mock 逐项注入，查 reviews 与事件 |
| B-S6 证据链 | 任一 closed gap 可导出五元组；作品回退旧 sha 后 doctor 报错 | export → 改回旧 sha → doctor |

## 11 风险与信号

- **挫败**：首个作品前 help_level ≥2，或 6 轮内 ≥2 次"不会/放弃" → 20 分钟切片与最低可跑版本；仍败分流到 A。
- **虚高**：四维全 ≥3 但 defense 失败 >50%，或 eval <50% 而 runnability ≥3 → 阈值制 + 行号 + 抽查复跑。
- **漂移**：同作品两次独立评审同一维差 ≥2 分，或结论翻转 → 0/3/4 锚点、temperature 0.2、记录分差。
- **代做**：行号正确率 <50% 或注释率突变 → defense + `assisted_level`。

## 12 8 轮实验

详见 `experiments/PLAN.md`。

| 轮 | 假设 | 变更 | 场景/画像 | 预期证据 | 收敛判据 |
| --- | --- | --- | --- | --- | --- |
| 1 | 3 问可定起点 | 最小闭环 + M1 rubric | S1/P1 | 首个 artifact | ≤8 轮首次提交 |
| 2 | 低分维度定下一课 | review + gaps + next | S2/P2 | 分数表与排序 | 一致 ≥9/10 |
| 3 | defense 能分"能跑"与"会做" | 三问 + 行号校验 | S2,S3/P2,P3 | 通过失败对照 | 无行号通过率 ≤10% |
| 4 | 克隆与同步不丢证据 | pause/sync/doctor | S3,S4/P3 | 克隆后对比 | 分数与 gap 全一致 |
| 5 | 20 分钟可推进 | 20/60 切片 | S5/P3 | 单次增量 | 至少 1 次增量或关缺口 |
| 6 | 换主题仍成立 | email 模板与写作 rubric | S6/P4 | 写作评分表 | 无编程术语残留 |
| 7 | 阻塞与漂移可收敛 | 锚点与复评规则 | S7/指定 | 修复前后分差 | 阻塞清零、单维差 ≤1 |
| 8 | 新体验者可走完门控 | 入口收尾，不改阈值 | S8/新上下文 | 新体验报告 | 10 轮走完全链、B-S1..S6 全过 |
