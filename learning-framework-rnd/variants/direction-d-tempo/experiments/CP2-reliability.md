# CP2 · 记忆与可靠性证据（Tempo · direction-d-tempo）

- 变体：`direction-d-tempo` 0.2.6；vendored core 1.0.4（`runtime/CORE_VERSION`，由 `shared/vendor_core.py` 统一写入，未手改 core）。
- 环境：Windows（PowerShell 7）、Python 3.14.6、git 2.55.0.windows.3；全部测试使用独立临时目录，无网络、无第三方库。
- 时间：默认 `LEARNARK_NOW=2026-11-04T19:00:00+08:00` 模拟时钟；所有相关事件 `simulated:true`。**模拟时间只证明调度/SRS 逻辑，不证明真实记忆保持。**
- 入口：
  - `python tests/test_reliability.py -v`（本卡新增，25 例）
  - `python tests/run_tests.py`（原有 50 例）
  - `python shared/check_variant.py --variant variants/direction-d-tempo`
  - `python shared/vendor_core.py --check variants/direction-d-tempo`
- 证据产物：`_sandbox/checks/direction-d-tempo/check-result.json`（check_variant 生成，仓库外）；本卡不粘贴 stdout，失败信息见各用例断言文本。
- **工具链状态（2026-11-04 复测）**：主负责人已完成中央 re-vendor：D 现为 vendored core 1.0.4（torn-tail append 修复 + 凭据形状 SECRET_PATTERNS），`version-manifest.json` `core_version=1.0.4`，`vendor_core.py --check-all` 全绿。本卡以下计数均在 1.0.4 上复跑得到；core 文件未手改。

## 1. 测试矩阵（场景 × 结果 × 证据）

