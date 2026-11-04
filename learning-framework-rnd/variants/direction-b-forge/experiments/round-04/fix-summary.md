# round-04 修复记录 — Forge v0.2.3

- 输入：`experiments/round-04/experience-S4-P3.md`（S4/P3，0.2.2 + core 1.0.1）
- 版本：`direction-b-forge 0.2.3`｜vendored `learncore 1.0.2`｜state `schema_version 1`
- 范围：修报告 #1（阻塞，冲突恢复）、#2（status/doctor 分叉）、#3（克隆 sha）、#5（coach 否认作品）；
  #4（锁文件）与 #6（截断重发）见文末。
- 回归：`python tests\run_tests.py` → **35/35 通过**；`shared/check_variant.py` → **18/18 ok**；
  `shared/vendor_core.py --check` → **core 1.0.2: all vendored copies match**。

## 问题 → 修复 → 测试

| # | 问题（报告） | 修复 | 测试 |
| --- | --- | --- | --- |
| 1 | 远程分叉后 `sync` 只 abort，恢复文案要求“解决冲突”但 `git status` 无冲突文件；重试只增加提交，无法恢复 | 接入 core 1.0.2：`sync` 在 `pull --rebase` 失败后自动调用 `recover_diverged()`——journal-only 冲突按 event id 并集合并、重排 seq、重建 dedupe、继续 rebase 并推送；快照冲突不自动合并，abort 后退出 **3** 并打印真实 `冲突文件：…`（从恢复 detail 的 blocking/unmerged 解析）。新增显式入口 `sync --recover`。 | `sync_recover_journal`：两个克隆各追加不同事件 → `sync --recover` exit 0、`pushed=yes`、远程 journal 含两个 id、seq 连续。`sync_snapshot_conflict`：两克隆各自 `say` → 第二次 `sync` exit 3、输出含“冲突文件”与 `state/session.json`；`sync --recover` 仍 exit 3 并列出文件。 |
| 2 | `ahead=2 behind=2` 时 `doctor` 仍全绿；`status` 不显示分叉 | `status --json` 的 `sync` 增加 `unmerged`/`diverged`；人读输出显示 `diverged=yes`、`⚠ 未合并文件` 或分叉提示。`doctor` 在 unmerged / diverged / rebase 未完成时记错误并退出 3。 | `sync_snapshot_conflict` 同用例断言：`status.sync.diverged=true`、人读含“分叉”、`doctor` exit 3。 |
| 3 | Windows `autocrlf=true` 干净克隆后作品 sha 与登记值不一致，`doctor` 误报“篡改”；仓库无 `.gitattributes` | core 1.0.2 `ensure_repository()` 生成 `.gitattributes`（`* -text`）与新的 `.gitignore`；`init` 直接调用；`sync`/`pause` 对已有仓库也调用 `ensure_repository()`，旧项目缺失时自动补并提交。`doctor` 缺 `.gitattributes` 时提示“运行 sync 或 init 会自动补上”。 | `clone_hash_consistency`：新建项目 → 登记作品 → `pause`/push → clone → 两边作品 sha256 相同、clone 中 `doctor` exit 0；删除 clone 的 `.gitattributes` 后 `doctor` 提示“sync 或 init”，`sync` 后文件补回。 |
| 5 | 原项目已有作品，导师却说“这台设备上我没看到 artifact add 的记录” | 同 round-03 #1：所有导师上下文注入完整已登记集合（id/path/sha256）；文本否认已登记作品时记 `review_note_conflict`（denied=true）并在输出纠正。 | `registered_set_and_denial`（round-03 修复中同一测试覆盖 coach 否认与纠正输出）。 |

## 复现命令（CLI，core 1.0.2）

```powershell
$V = "<variant>"
python "$V\runtime\learn.py" init --goal "Agent 开发" --dir p
python "$V\runtime\learn.py" start --project p --offline
python "$V\runtime\learn.py" pause --project p
git init --bare remote.git
git -C p remote add origin ..\remote.git
python "$V\runtime\learn.py" sync --project p          # pushed
git clone remote.git c1; git clone remote.git c2      # 两个克隆
# c1 / c2 各追加事件并 commit；c1 push；c2：
python "$V\runtime\learn.py" sync --recover             # exit 0，两边事件都在
# 快照冲突：两克隆各自 say + sync -> 第二个 sync exit 3 并列出 state/session.json
python "$V\runtime\learn.py" status --json               # sync.diverged=true
python "$V\runtime\learn.py" doctor                      # exit 3
```

## 改动文件

- `runtime/learn.py`：`sync --recover`；冲突文件列表；`sync` 退出码（conflict 3，commit/push 失败 4）；`status` unmerged/diverged；`doctor` 分叉即失败；`pause` 同步冲突返回 3；`sync`/`pause` 自动补 `.gitattributes`；coach 否认已登记事件。
- `runtime/forge_state.py` / `runtime/forge_mentor.py`：版本与导师上下文（同 round-03）。
- `tests/run_tests.py`：新增 `sync_recover_journal`、`sync_snapshot_conflict`、`clone_hash_consistency`，并在 `init` 中断言 `.gitattributes` 与忽略项。
- `START_HERE.md`、`version-manifest.json`（0.2.3）、`examples/demo.md`。

## 未修（round-04 #4、#6，非本轮要求）

- #4 旧项目里**已经跟踪**的 `journal.lock`/`state.lock`/`usage.jsonl` 不会自动 `git rm --cached`；新项目与旧项目的后续生成已被 `.gitignore` 忽略，但历史跟踪需要一次性手工清理（下轮可加 `doctor` 提示）。
- #6 PowerShell 5.1 内联 `say` 吞引号：已由“截断输入不猜原因 + `say -` 提示”缓解，需要学习者重发一次。
- 另：`status` 的 `behind` 仍依赖本地 remote ref，跨设备后需 `sync`/`fetch` 才刷新（本轮未改）。
