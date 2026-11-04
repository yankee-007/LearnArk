# 体验报告 — direction-c-atelier round-05 S5（P3 Mia，严格 20 分钟）

- 版本: 0.2.3（learncore 1.0.2 · schema 1；`START_HERE.md` 标注 0.2.3，`.learnark/project.json` 里 `variant.version=0.2.3`、`core_version=1.0.2`）
- 体验者: 独立子 Agent（DeepSeek Harness / deepseek-flash 上下文，独立会话）；非研发者，未参与该方向开发
- 场景: S5 短时与返学（P3 Mia：两周前学过一点 function calling，细节忘了；今晚只有 20 分钟；不想开始大课程）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r05-s5\proj`
- 入口: `python "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-c-atelier\runtime\learn.py" <cmd>`（cwd 在项目目录内；只用公开命令）
- 交互预算: 场景卡 12 次；本轮任务收紧为 **≤6 次**；**实际使用 4 次**
- 时间: 2026-11-04 12:21:56 → 12:23:16（+08:00），产品交互约 **80 秒**；"20 分钟"按任务要求用学习者自然语言给出（未用外部计时器伪造 20 分钟）
- 只读范围: 本任务卡、`learner-brief.md`、`START_HERE.md`、`personas.md`；未读 `runtime/`、`design.md`、`mentors/`、`curriculum/`、`tests/`、`experiments/`、其他方向文件；未改产品代码/测试/状态文件（只通过公开命令写项目）
- 状态: 完成，无阻塞；**全程真实 API**（`doctor` 显示 `llm：mode=api key=yes`，`model=deepseek-flash`，`synthetic: false`），无支付/HTTP 错误

## 1. 环境准备（每条新命令都重跑）

```powershell
. C:\Users\YK\Desktop\LearnArk\_sandbox\env.ps1
$env:PYTHONIOENCODING='utf-8'
$LA = "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-c-atelier"
cd "C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r05-s5\proj"
```

`init` 输出（关键行）：

```
已创建 Atelier 学习项目：C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r05-s5\proj
目标：Agent 开发
模板：Agent 开发 · 四周最小闭环（agent-dev） · 每周约 12 小时 · 计划 plan-v1 v1（10 步）
```

## 2. 实际步骤（命令 + 关键输出摘要）

### 2.1 建项目（命令 1）

```
python "$LA\runtime\learn.py" init --goal "Agent 开发" --dir "C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r05-s5\proj"
```

- 退出码 0，2 秒内完成；默认周预算是 **12 小时**、计划 **10 步 / 4 周**。
- 普通学习者（今晚 20 分钟、每周 1–2 小时）在这个默认值面前没有任何被问询或替代入口。

### 2.2 先不带分钟数 `start`（命令 2，用于任务 6 的对照）

```
python "$LA\runtime\learn.py" start
```

```
== Atelier 多导师工作室 · Agent 开发 · 四周最小闭环 ==
目标：Agent 开发 · 每周约 12 小时

计划：plan-v1 v1（权威：planner） · 进度 0/10 步
  · 当前目标：w1-agent-loop 说清 Agent 与单次问答的差别

上次停在哪：尚无学习记录（首次进入）

这一轮该找谁：策划导师 planner
  · 为什么：首次进入：planner 用 ≤4 轮诊断确认目标与周时长，再按计划移交
  · 首次诊断（每条 ≤1 分钟，答不出具体动作一律记 self_report）：
    - probe-d1：工具调用失败，第一步看什么（诊断题，不提供参考答案）
    - probe-d2：检索与记忆差在哪（诊断题，不提供参考答案）
    - probe-d3：凭什么说改好了（诊断题，不提供参考答案）
