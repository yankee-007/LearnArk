# round-05 修复记录 — SkillMap v0.2.4

- **输入**：`experiments/round-05/experience-S5-P3.md`（S5 短时返学，P3 Mia，真实 LLM，20 分钟预算，5 次 say + `diagnose --skip`）
- **版本**：0.2.3 → **0.2.4**；core 1.0.2（未升级，`vendor_core.py --check` 通过）
- **范围**：只改 direction-a 自己的 `runtime/`、`mentors/`、`design.md`、`START_HERE.md`、`tests/` 与实验记录。
- **结论**：报告 3 条重要问题全部修复；20 分钟现在真的是整场预算，跳过诊断在对话层生效，恢复语不再虚报通过。

## 问题 → 修复 → 测试

| # | 报告问题 | 根因 | 修复（文件） | 测试 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | 20 分钟 = 6 分钟诊断 + 20 分钟讲解，没人算总账；没有 5–10 分钟可收口的小活动 | `estimate_minutes` 只按预算封顶，不扣诊断；诊断按固定 5 题/6 分钟；卡只说“预算 20 分钟” | 会话开始记 `plan.diagnosis_minutes`；活动 = `min(20/45, budget - 诊断 - 收尾 2)`；<30 分钟只排 2 个探针（≈3 分钟）；`Context.activity_estimate()`/`budget_breakdown()` 统一供卡、context、`status`、`next`、handoff 使用；任务卡显示“诊断 3 + 活动 15 + 收尾 2”（`sm_model`、`sm_engine`、`sm_commands`、`sm_mentors`） | `test_budget_end_to_end_arithmetic`、`test_short_budget_caps_probes_and_task` | 20 分钟：诊断 1/2、活动 15、三项相加 20；10 分钟：只剩 5 分钟单一活动；`next.budget_breakdown` 与卡/status 一致 |
| 2 | 导师说“剩下三题跳过/诊断到此结束”，运行时仍显示 2/5、下一步 Q3；`diagnose --skip` 又提示“全部按 L0” | 运行时只认“本题 skip”，没有对话级结束；`finish_diagnosis` 在 `status != done` 时直接 return，丢掉 placement | `diagnosis_end_signal()` 识别导师话术、学习者“跳过诊断”、机器块 `"diagnosis":"skip"`；`finish_diagnosis_early()` 把未答题标 `deferred`、写 `diagnosis_skipped`、保留已得等级；`finish_diagnosis` 对 skipped 也计算 placement；`diagnose --skip` 只在无当前节点时才重选，提示改为“已答对的等级与定位保留”（`sm_engine`、`sm_commands`） | `test_dialogue_skip_stops_diagnosis_and_keeps_levels`、`test_placement_survives_skip_and_levels_never_roll_back` | 第 2 题后结束：status=`skipped`、Q3–Q5 `deferred`、B1/C2 仍 L1、>下一步不含 Q3；4 题后跳过：B1 L1 且 placement 仍是 B1-apply，等级不回退 |
| 3 | 两套“下一步”；恢复语说“第 1 次提交已通过”但 plan 说未通过 | 恢复语按节点汇总所有 attempt；没区分当前阶段是否真的 passed | 恢复语改用 `runtime_next.activity_id`，只数当前活动的 attempt；只有 `stage_progress.passed` + `correct=true` 才说“已通过”，否则“已判定正确、阶段未收口”/“本阶段还没有提交记录”；卡/status/handoff 继续共用 `runtime_next`（`sm_commands`、`sm_engine`） | `test_resume_note_never_claims_unearned_pass`、`test_budget_end_to_end_arithmetic` | apply 通过后进入 check，恢复语是“本阶段还没有提交记录”，不再出现“已通过”；status/next 的活动都是 A1-check |

## 复跑命令与结果

```powershell
$env:LEARNARK_LLM = "mock"
python tests\run_tests.py                                  # 50/50
python C:\...\shared\check_variant.py --variant <本方向>    # 18/18
python C:\...\shared\vendor_core.py --check <本方向>        # core 1.0.2 match
```

## 明确未做 / 留给下一轮

- **未指定 `--minutes` 时仍按 45 分钟上限展示**，没有先问“今天几分钟”；报告问题 6 只做到“预算显式时严格”，默认值仍待产品决定。
- **诊断时长的 1.5 分钟/题是设计估计**，不是实测；真实模型下 2 题可能超过 3 分钟，预算只会更紧。
- **`diagnose --skip` 的旧探针结果仍留在 project.json**，重新 `diagnose` 会重置；没有“只补未答题”的模式。
- **20 分钟内的活动粒度**仍是一个阶段（explain 限 4 轮/8 分钟，apply 一次产物），没有更细的 5 分钟微任务库。
