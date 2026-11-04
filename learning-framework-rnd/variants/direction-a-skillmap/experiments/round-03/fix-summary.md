# round-03 修复记录 — SkillMap v0.2.3

- **输入**：`experiments/round-03/experience-S3-P3.md`（独立子 Agent 体验，S3 / P3 Mia，真实 LLM，8 次 `say`）
- **版本**：0.2.2 → **0.2.3**；core 1.0.2（重新 vendor，`vendor_core.py --check` 通过）
- **范围**：只改 direction-a 自己的 `runtime/`、`mentors/`、`design.md`、`tests/` 与文档；未改 `shared/`、其他方向、vendored core。
- **结论**：报告中的 4 条重要/一般问题（预算、切换、导师一致性、伪回合）全部修复，各配确定性测试。

## 问题 → 修复 → 测试

| # | 报告问题 | 根因 | 修复（文件） | 测试 | 结果 |
| --- | --- | --- | --- | --- | --- |
| A | `--minutes 10` 仍输出“今天二十分钟”、任务卡 20 分钟、`constraints.short_session_minutes=20`，10 分钟全被 5 题诊断吃掉 | `_minutes_suffix` 硬编码“二十分钟”；`estimate_minutes` 只返回 20/45；诊断固定 5 题 | `estimate_minutes` 以预算封顶（10→10）；`_minutes_suffix` 用真实分钟；`constraints.short_session_minutes=15` + `short_diagnosis_probes=2`；预算 <15 分钟时 `ensure_probes` 只保留 2 题、其余标 `deferred` 并写 `diagnosis_deferred`；探针页脚显示 `n/2` 与延后提示；mentor context 注明短预算与单任务分钟（`sm_model`、`sm_engine`、`sm_commands`、`sm_mentors`、`sm_state`） | `test_short_budget_caps_probes_and_task` | 10 分钟：输出“10 分钟”、`诊断探针 1/2`、只做 2 题、`diagnosis_deferred` 含 Q3–Q5、`next/status/status.next_action` 均为 10 分钟、context 含“2 个诊断探针”；不再出现“二十分钟” |
| B | apply 阶段 `switch concept` 被拒；可用导师只能从报错得知，`status` 不列 | `allowed_mentors` 只用阶段默认集；`status`/卡片不显示目录 | `user_allowed` = 阶段默认 + `concept`（按需，任何学习阶段）；`mentor()` 接受按需 override；`switch` 成功时写 `on_demand_switch`；`MENTOR_REASONS` 生成一行说明；`status` 人类/JSON 与 `start` 任务卡都列“可切换导师（含理由）”；错误按名字列出全部可选项（`sm_model`、`sm_engine`、`sm_commands`） | `test_switch_lists_mentors_and_allows_concept_on_demand` | apply 下 `switch concept` 退出 0、有 `on_demand_switch`、`status.mentors.current=concept`；拒绝 examiner 时错误里同时出现 navigator/coach/concept；status 含“可切换”与“概念导师” |
| C | “下一位导师”三处不一致：status=navigator、handoff=navigator→coach、plan 里 override=navigator 而 session_mentor=coach | handoff 用 `next_decision` 选导师、status 用 `mentor()`、plan 只记会话创建者 | 新增 `Context.next_mentor()` 作为**唯一权威**：诊断→navigator；有当前节点→当前阶段导师（含 override）；否则看 `next` 选中项。`status`/`start`/`handoff`/`plan.next_mentor` 全部读它；`pause`/`switch` 写 `plan.next_mentor`（`sm_engine`、`sm_commands`、`sm_model`） | `test_next_mentor_consistent_across_status_handoff_plan` | explain 切 navigator → pause：handoff `from/to` 都是 navigator，`status.plan.next_mentor`、`plan.next_mentor`、第三次 `start` 后的 `session_mentor` 全部一致 |
| D | `start`/`switch` 被写成“学习者发言”，交接轮次虚高（11 vs 实际），第 5 题标成 `B1-apply`、apply 修订标成 `B1-check` | `_start_turn` 复用 `mentor_turn` + `append_session_turn(learner_text=...)`；`_record_turn_event` 在状态推进后读 `ctx.activity_id()` | 开场/继续/切换改为 `session_opened` 事件 + 会话 `## 系统` 块，不计 `turn_index`、不计 handoff 轮次；`process_turn`/`cmd_say` 在回合开始时捕获 `mentor`/`activity` 并用于事件与会话标题（`sm_engine`、`sm_commands`、`sm_state`） | `test_openings_are_system_events_and_activity_labels` | 5 次 say 只有 5 条 `mentor_turn`（全为 `diagnose`），会话无“开始学习/继续学习”，`## 学习者` 恰好 5 条；完成诊断的第 5 轮仍标 `diagnose`（placement 后 plan=B1）；apply 通过轮标 `A1-apply`（plan 已到 check）；pause 交接“本会话 1 轮对话” |

## 复跑命令与结果

```powershell
$env:LEARNARK_LLM = "mock"
python tests\run_tests.py        # 42/42
python C:\...\shared\check_variant.py --variant <本方向>   # 18/18
python C:\...\shared\vendor_core.py --check <本方向>       # core 1.0.2 match
```

- `tests/run_tests.py`：新增 4 条（预算、按需切换、导师一致性、系统事件与活动标签）。
- `check_variant.py`：18/18，退出码 0。
- `vendor_core.py --check`：core 1.0.2: all vendored copies match。

## 明确未做 / 留给下一轮

- **报告问题 2（10 分钟被诊断占满）**：本轮把诊断压到 2 题并延后其余，但没有为“跳过诊断的 10 分钟会话”设计更快路径；`diagnose --skip` 后仍从 A1 explain 起。
- **报告问题 6（会话归属）**：切换后的导师回合仍写在同一会话文件里；文件标题按会话创建者，未按每轮导师拆文件。
- **报告问题 7（独立通过 0 次 vs 最近等级变化“独立通过”）**：诊断带来的 L1 不计为独立尝试，但 `last_level_change` 仍显示诊断的等级变化来源；下轮可把 `source=diagnosis` 单独标注。
- 报告问题 8/9（恢复措辞、诊断收尾不给题面）未改。
