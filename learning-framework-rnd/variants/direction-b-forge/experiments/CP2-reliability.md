# CP2 · Forge 可靠性实验矩阵

- 方向：`direction-b-forge` 0.2.4｜vendored `learncore` 1.0.4｜schema_version 1
- 环境：Windows，Python 3.14.6，Git 2.55.0.windows.3，离线 mock LLM，本地裸仓库
- 结论日期：2026-11-04（shared/core-v1 于 13:06 升级到 1.0.4，B 已由主负责人统一 re-vendor）
- 复跑命令：
  ```powershell
  python tests/run_tests.py
  python tests/test_reliability.py -v
  python ..\..\shared\check_variant.py --variant .
  python ..\..\shared\vendor_core.py --check .
  ```
- 本次实测：完整回归 **42/42 PASS**；可靠性套件 **27/27 OK**（约 105 s）；`check_variant` **18/18**；`vendor_core --check` **core 1.0.4 全部一致**。

## 1. 场景 × 结果 × 证据

| # | 场景 | 预期 | 结果 | 证据（`tests/test_reliability.py::...`） |
| --- | --- | --- | --- | --- |
| 1 | 快照被截断、`.bak` 可读 | `status` 恢复且不丢作品 | 自动恢复，stderr `[恢复]`，doctor 0 | `test_snapshot_torn_write_recovers_from_backup` |
| 2 | journal 尾行半写（无换行）后再写 | 丢弃半行，新事件完整 | 新事件落盘，去重键存在 | `test_torn_journal_tail_is_ignored_and_next_append_survives` |
| 3 | journal 尾行非法但有换行 | 同样丢弃，不造成中部损坏 | 通过 | 同上（阶段 b） |
| 4 | 快照损坏且无 `.bak` | 明确报错、退出 3 | `not valid JSON`，无 traceback | `test_corrupt_snapshot_without_backup_reports` |
| 5 | 事件已落盘、作品快照未落盘（模拟 kill 窗口） | 下次读取重放作品 | 自动补回并标 `recovered` | `test_event_written_without_snapshot_is_replayed` |
| 6 | 评审事件已落盘、`reviews.json` 丢失 | 重放评审，不重复问 LLM | 通过 | `test_review_written_without_snapshot_is_replayed` |
| 7 | defense 快照落后于 journal | 重放最新 attempts/passed | M1 通过、ok_count=3 | `test_defense_snapshot_behind_journal_is_replayed` |
| 8 | 缺口已关闭但 `gaps.json` 是旧版 | 最新 journal 状态优先 | closed 不复活 | `test_closed_gap_snapshot_behind_journal_is_replayed` |
| 9 | 会话快照轮次落后 | 推进 turn_index，避免去重吞新回合 | 回合序列 1,2,3,4 | `test_session_turn_counter_behind_journal_is_replayed` |
| 10 | 事件找不到对应作品文件 | 报告「找不到」，不静默 | status 说明，doctor 退出 3 | `test_unrecoverable_event_is_reported_not_silent` |
| 11 | `dedupe.json` 损坏 | 从 journal 重建 | 键完整、无重复 | `test_corrupt_dedupe_index_rebuilds` |
| 12 | 同 sha 作品连续登记 3 次 | 1 条作品、1 个事件 | 通过 | `test_duplicate_artifact_add_is_idempotent` |
| 13 | 同一作品连续 review 3 次 | 1 次评审、分数不变 | 通过，事件携带完整评审快照 | `test_duplicate_review_does_not_rescore` |
| 14 | 同一 defense 连续 say 3 次 | 只通过 1 次、不双计 | `milestone_passed`=1，M2 active | `test_duplicate_defense_does_not_double_pass` |
| 15 | 两进程并发登记不同作品 | 串行成功、两件都在 | 2/2，doctor 0 | `test_concurrent_artifact_adds_keep_both` |
| 16 | 两进程并发登记同一作品 | 只算一次 | 1 条、1 事件 | `test_concurrent_duplicate_artifact_add_counts_once` |
| 17 | 两进程并发 `say` | 串行，两个回合都在 | turn_index=2，无幽灵回合 | `test_concurrent_says_serialize` |
| 18 | 并发 `artifact add` + `review` | 不丢作品、评审一致 | 2 件、1 评审，doctor 0 | `test_concurrent_artifact_add_and_review` |
| 19 | 锁被另一进程持有 | 明确锁错误、退出 3、不写状态 | 通过，释放后 status 0 | `test_lock_timeout_is_clear_and_non_destructive` |
| 20 | Document 旧版本保存 | `StaleWrite`，不覆盖新值 | 通过 | `test_document_cas_rejects_stale_save` |
| 21 | 命令级旧状态保存 | 退出 3 + 刷新提示；已落事件可重放 | 3 件作品最终齐全 | `test_command_stale_write_aborts_and_journal_replays` |
| 22 | journal-only 远程分叉 | `sync --recover` 保留双方事件、不 force push | pushed=yes，seq 连续，c1 是 HEAD 祖先 | `test_git_journal_divergence_recovers_without_force` |
| 23 | 快照冲突 | 退出 3、列出文件、保留本地 | 通过；远程 HEAD 不变；`--recover` 仍 3 | `test_git_snapshot_conflict_exit3_lists_files_and_keeps_local` |
| 24 | 无远程 | 本地提交成功并明确 `no-remote` | 通过 | `test_git_no_remote_reports_and_commits_locally` |
| 25 | 干净克隆恢复 M1（作品+评审+防御） | 新进程只凭文件恢复 | M1 passed、M2 active、sha 不变 | `test_clean_clone_recovers_m1_evidence_and_crlf_safe_sha` |
| 26 | 密钥/锁/usage 日志不提交 | 提交树与历史均无 | `git grep` 无命中 | `test_git_commits_no_secrets_locks_or_usage_logs` |
| 27 | 模拟时钟 | 事件标 `simulated`，门控不变 | 模拟/真实两项目结果一致 | `test_simulated_clock_marks_events_and_keeps_gating` |
| 28 | 本地秘密审计 | 状态、journal、导出均不含 key | 通过 | `test_secret_never_written_to_project_state` |

