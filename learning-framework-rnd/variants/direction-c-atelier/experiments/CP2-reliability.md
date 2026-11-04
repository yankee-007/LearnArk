# CP2 · 可靠性测试矩阵（direction C · Atelier）

状态：**完成（最终树）**
版本：direction-c-atelier **0.2.4** · core **1.0.4** · schema 1
记录时间：2026-11-04 13:25（Asia/Shanghai）
代码基线：commit `93a1681`（工作树干净；本轮之后未再改动 runtime）
环境：Windows 11 / Python 3.14.6 / git 2.55.0.windows.3 / 仅标准库；全部 `LEARNARK_LLM=mock`，无网络，远程均为本地裸仓库。

运行命令与最终结果：

```powershell
cd variants/direction-c-atelier
python tests/test_reliability.py            # 36 tests -> OK (122.062s)
python tests/run_tests.py                   # 80 tests -> OK (283.963s)
python ..\..\shared\check_variant.py --variant .   # 18/18 checks ok
python ..\..\shared\vendor_core.py --check .       # core 1.0.4: all vendored copies match
```

| 套件 | 用例数 | 通过 | 失败 | 证据 |
| --- | --- | --- | --- | --- |
| `tests/test_reliability.py` | 36 | 36 | 0 | `experiments/CP2-reliability-evidence/reliability-36.txt` |
| `tests/run_tests.py` | 80 | 80 | 0 | `experiments/CP2-reliability-evidence/run-tests-80.txt` |
| `shared/check_variant.py` | 18 | 18 | 0 | `experiments/CP2-reliability-evidence/check-variant.txt` |
| `shared/vendor_core.py --check` | 1 | 1 | 0 | 同上（末行） |

可靠性套件 36 个方法的分布：中断/半写/自检 11、重复命令 4、并发锁 4、strict 交接 4、git/密钥/克隆 9、上下文/模拟时钟 4。

## 1. 场景 × 结果 × 证据

