# 体验报告 — direction-c-atelier round-04 S4 Git 同步与干净克隆恢复

- 版本: **0.2.2**（core 1.0.2，schema 1；`version-manifest.json`）
- 体验者: 独立子 Agent（deepseek-flash，独立上下文，非研发者）
- 场景: **S4**（P3 Mia：换电脑继续；今天只有 20 分钟，不想从头学）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r04-s4\proj`
  克隆目录: `...\r04-s4\clone`　裸仓库: `...\r04-s4\remote.git`
- 入口: `python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-c-atelier\runtime\learn.py <cmd>`
- 交互预算: 场景卡 12 次 / 本轮任务卡 ≤8 次；实际 **4 次 `say`**
- 环境: Windows PowerShell 5.1，Python 3.14.6，git 2.55.0；真实 DeepSeek API（`deepseek-flash`），**未用 `--offline`**
- 远程说明: **本地裸仓库模拟远程，只验证了本地 Git 流程，真实 GitHub 未验证。**
- 只读范围: 本场景卡、`START_HERE.md`、产品生成的 `README.md`/`AGENTS.md`、`personas.md` 模板；未读源码/设计/测试/历史报告，未改产品。

## 实际步骤（命令 + 关键输出摘要）

### 1. 新建项目

```powershell
python $LA\runtime\learn.py init --goal "用 Python 写一个能调用工具的 Agent（两周前学过 function calling，想快速继续）" --dir ...\r04-s4\proj --minutes-per-week 60
```

输出（03:38:10）：

```text
已创建 Atelier 学习项目：...\r04-s4\proj
目标：用 Python 写一个能调用工具的 Agent（...）
模板：Agent 开发 · 四周最小闭环（agent-dev） · 每周约 60 小时 · 计划 plan-v1 v1（10 步）
```

注：`.learnark\project.json` 实际写的是 `"minutes_per_week": 60`，但界面显示成 **“每周约 60 小时”**（见问题 3）。

### 2. `start` 与 2 轮真实交流

`start`（03:38 出头）给出：上次停在哪=首次进入；计划 v1 0/10；该找 planner，并列 3 道诊断题。随后两次 `say`：

| # | 学习者输入（摘要） | 导师回复要点 | 帮助等级 |
| --- | --- | --- | --- |
| 1 | 两周前跟教程做过 function calling，只记得返回工具名和参数；今天只有 20 分钟，想直接做能调工具的 Agent，不想从头学 | planner 先指出“20 分钟 vs 计划里每周约 60 小时”矛盾；追问 20 分钟是日还是周、工具结果怎么回传；并说交接缺少 `known/do_not_redo/open_loops` | 独立完成 |
| 2 | 20 分钟是今天一天，平时每天 10–20 分钟；尝试回答：工具结果要作为 `role=tool` 消息回传，模型再决定下一步；参数校验不确定；想动手写最小循环 | planner 确认 `role=tool` 说对了，把本周改成“每天一小步”，今天落 `w1-agent-loop-ex1` 写伪代码；问先复述还是直接写 | 独立完成 |

`status`（同步前）：

```text
当前导师：planner ｜ 计划 v2 ｜ 进度 0/10
会话 S-20261104T033829-planner 进行中
最近回合：planner ｜ 帮助等级：独立完成
能力：四项均未验证（证据 0 条）
未决：无
下一步：learn.cmd switch concept
git：branch=master remote=（无） dirty=True diverged=False unmerged=0
```

### 3. 裸仓库 + `sync`

```powershell
git init --bare ...\r04-s4\remote.git
git remote add origin ...\r04-s4\remote.git
python $LA\runtime\learn.py sync
```

```text
git state: pushed
written=yes  committed=yes  pushed=yes
branch=master sha=2ad2102 remote=C:\...\r04-s4\remote.git
diverged=no  unmerged=0
files=7
```

核对：本地 `2ad2102` = 远程 `refs/heads/master`；commit 恰好 7 个文件，与 `files=7` 一致。同步后 `git status` 仍显示 `M .learnark/journal/events.jsonl`（sync 事件在提交后追加）。

### 4. 干净克隆 + 克隆内 `start`

```powershell
git clone ...\r04-s4\remote.git ...\r04-s4\clone
cd ...\r04-s4\clone
python $LA\runtime\learn.py start
```

`start` 输出：

```text
目标：... · 每周约 60 小时
计划：plan-v1 v2（权威：planner） · 进度 0/10 步
上次停在哪：H-0001 planner→planner（just now） · 未决 1 条
这一轮该找谁：概念导师 concept
  · 当前会话导师是 planner；切换会先写一份交接：learn.cmd switch concept
