# Round-01 修复摘要 — direction-d-tempo v0.2.1

- 版本：`0.2.1`（vendored core `1.0.1`，schema 1）
- 来源：`experiments/round-01/experience-S1-P1.md`（独立体验者 S1/P1，2026-11-04）
- 修复原则：只改本方向；不改 `shared/`、其他方向、vendored core；每个确认问题都有回归测试。
- 自检：`python tests\run_tests.py` → **33/33 通过**；`shared/check_variant.py` → **18/18**；`shared/vendor_core.py --check` → 一致。

## 问题 → 修复 → 测试

| # | 报告问题 | 修复 | 回归测试 |
| --- | --- | --- | --- |
| 1 | 同日第二次 `start`（无分钟数）把预算从 30 静默改回默认 20；`status` 既说 2/2 完成又推荐 15 分钟下一步；没有“今天还剩多少” | 当天无新分钟数时**沿用今日预算**并回显（`budget_carried` 事件）；本次声明的分钟数按“已用 + 本次”累计；`status` 与调度理由显示 `预算 / 已用 / 剩余`；`items_started`、`items_done`、`cap_reached` 分开，下一步在排满/预算不足时标“下次”；`start` 排满或剩余 <5 分钟时只收尾、不追加时间 | `test_budget_same_day_carry_and_remaining`（30 → 说完/复习后 30 不变；剩余 15；`next.when="next_session"`；人类输出含“剩余 15 分钟/下一步（下次）”） |
| 2 | 6 轮里 4 轮缺机器块；运行时把“导师漏了机器块/重试”等内部术语直接给学习者看；33% 额外调用 | 补问**静默化**（仅 `mentor_update_retried` + usage，不打印）；最多一次；强化 system/context 末尾的机器块提醒；学习档案里改成人话（“这一轮没有形成可记录的证据”）；隐藏别名/回填/信号/冲突等内部 note；离线未匹配时给中文说明而非英文 fallback | `test_missing_block_repaired_silently`（首条无块、静默补一次后记 attempt；stdout 不含“机器块/重试/mentor_update/补一次/learn-update”）；`test_update_validation` 保持非法块无证据 |
| 3 | 活动声明完成需 `artifacts/eval-cases.json`，首答即 `activity_completed`（`artifact:""`），随后导师继续追问；学习者后来真写了文件却无回执 | `code_kata`/`transfer_task` 的本周块步骤声明 `required_artifact`；文件不存在 → 记 `artifact_required`、活动保持未完成、`status` 显示“待确认产物”；文件后来落盘 → `say`/`start`/`pause` 记 `artifact_acknowledged` 并完成，handoff 写产物；非产物步骤不再提及产物 | `test_artifact_required_blocks_completion_and_acknowledges_later`（缺文件时 `activity_completed==0`；写文件后 `pause` 回执、`artifact_acknowledged`、handoff 含路径） |
| 4 | `init` 替学习者编造“调过 API、借 AI 做过 RAG”的自述 | 新项目 `learner.self_report=[]`、`note` 明确“尚未记录”；只有 `init --self-report "原话"` 或之后明确说的才记录，并标注“未经证据校准” | `test_init_does_not_invent_self_report`（默认无 RAG/API 字样；`--self-report` 后原文入库） |
| 5 | `.learnark/usage.jsonl` 未忽略，`doctor` 却报“工作区干净” | `.gitignore` 增加 `.learnark/usage.jsonl`、`sync-log.jsonl`（锁/tmp 已有）；`doctor`/`status` 的 git 快照把“被同步策略跳过但未忽略”的文件计入真实改动，并新增 `git_policy` 检查 | `test_gitignore_covers_usage_and_doctor_reports_true_state`（忽略生效后干净；放入未忽略文件后报 `个改动未提交` + `git_policy`，`sync.clean=false`） |
| 6 | CLI 说 `deepseek-chat`，`usage.jsonl` 实际 `deepseek-flash` | 记录每次调用实际返回的模型（`meta.last_model`）；`start`/`say` 在真实 API 下打印“实际返回 X（配置 Y）”；`status` 显示配置/上次实际 | `test_model_label_records_actual_model`（离线 last=mock；人类 status 不出现 deepseek-chat）；真实 API 手测见下 |
| 7 | 两次活动间导师 trainer→coach，未解释 | 按活动类型绑定导师保持不变；跨活动变化时 `start` 打一行“trainer → coach：按活动类型绑定导师（本次是概念块），不是随机切换”；首次进入不误报；`START_HERE` 增加“导师与活动绑定”段落 | `test_mentor_switch_between_activities_is_announced`（首活动 trainer；第二活动含 `trainer → coach` 与“按活动类型绑定”） |

## 兼容性与行为变化

- `schedule.today` 新增 `minutes_used` / `budget_source`；旧快照读取时自动补 0/default，不需要迁移脚本。
- 预算语义：本次声明的分钟数视为“这一次可用的时间”，日预算 = 已用 + 本次；同日无参数 `start` 沿用日预算。
- `status --json` 新增 `model`、`today.minutes_used/remaining_minutes/cap_reached`、`next.when`、`pending_artifact`；旧字段保留（`minutes_left` 仍等于剩余）。
- `say` 的机器块缺失输出改为“这一轮没有形成可记录的证据”，不再暴露协议术语；离线 fallback 改为中文说明。
- 活动产物只在本周块的 `code_kata`/`transfer_task` 步骤声明；概念/回忆/小测步骤不要求文件，避免误伤。
- `artifact` 路径必须在磁盘上存在才记为块产物（L3 依据）；不存在只记 `artifact_missing_file`。

## 真实 API 手测（2026-11-04）

```text
[预算] 今日 20 分钟 · 已用 0 · 剩余 20（--minutes）
本次导师：trainer · 高频练习导师
[模型] 实际返回：deepseek-flash（配置：deepseek-chat）
（say）提示级别 0（独立完成） · 本题判对 · 证据：观察记录
      agent-loop L0→L1；card-0001 记 good；活动完成：是
     实际模型：deepseek-flash（配置：deepseek-chat）
status.model = {"configured": "deepseek-chat", "last": "deepseek-flash"}
```

## 未关闭 / 观察项

- 真实导师仍可能连续两次不写机器块（本轮靠静默补问；两次都缺则无证据，不推测）。
- 报告 #8（到期卡 12→11→13→12）与 #10（30 分钟无代码）不在本轮确认修复范围；#9 的内部术语已收敛（别名/回填/信号不再显示），候选表仍保留 Tier/分数用于可解释性。
- `pushed` 仍只在本地裸仓库验证（`test_two_syncs_commit_modified_tracked_file`），未接真实 GitHub/跨设备。
- 旧项目里已写入的 `learner.note` 不自动改写（避免删除可能是真人说过的话）；新项目默认空自述。
