# 体验报告 — direction-d-tempo 0.2.4 · round-06 · S6 跨主题迁移（P4 Tina）

- **版本**: direction-d-tempo `0.2.4` / core `1.0.2`（项目 `.learnark/project.json` 记录 variant_version 0.2.4）
- **体验者**: 独立子 Agent（DeepSeek Harness 会话；底层导师模型实际返回 deepseek-flash；独立上下文，非研发者）
- **场景**: S6 跨主题迁移（P4 Tina，运营/非编程背景，目标英文工作邮件，20 分钟）
- **项目目录**: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r06-s6\proj`
- **入口**: `python ...\variants\direction-d-tempo\runtime\learn.py init --goal "能写出清楚、得体、简洁的英文工作邮件" --template email --dir <项目>`；此后 `start` / `say` / `status` / `pause`
- **交互预算**: 本轮任务 ≤8 次往返（场景卡总上限 12 次），**实际使用 7 次**（7 次 `say`）
- **时间**: 2026-11-04 12:06–12:08（真实时间，非模拟时钟）

## 实际步骤（命令 + 关键输出摘要）

1. `init --goal "能写出清楚、得体、简洁的英文工作邮件" --template email --dir <proj>` → 成功。输出：`模板 email`、`技能 6 个`、`卡片 6 张（今天到期）`、`git: 已提交 93ad666（本地）`、`下一步：start --minutes 20`。`project.json` 有 `"template_id": "email"`、`"diagnosed": true`，无 agent-dev 残留。
2. `start "今天只有二十分钟"` → 成功。识别预算 20 分钟（`matched: 二十分钟`），显示 `[诊断] 首次进入：先用到期卡自测校准等级`；候选表 3 项；本次导师 trainer（按活动类型绑定）；实际返回 `deepseek-flash`。选中 `recall-card-e001`（subject-line，5 分钟）；计划 2 项：该卡 + `block-2026-W45-step1-structure-clarity`（8 分钟）；12 分钟的 `step2` 被排除（`12 分钟活动本次放不下（剩余 7 分钟）`）。开场只问“英文邮件主题行应包含哪些信息？”
3. `say` 回答主题行三要素（含一处不确定：“紧急程度/截止时间要不要放进去？”）→ 导师判对，答复具体，并解释 URGENT 只在硬截止时用；追加 30 秒练习“把中文需求改成主题行”。
4. `say "Budget sheet from last meeting — need it by Friday for submission"` → 判对，逐项点出对象/来源/时间压力/用途。
5. `say "System maintenance on Friday — no access after 18:00"` → 判对；导师主动收尾“时间到，本轮 3 题全对”。3 题都记 `correct`、`help_level 0`；`subject-line L0→L1`，`card-e001` 记 good（2 天后到期）。
6. `start`（同一进程）→ 沿用今日 20 分钟（已用 5，剩 15）；导师自动切到 coach，并说明“按活动类型绑定导师，不是随机切换”。选中 `block-2026-W45-step1-structure-clarity`（8 分钟）：一封邮件只承载一个请求；给出“6 句压 3 句”的最小例子，要求用自己的话复述。
7. `say` 复述（一个请求为主、背景只留必要、期限只出现一次、不相干请求合并或另发）→ 导师肯定，补一个“可合并前提”的边界，要求一句话重述。
8. `say` 重述边界 + “我还有七分钟，想现在就用一封真实邮件练一下，可以吗？” → **导师文字说“边界复述准确”**，但拒绝加练（“不在这里加练，也不承诺排课”）；同屏“本轮记录”却显示 `这一轮部分正确：按 partial 记录…补齐缺的部分再答一次`、`活动完成：否（仍在进行中）`。CLI 同时输出 `[预算] 已记录 7 分钟（原句包含“七分钟”）；今日预算 20，已用 13，剩 7`。
9. `start "再给我二十分钟，我想真的写那封邮件"` → 被拒：`今日已排满 2/2 项…不追加新的分钟数`、`今天不再排新活动`。`plan --json` 显示次日建议是 `recall-card-e002`（5 分钟）+ `block-...-step3-language-accuracy`（8 分钟），12 分钟的写作块 `step2` 仍不在计划里。
10. `say` 直接提交手头真实邮件 v1（5 句），说明“排不进写作块，请按结构与简洁标准具体指出哪句该删、哪句该改” → 导师仍给出逐句点评（见下），但声明“这是你手头邮件的点评，不是本次活动的练习”。
11. `say` 提交按反馈修改后的 v2（3 句）→ 导师确认改对，并补一个逻辑边界（PO 期限早于交付日、未说明原因）。运行时把两次邮件点评都记为该 concept 活动的 `correct`、`observed` 证据。
12. `status` → 预算 20、已用 13、剩 7、已排 2/2（完成 2 项）；技能 6 项全为写作；下一步 `recall_card · opening-purpose`；本周块“把 6 句长邮件压到 3 句，保留请求与期限”步骤 1/3。
13. `pause --note "…"` → 生成 handoff，`git: 5de2644`，`written=yes committed=yes pushed=no（无远程）`，下次起点 `recall_card · opening-purpose（5 分钟）`。
14. **新进程** `status` + `start` → 记录完整：技能/卡片/交接/下一步都在；`start` 仍因今日 2/2 排满而不排新活动，并明确“这不是欠账”。确认跨进程恢复成功，下一步仍是写作任务（opening-purpose 卡片），非编程内容。

## 两版邮件

**v1（提交原稿，5 句）**

> Hi Mark,
>
> I hope you are doing well. I am writing to update you on the Atlas project. Because two reviewers were out of office last week, the delivery will be delayed by two days. The new delivery date is November 12. Please let me know if this works for you, and could you also send the updated PO number when you have time?
>
> Thanks,
> Tina

**v2（按反馈修改，3 句）**

> Hi Mark,
>
> I am writing to update you on the Atlas project. Because two reviewers were out of office last week, delivery will be two days later than planned, on November 12. Please let me know if this date works for you, and send the updated PO number by November 11.
>
> Thanks,
> Tina

## 导师反馈摘要

- v1：结构已不错（一个更新、一个期限、一个请求）；两处可动——① 删 `I hope you are doing well.`（寒暄不承载信息，删掉不影响得体）；② `when you have time` 是唯一实质问题，让请求没有期限，与 `November 12` 的明确形成落差，建议改 `by November 11`；其余句子（原因、新日期、确认请求）都保留。
- v2：改得对（寒暄删了、PO 请求有明确期限、两个请求落在同一件事/同一人上可以合并）；边界提醒：PO 期限（11 月 11 日）早于交付日（11 月 12 日）逻辑成立但未说明原因，对方可能追问。
- 主题行训练：三题均逐条指出对象/来源/时间压力/用途是否齐全；说明 `URGENT` 滥用会削弱可信度。反馈都落在具体句子或词上，没有“写得好”式空话。

## status 摘要（2026-11-04 12:08）

```text
模板 email · 版本 direction-d-tempo 0.2.4 / core 1.0.2
今日 预算 20 分钟（累计） · 已用 13 · 剩余 7 · 已排 2/2 项（完成 2 项）
技能：subject-line L1 observed；structure-clarity L1 observed；
      opening-purpose / ask-clarity / tone-register / language-accuracy 均 L0 self_report
