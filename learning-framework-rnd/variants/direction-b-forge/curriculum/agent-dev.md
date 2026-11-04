# Agent 开发 · 里程碑与验收 Rubric

## 0. 目标与默认参数

- 默认目标：能独立做出并解释一个可用的 Agent 作品，不依赖第三方 Agent 框架。
- 技术栈：Python 3.10+ 标准库 + DeepSeek API（OpenAI 兼容的 `POST /chat/completions`）。发请求可用 `urllib.request` 或 `openai` SDK，但工具循环、状态管理、错误处理必须自己写；禁止 LangChain / AutoGen / CrewAI / LlamaIndex Agent。
- 节奏：每周 10–20 小时，单次可低至 20 分钟。每个里程碑都拆成「能跑的最小版本 → 一个失败场景 → 一页设计说明」三段。
- 产物位置：代码 `m1/`…`m3/`，设计说明 `docs/`，评测数据 `eval/`，轨迹 `logs/`。未 `artifact add` 登记的文件不进入评审。

**起点校准**：不做诊断题组。首次进入只问三道选择题：一，能否自己跑通一次 DeepSeek API 调用（能／不确定／没有）；二，是否做过带工具调用的 Agent（做过／只是看过／没有）；三，这次想要什么（二十分钟见到东西／一次做完一个项目／先把概念搞清）。答案只写进 `start_profile`，不作能力证据。映射：三题都选「能／做过／一次做完」从 M1 后半开始（两个工具、失败处理、设计说明）；出现「不确定」或「没有」从 M1 前半开始，先交一个 spike；选「二十分钟」用 20 分钟切片，只做最小可运行版本；选「先搞清概念」仍先给 M1 最小作品，概念由 guide 微课补，不转成课程表。

## 1. M1 工具调用闭环

**交付物**：`m1/agent.py` + `docs/m1-design.md`。命令行 `python agent.py "把 in.txt 里的数字求和"` 一次跑通；至少两个工具（`read_file`、`calc`），工具定义含 name/description/参数类型；循环上限 6 步，每步打印 action 与 observation；缺文件、非法参数、模型返回非法格式三类失败给出可读信息而不是堆栈。

**Rubric**

| dim | criteria | weight | threshold |
| --- | --- | --- | --- |
| runnability | 干净目录一条命令跑通真实输入，有可观察输出 | 30 | 3 |
| contract | 工具定义与解析一致，参数有类型校验，非法输入返回结构化错误 | 30 | 3 |
| robustness | 缺文件、空文件、非数字不崩溃，至少改道或重试一次，步数有硬上限 | 20 | 3 |
| explainability | 设计说明讲清工具为何这样切、结果如何回填、上限为何是 6 | 20 | 2 |

**常见失败模式与微课要点**

1. 用 `eval` 或正则直接执行模型输出。微课：工具契约与 JSON schema，把错误当 observation 回填而不是抛异常。
2. 只 `print` 不维护 messages，模型看不到上一步结果。微课：assistant 与 tool 消息的追加顺序。
3. 无步数上限，模型反复调同一工具。微课：终止条件与预算（步数、token、时间取其二）。

**可接受实现**：`TOOLS` 为 `{name, description, parameters}` 列表；主循环 `for step in range(6)`；每轮把 `messages + tools` 发给 DeepSeek，解析 `tool_calls`，无调用则把 content 当最终答案；解析失败时追加一条 `{"role":"tool","content":"{\"error\":\"bad args\"}"}` 再请求一次。

## 2. M2 记忆与恢复

**交付物**：`m2/agent.py` + `m2/state/session.json` + `docs/m2-design.md`。多轮任务；每次工具调用后把会话状态原子落盘（临时文件 + `os.replace`）；消息超过阈值时用一次模型调用生成滚动摘要；进程被中断后 `python agent.py --resume` 能从磁盘继续；对 429/5xx 做最多 3 次指数退避；同一任务重复执行不产生重复副作用。

**Rubric**

