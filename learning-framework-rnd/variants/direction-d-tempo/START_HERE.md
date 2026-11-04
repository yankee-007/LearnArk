# Tempo · 动态调度复习型（direction-d-tempo v0.2.6）

**一句话**：每次进入只说“今天只有二十分钟”，系统在 1 次交互内给出**做什么、为什么是它**，然后由导师带你把 5–20 分钟的微活动做完。
**适合**：每周 10–20 小时、但时间散在 10–25 分钟碎片里、经常中断返学的学习者。
**不是**：连续两小时作品冲刺（用 Forge）、课程目录/证书、后台推送或手机提醒。调度是确定性的，不用 LLM 决定学什么。

## 3 步快速开始（Windows PowerShell）

```powershell
cd C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-d-tempo
$env:DEEPSEEK_API_KEY = "sk-..."          # 真实导师；不设则自动离线脚本导师
python runtime\learn.py init --goal "能独立设计、实现并评测一个可用的 Agent 应用" --dir "$env:USERPROFILE\LearnArk\agent-dev"
python runtime\learn.py start --project "$env:USERPROFILE\LearnArk\agent-dev"
```

也可以一句话给预算：`python runtime\learn.py start "今天只有二十分钟" --project <项目>`。
`learn.cmd` 是同义入口：`learn.cmd start --project <项目>`。

## 命令表

| 命令 | 作用 |
| --- | --- |
| `init --goal TEXT [--template agent-dev\|email] [--dir PATH] [--minutes-per-week N] [--name SLUG] [--self-report TEXT]` | 建项目、种子技能/卡片/本周块、git init；`--self-report` 只记录学习者原话，不替你编写自述 |
| `start [--minutes N] ["一句含分钟数的话"]` | 调度并开始一个活动：候选表 + 理由 + 导师开场 + 恢复上下文 |
| `say "学习者原话"` | 交给导师，解析机器块并应用证据；`say -` 从 stdin 读 |
| `status [--json]` | 目标、今日预算、到期、技能平表、上次停在哪、下一步、git 三态 |
| `pause [--note TEXT]` | 写交接 handoff、存档、sync、给出下次起点 |
| `switch coach\|trainer\|examiner` | 结束当前活动并指定下一次 `start` 的导师（sticky，用掉或再次 switch 后清除） |
| `due [--json]` | 到期卡与到期技能，含逾期天数；每会话最多清 3 张 |
| `plan [--json] [--minutes N]` | 今天 ≤3 项建议（不显示欠账总数） |
| `review [--minutes N]` | 强制到期复习（跳过同日不重复过滤，仍受预算/leech 限制） |
| `skills [--json]` | 技能平表：等级、证据级别、到期、lapses、错误标签；卡片统计 |
| `sync [--message TEXT] [--recover]` | 只提交项目白名单；报告 written/committed/pushed；分叉时 `--recover` 只对 journal 做并集合并，状态快照冲突需人工选择；冲突退出码 3 |
| `doctor` | 项目/状态/日志/去重索引/锁残留/git/LLM/时钟偏差/版本一致性 |
| `export --out FILE` | 导出 Markdown 学习档案（不含密钥） |
| `version` | 版本信息 |

全局参数：`--project PATH`（默认从当前目录向上找 `.learnark/`）、`--offline`（等价 `LEARNARK_LLM=mock`，所有导师输出带 `[离线脚本导师]`）。
退出码：0 成功；2 用法错误；3 状态/并发冲突（或 doctor 发现问题）；4 环境/网络（例如 API 模式无密钥）。

预算解析（纯正则，不调用 LLM）：`20分钟/二十分钟/20min`→20；`一刻钟`→15；`半小时`→30；`一小时`→45（回显“按 45 分钟上限安排”）；`一会儿/几分钟`→10；无法解析→20 并提示。区间 5–45，越界夹取并回显。

**当天预算不会被静默改写**：你本次说的分钟数是“这一次可用的时间”，会加到今天已用的时间上；`status` 同时显示 `预算 / 已用 / 剩余`。
同一天再 `start` 但没给新的分钟数时，沿用今天的预算并明确提示（不会退回默认 20）；`--minutes` / 一句话则按新说的分钟数追加。
若今日已排满 2 项或剩余不足 5 分钟，`start` 只收尾、不排新活动；`status` 的“下一步”会标成（下次）。

**导师与活动绑定**：`recall_card → trainer`、`concept_block/explain_back → coach`、`quiz/transfer_task → examiner`。
两次活动之间导师变化时，`start` 会用一行说明“按活动类型绑定导师，不是随机切换”；活动进行中不会换导师，`switch` 会先结束当前活动（见下）。

## 调度与证据（你能观察到的规则）

