# 离线合成演示（examples/demo.md）

> **性质：离线 / 合成**。导师是 `tests/fixtures/mentor_script.jsonl` 的脚本导师（`[离线脚本导师]`），时钟是模拟时间
> `LEARNARK_NOW=2026-11-04T19:00:00+08:00`。这里只证明“预算 → 调度 → 证据 → 到期 → 交接 → 同步”的流程与规则，
> **不证明真实教学质量，也不证明真人记忆保持**。下文代码块都是真实运行的输出节选（`…` 表示省略行）。
>
> 环境：Windows 11 · Python 3.14.6 · git 2.55.0 · direction-d-tempo 0.2.5 · learncore 1.0.2。
> 项目目录在演示时是临时目录 `$DEMO\proj`（下称 `proj`）。

## 1. 初始化的真实输出

```powershell
$env:LEARNARK_LLM='mock'
$env:LEARNARK_NOW='2026-11-04T19:00:00+08:00'
python runtime\learn.py init --goal "能独立设计、实现并评测一个可用的 Agent 应用" --dir proj
```

```
已创建 Tempo 项目：$DEMO\proj
目标    能独立设计、实现并评测一个可用的 Agent 应用
模板    agent-dev
导师    coach, trainer, examiner
技能    10 个
卡片    12 张（今天到期）
每周预算  600 分钟
每次默认  20 分钟
git: git init、.gitignore、.gitattributes
[时间] 模拟时钟 2026-11-04T19:00:00+08:00（仅证明调度逻辑，不证明真实记忆保持）；种子卡的 due_at 由该时钟写入
git: 已提交 b07293f（本地）
下一步：python learn.py start --minutes 20   （或 start "今天只有二十分钟"）
```

学习者档案初始为空：`learner.self_report=[]`，`note` 写“尚未记录学习者自述”；`init` 不会替学习者编写经历，
只接受 `--self-report "原话"`（见第 9 节）。

## 2. `start --minutes 5`：预算小就只清到期

```powershell
python runtime\learn.py start --minutes 5 --project proj --offline
```

```
[时间] 模拟时钟 2026-11-04T19:00:00+08:00（仅证明调度逻辑，不证明真实记忆保持）
[诊断] 首次进入：先用到期卡自测校准等级；自述（“我学过”）不计等级，只看行为证据。
[预算] 本次 5 分钟 · 已用 0 · 剩余 5（今日累计 5）
候选（按两级选择 + 组内打分，输入只有 state + 预算 + 时钟）：
#  活动                技能             时长  层级  总分     主因子  状态/理由
1  recall-card-0001  agent-loop     5m  T1  0.550  薄弱度  选中：本次活动
2  recall-card-0002  agent-loop     5m  T1  0.550  薄弱度  备选：可做但未入选（分数较低）
3  recall-card-0003  tool-contract  5m  T1  0.550  薄弱度  备选：可做但未入选（分数较低）
为什么是它：到期组：该卡逾期 0 天，先清到期；选 5 分钟的到期卡（recall），预算 5 分钟内能完整做完；
未入选：block-2026-W45-step1-eval-harness（tier 2 未进入：到期组非空）；…
本次可用 5 分钟；活动上限 20 分钟。
[离线脚本导师] 活动：记忆卡（recall-card-0001）· 5 分钟 · 技能 agent-loop（L0）
开始之前不要看卡背。第一张：Agent 循环的四个阶段是什么？
```

观察：Tier 1 到期组非空 → Tier 2 的块步骤明确写“tier 2 未进入”，没有被新内容挤掉。

## 3. 两轮 `say`：证据与卡片等级

```powershell
python runtime\learn.py say "五分钟" --project proj --offline
python runtime\learn.py say "连续两次没有新信息" --project proj --offline
```

第一轮（错误尝试，不计升级）：

```
[预算] 已记录 5 分钟（原句包含“五分钟”）；今日预算 10，已用 5，剩 5
[时间] 模拟时钟 2026-11-04T19:00:00+08:00（仅证明调度逻辑，不证明真实记忆保持）
[离线脚本导师] 五分钟只清到期卡，不铺新内容：…
—— 本轮记录 ——
提示级别 0（独立完成） · 本题未判对 · 证据：观察记录
- 下一步建议（不排课）：先答两张到期卡（建议，不排课）
- 活动完成：否（仍在进行中）
```

第二轮（独立答对 → 只升 1 级 + 卡片按 SRS 排期）：

