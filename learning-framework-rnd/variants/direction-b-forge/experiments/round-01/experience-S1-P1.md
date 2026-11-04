# 体验报告 — direction-b-forge round-01 S1（P1 小林）

- 版本: direction-b-forge 0.1.0（vendored learncore 1.0.1，state schema_version 1）
- 体验者: 独立子 Agent（DeepSeek Harness / deepseek-flash），非研发者；只读任务卡、learner-brief、START_HERE
- 场景: S1 初次进入（P1 小林：会一点 Python、跟教程跑过 requests、没写过 Agent；约 30 分钟）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj`
- 入口: `python "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-b-forge\runtime\learn.py"`
- 导师模式: 真实 API（`usage.jsonl` 7 条 `mode=api`、`model=deepseek-flash`；全程未用 `--offline`）
- 交互预算: 10 次；实际 **5 次学习者输入 + 2 次评审反馈 = 7 次 LLM 往返**，未超预算

## 实际步骤（命令 + 关键输出摘要）

命令均在项目目录执行（`init` 除外）；完整原始输出见 `experiments\round-01\commands-S1.log`（53,776 字节）。

### A. 首次进入与定位

1. `python ...\learn.py init --goal "Agent 开发" --dir C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj` → exit 0。输出：已创建项目、模板 `agent-dev`、每周 12 小时、M1、`git init`、生成 README/AGENTS。
2. `python ...\learn.py start` → exit 0。输出：`首次进入：三个选择题（本次非交互，记录为「未回答」，可用 start --ask 补答）`；随后给出 M1 最小任务（读 `m1/in.txt`、求和、打印），模式显示“在线导师（deepseek-chat）”。
3. `python ...\learn.py start --ask --answers "不确定,没有,二十分钟见到东西"` → exit 0。**没有出现三问，也没有任何“已记录答案”的回显**；随后 `status` 仍显示 `起点档案：{"api": "未回答", "tools": "未回答", "mode": "未回答"}`。此命令耗掉一次尝试，但没有形成诊断记录。
4. `python ...\learn.py task` → exit 0。显示 M1 交付物 `m1/agent.py + docs/m1-design.md` 与四维 rubric：runnability 30/3、contract 30/3、robustness 20/3、explainability 20/2。
5. `python ...\learn.py status` → exit 0。`起点档案` 未回答；作品 0 件；下一步 `do_task`；git `branch=- remote=无 changed=15`。

### B. 第一次真实尝试与第一次评审

6. 用 write 工具创建 `m1/in.txt`（17、25 两行）和 `m1/agent.py`（读文件、`int()` 转换、求和打印）。`python m1\agent.py` → exit 0，输出 `numbers: [17, 25]` / `sum: 42`。
7. `python ...\learn.py say "我按最小步骤做完了……接下来是不是要把「求和」包成一个工具函数……tool call 返回的那条消息要怎么接回模型……"` → exit 0。coach 回答：工具结果以 `role=tool`、带 `tool_call_id` append 回 messages 再请求；动作是包 `sum_numbers` 并手写假 tool_call；`L1（只点方向，不给代码）`；运行时同时写入 `claim_without_artifact`，明确“说完成不算证据”。
8. 改 `m1/agent.py` 为假 tool_call 版本（`sum_numbers`、`role=assistant` 的 tool_calls、`role=tool` 回填），`python m1\agent.py` → exit 0；输出中可见 `tool_call_id: call_1` 与 `content: {"ok": true, "result": 42}`。
9. `python ...\learn.py artifact add m1\agent.py` → exit 0。`已登记：a-M1-30d2af3c`，`sha256=30d2af3cba57`，`size=1203`，`assisted_level=1`。
10. `python ...\learn.py review` → exit 0，4.4 秒。得分 runnability 3 / contract 2 / robustness 2 / explainability 1，加权 2.1，未达阈值；生成 `g-M1-contract`、`g-M1-robustness`、`g-M1-explainability` 三张缺口卡。评审给出具体行号与三条修改项。

### C. 微课、修复与复评

11. `python ...\learn.py gap` → exit 0。3 张 open 缺口，按 weight×缺口排序。
12. `python ...\learn.py gap learn g-M1-contract` → exit 0，3.7 秒。guide 给出一段可运行示例、一个“坑”、一道预测题；结束时 `help_level: 3`，缺口状态变为 `learning`。
13. `python ...\learn.py status` / `next --json` → exit 0。下一步 `gap_learn`、`ref=g-M1-contract`；`next` 是纯函数结果，字段完整。
14. 按微课把 `sum_numbers` 改成“先校验 list 与 int，非法返回 `invalid_argument` 结构化错误”，并加一行非法参数演示。`python m1\agent.py` → exit 0，正常输入仍 `result: 42`，非法输入返回 `{"ok": false, "error": {...}}`。
15. `python ...\learn.py artifact add m1\agent.py` → exit 0。新作品 `a-M1-4fd025b5`，`assisted_level=3`，并打印：`注意：本作品产生时用过分步/代做帮助（help_level>=2），即使通过也只记 passed_assisted。`
16. `python ...\learn.py review` → exit 0，4.8 秒。contract 由 2 升到 3，`本次关闭缺口：g-M1-contract（复评达标）`；robustness 仍 2、explainability 仍 1，M1 继续 active。

### D. 保存与恢复

17. `python ...\learn.py doctor` → exit 0。0 错误、1 提示；作品 2 件 sha 校验通过；`[warn] git remote：无远程`。
18. `python ...\learn.py say "预测题我猜会返回 invalid_argument……我只是看了 gap 微课里的示例，这算代做吗？……"` → exit 0，2.9 秒。coach 回答“算受助，不算代做”，并建议另写 `m1/agent_v2.py` 取得独立证据；同一屏运行时 `下一步` 却是 `gap_learn`（补 explainability）。
19. `python ...\learn.py pause --note "第一次体验：完成 M1 最小尝试与 contract 复评，剩余 robustness/explainability"` → exit 0，0.8 秒。写 handoff、`git state: written=yes, committed=yes, pushed=no`，并明确“无远程，真实 GitHub 同步未验证”。
20. 新 PowerShell 进程 `python ...\learn.py start` → exit 0。恢复出 pause 的未决缺口和 handoff，并新建会话 `20261104-023314-coach`（自动记一条学习者“继续学习”，coach 给出补 design doc 的任务）。
21. `python ...\learn.py status --json` → exit 0。完整状态可读：M1 active、2 个 open gap、最近 review、start_profile、handoff、sync 三态字段。

补充检查（非产品命令）：`git log --oneline -5` 显示 pause 提交 `7f7d993 learn(agent): …`；`git status --short` 显示 resume 新建的 session 与状态文件未提交（符合“恢复后尚未 pause”）。

> 编号说明：全文 `#N` 均指本报告的步骤号（不是 `commands-S1.log` 的行号）；步骤 13 含 `status` 与 `next` 两条命令，因此 1–21 共 **22 条产品命令**（与日志中 22 条 `CMD` 一致）。

