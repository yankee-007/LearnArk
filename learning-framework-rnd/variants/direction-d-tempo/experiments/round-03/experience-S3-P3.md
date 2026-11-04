# 体验报告 — direction-d-tempo round-03 S3（导师切换与中断恢复）

- 版本: direction-d-tempo 0.2.2（core 1.0.1 / schema 1）
- 体验者: 独立子 Agent（DeepSeek Harness / deepseek-flash），独立上下文，非研发者
- 场景: S3（P3 Mia；两段各约 10 分钟，中断恢复 + 导师切换）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r03-s3\proj`
- 入口: `python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-d-tempo\runtime\learn.py <命令>`（工作目录为项目目录；每条命令前 `. C:\Users\YK\Desktop\LearnArk\_sandbox\env.ps1` 并设 `PYTHONIOENCODING=utf-8`）
- 交互预算: 两段共用 10 次；实际学习者发言 **5 次**（第一段 2 次，第二段 3 次）；有效 LLM 交互 **8 次**（第一段 3 次 = start+2 say，第二段 5 次 = 2 次 start+3 say）；另有 1 次 `start` 被当日 2/2 上限拒绝、未调用 LLM。未使用 `--offline`，全部为真实 API；实际返回模型 `deepseek-flash`（配置 `deepseek-chat`，`start`/`status` 均有披露）。

## 方法与限制

- **新进程**：每次 tool 调用都是独立 `pwsh -Command` 进程，不在旧进程里复用状态；第二段首条命令 PID=41584，后续命令 PID 分别为 14300/26492/7548/35976/524/37564/37784/27244/36504。恢复仅通过项目目录下的 `.learnark/` 与 `sessions/` 文件成立。
- **模拟时钟**：第二段先在真实时间 2026-11-04 03:19 新进程 `start`；当日晚间时段恰好用完 2/2 项后无法再排活动。为完成“与切换后的导师交流 1–2 轮 / 再结束一次”，按 `START_HERE.md` 公开的 `LEARNARK_NOW` 把时钟设到 `2026-11-05T20:00:00+08:00`（模拟“次日晚上”），仍是新进程、只读项目文件；会话头标注“模拟时间（LEARNARK_NOW=…）”，相关事件 `simulated:true`。LLM 仍为真实 API。此模拟不改变“只凭文件恢复”的结论，但 11-05 的导师归属是在模拟日期下观察到的。
- 未遇到 API/网络错误；两个回合出现一次静默 `mentor_update_retried`（`ok=true`，用户无感）。未使用离线模式。
- 只读公开入口、场景卡、模板和产品自身输出（sessions/handoff/journal/status）；未读源码、design、mentors、tests、历史报告，未修改产品与状态文件。

## 实际步骤（命令 + 关键输出摘要）

> 下文 `learn.py` 均指 `C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-d-tempo\runtime\learn.py`；每条命令前都重新 `. env.ps1`。

### 第一段（2026-11-04 03:19，真实时间）

1. 建项目（03:19:15）
   ```powershell
   python learn.py init --goal "用 Python 做出能调用工具的小 Agent" --dir "C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r03-s3\proj" --self-report "两周前学过一点 function calling，只记得模型会返回工具调用，细节忘了。今天只有十分钟。"
   ```
   输出：`已创建 Tempo 项目`；技能 10 个；卡片 12 张（今天到期）；`git: 已提交 ff8bebd（本地）`。

2. 开始（03:19:18）
   ```powershell
   python learn.py start "今天只有十分钟"
   ```
   输出：`本次导师：trainer · 高频练习导师   会话：20261104-031919-trainer`；`[模型] 实际返回：deepseek-flash（配置：deepseek-chat）`；候选 1 `recall-card-0001 / agent-loop / 5m / T1` 选中；理由“到期组：该卡逾期 0 天，先清到期；选 5 分钟的到期卡…”。导师问 Agent 循环四阶段与三种停止条件。

3. 第 1 次真实作答（03:19:25）
   ```powershell
   python learn.py say "四个阶段大概是：模型看当前对话和上一步结果，决定要不要调用工具，执行工具拿到返回，再把返回塞回对话让模型继续。停止条件我只记得两个：模型不再调用工具、直接给最终答案就停；还有达到最大轮数或工具一直报错也会停。"
   ```
   导师文字：`对：四个阶段你说全了（看上下文→决定调用→执行工具→回填结果）；停止条件漏了“连续没有新信息”这一条。`
   但同一屏“本轮记录”却写：`这一轮是提问/求助：按“无尝试”记录（不升级、不建卡；下一步以 status 为准）。`（详见问题 1）

4. 第 2 次作答（03:19:33）
   ```powershell
   python learn.py say "我的理解是：工具反复返回同样的内容、或者拿回来的信息对回答没有帮助，再继续转下去也不会多出新东西，这时就该停，直接把现在能答的答复给用户。"
   ```
   输出：`提示级别 0（独立完成） · 本题判对`；`agent-loop L0→L1`；`card-0001 记 good`；`活动完成：是`。

5. 看 status（03:19:38）
   ```
   导师  trainer
   今日 2026-11-04 · 预算 10 分钟（累计） · 已用 5 · 剩余 5 分钟 · 已排 1/2 项（完成 1 项）
   到期  11 张卡（最久逾期 0 天）
   下一步（下次）：recall_card · tool-contract（5 分钟，Tier 1；recall-card-0003）
     说明：今天已排满或预算不足，这是下次进入时的建议。
   ```

6. 结束第一段（03:19:43）
   ```powershell
   python learn.py pause --note "先到这里，晚上再继续；我两次时间都不多。"
   ```
   输出：`已保存交接：…\.learnark\handoff\latest.md`；交接含“上次停在哪：recall_card · agent-loop”“未完成：无”“下一步：下次 start 重新调度”；`git state: no-remote`，commit `20261da`。

### 第二段（新 PowerShell 进程；03:19:54 起）

7. 新进程恢复（PID=41584，03:19:54）
   ```powershell
   python learn.py start "晚上又只有十分钟"
   ```
   输出：`上次停在哪：recall_card · agent-loop（2026-11-04 03:19）`；`交接下一步：下次 start 重新调度（到期优先）`；`[预算] 本次 10 分钟 · 已用 5 · 剩余 10（今日累计 15）`；`本次导师：coach`；`[导师] trainer → coach：按活动类型绑定导师（本次是概念块），不是随机切换。` 选中 `block-2026-W45-step1-eval-harness / 10m / T2`，理由“到期组已清空，进入本周块步骤”。

8. 回答 coach（PID=14300，03:20:09）
   ```powershell
   python learn.py say "因为 10 条用例只说明这次每条过没过，没有参照就不知道改动是变好还是变差。固定输入和期望结果是为了每次都能重跑，基线指标是上次的分数，比如上次 10 条中 8 条过，这次只剩 6 条，就是回归，要回去查。"
   ```
   输出：`提示级别 1（小提示） · 本题判对`；`eval-harness L0→L1`；`本周块第 1 步完成（无产物，不计 L3 依据）`；`活动完成：是`。coach 又追问：“如果这次改了用例集，还能直接和旧基线比吗？为什么？”

9. 显式切换导师（PID=26492，03:20:16）
   ```powershell
   python learn.py switch examiner
   ```
   输出：`已切换导师：coach → examiner`；`交接已写：…\.learnark\handoff\latest.md`；`保留：目标、技能等级、到期队列、卡片、本周块；不保留旧会话正文作为上下文（只读 handoff 摘要）。`；`下一个活动将由调度器决定，不受导师 next 影响。`

10. 切换后 status（PID=7548，03:20:20）
    ```
    导师  examiner
    今日 2026-11-04 · 预算 15 分钟（累计） · 已用 15 · 剩余 0 分钟 · 已排 2/2 项（完成 2 项）
    下一步（下次）：recall_card · tool-contract（5 分钟，Tier 1；recall-card-0003）
    ```

11. 同日再 start（PID=35976，03:20:33）
    ```powershell
    python learn.py start
    ```
    输出：`今日已排满 2/2 项（完成 2 项）… 今天不再排新活动——这不是欠账：到期的卡明天仍在队列里。`；`现在可以 pause 结束并保存；…或明天直接 start。`

12. 模拟“次日晚上”再 start（PID=524，03:20:40；`LEARNARK_NOW=2026-11-05T20:00:00+08:00`）
    ```powershell
    python learn.py start "晚上只有十分钟"
    ```
    输出：`上次停在哪：concept_block · eval-harness（2026-11-04 03:20）`；`[时间] 模拟时钟 2026-11-05T20:00:00+08:00`；`[导师] examiner → trainer：按活动类型绑定导师（本次是记忆卡），不是随机切换。`；`本次导师：trainer`；选中 `recall-card-0003 / tool-contract / 5m / T1`。**显式切换的 examiner 没有出现在新会话里。**

13. 回答 Q1（PID=37564，03:21:00）
    ```powershell
    python learn.py say "要写清三类：工具的名字，给模型看的用途说明，还有参数——每个参数的名字、类型、是不是必填。"
    ```
    输出：`提示级别 0（独立完成） · 本题判对`；`tool-contract L0→L1`；`活动完成：是`；导师追问 top_k 传成字符串“10”时怎么办。

14. 回答 Q2（PID=37784，03:21:06）
    ```powershell
    python learn.py say "应该直接拒绝这次调用，返回参数类型错误，让模型自己改成整数再调用；不能偷偷把字符串转成数字，不然模型永远学不会正确格式。"
    ```
    输出：`两问都过，本轮结束`；`tool-contract 今天已升过一级`；`card-0003 记 good`。

15. 第二次结束（PID=27244，03:21:13）
    ```powershell
    python learn.py pause --note "晚上也到这儿，明天继续。"
    ```
    输出：handoff 已保存；“上次停在哪：recall_card · tool-contract”“未完成：无”“未决问题：无”；commit `2e1f402`。

16. 最终 status（PID=36504，03:22:26，模拟 11-05 20:02）
    ```
    导师  trainer
    今日 2026-11-05 · 预算 10 分钟（累计） · 已用 5 · 剩余 5 分钟 · 已排 1/2 项（完成 1 项）
    本周块：block-agent-dev-2026-W45 … 步骤 1/3
    下一步（下次）：recall_card · tool-calling（5 分钟，Tier 1；recall-card-0005）
    ```

## 会话 / 交接 / 状态证据路径

- 第一段会话：`C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r03-s3\proj\sessions\20261104-031919-trainer.md`
- 第二段切换前会话：`…\sessions\20261104-031957-coach.md`
- 第二段切换后（11-05 模拟）会话：`…\sessions\20261105-200000-trainer.md`
- 交接：`…\.learnark\handoff\latest.md`（两次 pause 与一次 switch 各覆盖一次；最终版本为 11-05 20:01）
- 权威事件流：`…\.learnark\journal\events.jsonl`（51 条；关键：seq 8 `turn_without_attempt`、seq 9 `attempt(correct=None)`、seq 12 `attempt(correct=True)`、seq 17 `activity_completed`、seq 33 `mentor_switch` coach→examiner、seq 35 `session_opened` mentor=trainer、seq 50/51 handoff/pause）
- 项目状态：`…\.learnark\project.json`（`mentor` 最终为 `trainer`；`updated_at=2026-11-05T20:00:00+08:00`）

### 切换前后 status 摘要

| 时点 | 导师 | 今日预算/已用/剩余 | 已排/完成 | status 的下一步 |
| --- | --- | --- | --- | --- |
| 03:19:38（第一段结束前） | trainer | 10 / 5 / 5 | 1/2，完成 1 | recall_card · tool-contract（5 分钟，Tier 1；recall-card-0003） |
| 03:20:20（switch 后立即） | **examiner** | 15 / 15 / 0 | 2/2，完成 2 | recall_card · tool-contract（5 分钟，Tier 1；recall-card-0003） |
| 11-05 20:02（第二段结束后） | **trainer** | 10 / 5 / 5 | 1/2，完成 1 | recall_card · tool-calling（5 分钟，Tier 1；recall-card-0005） |

`switch` 写下的交接（03:20:16）记录“导师：coach → examiner”“未决问题：无”；但下一次 `start` 打开的会话 `mentor=trainer`，控制台只给了一行“按活动类型绑定导师，不是随机切换”，journal 里没有 examiner→trainer 的回切事件。

## 完成情况

- **开始**: 成功。`init` 建项目并提交；`start` 在 1 次内给出本次活动、理由、导师和真实模型。
- **诊断/定位**: 成功。首次进入提示“自述不计等级，只看行为证据”；调度直接进入到期卡。
- **尝试与反馈**: 部分成功。5 次学习者发言中 4 次判对（3 次升级；第 5 次因同一技能当天已升级而只记卡片 good）；第 1 次实质作答被记为“提问/求助”，无证据（问题 1）。
- **保存**: 成功。两次 `pause` 都写 handoff、存档并 git commit；第二次 `pause` 明确“未完成：无”。
- **恢复**: 成功。新进程只凭项目文件即显示“上次停在哪/交接下一步”，没有重复 agent-loop 卡片或已完成的 recall 模板；第二个活动是 `eval-harness` 本周块，第三个是 `tool-contract` 卡。
- **切换导师**: 部分失败。自动 `trainer → coach` 有说明、可继续；显式 `switch examiner` 成功写交接，但下一次 `start` 被活动类型重新绑回 `trainer`，**未能与 examiner 交流 1 轮**（问题 2）。
- **再结束**: 成功。11-05 第二次 `pause` 再次写 handoff，下一步可用。
- **是否把未完成说成完成**: 未发现。status 的两段完成数（1/2、2/2）与实际活动一致；本周块始终显示“步骤 1/3”；handoff“未完成：无”与实际相符。coach 在活动完成后的追问未被回答，但活动完成标准已满足（问题 3 记录未决问题丢失）。

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 新进程直接 `start`，它知道上次停在哪、下一步是什么 | 是：首屏显示“上次停在哪：recall_card · agent-loop”“交接下一步”，并解释预算累计 | 03:19:54 start 输出；`handoff/latest.md` |
| 不重复已学内容 | 是：未重抽 agent-loop 卡，改做本周块 `eval-harness`，次日做 `tool-contract`；未发现同题重复 | 三张 session 头 `activity`；journal `session_opened` seq 3/20/35 |
| 不把未完成说成完成 | 是：本周块 1/3，handoff 未完成无；完成数与实际活动一致 | final status；两次 pause 输出 |
| 两段各 10 分钟能各完成一个单元 | 是：5 分钟回忆卡 + 10 分钟概念块；但第一段剩余 5 分钟未再排活动，第二段 10 分钟用完后无余量 | 03:19:38 status；03:20:33 start 拒绝 |
| 用 `switch` 换一个导师，并与之交流 1–2 轮 | 否：`switch examiner` 成功，但下一次 `start` 立刻回切 `trainer`；无法与 examiner 对话 | switch 输出；11-05 start `examiner → trainer`；final status `trainer` |
| 切换后新导师知道前面发生了什么 | 部分：`start` 头部和 handoff 知道活动名/下一步；导师正文没有引用学习者上一段说过什么，coach 的未答追问也没进 handoff | 11-05 start 头部；coach session 第 19–20 行；handoff“未决问题：无” |
| 两位导师的“下一步”一致 | 否，但系统明示以调度器为准：trainer 建议“先重抽同一张卡复述三种停止条件”，coach 计划继续 eval-harness，实际调度先做本周块、次日做 tool-contract；导师建议标注“只是建议、不排课” | 各轮 `导师建议` 行；03:19:54 start 候选表 |
| 结束时有明确下一步 | 是：`pause` 写“下次 start 重新调度”；`status` 给出具体卡 id 与分钟数 | 两次 pause；三次 status |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | **重要** | 一段实质作答被运行时判为“提问/求助”：`attempt correct=None`、`evidence none`、不建卡；同一屏导师文字却说“四个阶段你说全了”，导师机器块还给出了 `correct=false` + `misconception`。三者不一致，且 `flags.text_conflict=False`，学习者会以为答对已计入，实际没有。 | 在 agent-loop 回忆卡首问下输入陈述句（无问号/吗/呢/给我/帮我），内容含“我只记得两个…”。 | `sessions/20261104-031919-trainer.md` 第 12–25 行；journal seq 8/9；`status` 的“上次帮助” |
| 2 | **重要** | `switch examiner` 报告成功并写 handoff，但下一次 `start` 被活动类型重新绑定为 `trainer`；学习者无法与所选导师交流，S3 的显式切换步骤无法完成。handoff 记“导师 examiner”，下一会话 `mentor=trainer`，journal 没有回切事件，切换语义与生效范围不清。 | 任一活动后 `switch examiner` → 看 status（examiner）→ 新进程 `start`（本次为 5 分钟记忆卡）→ 会话导师变 trainer。 | switch 输出；03:20:20 status；11-05 start 输出；`sessions/20261105-200000-trainer.md` 第 2 行；journal seq 33/35；`project.json` 的 `mentor` |
| 3 | 一般 | 切换时丢失未答的导师追问：coach 问“改了用例集还能和旧基线比吗？”，学习者直接 switch；handoff 的“未决问题：无”“哪里不稳：暂无记录”没有记录它，次日也没有回到该问题。handoff 只有活动名/计数，没有“学到什么/卡在哪”的内容。 | coach 活动判对并追问 → `switch examiner` → 读 handoff“未决问题” → 下次 `start`。 | `sessions/20261104-031957-coach.md` 第 19–20 行；03:20:16 switch 输出/handoff；`handoff/latest.md` |
| 4 | 一般 | `status` 的“下一步（下次）”与同日再次 `start` 的实际选择不一致：03:19:38 说下一步是 5 分钟 `tool-contract` 卡，03:19:54 却选了 10 分钟 `eval-harness` 本周块，理由“到期组已清空”（同日 recall 模板去重）；status 还写“今天已排满或预算不足”，而当时是 1/2 项、剩余 5 分钟。两个“下一步”来源不同，文案没解释“下次”是明天还是下一次 start。 | 做完一张 5 分钟卡（剩余 5 分钟、1/2 项）→ `status` 记下下一步 → 同日再 `start` 并追加分钟数。 | 03:19:38 status；03:19:54 start 候选表/理由；journal seq 5/22 |

补充观察（不计入问题）：`status` 的模式行始终同时显示“配置模型 deepseek-chat / 上次实际 deepseek-flash”，披露清楚；两段各说 10 分钟但 status 累计 15 分钟（第一段未用的 5 分钟不累计），文档有解释，首次看略绕。

## 使用负担

- 师生往返：学习者发言 **5 次**（第一段 2 次、第二段 3 次）；有效 LLM 交互 8 次；未超 10 次预算。第一段停在 3 次有效交互（start+2 say），低于计划的 4–5 次：5 分钟卡两问就完成，剩余 5 分钟没有可排活动；没有再造对话凑数。
- 命令数：CLI **17 次**（version 1、init 1、start 4、say 5、status 3、pause 2、switch 1）；另外读取 sessions/handoff/journal 6 次。
- 需要阅读的文档：4 处（`round-03.md`、`learner-brief.md`、`START_HERE.md`、`personas.md` 的模板；`AGENTS.md` 由环境自动注入）。中文显示正常，无乱码。
- 不清楚的地方：
  - 为什么“陈述句 + 我只记得两个”会被判成提问/求助；运行时只给通用 reason。
  - `switch` 到底影响什么：既然活动类型绑定导师，为什么 switch 还提示“已切换导师”，且 status/project.json 暂时也显示 examiner。
  - `status` 的“下次”是下一次 `start` 还是明天；同日模板去重为何不在“下次”投影里体现。
  - 两段各 10 分钟为何累计是 15 分钟（文档可解释，但第一眼像预算丢了 5 分钟）。
- 时间：真实墙钟 03:19–03:22（约 4 分钟）；另用 `LEARNARK_NOW` 模拟 11-05 20:00–20:01。不是真实 20 分钟；模拟只用于验证“新一天 + 切换后”的恢复，已在上文披露。

## 结论

- **是否完成场景目标: 否（部分完成）**。中断保存、新进程仅凭文件恢复、不重复、不虚报完成、两次结束都成立；但“用 switch 换一个导师并与切换后的导师交流 1–2 轮”没有达成，显式切换被下一次 `start` 的活动绑定覆盖。
- **最需要修的一件事**: 把 `switch` 的语义和生效范围做一致——要么让下一次活动真正使用所选导师（并在活动不匹配时明确拒绝/说明），要么把 `switch` 改成“仅表达偏好、下次 start 可能被活动类型覆盖”，且不要先报“已切换导师”、handoff 记 examiner、下一次却静默回切 trainer；同时把这次回切写进 journal/handoff。其次修“实质作答被判提问/求助”的判定与文字/机器块冲突检测。
