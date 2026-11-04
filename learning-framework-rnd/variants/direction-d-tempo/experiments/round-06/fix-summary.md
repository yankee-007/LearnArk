# Round-06 修复摘要 — direction-d-tempo v0.2.5

- 版本：`0.2.5`（vendored core `1.0.2`，schema 1）
- 来源：`experiments/round-06/experience-S6-P4.md`（email 模板 / S6 跨主题迁移）
- 自检：`python tests\run_tests.py` → **50/50 通过**；`shared/check_variant.py` → **18/18**；`shared/vendor_core.py --check` → core 1.0.2 一致。

## 问题 → 修复 → 测试

| # | 报告问题 | 修复 | 回归测试 |
| --- | --- | --- | --- |
| 1 | 20 分钟里 5 分钟卡 + 8 分钟概念占满 2 项，12 分钟“写整封邮件”块连续被排除；次日计划仍没有写作块 | email 模板把当前周块的可交付写作步骤设为 priority：`select_activities(priority_ids=...)` 先选它，再按剩余预算补卡片/概念；12 分钟块在 20 分钟内**现在**就能排上。预算不足（如 10 分钟）时记 `core_block_deferred`，下一次 `start`/status 的 next 先做该写作块；`start` 不会启动无技能 fallback。 | `test_email_core_writing_block_is_not_starved`：email + 20 分钟 → 当前活动 `writing_block`/12 分钟且理由含“核心可交付块优先”；10 分钟 → `core_block_deferred` 且 status.next 是 12 分钟写作块 |
| 2 | 导师说“边界复述准确”、机器块 `correct=true`，却因 prose 里的“部分”被判 partial，界面让“补齐再答” | `prose_verdict` 不再从“部分/漏了/不完整”产生 partial；partial 只来自机器块 `result=partial` 或学习者明确自评（“我只记得/没答全/只答出一半”）。`block_correct=true` 优先；prose 明确相反时才记 `mentor_text_conflict`，且不产生证据/卡片。 | `test_correct_answer_with_partial_word_in_prose_stays_correct`：原句“对，边界复述准确。本轮概念部分就到这里。”+ block true → `result=correct`、有 level_change、无 `turn_partial` |
| 3 | 学习者回答里的“七分钟”被当成预算指令，`say` 打印已记录 7 分钟 | `say` 不再解析/应用预算；只记 `budget_ignored_in_answer` 并提示“要追加时间用 start --minutes N”。预算只由 `start`/显式 `--minutes` 决定。 | `test_say_answer_with_minutes_does_not_change_budget`；`test_budget_parsing` 更新为断言忽略而非追加 |
| 4 | 在 concept 会话里提交整封邮件，被记成该 concept 的 correct/observed 证据 | 检测写作草稿（`Hi/Dear/Subject:` + 结尾语）；在非写作活动里记 `off_activity_writing_review`，attempt 的 activity_type=`writing_review`、skill 路由到 `language-accuracy`（无则 structure-clarity），只记 observed，不升级/不建卡/不完成当前活动。 | `test_writing_draft_in_concept_session_routes_to_writing_skill`：concept-write 提交邮件 → attempt.skill=language-accuracy、concept skill L0/self_report、无 level_change、completed=False |
| 5 | email step2 的 `activity_type` 仍是 `code_kata`；6 张初始卡全部当天到期 | email 的写作步骤改为 `writing_block`（`kata` 别名仍映射），本地开场/证据/`PRODUCE_ACTIVITIES` 同步；`seed_cards` 前 2 张今天到期、其余 +1..+10 天，记 `initial_cards_spread`，init 输出“今天到期 2 张，其余分散”。 | `test_email_block_step2_is_a_writing_type`；`test_init_idempotent` 断言仅 2 张当天到期 + `initial_cards_spread` |

## 兼容性与状态变化

- 新增活动类型 `writing_block`；email 模板 12/15 分钟写作步骤使用它；`code_kata` 仅保留给 agent-dev。
- 新增事件：`core_block_deferred`、`off_activity_writing_review`、`initial_cards_spread`、`budget_ignored_in_answer`。
- 初始卡片不再全部当天到期；`due`/`start` 的首日样本变为 2 张（agent-dev 12 张中 2 张）。
- email 核心写作块优先**只对 email 模板**启用；agent-dev 仍按到期卡优先，避免破坏既有调度。

## 未关闭 / 观察项

- 写作草稿检测是启发式（问候 + 结尾语/Subject），非邮件正文可能漏判；路由为 observed、不升级，影响有限。
- 核心块 priority 只看“当前周块第一个未完成的可交付步骤”；若该步骤被同日模板过滤，会等待下一次。
- `partial` 自评词表有限；被误判为 failed 时不升级，可下一轮再答。
- 本轮未改 `shared/`、其他方向、vendored core。