```

stderr：

```text
提示：交接已超过 7 天，已补写 .learnark\handoff\20261104T033910-planner-to-planner.md（degraded）。
```

克隆内 `status` 摘要：

```text
当前导师：planner ｜ 计划 v2 ｜ 进度 0/10
上次停在 H-0001（planner→planner）
交接：H-0001 planner→planner（just now，degraded=False）
最近回合：planner ｜ 独立完成
能力：四项均未验证
未决：- OL-objective [一般] owner=concept ... 完成 w1-agent-loop
下一步：learn.cmd switch concept
git：branch=master remote=...\remote.git dirty=True diverged=False unmerged=0
```

- 计划、历史回合、下一步都带过来了，**没有原路径报错**；`artifacts/` 空目录不在克隆里（未被 git 跟踪），未触发报错。
- 但 `start` 并非只读：它新写了 `H-0001` 自交接、改了 `state/studio.json`、追加 3 条事件，工作树立即 `dirty=True`。同步前的原始项目里 `未决：无`，克隆里凭空多出 `OL-objective`。
- “已超过 7 天”不成立：`journal` 里 `stale_handoff` 的 `age_days=null`，此前根本没有 handoff；交手机器块又写 `degraded:false`，与 stderr/事件 `handoff_degraded` 矛盾。

### 5. 克隆内继续 1 轮并 `sync`

```powershell
python $LA\runtime\learn.py switch concept --why "克隆后按 start 建议换到概念导师"
python $LA\runtime\learn.py say "刚在克隆出来的新目录里继续。一句话版：单次问答一次请求一次回答；Agent 会循环——模型决定调工具、执行、把结果回传，直到能给出最终答案。对吗？我想直接写这个循环。"
```

concept 回复确认循环差别，指出终止条件与反例，帮助等级“分步引导”；`switch` 写 H-0002，未报错。

```text
git state: pushed
written=yes  committed=yes  pushed=yes
branch=master sha=0b89671 remote=...\remote.git
diverged=no  unmerged=0
files=10
```

核对：远程 tip 变为 `0b89671`，克隆本地同 sha。

### 6. 分叉测试（clone 侧先推过，proj 改一条再 sync）

克隆推送后，原始项目仍停在 `2ad2102`，本地已有第 3 个真实回合（planner，写最小循环伪代码的计划）。`sync`：

```text
git state: conflict
written=yes  committed=yes  pushed=no
branch=master sha=f7ec698 remote=...\remote.git
diverged=yes  unmerged=0
files=7
冲突文件（未自动合并）：
  ! .learnark/state/session.json
  ! .learnark/state/studio.json
提示：Remote and local histories diverged. Nothing was force-pushed and the local commit is intact. Conflicting paths: [...]. Journal-only conflicts can be recovered automatically with `sync --recover`; state/snapshot conflicts need a human choice (keep local or remote) before syncing again.
```

退出码 **3**。按提示执行 `sync --recover`：

```text
git state: conflict（recover）
written=yes  committed=yes  pushed=no
branch=- sha=7241382 remote=（无）
diverged=yes  unmerged=0
冲突文件（未自动合并）：
  ! .learnark/state/session.json
  ! .learnark/state/studio.json
