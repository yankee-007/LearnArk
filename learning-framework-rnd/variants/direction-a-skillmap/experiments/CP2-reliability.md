# CP2 · 记忆与可靠性（direction A / SkillMap）

- 日期：2026-11-04
- 运行时：vendored core 1.0.2；Windows；Python 3.14.6；git 2.55.0.windows.3
- 独立套件：`tests/test_reliability.py`（unittest、mock LLM、不联网、每例独立临时目录）
- 全量入口：`tests/run_tests.py`（含本套件的汇总用例）
- 证据目录：`experiments/CP2-reliability-evidence/`

## 1. 结果总览

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| 可靠性套件（修复后） | **24/24 通过** | `experiments/CP2-reliability-evidence/reliability-final.txt` |
| 全量回归（含可靠性套件） | **51/51 通过** | `experiments/CP2-reliability-evidence/run-tests-final.txt` |
| 共享冒烟检查 `shared/check_variant.py` | **18/18 ok** | `experiments/CP2-reliability-evidence/check-variant.txt` |
| `shared/vendor_core.py --check` | core 1.0.2 全部逐字节一致 | `experiments/CP2-reliability-evidence/vendor-core-check.txt` |
| 同一套件跑修复前运行时（commit `7abc1fa`） | **19/24，5 项真实失败** | `experiments/CP2-reliability-evidence/prefix-failures.txt` |

修复前失败的 5 项（即“先失败”证据）：`test_torn_journal_tail_is_repaired_before_append`、
`test_missing_trailing_newline_keeps_events_and_append_is_safe`、
`test_missing_map_snapshot_recovers_levels_from_bak`、
`test_missing_map_in_email_project_rebuilds_writing_map`、
`test_repeated_start_does_not_duplicate_session_opening`。修复后同一套件 24/24。

## 2. 测试矩阵（场景 → 结果 → 证据）