补充回归：`tests/run_tests.py` 的 42 项覆盖 B-S1..S6、email 模板、review/clamp、gap 关闭路径、同步/克隆、round-01..06 修复，全部通过。

## 2. 修复的真实缺陷（都在 `runtime/`，未改 `learncore/`）

1. **并发/中断会永久丢作品**：`artifact add` 先写 journal、后写 `artifacts.json`；两个进程各登记不同作品时，后写者 CAS 失败退出 3，但事件已存在，重试只命中 dedupe，作品永远进不了快照。
   - 修复：`Project.write_lock()` 让每个项目的命令串行；`load_state()` 增加 journal 重放（作品、评审、防御、缺口、会话轮次），CAS 失败后的事件可在下一次读取补齐。
2. **journal 尾行会吞掉下一个事件**：1.0.4 之前 core 的 `Journal.append` 在未写完的尾行后直接追加，新事件与半行粘成一行并被 `read_jsonl` 当尾行忽略；若半行带换行，则变成中部损坏。
   - 修复：`Project._prepare_journal_for_append()` 在写前丢弃未写完的尾行；完整 JSON 只缺换行则补换行。core 1.0.3 已修「缺换行」的情况，本方向的额外处理覆盖「非法但带换行」的尾行。
3. **事件已写、索引未写的窗口**：崩溃后 dedupe 索引缺键，重试会重复计数；core 1.0.4 仍未修。
   - 修复：写前从 journal 合并缺失的去重键（`_repair_dedupe_index`）。
4. **快照落后于 journal 的实体更新**：defense 第二次判定、gap 关闭、session turn 推进只更新已有对象；旧快照会复活旧状态。
   - 修复：重放「最新事件」并更新已有实体（不只补缺失实体）。
5. **事件不足以修复时不可见**：作品文件丢失时 doctor 只看到快照正常。
   - 修复：doctor 对账 journal/作品/评审/防御，缺快照即报错；status 打印恢复说明。
6. **可恢复性元数据不足**：评审/防御/缺口的 journal 只存摘要，重放会丢 note、问题与答案。
   - 修复：`review_recorded`、`defense_recorded`、`gap_*`、`artifact_added` 写入完整对象/目标路径与 assisted_level。
