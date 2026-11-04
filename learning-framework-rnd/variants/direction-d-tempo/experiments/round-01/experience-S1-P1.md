# 体验报告 — direction-d-tempo round-01 S1（P1 小林）

- 版本: direction-d-tempo `0.2.0`（vendored core `1.0.1`，schema 1；来源：`status` 头两行 + `.learnark/project.json`）
- 体验者: 独立子 Agent（DeepSeek Harness，独立上下文，非研发者）。只读了 `evaluation/prompts/round-01.md`、`evaluation/harness/learner-brief.md`、`variants/direction-d-tempo/START_HERE.md`、`shared/scenarios/personas.md` 的报告模板段落，以及产品自己的输出。
- 场景: S1 初次进入（P1 小林：会一点 Python，跟教程跑过 `requests`，没写过 Agent；今天约 30 分钟；概念题敢猜、代码题容易卡）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r01-s1\proj`
- 入口: `python runtime\learn.py <命令>`（工作目录 `learning-framework-rnd\variants\direction-d-tempo`）
- 交互预算: ≤10 次，实际使用 **6 次**（6 条 `say`）；真实 LLM 模式，未使用 `--offline`
- 环境: PowerShell，Python 3.14.6，`DEEPSEEK_API_KEY` 已由 `_sandbox\env.ps1` 注入（未写入项目）
- 时间: 2026-11-04 02:32–02:35（真实时间）

下文用 `$P` 表示 `_sandbox\projects\d\r01-s1\proj`；体验者本地命令日志在 `_sandbox\projects\d\r01-s1\c01…c14*.log`（**不是**产品文件，是我自己对终端的留档）。

---

## 实际步骤（命令 + 退出码 + 关键输出摘要）

| # | 命令 | 退出码 | 关键输出（截断） |
| --- | --- | --- | --- |
| 1 | `. _sandbox\env.ps1`；`$env:PYTHONIOENCODING='utf-8'`；`python --version` | 0 | `Python 3.14.6`；`DEEPSEEK_API_KEY` 长度 35，存在 |
| 2 | `learn.py init --goal "能用 Python 独立做出带工具调用的小 Agent" --dir $P` | 0 | `已创建 Tempo 项目`／技能 10 个／卡片 12 张（今天到期）／每周 600 分钟／每次默认 20 分钟／`git: 已提交 ac82591（本地）` |
| 3 | `learn.py start "今天只有半小时" --project $P` | 0 | `[预算] 30 分钟（来源：一句话）`；`[诊断] 首次进入：先用到期卡自测校准等级`；导师 `trainer`；候选表 3 行；`本次计划（≤2 项）`；开场问「Agent 循环的四个阶段是什么？」 |
| 4 | `say "我猜四个阶段是：接收输入 -> 思考/决定下一步 -> 调用工具 -> 观察结果。第二个停止条件我还想不出来，先只答这一问。"` | 0 | **`（导师漏了机器块，已自动补一次；正文保留原回复。）`**；`help_level=1 attempt correct=True`；`agent-loop L0→L1`；`活动完成：是` |
| 5 | `say "靠模型不再要求调用工具、直接给出最终回答？或者设一个最大轮数，到了就强制停。"` | 0 | 又一次 `导师漏了机器块`；`attempt correct=False`；`活动完成：否（仍在进行中）` |
| 6 | `say "连续几轮没有新信息？比如同一个工具反复返回一样的结果……"` | 0 | `attempt correct=True`；`card-0001 记 good：step 0→1，间隔 2 天`；`导师回填的 card-0001 字段与库中不一致（front,back,tags）`；`活动完成：是` |
| 7 | `status --project $P` | 0 | `今日 2026-11-04 · 预算 30 分钟 · 已开始 1/2 项 · 完成 1 项`；`agent-loop L1 observed`，错误标签「停止条件漏了连续无新信息」；`下一步：concept_block · eval-harness（10 分钟，Tier 2）` |
| 8 | `start --project $P`（**没再说分钟数**） | 0 | `上次停在哪：recall_card · agent-loop`；**`[预算] 20 分钟（来源：默认）`**；导师变成 `coach`；计划只剩 1 项；开场要求「把 10 条用例的骨架写进 artifacts/eval-cases.json」 |
| 9 | `say "得先保证题是同一套、评分标准也一样……"` | 0 | `eval-harness L0→L1`；`本周块第 1 步完成（无产物，不计 L3 依据）`；`活动完成：是`；导师随后追问「把 check 从 contains 改成 exact 还算变差吗？」 |
| 10 | `say "不算变差。变的是我的评分标准，不是 Agent……"` | 0 | 仍 `correct=True`、`活动完成：是`；导师要求「用自己的话回述 3–5 句……讲完这一步就算完成」 |
| 11 | `say "一条用例就是固定输入加期望结果和判分方式……"` | 0 | 导师「回述到位」；`下一步（下次做，不排课）：把 10 条用例写进 artifacts/eval-cases.json`；状态仍是 `活动完成：是` |
| 12 | 学习者自己写 `$P\artifacts\eval-cases.json`（10 条 `id/input/expect/check` + baseline 占位） | — | 产品**没有任何回执**：没有命令/提示说"产物已记录"，`status`、`pause`、handoff 都不提它 |
| 13 | `status --project $P` | 0 | `今日 … 预算 20 分钟 · 已开始 2/2 项 · 完成 2 项`；`到期 13 张卡`；`下一步做：transfer_task · guardrails（15 分钟）`（今日计划已 2/2 完成，仍在给 15 分钟下一步） |
| 14 | `pause --note "今天时间到了，明天接着写 artifacts/eval-cases.json 的基线"` | 0 | 写 `.learnark/handoff/latest.md`；`commit ef778e8`，`提交文件：11 个`；`git state: no-remote`；`下次开始：transfer_task · guardrails（15 分钟）` |
| 15 | `doctor --project $P` | 0 | `13 项正常，0 项警告，0 项问题`；其中 **`[ok] git: 工作区干净`** |
| 16 | `git -C $P status --short`（紧接着上一步） | 0 | **`?? .learnark/usage.jsonl`**（未被忽略，`git check-ignore` 退出码 1） |
| 17 | `status --project $P`（新进程，pause 之后） | 0 | 能读回：`交接：.learnark/handoff/latest.md · 下一步：transfer_task · guardrails（15 分钟）`；`journal 48 条事件` |

真实 LLM 调用统计（`$P\.learnark\usage.jsonl`）：**12 次调用**、prompt 24,138 tokens、completion 1,802 tokens、累计 16,689 ms；模型全部记为 `deepseek-flash`。其中 `mentor_update_retried` 事件 **4 条**（对应 6 条 `say` 里的 4 条），即 6 次师生往返产生 12 次模型调用（开场 2 次 + 往返 6 次 + 补机器块 4 次）。

---

## 完成情况

- **开始**: 成功。`init` → `start` 按 `START_HERE.md` 一次走通，没有查任何源码，没有问人。
- **诊断或定位**: 部分成功。产品用「首次进入：先用到期卡自测校准等级」定位，只测了 1 张 recall 卡 + 1 个概念块；**没有问**我的 Python 环境、有没有写过工具调用、目标想拆到哪一步。它写成「诊断完成」（`.learnark/project.json` 里 `diagnosed: true`），但我的画像信息只来自模板默认值（见问题 4）。
- **尝试与反馈**: 成功。共 6 次真实作答（4 次判对、1 次判错后被缩小问题引导、1 次回述）。反馈具体、能指出我漏了「连续几轮无新信息」，错误标签也写进了 `status`。
- **保存/恢复**: 保存成功（`pause` 写出 handoff + 本地 commit `ef778e8`）；**新进程 `status` 能读回**「下一步：transfer_task · guardrails」。**「新进程直接 `start` 恢复」未测试**——今日计划已是 2/2，再 `start` 会开第 3 个活动，超出我模拟的 30 分钟。
- **切换导师**: 未主动执行。产品在两次活动之间**自动**把导师从 `trainer` 换成 `coach`（`start` 输出里只写「本次导师：coach」），我并没有要求切换，也没有被告知为什么。

---

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 我说「今天只有半小时」，系统按 30 分钟安排一整天 | 第一次确实 30 分钟；做了一张卡再 `start`，**预算被静默改成默认 20 分钟**，`status` 也跟着显示 20 分钟 | c07 日志；`journal` seq 2（`minutes:30, matched:"半小时", source:"text"`）与 seq 23（`minutes:20, source:"default"`） |
| 状态页能告诉我"今天还剩多少、做完了没有" | `今日 … 预算 20 分钟 · 已开始 2/2 项 · 完成 2 项`，同一屏又给「下一步 transfer_task · guardrails（15 分钟）」，且理由写「预算 20 分钟内能完整做完」——既像做完、又像没做完 | `$P`… `c11-status2.log`、`c14-status-postpause.log` |
| 活动说完成标准是什么，就按那个标准结束 | 开场写「完成标准是……**并把 10 条用例的骨架写进 artifacts/eval-cases.json**」，但我只答了一句就被标 `活动完成：是`，`artifact:""`；我后来真写了这个文件，产品也**没有任何回执** | `sessions\20261104-023328-coach.md:7`；`journal` seq 34 `activity_completed artifact:""`、seq 35 `block_step_done artifact:"" note:"无产物"` |
| 导师说"讲完这一步就算完成"，那就还没完成 | 导师说完这句时，运行时的记录已经是 `活动完成：是`；我后面两轮回答仍挂在**同一个已完成活动**上 | `sessions\20261104-023328-coach.md:42`；`journal` seq 37/41 的 `activity_id` 仍是 `block-2026-W45-step1-eval-harness` |
| 系统对"我是什么水平"的描述，是我说过的话 | `.learnark/project.json` 写着 `"note": "自述：接触过 Python、调过 API、借 AI 做过 RAG……"`——我从没说过做过 RAG，也没写过 Agent | `.learnark\project.json:27`；`journal` seq 1 `project_initialized` 的 `learner_note` |
| `doctor` 说"工作区干净"就是干净 | `doctor` 报 `[ok] git: 工作区干净`，紧接着 `git status --short` 显示 `?? .learnark/usage.jsonl` | `c13-doctor.log`；`git status --short` 实测；`.gitignore` 里写的是 `.learnark/state/usage.jsonl`（路径不匹配） |
| 输出的"真实 API（deepseek-chat）"就是实际在用的模型 | 每条 `say` 头都写 `真实 API（deepseek-chat）`，但 `usage.jsonl` 12 条全部是 `"model": "deepseek-flash"` | `c03-say1.log` 等；`$P\.learnark\usage.jsonl` |
| 做对一张卡，到期卡就少一张 | 12 →（做完 1 张）11 →（每轮新建"下次到期今天"的卡，且当天同技能不许再练）**13** →（暂停时 `backlog_folded` 把最旧卡 +3 天）12 | c02 / c06 / c11 / c14 的「到期 N 张」；`journal` seq 46 `backlog_folded` |
| 30 分钟、目标是"用 Python 做出小 Agent"，应该至少碰一次代码 | 两次活动分别是 5 分钟 recall 与 10 分钟概念块，**没有一行可运行的 Python**；下一步 `transfer_task · guardrails` 也还是文字任务 | c02 / c07 的「本次计划」；`sessions\*.md` 全文没有代码 |

---

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | **重要** | **同日第二次 `start` 把当日预算从 30 分钟静默改写为默认 20 分钟**，`status` 与后续调度理由都跟着用 20；没有任何提示"你的预算被改了"。同时出现"今日 2/2 项已完成"却仍推荐 15 分钟下一步的自相矛盾。 | `start "今天只有半小时"` → 作答 → `start`（不带分钟数）→ `status` | `journal` seq 2 / seq 23（`budget_set`）；`c07-start2.log`「[预算] 20 分钟（来源：默认）」；`c11-status2.log`「预算 20 分钟 · 已开始 2/2 项」 |
| 2 | **重要** | **导师机器块缺失率 4/6**：运行时每次都要额外补调一次 LLM（6 次往返 → 12 次 API 调用，33% 是重试），并把内部术语「导师漏了机器块，已自动补一次」直接给学习者看。慢的那几轮用户能感觉到停顿。 | 连续 `say` 6 次，观察 `mentor_update_retried` | `journal` seq 6/13/27/36 `mentor_update_retried`；`$P\.learnark\usage.jsonl` 12 行；`c03/c04/c08/c09` 日志首行 |
| 3 | **重要** | **"活动完成"与导师口径、与它自己写的完成标准不一致**：完成标准要求落盘 `artifacts/eval-cases.json`，首答后即 `activity_completed`（`artifact:""`）、`block_step_done`（`artifact:""`）；导师随后仍连问两轮并说"讲完这一步就算完成"；学习者补写的产物**无人认领**（`status`/handoff/`doctor` 都不提）。`journal` 里第 37、41 条 `turn` 仍记在已完成活动上。 | `start`（第二个活动）→ 只答第一问 → `status` → 写完 `artifacts/eval-cases.json` → `status`/`pause` | `sessions\20261104-023328-coach.md:7,42`；`journal` seq 34/35/37/41；`$P\artifacts\eval-cases.json`；`c11-status2.log` |
| 4 | **重要** | **初始化时替我"自述"了我没说过的话**：`.learnark/project.json` 的 learner.note 写「调过 API、借 AI 做过 RAG」，与 P1 画像（没写过 Agent、只跑过 requests 教程）不符，且从未询问。导师若据此调难度，会误判。 | `init …` 后立即读 `.learnark/project.json` | `.learnark\project.json:27`；`journal` seq 1 `project_initialized.learner_note` |
| 5 | 一般 | **`doctor` 误报"工作区干净"**：实际 `.learnark/usage.jsonl` 未被跟踪也未被忽略（`.gitignore` 写的是 `.learnark/state/usage.jsonl`），`pause` 报 `committed=yes` 之后仓库仍是 dirty。 | `pause` → `doctor` → `git status --short` | `c13-doctor.log`「[ok] git: 工作区干净」；`git status --short` → `?? .learnark/usage.jsonl`；`git check-ignore` 退出码 1 |
| 6 | 一般 | **模型披露不一致**：CLI 头写 `真实 API（deepseek-chat）`，`usage.jsonl` 12 条全是 `deepseek-flash`。学习档案要长期留存，这一栏应可信。 | 任意 `say`，对比首行与 `usage.jsonl` | `c03-say1.log`；`$P\.learnark\usage.jsonl` |
| 7 | 一般 | **导师被自动替换且不解释**：第一次活动 `trainer`，第二次 `coach`，`start` 只打印「本次导师：coach」。`START_HERE` 说切换要自己 `switch`，我没切过。 | 连续两次 `start` | `c02-start.log`「本次导师：trainer」；`c07-start2.log`「本次导师：coach」 |
| 8 | 一般 | **到期卡数量不可解释地反向增长**：12→11→13→12；每轮回答新建"下次到期今天"的卡，又被"同一技能当天不重复"挡掉，暂停时触发 `backlog_folded`（最旧卡 +3 天）。初学者会以为"我越学欠得越多"。 | 跑完一轮 → `status`；`pause` 后再 `status` | `c02`「12 张」、`c06`「11 张」、`c11`「13 张」、`c14`「12 张」；`journal` seq 46 |
| 9 | 一般 | **学习者可见输出夹带内部机制**：`Tier 1/T2`、`总分 0.383`、`help_level=1`、`机器块`、`card-0001 字段与库中不一致`、`leech`、`backlog_folded`。更困惑的是候选表按"选择顺序"排，但 2 号候选总分 0.467 **高于**被选中的 1 号 0.383（因为先按 tier），表里没有一句话说明"先看层级再看分数"。 | 看任意一次 `start` 的候选表 | `c02-start.log`（0.467 vs 0.383）；`c05-say3.log`（card-0001 字段不一致） |
| 10 | 一般 | **30 分钟、目标"用 Python 做出带工具的 Agent"，全程零代码**：两次活动都是文字/概念，下一步的 `transfer_task` 仍是文字任务。对"代码题容易卡"的我，没有任何可运行的东西可以试错，"卡在哪"也就无从暴露。 | 完成 `init`+2 个活动后看 `status` | `c02`/`c07` 的「本次计划」；`$P\sessions\*.md` 无代码块 |
| 11 | 一般（环境，非产品缺陷） | **直接读 `.learnark\journal\events.jsonl` 中文乱码**（`Get-Content` 默认编码把 UTF-8 当 GBK）；而产品 CLI 输出本身正常。影响的是"我自己核对记录"这一步，必须显式 `-Encoding utf8` 或用 Python 读。 | `Get-Content $P\.learnark\journal\events.jsonl` | 本次调查的第一个 `ConvertFrom-Json` 报错；改用 Python `io.open(..., encoding='utf-8')` 后正常 |

> 说明：**没有出现阻塞级问题**——`init/start/say/status/pause/doctor` 全部退出码 0，真实 API 无报错、无超时、未降级到离线。

---

## 使用负担

- **师生往返**: 6 次（上限 10）
- **产品命令**: 14 条（`init` 1 + `start` 2 + `say` 6 + `status` 3 + `pause` 1 + `doctor` 1）；另有约 8 条我自己的检查命令（`git status`、`git log`、读文件、统计 journal），这些**不是**普通学习者必须做的
- **需要阅读的文档**: 3 处（`round-01.md`、`learner-brief.md`、`START_HERE.md`），外加产品在项目里自动生成的 `AGENTS.md`（我写产物时被注入，不是主动查的）
- **总耗时**: 真实墙钟约 3 分钟；按产品的活动时长累计约 15 分钟（5 分钟卡 + 10 分钟概念块），离"今天 30 分钟"还有一半没用完——但 `status` 已经显示"2/2 项完成"
- **不清楚的地方**（按出现顺序）:
  1. 第一次答完就看到「导师漏了机器块」，我不知道那是什么、我的回答算不算数；
  2. 「导师技能信号…运行时未采纳」——到底加没加分？
  3. 第二次 `start` 后我的"半小时"变成 20 分钟，是不是我操作错了？
  4. 导师说"讲完这一步就算完成"，可页面已经显示完成——我还该不该答？
  5. 我按它说的写了 `artifacts/eval-cases.json`，没有任何地方显示"收到了"；
  6. `status` 说 2/2 完成，却又给 15 分钟下一步——今天到底结束了没有？

---

## 结论

- **是否完成场景目标: 是（有保留）**。S1 要求的"首次进入 → 诊断/定位 → 至少一次真实尝试 → 得到反馈 → 查看 status → 保存"全部走通，真实 LLM 导师可用、能识别我的漏洞并给出具体纠正，`pause` 的交接与跨进程 `status` 恢复都成立。保留在于：诊断只是刷到期卡、全程没有代码、活动"完成"的判定与它自己写的完成标准不一致，且我按它要求补的产物没有任何回执——所以"知道自己在哪"这件事，`status` 只对了一半。
- **最需要修的一件事**: **当日预算与计划的一致性**——同一天第二次 `start` 不得静默把 30 分钟改写成 20 分钟，`status` 必须同时给出"今日还剩多少分钟 / 计划还剩几项"，并让"2/2 完成"与"下一步 15 分钟"二者只有一种成立。Tempo 的全部价值都押在"1 次交互内告诉你做什么、为什么是它"；预算这个数字一旦自己会变，后面每一条调度理由都失去可信度。
- 次优先：问题 3（活动完成判定 vs 完成标准 vs 导师口径三方不一致）——它直接决定学习记录是否诚实，对"证据驱动"的卖价伤害更大，只是这次没有阻塞我。

**未测试**（不推测为通过）：新进程直接 `start` 恢复、`switch` 切换导师、`review`/`due`/`plan`/`skills`/`export`/`sync` 的完整行为、跨天 SRS 与 `backlog_folded` 的长期效果、多日 30 分钟预算累计、离线模式。
