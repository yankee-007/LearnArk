# 体验报告 — direction-b-forge 0.2.2 round-03 S3 导师切换与中断恢复（P3 Mia）

- 版本: `direction-b-forge 0.2.2`（vendored `learncore 1.0.1`，state schema_version 1）
- 体验者: 独立子 Agent（DeepSeek Harness / deepseek-flash 上下文；非研发者，未读源码/设计/导师/测试/历史报告）
- 场景: S3（P3 Mia：两周前学过一点 function calling、细节忘了；今天先 10 分钟、晚上再 10 分钟）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r03-s3\proj`
- 入口: `. C:\Users\YK\Desktop\LearnArk\_sandbox\env.ps1` 后执行
  `python "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-b-forge\runtime\learn.py" <命令>`
- 交互预算: 两段共用 10 次；**实际 8 次**（第一段 4，第二段 4）
- 真实 LLM: `start` 打印「模式：在线导师（deepseek-chat）」，事件 `offline:false`；全程未用 `--offline`，`LEARNARK_LLM` 为空

## 0. 进程与真实性证据

| 项 | 证据 |
| --- | --- |
| 段 1 进程 | PowerShell PID **31048**，StartTime `2026-11-04T03:19:37+08:00` |
| 段 2 进程 | PowerShell PID **38600**，StartTime `2026-11-04T03:20:48+08:00`（新进程） |
| 段 2 未依赖旧进程 | 新进程只执行 `start`，无旧会话参数，输出「上次停在哪：coach → coach（pause）｜未决：g-M1-contract…；g-M1-robustness…」 |
| 真实 API | 两次段内所有导师回复均有 `help_level`、`runtime_next` 记录，`offline:false`；评审记录 `model: deepseek-flash` |

环境说明：python CLI 的中文输出正常；本采集环境里 pwsh `Get-Content` 读 UTF-8 文件显示乱码，改用 read 工具核对文件本身正常，**不计为产品缺陷**。

**版本未冻结（环境异常，非我修改）**：测试期间 `direction-b-forge` 目录有并发修改。段 1 开始后 `git status` 显示 12 个已修改文件；`START_HERE.md` mtime `03:23:25`、`examples/demo.md` `03:21:35`（均晚于我开始），而运行时代码最后写入为 `runtime/learn.py 03:19:12`、`forge_logic.py 03:16:41`，早于我的 `init`（03:19:26）。结论：我执行到的运行时在窗口内是一致的，但**入口文档在我读完后被改过**；复现请以当时快照为准，并确认是否有人并行改产品（我全程只写项目目录与报告）。

## 1. 实际步骤（命令 + 关键输出摘要）

### 第一段（03:19:37–03:20:39，PID 31048）

1. `init --goal "用 Python 做出能调用工具的小 Agent" --dir <proj>`
   → 已创建；里程碑 M1；下一步 `do_task`。
2. `start --ask --answers "能,没做过,一次做完一个项目"`
   → 起点档案 `{"api":"能","tools":"没做过","mode":"一次做完一个项目"}`；导师任务：「建 `m1/agent.py`，写一个工具，让模型/假回复触发一次调用并打印结果」；`▶ 唯一动作：do_task`。
   → 注意：档案写「60 分钟切片」，同一屏又打印「切片：20 分钟」。
3. 我写 `m1/agent.py`（假模型回复触发 `get_weather`；参数无校验；工具结果用 `role=user` 回填；注释自陈不确定）与 `docs/m1-design.md`；`python m1/agent.py`
   → `用户: 北京今天天气怎么样？ / 工具: get_weather / 参数: {'city': '北京'} / 结果: 晴 18C / 消息条数: 3`，EXIT=0。
4. `artifact add m1\agent.py docs\m1-design.md`
   → 两件登记：`a-M1-d3e79946`（agent.py，1773B）、`a-M1-4494fee9`（m1-design.md，944B），assisted_level=1；下一步 review。
5. `say -`（贴 5 行输出；说“今天只剩十分钟”；问 `role` 用 tool 还是 user、`tool_call_id`）
   → 导师：「本轮不评审、不算过 M1——你贴的是终端输出，**我没有看到已登记的作品文件**」「把 `m1/agent.py` 登记为作品」。实际两件在上一步已登记（`artifact list` 可证，评审随后也引用了 agent.py 行号）。页脚：`导师：coach｜help_level=1｜▶ 唯一动作：review（a-M1-4494fee9）`。
6. `status`（记录“它认为我在哪、下一步是什么”）
   → M1 `status=active`；作品 2 件；最近评审 无；下一步 `review a-M1-4494fee9（m1-design.md）`；切片 60 分钟。
7. `review`（按 ▶ 唯一动作，未指定 ID）
   → 实际生成 `r-M1-d3e79946`，四维 runnability 3 / contract 2 / robustness 2 / explainability 2，加权 2.3，达阈值 **False**；缺口 `g-M1-contract`（30）、`g-M1-robustness`（20）；`▶ 唯一动作：gap_learn（g-M1-contract）`。
8. `say -`（复述两个缺口，确认交接）
   → 导师确认缺口，并第二次说「`m1/agent.py` 还没登记为作品，review 只能看到 `m1-design.md`」；页脚 `▶ 唯一动作：gap_learn（g-M1-contract）`。
9. `pause --note "第一段 10 分钟结束：…"`
   → 已暂停；交接写 `.learnark/handoff/latest.md`（`20261104-031938-coach`）；open_items 两缺口；下次恢复 `start`（gap_learn）；git `written=yes, committed=yes, pushed=no`（无远程）。

### 第二段（03:20:48–03:21:36，新 PowerShell PID 38600）

10. `start`
    → 「上次停在哪：`coach → coach（pause）`｜未决：`g-M1-contract contract 2/3 (open)`; `g-M1-robustness robustness 2/3 (open)`」；动作 `gap learn g-M1-contract`；`▶ 唯一动作：gap_learn（g-M1-contract）`。**没有**重问三问、**没有**重讲基础、**没有**把 M1 标成完成。
11. `status`（切换前）
    → 导师 coach；作品 2 件；`r-M1-d3e79946` 2.3 未过；contract open、robustness open；最近交接 `coach→coach（pause）`；下一步 `gap_learn`；切片 60。
12. `switch guide`
    → 「已切换导师：coach → guide；交接 `.learnark/handoff/latest.md`｜未决：…」。
13. `say -`（晚上回来、只有十分钟、要一个“结构化错误”的最小例子）
    → 页脚 `导师：guide｜help_level=3`；给出 `calc` 代码、`isinstance` + bool 坑、预测题；正文末尾「回到作品…重新 `artifact add` + `review`」，与页脚「▶ 唯一动作：gap_learn」并存。
14. `gap learn g-M1-contract`
    → 与第 13 步**几乎逐字重复**（同一 `calc`/`n`/`isinstance` 例子、同一「关键三行」、同一预测题）；`缺口卡 g-M1-contract：contract 2/3 → status=learning`；页脚仍 `▶ 唯一动作：gap_learn（g-M1-contract）`；记录里 next 改为「加校验后重新 artifact add + review」。
15. `say -`（答预测题：True 会被当 1，所以输出 `{'result': 2}`；说明天再改代码）
    → 页脚 `导师：coach`（已自动回退），`help_level=3`；答「你猜对了」。但示例代码显式排 bool，按该代码应输出 error——反馈与所给代码不一致。
16. `next --json`
    → 仍 `"action": "gap_learn", "ref": "g-M1-contract", "minutes": 60`（缺口已是 learning）。
17. `pause --note "第二段 10 分钟结束：…"`
    → 交接 `latest.md`（`20261104-032049-coach`）；open_items 含 `contract 2/3 (learning)`；git `changed=0`。
18. `status`（收尾）
    → M1 active；contract 缺口 learning；上次会话 `20261104-032049-coach`（coach，4 轮，已结束）；下一步仍 `gap_learn`。

## 2. 完成情况

| 环节 | 结果 | 依据 |
| --- | --- | --- |
| 开始 | 成功 | `start --ask` 写入 `start_profile`，`answered=True` |
| 诊断/定位 | 成功 | `status`/`next` 一致显示 M1、两个缺口、权重与排序 |
| 尝试 | 成功 | `agent.py` + `m1-design.md` 登记（sha256、assisted_level=1） |
| 反馈 | 成功 | `review` 2.3、四维、两缺口卡；行号证据与源码一致（抽查 L19-23/45-62/51-52/57-61/65-66 均对） |
| 保存 | 成功 | 两次 `pause` 写 `latest.md`/`latest.json`，git 本地提交（无远程） |
| 新进程恢复 | 成功 | 新 PID 38600，仅凭项目文件读到上次停留、未决缺口与 next |
| 切换导师 | **部分成功** | `switch guide` 写入 `mentor_switch`，guide 答 2 次（1 次 say + 1 次 gap learn）后 `gap_learned` 自动回 coach；再说话已不是 guide |
| 再结束 | 成功 | 第二次 `pause`，交接 `coach→coach`，`changed=0` |

## 3. 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 新进程 `start` 只凭项目文件恢复 | 是：知道上次停在哪、缺口、下一步 | 段 2 `start` 输出 |
| 不重复已学/已做内容 | 启动不重复；但 guide 的自由提问回答与 `gap learn` 微课几乎逐字重复 | `sessions/20261104-032049-coach.md:26-48,61-84` |
| 未完成不能说成完成 | 正确：M1 active，review 达阈值 False，pause 仍指向缺口 | `status`、`reviews.json` |
| 切换有交接、新导师引用 | 有 `mentor_switch` 事件与交接；guide 用了当前作品/缺口上下文，但**没有一句**提到上次评审 2.3、上次停在哪或为什么换导师 | journal seq 19/27；session 2 |
| 两位导师对“下一步”一致 | 页脚一致（都是 gap_learn）；但 guide 正文说“回作品、artifact add + review”，与页脚冲突；`gap learn` 后页脚仍 gap_learn，而记录 next 已改成改作品+review | `sessions/20261104-032049-coach.md:48,82,101` |
| 短时（10 分钟）被尊重 | 否：三次说“只有十分钟”，切片始终 60 分钟（start 当屏还打印 20 分钟） | `status`、`next --json` |
| 结束有明确下一步可续 | 是：handoff next=gap_learn、note 写明明天怎么改 | `handoff/latest.md` |
| 作品/评审可追溯 | 部分：有 sha256 与行号；但 `next` 推荐 review 设计说明，实际评审锚定 agent.py，两件共用同一 review | `state/reviews.json`、`artifact list` |

## 4. 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | **重要** | 已登记作品被导师说成“未登记”，两次；并让学习者重复登记 `m1/agent.py`。导师上下文似乎只看到“最新一件”作品（m1-design.md），而实际两件都在，review 也逐行引用了 agent.py | `artifact add A B` → `say` → 导师答“没有看到已登记的作品文件” → `artifact list` 两件均在 | `sessions/20261104-031938-coach.md:27,43`；`artifact list` |
| 2 | **重要** | `gap learn` 后 `next` 不前进：同一缺口的 `gap_learn` 仍是“唯一动作”，学习者会被反复送回同一微课；且该微课与 9 秒前自由提问的回答几乎逐字重复（同一例子/同一预测题） | `review` → `gap learn g-M1-contract`（status=learning）→ `next --json` 仍 `gap_learn`；对比会话两段 | `sessions/20261104-032049-coach.md:26-48,61-84`；`next --json` |
| 3 | **重要** | 一条导师回复里同时存在两个“下一步”：正文“回到作品、artifact add + review”与页脚“▶ 唯一动作：gap_learn”；未记录 `mentor_next_conflict`（journal 无该事件） | 阅读 guide 的两次回复（say 与 gap learn） | `sessions/20261104-032049-coach.md:48,82,101`；journal 事件种类 |
| 4 | **重要** | critic 虚构“步数上限为 6”：explainability 要求“说明上限为何是 6”，同一次 robustness 又说“无步数硬上限”；作品与设计说明中均无 6 | 查看评审 note 与修改项 | `state/reviews.json:35,44` |
| 5 | 一般 | 切换不持久、记录不完整：guide 仅覆盖 2 次交互即被 `gap_learned` 自动切回 coach；会话文件仍名 `-coach.md`、文件头 `mentor: coach` 却混排 guide 回合；`latest.md` 单槽覆盖，切换瞬间的 `coach→guide` 16 秒后即被覆盖，查不到“为什么换导师” | `switch guide` → `say` → `gap learn` → `say` → `status` | `sessions/` 两个 `-coach.md`；journal seq 19/27；`handoff/latest.md` |
| 6 | 一般 | 时长约束未被采纳：三次明确说“只有十分钟”，`start_profile`/`status` 始终 60 分钟切片；`start` 当屏打印“切片：20 分钟”与档案 60 自相矛盾；`next` 仍按 60 分钟给三件交付物 | 对话中说“只有十分钟” → `status`/`next --json` | `status` 输出；`next --json` `minutes:60` |
| 7 | 一般 | 反馈与示例代码相反：预测题所给 `calc` 显式排 bool，正确答案应为 error；导师答“你猜对了……`{'result': 2}`” | 按微课代码推演，对照导师回复 | `sessions/20261104-032049-coach.md:84,96` |
| 8 | 一般 | `help_level` 话术与规则冲突：guide 说“这样只能算受助完成”，入口文档说 guide 微课不计入 `assisted_level`；`status` 最高 L3 但作品 `assisted=1`，学习者无法判断会被怎么记 | 阅读 START_HERE 规则 3，对照 guide 回复与 `status` | `START_HERE.md` 规则 3；session 2:48；`status` |
| 9 | 一般 | `start --help` 在项目外直接报 `not inside a LearnArk project` 并 **exit 1**（文档只列 0/2/3/4），不显示用法；在项目内 `--help` 才正常 | 在 `C:\Users\YK\Desktop\LearnArk` 执行 `start --help` | 命令输出 |
| 10 | 一般 | 会话头把学习者标成 `learner: P1`（默认占位），与本次 P3 不符；未提供 `init --name/--self-report` 时无设置入口 | 查看会话头与 project.json | `sessions/20261104-031938-coach.md:3`；`.learnark/project.json` `learner_profile.id=P1` |

## 5. 使用负担

- 师生往返：**8 次**（段 1：`start` / `say` / `review` / `say`；段 2：`start` / `say` / `gap learn` / `say`）；其中自由发言 `say` 4 次
- 命令数：约 **25 条**产品命令 + 1 次运行脚本（含 1 次失败的 `start --help`、多次 `status`/`artifact list`/`gap`/`next`）
- 需要阅读的公开文档：4 处（`round-03.md`、`learner-brief.md`、`START_HERE.md`、`personas.md` 模板）
- 实际墙钟：段 1 约 62 秒、段 2 约 48 秒（LLM 响应快，不代表学习时长；我没有在阅读/写代码上凑满 10 分钟）
- 不清楚的地方：
  1. 作品到底登记了几件？“最新作品”是否等于“只有这件”？
  2. `next` 说 review 设计说明，`review` 实际评的是代码——我该准备哪一件？
  3. `gap learn` 之后“唯一动作”还是 `gap learn`，我是该再学一遍，还是去改代码？
  4. 切换导师后还能聊几轮？`gap learn` 后自动回 coach，页脚与正文谁算数？
  5. “受助完成”到底记在哪里？`help_level` L3 与 `assisted_level=1` 为什么不一致？
  6. 60 分钟切片与我说的 10 分钟冲突时，听谁的？

## 6. 结论

- **是否完成场景目标: 是**。两段式中断恢复、新进程仅凭项目文件续学、导师切换、两次保存都发生了；没有把未完成标成完成，也没有重复开场三问。存在较多重复、错误陈述和“下一步”冲突，但不阻塞主流程。
- **最需要修的一件事**：把“已登记作品清单 + 唯一动作”变成导师上下文与界面的**单一事实源**——批量登记时列出全部作品（不要让导师误判“未登记”），并把 `next` 在 `gap learn` 后推进到“改作品 → 重新 review”，导师正文不得与“▶ 唯一动作”冲突。

## 7. 证据索引

| 类型 | 路径 |
| --- | --- |
| 段 1 会话 | `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r03-s3\proj\sessions\20261104-031938-coach.md` |
| 段 2 会话 | `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r03-s3\proj\sessions\20261104-032049-coach.md` |
| 交接（最终） | `...\proj\.learnark\handoff\latest.md`、`latest.json`（coach→coach，pause） |
| 事件流 | `...\proj\.learnark\journal\events.jsonl`（`artifact_added` seq 5/6；`review_recorded` seq 10；`mentor_switch` seq 19 coach→guide、seq 27 guide→coach；`handoff` seq 16/30） |
| 评审记录 | `...\proj\.learnark\state\reviews.json`（`r-M1-d3e79946`，`artifact_ids` 两件，`threshold_pass:false`） |
| 我的作品 | `...\proj\m1\agent.py`、`...\proj\docs\m1-design.md`（登记副本在 `...\proj\artifacts\M1\`） |
| 切换前 status | 导师 coach；contract open / robustness open；交接 `coach→coach(pause)`；next `gap_learn`；切片 60 |
| 切换后 status | 导师 **coach**（`gap_learned` 已回退）；contract `learning`；交接 `guide→coach(gap_learned)`；next `gap_learn`；切片 60（guide 回合的证据为 say 页脚 `导师：guide` 与 journal seq 19） |
