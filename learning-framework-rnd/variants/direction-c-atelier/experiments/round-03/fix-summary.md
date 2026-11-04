# round-03 修复摘要（v0.2.3）

- 基线：`experience-S3-P3.md`（0.2.2，S3/P3 导师切换与中断恢复）
- 版本：`0.2.3` · core 1.0.2 · schema 1
- 验证：`tests/run_tests.py` → 73 tests OK；`shared/check_variant.py` → 18/18；`vendor_core.py --check` → 1.0.2 一致
- 原则：运行时排程是唯一 `next`；换人只由显式请求触发；历史只从 journal/session 读取。

## 1. 交接丢失上一段会话（问题 4）

- 根因：`compose_what_tried` 只读当前 `session.json`，换人/暂停后上一段尝试消失，concept 从零重讲。
- 修复：`handoff.py` 增加跨会话聚合：当前会话 + journal `mentor_turn` 中最近 3 次其他会话的 attempt，按“上次会话 <id>：activity（自称对/未核验、帮助等级）”输出；`open_loops` 继续从状态聚合，总条数仍受 5×120 限。
- `next` 仍只来自 `next_step()`；导师正文说“过掉了”不改 step 状态或进度。
- 测试：`FlowTests.test_handoff_aggregates_attempts_across_sessions`（两次 pause 后 what_tried 同时含两段 activity，且 `steps_done=0`、步骤未 done）。

## 2. 误把导师解释当学习者弱点（问题 5）

- 根因：只要句子含纠正词+技能词就记录，计划/讲解/夸奖句被写进 `last_fail`，还给未开始的 `w2-tools` 建弱点。
- 修复：`extract_misconceptions` 只接受两类：学习者原话被点名（`你把/你说/你的回答/这句…` + 明确纠正词），或 planner 明确诊断（`误解/需要纠正/需要先讲清`）。解释句、夸奖句、泛泛“错误”不再记录；`source=mentor_correction`，没有 attempt/归属句不建技能弱点。
- 测试：`FlowTests.test_explanation_does_not_create_false_misconception`（解释句不产生 `misconception_observed`，w2 无 `last_fail`）；原有 `EvidenceTests.test_misconception_is_recorded_as_weakness_with_source` 保留真实纠正路径。

## 3. 叙述性提到导师导致换人（问题 6）

- 根因：`_has_switch_intent` 在名字前后 ±4 字找“让/找/换”，`上次 planner 让我…` 被当成请求，触发 concept→planner→concept。
- 修复：只有名字前以“让/找/请/叫/换到/切换到/交给/派/用/我要”结尾，或名字后以“来/考/讲/带/接/帮我/陪我/接手…”开头才换人；其余只记 `mentor_mentioned`（含 attempt_id、候选），当前导师不变。`switch` 命令与直接意图词（“考我/帮我复盘”）不受影响。
- 测试：`FlowTests.test_mentor_mention_is_recorded_without_switching`、`test_mentioning_planner_does_not_switch_sessions`。

## 4. pause 后工作树脏（问题 7）

- 根因：`pause` 先提交，再追加 `sync` 事件，导致 journal 永远落后一个提交。
- 修复：`session_end` 与 `sync`（phase=requested）在 `git.sync` 前写入；详细报告写入被忽略的 `.learnark/sync-log.jsonl`；`pause` 后树干净。普通 `sync` 同样先写事件。
- 测试：`GitTests.test_pause_leaves_git_tree_clean_with_remote`（有 remote 时 `committed=yes` 且 `git status --porcelain` 为空）。

## 5. start 写交接/造历史（问题 2）与周时长单位（问题 3）

- `start` 不再调用 stale-handoff 逻辑：不写 handoff、不改 studio、不生造 `OL-objective`；只打开一次会话（`session_opened`）并提交该指针，第二次 start 零写入。
- `--minutes-per-week` 按分钟存储、按小时显示：默认模板 12h→720，60→“1 小时”，600→“10 小时”；init/start/plan/context/export 统一。
- 测试：`FlowTests.test_start_is_read_only_and_does_not_invent_history`、`InitTests.test_minutes_per_week_uses_hours_for_display`。

## 仍未关闭

- 跨会话聚合只覆盖 journal 里带 attempt 的回合；纯文本回合仍只靠当前会话。
- 误解识别仍是关键词启发式；纠正句没有学习者归属时会漏记。
- `--minutes`（单次）仍只影响提示，未真正裁剪活动。
