# round-06 修复摘要（v0.2.4）

- 基线：`experience-S6-P4.md`（0.2.3，S6 跨主题迁移，email/P4）
- 版本：`0.2.4` · core 1.0.4 · schema 1
- 验证：`tests/run_tests.py` → 80 tests OK；`shared/check_variant.py` → 18/18；`vendor_core.py --check` → 1.0.4 一致

## 1. 生成入口文档的编程残留（问题 5）

- 根因：README 固定示例“工具调用报错”，AGENTS.md 固定 Agent/JSON/help_level 技术说明，与 email 模板无关。
- 修复：`assets.readme_text/agents_text` 按当前模板分支。email 版使用写作示例（“把这封邮件改到 150 词，只保留一个诉求”）、纯中文状态说明、写作练习规则；email 目标若含编程残留则回退为“英文工作邮件写作”；README 页脚不再出现 `help_level`。Agent-dev 仍保留技术说明。
- 测试：`InitTests.test_email_project_docs_are_writing_specific`（README/AGENTS 均不含 agent/json/help_level/tool call/工具调用）。

## 2. examiner 判定与 open_loop 矛盾（问题 6）

- 根因：handoff `what_tried` 只看 `claimed_correct`，examiner 的 `correct=true` 被写成“未判定”；pass 不关里程碑未决项；verified 等级可与空 artifact 并存。
- 修复：
  - `compose_what_tried` 对 exam 回合按 `correct` 写“通过/未通过”，练习回合仍区分“自称对（未核验）”。
  - `apply_evidence` pass 时调用 `close_open_loops_on_pass()`，关闭包含 node/activity 的 open_loop 并记 `open_loop_closed`。
  - examiner pass/fail 若没有 artifact，运行时自动写 `artifacts/<题号>.md`（题目、判定、依据、学习者原话）；证据 `artifact_verified=true`，不再出现 verified + null artifact。
- 测试：`EvidenceTests.test_three_question_exam_is_resumable_and_artifacts_verified`（artifact 存在/verified、stale loop 关闭）；原 examiner pass/fail 测试保留。

## 3. 3 题考核不可恢复（问题 7）

- 根因：`new_exam` 每次覆盖单个 pending；pass 一次就清空，q2/q3 无入口。
- 修复：pending_exam 持有 `questions/remaining_questions/answered/current_index/total=3`。`new_exam` 对已有队列复用；`_exam_progress` 答一题减一题，未答完保持 open/next=examine，答完才清空；status/start/examine 显示下一题；`run_tests` 覆盖三题顺序。
- 测试：`EvidenceTests.test_three_question_exam_is_resumable_and_artifacts_verified`（q1/q2 后 remaining=2/1、next=examine；q3 后清空）。

## 4. 无效回合与 probe 承诺（问题 8）

- 修复：机器块非法仍保留 `mentor_turn`/session 原文，footer 提示“本轮没有形成可记录的证据”；status 的最近回合显示 `!` 与“原文已保留”。start 只在模板确实有 diagnostics 时列 probe，并显示剩余待问题；email 的 probe-e1/e2 来自模板，不再凭空承诺。
- 测试：既有 `test_invalid_machine_block_retries_once_then_hides_jargon`；`test_planner_must_use_two_probes_before_diagnosis_done`；`test_email_project_docs_are_writing_specific`。

## 仍未关闭

- artifact 自动记录的是“判定摘要 + 学习者原话”，不是完整邮件成品；写作产物仍建议另存 `artifacts/`。
- 3 题队列按“答一题减一题”推进，examiner 临时改题号时只保证队列长度，不保证题号严格对应。
- 真实 API 的题目质量、跨设备与长期学习效果仍未验证。
