# round-01 修复记录 — Forge v0.2.1

- 输入：`experiments/round-01/experience-S1-P1.md`（S1/P1 独立体验，0.1.0 + core 1.0.1）
- 版本：`direction-b-forge 0.2.1`｜vendored `learncore 1.0.1`｜state `schema_version 1`
- 范围：只修 round-01 报告中 4 个“重要”问题（#1–#4）；#5–#8 见文末“未修”。
- 回归：`python tests\run_tests.py` → **24/24 通过**；`shared/check_variant.py` → **18/18 ok**；
  `shared/vendor_core.py --check` → **core 1.0.1: all vendored copies match**。

## 问题 → 修复 → 测试

| # | 问题（报告） | 修复 | 测试 |
| --- | --- | --- | --- |
| 1 | `start --ask --answers` exit 0 但不落库；`status` 仍“未回答”；`init` 预置了学习者没给过的 `self_report` | `cmd_start`：只要给了 `--answers`/`--ask` 就写 `start_profile`（不再只在首次进入时写），并写 `start_profile_recorded` 事件；`status` 显示 `answered`。`init` 的 `learner_profile.self_report` 初始为空，新增 `init --self-report "python=…,api=…"` 只记录明说的内容（`source=learner_stated`）。 | `profile_answers`：新项目 `self_report=={}`；非交互 `answered=False`；`--ask --answers` 后 `answered=True`、三答案原样保存、`mapped_start/slice` 正确、有事件；stdin 交互 `--ask` 同样落库；`init --self-report` 只存明说项。 |
| 2 | 跟随官方 `gap learn`（help=3）后，下一次 `artifact add` 记 `assisted_level=3`，被提示“受助/代做”，与 coach 口头“不算代做”冲突 | `_artifact_assist_level()`：只统计 `mentor ∈ {coach, critic}` 的 `mentor_turn.help_level`；`guide` 微课只写缺口卡（`learn_count`/`guide_help_level`），不计入作品帮助。coach/guide/critic 提示词与生成文档同步说明。 | `guide_not_assisted`：gap learn help=3 → 新作品 `assisted_level=0`，review+defense 后 M1=`passed`/`verified`。`coach_help_counts`：同样是 gap learn 后，coach help=2 → `assisted_level=2`，通过记 `passed_assisted`/`observed`。 |
| 3 | 第二次 `say` 后 coach 让写 `m1/agent_v2.py`，同屏运行时 `next` 却是 `gap_learn explainability` | `MentorRuntime.run(..., runtime_next=…)`：把运行时 `next` 作为“本轮唯一权威动作”注入 `compact_context` 首行；`say/start/review/gap learn` 都传入；`mentor_turn` 事件与会话记录写 `runtime_next`。PROTOCOL 增加第 5 条硬规则：不得另排任务，不同意只能一句话说明后继续。coach/critic/guide 提示词同步。 | `runtime_next_authoritative`：review 失败后 `say`，`mentor_turn.payload.runtime_next.action == gap_learn`、`ref == g-M1-contract`，会话 Markdown 含 `runtime_next: gap_learn`，终端也打印权威动作。 |
| 4 | `runnability` 给 3（=阈值）但评语承认没在干净目录验证；缺证据仍算达标 | `validate_rubric`：`score >= threshold` 必须带 `evidence_line`、`evidence_path`，或 note 中的行号/段落引用；缺失时降到 `max(1, threshold-1)`，记 `rubric_unevidenced` 事件，review 写入 `unevidenced[]`（**选择降分，不整次拒绝**：既保住其他维度证据，又保证“达标”一定有据）。critic 提示词要求每个达阈值维度附证据。 | `unevidenced_lowers`：runnability 3 无证据 → 落库为 2、`unevidenced` 有记录、有 `rubric_unevidenced` 事件、生成 `g-M1-runnability`；带 `evidence_line`/`evidence_path`/note 行号的 3 分保留原分且不记 unevidenced。 |

## 复现命令（离线）