上次帮助：提示级别 1（小提示） · 判对 · 证据 independent
本周块：block-email-2026-W45 · 把 6 句长邮件压到 3 句，保留请求与期限 · 步骤 1/3
下一步（下次）：recall_card · opening-purpose（5 分钟；recall-card-e002）
同步：written=yes committed=yes pushed=no（无远程，跨设备未验证）
```

## 完成情况

- **开始**: 成功。`init` + `start` 两条命令进入；无安装/配置门槛（测试环境已注入密钥）。
- **诊断或定位**: 部分成功。`[诊断] 首次进入：先用到期卡自测校准等级` 有说明，但首批 6 张卡全部当天到期，所谓诊断实际退化为刷到期卡（5 分钟主题行），没有针对“英文邮件写作水平”的定位题。
- **尝试与反馈**: 成功（内容层面）。主题行 3 题、概念复述 1 次、真实邮件 2 版；反馈具体到句子/用词。但“写整封邮件”不在当天调度内，是学习者自行塞进 concept 会话才发生的，且运行时把邮件点评记到了概念活动名下。
- **保存/恢复**: 成功。`pause` 写出 handoff 并本地提交（5de2644）；新进程 `status`/`start` 记录完整，下一步仍是写作。
- **切换导师**: 自动发生 trainer→coach，输出有一行解释“按活动类型绑定导师，不是随机切换”；未手动 `switch`（本场景不要求）。

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| `--template email` 后课程、任务、评分整体换成写作 | 是：6 个写作技能、6 张写作卡、块任务“6 句压 3 句”，反馈谈请求/期限/寒暄 | `project.json`、`due`、`skills`、两份 session |
| 20 分钟内能真正写一封邮件并改一版 | 否：5+8=13 分钟占满 2 项，剩 7；12 分钟写作块 step2 连续被排除；追加时间被“今日已排满”拒绝；邮件两版是我自己插进 concept 会话才得到点评 | `start` 候选表、journal seq 27/36、`plan --json` |
| 反馈针对我的句子，不是泛泛表扬 | 是：点名删 `I hope you are doing well.`、改 `when you have time`，并指出 PO 期限与交付日的逻辑缺口 | `sessions/20261104-120706-coach.md` |
| 非编程、零基础能看懂 | 基本是：无代码/Agent 术语；但界面反复出现“真实 API/密钥/配置模型/实际返回模型”等基础设施词 | 各命令输出首部 |
| 能力记录独立，不混 Agent 开发 | 是：只有 subject-line / opening-purpose / ask-clarity / structure-clarity / tone-register / language-accuracy | `skills`、`status` |
| 重新打开后记录还在、下一步仍是写作 | 是：新进程 handoff/skills/下一步均在；下一步 opening-purpose 卡 | 新进程 `status`/`start` |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | 重要（对 S6 近乎阻塞） | **20 分钟预算排不进“写整封邮件”的核心活动**。首日 5 分钟到期卡 + 8 分钟概念占满 2 项，只剩 7 分钟；12 分钟的 `step2` 因“放不下”被连续排除；再 `start` 被“今日已排满 2/2”拒绝且不追加分钟；次日计划仍是 5 分钟卡 + 8 分钟 quiz，`step2` 继续不在列。结果是“邮件模板”首日只有卡片和概念，没有写作产出。 | `init --template email` → `start "今天只有二十分钟"` → 完成两项 → `start "再给我二十分钟…"` | journal `seq 5`（step2 `not_entered`）、`seq 27`（step2 `rejected`）、`plan --json` items 无 step2、refusal 输出 |
| 2 | 重要 | **正确回答被判 partial，界面与导师原话矛盾**。第三轮边界复述导师说“边界复述准确”，机器块 `attempt.correct=true`，但运行时 `prose_verdict=partial`，最终记 `partial-no-credit` 并显示“补齐缺的部分再答一次”。推测：导师句中“本轮概念**部分**就到这里”的“部分”被当作 partial 信号（未验证）。同一轮还显示“活动完成：否”，而 `status` 记“完成 2 项”。 | 完成概念复述 → 在回答后追加“我还有七分钟，想…练一下” → 观察“本轮记录” | `sessions/20261104-120706-coach.md` L37–52；journal `seq 39`（`turn_partial`, `prose_verdict=partial`, `block_correct=true`, `decision=partial-no-credit`）、`seq 40` |
| 3 | 一般 | **学习者回答里的“N 分钟”被当成预算指令**：我说“我还有七分钟”，CLI 打印 `[预算] 已记录 7 分钟（原句包含“七分钟”）`；本次因总预算已定而未变，但若预算未满会追加，普通用户可能无意改动当天预算。 | 在 `say` 文本中写“我还有七分钟” | journal `seq 36`（`budget_set`, `source: say`, `matched: 七分钟`） |
| 4 | 一般 | **离题内容被记成活动证据**：导师明确说“这是你手头邮件的点评，不是本次活动的练习…不加练”，但两版邮件点评都被记为该 concept_block 的 `correct`/`observed` 证据，可能抬高 structure-clarity 的掌握度。 | 在 concept 活动结束后用 `say` 提交邮件并获点评 | `sessions/…coach.md` L74–81、L100–107；journal `seq 43`、`seq 47` |
| 5 | 一般（内部残留） | **email 模板的 `step2` 内部 `activity_type` 仍是 `code_kata`**。学习者界面目前不显示类型，不构成可见编程残留；但这是模板迁移未清干净的类型名，若将来在 UI/导出中展示会泄露编程语义。 | `init --template email` 后看候选/计划 JSON | journal `seq 5` candidates 中 `block-2026-W45-step2-structure-clarity` 的 `activity_type: "code_kata"` |
| 6 | 一般 | **首日诊断=刷到期卡**：6 张卡全部当天到期，`[诊断]` 只让做主题行回忆卡；没有写作水平定位（哪怕一道“写 3 句自我介绍邮件”），对“零基础写作”的人无法判断起点。 | `init --template email` → `start` | 首次 `start` 输出；`due`（5 张到期）；`skills` 中 4 项为 `self_report` |

## 使用负担

- **师生往返**: 7 次（上限 8；场景卡 12）——主题行 3 次、概念复述 1 次、边界+请求 1 次、邮件 v1 1 次、邮件 v2 1 次。
- **命令数**: 18 条（`init` 1、`start` 4（含 1 次排满被拒、1 次新进程恢复）、`say` 7、`status` 2、`pause` 1、`plan` 1、`due` 1、`skills` 1）。
- **需要阅读的文档**: 普通学习者只需 `START_HERE.md` 1 份（命令表清楚）；测试另用场景卡/说明/模板 3 份。
- **不清楚的地方**:
  - 20 分钟用完了却没写邮件，产品只说“今天不再排新活动”，不知道真正的写作块哪天才能轮到；
  - 导师说“准确”、界面说“部分正确”，不知道信哪个，也不知道要不要重答；
  - 回答里带“七分钟”被记成预算，是否影响后续不清楚；
  - 非技术用户看到“真实 API/密钥/配置模型 deepseek-chat/实际返回 deepseek-flash”是噪音，也不知道是否要处理。

## 结论

- **是否完成场景目标**: **部分完成（判否）**。主题迁移是真实的：模板、6 个写作技能、卡片、块任务、导师反馈全部围绕英文邮件（结构/语气/请求/简洁），没有学习者可见的代码、API 调用或 Agent 术语；记录独立、保存与跨进程恢复成功。但在 20 分钟预算内，产品没有安排“写整封邮件”这一核心任务（12 分钟块被排满规则挤掉，追加时间被拒），两版邮件与逐句反馈是我把邮件直接塞进 concept 会话后才拿到的，不属于调度内的写作活动；同时出现“正确回答被判 partial”的自相矛盾。
- **最需要修的一件事**: 让 20 分钟预算能排进“写/压缩一封真实邮件”的核心块——例如把 `step2` 时长降到 7–8 分钟，或允许在剩余 7 分钟“开始并跨会话续做”，并让到期卡让位给本周块的关键写作步骤；否则写作模板的首日体验只有卡片和概念，没有写作。