| dim | criteria | weight | threshold |
| --- | --- | --- | --- |
| runnability | 中断后 resume 继续原任务，摘要不丢关键约束 | 25 | 3 |
| contract | 状态文件字段固定且有 version，读到旧版本能拒绝或迁移 | 25 | 3 |
| robustness | 状态 JSON 损坏可回退，重试不重复写文件，并发写被拒绝 | 30 | 3 |
| explainability | 说明摘要触发条件、为何这样切分状态、副作用如何做幂等 | 20 | 2 |

**常见失败模式与微课要点**

1. 摘要只留对话不留约束，恢复后忘了「只能读 in.txt」。微课：状态里固定 `constraints` 字段，摘要不覆盖它。
2. 直接 `open(...,'w')` 写状态，进程被杀留下半个 JSON。微课：临时文件 + `fsync` + `os.replace`。
3. 重试整个任务导致工具被调用两次。微课：幂等键与已执行动作日志。

**可接受实现**：`state = {version, task, constraints, messages, steps, done_actions}`；每步 `write_json_atomic`；消息超过 12 条时请求一次摘要并把旧消息折叠成 `summary` 字段；恢复时校验 `version`，不匹配则提示迁移而不是静默覆盖。

## 3. M3 可评测的 Agent 作品集

**交付物**：`m3/` 完整 agent + `eval/tasks.jsonl`（不少于 10 条任务，含 2 条边界或对抗样例）+ `logs/trajectories.jsonl` + `REPORT.md`（成功率、平均步数、token 成本、失败分类）+ 三分钟讲解稿。评测必须可由一条命令重跑，结果写回报告。

**Rubric**

| dim | criteria | weight | threshold |
| --- | --- | --- | --- |
| runnability | 评测一条命令重跑，结果与报告一致 | 20 | 3 |
| contract | 评测用例格式统一，判定条件可程序化，轨迹字段完整 | 20 | 3 |
| robustness | 含失败与边界样例，崩溃被记录为失败而不是中断 | 25 | 3 |
| explainability | 报告有失败分类与改进假设，能讲清一次真实取舍 | 35 | 3 |

**常见失败模式与微课要点**

1. 评测集只挑会做的题，成功率虚高。微课：用例分层（常规、边界、对抗）与抽样规则。
2. 轨迹缺步数或 token，失败无法归因。微课：每步记录 step、tool、latency、tokens。
3. 报告只有结论没有失败分类。微课：失败分类表与「下一版改什么」的假设写法。

**可接受实现**：`tasks.jsonl` 每行 `{id, input, expect: {type: "contains"|"equals"|"file", value}}`；`run_eval.py` 逐条跑 agent 并把 `{task_id, passed, steps, tokens, error}` 追加到轨迹；`REPORT.md` 由脚本生成表格后再手写分析，避免手抄数字。

## 4. 通过规则与缺口排序

- 每维整数 1–4 分，四个维度全部达到各自 threshold 才算「候选通过」；再由 critic 发起三问 defense（每题绑定作品行号，至少两问通过且权重最大维度那问必过），两者同时满足才交运行时判定里程碑通过。
- 加权总分不用于通过判定，只用于缺口排序：先按 weight 降序，再按 `(threshold - score)` 降序，最后按里程碑升序。
- 缺口卡走 `gap learn` 后状态为 learning。关闭有三条路径，全部由运行时判定，导师不得自行关闭：
  (a) **复评达标**：后续评审同一 dim ≥ threshold，这是唯一算「已解决」的路径；
  (b) **微课 + 微练习**：help_level ≤1 完成一次针对该 dim 的小练习，记为「未在作品复验」，只降优先级、不算解决；
  (c) **drop 记 stale**：连续三次重开该卡仍未通过才允许，记 `stale`，不算解决，`doctor` 必须列出；该维度后续排序权重乘 0.6（每次 stale 累积衰减）。

**评审证据要求**：critic 的每条 note 必须能指向具体文件、函数或一次实跑输出；只有复述设计说明而没有实跑证据的维度最高给 2 分。同一份作品（同 sha256）重复提交不重复计分，只更新缺口状态。