| # | 场景 / 断言 | 结果 | 证据（`tests/test_reliability.py`） |
| --- | --- | --- | --- |
| R1 | 截断 `schedule.json`（有 `.bak`）→ `status`/`start` 可读，`[恢复]` 说明恢复的文件 | PASS | `InterruptedStateTests.test_torn_snapshot_recovers_from_bak_and_reports` |
| R2 | 状态文件是合法 JSON 但不是对象（`[]`）→ 从 `.bak` 恢复；无 `.bak` 时退出码 3（不是 4） | PASS | 同上 |
| R3 | `project.json` 损坏（有 `.bak`）→ 恢复、主文件重写、`status` 输出说明 | PASS | `test_corrupt_project_json_recovered_and_reported` |
| R4 | journal 尾部半行 + `usage.jsonl` 半写 → 读正常；下一次写只修一次并记 `journal_repaired`；两条 attempt 都在 | PASS | `test_torn_journal_tail_usage_and_midfile_corruption` |
| R5 | journal 中间损坏 → 退出码 3 并报 `not valid JSON`，不静默跳过 | PASS | 同上 |
| R6 | `dedupe.json` 损坏 → 下一次写按 journal 重建并持久化；`doctor` 0 问题 | PASS | `test_corrupt_dedupe_index_is_rebuilt_on_next_write` |
| R7 | 原子写残留 `.tmp` 与残留锁文件 → `doctor` 警告但 0 问题，`status` 正常 | PASS | `test_atomic_write_residue_is_reported_not_fatal` |
| R8 | 模拟「journal 已追加、快照未保存」的崩溃 → 下一次 `start` 从 journal 补回卡片复习、等级、完成标记，不重复计数 | PASS | `test_interrupted_turn_credit_is_rebuilt_from_journal` |
| R9 | 同一 `say` 连跑两次 → `turn/attempt/card_reviewed/level_change/activity_completed` 不翻倍，会话正文不重复 | PASS | `DuplicateSaveTests.test_duplicate_say_is_idempotent` |
| R10 | 单轮内两条相同 card review、整轮重放 → step 只 +1；重复 create 只建 1 张卡、`merge_count=1` | PASS | `test_duplicate_attempt_and_card_review_items_do_not_double_apply` |
| R11 | `Document` CAS：基于旧版本保存 → `StaleWrite`，磁盘内容不变 | PASS | `StaleWriteTests.test_document_cas_rejects_stale_save` |
| R12 | `Store.save()` 整快照 CAS：另一个写者已提交 → `StaleWrite`，不覆盖新状态 | PASS | `test_store_save_rejects_snapshot_based_on_old_version` |
| R13 | 命令层过期写入 → 退出码 3，stderr 提示「已被另一个进程更新…请重跑」，快照版本不变 | PASS | `test_command_level_stale_write_reports_refresh_instead_of_overwriting` |
| R14 | 两个进程同时 `start` → 串行成功：2 个 item、2 个会话文件、2 条 `session_opened`/`schedule_decision`，决策与 item 一致 | PASS | `ConcurrencyTests.test_two_concurrent_starts_serialize_without_losing_items` |
| R15 | 两个进程同时 `say`（各 review 不同卡）→ 2 条 attempt、2 条 `card_reviewed`，两张卡 step 都 +1，等级受「同技能每天 +1」限制 | PASS | `test_two_concurrent_says_keep_both_attempts_and_card_reviews` |
| R16 | 持有项目锁 + `LEARNARK_LOCK_TIMEOUT=0.4` → 退出码 3，明确「另一个进程正在写/锁超时/没有写入」，无事件写入 | PASS | `test_project_lock_timeout_is_a_clear_exit_3` |
| R17 | 持有 journal 锁 + journal 尾部半行 → 写命令等待锁释放后再修复并成功，无事件丢失 | PASS | `test_journal_repair_waits_for_the_journal_lock` |
| R18 | journal-only 分叉 → `sync --recover` 按 id 并集、重建 dedupe、推送；A 侧提交仍是远程 HEAD 祖先（无 force push） | PASS | `GitReliabilityTests.test_journal_divergence_recovers_by_union_without_force_push` |
| R19 | 快照冲突 → `sync` 退出码 3、输出含 `skills.json`/`sync --recover`/「没有 force push」；本地提交与数据保留、变基已中止、远程保留另一侧 | PASS | `test_snapshot_conflict_exits_3_lists_files_and_keeps_local_commit` |
| R20 | 密钥/`.env`/usage/日志/锁文件不入库；HEAD 所有 blob 不含假密钥；`.gitignore` 覆盖这些模式 | PASS | `test_sync_excludes_secrets_locks_usage_and_logs` |
| R21 | 干净克隆 → 只凭项目文件恢复 skills 等级、卡片 step、handoff 与下一步；新进程 `start` 打印「上次停在哪」 | PASS | `test_clean_clone_restores_skills_cards_and_next_step` |
| R22 | 含 CRLF + 中文的产物跨 `sync`/克隆后字节完全一致（`.gitattributes * -text`） | PASS | `test_crlf_artifact_bytes_survive_sync_and_clone` |
| R23 | 模拟时钟 SRS：`again` → step−2、次日到期；连续 2 次 lapse → `leech` + 需改写；leech 卡被 <10 分钟预算排除；事件 `simulated:true` | PASS | `SimulatedClockTests.test_srs_due_leech_simulated_and_leech_filtered_from_short_budget` |
| R24 | 13 张到期卡 → 折叠 1 张 +3 天、剩余 ≤12；两份相同状态折叠结果一致；事件 `simulated:true` | PASS | `test_backlog_folding_is_deterministic_under_simulated_clock` |
| R25 | 两份完全相同的项目 + 同一模拟时钟 → `start` 输出逐字节一致，decision_id/chosen 一致 | PASS | `test_two_identical_copies_schedule_byte_identically` |
| R26 | 环境里放 `DEEPSEEK_API_KEY`（mock 模式）→ 项目所有文件、导出档案、HEAD blob 均不含该密钥 | PASS | `SecretsAuditTests.test_api_key_never_persisted_in_project_or_archive` |
| R27 | token 命名的产物可提交：`artifacts/token-budget.md`/`token-usage-notes.md` 入库；`.env`/`api.key`/`usage.jsonl` 仍被拦截，HEAD 无密钥（core 1.0.4） | PASS | `SecretsAuditTests.test_token_named_artifacts_are_committed_but_secrets_stay_blocked` |

合计：`tests/test_reliability.py` 25 例 → **25/25 通过**（core 1.0.4）；原有 `tests/run_tests.py` **50/50** 通过；`check_variant` **18/18**；`vendor_core --check` 通过。

