# issues.md — SkillMap 已知问题与交接给可靠性工程师

版本：0.2.4（core 1.0.2）。每条都给出严重度、观察方式与建议处理；不掩盖失败。round-01…round-06 的已修问题见
`experiments/round-01/fix-summary.md` … `round-06/fix-summary.md`。

## 阻塞

（无）

## 已修复（D-Reliability · CP2，core 仍 1.0.2）

完整矩阵与未测项见 `experiments/CP2-reliability.md`；独立套件 `tests/test_reliability.py`（24/24，修复前 19/24）。

### R-01（已修复）journal 尾行半写后追加会拼行，新事件静默丢失且整份日志随后不可读

- **原现象**：进程被杀留下半行后，`status` 能读（容忍尾行）；但下一次 `say`/`start` 把新事件直接拼在残片后面，新事件当次被当作“尾行”丢掉，再下一条命令报 `line N is not valid JSON` 并退出 3。
- **修复**：`sm_state.repair_journal_tail()` 在 `Context` 初始化与 `init_project` 第一次读写前，持 `journal.lock` 只丢弃最后一行残片（完整末行只补换行），修复说明进入 `status.repairs` / `doctor`。
- **复测**：`test_torn_journal_tail_is_repaired_before_append`、`test_missing_trailing_newline_keeps_events_and_append_is_safe`、`test_mid_journal_corruption_fails_loudly`。

### R-02（已修复）map.json 丢失时静默按模板重建，`.bak` 不被使用

- **原现象**：删除/丢失 `map.json` 后 `status` 从 L0 重新生成并写盘，等级、证据、复习日期静默清零；`map.json.bak` 就在旁边却不用。email 模板还会误用 agent-dev 的默认地图（12+6 个节点）。
- **修复**：`Project._load_map()` 在文件缺失或节点为空时优先用**同模板**的 `.bak` 恢复并持久化（写 repair 说明）；无备份才按当前模板重建并说明降级。`doctor` 的重建建议改为同时删除 `map.json` 与 `.bak`。
- **复测**：`test_missing_map_snapshot_recovers_levels_from_bak`、`test_missing_map_in_email_project_rebuilds_writing_map`、`test_truncated_map_snapshot_recovers_levels_from_bak`。

### R-03（已修复）重复 `start` 写重复会话开场

- **原现象**：同一会话连续 `start` 3 次，`session_opened` 事件被幂等键挡住，但会话 markdown 仍追加 3 个 `## 系统` 块，出现“有块无事件”。
- **修复**：`_system_turn()` 只在事件真正追加成功时写会话块；`write_switch_handoff()` 同样只在事件非空时落 handoff 文件。
- **复测**：`test_repeated_start_does_not_duplicate_session_opening`。

### R-04（已修复）`status`/`map`/`next`/`export` 保存刷新状态时不拿项目锁

- **原现象**：这些命令会因 `refresh()` 的 drift/repair 而写盘，与 `say`/`sync` 并发时可能以 `StaleWrite` 退出 3，且没有统一的并发提示。
- **修复**：`learn.py` 对所有非 `init` 命令串行化；新增 `LEARNARK_LOCK_TIMEOUT`（默认 20 秒）便于测试与 CI 获得明确冲突。
- **复测**：`test_two_processes_writing_are_serialised`、`test_held_lock_reports_conflict_exit_3`。

### C-1（core 1.0.2 缺陷，未改 core，已用 runtime 规避）

- `append_jsonl` 不保证文件以换行结尾；`read_jsonl` 又只容忍“最后一行”损坏 → 半行后追加会丢一条事件，并把日志变成永久不可读。最小复现与建议修法见 `experiments/CP2-reliability.md` §4 与 `experiments/CP2-reliability-evidence/core-bug-repro.txt`。是否升 core 版本由主负责人决定。

## 已修复（v0.2.4，round-05/06）

### I-28（已修复）20 分钟预算不是整场，诊断 6 分钟 + 讲解 20 分钟

- **原现象**：`--minutes 20` 时导师先说“5 题诊断约 6 分钟”，诊断完又给 20 分钟讲解，合计 26 分钟；没有任何 5–10 分钟可收口的小活动。
- **修复**：预算是整场。`plan.diagnosis_minutes` 在会话开始记账；活动 = `min(20/45, budget - 诊断 - 2)`；任务卡/context/`status`/`next`/handoff 显示“诊断 x + 活动 y + 收尾 2”的算式。预算 <30 分钟诊断只排 2 题（约 3 分钟），其余 `deferred`。
- **复测**：`test_budget_end_to_end_arithmetic`（20 分钟 → 2 题、15 分钟活动、算式相加 ≤20；10 分钟 → 5 分钟单一活动）、`test_short_budget_caps_probes_and_task`。

