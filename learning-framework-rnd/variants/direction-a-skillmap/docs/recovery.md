# 学习记录恢复指南（SkillMap · direction A）

> 适用：`init` 之后的任意项目。命令都在项目目录内运行，或加 `--project <路径>`。
> 出问题先跑 `python <variant>\runtime\learn.py doctor`：它会列出状态、日志、锁与 git 的问题及建议。

## 1. 半写：进程在写盘时被杀

**自动**：所有快照（`project.json`、`state/*.json`）都是“临时文件 + 原子替换”，旁边保留 `.bak`。被截断或写了一半的 `map.json` / `plan.json`，下一次命令读取时会自动从 `.bak` 还原，并把原因写进 `status` 的 `repairs` 与 `doctor` 的“状态修复”。整个 `map.json` 丢失（不是截断）时也会用备份恢复等级。

**自动**：`journal/events.jsonl` 允许最后一行只写了一半。下一条命令运行前会丢掉这一条未完成的记录、补上缺失的换行，再继续追加；不会因为一行残片让整份日志读不出来。

**你要做**：看一眼 `status` 顶部的 `! 状态修复：…`，确认丢的只是“当时正在写的那一条”。如果记得内容，用 `say` 重说即可——同一活动同一答案有幂等键，不会重复加分。

**人工**：损坏出现在日志中间（不是最后一行）时，命令以退出码 3 明确报 `line N is not valid JSON`，不会静默丢弃。此时不要手改文件：从 `.bak`、另一台设备或 git 历史恢复 `events.jsonl` / `dedupe.json`。若 `map.json` 与 `.bak` 同时损坏，CLI 同样退出 3 并指出文件，需要从 git 或备份取回。

## 2. 索引损坏与重建

- `dedupe.json` 可以丢：删除或损坏后，下一次写入会从 journal 重建索引，重复提交仍被挡住。
- journal 是权威记录，快照只是缓存；两者冲突时以 journal 为准，不要反过来覆盖日志。
- 不要手工编辑 `.learnark/state/*.json`。要改等级就真实作答；要修项目就按 `doctor` 的建议做。
- 想真正把地图重置到 L0：请同时删除 `map.json` 与 `map.json.bak`，再运行 `init`；只删前者会被备份自动恢复。

## 3. 锁残留

**自动**：`.learnark/project.lock` 等只是占位文件，真正的锁由操作系统持有；进程被杀后锁自动释放，残留文件不会挡住后续命令，无需删除。

**人工**：若命令报 `state changed concurrently`，并提示 “another LearnArk process is writing this project”，说明另一个进程真的在写：等它结束再重试。默认等待 20 秒，可用 `LEARNARK_LOCK_TIMEOUT=5` 调短（CI/测试常用）。不要用删除锁文件来“解决”并发，那会在两个写入者之间制造竞态。

## 4. 分叉与冲突

`sync` 先 fetch 再判断；分叉时不会盲目 rebase，也不会反复堆提交。

1. **只有事件流分叉**（`journal/events.jsonl`、`dedupe.json`）：运行 `sync --recover`。它按事件 id 取并集、重排序号、重建去重索引，然后普通 push；不 force push，远程原有提交仍是新提交的祖先。
2. **状态快照等文件冲突**：退出码 3，并输出真实冲突文件（例如 `README.md`）。自动恢复只合并 journal；快照要你选一边。按提示用 `git status` 查看，保留你要的版本并提交，再运行 `sync --recover`。
3. **绝不** `push --force`、`reset --hard` 或删远程分支。本地提交始终保留，远程旧历史始终可回退。

## 5. 干净克隆后的意外

- 克隆只包含**已提交**的内容。换设备前先 `pause`（写交接并同步），否则未提交的会话与产物不在克隆里。
- 在克隆里先运行 `start`（或 `status --json`）：它只读项目文件恢复节点与阶段；`doctor` 应全绿。若 `status` 的 `sync` 显示 `diverged` / `unmerged`，按第 4 节处理。
- `.env`、`usage.jsonl`、`*.lock`、`*.bak` 与日志不会进入提交（这是有意的），所以克隆里没有它们属于正常；API key 只从环境变量读取。
- 如果 `start` 说地图从 L0 开始：先确认克隆里的 `state/map.json` 是否有内容、`status` 是否给出“状态修复”；都没有，说明源设备没把状态提交或推送。回源设备 `sync` 后重新克隆。

## 6. 永远不会自动发生的事

覆盖冲突快照、force push、`reset --hard`、按导师话术改等级、删除你的产物。遇到这些只能由人决定。
