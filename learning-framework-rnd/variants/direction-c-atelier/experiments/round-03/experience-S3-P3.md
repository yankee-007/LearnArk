# 体验报告 — direction-c-atelier round-03 S3（P3 Mia）

- 版本: 0.2.2（learncore 1.0.2 · schema 1；按 `START_HERE.md` 标注）
- 体验者: 独立子 Agent（DSH 会话，deepseek-flash 模型上下文；非研发者）
- 场景: S3 导师切换与中断恢复（P3 Mia）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r03-s3\proj`
- 入口: `$LA = "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-c-atelier"`；`python "$LA\runtime\learn.py" <cmd>`
- 交互预算: 两段共用 10 次；实际 **7 次 `say`**（第一段 3 次，第二段 4 次），另 `switch` 1 次、`pause` 2 次
- 运行模式: 真实 LLM API，全程未加 `--offline`；会话头 `offline: false`，事件 `mode: api`、`model: deepseek-flash`
- 时间: 2026-11-04 03:37:56–03:39:50（+08:00）。模拟两段各 10 分钟碎片时间，实际墙钟约 2 分钟
- 只读材料: 本场景卡、`evaluation\harness\learner-brief.md`、`START_HERE.md`、报告模板 `shared\scenarios\personas.md`；项目内只读产品生成的 `sessions/`、`.learnark/`。未读源码、设计、导师、测试或历史报告。

## 实际步骤（命令 + 关键输出摘要）

### 第一段（03:37:56–03:38:24）

1. 建项目：
   `python "$LA\runtime\learn.py" init --goal "用 Python 做出能调用工具的小 Agent" --dir C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r03-s3\proj`
   → `已创建 Atelier 学习项目`；默认 `每周约 12 小时`；`plan-v1 v1（10 步）`。
2. `start --minutes 10` → `上次停在哪：尚无学习记录（首次进入）`；`这一轮该找谁：策划导师 planner`；列出 `probe-d1..d3` 诊断题。
3. `say "我两周前学过一点 function calling，只记得模型会返回工具调用，细节都忘了。今天只有 10 分钟，晚上可能还有 10 分钟，不想从头学。"`
   → planner 先写：`交接信息不完整：我这边没有上一份 handoff 的 known / do_not_redo / open_loops`，再问“这周能挤出几小时”。
4. `say "这周大概能挤出 4 小时。今天先‘说清区别’，伪代码晚上再写。"`
   → planner：`本周按 4 小时重排`，要求说清“普通问答 vs 让 Agent 做事”的差别。本段三轮共触发 3 次 `replan_week`（plan v1→v4）。
5. `say "我试着说：1）普通问答是一次输入一次输出就完了；Agent 要跑好几步…3）Agent 最后还要自己判断什么时候停…"`
   → planner：`你讲的三条正好覆盖了核心`；`今天这 10 分钟到此收工。晚上那 10 分钟做 w1-agent-loop-ex1`（写循环伪代码）。该轮 `next` 字段同样是 `进入 w1-agent-loop-ex1`。
6. `status` → `当前导师：planner｜计划 v4｜进度 0/10`；`下一步：learn.cmd switch concept`；理由仍是 `w1-agent-loop：说清 Agent 与单次问答的差别`（与导师“覆盖核心/收工”的判断不一致，见问题 4）。
7. `pause --note "今天只有10分钟，讲完区别就收工；晚上继续写伪代码。"`
   → `已保存：.learnark\handoff\20261104T033824-planner-to-planner.md`、`H-0001`、`committed=yes`、commit `05cf0a8`；`下次继续：learn.cmd start`；建议下轮找 concept。

### 第二段（03:38:39–03:39:50，新 PowerShell 进程）

8. 新进程（PID 38692）中重新 `start --minutes 10`（工作目录=项目目录）：
   → `上次停在哪：H-0001 planner→planner`；`交接说的下一步：由 概念导师 concept 接续`；`这一轮该找谁：概念导师 concept`。恢复入口只读项目文件，成功。
9. `status`（切换前）→ `当前导师：planner｜计划 v4｜进度 0/10`；`上次停在 H-0001`；未决 `OL-objective`；`下一步：learn.cmd switch concept`。
10. `switch concept --why "想先把概念彻底讲清楚，再写伪代码"`
    → `已切换到 概念导师 concept（交接单 H-0002 已保存）`。
11. `status`（切换后）→ `当前导师：concept｜计划 v4｜进度 0/10`；`上次停在 H-0002（planner→concept）`；`下一步：learn.cmd say "..."`。
12. `say "我回来了，现在只有 10 分钟。上次 planner 让我讲 Agent 和单次问答的区别，我讲了三條，他说可以了，让我晚上写伪代码。我们从哪继续？"`
    → 输出第一行即 `已切换到 策划导师 planner（交接单 H-0003 已保存）`（原因“用户点名”）；planner 回复后，末尾又出现 `已切换到 概念导师 concept（交接单 H-0004 已保存）` 和 `[诊断转交]`。**一次发言触发 concept→planner→concept 两次切换**；学习者并未请求换人。
13. `status` → `当前导师：concept`、`上次停在 H-0004`；`薄弱/误解` 出现：
    `循环与边界（w1-agent-loop）：理由：你上次已用三条差别过掉了「说清区别」这一步…`（来源 `ev_d25dd6d446b7`）。这是 planner 的解释句，不是学习者说的。
14. `say "我回来了，只有 10 分钟。上次讲的差别我大概还记得，但让我写伪代码还是有点虚。你能先帮我把循环结构讲清楚一点吗？"`
    → concept 从零讲 `Agent 循环 = 模型→工具→观察→再决策`，要求复述（help_level=2）；未提及上一段已讲过的内容，也未引用 H-0004 的具体事实。
15. `say "我复述一下：1）模型决定下一步…4）再决策…只有需要外部信息或动作时才进这个循环。"`
    → concept：`复述基本对`，纠正“观察不是动作…”，并追问工具返回错误时第 4 步该做什么。
16. `say "那第 4 步模型看到「文件不存在」这个观察，应该决定换个做法…而不是直接说做完了。"`
    → concept：`对，这就是循环的价值…`，再追问“哪一步只产出动作”。该夸奖句随后被记成 w1-agent-loop 的误解。
17. `pause --note "晚上时间到了，先保存。今天跟 concept 把 Agent 循环四步过了一遍，还没写伪代码。"`
    → `H-0005`（concept→concept）、commit `925507a`、`committed=yes`。
18. 最终 `status` → `当前导师：concept｜计划 v4｜进度 0/10`；`薄弱/误解` 两条；`下一步：learn.cmd say`。再次新进程 `start` 仍显示 `上次停在 H-0005`、下一轮 `概念导师 concept`、`w1-agent-loop`。

切换观察：concept 的 `context_manifest` 确实显示注入了 `handoff/latest`（H-0004）与 `events/projection`，但 H-0004 的 `what_tried` 只有 planner 1 轮；concept 回复没有引用任何上一段内容，直接从零讲模型。因此它“知道当前目标未完成”，却不知道“四要素刚讲过并被认可”。

## 完成情况

- 开始: 成功（`init`、`start`，planner 正常开场）
- 诊断或定位: 成功（planner 问了周时长与今日重点，并下调计划；但列出的 probe-d1..d3 实际未逐题问）
- 尝试与反馈: 成功（学习者提交“三条差别”“四动作复述”“错误处理”共 3 次实质尝试；导师均给出具体反馈；尝试均记 `correct=null`，未升级能力）
- 保存/恢复: 成功（H-0001/H-0005、两次 commit；新进程仅凭项目恢复，H-0001/H-0005 均被读到）；但 `pause` 后工作区仍 dirty（问题 5）
- 切换导师: 命令行切换成功（H-0002），但被一次自然语言发言意外触发两次切换（问题 1）
- 学习目标: **未完成**（两段之后仍 `进度 0/10`，`w1-agent-loop` 仍 todo，未开始写伪代码）

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 新进程只凭项目文件就能恢复上次位置 | 是：新 PID 38692 的 `start` 直接读出 H-0001 | `sessions` 无跨进程依赖；第二段 start 输出 |
| 新导师知道“我已经讲过什么”，不重复 | 否：H-0004 只有 1 轮 `what_tried`；concept 从零讲四步并要求复述 | `H-0004`、`sessions\20261104-033856-concept.md` 第 1 轮 |
| 切换有交接记录，新导师会引用它 | 有 H-0002/H-0004 交接单，但新导师回复未引用任何具体旧事实 | `.learnark\handoff\`、concept 第 1 轮 |
| 未完成不会被说成完成 | 系统未标完成（0/10、step todo），但 planner 文本称“过掉了这一步” | planner 第 3 轮原文；`status`、`plan` |
| 两位导师对“下一步”说法一致 | 否：planner 说 `w1-agent-loop-ex1` 写伪代码，运行时/概念继续 `w1-agent-loop` 说清区别 | planner 第 3 轮 `next`；`start`；concept `next` |
| 结束保存可信 | 文件和 commit 都有，但 `pause` 报 `committed=yes` 后 `git status` 仍显示 `M .learnark/journal/events.jsonl` | `git status --short`、最终 `status` 的 `dirty=True` |
| 陈述句里提到 `planner` 只是回忆 | 被当成“点名换导师”，概念导师尚未发言就被换走 | H-0003、event seq 23/24/27 |
| “薄弱/误解”只来自学习者 | 否：导师的讲解、反例、夸奖被写成 3 条 `misconception`（含未开始的 w2-tools） | `.learnark\state\capability.json`；event seq 32/43/44/49 |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | 重要 | 自然语言里提到导师名会被当成“点名切换”。当前导师为 concept 时，说“上次 planner 让我…”，`say` 未回复先切到 planner（H-0003，why=用户点名），planner 回复后又自动切回 concept（H-0004）；一次发言两次换人，概念导师没有机会接话。 | concept 为当前导师时发送含“planner”的普通陈述句；观察 `say` 首尾两条切换提示。 | `.learnark\handoff\20261104T033853-concept-to-planner.md`、`...033856-planner-to-concept.md`；`.learnark\journal\events.jsonl` seq 23–27、33–35 |
| 2 | 重要 | 导师文本被错误写进学习者能力证据。`capability.json` 的 `misconceptions`/`last_fail` 收录了 planner 的理由句、concept 的“补一个精确处…”和“对，这就是循环的价值…”；其中“反例提醒：如果工具返回错误…”还被挂到**尚未开始的 w2-tools**，并给出 `review_due`。`status` 把这些当成学习者的“薄弱/误解”。 | 正常 `say` 让导师解释/夸奖；随后 `status` 或读 `capability.json`。 | `.learnark\state\capability.json`（w1-agent-loop 三条、w2-tools 一条）；events seq 32/43/44/49；H-0005 的 `known` |
| 3 | 重要 | 交接只保留**最近一段会话**且每条 `what_tried` 截断到句首（以 `…` 结尾）：H-0002 含第一段 3 轮，H-0004 只剩 planner 的 1 轮，H-0005 只有 concept 的 3 轮、没有前两段。新导师因此不知道“四要素已讲过/被认可”，从零重讲并要求复述，形成重复。 | 连续两段学习后对比 `handoff --last`；或看 concept 第 1 轮与上一段 planner 第 3 轮的内容重合。 | `.learnark\handoff\20261104T033844-planner-to-concept.md`、`...033856-planner-to-concept.md`、`...033943-concept-to-concept.md`；concept 会话第 1 轮 |
| 4 | 重要 | “下一步”冲突且不推进：planner 明确说 `w1-agent-loop` 已“过掉了”、晚上做 `w1-agent-loop-ex1`；`status`/`plan` 仍是 `w1-agent-loop` todo、`0/10`，`pause`/`start` 仍让 concept 继续“说清区别”，concept 也确实重讲同一模型。实际生效的是运行时计划（界面都按 `w1-agent-loop`），导师的 `ex1` 口头安排没有进入计划；学习者按界面走就到不了 `ex1`。 | 完成第一段三轮后看 `status`/`plan`/`start`；再问 concept。 | `sessions\20261104-033805-planner.md` 第 3 轮、`sessions\20261104-033853-planner.md`；`status`；`plan`；`H-0005`；`start` 输出 |
| 5 | 一般 | `pause` 报告 `written=yes, committed=yes`，但紧接着 `git status --short` 仍有 `M .learnark/journal/events.jsonl`，`status` 也显示 `dirty=True`。原因疑似 sync 事件在 commit 之后才写入 journal。 | `pause` → `git status --short`。 | `pause` 输出；`git status`；最终 `status` |
| 6 | 一般 | 首次进入（没有任何上一份交接）时，planner 开场就写“交接信息不完整：我这边没有上一份 handoff 的 known/do_not_redo/open_loops”，对第一次使用的学习者是无意义噪音，也让人怀疑记录是不是丢了。 | 全新项目 `start` 后第一次 `say`。 | `sessions\20261104-033805-planner.md` 第 1 轮 |
| 7 | 一般 | 时间口径没有同步：学习者明确说本周约 4 小时，`plan`/`start` 顶部仍显示“每周 12 小时”（只有周目标文字改成 4 小时三步）。 | 说“4 小时”后看 `plan`/`start` 头部。 | `plan` 输出；`start` 输出 |

（无命令级阻塞：流程命令均成功返回，`handoff --check` 5 份全部通过。）

## 使用负担

- 师生往返: **7 次**（第一段 3 次，第二段 4 次）；产品命令约 22 次（含 `status`/`start`/`plan`/`handoff --check`/`studio` 等只读），另有约 8 次只读文件检查
- 需要阅读的文档: 4 份（场景卡、`learner-brief.md`、`START_HERE.md`、报告模板）；项目内 `AGENTS.md` 由运行环境自动注入
- 最耗时/费解的地方:
  1. 第二段第一条 `say` 被拆成两次自动换人，需要读 journal 与 4 份 handoff 才能确认发生了什么；
  2. 导师说“过掉了”，系统却仍是 0/10、下一步 concept，学习者无法判断该写伪代码还是再复述；
  3. `status` 的“薄弱/误解”出现导师自己的句子，必须回到 `capability.json` 和事件才能确认不是自己说错；
  4. 不清楚“说清区别”这一步到底由什么动作算完成——没有 `pending_exam`，`plan` 也没有可执行的完成入口。

## 结论

- 是否完成场景目标: **否（流程可走通，学习目标未推进且记录被污染）**。开始、两段保存、新进程恢复、命令行切换、再次结束都能执行；但两段之后计划仍 `0/10`，伪代码未开始，概念导师重讲已讲过的四要素，`薄弱/误解` 被导师文本污染。
- 最需要修的一件事: **修交接/状态的事实链**——导师的讲解与夸奖不得写成学习者误解；`latest.md` 必须携带跨会话累计的已发生事实（而不只是最近一段）和导师最后给出的下一步，否则“换导师”实际等于“从头再讲一遍”。

## 附：会话、handoff 与 status 摘要

### 会话文件（两段 + 中间自动切换产生的一段）

- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r03-s3\proj\sessions\20261104-033805-planner.md`（第一段 planner，3 轮）
- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r03-s3\proj\sessions\20261104-033853-planner.md`（第二段被自动切到 planner 的 1 轮）
- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r03-s3\proj\sessions\20261104-033856-concept.md`（第二段 concept，3 轮）

