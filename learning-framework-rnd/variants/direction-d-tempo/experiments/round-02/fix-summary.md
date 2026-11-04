# Round-02 修复摘要 — direction-d-tempo v0.2.4

- 版本：`0.2.4`（vendored core `1.0.2`，schema 1）
- 来源：`experiments/round-02/experience-S2-P2.md`（独立体验者 S2/P2，2026-11-04，真实 API）
- 修复原则：只改本方向；不改 `shared/`、其他方向、vendored core；每个确认问题都有回归测试。
- 自检：`python tests\run_tests.py` → **43/43 通过**；`shared/check_variant.py` → **18/18**；`shared/vendor_core.py --check` → 一致。

## 问题 → 修复 → 测试

| 父任务 # | 报告问题 | 修复 | 回归测试 |
| --- | --- | --- | --- |
| 1 | 复述导师例子仍记 `correct=true/help_level=1`，`level_change.reason=independent-correct`，eval-harness L0→L1；纯提问轮记 `correct=true` 并建卡；`status` 看不到 help_level（报告 #1/#3） | (a) 复述检测：与上一轮导师文本做字符 bigram 覆盖率，≥0.72 且长度足够 → `echoed_example`、帮助等级抬到 ≥2、证据按受助、**不升级**，卡片 `good/easy` 降级为 `hard`；(b) 提问/求助检测（问号、吗/呢、给我/帮我/直接给等）→ `turn_without_attempt` + `attempt.correct=null`，不升级、不建卡；(c) `schedule.last_turn` 与 `skills[].last_help_level/last_evidence_kind`；`status` 人类视图新增“上次帮助/证据类型”和技能“上次帮助”列 | `test_echo_is_not_independent_correct`；`test_pure_question_turn_is_not_an_attempt`；`test_offline_e2e` 的 last_turn/help 断言 |
| 2 | 同一轮导师文字“对”而记录 `correct=false/again`；连续失败生成 3 张同 front 误解卡（12→18）；积压折叠静默 +3 天（报告 #2/#4/#5） | (a) `prose_verdict` 读导师文字，与机器块明确冲突 → `mentor_text_conflict`，**以机器块为准**，学习者记录只出现“以机器块为准 → 未判对”一个结论；(b) 卡片按 `skill + normalize(front)` 去重，重复 create/自动误解卡改为 `card_merged`（合并 back/tags，不新增卡、不占周配额）；(c) 积压折叠在 `start/say/due/plan/review/pause` 当场打 `[调整] …顺延 3 天…`（事件 `backlog_folded` 保留） | `test_text_conflict_uses_block_and_is_logged`；`test_duplicate_card_fronts_merge`；`test_backlog_fold_and_session_cap`（新增 `[调整]`/“顺延 3 天”断言） |
| 3 | `status` 显示 `recall_card · -` / `next-due`，与 trainer“写 20 行循环”、coach“写 10 条用例”三处冲突（报告 #7） | 下一步唯一来自调度器：今天排满或预算不足时用 `ignore_today` 投影出**具体**的下一项（真实 activity_id + skill + 分钟），`when=next_session`；`plan` 同理；导师 `next` 只显示“导师建议（只是建议、不排课；下一步以 status 为准）”；`status` 渲染不再出现 `· -`；`handoff` 的下一步也带具体 id | `test_budget_same_day_carry_and_remaining`（next 非 `next-due`、有 skill、无 `· -`、plan JSON 具体）；`test_offline_e2e`/`test_say` 的“导师建议”标签 |
| 4 | 5 分钟 recall 卡在导师说“时间到”后仍未完成，被下一次 `start` 静默换掉且照扣 5 分钟（报告 #6） | 导师文字含“时间到/时间用完/到此收尾”且未完成 → `time_boxed_incomplete`（`planned_min`、`elapsed_min`、mentor 原话片段）+ 学习者可读的一句“时间到但活动未完成…”；下一次 `start` 检测未完成活动 → `activity_replaced` + `[未完成]` 提示，`status.unfinished`、handoff“未完成：”都列出；不静默替换 | `test_time_boxed_incomplete_and_replacement_noted`；`test_d_s3_same_day_no_repeat` 新增 `[未完成]`/`activity_replaced` 断言 |
| core 1.0.2 | R3/R4 报告：分叉时 `sync` 仍退出 0；无 `.gitattributes`；手动 `.gitignore` 绕行 | `sync --recover` 暴露 `GitSync.recover()`；`sync` 冲突退出 3 并列出 `skills.json` 等冲突文件；`status`/`--json` 暴露 `sync.diverged`/`unmerged`；`doctor` 分叉即 `git_divergence` 失败；生成项目由 core 写 `.gitattributes`（`* -text`）与锁/usage/sync-log 忽略；删除 `extend_gitignore` 本地绕行 | `test_sync_recover_unions_journals_and_snapshot_conflict_exits_3`（两克隆追加不同事件 → `sync --recover` 双方都在且推送；快照冲突 → 退出 3 + 文件名；status diverged；doctor 退出 3）；`test_init_idempotent`/`test_gitignore...` 加 `.gitattributes` 断言 |

## 兼容性与状态变化

- `schedule.last_turn`：最近一轮的 help_level/correct/attempt_kind/evidence_kind/assisted/echoed/text_conflict/time_boxed。
- `schedule.today` 不变；`skills[]` 新增 `last_help_level`、`last_evidence_kind`。
- `status --json` 新增 `last_turn`、`unfinished`，`skills[]` 新增两个字段；`next` 现在保证有具体 `activity_id`/`skill`（除非整个项目没有候选）。
- `plan --json` 在“下次”模式下也返回具体 items；`due/plan --json` 保持纯 JSON（调整提示只出现在人类视图）。
- `session/*.md` 的“记录”不再写别名/回填/skill_signal 等内部术语（与 CLI 输出同过滤）。
- `status --json.sync` 新增 `unmerged`/`diverged`/`state=conflict`；`sync`/`pause` 在冲突时退出 3；`doctor` 在分叉时失败。
- 生成项目新增 `.gitattributes`（`* -text`）；`.gitignore` 由 core 1.0.2 统一忽略锁/usage/sync-log，不再由方向追加。
- 新增事件：`echoed_example`、`turn_without_attempt`、`mentor_text_conflict`、`card_merged`、`time_boxed_incomplete`、`activity_replaced`。

## 未关闭 / 观察项

- 复述/提问/文字冲突都是启发式（阈值与词表见 `version-manifest.json` 的 known_limits）；覆盖率与判定写入事件，可复核。
- 报告 #8（“这点先记下”未落库）、#9（错误标签重复/截断）、#10（初始 evidence_level=self_report 与“无自述”观感）、#11（到期卡 13/12 口径）、#13（首会无代码）不在本轮确认修复范围；#12 的内部术语泄漏已随记录过滤一并收敛。
- `time_boxed_incomplete` 仍按计划分钟计费（时间盒已占用），`elapsed_min` 只作记录，不改预算；若需按实际分钟计费需另立规则。
- `status` 的“下次”是投影，假设明天到期队列与今天相同，不是承诺。
- 真实 API 手测：start + 2 轮 say（deepseek-flash，配置 deepseek-chat）；首轮 1 次静默补块，次轮正常；`status.model` 正确。