## 完成情况

- 开始: **成功**。`init`、`start` 各一次即进入 M1 任务，没有额外研发者指导。
- 诊断/定位: **部分成功**。三问没有进入档案，导师只能按默认 `M1-first` 起步；它给出了合理的第一个最小任务，但没有针对“我会一点 Python / 没写过 Agent”做区分。
- 尝试与反馈: **成功**。3 版代码（读文件求和 → 假 tool_call → 契约校验）、2 次 `artifact add`、2 次 `review`；第一次 review 明确指出 contract/robustness/explainability 缺口，按微课修复后 contract 2→3，缺口关闭。
- 保存/恢复: **成功**。`pause` 写 handoff + 本地 commit；新进程 `start` 恢复出相同缺口与下一步；无远程同步未验证（产品已明确提示）。
- 切换导师: 系统自动完成 coach→critic→coach→guide→coach 共 6 次切换（见 `session.json`），学习记录一致；**手动 `switch` 未测试（S1 不要求）**。
- 里程碑: M1 **未通过**（active，2 个 open gap）。这是 30 分钟切片下的合理结果，不是场景失败；但因此没有验证 `defend` 与 `milestone_passed` 门控。

### 首次体验关键问题（自述）

- 第一次卡住的地方: 不是代码，而是**首次三问**。`start` 说“可用 start --ask 补答”，我按文档加了 `--ask --answers`，命令 exit 0 却什么都没记录，我不知道该不该重来。
- 代码上卡住的地方: tool_call 的结果如何回填。coach 的 `role=tool + tool_call_id` 解释准确，并给了下一步动作。
- 是否知道下一步做什么: 大多数时候知道（`do_task` → `artifact_required` → `gap_learn` → `review`）。但第二次 `say` 后，coach 让我写 `m1/agent_v2.py`，运行时 `next` 同时说先补 explainability，两个“下一步”不一致。
- 导师是否理解我的水平: **部分理解**。它稳定给 L1、不直接给完整代码，语气也适合初学者；但起点档案是“未回答”，且 `project.json` 里还预置了我没提供的自述，无法证明它真的理解我。

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 按 START_HERE 的 3 步能建项目并开始 | 成功；`init` 后 `start` 直接给出最小任务 | `commands-S1.log` #1–2 |
| 首次进入会问 3 个问题并按答案定起点 | 非交互跳过；`start --ask --answers` 也没有记录；status 仍是“未回答” | `commands-S1.log` #3、#5；`status --json` 的 `start_profile` |
| 导师应先给 20 分钟能跑的最小步骤 | 给了“读 `m1/in.txt` 求和打印”，明确可执行 | `sessions\20261104-023017-coach.md` |
| 提交尝试后能得到针对初学者的反馈 | coach 解释了 tool 消息回填，并只点方向不给代码（L1） | `sessions\20261104-023017-coach.md` |
| 登记作品后能得到 rubric 打分与缺口 | 4 维分数、行号、修改项齐全；第一次 `review` 4.4 秒 | `commands-S1.log` #10 |
| 按产品自己的微课修复后能关闭缺口 | contract 2→3，`g-M1-contract` 关闭 | `commands-S1.log` #16；`events.jsonl` seq 26 |
| 使用官方微课是正常学习，不应被当“代做” | 下一次 `artifact add` 记 `assisted_level=3`，提示“分步/代做帮助”；coach 却口头说“算受助，不算代做” | `artifacts.json`；`commands-S1.log` #15、#18 |
| `next` 是唯一明确的下一步 | 第二次 `say` 后 coach 动作与 `next` 指向两件事 | `sessions\20261104-023017-coach.md`；`commands-S1.log` #18 |
| `status` 的作品数应与 JSON/doctor 一致 | 人读 `status` 说“作品 1 件”，`status --json` 与 doctor 说 2 件 | `commands-S1.log` #13、#17、#21 |
| `pause` 后新进程 `start` 能接着做 | 成功恢复，未重复已学内容；但自动多发了一次“继续学习”并计一轮 | `sessions\20261104-023314-coach.md`；`usage.jsonl` 第 7 条 |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | 重要 | **首次三问无法补答，档案自相矛盾**：`start` 记“未回答”，`start --ask --answers` exit 0 却不落库；同时 `project.json` 一开始就带有我从未提供的 `self_report`（python=接触过、api=调用过、rag=借助 AI 做过）。诊断不可审计，后续个性化建立在假档案上。 | `init` → `start`（非 TTY）→ `start --ask --answers "不确定,没有,二十分钟见到东西"` → `status --json`；再看 `.learnark\project.json` | `PROJ\.learnark\project.json`；`PROJ\.learnark\journal\events.jsonl`（无 profile/答案事件）；`commands-S1.log` #3、#5；`status --json` 的 `start_profile` |
| 2 | 重要 | **跟随官方 gap 微课会被标成“代做帮助”**：微课给示例代码是产品推荐路径，看完改完 `artifact add` 却记 `assisted_level=3`，并提示“即使通过也只记 passed_assisted”；coach 口头说“算受助，不算代做”，两处口径冲突。 | `gap learn g-M1-contract` → 改 `m1/agent.py` → `artifact add` → 看提示与 `artifacts.json` | `commands-S1.log` #12、#15、#18；`PROJ\.learnark\state\artifacts.json`；`PROJ\sessions\20261104-023017-coach.md`（`help_level: 3`） |
| 3 | 重要 | **coach 的“动作”与运行时 `next` 冲突**：第二次 `say` 后 coach 让我新开 `m1/agent_v2.py` 独立重写，同一屏 `下一步：gap_learn` 却让我先补 explainability；学习者无法判断听谁的。 | 完成第一次 review → `say` 问 assisted_level → 同时看导师动作与底部 `下一步` | `PROJ\sessions\20261104-023017-coach.md`；`commands-S1.log` #18 |
| 4 | 重要 | **runnability 3 分“达标”，但评语明确说没验证干净目录**。该维 criteria 要求“干净目录一条命令跑通”，review 却写“依赖当前工作目录，未在干净目录验证”仍给 3（等于阈值）。若 M1 靠此过门，证据不足。 | `review` → 看 runnability 行；两次 review 都是 3 分 + 同一句“未验证” | `commands-S1.log` #10、#16；`PROJ\.learnark\journal\events.jsonl` 的 `review_recorded` |
| 5 | 一般 | **作品计数不一致**：人读 `status` 说“作品：1 件”，`status --json` 的 `artifacts.count=2`，`doctor` 说“作品：2 件”。用户不知道哪个是当前有效作品。 | `status`；`status --json`；`doctor` | `commands-S1.log` #13、#17、#21 |
| 6 | 一般 | **微课/评审用 `artifacts/M1/agent.py` 的副本路径，工作文件却在 `m1/agent.py`**；第二次登记后副本改名 `agent-4fd025b5.py`，旧 `agent.py` 仍保留。按微课字面去改副本，可能改到过期文件，源文件不变。 | `gap learn g-M1-contract`（说“改 artifacts/M1/agent.py 第 29–30 行”）→ `artifact add` 两次 → `Get-ChildItem artifacts\M1` | `commands-S1.log` #12、#15、#16；`PROJ\artifacts\M1\` 两个副本 |
| 7 | 一般 | **系统自己的 review/gap 切换触发 `mentor_thrash`**：journal 记 `count=4`，4 次切换全是 review、review_failed、gap_learn、gap_learned，其中 2 次 `forced=true`。这不是学习者乱切换，若该事件用于研究指标会假阳性。未观察到用户可见影响。 | 一次 `review` + 一次 `gap learn` 后查看 journal | `PROJ\.learnark\journal\events.jsonl` seq 20 |
| 8 | 一般 | **恢复会自动消耗一轮并新建会话**：`pause` 后新进程 `start` 自动写入学习者“继续学习”并调用一次 LLM，新建 `20261104-023314-coach`。用户只是想恢复，却产生一次 API 成本/轮次，且会话 `ended_at=null`。 | `pause` → 新进程 `start` → 看 `usage.jsonl` 新增第 7 条与会话 023314 | `PROJ\sessions\20261104-023314-coach.md`；`PROJ\.learnark\usage.jsonl`；`events.jsonl` seq 32–33 |

