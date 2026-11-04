# round-04 修复摘要（v0.2.3）

- 基线：`experience-S4-P3.md`（0.2.2，S4/P3 Git 同步与干净克隆恢复）
- 版本：`0.2.3` · core 1.0.2 · schema 1
- 验证：`tests/run_tests.py` → 73 tests OK；`shared/check_variant.py` → 18/18；`vendor_core.py --check` → 1.0.2 一致
- 远程说明：仍只用本机裸仓库模拟，真实 GitHub 未验证。

## 1. 分叉没有产品级恢复（问题 1，blocking）

- 根因：core 1.0.2 只自动并集 journal；`state/session.json`、`studio.json` 冲突时 `sync`/`sync --recover` 都退出 3，只留一句人工提示。
- 修复：新增 `runtime/atelier/recovery.py` 与命令 `learn sync --recover --prefer local|remote`。
  - **默认拒绝**：不带 `--prefer` 时只读地重放 rebase 以列出真实冲突文件，然后 abort，`written=no`，绝不写或 force push；报告保留 `branch`/`remote`。
  - `local`：journal 始终按事件 id 并集；state/session 冲突取本机（rebase 中的 `--theirs`），继续 rebase，普通 push。
  - `remote`：journal 并集；state/session 取远程（`--ours`），继续 rebase，普通 push；dedupe 从并集 journal 重建。
  - 日志写 `recover_choice`（prefer/chosen/branch）；标准输出逐项打印保留/覆盖的文件，详细报告写忽略文件 `.learnark/sync-log.jsonl`。
- 测试：`GitTests.test_recover_prefer_local_keeps_local_state_and_both_journals`（本地 session 保留、两 clone 事件均在、pushed）、`test_recover_prefer_remote_takes_remote_state_and_keeps_journal`（远程 session 生效、journal 仍并集）、`test_snapshot_conflict_exits_three_and_doctor_flags_diverged`（无 prefer 退出 3、列出 studio.json、`written=no`、branch/remote 有值）。

## 2. start 不是只读（问题 2）

- 修复：删除 start 的 stale-handoff 补写路径；start 只打开一次会话（`session_opened` + session 指针提交），不写 handoff/studio、不生造未决项；没有时间戳就不再声称“超过 7 天”。
- 测试：`FlowTests.test_start_is_read_only_and_does_not_invent_history`（两次 start：无 handoff、studio 字节不变、树干净、仅 1 个 session_opened）。

## 3. 周时长 60 倍（问题 3）

- 修复：`minutes_per_week` 内部按分钟存储；模板默认值按小时换算（12h→720）；显示统一 `format_weekly()`（init/start/plan/context/export）。60→“1 小时”，600→“10 小时”。
- 测试：`InitTests.test_minutes_per_week_uses_hours_for_display`（60/600 的 project.json 与显示）；`test_email_template_has_no_programming_residue` 断言 email 默认 180 分钟。

## 4. 同步状态/工作树

- `status` 继续显示 `diverged/unmerged`；`doctor` 分叉即失败；冲突/无仓库退出 3。
- 生成项目由 core 写 `.gitattributes`（`* -text`），`.gitignore` 覆盖 lock/usage/sync-log；已删除本方向的本地 gitignore 补丁。
- `pause`/`sync` 的事件在最终提交前写入，报告写忽略的 sync-log，避免“committed=yes 但树脏”。
- 测试：`test_pause_leaves_git_tree_clean_with_remote`、`test_two_clone_journal_divergence_is_union_merged`、`test_sync_without_remote_reports_honestly`、`InitTests.test_init_creates_contract_files`。

## 仍未关闭

- `--prefer` 是文件级选边，不做字段级语义合并；跨侧 capability 证据不会自动并集（dedupe 会重建）。
- 无 upstream 的 remote 或受保护分支推送失败时只能重试，不 force push。
- 真实 GitHub、跨设备、真实时间跨天恢复仍未验证。