## 2. 发现并修复的真实缺陷（均只改 `runtime/` 与测试）

| # | 缺陷 | 复现（修复前） | 修复 |
| --- | --- | --- | --- |
| D1 | `Store.save()` 调 `Document.save()` 不传 `expected_version`：两个进程/两个 Store 基于旧状态写会静默覆盖新状态（丢失卡片复习、等级） | 探针：旧 Store 先读、另一写者升级 skills，再 `store.save()` → 磁盘被旧值覆盖（level 9 写回） | `Store` 记录 load 时各文档 version，`save()` 用 CAS；`StaleWrite` → 命令层提示重跑 |
| D2 | 无项目级锁：两个 `start` 并发时都从同一快照调度，最终 2 个 `session_opened`/2 个会话文件但只剩 1 个 item（scheduler 结果被后写覆盖） | 探针：并行两个 `start` → items 长度 1、session_opened 2 | 所有非 `init` 命令持 `.learnark/project.lock`（可配 `LEARNARK_LOCK_TIMEOUT`）；锁超时退出 3 且不写任何文件 |
| D3 | `_apply_card_review` 先 `grade_card()` 改内存、后 `append()` 去重：同一轮两条相同 review 时 step 前进两次而事件只有 1 条；重放路径同样会双跳 | 探针：同一 `attempt_key` 调两次 → step 1→2，`card_reviewed` 1 条 | append 前检查 `card:review:<card>:<attempt>`，命中则跳过并说明「重复条目已忽略」 |
| D4 | `_merge_card` 同样先改 `merge_count` 后去重 | 同上模式 | 合并前去重，命中则只记 note |
| D5 | `repair_journal_tail()` 不加 journal 锁、用 `atomic_write_text` 整体替换：读到「半行」与重写之间别的进程追加的事件会被覆盖丢失 | 注入钩子（读后写前追加事件）→ `concurrent_event` 丢失 | 持 `journal.lock` 修复；原地 `truncate` 而非替换文件 |
| D6 | 状态文件是合法 JSON 但不是对象（如 `[]`）时 `Document.load` 抛 `ValueError` → CLI 落进通用异常，退出码 4（环境错误） | `skills.json=[]` → exit 4 "unexpected error" | 先尝试 `.bak` 恢复；否则抛 `LearnError` → 退出码 3，消息指向具体文件 |
| D7 | `project.json` 从 `.bak` 恢复是静默的（`read_json` 兜底但不报告、主文件不重写） | 损坏 project.json 后 `status` 正常但 `recovery` 为空，磁盘仍是坏文件 | `Store` 用 `load_json_state` 读取并写 `repairs`，`status`/`doctor` 可见，主文件被重写 |
| D8 | 崩溃/被拒绝的写入后，快照不追平 journal：卡片复习、等级变更、活动完成标记可能永久落后 | journal 有事件、快照 step=0/level=0 | `reconcile` 保守回放 `card_reviewed`、`level_change/decayed/l3_granted`、`activity_completed`（仅当快照明显落后；不追加事件） |
| D9 | `dedupe.json` 损坏只在内存重建，若下一次写入全是重复键则磁盘仍是坏文件 | 损坏 dedupe 后重复 `say` → 文件仍损坏，`doctor` FAIL | `reconcile` 检测索引损坏并追加带键事件，持久化重建 |

## 3. Core 缺陷（记录，未手改 `runtime/learncore`；由主负责人升 core 修复）

**C1（高，已在 core 1.0.4 修复）：`learncore/sync.py` 的 `SECRET_PATTERNS` 曾用 `token`/`secret` 匹配路径任意位置，导致合法学习产物被永久排除出同步。**

历史最小复现（core 1.0.2，供追溯）：

```powershell
python runtime/learn.py init --goal "复现" --dir <tmp>/proj
# 写入 artifacts/token-budget.md 与 artifacts/notes.md
python runtime/learn.py sync --project <tmp>/proj
git -C <tmp>/proj ls-files   # 1.0.2：notes.md 在；token-budget.md 不在
python runtime/learn.py doctor --project <tmp>/proj   # git_policy 只给 warning
```

