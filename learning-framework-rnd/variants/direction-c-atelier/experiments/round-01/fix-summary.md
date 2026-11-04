# round-01 修复摘要（v0.2.1）

- 基线：`experience-S1-P1.md`（0.2.0，真实 API，S1/P1 阻塞）
- 修复版本：`0.2.1`（`version-manifest.json`）· core 1.0.1
- 验证：`python tests/run_tests.py` → 56 tests OK；`shared/check_variant.py` → 18/18；`vendor_core.py --check` → core 1.0.1 一致
- 真实 API 冒烟（deepseek-flash）：`say` → `mode=api`、`invalid=false`、`attempt_id` 存在；随后 `switch concept`（无提案）exit 0，`handoff --check` 通过，`do_not_redo` 为空、`what_tried` 含真实轮次。
- 修复原则：**回合落盘优先于交接严格性**；交接内容由运行时从 journal/session/plan 合成，导师只给 `why`。

## 1. say 丢回合（B-1）

- 根因：`say` 在调用导师前先做名称触发的 `_do_switch`，严格交接失败直接 `return 3`，学习者消息、导师回复、会话均未写。
- 修复：`runtime/atelier/commands.py`
  - 先写 `say_attempt`（唯一 `attempt_id`），再处理可选换人；换人失败记 `handoff_rejected{reason,missing,source}` 并留在当前导师继续本轮。
  - 自动交接失败同样只记 `handoff_rejected`，`say` 始终 `0`。
  - `perform_turn` 先落会话与 `mentor_turn`，再做后续动作。
- 测试：`FlowTests.test_say_keeps_turn_when_auto_handoff_is_incomplete`（exit 0、session 含双方原文、`handoff_rejected`、导师不变）。
- 证据：journal `say_attempt`→`mentor_turn`→`handoff_rejected` 顺序可在任意失败回合复核。

## 2. start/status 提示的 switch 默认失败（B-2）

- 根因：交接内容字段被要求由导师提案，缺字段即 exit 3。
- 修复：`runtime/atelier/handoff.py`
  - `compose_payload` 默认由运行时合成 `known/what_tried/open_loops/next/do_not_redo`；`why` 缺省“用户点名”。
  - `what_tried` 取当前会话轮次/尝试，退化时取 journal 最近 attempt/assisted/exam；不再写“没有新的动手尝试”这类推断。
  - `switch` 默认成功；新增 `--strict` 仅供 C-S2 契约测试（仍 exit 3、不写文件、不换导师）。
- 测试：`HandoffTests.test_switch_without_mentor_proposal_succeeds_and_composes_everything`、`HandoffTests.test_strict_incomplete_handoff_is_rejected_without_side_effects`、`HandoffTests.test_fill_missing_degrades_explicitly_under_strict`。

## 3. 丢失/不可见回合与重名误判（B-3 / I-5）

- 修复：`say` 每次尝试都写 `say_attempt`（唯一 `attempt_id`）；重复文本若已有成功回合才按“已记录”跳过，失败回合不会因 dedupe 消失。
- 名称解析：精确 id 优先；只有 id 与“找/让/讲/考…”邻近才算点名；多候选 exit 2 并列出候选，绝不静默 no-op。
- 测试：`FlowTests.test_three_failed_proposals_leave_three_audit_events`（3 个 `say_attempt` + 3 个 `handoff_rejected`）、`FlowTests.test_switch_plan_is_rejected_with_candidates`、`FlowTests.test_mentioning_planner_does_not_switch_sessions`。

## 4. 交接历史失真（I-4）

- 修复：`handoff.py` 的 `known/what_tried` 只取 capability 证据、会话轮次与 journal；删除模板 anti-pattern 注入。
- `do_not_redo` 只收导师 `do_not_redo` / 学习者明确“不要再讲/讲过了”等原话，写 `do_not_redo_recorded`；空列表合法。
- 测试：`FlowTests.test_handoff_what_tried_has_real_attempt_and_no_invented_dnr`、`HandoffTests.test_explicit_do_not_redo_is_capped_and_logged`。

## 5. 计划/进度不一致（I-6）

- 修复：`plan` 周目标行显示运行时算出的 `x/y 步完成`；`replan_week/replace_step` 文本中的“已完成/已掌握”在没有证据时改为“进行中（待证据）”并记 `plan_claim_sanitized`。
- `op:"none"` 不再生成空的待批 `plan_changes` 行；待批提示使用真实 ID；`status` 也列出待批 ID。
- 测试：`PlanAuthorityTests.test_plan_text_cannot_claim_unverified_completion`、`test_pending_plan_change_renders_non_empty_and_hint_uses_its_id`、`test_op_none_does_not_create_empty_pending_change`。

## 顺带修复

- 首次 `start` 不再打印诊断题参考答案（G-8）。
- `.gitignore` 增加 `.learnark/usage.jsonl`（G-9）。
- `START_HERE.md` / manifest / runtime 统一为 0.2.1（G-10）。
- 终端提示去掉 `help_level`/`manifest` 等术语，改为“帮助等级/本轮上下文”；自交接标题改为“会话交接（X 收工）”。
- 当前导师与建议导师一致时，`pause/status` 不再提示“换到同一位”。

## 仍未关闭

- 无 journal→snapshot 自动重建；崩溃在 `mentor_turn` 与会话写之间仍可能产生快照漂移（doctor 检出部分）。
- `do_not_redo` 归档/退役、`handoff_stale_plan` 未实现。
- `--minutes` 仍未真正裁剪活动；30 回合/真实 API 成本曲线未验证。
- `sync` 事件在提交后追加，紧跟其后的 `status` 可能仍显示 journal dirty。
