# round-01 修复记录 — SkillMap v0.2.1

- **输入**：`experiments/round-01/experience-S1-P1.md`（独立子 Agent 体验，S1 / P1 小林，真实 LLM，10 次往返）
- **版本**：0.2.0 → **0.2.1**；core 1.0.1（未升级，`vendor_core.py --check` 通过）
- **范围**：只改 direction-a 自己的 `runtime/`、`mentors/`、`templates/`、`tests/` 与文档；未改 `shared/`、其他方向、vendored core。
- **结论**：报告中的 4 条「重要」+ 1 条文档不一致（问题 8）已修；每条都有确定性测试。真实 API 的漏块率本轮未复测（见末节）。

## 问题 → 修复 → 测试

| # | 报告问题 | 根因 | 修复（文件） | 测试 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | 诊断评级不进入地图：导师说“全对、从 A2 开始”，运行时记 B1/D2 为 L0 并排 A1 | 机器块没有 `probe` 字段，运行时只能从 `attempt.correct` 推等级；导师正文不落盘 | 机器块新增 `probe{node,level,reason}`；`validate_turn` 只接受 level 0/1 与模板声明的锚点；`apply_probe_answer` 用 claim 定级、错锚点记 `probe_claim_rejected` 并忽略；`probe` 写入 `diagnosis_probe` 事件与 `project.json` 的 probe 记录；定位逻辑不变（先修 ≥L1 才参与）（`runtime/sm_engine.py`、`runtime/sm_mentors.py`、`mentors/navigator.md`） | `test_placement_all_correct_profile`、`test_placement_mostly_wrong_profile`、`test_probe_claim_validation` | 全对档案：5 个锚点全 L1、`current_node=B1 stage=apply`、`placement_applied{node:B1,level:1,probe:Q1}`；偏弱档案（仅 A2 对）：`A1-explain`；level=2 的 claim 记 `mentor_update_invalid`；错锚点 claim 记 `probe_claim_rejected` 且地图不变 |
| 2 | 补问提示泄漏给学习者，且 9/12 回合要补问 | `process_turn` 把 `repaired` 写进 `outcome.notes`，`cmd_say` 用 `!` 打印 | 补问改为静默：只写 `mentor_update_retried` 事件（`say` 与 `start` 两条路径），stdout 不再出现内部提示；system prompt 末尾加“最后一条硬规则”，诊断轮注入题面与 `probe` 模板（`runtime/sm_engine.py`、`runtime/sm_commands.py`、`runtime/sm_mentors.py`） | `test_repair_is_silent_and_applies_state` | 假 LLM 首轮无块→恰好 1 次补问；`outcome.notes == []`；存在 `mentor_update_retried`；补回的块仍把 A1 升到 L1 |
| 3 | apply 假阴性：文件在 `artifacts/parse_record.py`，导师报 `parse_record.py` 仍记 `artifact_missing` | `artifact_info` 只按“项目根 + 原样路径”解析 | 依次尝试「项目根 / `artifacts/` / `artifacts/<basename>`」，命中后把证据路径规范化为项目相对路径；三者都不存在才算 `artifact_missing`（`runtime/sm_state.py`，`coach.md` 补路径说明） | `test_artifact_paths_accept_basename` | `parse_record.py` 与 `artifacts/parse_record.py` 两种写法都通过、`level_up.artifact` 统一为 `artifacts/parse_record.py`；真缺失仍记 `artifact_missing` 且不写 attempt |
| 4 | 诊断题正文与页脚不一致（Q2 12 行伪代码 vs `i += 0`；Q5 数函数 vs 加法评测） | 导师自己编题；页脚是运行时题面，两者无约束 | 题面唯一权威改为运行时：`PROTOCOL_TEMPLATE` 每轮注入「本轮诊断题（唯一合法题面，正文照抄）」；`navigator.md`、`templates/agent-dev.md` 抄录同一组 5 题；`design.md` §3 同步（`runtime/sm_mentors.py`、`mentors/navigator.md`、`templates/agent-dev.md`、`design.md`） | `test_probes_render_once_with_consistent_anchors` | 5 题各渲染一次，页脚序列固定为 `1/B1, 2/C2, 3/D2, 4/A2, 5/E1`；5 个题面互不相同；navigator.md 含同一组关键词 |
| 5 | 导师提醒“没加引号”（PowerShell 5.1 吞引号，不是学习者的错） | 导师 improvised；产品无约束 | 运行时协议加一条：不要评价/纠正学习者怎么调用 shell、不要要求加引号，按原意理解；START_HERE 增加 `say -` + UTF-8 文件的引用安全写法（`runtime/sm_mentors.py`、`START_HERE.md`） | 由 `test_probes_render_once_with_consistent_anchors` 的 navigator 文本检查 + 人工复核协议文本 | 协议中不再出现“加引号/换引号”类要求；START_HERE 的示例改为 stdin 管道 |
| 8 | 版本文档不一致（标题 v0.1.0 / 页脚 0.1.1） | 手工改版本时漏改标题 | 标题与页脚统一为 **v0.2.1**；`version-manifest.json` 0.2.1（`START_HERE.md`、`version-manifest.json`） | `check_variant` + 文档复核 | 标题与页脚一致 |

## 复跑命令与结果

```powershell
$env:LEARNARK_LLM = "mock"
python runtime\learn.py init --goal "回归" --dir <tmp>\proj        # 0
python runtime\learn.py start --project <tmp>\proj                  # 0
python runtime\learn.py say "..." --project <tmp>\proj              # 0
python tests\run_tests.py                                           # 28/28
python C:\...\shared\check_variant.py --variant <本方向>            # 18/18
python C:\...\shared\vendor_core.py --check <本方向>                # core 1.0.1: all vendored copies match
```

- `tests/run_tests.py`：**28/28 passed**（约 61 s，全程离线、无网络；新增 6 个用例：两个 placement、claim 校验、题面渲染、产物路径、静默补问）。
- `check_variant.py`：**18/18 checks ok**，退出码 0。
- `vendor_core.py --check`：**core 1.0.1: all vendored copies match**。

## 明确未做 / 留给下一轮

- **真实 API 漏块率未复测**：本轮只用假 LLM 验证“静默补问 + 状态仍生效”；prompt 强化是否把 9/12 降到更低，需要下一次真实体验统计 `mentor_update_retried` 比例。
- **进程内测试的边界**：静默补问测试直接调用 `sm_mentors.turn` + `sm_engine.process_turn`（mock 不会触发补问，故用假 LLM）；CLI 层只保证不再打印该类提示。
- **问题 6（45 分钟 vs 30 分钟预算）与问题 7（会话/日志导师归属）** 不在本轮 5 条修复范围内，仍记录在 `issues.md`；问题 7 建议下一轮单独修（session 标题按回合导师写，而不是按会话创建时的导师）。
- **问题 3 的产品侧无法根除**：Windows PowerShell 5.1 的参数解析会吞双引号；本轮只做到“不责怪学习者 + 给出 `say -` 写法”，无法让 `say "..."` 在 PS 5.1 下保留内层引号。