### Handoff 文件

| 交接 | from→to | why | 关键内容 |
| --- | --- | --- | --- |
| H-0001 | planner→planner | 会话结束：保存进度 | 含第一段 3 轮 `what_tried`；next=concept |
| H-0002 | planner→concept | 想先把概念彻底讲清楚，再写伪代码 | 含第一段 3 轮 `what_tried` |
| H-0003 | concept→planner | 用户点名 | `what_tried` 写明“尚无导师回合”；由陈述句中的 planner 触发 |
| H-0004 | planner→concept | 诊断发现需要讲解/陪练的误解 | `what_tried` 只剩 planner 1 轮；`known` 是 planner 的理由句 |
| H-0005 | concept→concept | 会话结束：保存进度 | 只有 concept 3 轮；`known` 是 concept 的反例句 |

- 目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r03-s3\proj\.learnark\handoff\`
- `latest.md` 与 `20261104T033943-concept-to-concept.md` 内容一致（H-0005）。
- `handoff --check`：`检查 5 份交接：全部通过`（机器块格式均合法，问题在内容合成，不在 schema）。

### 切换前后 `status` 摘要

切换前（第一段结束，planner）：

```text
当前导师：planner ｜ 计划 v4 ｜ 进度 0/10
上次停在 H-0001（planner→planner）
下一步：learn.cmd switch concept
  · 导师：概念导师 concept
  · 理由：计划下一步 w1-agent-loop：说清 Agent 与单次问答的差别
```

切换后（`switch concept`，H-0002）：

```text
当前导师：concept ｜ 计划 v4 ｜ 进度 0/10
上次停在 H-0002（planner→concept）
下一步：learn.cmd say "..."
```

被自动切换两次后（H-0004）：

```text
当前导师：concept ｜ 计划 v4 ｜ 进度 0/10
上次停在 H-0004（planner→concept）
薄弱/误解：
  - 循环与边界（w1-agent-loop）：理由：你上次已用三条差别过掉了「说清区别」这一步…
```

第二段结束（H-0005）：

```text
当前导师：concept ｜ 计划 v4 ｜ 进度 0/10
上次停在 H-0005（concept→concept）
薄弱/误解：
  - 循环与边界（w1-agent-loop）：对，这就是循环的价值：错误也是观察…
  - 工具与可靠性（w2-tools）：反例提醒：如果工具返回错误…
git：branch=master remote=（无） dirty=True
```