| # | 场景 | 操作 | 期望 | 实测 | 证据（方法名，均在 `tests/test_reliability.py`） |
| --- | --- | --- | --- | --- | --- |
| 1 | 快照半写有 `.bak` | 截断 `studio.json`，`status --json` | 从 `.bak` 恢复，`recovered` 有记录，退出 0 | 通过 | `test_snapshot_recovers_from_bak_and_status_reports_it` |
| 2 | 恢复后继续 | 交接后损坏快照，`start` | 退出 0，输出最新 `handoff_id` | 通过 | `test_start_after_snapshot_recovery_reaches_the_handoff` |
| 3 | journal 尾部半行 | 追加无换行残行，再 `say` | 残行被截断并记 `journal_tail_repaired`；新事件可读、序号单调 | 通过 | `test_torn_journal_tail_is_ignored_and_repaired_before_next_append` |
| 4 | 完整事件缺结尾换行 | 追加完整 JSON 行（无换行）后 `say` | 补换行保留事件，不误删 | 通过 | `test_complete_event_without_trailing_newline_is_preserved` |
| 5 | 快照损坏无 `.bak` | 删 `.bak`，写 `{broken` | 退出 3、指名文件、无 traceback | 通过 | `test_corrupt_snapshot_without_backup_is_reported_as_state_error` |
| 6 | 合法 JSON 错形状 | 写 `[]` 后 `status` | 退出 3 状态错误，非“未预期错误” | 通过 | `test_wrong_json_shape_is_reported_not_a_crash` |
| 7 | doctor 遇损坏快照 | 删 `.bak`，写 `{broken`，跑 `doctor` | 输出 `[FAIL] studio_readable` 且继续输出其余检查，退出 3 | 通过 | `test_doctor_reports_corrupt_studio_with_fail_rows` |
| 8 | journal 领先快照 | 正常一轮后手工追加 `mentor_turn`（模拟崩在保存前） | `doctor` 报 `[FAIL] snapshot_drift`，退出 3 | 通过 | `test_doctor_flags_journal_ahead_of_snapshot` |
| 9 | 去重索引损坏 | 写坏 `dedupe.json` 再 `say` | 从 journal 重建，键集合一致 | 通过 | `test_corrupt_dedupe_index_is_rebuilt_from_journal` |
| 10 | 锁文件残留 | 预置项目/状态/journal 三个 `.lock` 后 `say` | 自动接管，不阻塞 | 通过 | `test_residual_lock_file_does_not_block_commands` |
| 11 | 过期写入 CAS | 旧 `Document` 版本 `save(expected_version=旧)` | 抛 `StaleWrite`，磁盘不被覆盖 | 通过 | `test_stale_document_write_is_rejected_by_cas` |
| 12 | 重复 `say` | 同文 2 次（含 `plan_change` 提案） | 1 turn/1 提案/plan 版本不变；2 个 `say_attempt` 不同 id | 通过 | `test_duplicate_say_does_not_double_turn_plan_or_evidence` |
| 13 | 重复 `switch` 同目标 | `switch coach` ×2 | 第 2 次 noop；1 份交接 | 通过 | `test_switch_to_same_mentor_twice_writes_one_handoff` |
| 14 | 重复 `pause` | 有回合后 `pause` ×2 | 1 份交接、1 个 `handoff` 事件 | 通过 | `test_pause_twice_does_not_duplicate_the_handoff` |
| 15 | 重复 `examine` | `examine` ×2 | 1 份交接、1 个 `exam_started`、pending 仍 open | 通过 | `test_examine_twice_does_not_duplicate_handoff_or_exam` |
| 16 | 并发两个 `say` | Popen 同时启动 | 串行成功；两条消息/两个 turn；序号单调 | 通过 | `test_two_concurrent_says_keep_both_messages_and_turns` |
| 17 | 并发 `say` + `pause` | Popen 同时启动 | 两边成功、1 份交接、消息不丢 | 通过 | `test_concurrent_say_and_pause_lose_nothing` |
| 18 | 锁超时 | 测试进程持 `project.lock`，`LEARNARK_LOCK_TIMEOUT=0.4` | 退出 3、明确提示、无部分写入；解锁后重试成功 | 通过 | `test_lock_timeout_is_reported_without_partial_writes` |
| 19 | 并发 `switch` 同目标 | 两个 Popen | 1 份交接、1 个 handoff 事件 | 通过 | `test_concurrent_switch_same_target_writes_one_handoff` |
| 20 | strict 缺字段 | 提案仅 `known`，`switch concept --strict` | 退出 3、无交接/不换人、列出 4 缺项 | 通过 | `test_strict_incomplete_handoff_exits_three_without_side_effects` |
| 21 | strict 可复现 | 同命令跑 2 次 | 两次均退出 3、无副作用、缺项/hash 一致 | 通过 | `test_strict_is_reproducible` |
| 22 | 默认合成交接 | 无提案 `switch concept` | 9+2 字段齐全、`degraded=false`、`handoff --check` 通过 | 通过 | `test_default_switch_composes_a_valid_handoff` |
| 23 | 显式补齐 | `--strict --fill-missing` | 成功且 `degraded=true`、`filled` 4 项、记 `handoff_degraded` | 通过 | `test_strict_fill_missing_is_explicitly_degraded` |
| 24 | journal 分叉 | 两克隆只让 journal 冲突 | `--recover --prefer local/remote` 均成功；并集保留双方事件 | 通过 | `test_journal_divergence_recover_prefer_local...` / `...remote...` |
| 25 | 快照分叉 | 两端都改 state，先 `sync` | 退出 3、列出 `studio.json`、远程 HEAD 不动、本地提交保留 | 通过 | `test_snapshot_conflict_exits_three_and_keeps_local_commit` |
| 26 | 恢复偏好 | 冲突后 `--prefer local/remote` | 各自保留选择侧会话；journal 双方保留；旧远程 HEAD 仍是祖先（无强推） | 通过 | 同上 / `test_snapshot_conflict_prefer_remote_takes_remote_state` |
| 27 | 恢复不选边 | `sync --recover` | 退出 3、`written=no`、HEAD/远程不变、无 `recover_choice` | 通过 | `test_recover_without_preference_refuses_without_writing` |
| 28 | `start` 清洁树 | `pause` 后 `start` | `git status --porcelain` 为空 | 通过 | `test_start_leaves_a_clean_worktree` |
| 29 | 密钥/锁/日志 | 造 `.env`、`usage.jsonl`、`*.lock`、`*.log` 后 `sync` | 均不在 `git ls-files`；`git grep HEAD` 无 `sk-`；提交的 project.json 无密钥 | 通过 | `test_secrets_locks_and_usage_logs_never_enter_commits` |
| 30 | 干净克隆恢复 | 裸仓库 → 新目录 → `status`/`start`/`studio` | 计划版本、`current_mentor=coach`、`handoff_id` 一致；5 位导师可见 | 通过 | `test_clean_clone_restores_plan_mentor_and_handoff` |
| 31 | 无远程 | `sync` | `no-remote` + `written=yes/committed=yes/pushed=no`；本地提交存在 | 通过 | `test_no_remote_is_explicit_and_commit_is_local` |
| 32 | 上下文预算 | 注入超长 handoff/笔记 | `chars ≤ 6000`、无 `journal/full`、不读他人笔记 | 通过 | `test_context_budget_is_enforced_with_hostile_inputs` |
| 33 | examiner 隔离 | coach 笔记/提示/`do_not_redo` 放哨兵串 | 上下文中无哨兵；sources 无 coach 笔记；excluded 含 coach 笔记与 `handoff/what_tried` | 通过 | `test_examiner_context_never_opens_coach_private_notes` |
| 34 | CLI manifest | `examine` 后 examiner 回合 | manifest `chars≤6000`；sources 无 coach 笔记；excluded 有 | 通过 | `test_cli_context_manifest_is_bounded_and_examiner_isolated` |
| 35 | 模拟时钟 | `LEARNARK_NOW=2026-11-20T19:00+08:00` 走 init/say/pause；推进到 11-23 | 所有事件 `simulated=true`/`at` 前缀正确；`review_due=11-22`；`status` 显示 `2 d ago`；`start` 恢复 | 通过 | `test_simulated_clock_tags_events_and_drives_schedule` |
| 36 | 全量套件稳定性 | 36 个方法在 core 1.0.3 与 1.0.4 上各跑一次；并发组额外连跑 3 次 | 每次均 36/36；并发组 3/3 稳定 | 通过 | `reliability-36.txt` |

