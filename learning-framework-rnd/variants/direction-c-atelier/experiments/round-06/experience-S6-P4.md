# 体验报告 — direction-c-atelier round-06 S6 跨主题迁移

- 版本: Atelier 多导师工作室 0.2.3（learncore 1.0.2，schema 1）
- 体验者: 独立子 Agent（DeepSeek Harness / deepseek-flash 上下文，独立上下文，非研发者）
- 场景: S6 跨主题迁移（P4 Tina，运营，非编程背景，20 分钟）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r06-s6\proj`
- 入口: `python "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-c-atelier\runtime\learn.py" ...`
- 交互预算: round-06 卡为 **8 次**（personas 模板默认 12 次），实际使用 **8 次**，未超
- 会话时钟: 2026-11-04 12:21:50 – 12:23:02（+08:00），工具实际耗时约 75 秒；20 分钟预算没有用满，先撞到的是 8 回合上限
- 真实 LLM: 8 次 `say` 全部为真实 API（各 session 头 `offline: false`，`status --json` 的 `synthetic_turns: 0`），无 `--offline`，无付费/HTTP 错误
- 未读：`runtime/`、`design.md`、`curriculum/`、`mentors/`、`tests/`、`experiments/` 既有报告。只读了场景卡、learner-brief、START_HERE、报告模板，以及项目自己生成的 README/AGENTS 与 sessions/状态输出

## 实际步骤（命令 + 关键输出摘要）

1. `source _sandbox\env.ps1`，确认 `DEEPSEEK_API_KEY` 存在。
2. 建项目：
   `learn.py init --goal "英文工作邮件写作" --dir ...\proj --template email --minutes-per-week 30`
   → 输出「模板：英文工作邮件 · 四周写作工作坊（email）· 计划 plan-e1 v1（7 步）」。
3. `learn.py start --minutes 20`
   → 计划 `plan-e1 v1`，当前目标 `em-w1-structure`；该找 planner；列出两道首次诊断题 `probe-e1`（把中文诉求写成英文主题行）、`probe-e2`（指出样例邮件最该先删的一句）。
4. `say`（第 1 轮）：说明运营/不写代码/只想要英文邮件开头/今天 20 分钟。
   → planner 反问「开头」指主题行+首句还是整封起手结构，并确认 0.5 小时是固定还是零散。
5. `say`（第 2 轮）：确认指整封起手结构（主题行+第一段），时间零散。
   → planner 把本周压成三步，今天只做「主题行+第一段」。
6. `say`（第 3 轮）：给出真实场景（合作方 Northwind Studio 的 Ms. Lee，campaign brief 原定 11/6，法务审 tagline 延误，新日期 11/10，需确认能否开拍）。
   → planner 定验收标准（读完第一段就能决定回什么），随即自动交接 concept（H-0001）。
7. `say`（第 4 轮）：提交第一版邮件 V1（见附录），要求直接指到句子/用词。
   → concept 指出主题行挤了两个信息、首段先原因后请求；讲 BLUF；给最小改法（主题行只留一个诉求，请求放首句、原因退第二句）。
8. `say`（第 5 轮）：用自己的话复述 BLUF，提交修改版 V2。
   → concept 确认「复述和改写都到位」，补语气边界（Can you / Could you confirm whether 不影响诉求位置），并追问兜底句为什么放最后。
9. `say`（第 6 轮）：回答兜底句位置与理由，请求「用新场景考我一次」。
   → concept 给小自查（供应商报价单从周五提前到周三，只写主题行+首句）；本轮出现「**! 本轮没有形成可记录的证据**」。
10. `say`（第 7 轮）：提交自查答案，并明确请求交 examiner 正式考。
    → 自动切换到 examiner（H-0002）。examiner 判定我贴的是成品、不是对出题的作答，记 `pending`，然后出第 1 题（客户经理，报价截止从周五推迟到下周三，需先确认预算口径，只写主题行+第一段）。
11. `say`（第 8 轮）：提交 examiner 第 1 题答案（见附录）。
    → 「判定：pass」，`exam-em-w1-q1（对）`，能力「结构与主题行」变为 4 级（来源 verified）；examiner 说下一题 q2 是把同一诉求压到 60 词以内。8 回合预算用完，停止。
12. `learn.py status`
    → 见下方 status 摘要；同时暴露「独立验证」与「未决 OL-objective」并存。
13. `learn.py pause --note "20 分钟到：完成主题行+首段两版修改，examiner 第一题 pass；剩余两题下次再做。"`
    → `已保存`，H-0003，git `written=yes, committed=yes, pushed=no`（无 remote）。
14. **新进程**（新 pwsh）`learn.py start`
    → `plan-e1 v3`，进度 1/7，上次停在 `H-0003 examiner→examiner`，下一步仍是写作任务「em-w1-rewrite 把 200 词坏邮件改到 120 词」，该找 coach。记录仍在。

## 完成情况

- 开始: 成功（email 模板建成，`start` 正常给出计划、诊断题、当前导师）
- 诊断或定位: **部分成功**。planner 用 3 轮确认目标范围、时间形态、真实场景，适配「零散 20 分钟」；但 `start` 承诺的 `probe-e1`/`probe-e2` 两道写作诊断题从未出现，没有写作基线样本就直接进入 concept 教学
- 尝试与反馈: 成功。V1 → V2 的反馈具体到主题行与首段第一句，并给出最小改法；V2 被确认；examiner 第 1 题 pass
- 保存/恢复: 成功。`pause` 写 H-0003 并本地提交；新进程 `start` 恢复计划 v3、能力 4 级、下一步 coach 写作任务
- 切换导师: 成功。planner→concept 自动交接 H-0001；concept→examiner 由我明确请求触发 H-0002
- 跨主题: **成功但入口有残留**。导师任务、评分口径、能力节点全部是写作；项目根 README 仍有编程示例，AGENTS.md 是 Agent/JSON 技术说明（见问题 1）
- 考核: **部分成功**。只完成 3 题中的第 1 题；q2/q3 没有继续入口，重开后被计划下一步覆盖

## 两版邮件与导师反馈

### V1（第 4 轮提交，未按反馈修改）

```text
Subject: Delivery moved to Tue 10 Nov - can you still start production?

