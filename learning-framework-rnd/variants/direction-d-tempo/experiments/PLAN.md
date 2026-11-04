# Tempo 方向 8 轮实验计划（plan-tempo-v1）

版本基线：`version-manifest.json` 0.1.0 / core 1.0.0。细则以 `design.md` 与 `shared/acceptance.md` 为准。
所有轮次按 `research-plan.md` 第 6 节推进；每轮必须有“可检验假设 → 实现/场景变更 → 独立体验 → 反馈分诊 → 修复 → 独立复测 → 记录”七步，只跑测试或只改文案不算一轮。

## 0. 指标定义（固定，禁止临轮改口径）

| 指标 | 定义 | 目标 |
| --- | --- | --- |
| 会话完成率 | 完成活动数 / 开始活动数 | ≥0.80 |
| 决策数 | 除分钟数外，开始一次学习所需必要输入次数 | ≤1 |
| 命令数 | 单次会话执行的命令条数（不含 `say` 正文） | ≤3 |
| 延迟回忆通过率 | 卡在 `due_at+7±1` 天首次复测中 `correct=true` 且 `help_level≤1` 的比例 | ≥0.70 |
| 到期选中率 | 到期组非空时实际选中到期项的会话数 / 到期组非空的会话数 | 100% |
| 同日重复数 | 同一模拟日内同一 `activity_id` 或同一 `skill` 被再次调度的次数（显式 `review` 除外） | 0 |
| 积压量 | `due` 队列中已过期卡片数 | ≤12 |
| 块完成率 | 已完成块步骤数 / 计划块步骤数 | ≥0.80/周 |
| L3 纯卡获得数 | 仅凭卡练习取得 L3 的技能数 | 0 |

## 1. 八轮表

| 轮 | 可检验假设（失败即证伪） | 实现/场景变更 | 主证据 | 通过线 | 失败即处置 |
| --- | --- | --- | --- | --- | --- |
| 1 | 只说“今天只有二十分钟”即可在 ≤1 次决策内开始并完成 1 个活动 | 最小闭环：`start` 预算解析、调度 top3、单活动、`pause` | `experiments/round-1/experience-S1-P1.md`；`schedule.json`；D-S4 输出 | 解析 3/3 正确；决策数 ≤1；完成率 ≥0.80 | 阻塞级：预算解析或调度不可用，当轮修复后重跑 S1 |
| 2 | 到期优先可解释，错误能生成误解卡并进入次日队列 | 到期队列 `due`、lapse 规则、误解卡生成 | D-S2 / D-S5 测试输出；`round-2/experience-S2-P2.md` | 到期选中率 100%（10 次构造）；误解卡次日到期 | 若 U 因子被新内容压过，收紧缩为硬 tier 并复测 |
| 3 | 三导师切换不改变已调度活动，handoff 保留未决项 | coach/trainer/examiner 绑定、`switch` 契约、`mentor_schedule_conflict` | `round-3/experience-S3-P3.md`；handoff 前后对比；冲突事件 | 无调度漂移；切换后 `status` 下一步一致 | 若导师 `next` 被误用，冻结该字段并记缺陷 |
| 4 | 干净克隆后 due 队列、同日不重复、最近重复惩罚仍生效 | `sync` 三态报告；克隆目录运行 | `round-4/experience-S4-P3.md`；克隆目录 `due`/`start` 输出；`git log` | 恢复后同日重复数 = 0；written/committed/pushed 标注准确 | 无远程时如实标 pushed 未验证，不改口径 |
| 5 | 预算 5/20/45 改变选择与计划长度；同日两次不撞活动 | 预算档位、会话 2 项上限、`recent` 过滤 | D-S1 / D-S3；`round-5/experience-S5-P3.md`；P1/P2 分桶数据 | 5 vs 20 选择不同；45 计划 2 项；同日重复数 = 0 | 若差异只出现在文案，重构打分或候选集 |
| 6 | email 模板完成“预算→微活动→反馈→保存→恢复”且无编程残留 | `templates/email.md` 写作微技能、句式卡、rubric | `round-6/experience-S6-P4.md`；`skills.json`（email 项目） | 无 agent/python 字段残留；卡片为句式/语气卡；完成率 ≥0.80 | 若残留编程标准，重写模板与评价标准后重测 |
| 7 | 积压折叠与 leech 隔离能消除复习轰炸 | backlog 折叠 +3 天、leech 仅 ≥10 分钟、每会话到期上限 3 | `round-7/experience-S7-retest-P3.md`；积压时序；首活动退出率 | 积压 >12 时不再增长；首活动退出率下降 ≥10 个百分点 | 若下降不足，降每周卡量上限并复测 |
| 8 | L3 只能由“块产物 + ≥7 天延迟复测”取得；整体优于消融组 | 周项目块 Tier 2、D-ablate 固定顺序对照、比较矩阵 | `round-8/experience-S8-fresh.md`；`evaluation/` 独立验收；比较矩阵 | 纯卡 L3 = 0；块完成率 ≥0.80；消融组完成率差 ≥10 个百分点 | 若消融差 <10 点，公开承认“调度假设未获支持”，不改指标 |

## 2. 固定 fixture（D-S1 复现用，写在 `experiments/fixtures/tempo-budget.json`）

候选 6 个，技能与卡均为构造值，**不得**用于体验报告冒充真实记录：

| 候选 | 活动 | 时长 | tier | 关键字段 |
| --- | --- | --- | --- | --- |
| A | recall_card | 5 | 1 | `overdue_days=0`, level 1 |
| B | code_kata | 15 | 1 | `overdue_days=3`, level 2 → U=1.0 |
| C | quiz | 12 | 2 | 本周块下一步，P=1.0 |
| D | concept_block | 5 | 3 | level 0, N=1 |
| E | explain_back | 10 | 3 | level 0, N=1 |
| F | code_kata | 20 | 3 | level 0, N=1 |

预期：`--minutes 5` → A（B 超预算被硬过滤，理由须含“超出剩余 5 分钟”）；`--minutes 20` → B（U=1.0、F=0.75 胜过 A 的 0.25/0.25）；`--minutes 45` → 仍 B，但计划追加 C（2 项上限）；三次连跑输出逐字节一致。

## 3. 时间与证据纪律

- 全部 SRS/间隔/积压断言用 `learncore.clock` + `LEARNARK_NOW`；事件带 `simulated:true`；报告必须写“模拟时间，仅证明调度逻辑，不证明真人保持”。
- 禁止在测试与 fixture 里手写固定日期冒充 `due_at`；只能经 env 注入后由运行时写入。
- 每个结论标注 `通过 / 失败 / 未测试 / 不适用（附理由）`，附版本、证据路径、复测日期；不得删测试、放宽阈值或改预期。
- 体验者与研发者上下文分离；实现者不得给自己签独立验收；阻塞问题先留证据再修。
- 缺陷分级按 `shared/acceptance.md` 第 D 节执行，阻塞问题未关闭则该轮不通过。