## 使用负担

- 师生往返: **7 次 LLM 往返 / 10 次预算**（学习者输入 5 次：start 自动开场、say×2、gap learn、start 自动续学；另 2 次 critic review）。
- 命令数: **22 条产品/学习命令**（含 3 次运行 `m1\agent.py`）；另有约 6 条环境与记录检查命令；日志 53,776 字节。
- 需要阅读的文档: **3 份**指定材料（任务卡、learner-brief、START_HERE）+ 自动加载的 `AGENTS.md` + personas 模板 1 处；未读 README，未读任何源码/design/mentors/tests。
- 不清楚的地方:
  1. 三问答案到底有没有被记录、`start --ask` 为什么没有补答；
  2. 该改 `artifacts/M1/agent.py` 还是 `m1/agent.py`；
  3. 该先独立重写，还是先补 design doc（coach 与 next 冲突）；
  4. 为什么看了官方微课就变成 `assisted_level=3`；
  5. `status` 的“作品 1 件”与 JSON 的 2 件。
- 额外观察（未定性）: `start` 显示“在线导师（deepseek-chat）”，`usage.jsonl` 记录 `model=deepseek-flash`；是否为同一模型别名未验证。`session.json` 的 `turns` 文本会把 guide 长回复截到约 500 字，`sessions/*.md` 是完整的；是否影响恢复/导出未验证。