| ID | 场景 | 注入 / 操作 | 结果 | 证据（测试名；日志） |
| --- | --- | --- | --- | --- |
| R-T1 | 快照截断 | `map.json` 截到一半，保留 `.bak`，跑 `status --json` | 退出 0；从 `.bak` 恢复；A1 等级仍 L2；`repairs` 报 “recovered map.json from backup”；`doctor` 0 | `TornStateTests.test_truncated_map_snapshot_recovers_levels_from_bak` |
| R-T2 | 快照截断（计划） | `plan.json` 截到 1/3，跑 `status`/`start` | 退出 0；当前节点/阶段/20 分钟预算都恢复；`start` 正常继续 | `test_truncated_plan_snapshot_recovers_next_step` |
| R-T3 | 快照丢失 | 删除 `map.json`（保留 `.bak`） | 退出 0；从备份恢复 A1 等级 L2；`repairs` 说明；不留 L0 静默重置 | `test_missing_map_snapshot_recovers_levels_from_bak`；修复前日志 `prefix-failures.txt` |
| R-T4 | 快照损坏且无备份 | `map.json` 写成非法 JSON 且删 `.bak` | 退出 3；stderr 明确 `map.json` + `not valid JSON`；文件未被覆盖 | `test_corrupt_snapshot_without_backup_fails_clearly` |
| R-T5 | journal 尾行半写 | 在最后一条事件中间截断 45 字节 | 退出 0；只丢这一条未完成记录；`repairs` 报 journal 残留；随后 `start`/`say` 追加后每行都可解析 | `test_torn_journal_tail_is_repaired_before_append` |
| R-T6 | journal 末行缺换行 | 删掉文件末尾 `\n`（事件完整） | 完整事件保留（不丢）；追加后仍可解析，新事件在末行 | `test_missing_trailing_newline_keeps_events_and_append_is_safe` |
| R-T7 | journal 中间损坏 | 在第 3 行插入非 JSON | 退出 3；报 `line 3 is not valid JSON`，不静默丢弃 | `test_mid_journal_corruption_fails_loudly` |
| R-T8 | 锁残留 | 三个 `.lock` 写入死 pid 内容 | 全部命令照常执行；`doctor` 0 | `test_stale_lock_files_do_not_block_commands` |
| R-T9 | 重建用错模板 | email 项目删除 `map.json` 与 `.bak`，重建 | 地图恰为 W1/W6/W2/W3/W4/W5 六个写作节点，不混入 agent-dev 节点；`repairs` 说明“按模板重建” | `test_missing_map_in_email_project_rebuilds_writing_map` |
| R-D1 | 命令重放（检查点丢失） | 提交后把 `plan.json` 回滚到写前副本，再跑同一条 `say` | 退出 0；输出“已记录”；attempt/level_up 仍各 1；会话只有 1 个学习者块 | `test_replay_after_lost_plan_checkpoint_is_idempotent` |
| R-D2 | 同答案刷 drill | 同一答案连续 3 次 | attempt 仅 1；`drill_streak` 停在 1；阶段不前进 | `test_same_drill_answer_never_passes_twice` |
| R-D3 | 重复 `pause` | 连续两次收工 | 仅 1 条 `handoff` 事件；第二次数输出“已存在”；handoff 文件仍是 latest + 1 份归档 | `test_duplicate_pause_writes_one_handoff` |
| R-D4 | 重复 `start` | 同一会话连续 3 次 start | 会话中 `## 系统` 块数 == `session_opened` 事件数（2），不再出现“有块无事件”的重复开场 | `test_repeated_start_does_not_duplicate_session_opening` |
| R-C1 | 并发写 | 3 个 `subprocess` 同时 `say` 不同内容 | 3 个都退出 0；`turn_index` 恰为 1/2/3；3 条 `mentor_turn`；无重复 dedupe key；无 attempt；`doctor` 0 | `test_two_processes_writing_are_serialised` |
| R-C2 | 锁被活进程占用 | 测试进程持 `project.lock`，子进程带 `LEARNARK_LOCK_TIMEOUT=0.3` 执行 `say` | 退出 3；stderr 含 `another LearnArk process` 与 `state changed concurrently`；journal 无新事件；锁释放后同一命令成功 | `test_held_lock_reports_conflict_exit_3` |
| R-S1 | 文档级 CAS | `Document.save(expected_version=0)` 基于旧版本写 | 抛 `StaleWrite`；磁盘仍是新值/新版本；`update()` 正常推进版本 | `test_document_cas_rejects_stale_write` |
| R-S2 | 命令级过期写入 | 在 `Project.save_plan` 前注入“另一写入者”先改版本 | CLI 退出 3；输出 `state changed concurrently` + `changed since it was read`；另一写入者的 `session_goal` 未被覆盖 | `test_command_reports_stale_write_instead_of_overwriting` |
| R-G1 | 无远程 | 新项目直接 `sync` | 退出 0；`no-remote`；`committed: yes`；`pushed: no`；明确“无远程/未验证”；本地 1 条提交 | `test_sync_without_remote_reports_no_remote` |
| R-G2 | 仅事件流分叉 | 裸仓库 + 两克隆各追加事件并提交；一方先 push；另一方 `sync --recover` | 退出 0；`pushed: yes`；两条事件都在；远程旧 tip 仍是新 HEAD 祖先（无 force）；第三个克隆可见两条事件；`dedupe.json` 已重建 | `test_journal_only_divergence_recovers_by_union_and_pushes` |
| R-G3 | 快照冲突 | 两克隆改同一 `README.md`，一方先 push；`sync --recover` | 退出 3；列出 `file: README.md`；远程 sha 不变；本地提交保留；无 rebase 残留；`doctor` 非 0 且提示 `sync --recover` | `test_snapshot_conflict_exits_3_with_files_and_keeps_local_work` |
| R-G4 | 秘密/锁不进提交 | `.env`、`notes_token.txt`、`*.log`、`usage.jsonl`、`project.lock` 都放真实假 key | `git ls-files` 不含这些文件；`git log -p` 不含假 key/usage 字段；`export` 不泄密 | `test_secrets_usage_and_locks_are_never_committed` |
| R-G5 | 干净克隆恢复 | 裸仓库 → 新目录 clone → 新进程 `status`/`start`/`say` | 克隆直接定位 `A1` / `drill` / `A1-drill`；`start` 输出节点与阶段；`doctor` 0；新进程可继续写 | `test_clean_clone_recovers_next_step_in_a_new_process` |
| R-K1 | 模拟时间 | `LEARNARK_NOW`：到期前、到期当天、复习通过 | 到期前 0 个并给最近到期日；当天 1 个并进 review；通过后间隔 1→2、due +7 天；**所有事件 `simulated: true`** | `test_simulated_clock_schedules_review_and_tags_events` |
| R-K2 | 去重索引损坏 | 把 `dedupe.json` 写成非 JSON，再提交同答案 | 不重复计数（attempt 仍 1、streak 仍 1）；索引从 journal 重建且含 `attempt:` 键 | `test_corrupt_dedupe_index_is_rebuilt_without_double_counting` |

## 3. 发现并修复的真实缺陷（只改 runtime，未改 core）