- **两级选择**：Tier1 到期卡（逾期降序，单次最多 3 张）→ Tier2 本周块下一步 → Tier3 薄弱/新内容。当前 tier 过滤后为空才进入下一 tier，理由里会写“到期组已清空”。
- **组内打分** `0.40U+0.20W+0.15P+0.20F+0.05N−0.35R`：到期紧急度、薄弱度、计划推进、时长匹配、新鲜度、最近重复惩罚。同分按 `(due_at, activity_id)` 升序；输入只有 state + 预算 + 时钟，无随机、无网络。
- **硬过滤**：时长 ≤ 剩余预算；同日不重复活动模板；同日不重复技能（显式 `review` 除外）；leech 卡只在 ≥10 分钟预算出现。
- **证据**：只有 `correct=true` 且 `help_level≤1` 才能 +1 级，每技能每天最多 +1；`help_level≥2` 只记“受助完成”；examiner 给提示 → `examiner_hint_leak` 并降为 observed；导师 `next` 只记 `mentor_suggestion`，改计划会记 `mentor_schedule_conflict` 并按调度执行。
- **复述不算独立**：如果这一轮回答与导师刚给的例子高度重合（字符 bigram 覆盖率 ≥72%），运行时会记 `echoed_example`、把帮助等级抬到 ≥2，**不升级**、卡片按“hard”而非“good”排期；`status` 的“上次帮助/证据类型”可复核。
- **提问不算作答**：只有短、且没有作答内容的提问/求助才算纯提问（问号、吗/呢、开头请求词）；陈述句里出现“直接给最终答案”不算提问。纯提问记 `turn_without_attempt` 与 `correct=null`，不升级、不建卡；`status.last_turn.attempt_kind=question`。
- **部分正确单独记**：只有机器块 `result=partial` 或学习者明确说“只答出一半/没答全”才记 `result=partial`（不升级、不建卡、活动不完成）；导师文字里的“部分/漏了”不再降级正确回答。导师文字与机器块明确冲突记 `mentor_text_conflict`，两者都不产生证据/卡片。
- **核心写作块优先**：email 模板当前周块的可交付写作步骤（如 12 分钟写作块）优先于到期卡；预算不够时记 `core_block_deferred` 并让下一次 `start` 先做它，首日不会只有卡片和概念。`start --minutes 0`/拒绝追加时会用一行说明如何追加时间。
- **`say` 不改预算**：回答里的“七分钟/一刻钟”只算内容，记 `budget_ignored_in_answer`；预算只由 `start`/显式 `--minutes` 决定。
- **显式 switch 生效**：`switch examiner` 写入 `mentor_override`；下一次 `start` 优先由 examiner 带（必要时换成 examiner 能带的小测/回忆），用掉后清除；`status.mentor_override` 可查。
- **一轮一个判定**：导师文字与机器块明确冲突时记 `mentor_text_conflict`，以机器块为准，学习记录只出现一个结论，不会同时出现“对/未判对”。
- **卡片去重**：同 skill + 归一化 front 的卡片只保留一张，后续合并内容并记 `card_merged`；连续失败不会再生成三张同题误解卡。
- **积压折叠不静默**：到期卡超过 12 张时，最旧的若干张顺延 3 天并当场用一句 `[调整]` 说明（`backlog_folded` 事件可查）；**未完成的当前卡不折叠**，下一次先回到它（`resume_activity`）。
- **下一步唯一**：`status`/`plan` 的下一步只来自调度器；导师的 `next` 只显示为“导师建议（不排课）”。今天排满或预算不足时，下一步用“下次”投影给出**具体卡片/技能/活动 id**（不是 `-` 占位符）。`status` 会把可行决策缓存到 `.learnark/tmp/next-decision.json`，下一次 `start` 在同一状态签名下复用它（`next.decision_id` 可核对），不会出现 status 说 A、start 选 B。
- **预算文案**：候选放不下时只写“本次放不下（剩余 N 分钟）；下次（约 M 分钟）”，不再写“超出剩余 N 分钟”这类自相矛盾的比较；5 分钟够做 5 分钟活动时 status 显示“现在”。
- **时间到但未完成**：只有实际经过 ≥60% 计划分钟或学习者明确说“先到这里/不练了”时才记 `time_boxed_incomplete`；导师单方面说“时间到”记 `time_box_ignored`，活动保持开放，开头也写明“判对且达标才算完成”。
- **SRS**：阶梯 `[1,2,4,8,15,30,60]` 天，ease `[0.85,1.60]`；失败 step−2、ease−0.20、次日到期；连续 2 次 lapse → leech + 技能 −1 级并要求改写卡片；积压 >12 张折叠最旧 +3 天（`backlog_folded`）；每周新卡上限 `clamp(round(minutes_per_week/45),5,40)`，超出排队。
- **L3 唯一路径**：块产物 + ≥7 天延迟复测；纯卡练习最高 L2。所有等级变更带事件 ID 与产物路径。
- **产物是完成条件**：`code_kata` / `transfer_task` 的本周块步骤会声明产物路径（如 `artifacts/eval-cases.json`）。文件没落盘时只记 `artifact_required`，活动保持未完成；你后来把文件写好，再 `say`/`start`/`pause` 会记 `artifact_acknowledged` 并确认完成，`status`/handoff 都会提到它。
- **模型披露**：`status` 显示“配置模型 / 上次实际返回”，`start`/`say` 在真实 API 下显示实际返回的模型；两者不同时不会只报配置值。
- **自述**：`init` 不替你编写学习经历；只有 `init --self-report "我的原话"` 或你后来明确说的，才会记录为自述（且不计等级）。

