# Atelier 学习记录恢复手册

适用版本：direction-c-atelier 0.2.x（core 1.0.2）。不在项目内时用 `--project <路径>`。

先记住三类事实的优先级：`.learnark/journal/events.jsonl` 是**权威事件流**；`state/*.json` 是可重建的快照；`handoff/` 与 `sessions/` 是交接和会话记录。任何恢复都不要先删 journal。

## 一、先做只读诊断

1. `learn.cmd status --json`：能否读出项目、计划、能力、下一步；输出里的 `recovered` 会列出自动修复。
2. `learn.cmd doctor`：检查状态可读、日志完整性、去重索引、锁、git、计划哈希、交接合法性。
3. `learn.cmd handoff --check`：逐份校验历史交接的机器块。
4. `git status` 与 `git log --oneline -5`：分清“已写入 / 已本地提交 / 已推送”。

## 二、半写与损坏（多数自动）

- **快照 JSON 截断或乱码**：运行时自动从同名 `.bak` 恢复，并在 stderr 打印 `recovered ... from backup`，`status` 继续可用。若 `.bak` 也坏了，`doctor` 报 `[FAIL] studio_readable`，命令以 3 退出并指出文件——此时从 git 历史取回上一版（`git show HEAD:.learnark/state/studio.json`）。
- **journal 尾部半行**：视为进程被杀留下的残渣，读取时自动忽略；下一次写入前会截掉残行并记 `journal_tail_repaired`，不会把新事件粘到残行上。若坏行在中间（退出码 3），说明文件被外部改过：保留副本，用 `git diff` 对照历史恢复；不要整段删除。
- **去重索引损坏**：`dedupe.json` 会从 journal 重建，`doctor` 会报告并修复；重建期间重复命令最多被去重一次，不会重复计数。
- **写到一半崩溃**：journal 可能已有一条事件、快照还没更新。`status` 仍可读；以 journal 为准，`doctor` 的 `snapshot_drift` 会报告快照漂移。不要用旧快照覆盖 journal。

## 三、锁残留与并发

写命令会持有 `.learnark/project.lock`；等待超过上限（默认 60 秒，可用 `LEARNARK_LOCK_TIMEOUT` 缩短）会以 3 退出并明确提示“状态被并发修改”。锁文件本身残留是正常的，操作系统释放后下一次命令会自动接管，**不要手删正在使用的锁**。若持续超时：确认没有另一个终端在跑 `say`/`pause`，结束卡住的 python 进程后重试。并发写入被串行化后，两条学习者消息都会保留，不会丢交接。

## 四、过期写入（StaleWrite）

两个写入者基于同一旧版本保存时，后写者会被拒绝（退出码 3），提示重跑，而不是覆盖。正确处理是重新执行命令、让运行时在新状态上重算；不要把旧 JSON 直接拷回去。

## 五、Git 分叉与冲突（需人工选择）

`sync` 绝不 force push、绝不 reset --hard。分叉时它先尝试 `pull --rebase`：

- 只有 journal（`events.jsonl` / `dedupe.json`）冲突：自动按事件 id 并集合并、重排序号、重建去重索引，保留双方事件。
- 快照/会话冲突：中止变基，保留本地提交，以 3 退出并列出冲突文件。此时必须显式选择：
  - `learn.cmd sync --recover --prefer local`：保留本机 state，远程被覆盖的文件会列出来；
  - `--prefer remote`：采用远程 state，本机被覆盖的文件会列出来；
  - 不带 `--prefer` 时只报告、不写任何东西。
- 恢复后重新 clone，验证两端 journal 事件都在。若推送失败（网络/凭据），记录已本地提交，稍后重试即可。

## 六、克隆之后

干净克隆只含受版本控制的项目文件；`usage.jsonl`、`*.lock`、`*.bak`、`.env`、日志不会进提交。克隆后先 `status`，再 `start`；若报“不是 LearnArk 项目”，多半是目录不对或克隆不完整（`.learnark/` 缺失）。若 `written=yes, committed=yes, pushed=no`，说明源机器从未推送成功，需要回到源机器 push。计划/导师状态不一致时跑 `doctor --plan` 与 `handoff --check`，按提示补一份交接，不要手改 plan。

## 七、哪些自动、哪些必须人工

| 情况 | 自动 | 人工 |
| --- | --- | --- |
| 快照损坏有 `.bak` | 恢复并提示 | 无 |
| journal 尾部半行 | 忽略、下次写入修复 | 无 |
| 去重索引损坏 | 从 journal 重建 | 无 |
| 锁超时 | 明确报错、状态不变 | 等/结束占用进程后重试 |
| StaleWrite | 拒绝覆盖 | 重跑命令 |
| journal 分叉 | 并集合并 | 需要时用 `--recover --prefer` 确认 |
| 快照分叉 | 停止并列出文件 | 选 local/remote，再 sync |
| 中间坏行/无 `.bak` | 报错 | 从 git 历史恢复 |
| 密钥误提交 | 阻止新提交 | 轮换密钥、清理历史 |

任何时候不要 `git push --force`、`git reset --hard`、删除 `.learnark/journal/`。先备份整个项目目录，再按“诊断 → 找 `.bak`/git 历史 → 重跑命令”的顺序处理。