## 2. 缺陷与修复状态（D1–D8 全部关闭）

| ID | 缺陷 | 最小复现 | 修复位置 / 状态 |
| --- | --- | --- | --- |
| D1 | journal 尾行残写会毒化下一次追加（core 1.0.2 只在读取时容忍尾行） | `init` → `say` → 向 `events.jsonl` 追加无换行 `{"id":"ev_torn"` → 再 `say`：退出 3 或新事件静默丢失 | **core 1.0.3** 在 `fsutil.append_jsonl` 追加前截断残行；变体 `ProjectJournal` 先做更保守的修复（完整 JSON 尾行只补换行、不截断）并记 `journal_tail_repaired`。保留变体层是因为 core 会误删“完整但缺换行”的事件且无审计事件；**已关闭**（core 回归测试 + 本套件 #3/#4） |
| D2 | journal 已落盘、`dedupe.json` 未写时重试会重复计数 | `Journal.append(dedupe_key="k")` 后把索引覆盖为 `{}`，同 key 再 append 得到第二个事件 | `atelier/state.py` `ProjectJournal._load_index` 每次与 journal 对账，journal 胜出；**已关闭**（#9） |
| D3 | 无跨进程项目写锁 | 两个 Popen 同时 `say` → 后写者 `StaleWrite` 丢消息；两个 `switch coach` → 2 份交接 | `atelier/state.py` `project_lock` + `commands.main()` 写命令整段加锁（默认 60s，`LEARNARK_LOCK_TIMEOUT` 可调）；**已关闭**（#11、#16–#19） |
| D4 | 重复 `pause` 写第二份交接 | `init`→`say`→`pause`→`pause` | `handoff` 载荷带 `session_id`；`cmd_pause` 对已结束且最新自交接匹配的会话早退；**已关闭**（#14） |
| D5 | 重复 `examine` 每次重写交接 | `init`→`examine`→`examine` | `pending_exam.opened_session/opened_turn` 与当前会话一致时跳过；**已关闭**（#15） |
| D6 | 合法 JSON、错形状快照按“未预期错误”退出 4 | 删 `.bak`，写 `[]`，`status` | `atelier/state.py` `load_with_repair` 把 `ValueError` 转 `StateCorrupt`；**已关闭**（#6） |
| D7 | `doctor` 遇损坏 `studio.json` 中断，不输出检查表 | 删 `.bak`，写 `{broken`，`doctor` | `cmd_doctor` 捕获 `LearnError`，新增 `[FAIL] studio_readable` 后继续跑其余检查；**已关闭**（#7） |
| D8 | journal 已记 turn、快照未保存时 `doctor` 不报漂移 | 正常一轮后手工追加 `mentor_turn` 再 `doctor` | `cmd_doctor` 比较 `mentor_turn` 事件数与 `studio.mentors[*].turns`，新增 `[FAIL] snapshot_drift`；**已关闭**（#8） |