Hi Ms. Lee,

I am writing to let you know that the final campaign brief will now arrive on Tuesday, 10 November, two business days later than the original Friday, 6 November, because legal review of the tagline took longer than expected. Everything else is final. Could you confirm whether you can still schedule the shoot from 10 November?

Best regards,
Tina
```

### V2（第 5 轮，按 concept 的最小改法修改）

```text
Subject: Can you still schedule the shoot from Tue 10 Nov?

Hi Ms. Lee,

Can you still schedule the shoot from Tuesday, 10 November? The final campaign brief will now arrive that day, two business days later than the original Friday, 6 November, because legal review of the tagline took longer than expected. Everything else is final. If 10 November does not work, please tell me the earliest date you can start.

Best regards,
Tina
```

### examiner 第 1 题作答（第 8 轮）

```text
Subject: Budget scope confirmation needed by Wed 12 Nov

Hi Mr. Chen,

Can you confirm the budget scope by Wednesday, 12 November, so we can move the quote deadline from Friday to the same date and send a quote that matches it? We will hold the quote until your confirmation arrives.

Best regards,
Tina
```

### 导师反馈摘要

- concept（V1）：**具体到句**——主题行把「延期」和「确认能否开工」两个信息挤在一起；正文第一句先讲原因、再讲请求，收件人读到倒数第二句才知道要回什么。给出 BLUF 定义、边界（只调顺序、不删信息、不等于语气硬）和一个反例，最小改法是主题行只留「确认 11/10 能否开拍」、首句写请求、原因挪到第二句。
- concept（V2）：确认「主题行只有一个诉求、首句就是要她做的事、原因退到第二句、信息没丢」；补语气边界（`Can you…?` 换成 `Could you confirm whether…` 更客气，但诉求位置不变）；追问兜底句为什么放最后。**这一轮的回复没有被记录**（界面提示「本轮没有形成可记录的证据」）。
- examiner：先拒绝把自查成品当作答（记 `pending`，不算通过），随后用新题考；判定 **pass**，指出主题行直接给出动作+期限、第一段只有一个诉求且与延期因果绑定；唯一可挑的是 `by Wednesday, 12 November` 与主题行 `Wed 12 Nov` 日期重复，不扣分。

## status 摘要（`learn.py status`，12:23 左右）

```text
目标：英文工作邮件写作
当前导师：examiner ｜ 计划 v3 ｜ 进度 1/7
上次停在 H-0002（concept→examiner）
能力：
  - 结构与主题行：独立验证（证据 1 条）
  - 请求与状态同步：未验证（证据 0 条）
  - 拒绝与延期：未验证（证据 0 条）
  - 跟进与升级：未验证（证据 0 条）