7. **凭据模式会误伤合法产物 / 漏掉真实凭据形状**：core 1.0.4 已把 `SECRET_PATTERNS` 改为按文件名/凭据形状匹配；本方向提交树测试覆盖 `.env`、`usage.jsonl`、`*.lock`、`*.bak` 不进入提交，`artifacts/token-budget.md` 这类合法产物不受影响（由 core 1.0.4 保证）。

## 3. core 缺陷报告（core 1.0.4 现状）

### C1（1.0.3 已修）：`Journal.append` 不修复缺换行的尾行

最小复现（对 1.0.4 之前的 core；现已被 `append_jsonl` 的残尾修复覆盖）：

```python
from learncore.events import Journal
j = Journal(tmp / "events.jsonl", tmp / "dedupe.json")
j.append("first", {"n": 1})
with open(j.path, "a", encoding="utf-8") as fh:
    fh.write('{"torn": ')
j.append("second", {"n": 2})          # 1.0.4 返回 event 且两条都在；旧版只留 first
print([e["kind"] for e in j.all()])
```

残余边界：若尾行**带换行但 JSON 非法**，1.0.4 的 `append_jsonl` 只看最后一个字节是否为 `\n`，不会清理；下一次 append 后该行变成中部损坏。本方向 `_prepare_journal_for_append()` 同时覆盖此形态。

### C2（1.0.4 仍开放）：事件与去重索引非原子

```python
j.append("dup", {}, dedupe_key="k")
json.dump({}, open(j.index_path, "w", encoding="utf-8"))  # 模拟索引写前崩溃
j.append("again", {}, dedupe_key="k")                     # 同一个 key 又写入一次
print(j.integrity()["problems"])  # 1.0.4 仍为 ['duplicate dedupe keys in journal']
```

期望：启动/追加前用 journal 重建缺失键；或索引写入与事件写入同锁同事务。本方向已在 `Project._repair_dedupe_index()` 做了读侧修补，但 core 层仍有此窗口。

## 4. 未覆盖 / 仍是风险（如实）

- **没有真实 SIGKILL/断电注入**：用「事件已落盘、快照缺失」「截断文件」「恢复旧快照」模拟，未在写系统调用中间杀进程；真实磁盘写序/缓存行为未验证。
- **没有真实 GitHub/多设备**：只用本地裸仓库与两个本地克隆；凭据、网络中断、GitHub 保护分支、跨时区未验证。
- **`init` 并发未加项目锁**：命令并发测试覆盖写命令，未覆盖两个 `init` 同时指向同一目录。
- **journal 中部损坏**：只保证尾部可修；中部损坏会退出 3，需人工换 journal，未实现自动截断/重写。
- **快照冲突的人工选择未自动化**：`sync --recover` 只合并 journal；`state/*.json` 冲突仍要人决定保留哪版。
- **作品原件丢失**：只有 `source_path` 仍存在且 sha 匹配才能自动回拷；否则需要用户重新 `artifact add` 或从备份恢复（doctor/status 会报，不静默）。
- **模拟时钟不覆盖调度**：Forge 没有按时间排程的复习，测试只证明时间戳与 `simulated` 标记、门控不受影响。
- **真实 LLM 的非确定性**：评审分数漂移、超长回复、token 用量仍未在真 API 下做可靠性复测；离线 mock 不能代表教学质量。
- **Windows 环境差异**：杀毒/OneDrive/网络盘的文件锁与 flush 行为、Windows 与 Linux 跨平台互操作未测；锁超时默认 60 s，长事务未压测。
- **秘密审计是模式匹配**：core 1.0.4 已按文件名/凭据形状匹配（`.env`、`*credential*`、`*secret*`、`*.key/*.pem`、`tokens*`、`usage.jsonl`、`sync-log.jsonl`、锁/临时文件），本方向测试额外覆盖 `.env`、`usage.jsonl`、`*.lock` 与 `sk-` 串；编码、拆分、历史深处的秘密仍需人工 `git grep` 与轮换。
- **性能**：每次 `load_state` 重放整份 journal；大项目（数万事件）未做基准，可能拖慢 `status`。