```

- 不带 `--minutes` 时：**没有本次会话时长**、没有"只做一个活动"的任何提示，默认仍是 12 小时/周 + 10 步。
- `start` 自己列出了 3 道诊断题（probe-d1/d2/d3），这为后面"诊断是否兑现"留下了对照。

### 2.3 带 `--minutes 20` 的 `start`（命令 3）

```
python "$LA\runtime\learn.py" start --minutes 20
```

唯一差异（当前目标那行）：

```
  · 当前目标：w1-agent-loop 说清 Agent 与单次问答的差别（本次按 20 分钟裁剪，只做一个活动）
```

- 计划版本、周预算、步骤数都没变；`--minutes` 只加了一行显示（与 `START_HERE.md` §7 "`--minutes` 目前只影响提示与展示" 一致）。
- 学习者看到"12 小时/周"和"20 分钟"同时出现，没有任何解释两者关系的话。

### 2.4 第 1 次发言（命令 4，学习者往返 #1）

```
python "$LA\runtime\learn.py" say "今天只有二十分钟，上次学过一点 function calling，但忘了，继续吧"
```

planner 回复（全文，602 字符）：

> 先确认一件事再往下走：你说的「上次学过一点 function calling」，我这边没有任何上一轮的交接记录（`known` / `do_not_redo` / `open_loops` 都缺失），所以我不确定上次具体做到哪、卡在哪。交接不完整，我不替你补全。
>
> 今天二十分钟，我建议只做一件事：把「Agent 和单次问答差在哪」用自己的话说清四要素，做到能复述就收工。理由是你计划里 `w1-agent-loop` 就在这一步，而 function calling 只是它的实现手段——先分清差别，再写伪代码才不会背名词。
>
> 两个问题，回答完就开工：
> 1. 这周实际能投入几小时？计划里写的是 12 小时，今天只有 20 分钟，两者差得有点远，我需要知道真实数字才能决定要不要砍范围。
> 2. 你记忆里「上次学 function calling」大概是在哪一步停的——是看过概念，还是动手写过调用？

本轮记录行：

```
本轮记录：帮助等级：独立完成 ｜ 下一步：学习者回答周可用小时数与上次停点后，进入 w1-agent-loop 复述四要素
计划：本轮无需改动。
本轮上下文：602 字符
```

- **好的地方**：没有硬塞整章；明确"只做一件事""做到能复述就收工"；先问真实周时长再砍范围；拒绝替学习者补全不存在的上一轮记录。
- **问题**：`start` 列出的 3 道诊断题一道都没用，改成两个"元问题"；开场第一段是审计口吻（"我不替你补全"），对"两周前学过一点"的返学者没有一句"你上次大概到过这"的接续。

### 2.5 第 2 次发言（命令 5，往返 #2）

```
python "$LA\runtime\learn.py" say "一周大概也就一两个小时，其他晚上都在加班。上次只是看过概念视频，没真写过调用。今天别从头讲，做一点点就行。"
```

planner 回复（796 字符，摘）：

> 收到，按每周 1–2 小时重排这周：范围砍到三步，今天只走第一步的一半——你只需说出「Agent 和单次问答的差别」，不用碰代码。理由是你只停留在看视频、没写过调用，直接上伪代码会变成背名词；先把差别说清，下次 20 分钟才够写伪代码。
>
> 现在给我一句话就行：如果我问你「普通问答」和「Agent」最本质的区别是什么，你会怎么答？答不上来也没关系，说「不知道」我们就换个更小的入口。

```
本轮记录：帮助等级：独立完成 ｜ 下一步：学习者用一句话说出 Agent 与单次问答的差别，再决定是否进 w1-agent-loop-ex1
计划：已按 planner 的变更更新。
本轮上下文：796 字符
```

- 规模判断在这一轮是对的：把 20 分钟预算换成一个"一句话"活动，并给了"不会就换更小入口"的退路。
- `计划：已按 planner 的变更更新` 只有这一行，学习者看不到改了什么（实际是 PC-0001，见 §5）。

### 2.6 第 3 次发言（命令 6，往返 #3）

```
python "$LA\runtime\learn.py" say "普通问答是问一句答一句，一次就完了。Agent 会自己决定要不要调工具，再按工具返回的结果往下做。不过我说不清它靠什么记住上一步，可能就是把前面的消息都塞回去？"
```

planner 回复（1009 字符，全文）：

> 这个回答已经抓到核心了：一次就完 vs 自己决定调工具、按结果继续。你补的那句「靠什么记住上一步」正好是四要素里最容易含糊的一环，你的猜测方向是对的，但具体机制不该由我讲——那是概念导师的活，我把它记成待办，下次由 concept 展开。
>
> 今天 20 分钟到这儿就收工，符合「做一点点」的约定。下次进来先由 concept 用十分钟把「状态/记忆」讲清，再回到伪代码那一步。

```
本轮记录：帮助等级：独立完成 ｜ 下一步：下次由 concept 讲清 Agent 的状态/记忆机制，再进 w1-agent-loop-ex1 写伪代码
计划：已按 planner 的变更更新。
本轮上下文：1009 字符
已切换到 概念导师 concept（交接单 H-0001 已保存）。
下一步：直接说话即可（learn.cmd say "..."），或 learn.cmd status 看状态。