提示：Automatic recovery only merges journals. Conflicting state files need a manual choice: inspect `git status`, keep one side's state/*.json, then run `sync`.
```

退出码仍 **3**。

- 本地随后有 `f7ec698`（proj 第 3 回合）和 `7241382`（recover 只追加了 1 条 `sync_recover` 事件）；远程仍是 `0b89671` 未变。
- 双方记录**都没有被覆盖**：proj 有 planner 三回合，克隆/远程有 planner 两回合 + concept 回合。但 proj 看不到克隆的 concept 会话（`sessions/20261104-033938-concept.md` 只在克隆/远程）；proj journal 本地有 22 条事件，却没有 H-0002、也没有 concept 回合，说明 `recover` 并未把对方的事件并进来。
- 没有 force push；远程历史仍是 `999d5f5 → 2ad2102 → 0b89671` 的直链。
- 按提示“inspect `git status`，保留一边 `state/*.json`，再 `sync`”无法照做：此时仓库没有 merge/rebase 冲突态，`git status` 只显示分叉；产品面也没有“选本地/选远程”的命令。照做只会再次得到同一个 exit 3。`status` 只显示 `diverged=True`，不提示怎么恢复（只有 `doctor` 提示 `sync --recover`）。

## 完成情况

| 环节 | 结果 |
| --- | --- |
| 开始（init/start） | 成功 |
| 诊断/定位 | 成功（2 轮内定位时间矛盾与工具结果回传理解） |
| 尝试与反馈 | 成功（`role=tool` 尝试被具体确认；分步引导可见） |
| 保存/同步（单设备） | 成功（两次 pushed，sha 与远程一致） |
| 切换导师 | 成功（克隆内 planner→concept，写 H-0002，未报错） |
| 干净克隆恢复 | **基本成功**：计划 v2、历史回合、下一步 concept 都在；但 `start` 写入了伪造的 H-0001 与 OL-objective，且“超过 7 天/degraded”自相矛盾 |
| 分叉 | **失败（产品侧）**：exit 3，无产品级解决路径；未 force push、未覆盖数据 |

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 换电脑 clone 后 `start` 只读地恢复 | 写 handoff、改 studio/journal，工作树变脏 | `clone-start.txt`、`git status`、H-0001 文件 |
| `start` 说清楚“上次停在 H-0001” | H-0001 是 start 自己刚造的，且理由称“超过 7 天” | H-0001 `why`、`stale_handoff.age_days=null` |
| `sync` 的 written/committed/pushed 可信 | 4 次 sync 的 pushed 均与远程 sha 一致；但 `--recover` 同一结果块里的 `branch`/`remote` 字段错误 | `sync1.txt`、`clone-sync.txt`、`proj-sync2.txt`、`proj-sync-recover.txt` |
| 分叉时自动并集 journal，快照冲突要求人工 | 自动恢复未并入对方事件；人工路径无可执行命令 | `proj-sync-recover.txt`、proj journal 无 H-0002 |
| 冲突不会静默覆盖任何一方 | 未覆盖：两边提交都在；但也无法合并使用 | `git-history.txt` |
| 开始前填的每周 60 分钟被当成 60 分钟 | 界面/导师上下文都是“每周约 60 小时”，planner 据此重排 | init/start 输出、`say1.txt`/`say2.txt` |
| 克隆不依赖原路径 | 无路径错误；仅空的 `artifacts/` 未跟过去 | `clone-status1.txt` |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | **阻塞（分叉场景）** | 分叉后没有产品级恢复路径：`sync` exit 3 → `sync --recover` 仍 exit 3；提示“保留一边 `state/*.json` 再 sync”无法执行（无 merge 冲突态、无选边命令），照做会再次冲突。`status` 也不给恢复指引 | 两端都有本地回合后：A 端 sync（提交/推送）；B 端 sync（冲突）→ `sync --recover` → `status`/`git status` | `evidence\proj-sync2.txt`、`evidence\proj-sync-recover.txt`、`evidence\proj-status-conflict.txt`、`evidence\proj-doctor-conflict.txt` |
| 2 | **重要** | `start` 文档写明“只读项目文件”，实际在无 handoff 的克隆/项目里写 degraded 自交接 H-0001、追加 3 条事件、改 studio，导致工作树 dirty；理由误报“超过 7 天”（`age_days=null`）；交手机器块 `degraded:false` 与事件/stderr 的 degraded 矛盾；凭空生成 `OL-objective` 未决项 | 干净克隆内直接 `start`；看 stderr、`git status`、`.learnark/handoff/`、journal 的 `stale_handoff` | `evidence\clone-start.txt`、`clone\.learnark\handoff\20261104T033910-planner-to-planner.md`、`evidence\proj-start-after-turns.txt` |
| 3 | **重要** | `--minutes-per-week 60` 被显示/注入为“每周约 60 小时”（60 倍误差）；planner 在上下文里把它当真，先要求澄清再重排计划 | `init --minutes-per-week 60` 后看 init/`start` 输出；再 `say`，看 planner 引用“60 小时” | `proj\.learnark\project.json`（60）、`evidence\say1.txt`、`evidence\say2.txt`、`evidence\status-before-sync.txt` |
| 4 | 一般 | `sync --recover` 的结果块把 `branch` 打成 `-`、`remote` 打成 `（无）`，与实际（master、origin 存在）不符；用户难以判断仓库是否还正常 | 分叉后执行 `sync --recover` | `evidence\proj-sync-recover.txt` |
| 5 | 一般 | `sync` 成功后 journal 仍 dirty（同步事件在提交后追加），所以“干净”状态永远观察不到；按机制推断，紧接着再 sync 会再产生一条仅含 sync 事件的提交（本次未执行，属推测；版本说明已列为已知限制） | sync 后立即 `git status` | `evidence\sync1.txt`、`git status` |
| 6 | 一般 | 空目录 `artifacts/` 不进 git，克隆里不存在；本次未报错，但依赖该目录存在的操作在“新设备”上可能失败 | `git clone` 后 `Test-Path clone\artifacts` = False | `evidence\clone-status1.txt` |

## 使用负担

- 师生往返: **4 次**（say×4；switch/status/sync 不计）
- 命令数: 约 22 条（含 4 次 sync、4 次 status、3 次 start、1 次 doctor）
- 需要阅读的文档: 3 处（`START_HERE.md`、生成的 `README.md`、`AGENTS.md`）+ 模板 1 处
- 不清楚的地方:
  - 分叉后到底该敲什么？`status` 说 `diverged=True`，`doctor` 说 `sync --recover`，`--recover` 又说“手动选择题”，但没有对应命令。
  - `written=yes` 具体指写了什么？失败/半恢复时也报 yes。
  - 克隆里 `H-0001` 从哪来、为什么是“上次停在哪”。

## 结论

- **是否完成场景目标：部分完成（主线是，分叉否）。** 单设备 `init → 2 轮真实对话 → 本地裸仓库 → sync → 干净克隆 → 克隆内继续 1 轮 → 再 sync` 全部走通；`written/committed/pushed` 三态字段本身与 git 事实一致（4 次 sync 的 pushed 均以远程 sha 核对）。但失败恢复也报 `written=yes`，且 `--recover` 同块里的 `branch=-`/`remote=（无）` 错误，容易误读。“另一台电脑继续”只在没有并发修改时成立；两端都学习后，产品没有可执行的合并/恢复路径，跨设备目标只完成一半。没有 force push，没有静默覆盖任何一方。
- **最需要修的一件事：** 给分叉一个可执行的单命令恢复（按事件 id 并集保留双方会话/能力/交接，重建 `session.json`/`studio.json` 快照；或明确输出可复制的 `git` 命令并让 `--recover` 保留 merge 冲突态供人选择），同时让 `start` 真正只读，不要在读取时补造 handoff。

## 附录 A：git 记录

`git log --oneline`（proj）：

```text
7241382 learn(proj): 2026-11-04 03:40
f7ec698 learn(proj): 2026-11-04 03:40
2ad2102 learn(proj): 2026-11-04 03:38
999d5f5 learn(proj): initial project skeleton
```

`git log --oneline`（clone / remote）：

```text
0b89671 learn(proj): 2026-11-04 03:39
2ad2102 learn(proj): 2026-11-04 03:38
999d5f5 learn(proj): initial project skeleton
```

`git remote -v`（proj 与 clone 相同）：

```text
origin  C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r04-s4\remote.git (fetch)
origin  C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r04-s4\remote.git (push)
```

远程未被改写的依据：远程 tip 始终是 `0b89671`，且 `999d5f5 → 2ad2102 → 0b89671` 为直系历史；proj 的 `f7ec698`/`7241382` 只在本地，`pushed=no`。

## 附录 B：克隆目录 `status` 摘要与首个 `start`

见第 4 节；完整捕获 `evidence\clone-status1.txt`、`evidence\clone-start.txt`、`evidence\git-history.txt`。

## 附录 C：同步输出原文

- 首次 `sync`：`evidence\sync1.txt` → pushed，`2ad2102`，files=7
- 克隆 `sync`：`evidence\clone-sync.txt` → pushed，`0b89671`，files=10
- proj 冲突 `sync`：`evidence\proj-sync2.txt` → conflict，`f7ec698`，pushed=no，exit 3
- `sync --recover`：`evidence\proj-sync-recover.txt` → conflict（recover），`7241382`，pushed=no，exit 3
- `doctor`：`evidence\proj-doctor-conflict.txt` → FAIL git（diverged）+ FAIL handoff_present，exit 3

## 附录 D：证据文件

均位于 `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r04-s4\evidence\`：
`say1.txt`、`say2.txt`、`status-before-sync.txt`、`sync1.txt`、`clone-start.txt`、`clone-status1.txt`、`clone-switch.txt`、`clone-say1.txt`、`clone-sync.txt`、`proj-say3.txt`、`proj-sync2.txt`、`proj-sync-recover.txt`、`proj-status-conflict.txt`、`proj-status-after-recover.txt`、`proj-doctor-conflict.txt`、`proj-start-after-turns.txt`、`git-history.txt`。