```
[离线脚本导师] 三条都中，这张记 good，间隔推到 2 天，不用看卡背。…
—— 本轮记录 ——
提示级别 0（独立完成） · 本题判对 · 证据：观察记录
- agent-loop L0→L1（正确 + help_level≤1；每天最多 +1）
- card-0002 记 good：step 0→1，间隔 2 天（2026-11-06 到期）
- 下一步建议（不排课）：下一张 card-0003（建议）
- 活动完成：是
```

观察：导师的 `skill_signal`/活动别名只写进 journal，不再显示给学习者；等级由运行时按证据规则计算。

## 4. `start --minutes 20`：预算变大后换活动

```powershell
python runtime\learn.py start --minutes 20 --project proj --offline
```

```
上次停在哪：recall_card · agent-loop（2026-11-04 19:00）
[预算] 本次 20 分钟 · 已用 5 · 剩余 20（今日累计 25）
本次导师：coach · 概念与回述导师   会话：20261104-190000-coach
[导师] trainer → coach：按活动类型绑定导师（本次是概念块），不是随机切换。
#  活动                                 技能            时长   层级  总分     主因子  状态/理由
1  block-2026-W45-step1-eval-harness  eval-harness  10m  T2  0.500  薄弱度  选中：本次活动
2  block-2026-W45-step3-guardrails    guardrails    15m  T2  0.475  薄弱度  排除：15 分钟活动超出剩余 10 分钟
3  block-2026-W45-step2-eval-harness  eval-harness  8m   T2  0.405  薄弱度  排除：同一技能当天已练过
为什么是它：到期组已清空，进入本周块步骤；…
本次可用 20 分钟；活动上限 20 分钟。
```

观察：同一天第二次进入因“同日不重复活动模板 + 同日不重复技能”硬过滤，到期卡不再可选，进入 Tier 2 本周块；
第二个候选因为超出剩余 10 分钟被排除。导师变化会明确说明是“按活动类型绑定”，不是随机替换。

## 5. `due` / `plan` / `skills`

```powershell
python runtime\learn.py due --project proj --offline
```

```
今天到期（2026-11-04，模拟时间）：
类型  id         技能/标题          内容                          到期          逾期   状态
卡   card-0001  agent-loop     Agent 循环的四个阶段是什么？      2026-11-04  0 天  step 0
卡   card-0003  tool-contract  工具 schema 至少要写清哪三类信息？   2026-11-04  0 天  step 0
…（共 11 张，每会话最多清 3 张；积压上限 12 张，超出折叠 +3 天）
```

```powershell
python runtime\learn.py plan --project proj --offline
```

```
下次建议（具体可用 20 分钟，最多 3 项；只给今天，不显示欠账总数）——今日已排 2/2 项、剩 10 分钟
#  活动             技能             时长     分数     主因子  理由
1  recall_card    tool-contract  5 分钟   0.225  薄弱度  下次第一项
2  transfer_task  guardrails     15 分钟  0.475  薄弱度  计划内的下一项

今天已排满或预算不足：以上是下次进入后的建议，不是今天的欠账。
```

`plan` 不再把“候选为空”的回落项伪装成真实建议；今天排满时给出的是**具体卡片/活动**，并明确标为“下次”。

```powershell
python runtime\learn.py skills --project proj --offline
```

```
技能             等级  证据           到期  逾期   lapses  错误标签  块产物
agent-loop     L1  observed     -   0 天  0       -     -
tool-contract  L0  self_report  -   0 天  0       -     -
…（平表，无 prereq / 无层级列）
卡片：12 张 · 到期 11 张 · leech 0 张 · 待改写 0 张
L3 规则：只能由“块产物 + ≥7 天延迟复测”授予；纯卡练习最高 L2。
```

## 6. `status --json`（节选）与人类可读状态

```powershell
python runtime\learn.py status --json --project proj --offline
```

```json
{
  "variant": "direction-d-tempo",
  "version": "0.2.5",
  "core_version": "1.0.2",
  "schema_version": 1,
  "learner": {
    "name": "学习者",
    "self_report": [],
    "note": "尚未记录学习者自述；只按行为证据校准（可随时用 init --self-report 补充原话）"
  },
  "offline": true,
  "simulated": true,
  "model": {"configured": "mock", "last": "mock"},
  "today": {
    "date": "2026-11-04", "minutes_budget": 25, "minutes_used": 15,
    "remaining_minutes": 10, "budget_source": "flag",
    "items_started": 2, "items_done": 1, "max_items": 2, "cap_reached": true
  },
  "due": {"cards": 11, "skills": 0, "max_overdue_days": 0},
  "last_turn": {
    "activity_id": "recall-card-0001", "skill": "agent-loop", "help_level": 0,
    "correct": true, "attempt_kind": "answer", "evidence_kind": "independent",
    "assisted": false, "echoed": false, "text_conflict": false, "time_boxed": false
  },
  "unfinished": [
    {"activity_id": "block-2026-W45-step1-eval-harness", "activity_type": "concept_block", "skill": "eval-harness", "minutes": 10}
  ],
  "next": {
    "activity_id": "recall-card-0003", "activity_type": "recall_card", "skill": "tool-contract",
    "minutes": 5, "tier": 1, "when": "next_session",
    "reason": "到期组：该卡逾期 0 天，先清到期；选 5 分钟的到期卡（recall），预算 20 分钟内能完整做完；…"
  },
  "pending_artifact": null,
  "sync": {"state": "written", "written": true, "committed": false, "pushed": false, "remote": ""},
  "journal": {"events": 22}
}
```

