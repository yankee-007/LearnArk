# Tempo 恢复手册（direction-d-tempo 0.2.6）

原则：**journal（`.learnark/journal/events.jsonl`）是权威记录，`state/*.json` 只是快照**；写入是原子写 + 幂等键，崩溃最多丢一次未落盘的快照，不会丢已追加的事件。先跑 `python runtime/learn.py status` 与 `doctor`，再按类型处理。

## 1. 命令被杀 / 半写

现象：命令被 Ctrl-C、关终端或断电打断；`state/` 出现 `*.tmp`；下次输出 `[恢复]`。

自动：状态文件用临时文件 + 原子替换，读者看不到半个 JSON；成功写入时同时更新 `.bak`。主文件损坏或不是 JSON 对象时，`status`/`start` 自动从 `.bak` 重建，并在 `recovery` 中说明。

人工步骤：① `status` 确认目标、预算、到期仍在；② `doctor` 看 `interrupted_writes`、`snapshot_journal`；③ 直接 `start`。重启会从 journal 补回卡片复习、等级变更与完成标记（幂等，不重复计数），不需要手工补记录。

## 2. journal 尾部半行 / 中间损坏

尾部半行自动处理：读命令忽略它，下一次写先截断残行、记 `journal_repaired`，再追加新事件。不要手写 journal 尾部。

中间损坏会以退出码 3 停止（报 `line N is not valid JSON`），不会静默跳过。人工：备份 `events.jsonl` 与 `dedupe.json`；定位第 N 行，只删明显残缺的一行，不重排、不改 `id`/`seq`；无法判断时保留文件，把 `doctor` 输出交给维护者，不要重建整个 journal。

## 3. 去重索引损坏

`dedupe.json` 只是幂等索引，损坏不影响事件。下一次写命令会按 journal 重建并持久化（`journal_index_rebuilt`），`doctor` 的 `dedupe_index` 会提示缺键/多键。自动恢复即可，无需手删文件。

## 4. 锁残留与并发冲突

项目锁 `.learnark/project.lock` 让写命令串行；journal/state 另有细粒度锁。进程被杀后锁文件会留在磁盘，但操作系统已解锁，**残留无害，不要手删项目锁**。

- 两个命令同时写：后一个等待；超过 20 秒（可用 `LEARNARK_LOCK_TIMEOUT` 调整）退出码 3，提示“另一个进程正在写这个项目”，本次不写任何文件。等前一个结束后重跑即可。
- 过期写入：运行时用版本号 CAS 拒绝保存，退出码 3 并提示“状态已被另一个进程更新……请重跑”，不会覆盖较新的数据。重跑同一命令即可。
- 判断是否真卡住：`doctor` 不占项目锁，可随时运行；`status` 在锁被长期占用时会等到超时，这是预期行为。

## 5. Git 同步

- 无远程：`sync` 报 `no-remote`，本地提交保留；补 `git remote add origin <URL>` 后再 `sync`。
- 仅 journal 分叉：`sync --recover` 按事件 `id` 做并集、重排序号、重建 dedupe 后推送；不会 force push。
- 快照冲突（如 `state/skills.json`）：`sync` 以退出码 3 停止并列出冲突文件。人工看 `git status`，决定保留哪一侧的该文件，手工改好并 `git add`，再 `sync`。禁止 `git push --force` 与 `git reset --hard`。
- 被拒绝的同步：本地提交一定还在（`git log --oneline` 可见），远程保留对方提交；不要为提高“干净度”重建仓库。

## 6. 干净克隆 / 换机器后异常

① 确认目录含 `.learnark/`、`sessions/`、`artifacts/`；缺 `.learnark` 说明克隆不完整，重新克隆。② `status` 应显示目标、技能等级、到期卡与上次交接；`start` 应打印“上次停在哪”“到期提醒”。③ `.gitattributes` 必须存在且含 `* -text`，否则产物在 Windows 换行转换后哈希会变；旧项目先补该文件再 `sync`。④ 若 `status` 报状态损坏，按第 1 节从 `.bak` 恢复；`.bak` 也损坏则保留现场并联系维护者，不要手改 JSON。

## 7. 自动 vs 人工一览

| 情况 | 方式 |
| --- | --- |
| 快照截断/不是 JSON 对象 | 自动从 `.bak` 恢复并报告 |
| journal 尾部半行 | 自动截断 + `journal_repaired` |
| 去重索引损坏 | 下次写入自动重建 |
| 锁文件残留 | 自动（OS 解锁），文件可留 |
| 并发/过期写入 | 拒绝并提示重跑（退出码 3） |
| journal 中间损坏 | 人工定位并删残行 |
| 快照冲突 | 人工保留一侧后 `sync` |
| journal-only 分叉 | `sync --recover` 自动并集 |
| 无远程 | 自动本地提交，人工补 remote |
| `.bak` 也损坏 | 人工，保留现场 |

永远不要：手改 `state/*.json`、删除 journal、force push、用“重新 init”覆盖已有项目。
