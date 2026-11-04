# round-05 修复摘要（v0.2.4）

- 基线：`experience-S5-P3.md`（0.2.3，S5 短时与返学）
- 版本：`0.2.4` · core 1.0.4 · schema 1
- 验证：`tests/run_tests.py` → 80 tests OK；`shared/check_variant.py` → 18/18；`vendor_core.py --check` → 1.0.4 一致

## 1. 学习者时间不落盘（问题 1）

- 根因：`say` 只把时间当对话内容；project/plan 仍是 init 的 720 分钟/12 小时，`--minutes` 只加显示行。
- 修复：新增 `timeparse.py`，解析“每周 1–2 小时 / 每周 90 分钟 / 今天 20 分钟 / 还有 10 分钟”（含中文数字）。`say` 在模型调用前把每周值/区间写入 `project.learner` 与 `plan.minutes_per_week/weekly_range_minutes`，把今天分钟写入 `session.budget_minutes`；写 `learner_time_recorded` 并显示“已记录你的时间…”。start/plan/context/export 用 `format_weekly_scope` 显示真实区间。
- 测试：`FlowTests.test_learner_time_is_persisted_and_displayed`（1–2 小时→[60,120]/120，start 与 plan 均显示 1–2 小时）。

## 2. 结束后的 next 不可执行（问题 2）

- 根因：`next` 只有一句 step 文本，没有动作/活动/预计分钟；导师口头承诺“concept 十分钟讲状态/记忆”没有进入计划/未决/交接。
- 修复：`next_step()` 统一返回 `action/activity_id/est_minutes`（考核还带 `question_id`）；start/status/pause 都打印动作、约几分钟、导师。导师 `next` 中带“下一轮/明天/十分钟/分钟”且点名导师时，记 `mentor_next_observed` 并写成 blocking open_loop；有已生效计划变更、pending exam 时视为已被记录决策取代，不重复。
- 测试：`FlowTests.test_promised_next_becomes_open_loop_with_time_estimate`（status next=concept、action 含“状态”、est=10）。

## 3. 20 分钟按导师口播、probes 未用（问题 3）

- 根因：无会话时钟，mentor 说“20 分钟到”就结束；start 列的 probe 没人核对。
- 修复：session 记录 `budget_minutes/started_at`，每回合按真实 `clock` 算 elapsed/remaining，打印“本次剩余/还有 N 分钟”；到点只提示预算已到，不自动结束。start 记录 promised probes；planner 回复检测 `probe-d1..d3/e1/e2` 的 ID/题干/关键词，写 `probes_asked`；未覆盖 2 道且没有计划/交接时 `plan_state=diagnosing`，start 继续列未问题。
- 测试：`FlowTests.test_session_clock_and_probes_are_real`（模拟 19:00/19:05/19:40）、`test_planner_must_use_two_probes_before_diagnosis_done`。

## 4. 空会话自交接与“独立完成”措辞（问题 4）

- 修复：pause 发现 `session.turns` 为空时只记 `pause_no_handoff`、不写 handoff/session 原文；帮助等级 0 文案由“独立完成”改为“独立作答（无提示）”。
- 测试：`HandoffTests.test_pause_empty_session_writes_no_handoff`；原 pause 测试改为“有回合但无提案仍写完整交接”。

## 仍未关闭

- probe 识别是关键词/ID 启发式，模型完全换措辞仍可能漏判。
- 时间语句只解析常见中文/阿拉伯数字；复杂条件句仍可能漏。
