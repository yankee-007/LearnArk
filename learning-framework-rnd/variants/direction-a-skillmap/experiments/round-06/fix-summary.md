# round-06 修复记录 — SkillMap v0.2.4

- **输入**：`experiments/round-06/experience-S6-P4.md`（S6 跨主题迁移，P4 Tina，email 模板，真实 LLM，8 次 say）
- **版本**：0.2.3 → **0.2.4**；core 1.0.2（未升级，`vendor_core.py --check` 通过）
- **范围**：只改 direction-a 自己的 `runtime/`、`mentors/`、`design.md`、`START_HERE.md`、`tests/` 与实验记录。
- **结论**：4 条问题全部修复；email 探针自带材料、写作产物自动归档、模板计数/题目不再串到 Agent 主题。

## 问题 → 修复 → 测试

| # | 报告问题 | 根因 | 修复（文件） | 测试 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 4 | Q2 说“下面这封 6 句邮件”，正文没给，学习者为“邮件没看到”多花一轮 | 探针题面只写引用、不带材料 | email Q2 题面内嵌 `材料：` 6 句邮件（含末句结论/日期）；约定引用文本的题必须自带材料；agent-dev 的 Q2 伪代码本来就内嵌（`sm_model`） | `test_email_probes_include_their_material` | Q2 含“材料：”和 `November 12`；所有“下面/以下/材料”类探针都自带材料 |
| 5 | apply 要求“可运行文件”，第一版正确邮件没被计入 attempt，补交文件多花一轮 | 产物规则只认文件；写作节点没有自动归档；卡不提前写产物要求 | email 模板 apply 接受 `.md`/`.txt`；学习者正文即产物，`Project.autosave_artifact()` 自动写 `artifacts/w*-apply-<时间>.md` 并记 `artifact_autosaved`；任务卡提前写“产物：…（接受 .md/.txt）”；agent-dev 仍要求真实文件，缺失时在计入 attempt 前提示（`sm_state`、`sm_engine`、`sm_commands`） | `test_writing_artifact_is_autosaved_from_message` | apply 前卡片含“产物：…md”；提交全文后自动生成 `w2-apply-*.md`、W2 L1→L2、stage=check、有 `artifact_autosaved` |
| 6 | email 模板仍说“12 个节点/5 题”，check Q1 是 API/auth/联调场景 | README 命令表、navigator 开场写死 12/5；examiner 提示词含编程迁移题；protocol 不注入模板规模 | README 节点数/命令表从模板派生；protocol 注入“地图与诊断规模：6 节点/3 题”；navigator 要求以 system 数字为准；examiner 对 email 模板加硬约束“只出英文邮件写作题，不得出现代码/API/接口/认证/联调/部署”，concept/coach 同步（`sm_state`、`sm_mentors`、`mentors/*.md`） | `test_email_template_counts_and_topic_are_derived` | README 含“6 个节点”、无“12 节点”；start/README 无 Agent/API/接口/认证/联调/代码；examiner prompt 含“英文工作邮件写作”约束；start 探针为 1/2（20 分钟预算） |
| 7 | 恢复语与 status 的下一步和运行时状态不一致；status 看不到本会话提示等级 | 恢复语按节点混合 attempt；status 只有历史帮助汇总 | 恢复语只数当前活动、只在 `passed`+`correct` 时说过；status 的 `help.last_help_level` 取当前会话最近 `mentor_turn`，人类输出显示“上次提示等级 N”；`status.plan.activity_id` 与 `runtime_next` 同源（`sm_commands`、`sm_engine`） | `test_resume_note_never_claims_unearned_pass`、`test_status_exposes_session_help_level` | check 阶段恢复语“本阶段还没有提交记录”；help 1 的回合后 status 显示“上次提示等级 1” |

## 复跑命令与结果

```powershell
$env:LEARNARK_LLM = "mock"
python tests\run_tests.py                                  # 50/50
python C:\...\shared\check_variant.py --variant <本方向>    # 18/18
python C:\...\shared\vendor_core.py --check <本方向>        # core 1.0.2 match
```

## 明确未做 / 留给下一轮

- **email check 的题面仍由导师生成**：本轮用提示词 + protocol 约束“只出写作题”，并测了 runtime 生成文本不含编程词；但没有对导师回复做关键词拦截或拒答重试。真实模型仍可能偶发编程场景，需要下一轮加输出侧校验。
- **写作产物自动存的是学习者原文**（可能含称呼/落款/草稿），不做清洗或版本对比；同一秒内两次提交会按时间戳区分，未做多版本 diff。
- **email apply 的评分 rubric 仍是文本描述**，没有可执行的写作检查器（例如“结论是否首句”“道歉是否只出现一次”）；通过与否仍依赖导师判定。
- **20 分钟内的 check 往往做不完**：报告 S6 在 apply 产物补交后预算用尽；本轮只修了产物与预算核算，没有为“只剩 3 分钟”设计更小的 check。
