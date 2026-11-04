# 实现工程师简令（四个方向共用）

你负责把所在方向的 `design.md` + `mentors/` + `curriculum/` + `templates/` 变成**真的能跑**的本地学习框架。
只改本方向目录，不改 `shared/`、不改其他方向、不改 DSH。

## 必读
1. `shared/spec-core.md`（核心 API、CLI 契约、目录、导师更新块、测试钩子）
2. `shared/requirements.md`（底线；第 6 节证据规则、第 7 节可靠性）
3. `orchestration/briefs/direction-<x>.md`（本方向机制与特有验收）
4. 本方向的 `design.md`、`mentors/*.md`、`curriculum/*`、`templates/*`

## 交付
```
runtime/
  learn.py            # CLI 入口（sys.path 注入本目录，导入 learncore）
  <方向模块>.py        # 状态、调度、导师上下文、证据应用、会话写入
  learncore/          # 必须由 `python shared/vendor_core.py --variant <本目录>` 生成，禁止手改
  CORE_VERSION
learn.cmd             # @python "%~dp0runtime\learn.py" %*
templates/            # 已存在则复用
tests/run_tests.py    # 必须可独立运行，默认 mock LLM，无网络
examples/demo.md      # 一次真实离线运行的记录（命令 + 输出摘要，标注“离线/合成”）
START_HERE.md         # 公开入口（见下）
```

`START_HERE.md` 是体验者唯一能依赖的入口文档（≤120 行，中文）：
- 一句话说明这个版本是什么、适合谁、不是什么；
- 3 步快速开始（设置 `DEEPSEEK_API_KEY`、init、start），含 Windows PowerShell 原文；
- 全部命令表（含方向特有命令与 `--json`/`--offline`）；
- 学习记录在哪（`.learnark/`、`sessions/`、`artifacts/`）、如何恢复、如何同步、没有远程时会怎样；
- 离线模式的限制（脚本导师，不代表真实教学质量）；
- 已知限制与版本号。
同时 `init` 生成的项目 `README.md` 必须能在 1 分钟内告诉学习者“现在输入什么”，`AGENTS.md` 必须告诉任意 DSH/Agent：先用本入口 `start` 读取状态，按导师协议继续，不要凭空编造学习记录。

## 必须实现的命令
`init`、`start`、`say`、`status [--json]`、`pause`、`switch`、`sync`、`doctor`、`export --out`，以及方向特有命令（见 brief）。
所有方向还必须有：`--project PATH`（默认 cwd 向上找 `.learnark/`）、`--offline`（= `LEARNARK_LLM=mock`，输出必须标明离线）、退出码 0/2/3/4。

## 关键实现要求

1. **状态**：`.learnark/project.json`（目标、模板、约束、学习者档案、schema_version）；方向快照放 `.learnark/state/*.json`（`Document`）；事件写 `journal/events.jsonl`（`Journal`）。
2. **幂等**：每条写命令生成稳定 `dedupe_key`（如 `say:<session_id>:<turn_index>`、`attempt:<activity>:<answer_sha>`），重复执行返回已有结果并提示“已记录”，不得重复计数。
3. **会话**：`sessions/YYYYMMDD-HHMMSS-<mentor>.md`，含学习者/导师原文、活动、help_level、attempt、next。`say` 同时写事件与会话。
4. **导师回合**：
   - 用 `mentor.run_turn`（system=mentor 协议，context=紧凑状态摘要，user=学习者输入，transcript=本会话最近 4–6 轮）。
   - 应用更新前用 `validate_updates` + 方向 schema 校验；非法 → 记 `mentor_update_invalid` 事件（含 raw sha256、原因），本轮按“无证据”处理，并在输出中告知。
   - 证据规则：只有 `help_level <= 1` 且 `correct` 才可提升能力，单轮最多 +1；`help_level >= 2` 记 `assisted`（只证明接触）；学习者自述不得升级。
   - 导师不得直接改状态：所有状态变更由运行时根据事件与规则计算。
5. **恢复**：`start` 必须只依赖项目文件（project.json + 快照 + journal + handoff），能回答“上次停在哪、下一步做什么”；不得依赖进程内缓存或旧聊天。
6. **交接**：`pause` 与 `switch` 写 `.learnark/handoff/latest.md`（字段见 design），并写 `handoff` 事件；下一导师上下文包含该摘要。
7. **同步**：用 `GitSync`；`init` 时 `ensure_repository()`；`sync` 输出 written/committed/pushed/remote/recovery，绝不 force push。
8. **doctor**：检查项目可读、journal 完整性、去重索引、锁残留、git 状态、LLM 配置（是否可用 key/是否离线）、快照与 journal 的版本一致性；输出问题与建议，返回码非 0 表示有问题。
9. **离线模式**：`LEARNARK_LLM=mock` 时用 `MockLLM` + `tests/fixtures/mentor_script.jsonl`，并在每个导师输出前标注 `[离线脚本导师]`；不得把 mock 输出写成真实 LLM 证据。
10. **UTF-8**：`cli.main()` 已处理 stdio；不要用系统默认编码写文件。

## 测试（`tests/run_tests.py`）
至少覆盖：
- init 可重复、目录/入口/AGENTS.md 生成；
- 离线 E2E：init → start → say → status → pause → sync → doctor 全部返回 0；
- 幂等：同一 `say`/attempt 重放不重复计数；
- 证据规则：help_level 2/3 不升等级，help_level 0 才升；
- 交接：switch/pause 后 handoff 文件与事件存在；
- 恢复：复制项目到新目录（或新进程）后 `start` 能定位下一步；
- 损坏恢复：快照写坏 → `status` 自动从 `.bak` 恢复并提示；日志尾部半行可忽略；
- git：本地裸仓库 sync → pushed，克隆 → 可 `status`；
- 方向特有算法（地图门控 / rubric 门控 / 交接字段 / 调度打分）各 1–2 个确定性测试。

## 自检（交付前必须自己跑通并修到绿）
```powershell
. C:\Users\YK\Desktop\LearnArk\_sandbox\env.ps1
cd <项目临时目录>
python <variant>\runtime\learn.py init --goal "Agent 开发" --dir proj
python <variant>\runtime\learn.py start --project proj --offline
python <variant>\runtime\learn.py say "我不确定 RAG 和 Agent 记忆的区别" --project proj --offline
python <variant>\runtime\learn.py status --project proj
python <variant>\runtime\learn.py pause --project proj
python <variant>\runtime\learn.py sync --project proj
python <variant>\runtime\learn.py doctor --project proj
python <variant>\tests\run_tests.py
```
再用真实 API 跑一次 `start` + 1 次 `say`（去掉 `--offline`），确认导师回复正常、机器块被解析（查看 journal 事件）。

## 报告
回复：文件清单（一行一个）、自检结果、方向特有命令示例、留给可靠性工程师的已知问题、设计文档与实现之间的偏差（如有）。不超过 400 字。