[自动交接] 已切换到 概念导师 concept。
```

- 反馈具体（点出"状态/记忆"是四要素里最容易含糊的一环），没有泛泛表扬，也没宣布掌握。
- 但它自己把时间判成"20 分钟到这儿"——从第一次发言到此只有 **16 秒**（12:22:09 → 12:22:25）。学习者实际还剩十几分钟，产品既没有问"还剩多少"，也没有给"想再用 10 分钟可以做 X"的选项。
- 收工时自动切到 concept，学习者没点名要换人。

### 2.7 收工保存（命令 7，pause #1）

```
python "$LA\runtime\learn.py" pause --note "今天只有20分钟，就说了一句 Agent 与单次问答的差别，没碰代码"
```

```
已保存：.learnark\handoff\20261104T122240-concept-to-concept.md
交接：H-0002（concept 收工）
git：git state: no-remote (written=yes, committed=yes, pushed=no)；remote=（无）
提示：No git remote is configured. Local commit is kept; add a remote (git remote add origin URL) to enable cross-device sync.

下次继续：learn.cmd start（会从 H-0002 恢复）
下一轮仍由 概念导师 concept 接续：计划下一步 w1-agent-loop：说清 Agent 与单次问答的差别
```

- 保存成功（本地提交 `committed=yes`，`dirty=False`）；`pushed=no` 且明确说明原因，没有谎报同步。
- 结束语给的"下一步"= 再做一遍"说清 Agent 与单次问答的差别"——**这正是学习者刚刚答过的那步**，且没有动作、没有时长，也没有 planner 刚承诺的"concept 用十分钟讲状态/记忆"。

### 2.8 次日/新进程 `start`（命令 8）

```
python "$LA\runtime\learn.py" start
```

```
目标：Agent 开发 · 每周约 12 小时
计划：plan-v1 v3（权威：planner） · 进度 0/10 步
  · 当前目标：w1-agent-loop 说清 Agent 与单次问答的差别

上次停在哪：H-0002 concept→concept（just now） · 未决 1 条
  · 交接说的下一步：由 概念导师 concept 接续：计划下一步 w1-agent-loop：说清 Agent 与单次问答的差别

这一轮该找谁：概念导师 concept
  · 为什么：计划下一步 w1-agent-loop：说清 Agent 与单次问答的差别