core 1.0.4 已把 `SECRET_PATTERNS` 收窄为凭据形状（`.env`、`*credential*`、`*secret*`、`*.key/.pem/.p12/.pfx`、`tokens.json/txt/yaml/yml`、`access|api|auth|bearer token`、`*.log`、`usage.jsonl`、`sync-log.jsonl`、`*.bak/.lock/.tmp` 等）。本变体把它固定为回归用例 `test_token_named_artifacts_are_committed_but_secrets_stay_blocked`：token 命名的 md 产物必须入库，`.env`/`api.key`/`usage.jsonl` 必须继续被拦截，且 HEAD 不含假密钥——1.0.4 上通过。

**C2（低，core 1.0.4 仍存在，本变体已规避）：`Document.load()` 对「合法 JSON 但不是对象」抛 `ValueError`，不属于 `StateCorrupt/LearnError`，core 的 CLI 错误封装会退化成 exit 4。** 变体已包装为 `LearnError`；若其他方向直接用 `Document`，会遇到同样的错误分类问题。

## 4. 未覆盖 / 未验证（如实列出）

1. **真断电/任意点杀进程**未做；用「截断文件」「journal 已写、快照未保存」模拟。`TaskKill` 在不同写入阶段的概率性交织未测。
2. **journal 修复与并发 append 的竞态**只在修复前用注入钩子复现；修复后黑盒测试只能验证「修复期间其他进程等待锁」，无法确定性复现微秒级交错。
3. **Linux/macOS**：全部用例只在 Windows 跑；`fcntl.flock` 路径、`_fsync_dir` 逻辑未执行。
4. **网络文件系统/SMB/OneDrive 同步盘**上的 `msvcrt` 锁语义未测；跨机器同时写未测。
5. **真实 GitHub 远程**（凭证、网络中断、HTTP 代理）未测；只用本地裸仓库模拟分叉/推送失败。
6. **真实 LLM 模式**未测（全部 mock）。API key 泄露测试是 mock + 环境变量注入，未验证真实请求路径的日志。
7. **>2 个并发进程**未测（锁理论上串行，但未做 5–10 进程压力测试）；锁等待 20 秒上限只测了短超时。
8. **save 中途失败**（多文档：schedule 已写、skills 未写）没有回滚机制；`Store.save` 按文档原子但非跨文档事务。未测该场景下的快照一致性。
9. **大 journal**（10 万+ 事件）性能、seq 修复、union 合并内存占用未测。
10. **时钟回拨/时区混用/DST** 未测；`_parse` 对混合偏移量的时间戳只做字符串比较，未覆盖。
11. **CRLF 跨设备**只验证到「本地 bare → 同机 clone」；真实另一台 Windows/macOS 的 `core.autocrlf` 组合未测。
12. **`sync --recover` 的 snapshot 冲突**按设计不自动合并，只验证了拒绝与退出码；手工保留一侧的流程没有自动化测试（只能人工验证）。
13. **旧项目补提交**：core 1.0.4 修复后，新 `sync` 会把以前被跳过的 token 命名产物补进提交；但没有在「已经 sync 过、当时被跳过」的旧项目上实测补齐行为（预期只需再跑一次 sync），也未验证 remote 端历史清理。
14. **core 版本差异审计**：1.0.4 由主负责人中央 re-vendor（`vendor_core --check-all` 绿），本卡只验证了哈希一致与全套测试结果，没有逐行审计 1.0.3→1.0.4 的全部 diff。

## 5. 结论

- 本方向可交付：中断可恢复、重复保存不翻倍、双进程写串行/明确拒绝、过期写入被拒、Git 分叉有自动（journal）与人工（快照）两条路径、干净克隆可恢复、模拟时钟下 SRS 确定。
- 但「不丢记录」的边界是：**同一台机器、本地文件系统、mock 导师**。跨设备、真实网络与真断电仍是未验证风险。
- core 1.0.4 已修复 token 过度拦截（凭据形状匹配），并由本变体的回归用例固定；core 升级后 25/25 + 50/50 + check_variant 18/18 + vendor check 全绿。
- 结论仍是单机/本地文件系统/mock 导师；跨设备、真实网络与真断电未验证（§4）。
