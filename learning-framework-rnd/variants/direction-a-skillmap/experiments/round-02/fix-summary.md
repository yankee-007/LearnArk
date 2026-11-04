# round-02 修复记录 — SkillMap v0.2.2

- **输入**：`experiments/round-02/experience-S2-P2.md`（独立子 Agent 体验，S2 / P2 阿哲，真实 LLM，9 次 `say`）
- **版本**：0.2.1 → **0.2.2**；core 1.0.1（未升级，`vendor_core.py --check` 通过）
- **范围**：只改 direction-a 自己的 `runtime/`、`mentors/`、`design.md`、`tests/` 与文档；未改 `shared/`、其他方向、vendored core。
- **结论**：报告 5 条（4 重要 + 1 一般）全部修复，各配确定性测试；无阻塞、无回归（上一轮 28 条测试全保留，现 34 条）。

## 问题 → 修复 → 测试

| # | 报告问题 | 根因 | 修复（文件） | 测试 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | 探针错位/跳题：导师追问被当成 Q2 答案；Q2 真答案记到 Q3；D2 未答即 `done`（`correct=null`） | `apply_probe_answer` 对每个 `say` 无条件推进游标；无「追问 ≠ 作答」判定 | 游标只跟学习者对**当前题**的作答：`probe` claim 必须匹配当前锚点；导师只追问时 `probe`/`attempt.correct` 都应为 null → 记 `probe_deferred`、**题号不变并重问同一题**；错锚点记 `probe_claim_rejected` 且不推进；任何 `done` 探针必须有 true/false 判断，绝不为 null（无法解析的回合按 L0 兜底）（`runtime/sm_engine.py`、`runtime/sm_mentors.py`） | `test_probe_followup_does_not_advance`、`test_probe_claim_validation`（错锚点后游标不动、再匹配才推进）、`test_three_answers_map_to_their_own_probes`（Q1/Q2/Q3 → B1/C2/D2，Q4/Q5 仍 pending） | 追问轮不推进；错锚点不推进；三次作答各归其题；无 `done` 且 `correct=null` |
| 2 | 诊断总结与运行时计划冲突：正文说 B1 apply，任务卡说 A1 explain；总结说 C2 L1，`status` 是 L0 | 导师上下文没有运行时的权威结论 | 上下文顶部注入 `runtime_next{status,node,stage,activity_id,mentor,source,reason}`；协议加硬规则“不得宣布与 runtime_next 不同的起点/下一步”；`status --json` 也输出 `runtime_next`；`start` 任务卡与它同源（`runtime/sm_engine.py`、`runtime/sm_mentors.py`、`runtime/sm_commands.py`） | `test_runtime_next_matches_start` | 有 placement：context 与 `start` 都是 `B1-apply`、`status.runtime_next.activity_id=B1-apply`；无 placement：都是 `A1-explain`，且不出现 B1-apply |
| 3 | 帮助等级不可见；受助后下一轮答对即升 A1 L0→L1，`status` 无帮助信息 | `status` 不汇总 help；`assisted` 不跨轮约束 | `status`/`--json` 新增 `help{last_help_level,independent_attempts,assisted_attempts,assisted_completions,last_level_change{...,assisted}}`，人类输出显示“上次提示等级/独立通过/受助完成/最近等级变化（独立通过 vs 受助后）”；上一轮 `help_level≥2` 时下一轮记 `assisted_carryover`，升级理由 `after_assisted`、`level_up.assisted=true`，等级最多 L1，apply/check 当轮不通过（`runtime/sm_engine.py`、`runtime/sm_commands.py`） | `test_assisted_carryover_is_not_independent` | `level_up.reason=after_assisted`、`assisted=true`；attempt 带 `assisted_context`；`help.independent_attempts=0`；人类输出含“受助后，不计为独立” |
| 4 | 内部术语泄漏：`机器块/claim/help_level/attempt_failed/mentor_update` 出现在学习者界面 | 记录块与提示直接打印内部字段 | 学习者可见文本改为白话（“提示等级/作答/阶段通过/诊断：第 n 题已记录/受助完成/错因”）；内部术语只留在 journal 事件与 session 记录；导师协议禁止正文出现内部术语与 JSON（`runtime/sm_commands.py`、`runtime/sm_engine.py`、`runtime/sm_mentors.py`） | `test_no_internal_terms_in_stdout` | 诊断与阶段两种 `start`/`say` stdout 均不含 `机器块`、`claim`、`help_level`、`mentor_update` |
| 5 | 同一错因在 `status` 的 `weak_points`/`misconceptions` 与 handoff `unresolved` 重复 | 展示层逐条追加，未去重 | `status` 按 `(node,label)` 去重（weak/misconceptions）；handoff `unresolved` 按标签去重；`next_action` 不变（`runtime/sm_commands.py`、`runtime/sm_engine.py`） | `test_weak_points_and_handoff_dedupe` | 同一错因在 status 的两个数组各 1 条，交接文件里也只出现 1 次 |

## 复跑命令与结果

```powershell
$env:LEARNARK_LLM = "mock"
python tests\run_tests.py        # 34/34
python C:\...\shared\check_variant.py --variant <本方向>   # 18/18
python C:\...\shared\vendor_core.py --check <本方向>       # core 1.0.1 match
```

- `tests/run_tests.py`：**34/34 passed**（约 81 s，离线；新增 6 条：追问不推进、三题归位、runtime_next 一致、受助余波、术语不泄漏、错因去重；另更新 claim 校验与幂等断言）。
- `check_variant.py`：**18/18 checks ok**，退出码 0。
- `vendor_core.py --check`：**core 1.0.1: all vendored copies match**。

## 明确未做 / 留给下一轮

- **真实 API 未复测**：本轮只做离线确定性测试；`probe_deferred` 在真实模型上的触发率、`runtime_next` 对导师措辞的抑制效果需要下一次真实体验统计。
- **报告问题 6（页脚与下一轮正文各出现一次题面）**：本轮只保证“追问不推进 + 同一题重问”，页脚与导师正文仍可能各出现一次同一题；彻底去重需要让导师正文不再重复题面（已写进协议，未单独测试）。
- **报告问题 3 的“导师仍给了完整代码”**：产品无法阻止 LLM 给答案，只能把该轮记为受助完成并约束下一轮；本轮把约束从“同一轮”扩展到“下一轮”（见问题 3）。
- `issues.md` 的 I-2（L3 早授予）、I-13（定位偏高）仍开放。