```

- 恢复本身成功（新进程只读项目就接上了），但"上次停在哪"指向的是一个人没说过话的 concept 会话；"下一步"仍是同一个目标，进度仍是 0/10。

### 2.9 无分钟数的对照发言（命令 9，往返 #4，仅用于任务 6）

```
python "$LA\runtime\learn.py" say "接着来吧，有点时间，但不多"
```

concept 回复（1263 字符，摘）：

> 上次那个点——「Agent 和单次问答到底差在哪」——现在还卡吗？如果只是有点模糊，我们就直接往下走。
>
> 今天只讲一个模型：**Agent 是一个「循环」，不是一次「回答」**。边界在于：单次问答是「输入→输出」一步到底，Agent 是「决策→调工具→看结果→再决策」反复转，直到任务完成或主动停下；反例是那种一次生成完整答案、中途不回头看的系统，它再长也不算 Agent。最小例子：查天气——单次问答直接编一个温度；Agent 先调天气接口，看到返回「接口超时」，再决定重试或换城市名。
>
> 讲完了，请你用自己的话回答：这个循环里，**「观察」那一步如果被跳过，会发生什么？**

```
本轮记录：帮助等级：分步引导 ｜ 下一步：请学习者复述：跳过「观察」这一步会怎样
本轮上下文：1263 字符
```

- 没有分钟数时：**没有任何默认会话时长**，concept 不问、不说预计几分钟，直接讲一个模型 + 出一题。内容量大约 5 分钟，尺寸本身不算离谱，但产品没有"默认给多长时间"这个概念；项目层默认仍是 12 小时/周。
- 它先问了"现在还卡吗"，没有把昨天已经答过的四要素重讲一遍（但紧接着仍完整讲了一遍"循环"模型，与已答内容部分重叠）。
- 为遵守"20 分钟到点就停"，我没有回答这道题，直接保存（往返停在 4 次）。

### 2.10 再次保存（命令 10，pause #2）

```
python "$LA\runtime\learn.py" pause --note "只测了一下没有分钟数时它怎么安排，没继续做题，20分钟到此为止"
```

```
已保存：.learnark\handoff\20261104T122316-concept-to-concept.md
交接：H-0003（concept 收工）
git：git state: no-remote (written=yes, committed=yes, pushed=no)；remote=（无）