附带修复的工具问题：`version-manifest.json` 曾被文本工具写成带 UTF-8 BOM，导致 `json.loads` 直接失败（80 测试里表现为 version 测试 ERROR）。已按字节剥离 BOM（保留原格式），并在最终树上复跑通过。`START_HERE.md` / `curriculum/agent-dev.md` 仍带 BOM（Markdown，不影响运行）。

## 3. 未覆盖 / 剩余风险

- **真实杀进程/断电**：半写用截断文件模拟；未在写盘瞬间 Kill 进程，Windows 目录 fsync 由 core 跳过，断电持久性未证明。
- **并发规模**：只测 2 进程；未测 5+ 进程、真实 API 长回合（30s+）下的 60s 锁等待；`sync` 与 `say` 同时运行的组合未单独测。
- **性能**：`ProjectJournal._load_index` 每次 append 全量读 journal（对账换正确性），10 万事件级未压测；尾行检查已优化为只读最后 1 字节。
- **跨设备 git**：仅本地裸仓库；未测 GitHub 凭据、分支保护拒绝 push、两真实设备同时推。
- **网络盘/SMB**：`msvcrt.locking`/`flock` 在 SMB/NFS 上的语义未验证。
- **损坏组合**：`.bak` 同时损坏、只读文件系统、磁盘满未测。
- **历史泄密**：只审计当前 `HEAD` 的文件与内容，未扫描全部历史 commit。
- **Python 3.10**：本机只有 3.14，未在最低版本实测。
- **D8 误报边界**：手工恢复 plan/state 后 journal 与 studio 计数可能合法不一致，`snapshot_drift` 会报 FAIL（当前提示人工核对，未做白名单）。

## 4. 结论

v0.2.4 / core 1.0.4 最终树上，可靠性 36/36、功能 80/80、契约冒烟 18/18、core 逐字校验 1/1，全部通过。D1–D8 均已关闭；D1 的通用部分已升入 core 1.0.3，变体保留更保守的尾行处理与去重索引对账。剩余风险集中在“真实断电/多进程规模/非本地远程”三类，未做真机验证，不追认为已通过。
