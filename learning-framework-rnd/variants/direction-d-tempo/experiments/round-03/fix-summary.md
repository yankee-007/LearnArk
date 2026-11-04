# Round-03 修复摘要 — direction-d-tempo v0.2.4

- 版本：`0.2.4`（vendored core `1.0.2`，schema 1）
- 来源：`experiments/round-03/experience-S3-P3.md`（S3/P3，真实 API；含 2026-11-05 模拟时钟段）
- 自检：`python tests\run_tests.py` → **43/43 通过**；`shared/check_variant.py` → **18/18**；`shared/vendor_core.py --check` → core 1.0.2 一致。

## 问题 → 修复 → 测试

| # | 报告问题 | 修复 | 回归测试 |
| --- | --- | --- | --- |
| 1 | “四个阶段…我只记得两个…”是实质作答，却因句中出现“直接给最终答案”被 `looks_like_question` 判为提问，记 `correct=None`、无证据；导师文字“对：四个阶段你说全了…”与机器块 `correct=false` 冲突但 `text_conflict=False`；部分正确没有单独结果 | (a) 提问启发式收紧：只有短（≤36 归一化字符）且无作答内容（`我只记得/我的理解/因为/停止条件/四个阶段…`）的请求才算纯提问；请求词必须在开头，陈述句里的“直接给…”不再命中。(b) `prose_verdict` 先识别“部分/漏了/不完整/没答全…”→ `partial`；只有明确“对/不对”与机器块矛盾才记 `mentor_text_conflict`。(c) `result` 成为每轮一等字段：`correct/partial/conflict/failed/question`；partial/conflict 记 attempt 但 `correct=null`、`evidence=none`、**不升级、不建卡、不完成活动**；partial 记 `turn_partial`。 | `test_partial_answer_is_not_question_and_gets_no_credit`（含 `looks_like_question` 为 False、partial、无 level/card）；`test_text_conflict_uses_block_and_is_logged`（conflict、`no-evidence`、无 level/card）；`test_pure_question_turn_is_not_an_attempt` 仍保留 |
| 2 | `switch examiner` 报成功、handoff 记 examiner，但下一次 `start` 按活动类型回切 trainer；journal 缺回切说明 | (a) `switch` 写 `meta.mentor_override`，`plan_decision` 在下一次调度时优先构造 override 能带的活动（examiner→quiz/recall，coach→concept/explain/recall），`start` 显示“switch 指定 examiner”。(b) `open_session` 只在活动真正由 override 导师带时清除 override，并记 `mentor_override_used`；未开始则保留。(c) 再次 `switch coach` 记反向 `mentor_switch`。 | `test_explicit_switch_is_sticky_for_next_start`（switch examiner→start 的 session.mentor=examiner、活动为 quiz/recall、override 清空；pause→switch coach→start coach；journal 反向事件与 `mentor_override_used`） |
| 3 | handoff “未决问题：无”漏掉导师最后追问；`status.next` 与同日 `start` 选择不一致，5 分钟剩余却说预算不足 | (a) `handoff_summary` 在最后一条 mentor 消息带问号时记“导师追问：…”，写入最新 handoff。(b) `status` 计算下一步后把可行决策缓存到 `.learnark/tmp/next-decision.json`（状态签名+预算校验），`start` 在同一签名下复用，`next.decision_id` 可核对；today 模板/技能覆盖导致不能开始时，`start` 明确收尾而不是启动 fallback。(c) 状态文案区分“已排满”“剩余不足（约 N 分钟）”“剩余够但同模板/技能已覆盖”，5 分钟够 5 分钟活动时显示“现在”。 | `test_handoff_captures_open_question_and_concrete_next`（open_questions 含导师追问、next_step 具体）；`test_status_next_matches_start_and_five_minute_wording`（status.next 与 start 活动 id 一致；5 分钟时无“不足下一项”、start 收尾不建 fallback） |

## 兼容性与状态变化

- `status.last_turn.result`、`status.mentor_override`、`status.next.decision_id` 新增；`status --json` 同步。
- 新增事件：`turn_partial`、`mentor_override_used`；`mentor_text_conflict.decision=no-evidence`（不再 `use-block`）。
- `switch` 现在真正影响下一次 `start`；`status` 显示“导师覆盖：examiner（下次 start 生效）”。
- 预算拒绝理由改为“本次放不下（剩余 N 分钟）；下次（约 M 分钟）”，不再出现“超出剩余 N 分钟”。

## 未关闭 / 观察项

- 提问/partial/冲突检测仍是启发式；误判边界写入事件，可复核。
- `next-decision.json` 只是同一状态下的缓存；`say`/预算变化会改变签名并重新调度，这是预期。
- sticky override 只覆盖下一次 `start`；若因 2/2 上限或预算收尾而未开始，override 保留。
- 本轮未改 `shared/`、其他方向、vendored core。
