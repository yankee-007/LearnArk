# Forge 恢复手册

适用：`direction-b-forge` 的单个学习项目（vendored `learncore` 1.0.4）。原则：`.learnark/journal/events.jsonl` 是权威事实，`state/*.json` 只是可重建缓存；任何恢复都不要先删整个 `.learnark/`。

## 0. 先做三件事

1. 运行 `status --json`：读权威状态与 `next`，并留意 stderr 的 `[恢复]` 行。
2. 运行 `doctor --json`：一次检查状态文件、schema、journal、去重索引、锁、git、作品 sha 与证据链。
3. 先复制整个项目目录（含 `.git`）再动手；不要 `git reset --hard`，不要 `push --force`。

## 1. 半写 / 快照损坏

- 现象：`state/*.json` 被截断，`status` 报 `not valid JSON`。
- 自动：读取时从同名 `.bak` 恢复并重写主文件；journal 重放会把「事件已落盘、快照未落盘」的作品、评审、防御、缺口和会话轮次补回，stderr 出现 `[恢复] ...`。
- 人工：若 `.bak` 也没有，`status`/`start` 以退出码 3 明确报错，不会假装成功。可从备份、另一台设备或 `git show HEAD:.learnark/state/<name>.json` 取回；都没有时重新 `init` 到新目录，再按 journal 手工补记录。

## 2. journal 尾行与去重索引

- 尾部半行：core 1.0.4 会在追加前修复「缺换行」的残尾；本方向还会丢弃「带换行但 JSON 非法」的尾行。若最后一行 JSON 完整、只缺换行，会补换行并保留事件。先跑 `status`、`doctor` 也不会因尾行报废。
- 去重索引损坏：读取或下一次写入时从 journal 重建；也可显式运行 `doctor --rebuild`。
- journal 中部损坏（不是尾行）：`status`/写命令退出 3，防止继续写坏。用 `git show HEAD:.learnark/journal/events.jsonl` 或干净克隆恢复整份 journal，再跑 `doctor` 核对 seq、id、去重键。

## 3. 锁与并发

- 每个项目一把 `.learnark/write.lock`，写命令串行执行，正常等待通常无感。
- 看到 `another LearnArk process is writing this project`：另一个进程持有锁，等它结束再重跑；不要删锁文件。进程退出后操作系统自动释放，锁文件残留无害。
- 自动化脚本可设 `LEARNARK_LOCK_TIMEOUT=0.3` 让冲突快速失败；超时退出码 3，且不会写状态。

## 4. 过期写入（CAS）

- 看到 `state changed concurrently ... Re-run`：说明基于旧快照的写被拒绝，新数据没有被覆盖；直接重跑该命令。
- 不要手改 `version` 字段。已经落进 journal 的事件会在下次读取时自动补齐，不会因这次中止而丢。

## 5. Git 分叉与冲突

- 仅 journal 分叉：`sync` 会自动并集合并（按事件 id 去重、重排 seq、重建去重索引）；也可显式 `sync --recover`。
- 快照冲突：退出码 3，并列出真实冲突文件；本地提交保留，绝不 force push。先备份，再人工选择保留哪一版 `state/*.json`，`git add` 后正常 `sync`。
- 无远程：`sync` 明确报告 `no-remote`，本地提交成功。这不是错误，但跨设备同步未验证。

## 6. 干净克隆

- `git clone` 后直接在新目录运行 `status --json` 或 `start`；核对 `doctor` 0 错误、M1 的 artifact/review/defense 与 sha256。
- `.gitattributes` 里的 `* -text` 防止 CRLF 改写作品。旧仓库若缺它导致 sha 变化，先 `sync` 补上，再 `git checkout -- artifacts` 或重新克隆。

## 7. 模拟时钟

- `LEARNARK_NOW=...` 写入的事件带 `simulated: true`；它只证明调度与幂等逻辑，不代表真实学习时长。
- 用完立即取消该变量，别把模拟记录混进真实档案；`status`、`export` 会显示模拟标记。

## 8. 秘密与提交

- 密钥只从 `DEEPSEEK_API_KEY` / `LEARNARK_API_KEY` 读取；core 1.0.4 按文件名/凭据形状拦截 `.env`、`*credential*`、`*secret*`、`*.key`/`*.pem`、`tokens*`、`usage.jsonl`、`sync-log.jsonl`、`*.lock`、`*.bak`，不进入提交。`artifacts/token-budget.md` 这类合法产物不会被误拦。
- 若怀疑泄漏，用 `git log -S "<前缀>" --all --oneline` 查历史并立刻轮换密钥；只删工作区文件不够。

## 自动 / 人工对照

| 情况 | 自动 | 需要人工 |
| --- | --- | --- |
| 快照半写、有 `.bak` | 从备份恢复 | 无备份时找备份或重建 |
| journal 尾行半写 | 丢弃/补换行 | 中部损坏需换整份 journal |
| 去重索引损坏 | 从 journal 重建 | 无 |
| 事件领先快照 | 自动重放补齐 | 作品文件丢失需重新登记 |
| 锁被占用 | 等待或退出 3 | 结束卡死进程后重跑 |
| journal-only 分叉 | `sync` 并集合并 | 快照分叉需人工选版本 |
| 无远程 | 本地提交、明确报告 | 配置远程后重试 |
| 克隆后 sha 变化 | `.gitattributes` 固定字节 | 重新克隆或 checkout 作品 |

保命顺序：`status` → `doctor` → 备份 → 只改必需的文件 → 再 `doctor`。任何一步不确定，先保留现场，不要把 journal 或 `.git` 清空。