薄弱/误解：暂无已记录的误解（不代表不会，只是还没有证据）
未决：OL-objective [一般] 完成 em-w1-structure：主题行、首段、单一诉求（owner=concept）
下一步：learn.cmd switch coach（计划下一步 em-w1-rewrite：把 200 词坏邮件改到 120 词）
git：branch=master remote=（无） dirty=True
```

能力节点命名 `em-w1-structure` / `em-w2-request` / `em-w3-decline` / `em-w4-followup`，标签是「结构与主题行 / 请求与状态同步 / 拒绝与延期 / 跟进与升级」，没有出现 Agent、API、函数、代码类节点；`synthetic_turns: 0`。这是「切换主题后能力记录独立」的正面证据。

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 换 email 模板后，看到的是写作课，不是改名的编程课 | 导师任务、反馈、能力节点都是写作；但 README 示例仍是「工具调用报错」，AGENTS.md 是 Agent/JSON 说明 | `proj\README.md:21`、`proj\AGENTS.md:1-33` |
| 第一次诊断会先摸我的写作基线 | 只问目标/时间/场景；`start` 列出的两道写作诊断题没出现 | `start` 输出 vs `sessions\20261104-122150-planner.md` |
| 反馈能指到我的句子和用词 | 指到主题行、首段第一句、兜底句，并给最小改法 | `sessions\20261104-122214-concept.md:24,49` |
| 8 回合内完成一个活动并看到下一步 | 完成主题行+首段，q1 pass；但 3 题考核只做了 1 题 | `sessions\20261104-122245-examiner.md:40-45`、`status --json` |
| 记录一致：能力提升后未决项应关闭 | 能力已 verified 4 级，`OL-objective` 仍挂「完成 em-w1-structure」；交接把两轮考试都写成「未判定」 | `.learnark\state\capability.json:4-24`、`.learnark\handoff\latest.md:44-58` |
| 写完的邮件能作为产物回看 | `artifacts/` 为空；verified 证据 `artifact=null, artifact_verified=false` | `.learnark\state\capability.json:13-14`、`artifacts\` |
| 新进程恢复后下一步仍是写作任务 | `start` 恢复 plan v3、能力 4 级、下一步 coach「把 200 词坏邮件改到 120 词」 | 新进程 `start` 输出 |

## 问题

| # | 严重度（阻塞/重要/一般） | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | 重要 | email 模板生成的 README 仍用编程示例：`say "我卡在工具调用的报错上"`；项目根 AGENTS.md 通篇 Agent、journal、JSON、help_level、handoff 机器块。非编程学习者第一眼会怀疑「只是把编程课改名」 | `init --goal "英文工作邮件写作" --template email` 后打开项目根 README.md 第 21 行与 AGENTS.md | `proj\README.md:21`、`proj\AGENTS.md:1-33` |
| 2 | 重要 | 记录互相矛盾：H-0003 的 `what_tried` 把 examiner 两轮都写成「未判定，帮助等级 0」，但第 2 轮实际 pass；能力已 verified 4 级，`OL-objective` 仍为 open「完成 em-w1-structure」；`status` 同时展示「独立验证」和未决 | 完成一次 examiner pass 后 `status`，再读 `latest.md` 与 `capability.json` | `.learnark\handoff\latest.md:44-58`、`.learnark\state\capability.json:4-24`、`status` 输出 |
| 3 | 重要 | examiner 宣布「三题、五分钟」，但只把第 1 题记成 `exam-em-w1-q1`；pass 后说下一题 q2，`pending_exam` 却是 null，`start`/`status` 的下一步直接变成 coach 的改稿活动，没有「继续考试」入口。8 回合预算也不可能做完 3 题 | 完成 q1 后 `pause`，新进程 `start`，观察下一步 | `sessions\20261104-122245-examiner.md:44-45`、`.learnark\state\capability.json:55`、新进程 `start` 输出 |
| 4 | 重要 | 写作考核没有可核对的产物：`artifacts/` 为空，verified 证据 `artifact=null`、`artifact_verified=false`；`status` 只显示「证据 1 条」，不提示产物缺失。学习者只能回 sessions 里找自己写的邮件 | examiner pass 后查看 `artifacts/` 与 `capability.json` | `.learnark\state\capability.json:8-18` |
| 5 | 重要 | concept 第 3 轮（回答兜底句问题）没有形成记录：`help_level=None`、`attempt=None`、`next=None`，界面提示「本轮没有形成可记录的证据」，`status --json` 里 `invalid: true`；人类可读 `status` 不展示该回合，交接的 `what_tried` 也没有它。学习者会以为自己的回答丢了 | 在 concept 会话第 3 轮后 `status` 与 `status --json`，对比 session 文件 | `sessions\20261104-122214-concept.md:63-70`、`status --json.recent_turns[2]` |
| 6 | 一般 | `start` 承诺首次诊断用 `probe-e1`/`probe-e2`，实际 planner 三轮只问目标、时间、场景，未做写作基线；随后直接由 concept 教学并在一次 pass 后给到 4 级，缺少基线对照 | `start` 记录两道 probe，再读 planner 会话 | `start` 输出、`sessions\20261104-122150-planner.md` |
| 7 | 一般 | 收工交接写成 `examiner→examiner`（H-0003），`start` 显示「上次停在哪 H-0003 examiner→examiner」，对学习者没有信息量；「为什么现在交接」只写「会话结束：保存进度」 | `pause` 后 `start` | `.learnark\handoff\latest.md:3-11`、新进程 `start` 输出 |
| 8 | 一般 | 帮助等级/未标注只在 `status --json` 的 `recent_turns` 可见，人类可读 `status` 只显示最后一回合；与 START_HERE 所称「status 显示未标注」不一致 | 制造一次 invalid 回合后运行两种 `status` | `status` 与 `status --json` 输出 |

## 使用负担

- 师生往返: **8 次**（预算 8，未超）；命令数: **14 次**（init 1、start 2、say 8、status 2、pause 1）
- 需要阅读的文档: 6 处——场景卡、learner-brief、START_HERE、报告模板、生成项目 README.md、生成项目 AGENTS.md。其中后两份是产品自己生成的入口，非我主动找资料
- 不清楚的地方:
  - `status` 的「未决 OL-objective」和「能力：独立验证」同时出现，到底算是完成还是没完成？
  - examiner 说还有 q2/q3，但所有入口都只给 coach 改稿；下次要不要自己记得回来考试？
  - 我写的邮件除 sessions 外没有产物文件，导出/回看在哪里？
  - concept 第 3 轮为什么没记录？是我的回答格式问题还是产品问题？
  - README 里的「工具调用报错」是不是模板没换干净？AGENTS.md 是给我看的还是给 Agent 看的？
- 需要研发者指导: 无（全程按 START_HERE 完成）；但若要完成 3 题考核，需要研发者告知如何继续，公开入口没有答案

## 结论

- **是否完成场景目标: 是（核心目标达成，但有明显保留）**。写作教学确实成立：任务、验收标准、反馈、能力节点全部围绕主题行/首段/单一诉求，反馈能指到具体句子，记录在新进程可恢复且下一步仍是写作。保留项：3 题考核只完成 1 题且无继续入口；记录内部矛盾；入口文档有编程/Agent 残留。
- **最需要修的一件事:** 把 email 模板生成的项目文档彻底写作化——删掉 README 里「我卡在工具调用的报错上」这类编程示例，并让 AGENTS.md 不再作为学习者的项目根入口（或改成写作版说明）。这是本场景「是不是只把编程课改名」的第一眼证据。
- 次优先（同样重要，但不作为「一件事」）：统一 capability / handoff / open_loop 的判定与状态；给 examiner 的多题考核一个可恢复的 pending 入口；把学员的邮件写成 `artifacts/<activity>.md` 以便核对。
