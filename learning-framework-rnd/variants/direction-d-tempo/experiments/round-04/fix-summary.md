# Round-04 修复摘要 — direction-d-tempo v0.2.4

- 版本：`0.2.4`（vendored core `1.0.2`，schema 1）
- 来源：`experiments/round-04/experience-S4-P3.md`（S4/P3，真实 API + 本地裸仓库模拟远程）
- 自检：`python tests\run_tests.py` → **43/43 通过**；`shared/check_variant.py` → **18/18**；`shared/vendor_core.py --check` → core 1.0.2 一致。

## 问题 → 修复 → 测试

| # | 报告问题 | 修复 | 回归测试 |
| --- | --- | --- | --- |
| 4 | 冲突 `sync` 退出 0；`status` 只显示 `committed-local`；指导语让学习者在干净树里解决冲突；没有 `diverged`/`unmerged`，也没有 `sync --recover` | (a) 升级 core 1.0.2 并由方向暴露：`status`/`--json` 的 `sync` 新增 `diverged`、`unmerged`、`state=conflict`；人类视图打印 ahead/behind 与未合并文件。(b) `sync`/`pause` 在 `report.state=conflict` 时退出 **3**；`print_sync` 解析 core 的 detail，打印真实冲突文件列表和“journal-only→sync --recover；状态快照→人工保留一侧”的指导。(c) `sync --recover` 调用 `GitSync.recover()`：journal 按 event id 并集合并、重建 dedupe、再推送；快照冲突 abort 并返回 blocking，不 force push。(d) `doctor` 分叉即 `git_divergence` 失败（退出 3）。(e) 删除本地 `extend_gitignore` 绕行；`init` 使用 core 的 `.gitignore`（锁/usage/sync-log）与 `.gitattributes`（`* -text`）。 | `test_sync_recover_unions_journals_and_snapshot_conflict_exits_3`（两克隆各追加不同事件→`sync --recover` 双方事件都在且 pushed；快照 `skills.json` 冲突→退出 3、输出文件名、status.diverged/state=conflict、doctor 退出 3）；`test_init_idempotent` 与 `test_gitignore_covers_usage_and_doctor_reports_true_state` 断言 `.gitattributes`/core ignore |
| 5 | 15 分钟候选在剩余 5 分钟时写成“超出剩余 5 分钟”，读起来像矛盾；5 分钟剩余时状态仍说预算不足 | (a) 拒绝理由改为“{M} 分钟活动本次放不下（剩余 {N} 分钟）；下次（约 {M} 分钟）”，不再出现“超出剩余”。(b) status 的“下次”说明区分：已排满 / 剩余确实小于下一项（约 M 分钟）/ 时间够但同模板或技能今天已覆盖；5 分钟够 5 分钟活动时 `when=now`。(c) `start` 在只有 fallback 时明确收尾，不启动无技能的 fallback 活动。 | `test_d_s1_budget_changes_choice`（kata-B 理由含“本次放不下”“下次（约 15 分钟）”，且不含“超出剩余”）；`test_status_next_matches_start_and_five_minute_wording`（5 分钟剩余时状态不写“不足下一项”，start 收尾不建 fallback） |

## 兼容性与状态变化

- `status --json.sync`：`{state, written, committed, pushed, branch, remote, ahead, behind, unmerged, diverged, clean}`；冲突时 `state=conflict`、`diverged=true`。
- `sync --recover` 失败（快照冲突）退出 3；成功（journal 并集 + push）退出 0，输出“recovered by union merge (N events)”。
- `init` 生成 `.gitattributes`（`* -text`）；`.gitignore` 由 core 1.0.2 负责；方向不再追加忽略规则。
- `doctor` 检查项新增 `git_divergence`（15 项）。

## 未关闭 / 观察项

- 自动恢复只合并 journal；`state/*.json` 快照冲突仍需人工选择，运行时不会猜测。
- 两个克隆的测试用本地裸仓库模拟远程；真实 GitHub 的认证/网络仍未验证。
- `pushed` 只在有远程且 ahead/behind=0 时为 yes；无远程时只到 `committed-local`。
- 本轮未改 `shared/`、其他方向、vendored core。