下次继续：learn.cmd start（会从 H-0003 恢复）
下一轮仍由 概念导师 concept 接续：计划下一步 w1-agent-loop：说清 Agent 与单次问答的差别
```

### 2.11 只读核对（命令 11–17）

```powershell
python "$LA\runtime\learn.py" status
python "$LA\runtime\learn.py" plan
python "$LA\runtime\learn.py" plan --json
python "$LA\runtime\learn.py" doctor
python "$LA\runtime\learn.py" handoff --check
```

- `status`：`当前导师：concept ｜ 计划 v3 ｜ 进度 0/10`；能力四节点全部"未验证（证据 0 条）"；`未决：OL-objective 完成 w1-agent-loop：说清 Agent 与单次问答的差别（owner=concept）`；`最近回合：concept ｜ 帮助等级：分步引导`。
- `plan`：`每周 12 小时`；周目标文本却是"每周实际可用 1–2 小时，单次会话按 20 分钟切块"；`已生效：PC-0001 / PC-0002（by planner）`。
- `plan --json`：`plan.minutes_per_week = 720`、`plan.version = 3`、`current_objective.est_minutes = 20`、`steps = 10`、`hash_consistent = True`。
- `doctor`：19 项全 ok，`llm：mode=api key=yes`、`plan_authority：plan v3 hash 一致`、`handoff_event：latest=H-0003`、`journal_markers：mentor_turn=4`、`evidence_honesty：synthetic turns=0`。
- `handoff --check`：3 份交接全部通过（H-0001 planner→concept、H-0002/H-0003 concept→concept）。
- `.learnark/project.json`：`learner.minutes_per_week = 720`（仍 12 小时），与周目标文本"1–2 小时"冲突。
- 事件流（`.learnark\journal\events.jsonl`）里还能看到：seq 7 `plan_change status=noop`（理由"学习者自报今日仅 20 分钟，与计划假设的 12 小时/周不符，需先核实"）、seq 10 `mentor_update_retried`（turn 2 首次回复缺 `learn-update` 机器块，静默重试后 repaired=true）、seq 13/18 两次 `plan_change_applied`（PC-0001/PC-0002）。

## 3. 导师开场与结束语摘要

| 位置 | 原文摘要 |
| --- | --- |
| planner 开场（第 1 轮） | "我这边没有任何上一轮的交接记录……交接不完整，我不替你补全。今天二十分钟，我建议只做一件事：把「Agent 和单次问答差在哪」用自己的话说清四要素，做到能复述就收工。" |
| planner 收束（第 3 轮） | "这个回答已经抓到核心了……你补的那句「靠什么记住上一步」正好是四要素里最容易含糊的一环……今天 20 分钟到这儿就收工，符合「做一点点」的约定。下次进来先由 concept 用十分钟把「状态/记忆」讲清，再回到伪代码那一步。" |
| concept 开场（第 4 轮） | "上次那个点——「Agent 和单次问答到底差在哪」——现在还卡吗？……今天只讲一个模型：Agent 是一个「循环」，不是一次「回答」……讲完了，请你用自己的话回答：这个循环里，「观察」那一步如果被跳过，会发生什么？" |
| 保存结束语（pause） | "下次继续：learn.cmd start（会从 H-0003 恢复）；下一轮仍由 概念导师 concept 接续：计划下一步 w1-agent-loop：说清 Agent 与单次问答的差别" |
| 次日 start | "上次停在哪：H-0002 concept→concept（just now） · 未决 1 条 · 交接说的下一步：……说清 Agent 与单次问答的差别" |

## 4. 完成情况

| 环节 | 结果 | 证据 |
| --- | --- | --- |
| 开始 | 成功 | `init` 退出码 0；`start` 给出计划/当前目标/该找谁 |
| 诊断或定位 | **部分** | 只用 2 个自述问题（周时长、上次停点）；`start` 列出的 probe-d1/d2/d3 一道未用；planner 首轮 `plan_change noop` 事件承认 12h/周与 20 分钟不符 |
| 尝试与反馈 | **成功** | 1 次真实尝试（一句话说清差别），得到具体、不泛泛的反馈；能力仍 0 证据、进度 0/10（未伪造） |
| 保存/恢复 | 成功 | `pause` 写 H-0002/H-0003、git 本地提交；新进程 `start` 只读项目即可恢复 |
| 切换导师 | **自动发生，非学习者请求** | 第 3 轮后"[自动交接] 已切换到 概念导师 concept"；产生空会话与 concept→concept 自交接 |
| 20 分钟约束 | 对话内被遵守，计划内未落地 | 任务压到"一句话"；但 `start`/`plan` 仍显示 12 小时/周，`--minutes` 只影响显示 |
| 下一步可执行性 | **不达标** | 结束语只重复目标（"说清 Agent 与单次问答的差别"），无动作、无时长；planner 口头承诺的"concept 十分钟状态/记忆"没进计划或未决项 |

## 5. 20 分钟约束评估（任务 3/4/5/6）

1. **给的是小单元还是整章？** 是小单元，且偏小。第 2 轮明确"范围砍到三步，今天只走第一步的一半""一句话就行，不用碰代码"；第 3 轮就收工。没有硬塞一整章/一整周。
2. **实际用时**：从第 1 次发言到"收工"只有 16 秒；整个产品交互 80 秒。产品把"20 分钟"当成"已经用完"并主动结束，但没有任何"还剩多少时间/要不要再做 5 分钟"的确认。对 P3 是双刃：不超时（好），但 20 分钟只换来 1 分钟活动（也谈不上"做了一点"）。
3. **是否因时间短跳过必要诊断？** 是。`start` 明说 planner 会用 ≤4 轮诊断并列出 3 道诊断题，实际对话里一道没问，只用"周几小时/上次在哪停"两个自述问题；`project.json` 的 `diagnostics`（probe-d1/d2/d3）在会话里没有出现。
4. **结束的下一步是否具体（做什么、多久）？** 不具体。`pause`/`start` 都给"计划下一步 w1-agent-loop：说清 Agent 与单次问答的差别"——没有动作动词、没有时长、没有说"你昨天已经答过、今天从状态/记忆或伪代码继续"。第 3 轮导师口头说的"concept 用十分钟讲状态/记忆，再回伪代码"在计划、未决项、交接 `next` 里都找不到（`plan` 周目标只写了三步；`OL-objective` 只有原目标）。
5. **是否觉得"欠了很多账"？** 有一点，且来自界面而非真实任务量：每次 `start`/`plan` 都是"每周约 12 小时""进度 0/10 步""4 周""未决 1 条"，而学习者刚说了每周只有 1–2 小时、今晚只做了一句话。没有复习队列/积压惩罚（这点是好的），但 12 小时/周的数字会持续制造"落后"感。
6. **没有明确分钟数时的默认（任务 6）**：
   - 项目层：`init` 默认"每周约 12 小时"（`learner.minutes_per_week=720`），`start` 不带 `--minutes` 时**不显示任何本次时长**，也没有"只做一个活动"提示；
   - 对话层：说"有点时间，但不多"后，concept 不问时长、不说预计几分钟，直接讲一个完整模型 + 出题（约 5 分钟的量）；
   - 结论：没有"默认会话时长"这个概念，默认永远是 12 小时/周的课程节奏。对 P3 不合理；20 分钟只有在学习者**说出口**、且当轮 planner 愿意砍范围时才生效。

## 6. 预期 vs 实际

| 预期（普通学习者期待） | 实际 | 证据 |
| --- | --- | --- |
| 说"今天只有二十分钟"，产品把它当硬约束，给 ≤20 分钟的任务 | 会话内做到了：压成"一句话复述"，明确"收工" | planner 第 1/2/3 轮；`sessions\20261104-122200-planner.md` |
| 20 分钟能填满一点，做 1 个小活动 | 3 轮、16 秒就宣布"20 分钟到这儿"，剩余时间无建议 | 事件时间 12:22:09→12:22:25 |
| 短时也不省略必要诊断 | 跳过 `start` 明示的 3 道诊断题，改用自述 | `start` 输出；planner 第 1 轮 |
| 结束给出"明天做什么、多久" | 只重复同一目标；无动作/时长；导师承诺的 10 分钟 concept 未落计划 | `pause` 输出；H-0003 `next`；`plan` 周目标 |
| 不因为时间短就伪造"学会了" | 能力 0 证据、进度 0/10、`synthetic:false`，未升级 | `status`；`doctor` |
| 明天进来不重复已答内容 | 次日 `start` 又指向"说清 Agent 与单次问答的差别"；concept 虽先问"现在还卡吗"，但仍完整重讲循环模型 | `start` 输出；concept 第 1 轮 |
| 计划反映我真实可用的时间 | `plan.minutes_per_week` 仍 720；`start`/`plan` 头部"每周 12 小时"；只有周目标文本写"1–2 小时" | `plan --json`；`project.json` |
| 计划变更我能看懂改了什么 | 只有一行"计划：已按 planner 的变更更新"；实际两次 replan 自动 applied | `plan_changes` PC-0001/PC-0002；journal seq 13/18 |
| 收工时状态干净、下次从人真的停下的地方继续 | 自动切到 concept 并留下空会话，`pause` 写成 concept→concept；H-0002 `what_tried` 写"尚无导师回合" | `sessions\20261104-122226-concept.md`（仅 7 行）；H-0002 |

## 7. 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | 重要 | **时间预算不进入权威状态**：学习者说"每周 1–2 小时/今天 20 分钟"后，planner 只改周目标自由文本，`plan.minutes_per_week` 与 `project.json learner.minutes_per_week` 仍是 720（12 小时）；`start`/`plan` 头部继续显示"每周约 12 小时"，`--minutes` 只加一行显示提示。短时用户第二天仍被 12 小时/周和 10 步计划迎接，直接制造"欠账"感。 | `init`（默认 720）→ `start`（显示 12 小时）→ `say` 说 1–2 小时/20 分钟 → `plan --json` 看 `minutes_per_week` → 仍是 720；`start` 头部仍 12 小时 | `.learnark\project.json`（`learner.minutes_per_week:720`）；`python learn.py plan --json`（`plan.minutes_per_week:720`）；`plan` 输出"每周 12 小时" |
| 2 | 重要 | **结束"下一步"不可执行且与导师当场承诺不一致**：`pause`/`start` 的 next 只有"计划下一步 w1-agent-loop：说清 Agent 与单次问答的差别"（无动作、无时长、与刚答过的内容重复，进度 0/10）；planner 第 3 轮说的"下次由 concept 用十分钟讲状态/记忆，再回伪代码"没有落进计划、未决项或交接 `next`。次日 concept 只能重新从同一目标开始。 | 3 轮对话 → `pause` 看"下次继续" → 新进程 `start` 看"下一步" | `.learnark\handoff\20261104T122316-concept-to-concept.md`（`next`）；`status`（未决 OL-objective）；`sessions\20261104-122200-planner.md` 第 3 轮 |
| 3 | 重要 | **20 分钟被当作"已用完"，实际只做了 ~1 分钟且不给续做选项**：第 3 轮导师自行宣布"今天 20 分钟到这儿就收工"，而三轮对话只用了 16 秒；没有"你还剩多少时间"/"想再用 10 分钟可以做 X"。既不超时，也没把预算用起来。 | `say` 三轮 → 观察第 3 轮收工语与 journal 时间戳 | `sessions\20261104-122200-planner.md` 第 3 轮；`events.jsonl` seq 5/11/16 时间 12:22:09/17/25 |
| 4 | 重要 | **短时场景跳过了入口承诺的诊断**：`start` 明说"planner 用 ≤4 轮诊断"并列出 probe-d1/d2/d3，实际一道未问，诊断完全依赖学习者自述；产品自己的规则是"自述不算能力"。 | `start` 看诊断题 → `say` 两轮，观察没有 probe 出现 → 查 `sessions/*.md` 与 `project.json diagnostics` | `sessions\20261104-122200-planner.md`；`.learnark\project.json`（`diagnostics` 3 条） |
| 5 | 一般 | **收工自动换人产生空会话/自交接**：第 3 轮后自动切 concept（学习者没请求），`pause` 写成 `concept→concept`；被切的 concept 会话 7 行、无任何师生对话，H-0002 的 `what_tried` 只能写"本次交接前没有记录到尝试或产物（尚无导师回合）"。次日"上次停在哪"指向这个空会话。 | 第 3 轮后看"[自动交接]" → `pause` 看 H-0002 → 次日 `start` | `.learnark\handoff\20261104T122240-concept-to-concept.md`；`sessions\20261104-122226-concept.md` |
| 6 | 一般 | **"帮助等级：独立完成"读起来像"完成"**：三次 planner 回合（学习者只回答元问题、无尝试）都显示"帮助等级：独立完成"；`status` 把它与"进度 0/10、能力 0 证据"并列。语义是"help_level=0 未求助"，但对短时学习者容易被读成"过了"。 | 任一轮 `say` 后看"本轮记录"；`status` 看"最近回合…帮助等级" | `sessions\20261104-122200-planner.md`（每轮 `help_level: 0`）；`status` |
| 7 | 一般 | **计划变更自动生效且没有差异摘要**：两次 `replan_week` 在 `say` 内直接 applied（PC-0001/PC-0002），可见输出只有"计划：已按 planner 的变更更新"，学习者看不到 10 步→三步的实质变化；`do_not_redo` 仍为空，尽管学习者说过"今天别从头讲"。 | 第 2/3 轮 `say` 后看"计划"行 → `plan`/`plan --json` 对比 | `plan --json`（`plan_changes` PC-0001/PC-0002）；`.learnark\handoff\...planner-to-concept.md`（`do_not_redo: []`） |
| 8 | 一般 | **导师机器块缺失时静默重试，界面无提示**：第 2 轮首次回复缺 `learn-update` 块，运行时静默重试（`mentor_update_retried`，repaired=true），学习者只感知到回复延迟/一次额外 API 调用；本轮无任何"记录可能不完整"提示。 | 第 2 轮 `say` → 查 journal seq 10 | `.learnark\journal\events.jsonl` seq 10 |
| 9 | 一般 | **开场是审计口吻，不是接续**：planner 第一段先强调"没有上一轮交接记录……我不替你补全"，对"两周前学过一点"的返学者缺少"你上次大概到过这里"的接续尝试，也没有先用 `start` 已列出的诊断题低成本定位。 | 第 1 次 `say` | `sessions\20261104-122200-planner.md` 第 1 轮 |

**做对的地方（也要写清）**：不硬塞整章；不为了"20 分钟"跳过安全边界（拒绝编造上一轮）；不把自述升级成能力（0 证据、0/10、`synthetic:false`）；一次尝试得到具体、非泛泛的反馈；保存/恢复/`doctor`/`handoff --check` 全部正常；无任何支付或 HTTP 错误。

## 8. 使用负担

- 师生往返: **4 次**（上限 6，场景卡 12）——3 轮 planner 会话 + 1 轮"无分钟数"对照；没有为凑满 20 分钟额外发言
- 命令数: **17 次** `learn.py` 调用（init 1、start 3、say 4、pause 2、status 2、plan 3、doctor 1、handoff 1），其中只读命令 6 次
- 需要阅读的文档: **4 份**（`round-05.md`、`learner-brief.md`、`START_HERE.md`、`personas.md`），另有产品自动注入的 `AGENTS.md` 1 份
- 不清楚的地方:
  1. `start` 头写"每周约 12 小时"，周目标写"1–2 小时/20 分钟切块"，哪个作数？
  2. 今天已经说出"差别"，为什么进度还是 0/10、明天还让我说同一件事？"能复述四要素"什么时候算过？
  3. "帮助等级：独立完成"是指"我完成了"还是"我没要帮助"？
  4. 产品凭什么在第 3 轮就说"今天 20 分钟到这儿"？它知道我用了多久吗？
  5. `--minutes 20` 除了那行提示，到底改变了什么？（文档说只影响提示，实测一致，但那为什么计划头还是 12 小时？）
- 环境备注: `Get-Content` 直接读交接 `.md` 时控制台出现乱码，产品输出本身与 `read` 读取均正常（UTF-8）；`plan --json | Select-Object -First 80` 会因管道提前关闭返回 `EXIT=-1`，是 PowerShell 管道行为，不是产品错误。

## 9. 结论

- **是否完成场景目标: 是（有条件）**。短时进入、1 次最小尝试、具体反馈、结束保存、新进程能恢复、知道"明天还是 concept + w1-agent-loop"——主链路走通，且在对话内没有硬塞长课程，也没有伪造掌握。但"20 分钟"只活在当轮对话里：计划与状态仍是 12 小时/周、0/10；结束的"下一步"不可执行，且与导师当场承诺的"concept 十分钟讲状态/记忆"不一致，明天大概率重说同一句话。对 P3 的净收益是"确认自己大致懂了、知道还有个坑（状态/记忆）"，不是"完成了一个 20 分钟单元"。
- **最需要修的一件事**: 把学习者真实可用的时间写进权威状态并在入口/结束处使用——即 `learner.minutes_per_week` 与计划里的时间预算随对话更新，`start`/`plan`/`pause` 的下一步必须带"做什么 + 预计几分钟 + 从哪个 step 继续"；否则短时用户第二天看到的仍是"12 小时/周、10 步、0/10"，而导师口头承诺的下一步永远落不到计划上。
- 未验证/推测: 本报告是单次模拟会话（4 次往返、1 个模型 `deepseek-flash`、1 次运行），不能证明真人长期学习收益；"20 分钟是否偏小"混合了产品判断与我的模拟节奏，已在 §5 标注。未复现支付/HTTP 错误，故无此类记录。
