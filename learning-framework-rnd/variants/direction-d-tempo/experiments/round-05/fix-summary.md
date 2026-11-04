# Round-05 修复摘要 — direction-d-tempo v0.2.5

- 版本：`0.2.5`（vendored core `1.0.2`，schema 1）
- 来源：`experiments/round-05/experience-S5-P3.md`
- 自检：`python tests\run_tests.py` → **50/50 通过**；`shared/check_variant.py` → **18/18**；`shared/vendor_core.py --check` → core 1.0.2 一致。

## 问题 → 修复 → 测试

| # | 报告问题 | 修复 | 回归测试 |
| --- | --- | --- | --- |
| 1 | 5 分钟 recall 卡在 elapsed 0.2/5 时被导师一句“时间到”记成 `time_boxed_incomplete`，无证据、无卡；开场说“答完就算完成”，与 completion 规则矛盾 | 时间盒需真实经过 ≥60% 计划分钟，或学习者明确说“先到这里/不练了”；否则记 `time_box_ignored`，活动保持开放、正常按机器块记证据。API 开场 prompt 与本地开场都写明“判对且达到完成标准才算完成；只答一部分记 partial，活动保持开放”。 | `test_time_boxed_incomplete_and_replacement_noted`：第一段 0.2/5 → `time_boxed=False` + `time_box_ignored`；第二段 elapsed 4/5 → `time_boxed_incomplete` 且 `elapsed>=3` |
| 2 | `pause` 把未完成的 card-0001 折叠到 11-07，而 handoff/status 指向 card-0002，due 列表里也没有 folded card；下一项与新工作错位 | `fold_backlog(protected=...)` 跳过未完成当前卡与 `resume_activity.card_ids`；`pause` 把未完成活动写入 `resume_activity`，`plan_decision` 把它的 activity_id 加入 priority，下一次 `start` 先回到它；`due` 仍包含它。 | `test_unfinished_card_not_folded_and_first_next`：13 张到期 + 未完成卡 → 次日 `prepare_day` 后该卡仍 due、handoff next 与 status.next 都是它、due 列表含它 |
| 3 | 同一屏“剩余 15 / 剩余 5 / 20 分钟内能做完 / 剩余 0”互相矛盾 | 候选拒绝理由统一引用**本次入场预算**（“可用 20 分钟”），不再用循环中的剩余数；status 在 `next_session` 时 reason 以“下次：”开头，并区分“已排满 / 剩余不足（约 N 分钟）/ 时间够但模板已覆盖”；`start` 的 head 与 decision 用同一个 `entry_budget`。 | `test_remaining_minutes_one_source`：start 输出含“本次可用 20 分钟”、不含“本次放不下（剩余”；status 的 next 分钟 ≤ 剩余；cap 时 next_session 且 reason 以“下次：”开头 |

## 兼容性与状态变化

- 新增 `schedule.resume_activity`；开始该活动时记 `resume_activity_used` 并清除。
- 新增事件：`time_box_ignored`、`resume_activity_used`、`core_block_deferred`（R6）。
- `status.next.reason` 在下次模式下带“下次：”前缀；候选表不再出现“剩余 N 分钟”与 header 预算不一致。

## 未关闭 / 观察项

- 60% 判断用模拟/真实时钟的实际 elapsed；导师单方面“时间到”不再能结束活动，但学习者可以明确说停。
- `resume_activity` 只保证下一次优先；若该卡已复习/不再 due，priority 自然失效。
- 本轮未改 `shared/`、其他方向、vendored core。
