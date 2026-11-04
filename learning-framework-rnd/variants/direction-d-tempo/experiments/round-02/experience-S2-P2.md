# 体验报告 — direction-d-tempo round-02 S2（P2 阿哲）

- 版本: `direction-d-tempo 0.2.1` / `learncore 1.0.1` / schema 1（`learn.py version` 输出）
- 体验者: 独立子 Agent（DeepSeek Harness 会话，deepseek-flash 上下文；独立上下文，非研发者；未读 runtime 源码、design、mentors、tests、历史报告内容）
- 场景: S2 诊断与错误反馈（P2 阿哲 / 20 分钟 / 真实 LLM API）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r02-s2\proj`
- 入口: `python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-d-tempo\runtime\learn.py <命令>`（cwd 在 variant 根）
- 交互预算: **10 次，实际 7 次**（`say` 7 次）；另有 18 条 CLI 命令、公开文档 4 份
- 导师模式: 真实 API（`offline=false`，全程**未使用** `--offline`）。配置模型 `deepseek-chat`，实际返回 `deepseek-flash`（`start`/`say`/`status` 均披露）
- 体验时间: 2026-11-04 02:54:58 – 02:57:08（真实钟，约 2 分 10 秒；产品按活动时长计预算 15/20 分钟）
- API/导师故障: 无失败。2 次 `mentor_update_retried`（`ok=true`，静默补问一次）未造成缺证据

## 0. 读过的公开材料

只读了：`evaluation/prompts/round-02.md`、`evaluation/harness/learner-brief.md`、`variants/direction-d-tempo/START_HERE.md`、`shared/scenarios/personas.md`（仅为取报告模板，任务卡要求）。
未读：`runtime/` 源码、`design*`、`mentors/`、`curriculum/`、`tests/`、其他方向、历史实验报告内容。
另外按学习者可见范围读了产品自己生成的 `AGENTS.md`、`sessions/*.md`、`.learnark/handoff/latest.md`、`.learnark/journal/events.jsonl`、`.learnark/state/cards.json|skills.json`，作为观察证据，未手工修改任何状态文件。

## 1. 实际步骤（命令 + 关键输出摘要）

> 每条命令前统一执行 `. C:\Users\YK\Desktop\LearnArk\_sandbox\env.ps1` 并设 `$env:PYTHONIOENCODING='utf-8'`。以下摘要为原文截取；完整原文在会话文件与 journal 中。

### 1) `version`
```
direction-d-tempo 0.2.1 · learncore 1.0.1 · schema 1
```

### 2) `init --goal "能用Python做出会调用工具的Agent应用" --dir <proj>`
```
已创建 Tempo 项目：...\proj
模板 agent-dev · 技能 10 个 · 卡片 12 张（今天到期）
git: 已提交 11f86c2（本地）
下一步：python learn.py start --minutes 20
```

### 3) `start --minutes 20`（第一次进入）
关键输出：
```
[诊断] 首次进入：先用到期卡自测校准等级；自述（“我学过”）不计等级，只看行为证据。
本次导师：trainer · 高频练习导师
候选：1 recall-card-0001 agent-loop 5m T1 0.400 薄弱度 选中
      2 block-2026-W45-step1-eval-harness eval-harness 10m T2 ...
为什么是它：到期组：该卡逾期 0 天，先清到期；...
本次计划（≤2 项）：1) recall_card·agent-loop（5 分钟） → 2) concept_block·eval-harness（10 分钟）
这次做 5 分钟回忆抽卡：不看卡背，用一句话答出 Agent 循环的四个阶段，再答三种停止条件。
第一问：Agent 循环的四个阶段是什么？
```
观察：**“定位/诊断”被实现为一张内容抽卡，没有询问背景或让学习者自述**；P2 需要“验证它能不能看出我不会”，但首问是记忆题。

### 4) `say` #1 —— 自信但含 RAG=记忆 的错误答案
学习者原文（截取）：
> 这个我懂。Agent 就是 LLM 加工具加记忆。循环就是：先检索知识库，再让模型推理规划……记忆那块就是 RAG，把文档塞进向量库就完事了。

导师：
```
不对。四个阶段是“观察/接收输入 → 思考/决定 → 行动/调用工具 → 观察结果再循环”，你答的是组件和一条具体流水线；停止条件也漏了轮次上限和“连续无新信息”。
下一问：循环的三种停止条件是什么？
提示级别 0（独立完成） · 本题未判对
```
观察：错误被**具体命名**（组件/流水线混淆、漏停止条件）；但对 RAG=记忆 只在机器块 `misconception` 中记录，**对话里没有点名**。

### 5) `say` #2 —— 部分改对、仍自信
导师：
```
前两条对；第三条错，工具报错通常应把错误当观察结果回灌继续循环，真正的第三种是“连续多轮没有新信息”。
下一问（最后一问）：工具报错后，循环里下一步该做什么？
提示级别 0（独立完成） · 本题未判对
- card-0001 记 hard
- 连续 2 次失败：自动生成误解卡 card-99bfe3（正反面需改写）
```
观察：第二次反馈**针对新答案**，具体；但**直接把正确答案说出来了**，且仍记 `help_level=0`。

### 6) `say` #3 —— 按导师原话复述
学习者原文：> 就是像你说的，把工具报错当成观察结果回灌给模型，让它继续循环。这个我其实一直懂，就是刚才没答全。

导师：> 对。工具报错要作为观察结果回灌给模型……**时间到，收尾**：本轮两问都未一次答全……

记录：
```
提示级别 2（分步引导） · 本题未判对 · 证据：观察记录（受助完成，只算接触）
- card-0001 记 again
- 连续 2 次失败：自动生成误解卡 card-b5e6d8（正反面需改写）
- 活动完成：否（仍在进行中）
```
观察：**同一轮对话里导师说“对”，记录却“本题未判对”并记 again**；`help_level` 从 0 跳到 2，但与学习者实际请求的“提示”不符。导师文本自称“时间到”，运行时不关闭活动。

### 7) `status` / `status --json`（第一次）
```
今日 预算 20 · 已用 5 · 剩余 15 · 已排 1/2（完成 0 项）
到期 13 张卡（最久逾期 0 天）
agent-loop L0 observed  wrong_tags: 把组件与固定流水线当成循环四阶段，停止条件漏轮次上限与连续无新信息、
                            停止条件误把工具报错当终止，且把记忆等同于RAG、停止条件漏了轮次上限与连续无新信息；
                            把工具报错当终止条件
上次活动：recall_card · agent-loop（2026-11-04 02:55）
会话：20261104-025502-trainer · sessions/20261104-025502-trainer.md · 3 轮
下一步（现在）：concept_block · eval-harness（10 分钟，Tier 2）
```
`status --json` 中 `skills[]` 有 `evidence_level` 和 `wrong_tags`，**没有任何 `help_level` 字段**（`$json -match 'help_level'` 为 `False`）。

### 8) `say` #4 —— “别绕了，直接给我答案/代码”
学习者原文：> 我卡在不知道怎么把这些真正写成代码。别绕了，直接把答案和完整代码给我吧，我要那种复制就能跑的。

导师：
```
本轮到此为止，不再加题。你的卡点是“知道概念但落不到代码”，这属于下一步的动手环节，不在这次 5 分钟 recall 里解决。
已过/未过：未过（两问均未一次答全，且概念里混入了 RAG 等于记忆的误解）。下一轮建议只做一件事：写一个 20 行的最小循环，把工具报错当观察结果回灌。
提示级别 0（独立完成）
- 连续 2 次失败：自动生成误解卡 card-9056f0（正反面需改写）
```
观察：**守住“不代写”**，并第一次在对话中明确点出 RAG=记忆 的误解、以及“知道概念但落不到代码”。但学习者明确求助，仍记 `help_level=0 / assisted=false`。

### 9) `start`（第二次活动）
```
上次停在哪：recall_card · agent-loop（2026-11-04 02:55）
[导师] trainer → coach：按活动类型绑定导师（本次是概念块），不是随机切换。
1 block-2026-W45-step1-eval-harness eval-harness 10m T2 0.533 选中
2 block-2026-W45-step3-guardrails 15m T2 0.525 排除：15 分钟活动超出剩余 5 分钟
3 block-2026-W45-step2-eval-harness 8m T2 0.432 排除：8 分钟活动超出剩余 5 分钟
本次可用 15 分钟；活动上限 20 分钟。
请先回答一句——如果你改了一版提示词，怎么判断它比上一版更好还是更差？
```
观察：上一个 5 分钟卡**未完成就被换掉，没有“活动未完成”提示**；候选行里的“剩余 5 分钟”与同屏“剩余 15 分钟”口径不说明（推测是选完 10 分钟后的投影，但界面未写）。

### 10) `say` #5 —— 主观感受 + prompt=工具调用 的第二个误解
学习者原文（截取）：
> 改完提示词我就随便问几个问题，感觉回答更顺……工具调用也不用那么麻烦，我在 prompt 里写清楚工具列表，模型就会自动调用，不需要我解析和回传结果。

导师：
```
“感觉更顺”正是基线要解决的问题……（给出完整例子：固定 10 条 → 答对 7/10 → 改后 8/10）
至于工具调用：模型只输出“要调哪个工具、参数是什么”，真正执行和把结果回传，仍需你的代码完成——这点先记下，不在本次展开。
请用一句话复述：基线指标的作用是什么？
提示级别 1（小提示） · 本题未判对
```
观察：第二个误解也被**具体纠正**；但“这点先记下”**没有落进状态**：`status` 中 `tool-calling` 仍是 `self_report`、无错误标签。

### 11) `say` #6 —— 几乎逐字复述导师刚给的完整答案
学习者原文：> 基线指标就是先固定一组输入和期望答案，记录一个可比的分数；改完提示词再跑同一组……

导师：> 复述准确……本次到此收尾。

记录：
```
提示级别 1（小提示） · 本题判对
- eval-harness L0→L1（正确 + help_level≤1；每天最多 +1）
- 新卡已建：card-4ebe26（eval-harness，下次到期今天）
- 本周块第 1 步完成（无产物，不计 L3 依据）
- 活动完成：是
```
journal 事件 `level_change` 的 `reason` 是 **`independent-correct`**，`help_level=1`。导师自己的 `skill_signal.note` 却写“经一次方向提示后能准确复述……**尚未独立产出用例集**”。

### 12) `say` #7 —— 追问下一步 + 再次要代码
学习者原文：> 那我下次到底先做什么？你让我写 20 行最小循环，status 又让我重抽卡。别绕了，直接把我下一步要跑的代码给我吧。

导师：
```
……但下一步的代码我不能代写：本次活动只做概念复述，不产出代码；而且“写 20 行最小循环”和“重抽卡”是两件不同的事，我不替你决定哪件优先。
下次第一步建议：先为那 10 条问题各写一行“输入 → 期望要点”，跑一遍记下答对数，作为基线。
提示级别 0（独立完成） · 本题判对
- 新卡已建：card-dd5e8f
```
观察：再次**守住不代写**，但把“先做什么”的决定推回给学习者；且这是一轮**纯提问、没有作答**，却被记为 `correct=true / help_level=0`，还生成一张新卡。

### 13) `status` / `skills`（收尾复核；`skills` 那次输出在 `say` #6 后，`status --json` 在 `say` #7 后）
```
今日 预算 20 · 已用 15 · 剩余 5 · 已排 2/2（完成 1 项）
到期 13 张卡（最久逾期 0 天）
eval-harness L1 observed  wrong_tags: 以主观感觉代替固定用例与基线指标
本周块：block-agent-dev-2026-W45 · 步骤 1/3 · artifact 空
下一步（下次）：recall_card · -（5 分钟，Tier 1）
  理由：今天可用的活动模板/技能已覆盖或预算不足
卡片：17 张 · 到期 13 张 · leech 1 张 · 待改写 3 张      ← say #6 后；say #7 后为 18 张
```
`status --json` 的 `next.activity_id` 是占位符 **`next-due`**，`next.skill = "-"`。

### 14) 只读核对产品状态（非 CLI 修改）
- `.learnark/state/cards.json`：18 张；`kind=misconception` 7 张，其中 **card-99bfe3 / card-b5e6d8 / card-9056f0 三张 front 完全相同**（`你上次把「Agent 循环与停止条件」误解成什么？`）。
- journal：`card_created` 6 次（3 张 agent-loop 误解卡 + 3 张 eval-harness 新卡）；`backlog_folded` 3 次，把 card-0002/0003/0004 各推后 3 天（2026-11-07）；`card_echo_mismatch` 3 次。
- `skills.json`：除 agent-loop/eval-harness 外，其余 8 个技能均为 `evidence_level=self_report`，但 `project.json` 的 `learner.self_report=[]`，`status` 同时写“尚未记录学习者自述”。

### 15) `pause --note "..."`
```
已保存交接：...\.learnark\handoff\latest.md
- 上次停在哪：concept_block · eval-harness
- 试过什么：今天已排 2 项，预算 20 分钟（已用 15，剩 5）；到期卡 12 张
- 哪里不稳：agent-loop（L0）、eval-harness（L1）
- 产物：无
- 下一步：下次 start 先清到期卡
- 未决问题：agent-loop 的错误标签：（一长串，含重复）……
git state: no-remote (written=yes, committed=yes, pushed=no) commit d6fc555
```
同一时点：`pause`/`start` 报“到期卡 12 张”，`status` 报“13 张”。

### 16) 新进程 `start`（恢复验证）
```
上次停在哪：concept_block · eval-harness
交接下一步：下次 start 先清到期卡
交接不稳：agent-loop（L0，lapses 0）、eval-harness（L1，lapses 0）
今日已排 2/2 项（完成 1 项） · 预算 20 分钟（已用 15，剩 5）。
今天不再排新活动——这不是欠账……
现在可以 pause 结束并保存；想提前清到期卡可以显式 review；或明天直接 start。
```
恢复成功；但**没有给出“具体做哪张卡/哪个活动”**。

## 2. 完成情况

| 环节 | 结果 | 说明 |
| --- | --- | --- |
| 开始 | 成功 | `init` + `start` 一次成功；候选表、理由、导师开场齐全 |
| 诊断/定位 | **部分成功** | 首问是内容抽卡，不是背景/自述/动手诊断；但错误被逐条具体命名，最后明确“知道概念但落不到代码” |
| 尝试与反馈 | **部分成功** | 3 次真实尝试；第二次反馈针对新答案；但“对”与“未判对”矛盾，help_level 与导师实际披露不符 |
| 直接要答案 | **守住** | 两次（`say` #4、#7）拒绝代写代码/答案，并说明原因 |
| 保存 | 成功 | `pause` 写 handoff、提交 `d6fc555` |
| 新进程恢复 | 成功 | 新进程 `start` 能读出上次停在哪、交接、预算 |
| 切换导师 | 自动成功 | `trainer → coach`，说明“按活动类型绑定，不是随机切换”；未手动 `switch` |
| `status` 可读性 | **部分** | 能看到“哪里不会”（wrong_tags），**看不到“用过什么帮助”**；下一步是占位 |

## 3. 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 进入后 1 屏内知道“今天做什么、为什么是它” | 是；有候选表、主因子、理由、计划 ≤2 项 | 步骤 3 输出 |
| 20 分钟内至少动手一次，向“做出 Agent”推进 | 否；**0 行代码、0 产物**，只做了口头抽卡 + 概念复述；块进度 1/3、artifact 空 | 步骤 13；`status --json.block` |
| “它能不能看出我不会” | 部分；能指出具体概念错误，最后点名“知道概念但落不到代码”；但直到第 4 轮才在对话中说 RAG 误解，且未用动手任务验证 | 步骤 4/8 导师原文 |
| 提示逐级（先方向、再关键步、最后示例） | **否**；第 1 轮就直接给出完整正确答案，第 5 轮直接给完整例子；help 仍记 0/1 | 步骤 4、10 导师原文；journal seq 7/38 |
| 帮助等级在 `status` 可见 | **否**；`status`/JSON 无 help_level，只有 session/journal 里有数字（且无图例） | `status --json`（`help_level` 不出现）；session 记录行 |
| “别绕了给答案”被守住，且记录帮助程度 | 守住；但 help_level=0、assisted=false，未记录“被拒绝的求助” | 步骤 8/12；journal seq 27/55 |
| 保存后换进程能继续 | 是；handoff + `start` 正常 | 步骤 15/16 |
| `status` 能看出“哪里不会” | 是，但错误标签是追加的长串、含重复；`skills` 视图截断到约 30 字 | 步骤 7/13；`skills.json` |

## 4. 问题

| # | 严重度 | 描述 | 复现步骤 | 证据 |
| --- | --- | --- | --- | --- |
| 1 | **重要** | **“听懂/复述”被记为独立正确并升级**：学习者几乎逐字复述导师刚给的完整例子，仍 `correct=true, help_level=1`，`level_change.reason=independent-correct`，eval-harness L0→L1；导师自己的 note 却写“尚未独立产出用例集”。`status` 完全不显示 help_level，外部无法复核。 | 1) `start` 进 concept_block；2) 导师给出“10 条→7/10”完整例子；3) 学习者复述；4) 看 `say` 记录与 `level_change` | `sessions/20261104-025557-coach.md:31-45`；`.learnark/journal/events.jsonl` seq 44/47 |
| 2 | **重要** | **同一轮“对”与“本题未判对”矛盾**：`say` #3 导师可见文本说“对”，记录却 `correct=False`、card 记 `again`、help_level 从 0 跳到 2。学习者会认为自己过了；系统却判失败。 | 按步骤 6 复现；对比 `## 导师` 与 `## 记录` | `sessions/20261104-025502-trainer.md:44-60`；journal seq 17/19 |
| 3 | **重要** | **纯提问轮被判 correct 并生成卡片**：`say` #7 没有任何作答，只问“下一步做什么/给代码”，记录 `correct=true, help_level=0`，`skill_signal.level_hint=2 basis=independent`，并新建 `card-dd5e8f`。本次只是被“同一技能每天最多 +1”挡住；否则这一轮还会再贡献一次 correct（推测，依据事件与规则）。 | 完成一个活动后 `say` 一句问题；看记录 | `sessions/20261104-025557-coach.md:47-63`；journal seq 53/55 |
| 4 | **重要** | **同一误解自动生成 3 张完全相同的卡**：card-99bfe3 / b5e6d8 / 9056f0 的 front 都是“你上次把「Agent 循环与停止条件」误解成什么？”，且都标“正反面需改写”。学习者被要求改 3 张同题卡。20 分钟内卡片 12→18。 | `say` 连续 3 次判错同一张卡；查 `cards.json` | `.learnark/state/cards.json`；journal `card_created` seq 16/23/31 |
| 5 | **重要** | **积压折叠静默改到期日**：项目初始就 12 张当天到期、`backlog_cap=12`；一有新卡即触发 `backlog_folded`，把 card-0002/0003/0004 推后 3 天。`status`/`pause` 都不提“有卡被推迟”，只有 journal 有。 | 新项目 `start` 后 `say` 两次；查 journal | journal `backlog_folded` seq 24/32/43；`project.json.limits.backlog_cap=12` |
| 6 | **重要** | **未完成活动被静默换掉且计满时长**：5 分钟 recall 卡在导师“时间到”后仍未完成（`活动完成：否`），`start` 直接开启下一个活动，没有“未完成/将放弃”提示；5 分钟已计入预算，最终完成 1/2 项。 | 按步骤 6 出现“时间到”；再 `start` | `sessions/20261104-025502-trainer.md:48-60`；`status --json.today.items`（recall done=false） |
| 7 | **重要** | **“下一步”三处冲突且 status 是占位符**：status 显示 `recall_card · -（5 分钟）`、JSON `next.activity_id=next-due`；trainer 让“写 20 行最小循环”；coach 让“写 10 条输入→期望要点”，并说“我不替你决定哪件优先”。P2 不知道下次先做什么。 | 完成活动后 `status`；对比两位导师建议 | `status`（步骤 13）；`status --json.next`；coach 会话 51 行 |
| 8 | 一般 | **“先记下”的误解没落库**：coach 对“prompt 写工具列表=自动调用”说“这点先记下”，但 `tool-calling` 仍 `self_report`、0 个错误标签。 | 按步骤 10 回答；`status`/`skills` 查 tool-calling | 步骤 13 `skills` 输出；`.learnark/state/skills.json` |
| 9 | 一般 | **错误标签重复膨胀、视图截断**：agent-loop 有 4 条标签，其中两条近义重复；`status` 显示成一长串，`skills` 只截前约 30 字；handoff 的“未决问题”也是同一长串。 | 连续答错同一卡；看 `status`/`skills`/handoff | `.learnark/state/skills.json`；`handoff/latest.md` |
| 10 | 一般 | **默认 `self_report` 与“无自述”自相矛盾**：`learner.self_report=[]`、note 写“尚未记录学习者自述”，但 8 个技能初始 `evidence_level=self_report`。用户会以为系统记了自己“学过”。 | 新项目 `status --json` | `project.json.learner`；`skills.json` |
| 11 | 一般 | **到期卡数口径不一致**：同一时点 `status` 13 张，`start`/`pause` 12 张，`cards.json` 中 due 日期为 2026-11-04 的也是 12 张。 | 连续执行 `status`、`pause`、`start` | 步骤 7/13/15；`cards.json` |
| 12 | 一般 | **内部实现细节泄漏到学习者记录**：session 中出现“导师回填的 card-0001 字段与库中不一致（front,back,tags），按库中卡片判级”“解除 leech 改写要求”“导师 skill_signal 高于当前等级：只记录，不采纳”等；候选行“超出剩余 5 分钟”与同屏“剩余 15”未说明是投影。 | 读 session 文件 | `sessions/20261104-025502-trainer.md:39,57,76-78`；`sessions/20261104-025557-coach.md:62` |
| 13 | 一般 | **首会无动手/无产物**：P2 目标是“写出能调用工具的小 Agent”，20 分钟里没有写一行代码，块进度 1/3、artifact 空；导师自己也说“不在这次 5 分钟 recall 里解决”。 | 走完 20 分钟 | `status --json.block`；步骤 8 |

**阻塞问题：无**（无启动失败、无 API 失败、无状态损坏）。

## 5. 使用负担

- 师生往返：**7 次**（预算 10；brief 通用上限 12）
- CLI 命令：**18 条**（`version` 1、`init` 1、`start` 3、`say` 7、`status/status --json` 4、`skills` 1、`pause` 1）
- 需要阅读的文档：**4 份**（任务卡、learner-brief、START_HERE、personas 模板）；另有产品生成的 `AGENTS.md` 被自动注入
- 真实耗时：约 2 分 10 秒；产品口径“已用 15/20 分钟”（按活动时长，不按真实钟）
- 不清楚的地方：
  1. `提示级别 0/1/2` 各代表什么？为什么“直接给完整答案”是 0，“复述”是 1，“按导师原话补一句”却是 2？
  2. 导师说“对”，记录说“本题未判对/again”，到底算过没过？
  3. 三张同题误解卡都要“正反面改写”，先改哪张？改写要求和标准是什么？
  4. 下次到底先做什么：`status` 的 `recall_card · -`、trainer 的“20 行最小循环”、coach 的“10 条用例”，三选一没有仲裁。
  5. 为什么“到期 13 张”和“12 张”同屏不一致？被折叠推后 3 天的卡为什么没有任何提示？
  6. 5 分钟卡只聊了 3 轮、真实 25 秒就说“时间到”，这算完成还是失败？5 分钟为什么照扣？

## 6. 做得好的地方（对照）

- 错误命名具体：四阶段 vs 组件/流水线、停止条件、工具报错回灌、RAG=记忆、prompt≠工具执行，均被点名，不是泛泛表扬。
- 两次“直接给答案/代码”都守住边界，没有代写，并说明“下一步是动手环节”。
- `status` 能列出错误标签和证据级别（observed/self_report），不是只报“已掌握”。
- 新进程恢复可靠：`pause` 的 handoff 含上次停顿、预算、不稳技能、下一步；新进程 `start` 能读回。
- 导师切换有解释（按活动类型绑定），不是静默随机换人。
- 模型披露诚实：配置 `deepseek-chat`、实际 `deepseek-flash` 同时显示。

## 7. 结论

- **是否完成场景目标：是（流程）/ 部分（诊断质量）**。开始→多次尝试→具体反馈→保存→新进程恢复都走通；但 S2 的核心“能不能看出我不会、并把‘听懂’与‘会做’分开”只达成一半：
  - 它确实指出了具体错误，并在第 4 轮说出“知道概念但落不到代码”；
  - 但**没有用任何动手任务验证**，且把“复述导师刚给的答案”判成 `independent-correct` 并升到 L1；`status` 又不显示帮助等级，外部无法复核；
  - 同一轮“对/未判对”矛盾、纯提问轮被判对、三张重复误解卡、5 分钟未完成活动照扣，都会直接损害学习者对诊断的信任。
- **最需要修的一件事**：把 `help_level` 从“导师自报的数字”改成**可核对的事实记录**（导师这一轮实际透露了哪一步/是否给出完整答案/学习者是否复述或抄用），并在 `status` 里展示；否则“复述=掌握”会持续污染等级与诊断结论。
- 对 P2 的 20 分钟目标而言，第二优先是**给“下一步”一个唯一、可执行的出口**（具体活动/卡片/产物路径，而不是 `recall_card · -` + 两位导师三套建议）。

### 证据索引

> 以下路径默认相对于项目根 `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r02-s2\proj`。
- 项目：`C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r02-s2\proj`
- 会话 1：`sessions/20261104-025502-trainer.md`
- 会话 2：`sessions/20261104-025557-coach.md`
- 交接：`.learnark/handoff/latest.md`
- 权威事件：`.learnark/journal/events.jsonl`（turn/attempt：seq 9/12/17/19/27/38/44/46/53/55；`level_change` 47；`activity_completed` 50；`card_created` 16/23/31/41/48/56；`backlog_folded` 24/32/43）
- 状态：`.learnark/state/cards.json`、`.learnark/state/skills.json`、`.learnark/project.json`