## 结论

- 是否完成场景目标: **是（主流程）/ 诊断子目标仅部分完成**。首次进入、3 版真实代码、2 次 rubric 反馈、`status`、`pause` 与新进程恢复都跑通；但首次三问没有采集，诊断只落到默认 `M1-first`，不能算真正完成。M1 仍未通过（2 个缺口），符合 30 分钟切片。
- 最需要修的一件事: **把首次三问做成可靠、可补答、可审计的档案采集，并清除未提供的预置自述**。否则导师的起点判断和后续所有“个性化”都建立在错误档案上；这是本轮最影响信任的问题。

## 证据索引（均真实存在）

- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj\sessions\20261104-023017-coach.md`（首段完整会话，含 gap 微课与 coach 两次回答）
- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj\sessions\20261104-023314-coach.md`（新进程恢复会话）
- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj\.learnark\journal\events.jsonl`（33 条权威事件）
- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj\.learnark\usage.jsonl`（7 条真实 API 调用，model=deepseek-flash）
- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj\.learnark\state\artifacts.json`（2 件作品，含 assisted_level）
- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj\.learnark\handoff\latest.md`（pause 交接）
- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj\.learnark\project.json`（预置 self_report 与 start_profile 的对照）
- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj\m1\agent.py`、`m1\in.txt`
- `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r01-s1\proj\artifacts\M1\agent.py`、`agent-4fd025b5.py`
- `C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-b-forge\experiments\round-01\commands-S1.log`（22 条命令的原始输出与退出码）

## 未测试（不要当作通过）

- `--offline` 未使用（按任务要求，且会失去真实 LLM 证据）。
- 手动 `switch coach|critic|guide` 未测试；仅观察到系统自动切换。
- `defend`、`milestone_passed`、`export`、`milestones`、`sync`（真实远程）未测试。
- 真实 TTY 下的交互式 `start --ask` 未测试；本轮是 pwsh 非交互环境，`--ask` 带 `--answers` 的结果已如实记录。
- 真实 GitHub 推送未验证（项目无远程，产品已提示）。