```powershell
$V = "<variant>"
python "$V\runtime\learn.py" init --goal "Agent 开发" --dir p
python "$V\runtime\learn.py" start --project p --offline --ask --answers "不确定,没有,二十分钟见到东西"
python "$V\runtime\learn.py" status --project p --json      # start_profile.answered=true
python "$V\runtime\learn.py" artifact add "$V\examples\demo-artifact-v1.py" --project p
python "$V\runtime\learn.py" review --project p --offline    # explainability 2→1，rubric_unevidenced
python "$V\runtime\learn.py" gap learn g-M1-contract --project p --offline
python "$V\runtime\learn.py" say "评审没通过" --project p --offline   # 输出 runtime_next
python "$V\runtime\learn.py" artifact add "$V\examples\demo-artifact-v2.py" --project p  # assisted_level 只含 coach/critic
```

完整离线记录见 `examples/demo.md`（0.2.1 重新跑过）。

## 真实 API 复验（deepseek-chat，3 轮）

- `start --ask --answers "不确定,没有,二十分钟见到东西"` → 输出“起点档案（已记录）”，`status` 后
  `answered=True`、答案原样保存（round-01 #1 修复生效）。
- 同一项目 `review` 真实作品后，critic 的逐维 note 带行号（如“主循环 56–74 行”）；runnability 3 达标。
- 随后 `say "我接下来做什么"`，coach 回答：“本轮唯一动作是补 contract 缺口——做 g-M1-contract 的微课学习，
  不是改代码。动作：运行 `gap learn g-M1-contract`。” 同屏运行时 `runtime_next: gap_learn（g-M1-contract）`
  （round-01 #3 修复在真实模型上生效）。
- 这轮真实评审还暴露一个新边界：note 写“无行号级证据”时，旧正则会把“行号”两字当作证据，导致
  explainability 2 分未被降级。已加否定检测（`forge_logic.has_line_evidence`：显式“无/缺/未…行号”不算证据，
  除非同时出现“第 N 行/段”），并在 `unevidenced_lowers` 里加入该反例；修复后离线测试 24/24。

## 改动文件

- `runtime/learn.py`：三问补答与事件、`--self-report`、`learner_profile` 空初始化、`runtime_next` 注入与记录、
  `_artifact_assist_level`、`validate_rubric` 四元返回、`rubric_unevidenced` 事件、status 显示 `answered`/自述。
- `runtime/forge_mentor.py`：PROTOCOL/REVIEW/GUIDE/COACH 提示、`runtime_next` 参数与上下文、
  `validate_rubric` 证据校验与降分、review 提示词。
- `runtime/forge_logic.py`：`has_line_evidence()` 公开；`needs_extra_gap` 复用它。
- `runtime/forge_state.py`：会话记录渲染 `runtime_next`；版本 0.2.1。
- `mentors/{coach,critic,guide}.md`：权威动作、微课不计作品帮助、证据要求。
- `tests/run_tests.py`：新增 5 个用例（含交互 stdin）。
- `tests/fixtures/mentor_script.jsonl`：review #1 的 runnability note 补行号（保留 explainability 无证据以演示降分）。
- `START_HERE.md`、`version-manifest.json`（0.2.1）、`examples/demo.md`、本文件。

## 未修（round-01 #5–#8，非本轮要求）

- #5 作品计数：复核 `commands-S1.log` 后确认 #13 在第二次登记前、#17/#21 在其后，属时间点差异，未改代码。
- #6 副本路径 vs 工作文件：仍按“副本是登记产物、源文件是学习者的”设计；计划在 M1 文案里明确“改源文件再 add”，本轮未改。
- #7 `mentor_thrash` 被系统强制切换触发：仍会把 forced 切换计入会话切换次数；建议下轮改为只统计非 forced 的用户切换。
- #8 `pause` 后 `start` 自动多发一轮“继续学习”：仍会消耗一次 LLM 往返；建议下轮改为“有 handoff 且会话刚结束时只展示状态、不自动调用”。