### I-29（已修复）对话里说“跳过诊断”不生效，`diagnose --skip` 还回退起点

- **原现象**：导师说“剩下三题跳过/诊断到此结束”，运行时仍显示“诊断中 2/5、下一步 Q3”；`diagnose --skip` 提示“全部按 L0 起算”，已答对的 B1/C2 L1 没有被用于定位。
- **修复**：导师正文/学习者话术/`"diagnosis": "skip"` 三种信号都会触发 `finish_diagnosis_early`：未答探针标 `deferred`、写 `diagnosis_skipped`、`end_reason` 记录来源；已获得的等级和 `compute_placement` 定位保留；`diagnose --skip` 也保留等级并只在没有当前节点时才重新选节点。
- **复测**：`test_dialogue_skip_stops_diagnosis_and_keeps_levels`、`test_placement_survives_skip_and_levels_never_roll_back`。

### I-30（已修复）两套“下一步”与“第 1 次提交已通过”假声明

- **原现象**：导师说去写 `dispatch/max_steps`，status/handoff 说继续 A1 explain；恢复语说“第 1 次提交已通过”，plan 却是未通过/未提交。
- **修复**：恢复语从 `runtime_next.activity_id` 取当前活动，只统计**当前活动**的 attempt；只有 `stage_progress.passed` 与 `correct=true` 同时成立才说“已通过”，否则说“已判定正确、阶段未收口”或“本阶段还没有提交记录”。
- **复测**：`test_resume_note_never_claims_unearned_pass`（apply 已过后进入 check，恢复语不得说 check 已通过）、`test_budget_end_to_end_arithmetic`（卡/status/next 同一活动）。

### I-31（已修复）email 探针引用了未给出的邮件正文

- **原现象**：Q2 说“下面这封 6 句邮件”但正文没给，学习者只能要求补发。
- **修复**：Q2 题面内嵌 `材料：` 6 句邮件（含结论/日期在末句）；约定“引用文本的题必须自带材料”。
- **复测**：`test_email_probes_include_their_material`。

### I-32（已修复）写作节点要“可运行文件”，正确提交被静默跳过

- **原现象**：email apply 要求可运行文件，第一版正确邮件没被计入 attempt，补交文件多花一轮。
- **修复**：email 模板的 apply 接受 `.md`/`.txt`；学习者正文即产物，运行时自动写 `artifacts/w*-apply-*.md` 并记 `artifact_autosaved`；任务卡提前写明产物路径/格式；agent-dev 仍要求真实文件，缺失时在计入 attempt 前提示。
- **复测**：`test_writing_artifact_is_autosaved_from_message`（任务卡含“产物：”，提交后自动存 .md、W2 L1→L2、stage=check）。

### I-33（已修复）email 模板写死 12 节点/5 题，check 出现 API/认证场景

- **原现象**：start 开场说“12 个节点”，README/map 行写 12 节点；check Q1 是 API/auth/集成场景。
- **修复**：README 的节点数、命令表、navigator 开场都从当前模板派生；protocol 注入“地图与诊断规模”（email 6/3）；examiner/概念/教练提示词对 email 模板加硬约束：只出英文邮件写作题，不得出现代码/API/接口/认证/联调/部署。
- **复测**：`test_email_template_counts_and_topic_are_derived`（README 含 6 节点、start/README 无 Agent/API/接口/认证/联调/代码，examiner prompt 含写作约束）。

### I-34（已修复）status 不显示本会话提示等级

- **原现象**：恢复后只能从导师话术猜本轮提示等级。
- **修复**：`status`/`--json` 的 `help.last_help_level` 取当前会话最近 `mentor_turn` 的 help_level，人类输出同时显示“上次提示等级 N”。
- **复测**：`test_status_exposes_session_help_level`。

## 已修复（v0.2.3，round-03/04）

### I-21（已修复）预算未被尊重