| 编号 | 缺陷 | 影响 | 修复 | 证据 |
| --- | --- | --- | --- | --- |
| A-R1 | journal 尾行半写后，下一次 `append` 直接把新事件拼在残片后面 | 新事件当次即被静默吞掉；再下一次读取整份 journal 报 `line N is not valid JSON`，项目进入“每条命令退出 3”的不可用状态 | 新增 `sm_state.repair_journal_tail()`：在 `Context.__init__` 与 `init_project` 的第一次读写前，持 `journal.lock` 只丢弃最后一行的残片（完整末行只补换行），并在 `repairs`/`doctor` 说明 | R-T5/R-T6；修复前失败日志 |
| A-R2 | `map.json` 丢失（不是截断）时静默按模板重建；且 email 模板会误用 agent-dev 默认地图 | 等级、证据、复习日期全部静默清零，只留 `.bak` 不被使用；email 项目重建出 12 个 agent-dev 节点 + 6 个写作节点 | `Project._load_map()`：文件缺失或节点为空时优先用 **同模板** 的 `map.json.bak` 恢复并持久化；无备份才按当前模板重建，并写入 repair 说明 | R-T3/R-T9；修复前失败日志 |
| A-R3 | 重复 `start` 每次都把开场写进会话 markdown，但 `session_opened` 事件有幂等键 | 会话文件出现“有块无事件”的重复开场，交接/统计被污染 | `_system_turn()` 只在事件真正追加成功时写会话块；`write_switch_handoff()` 同样只在事件非空时落 handoff 文件 | R-D4；修复前失败日志 |
| A-R4 | `status`/`map`/`next`/`export` 会保存刷新后的状态，却不拿项目级锁 | 与 `say`/`sync` 并发时可能以 `StaleWrite` 退出 3（“读状态也会失败”），且没有统一的冲突提示 | `learn.py` 对所有非 `init` 命令串行化；新增 `LEARNARK_LOCK_TIMEOUT`（默认 20s）让锁冲突可测试、可配置 | R-C1/R-C2 |

附带修正：`doctor` 现在显示“状态修复”；重建地图的建议改为同时删除 `map.json` 与 `map.json.bak`（否则会被备份恢复）。

## 4. 核心（core 1.0.2）缺陷报告 —— 未改 core，提供最小复现

**C-1：`append_jsonl` 不保证文件以换行结尾，`read_jsonl` 的“容忍尾行”会把拼接后的新事件静默丢掉。**

复现（`experiments/CP2-reliability-evidence/core-bug-repro.txt`）：

```python
p.write_text('{"kind": "ok", "id": "ev_1"}\n{"kind": "torn", "id": ', encoding="utf-8")
read_jsonl(p)                      # 1 条（容忍残尾）
append_jsonl(p, {"kind": "next", "id": "ev_2"})
read_jsonl(p)                      # 仍是 1 条：ev_2 被拼进残行并被当作“尾行”丢掉
append_jsonl(p, {"kind": "next", "id": "ev_3"})
read_jsonl(p)                      # StateCorrupt: line 2 is not valid JSON
```

影响：任何在“被杀进程留下半行”之后继续追加的调用方都会丢一条事件，并把 journal 变成永久不可读。
建议 core 修法：`append_jsonl` 写入前若文件存在且末字节不是 `\n`，先补一个换行（或在 `Journal.append` 前调用同一 repair）。
本方向已在 runtime 侧以 `repair_journal_tail()` 规避，core 保持 1.0.2 不动；是否升 core 版本由主负责人决定。

## 5. 未测试 / 未验证（如实列出）

1. 真实 `SIGKILL`/断电发生在 `os.replace`/`fsync` 中间：本套件用“截断字节”模拟半写，没有杀真实写盘进程。
2. 持有锁的进程被强杀：只测了“锁文件残留但无持有者”和“活进程持锁”两种，没测持锁瞬间被杀的内核语义。
3. 真实 GitHub/网络：全部 git 场景用本地裸仓库；未验证认证、代理、推送超时、跨设备时钟偏差。
4. 三个以上克隆同时分叉、rebase 与 union merge 的交错；`sync --recover` 对非 journal 冲突只验证了单文件。
5. 并发 `init` 同一个新目录；以及 `init` 期间的锁（`init` 仍不拿项目锁）。
6. 网络盘（SMB/NFS）上的 `os.replace` 原子性与 `msvcrt.locking` 语义；本机 NTFS 之外未测。
7. journal 规模（1 万条以上）时的线性读取与每次命令的尾部修复开销；只测了数十条事件。
8. 真实 LLM 后端在持锁期间变慢/挂起：`say` 持锁调用 LLM，会把 `status` 等命令拖到 `LEARNARK_LOCK_TIMEOUT`（默认 20s）后退出 3；未做真实 API 压测。
9. 会话 markdown 的并发追加只在项目锁下间接验证；没有单独的大文件压力测试。
10. `sync --recover` 合并顺序按事件 `at` 再按 id 排序；时钟偏差下“真实先后”不保证一致，未验证。
11. 非 Windows 平台（Linux/macOS 的 `fcntl` 分支）未运行。
12. 真实学习者手写损坏（手工编辑 JSON、半删除 `.learnark/`）未逐一构造，只覆盖了程序化损坏。

## 6. 复跑命令

```powershell
cd learning-framework-rnd
python variants\direction-a-skillmap\tests\test_reliability.py          # 24/24
python variants\direction-a-skillmap\tests\run_tests.py                 # 51/51（含可靠性套件）
python shared\check_variant.py --variant variants\direction-a-skillmap  # 18/18
python shared\vendor_core.py --check variants\direction-a-skillmap      # core 1.0.2 一致
```
