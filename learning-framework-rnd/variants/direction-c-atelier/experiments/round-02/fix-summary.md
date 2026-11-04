# round-02 修复摘要（v0.2.2）

- 基线：`experience-S2-P2.md`（0.2.1，真实 API，S2/P2）
- 修复版本：`0.2.2` · core 1.0.2
- 验证：`tests/run_tests.py` → 66 tests OK；`shared/check_variant.py` → 18/18；`vendor_core.py --check` → 1.0.2 一致
- 原则：**正确性由 examiner 独立判定**；导师文本只是观察，运行时按证据与事实记录。

## 1. 错误答案被判对并升级（重要，完整性问题 1）

- 根因：非 examiner 的 `attempt.correct=true` 会走 observed 升级路径。
- 修复：`evidence.py` 删除非 examiner 的升级分支；任何非 examiner 尝试只写 `practice_attempt`（`correct=null`、`claimed_correct`）与 `observed` 证据（`counts_for_level=false`）。只有 examiner pass 写 `verified` 并升级。导师正文“夸奖+纠正”同时出现时记 `mentor_verdict_conflict`，按未通过/无证据处理，`mentor_turn`/session 里非 examiner 的 `attempt.correct` 也归一为 null。
- 测试：`EvidenceTests.test_coach_correct_claim_is_practice_only`、`test_coach_conflict_marks_not_correct`、`test_examiner_pass_writes_verified`。

## 2. 机器块缺失丢回合信息（问题 2）

- 修复：首轮解析失败时静默重试一次（记 `mentor_update_retried`，含首轮 sha/原因/是否修复）；仍失败才记 `mentor_update_invalid`。学习者只看到“本轮没有形成可记录的证据”，不再出现“机器块/字段名”。`status` 新增 `recent_turns`/`last_turn`，帮助等级为空显示「未标注」。
- 测试：`test_missing_machine_block_is_repaired_silently`、`test_invalid_machine_block_retries_once_then_hides_jargon`（后者断言 stdout 无“机器块”、status 含“未标注”）。

## 3. status 看不出哪里不会（问题 3）

- 修复：`record_misconceptions` 从 `update.misconception` 与含纠正标记的导师句子提取误解，按关键词映射技能模块（RAG/记忆→`w3-memory`，工具→`w2-tools`，评测→`w4-eval`，循环→`w1-agent-loop`）；写 `misconception_observed`、节点 `misconceptions` 与 `last_fail{source_event}`；`status` 增加「薄弱/误解」区，`--json` 增加 `weaknesses`。
- 测试：`test_misconception_is_recorded_as_weakness_with_source`。

## 4. 证据指向不存在的产物（问题 4）

- 修复：`apply_evidence` 先解析并校验 `artifacts/<activity>.md`（或导师声明的 `artifact`）；缺失记 `evidence_artifact_missing`，证据 `artifact=null`、`artifact_verified=false`，不再写不存在的路径；存在时记录真实相对路径。
- 测试：`test_evidence_artifact_must_exist`（遍历全部证据，路径为 null 或真实存在）。

## 5. 下一步冲突（问题 5）

- 修复：coach/concept 文本或 `next` 请求 examiner 独立题/验证时，自动 `new_exam`（`exam_requested`）；`next_step` 统一返回 examiner；`status`/`start`/`pause` 的命令统一为 `learn.cmd examine`；导师上下文增加「运行时排程（权威）」块。
- 测试：`FlowTests.test_coach_exam_request_creates_pending_exam_and_examine_next`（pending_exam=open、status.next.command=examine、start 同一命令）。

## 6. 交接截断与虚构前情（问题 6/8）

- 修复：`_short` 在句子/标点边界截断并保留 `…`；`compose_what_tried` 输出原始条目后由 compose 统一截断并记 `handoff_truncated`（含单条超长）；`what_tried` 仅来自 session/journal。提示词增加“不要虚构上一轮的尝试、报错或产物；不知道就说不知道”。
- 测试：`ContextTests.test_long_what_tried_is_cut_on_a_boundary`（≤120、以…结尾、前一字为标点）、`test_prompt_forbids_inventing_history_and_context_has_no_fake_error`。

## 7. 诊断不触发交接（问题 9）

- 修复：提示词要求 planner 诊断出误解时给 `handoff{auto:true,to_hint}`；运行时兜底：planner 回合出现 `misconception_observed` 且无 auto 提案时，记 `diagnosis_handoff_requested` 并自动切到 concept/coach，交接由运行时合成。
- 测试：`FlowTests.test_planner_diagnosis_triggers_handoff`（当前导师变成 concept/coach、handoff 必填字段完整、mentor_switch.source=diagnosis）。

## 8. core 1.0.2：分叉恢复与同步状态

- 修复：re-vendor core 1.0.2；`learn sync --recover` 暴露 `GitSync.recover()`；普通 `sync` 在 rebase 失败后自动尝试 journal 并集恢复，快照冲突中止并输出真实冲突文件。`status` 增加 `sync.unmerged/diverged`，`doctor` 分叉即失败，冲突返回 3。
- 生成项目由 core 写 `.gitattributes`（`* -text`），.gitignore 覆盖 lock/usage/sync-log；删除本方向旧的 `EXTRA_GITIGNORE` 补丁，`.gitattributes` 纳入提交 allowlist。
- 测试：`InitTests.test_init_creates_contract_files`（属性/忽略项）、`GitTests.test_two_clone_journal_divergence_is_union_merged`（两 clone、事件并集、pushed、`--recover`）、`test_snapshot_conflict_exits_three_and_doctor_flags_diverged`（退出 3、列出 studio.json、status diverged、doctor 失败）。

## 仍未关闭

- 关键词/文本启发式（误解、冲突、考核请求、诊断交接）可能漏判或误触发，需要真实数据校准。
- 非 examiner 永不升级，若 examiner 一直未被安排，进度会停在 0（这是有意的证据纪律）。
- artifact 只校验存在性，不校验内容；`do_not_redo` 归档/退役、30 回合预算曲线仍未实现。