## 记录在哪、怎么恢复

```
<项目>/.learnark/project.json        目标/模板/约束/学习者/导师/诊断标记
<项目>/.learnark/state/*.json        schedule / skills / cards / blocks 快照（原子写 + .bak）
<项目>/.learnark/journal/events.jsonl 权威事件流（追加写、幂等键、simulated 标记）
<项目>/.learnark/handoff/latest.md  交接：上次停在哪/试过什么/哪里不稳/下一步/未决问题
<项目>/sessions/YYYYMMDD-HHMMSS-<mentor>.md  每次会话的可读记录
<项目>/artifacts/                    作品与练习产物
```

- 换进程、换会话、干净克隆：直接 `start`，只依赖上述文件（不依赖旧聊天或进程内缓存）。
- 状态 JSON 损坏：自动从 `.bak` 恢复并在 `status`/`doctor` 提示；日志尾部半行会被丢弃并在下次写入前记 `journal_repaired`。
- 去重索引损坏：下一次写入自动从 journal 重建；`status` 不依赖它。
- 同步：`sync` 只提交项目白名单，绝不 force push；无远程时只到 `committed`，明确写“无远程，真实 GitHub 同步未验证”。
  - 分叉（本地与远程各有新提交）时：`status`/`status --json` 显示 `diverged`/`unmerged`，`doctor` 报 `git_divergence` 并退出 3，`sync` 冲突退出 3 并列出冲突文件。
  - 只冲突 `.learnark/journal/events.jsonl`（及 dedupe）时，`sync --recover` 按 event id 并集合并、重建去重索引、再推送；不会丢任何一方的事件。
  - `skills.json`/`cards.json`/`schedule.json` 等快照冲突**不会**自动合并：先人工保留一侧，再 `sync`；运行时不会猜。
  - 生成的项目带 `.gitattributes`（`* -text`），避免跨机器换行归一化改变文件哈希；锁/usage/sync-log 已在 `.gitignore`。
  - `.gitignore` 已排除 usage/sync-log/锁/.tmp；`doctor` 会把“被同步策略跳过但没被忽略”的文件报出来，不会假报干净。

## 离线模式

`--offline` / `LEARNARK_LLM=mock` 时用 `tests/fixtures/mentor_script.jsonl` 的脚本导师：流程、证据规则、到期与等级都真实运行，但**教学文本是脚本/模板，不代表真实 LLM 教学质量**。脚本没匹配到时会按“导师回复不完整 → 本轮无证据”处理（不向学习者暴露内部协议术语），不会伪造学习记录。真实导师偶尔漏掉机器可读块时，运行时会**静默补问一次**（`mentor_update_retried`，最多一次），仍缺则本轮不计证据。

## 已知限制与版本

- 版本 `0.2.6`，vendored core `1.0.4`（`runtime/CORE_VERSION`），schema 1。
- 同一项目的写命令用项目锁串行；锁等待超时或基于旧快照写入时退出码 3，不覆盖数据（见 `docs/recovery.md`）。
- 中断/崩溃后 journal 是权威，`start` 会补回卡片复习、等级与完成标记；`state/*.json` 只是快照，不要手改。
- 模拟时间（`LEARNARK_NOW`）只证明调度与 SRS 逻辑，不证明真实 6 周记忆保持或真人收益；相关事件自动带 `simulated: true`。
- SRS 参数与每周卡量上限为设计初值，未经真人校准；周项目块（30–60 分钟）只能部分补偿碎片化，复杂工程能力的损失未测量。
- 无远程仓库时 `pushed` 与真实跨设备未验证；干净克隆 ≠ 真实换机。
- 导师为 LLM 时教学回复质量波动会混入完成率指标；本方向未与教学能力解耦。
- 不提供后台提醒、账号系统、云服务、移动端。

## 自检

```powershell
python tests\run_tests.py
python tests\test_reliability.py -v
python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\shared\check_variant.py --variant C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-d-tempo
```

`examples/demo.md` 记录了一次离线合成运行（命令 + 输出摘要）。