人类可读的 `status` 同屏给出：`预算 25 分钟（累计）· 已用 15 · 剩余 10`、`已排 2/2 项（完成 1 项）`、
`上次帮助：提示级别 0（独立完成） · 判对 · 证据类型 independent`、`未完成：concept_block · eval-harness（10 分钟）`，
下一步是具体的 `recall_card · tool-contract（5 分钟，Tier 1；recall-card-0003）`，不会出现 `recall_card · -` 占位符。
技能表新增“上次帮助”列；`status --json` 的 `skills[].last_help_level/last_evidence_kind` 可复核每轮帮助程度。

## 7. `pause` / `sync` / `doctor` / `export`

```powershell
python runtime\learn.py pause --note "demo" --project proj --offline
```

```
# 交接 · 2026-11-04 19:00
- 原因：pause（demo）
- 导师：coach
- 上次停在哪：concept_block · eval-harness（2026-11-04 19:00）
- 试过什么：今天已排 2 项，预算 25 分钟（已用 15，剩 10）；到期卡 11 张（最久逾期 0 天）
- 哪里不稳：暂无记录
- 产物：无
- 未完成：concept_block · eval-harness（10 分钟）
- 下一步：recall_card · tool-contract（5 分钟，下次；recall-card-0003）
- 未决问题：无

git state: no-remote (written=yes, committed=yes, pushed=no)
  提交文件：9 个（样例：.learnark/journal/dedupe.json, .learnark/journal/events.jsonl, …）
  remote: 无（无远程，真实 GitHub 同步未验证；本地记录已保存）
下次开始：recall_card · tool-contract（5 分钟，下次；recall-card-0003）
```

```powershell
python runtime\learn.py sync --project proj --offline
# git state: clean (written=yes, committed=no, pushed=no)   ← pause 已提交，本次无需再提交

python runtime\learn.py doctor --project proj --offline
```

```
[ok  ] project / state / schema / journal（24 条事件，seq 单调、id 唯一）
[ok  ] dedupe_index（24 个幂等键与日志一致） / interrupted_writes / locks
[ok  ] snapshot_journal: 快照中的卡片与 journal 一致
[ok  ] git_divergence: 本地与远程未分叉
[ok  ] git: 工作区干净；分支 master；远程 无（pushed 未验证）
[ok  ] git_policy: 没有“未忽略但被跳过”的文件
[ok  ] llm（离线脚本导师）/ clock_skew / core_version（1.0.2 与 pin 一致）/ session_file
结论：15 项正常，0 项警告，0 项问题。
注意：当前为模拟时钟（LEARNARK_NOW），只证明调度逻辑，不证明真实时间下的记忆保持。
```

`.gitignore` 已排除 usage/sync-log/锁/.tmp，`.gitattributes` 固定 `* -text`；
若有人放入未忽略的杂项文件，`doctor` 会报 `git_policy`，不会假报干净。分叉时 `doctor` 报 `git_divergence` 并退出 3。

```powershell
python runtime\learn.py export --out $DEMO\export.md --project proj --offline
# 已导出学习档案：$DEMO\export.md（8256 字节）；不含 API 密钥
```

## 8. 这次运行写下了什么（journal 权威记录）

```
events: 24
project_initialized: 1   budget_set: 3   session_opened: 2   mentor_opening: 2
schedule_decision: 2     turn: 2          mentor_activity_alias: 2
mentor_suggestion: 2     attempt: 2       level_change: 1     card_reviewed: 1
skill_signal: 1          activity_completed: 1   handoff: 1    pause: 1
simulated: 全部事件为 true
```