- **原现象**：`start --minutes 10` 仍说“今天二十分钟”、任务卡 20 分钟、`short_session_minutes=20`，10 分钟全花在 5 题诊断。
- **修复**：`estimate_minutes` 以预算封顶；`_minutes_suffix` 用真实分钟；`short_session_minutes=15`；预算 <15 分钟只做 2 题、其余 `deferred` 并写 `diagnosis_deferred`；context/status/next 都按预算。
- **复测**：`test_short_budget_caps_probes_and_task`。

### I-22（已修复）切换导师不可发现、concept 被阶段锁死

- **原现象**：apply 下 `switch concept` 被拒；`status` 不列可选导师，错误也不给替代项。
- **修复**：`status`/`start` 列“可切换导师（含一句理由）”；`concept` 在任何学习阶段按需可切（`on_demand_switch`）；拒绝时按名字列出可选值与理由。
- **复测**：`test_switch_lists_mentors_and_allows_concept_on_demand`。

### I-23（已修复）“下一位导师”三处不一致

- **原现象**：status=navigator、handoff=navigator→coach、plan 里 override 与 session_mentor 冲突。
- **修复**：`Context.next_mentor()` 作为唯一权威；status/start/handoff/plan 全部读它；`pause`/`switch` 写 `plan.next_mentor`。
- **复测**：`test_next_mentor_consistent_across_status_handoff_plan`。

### I-24（已修复）伪学习者回合与活动标签错位

- **原现象**：`start`/`switch` 以“开始学习/继续学习”写进权威会话并计入轮次；第 5 题标成 `B1-apply`、apply 修订标成 `B1-check`。
- **修复**：开场/继续/切换改为 `session_opened` + 会话 `## 系统` 块，不计轮次；回合开始时捕获 mentor/activity 用于事件与会话标题。
- **复测**：`test_openings_are_system_events_and_activity_labels`。

### I-25（已修复）克隆恢复到 check 时 examiner 仍要 apply 变式

- **原现象**：运行时阶段 check，考核导师却要求补交上一阶段变式。
- **修复**：协议规定本轮只能围绕 `{activity_id}` 出题/追问；`runtime_next` 已在上下文首部。
- **复测**：`test_clone_resume_examiner_context_has_check_activity`。

### I-26（已修复，阻塞）冲突恢复死循环

- **原现象**：`sync` 提示“手动 resolve”但 `git status` 无冲突文件；重试不断新增提交；`status` 说 clean、`doctor` 全绿。
- **修复**：采用 core 1.0.2 `GitSync.recover()`：`sync --recover` 合并 journal（union by event id + 去重索引重建），非 journal 冲突中止并列出真实文件；`sync` 先 fetch 判断分叉，不堆提交；`status`/`--json` 暴露 `diverged`/`unmerged`；`doctor` 分叉即失败；冲突退出码 3。
- **复测**：`test_sync_recover_merges_two_clones`、`test_sync_recover_snapshot_conflict_fails_with_file_list`（两克隆各追加事件 → 合并后双方事件都在且已推送；README 冲突 → 退出 3 + 文件列表 + doctor 非 0）。

### I-27（已修复）口头通过但无证据

- **原现象**：examiner 说“独立题这关过了”，`check_correct` 仍 0。
- **修复**：`claims_pass()` 检测正文通过声明（排除否定），check/review 中无 `correct=true` 时写 `mentor_verdict_conflict`，不升级、不显示“阶段通过”。
- **复测**：`test_verbal_pass_without_evidence_is_conflict`。

## 已修复（v0.2.2，round-02）

### I-16（已修复）诊断探针错位 / 追问被当成下一题

- **原现象**：导师在 Q1 后追加预测题，运行时把追问答案记成 Q2；Q2 的真答案记到 Q3（D2）；D2 未作答即 `done` 且 `correct=null`。
- **修复**：探针游标只跟学习者对**当前题**的作答；导师只追问时 `probe`/`attempt.correct` 都应为 null → `probe_deferred`、题号不变并重问；错锚点 claim → `probe_claim_rejected` 且不推进；`done` 的探针必须有 true/false 判断。
- **复测**：`test_probe_followup_does_not_advance`、`test_probe_claim_validation`、`test_three_answers_map_to_their_own_probes`。

### I-17（已修复）导师总结与运行时计划冲突

