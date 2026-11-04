# round-04 修复记录 — SkillMap v0.2.3

- **输入**：`experiments/round-04/experience-S4-P3.md`（独立子 Agent 体验，S4 / P3 Mia，真实 LLM，8 次 `say`，本地裸仓库模拟远程）
- **版本**：0.2.2 → **0.2.3**；core 1.0.2（重新 vendor；`GitSync.recover()`/`status().diverged`/`status().unmerged`/`.gitattributes` 均由 core 提供）
- **范围**：只改 direction-a 自己的 `runtime/`、`mentors/`、`design.md`、`tests/` 与文档；未改 `shared/`、其他方向、vendored core。
- **结论**：报告中的克隆恢复矛盾、冲突恢复死循环（阻塞）、口头通过无证据全部修复；`status`/`doctor` 现在会报分叉。

## 问题 → 修复 → 测试

| # | 报告问题 | 根因 | 修复（文件） | 测试 | 结果 |
| --- | --- | --- | --- | --- | --- |
| E | 克隆恢复后运行时是 check，examiner 却要求补交 apply 的变式 | 导师上下文没有“本轮唯一活动”的硬约束；`runtime_next` 只给下一步 | 协议新增：本轮只能围绕 `{activity_id}` 出题/追问，不得要求上一阶段变式或补交；`runtime_next` 已在 context 首部（v0.2.2）（`sm_mentors`、`sm_engine`） | `test_clone_resume_examiner_context_has_check_activity` | 克隆后 context 含 `"activity_id": "A1-check"`，system prompt 含 `A1-check` 与“本轮只能围绕”；`start` 只出现 A1-check |
| F | 冲突恢复是死循环：提示“手动 resolve”但 `git status` 无冲突文件；重试 1/1→2/1；`status` 说 clean、`doctor` 全绿 | `sync` 先追加事件再盲目 rebase；产品层没有分叉检测与恢复入口；`status` 只看工作区 | 采用 core 1.0.2：`sync --recover` 调 `GitSync.recover()`（fetch/pull → journal union merge by event id + dedupe 重建 → 非 journal 冲突中止并给出真实文件列表 → push）；`_sync_report` 先 fetch 判断分叉，分叉时走同一 recover 路径而非堆提交；`status`/`--json` 暴露 `diverged`/`unmerged`/`ahead`/`behind`，状态为 `diverged`/`unmerged`；`doctor` 分叉即失败并指向 `sync --recover`；冲突退出码 3（`sm_commands`、`learn.py`） | `test_sync_recover_merges_two_clones`、`test_sync_recover_snapshot_conflict_fails_with_file_list` | 两个克隆各追加不同事件 → `sync --recover` 退出 0、`pushed: yes`，两边事件 id 都在，第三个克隆从远程也拿到全部事件；README 两边冲突 → 退出 3、输出含 `README.md`、`status.sync.state=diverged`、`doctor` 非 0 且提示 `sync --recover` |
| G | examiner 口头说“独立题这关过了”，但 `check_correct` 仍 0，未记证据 | 只依据 `attempt.correct`，没有检测导师正文的口头通过 | `claims_pass()`（带否定前缀判断）+ `_verdict_conflict()`：check/review 中正文声称通过但无 `correct=true` 时写 `mentor_verdict_conflict`，不升级、不显示“阶段通过”，并提示“以状态为准”（`sm_engine`） | `test_verbal_pass_without_evidence_is_conflict` | 有 `mentor_verdict_conflict`；A1 仍 L2、`check_correct=0`、无 `level_up`；输出不含“阶段通过”且含“以状态为准” |
| 3（R4） | `start` 伪造“开始学习/继续学习”并计入轮次；活动标签错位 | 同 round-03 D | 已由 v0.2.3 的 `session_opened` + 回合前捕获 activity 修复；交接轮次只数 `say` | round-03 的 `test_openings_are_system_events_and_activity_labels` | 5 次 say = 5 轮；第 5 题标签 diagnose；apply 轮标签 A1-apply |

## 复跑命令与结果

```powershell
$env:LEARNARK_LLM = "mock"
python tests\run_tests.py        # 42/42
python C:\...\shared\check_variant.py --variant <本方向>   # 18/18
python C:\...\shared\vendor_core.py --check <本方向>       # core 1.0.2 match
```

- `tests/run_tests.py`：新增 `test_sync_recover_merges_two_clones`、`test_sync_recover_snapshot_conflict_fails_with_file_list`、`test_clone_resume_examiner_context_has_check_activity`、`test_verbal_pass_without_evidence_is_conflict`（共 42 条）。
- `check_variant.py`：18/18，退出码 0。
- `vendor_core.py --check`：core 1.0.2 match。

## 明确未做 / 留给下一轮

- **真实 GitHub / 跨设备**仍未验证；本轮仍用本地裸仓库模拟远程。
- **冲突恢复只自动合并 journal/dedupe**：`state/*.json`、`sessions/*`、`artifacts/*` 冲突仍需人工决定（core 的既定边界）；产品给出文件列表但不提供三选一交互。
- **报告问题 6（恢复摘要计数/旧文案）**：`_resume_note` 的“第 N 次提交已通过”已随 D 修复，但任务卡理由仍可能引用定位时的旧等级（`last_decision` 未在升级后刷新）。
- **报告问题 8（README/AGENTS 硬编码本机路径）**：生成文档中已有“换机器改路径”的提示，未改成相对/环境变量入口。