- `schedule_decision` 保存了每个候选的 tier/score/factors/status/reason（可回溯“为什么选它”）。
- `attempt` / `level_change` / `card_reviewed` 都带幂等键；同一条 `say` 重放只输出“重复执行”，不重复计数。
- 导师把活动叫成 `recall-due-2cards` 时，运行时记 `mentor_activity_alias`，仍按已调度的 `recall-card-0001` 记证据；
  真正换活动/改计划会记 `mentor_schedule_conflict`（见 `tests/run_tests.py::test_mentor_cannot_change_schedule`）。

## 9. 本轮（0.2.5）新增行为的现场证据

- **实质作答不再误判提问**：短且无作答内容的请求才算提问；陈述句里的“直接给最终答案”不算。partial 只来自机器块 `result=partial` 或学习者明确自评，导师文字里的“部分/漏了”不再降级正确回答；明确冲突记 `mentor_text_conflict`，两者都不产生证据/卡片。
- **核心写作块先排**：email 模板 20 分钟时先排 12 分钟 `writing_block`；预算不足记 `core_block_deferred`，下次先做它（`test_email_core_writing_block_is_not_starved`）。
- **时间盒/折叠**：导师单方面“时间到”但未过 60% 记 `time_box_ignored`、活动保持开放；未完成卡不被积压折叠，`resume_activity` 让下次先回到它（`test_time_boxed_incomplete_and_replacement_noted`、`test_unfinished_card_not_folded_and_first_next`）。
- **回答里的分钟数不改预算**：`say` 只记 `budget_ignored_in_answer`；预算只由 `start`/`--minutes` 决定（`test_say_answer_with_minutes_does_not_change_budget`）。
- **显式 switch 生效**：`switch examiner` 后下一次 `start` 的 session.mentor=examiner（必要时换 examiner 能带的小测/回忆），用掉后清空，`status.mentor_override` 可查。
- **交接/下一步一致**：handoff 会抓导师最后追问；`status` 的可行决策缓存给下一次 `start` 复用（`next.decision_id`），5 分钟够 5 分钟活动时不再说预算不足。
- **复述不算独立**：回答与导师例子高度重合（bigram 覆盖率 ≥72%）时记 `echoed_example`、帮助等级抬到 ≥2、不升级、卡片按 hard 排期；`status.last_turn.echoed` 可查。回归测试 `test_echo_is_not_independent_correct`。
- **提问不算作答**：纯提问/求助记 `turn_without_attempt`、`correct=null`，不升级、不建卡。回归测试 `test_pure_question_turn_is_not_an_attempt`。
- **一轮一个判定**：导师文字“对”与机器块 `correct=false` 冲突时记 `mentor_text_conflict`，以机器块为准，只输出一个结论。回归测试 `test_text_conflict_uses_block_and_is_logged`。
- **重复卡片合并**：同 skill + 归一化 front 只保留一张卡并记 `card_merged`；自动误解卡不再产生三张同题卡。回归测试 `test_duplicate_card_fronts_merge`。
- **下一步唯一**：`status`/`plan` 给出具体 `recall-card-0003`（skill tool-contract），不再出现 `recall_card · -`；导师 `next` 只标“导师建议（不排课）”。回归测试 `test_budget_same_day_carry_and_remaining` 的 next/plan 断言。
- **积压折叠不静默**：`[调整] 今天到期的卡超过 12 张：最旧的 N 张已顺延 3 天…`；`backlog_folded` 事件可查。回归测试 `test_backlog_fold_and_session_cap`。
- **时间到未完成**：实际 elapsed ≥60% 或学习者明确说停才记 `time_boxed_incomplete`；否则 `time_box_ignored`、活动保持开放。回归测试 `test_time_boxed_incomplete_and_replacement_noted` 覆盖两分支。
- **帮助程度可见**：`status` 有“上次帮助/证据类型”和技能“上次帮助”列；`status --json.last_turn`、`skills[].last_help_level/last_evidence_kind` 可复核。
- 0.2.1 的预算/静默修复/产物门控/自述/doctor/模型/导师切换回归仍全部保留（38 项测试全绿）。

## 10. 这个演示**没有**证明什么

- 脚本导师的教学质量（文本是 fixture，且活动命名是别名）；真实 LLM 回合见 `experiments/round-01/fix-summary.md` 与 `experiments/round-02/fix-summary.md` 的手测记录。
- 真实时间下的记忆保持：SRS 断言全部是 `LEARNARK_NOW` 模拟时间（见 `tests/run_tests.py` 的 0/1/3/7/15/30 天用例）。
- 跨设备/GitHub：本演示没有远程，`pushed=no` 是如实状态；两次 sync 的回归用本地裸仓库验证。
- L3：本演示没有块产物，因此没有任何技能到 L2 以上；L3 的“块产物 + ≥7 天延迟复测”由单元测试覆盖。