- **原现象**：同一回复里“从 B1 apply 开始”与“今日任务 A1 explain”并存；总结称 C2 L1，`status` 是 L0。
- **修复**：上下文顶部注入 `runtime_next`（唯一权威）；协议禁止宣布不同起点；`status`/`start`/`next` 同源。
- **复测**：`test_runtime_next_matches_start`（有/无 placement 两种）。

### I-18（已修复）帮助等级不可见 + 受助后立刻升级

- **原现象**：完整代码（help 3）给了之后，下一轮同构题答对即 `A1 L0→L1`，`status` 无帮助信息。
- **修复**：`status`/`--json` 新增 `help` 摘要（上次提示等级、独立/受助次数、最近等级变化是否受助）；上一轮 `help≥2` 时下一轮记 `assisted_carryover`、`level_up.reason=after_assisted`、`assisted=true`，等级最多 L1，apply/check 当轮不通过。
- **复测**：`test_assisted_carryover_is_not_independent`。

### I-19（已修复）学习者界面泄漏内部术语

- **原现象**：`机器块/claim/help_level/attempt_failed` 直接出现在学习者可见输出。
- **修复**：记录块改白话（“提示等级/作答/阶段通过/诊断：第 n 题已记录/受助完成/错因”）；内部术语只进 journal 与 session 记录；导师协议禁止正文出现内部术语与 JSON。
- **复测**：`test_no_internal_terms_in_stdout`。

### I-20（已修复）同一错因重复展示

- **原现象**：`status.weak_points`/`misconceptions` 与 handoff `unresolved` 各重复同一条。
- **修复**：按 `(node,label)` 去重（status）与按标签去重（handoff）。
- **复测**：`test_weak_points_and_handoff_dedupe`。

## 已修复（v0.1.1 / v0.2.1，保留证据）

### I-1（已修复）诊断无法改变首个活动

- **原现象**：诊断只允许把锚点置 L1，而可用门槛是 L2，于是任何档案的首个活动都是 `A1-explain`。
- **修复**：可用门槛降为 **L1**（先修 ≥L1 即可开始；掌握仍要 L2 证据），并在 `diagnosis_done` 后做
  **诊断定位**：探针置 L1 且先修全 ≥L1 的锚点直接以 `apply` 起步，写 `placement_applied`。
- **v0.2.1 补强**：评级改由导师写进机器块 `probe{node,level,reason}` 才进入地图（只接受 0/1 与声明锚点）；
  正文口头评价永不生效。
- **复测**：全对档案（5 题都判 L1）→ 锚点全 L1、`B1-apply`、`placement_applied{node:B1,level:1,probe:Q1}`；
  偏弱档案（只有 Q4→A2 答对）→ `A1-explain`（A2 的先修 A1 仍 L0）。
  证据：`tests/run_tests.py::test_placement_all_correct_profile`、`test_placement_mostly_wrong_profile`、
  `test_probe_claim_validation`。

### I-4（上游已修复）core 1.0.0 `GitSync` 的 porcelain 解析 bug

- **原现象**：`learncore/sync.py::run()` 对整段 stdout 做 `.strip()`，`git status --porcelain` 首行的前导空格
  被吃掉，`changed_paths()` 得到 `learnark/...`，第二次 `sync` 必报 `git add failed`。
- **修复**：core 1.0.1 改为只 `rstrip` 行尾；本方向已重新 vendor，删除了临时 `SafeGitSync` 子类。
- **复测**：`shared/vendor_core.py --check` 通过；`init → start → pause → sync → sync` 两次 `sync` 均退出码 0，
  第二次输出 `committed=yes`（有日志变更）且 `pushed=no`；`git status --porcelain` 解析正确。

### I-14（v0.2.1 已修）诊断题正文与页脚不一致

- **原现象**：导师正文自行另写 12 行伪代码，页脚仍是运行时的 `i += 0` 题面；Q5 同理。
- **修复**：题面唯一权威是运行时；`PROTOCOL_TEMPLATE` 每轮注入「本轮诊断题（唯一合法题面，正文照抄）」，
  `mentors/navigator.md` 与 `templates/agent-dev.md` 抄录同一组题面。
- **复测**：`tests/run_tests.py::test_probes_render_once_with_consistent_anchors`（5 题各渲染一次、锚点顺序固定）。

### I-15（v0.2.1 已修）apply 产物 basename 假阴性

- **原现象**：文件已在 `artifacts/parse_record.py`，导师报 `parse_record.py` 时被判 `artifact_missing`。
- **修复**：`Project.artifact_info` 依次尝试「项目根 / `artifacts/` / `artifacts/<basename>`」，命中后把证据路径
  规范化为项目相对路径；三者都不存在才算 `artifact_missing`。
- **复测**：`tests/run_tests.py::test_artifact_paths_accept_basename`（两种写法都通过，真缺失才报错）。

## 重要

### I-2 L3 在 check 通过时即授予，「≥7 天复测」只记录不阻塞

- **现象**：`promote(..., 3)` 在 check 通过时执行；7 天后的 review 通过会写 `retest_confirmed`，
  review 失败会降 1 级。即"L3 需要 7 天后复测"被实现为保留性复核，而不是先决条件。
- **影响**：短期内会看到 L3 早于 design §4 的字面定义。
- **建议**：若坚持字面定义，改为 L3 前需要一次 ≥7 天的 `retest_confirmed`（会影响测试与首次体验时长）。

### I-3 真实 LLM 偶尔漏机器块（v0.2.1 降低影响）

- **现象（round-01 实测）**：12 个导师回合中 9 个首轮缺 `learn-update`，补问把 API 调用推到 21 次。
- **v0.2.1 处理**：补问仍然只有 1 次，但**不再打印内部提示**（只在 journal 记 `mentor_update_retried`）；
  system prompt 末尾加硬提醒，诊断轮注入题面与 `probe` 模板，要求「先写完正文再写块」。
- **仍存在**：模型仍可能漏块；本轮未重新测真实 API 的漏块率（下一轮独立体验应统计 `mentor_update_retried` 比例）。
- **建议**：若漏块率仍高，可把机器块改成强制 JSON mode 的第二个请求，或两次补问。

### I-13 诊断定位是启发式，可能把起点放得偏高

- **现象**：探针只覆盖 B1/C2/D2/A2/E1 五个锚点；某锚点被置 L1 且先修 ≥L1 时直接从 apply 起步，
  但 L1 只证明「能复述」，apply 仍要求真实产物与 `help_level≤1`，失败会停留在 apply 而不会升级。
- **观察**：全对档案首个任务 `B1-apply`；若学习者连续两次 apply 未过，应回 drill（当前需人工 `switch` 或重新 explain）。
- **建议**：可加"apply 连续 2 次失败 → 回 drill"的自动回退（design §5 已有此意图，当前只在 check 失败时回退）。

## 一般

| id | 问题 | 观察方式 | 建议 |
| --- | --- | --- | --- |
| I-5 | 默认离线脚本 `tests/fixtures/mentor_script.jsonl` 只覆盖少数关键词；未命中时回退英文占位文本并记 `mentor_update_invalid` | `/offline` 下 `say` 任意内容 | 扩充脚本或在 START_HERE 里明确"离线只演示流程" |
| I-6 | `start` 的开场导师偶尔会自己把探针问题也问一遍，接着运行时再打印探针卡（内容重复） | 真实 API `start` 输出 | 开场 prompt 里禁止重复 question 字段 |
| I-7 | `review` 没有 `--json`，复习队列只能在人类输出里读 | `review` | 如需自动化验收再补 `--json` |
| I-8 | 复习到期只按命令执行时计算；没有后台提醒，不进入会话就不会通知 | design 已知限制 | 保持 |
| I-9 | 项目级锁只在 `learn.py` 入口获取；直接 import 模块（测试/脚本）不会串行化 | 并发压测 | 若做并发验收，请只经 CLI |
| I-10 | `map --json` 的 `today`、`status` 是读时值；跨午夜调用会变（`next --json` 同状态同一天才字节一致） | 跨日对比 | A-S6 的比较请固定 `LEARNARK_NOW` |
| I-11 | email 模板复用四阶段与同一套证据规则，但诊断只有 3 题、目标等级 W5/W6 为 2 | `--template email` | 若做跨主题验收，按写作 rubric 补测试 |
| I-12 | `doctor` 只报告 `artifact_missing`，不自动把等级退回 L1（design §4 提到退回） | 删除 artifacts 后 `doctor` | 需要时加 `doctor --fix`（当前故意不自动改等级） |

## 未验证

- 真实 GitHub 远程、跨设备、多人同时写同一项目；
- 真人学习效果、诊断精度、真实遗忘曲线（复习间隔是设计假设）；
- 10–20 小时/周 × 多周的长期状态规模（当前 journal 为线性读取）。
