# 体验报告 — direction-a-skillmap round-05 S5（P3 Mia，严格 20 分钟）

- 版本: 0.2.3（core 1.0.2，schema 1）
- 体验者: 独立子 Agent（deepseek-flash 独立上下文，非研发者；只读公开入口文档与产品输出）
- 场景: S5 短时与返学（P3 Mia：两周前学过一点 function calling，今晚只剩 20 分钟，明早要早起）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r05b-s5\proj`
- 入口: `python runtime\learn.py`（cwd = `variants\direction-a-skillmap`）；真实 LLM，**未使用** `--offline`
- 交互预算: 6 次，实际使用 **5 次**（另加 1 次命令级 `diagnose --skip`）
- 真实时间: 主会话 11:52:27 → 11:54:08，工具实际耗时 **1 分 41 秒**（每轮 LLM 3–6 秒）。20 分钟按“学习者预算”核算产品声称时长，而不是本地墙钟；见下文预算核算。

## 实际步骤（命令 + 关键输出摘要）

1. 建项目（全新目录，先前不存在）：
   ```powershell
   python runtime\learn.py init --goal "能独立设计与实现最小可用 Agent" --template agent-dev --dir C:\...\_sandbox\projects\a\r05b-s5\proj
   ```
   输出：`模板：agent-dev（12 个节点，诊断 5 题）/ 已创建 / git init ...`，exit 0。生成 `README.md`、`AGENTS.md`、`.learnark/`。

2. 带 20 分钟参数开始：
   ```powershell
   python runtime\learn.py start --project <proj> --minutes 20
   ```
   导航导师开场：先对齐目标，说明“5 题诊断，约 6 分钟，可以跳过”，然后问 Q1（B1：tool call 的一来一回）。真实 LLM 输出（无 `[离线脚本导师]` 标记，`status` 显示 `离线：no`）。

3. **第 1 次 say**（普通学习者原话，含时间）：
   > 今天只有二十分钟，上次学过一点 function calling，但忘了，继续吧。明早还要早起，别给我排一整章。……
   导师回应：记住了“你只有 20 分钟，所以今天诊断完只推一个节点，不排整章”——**口头上把 20 分钟当约束**。但同一轮又把 Q1 变成追问（提示等级 1），诊断进度仍是 1/5：**一个探针消耗了 2 次往返**。

4. **第 2 次 say**（补答 tool 消息角色 + 请求压缩诊断）：
   > 模型那一步没有真的执行函数……执行完把返回值作为一条 tool 角色的消息发回给对话……剩下的诊断能不能压缩一点？
   导师判定 B1=L1，答应“能答就一句话，总时间控制在 5 分钟内”，出 Q2（C2 死循环）。

5. **第 3 次 say**（答对 `i += 0`，并请求跳过剩余诊断）：
   导师说“**剩下三题跳过**，不再逐题问”“**诊断到此结束**”，并给出一张“C2 的下一站：把 tool call 跑通”的任务卡（`预计时长：15–18 分钟`，含 read_file/calc/dispatch/max_steps/steps.jsonl 四件事）。**但**该轮输出末尾仍打印“诊断探针 3/5 · 锚点 D2”；`status` 显示：
   ```
   当前：诊断中（2/5 题）
   下一步：回答诊断探针 Q3（锚点 D2）
   ```
   → 对话声称跳过，运行时没有跳过；导师给的 C2 任务并非运行时任务。

6. 用公开文档里的命令收口诊断（学习者不想在诊断上耗完 20 分钟）：
   ```powershell
   python runtime\learn.py diagnose --skip --project <proj>
   ```
   输出：`诊断已跳过：全部节点按 L0 起算`。但 `status` 仍有 `L1 2`（B1/C2）。随后“今日任务”变成：
   ```
   节点：A1 Python 数据结构与异常（L0 → 目标 L3）
   阶段：讲解 explain · 导师：概念导师 · 活动：A1-explain
   预计：20 分钟（本次预算 20 分钟，只承诺推进一个阶段）
   ```
   → 已答对的 B1/C2 没能把起点带到 tool use；20 分钟预算被**整段**分给一个基础节点的“讲解”。

7. 继续：
   ```powershell
   python runtime\learn.py start --project <proj> --minutes 20
   ```
   概念导师（自动从 navigator 切到 concept）接着上一条“没贴代码”的话头，讲 `dispatch` 错误对象、`try/except`、`eval` 边界；给 1 道微检查：`dispatch("calc", {})` 返回什么？并说“答完这题，今晚就收尾”。

8. **第 4 次 say**：答“返回 `{"ok": False, "error": "..."}`……不确定是 KeyError 还是 TypeError”。导师确认设计，并明确指出 `fn(**args)` 缺参是 **TypeError 不是 KeyError**，给出修正版；再追问“为什么单独捕获 TypeError”。

9. **第 5 次 say**：答“混淆后分不清是模型传错参数还是工具坏了；分开可按类型决定重试/纠正/终止”。导师判“答得准”，但记 **提示等级 2、受助完成，不升级**；收尾语给出具体下一步：
   > 下次接着做：把 `dispatch` 和那个 `max_steps = 5` 的循环写完，跑一次，把 `steps.jsonl` 贴出来……

10. 保存：
    ```powershell
    python runtime\learn.py pause --project <proj> --note "今天只有二十分钟，先到这，明早还要早起"
    ```
    输出：`已收工。交接已写入 .learnark/handoff/latest.md`；`committed: yes (sha 5acf316)`；`pushed: no / remote: none`（诚实）。`status` 却仍是：
    ```
    当前：A1 ... explain（A1-explain）
    上次交接：... 未决：A1 的 讲解 阶段未收口
    下一步：继续 A1 的 讲解（A1-explain），约 20 分钟
    ```

11. 新进程恢复（模拟“明天从哪继续”）：
    ```powershell
    python runtime\learn.py start --project <proj>     # 不带 --minutes
    ```
    输出：`上次停在 A1 的 讲解，第 1 次提交已通过；今天续做 A1-explain，约 20 分钟。` 随后重新讲了一个**不同的**讲解主题（`dict[]` vs `get`），任务卡仍写 `预计：20 分钟（本次预算 20 分钟）`。再次 `pause` 收尾（sha 9120444），handoff 的 `next` 仍是“继续 A1 的 讲解，约 20 分钟”。

12. 辅助探针（回答任务第 6 条：完全不说分钟数时的默认值），另建 `_sandbox\projects\a\r05b-s5\probe-default`：
    ```powershell
    python runtime\learn.py init ... --dir <probe>
    python runtime\learn.py start --project <probe>   # 无 --minutes
    ```
    `start` 直接进入 5 题诊断（“大约 6 分钟”），**没有询问、也没有说明今天总时长**；`plan.json` 里 `minutes_budget: null`。即：**没有默认时长**，不是给一个合理默认值。

### 导师开场 / 结束语摘要

- 开场：`5 题诊断，约 6 分钟，可以跳过`；得知 20 分钟后：`你只有 20 分钟，所以今天诊断完只推一个节点，不排整章`。
- 中段（对话层）：`剩下三题跳过`、`诊断到此结束`、`今晚就一个任务，20 分钟内能收尾`、`预计时长：15–18 分钟`。
- 结束：`今晚到这里收尾`；`B1 通`、`C2 通`；`这轮我给了示例代码，属于受助完成，等级不往上抬`；`下次接着做：把 dispatch 和 max_steps 循环写完，跑一次，把 steps.jsonl 贴出来`。

### 20 分钟预算核算（关键）

| 项目 | 产品声称时长 | 依据 |
| --- | --- | --- |
| 首次诊断 5 题 | ≈ 6 分钟 | 开场语与任务卡 |
| 诊断后“今日任务”（A1-explain） | 20 分钟（“本次预算 20 分钟”） | `diagnose --skip` 输出、`status`、`next --json` |
| 合计 | **≈ 26 分钟 > 20 分钟** | 两个数字直接相加 |

另外，第 1 个探针因追问用了 2 次往返；若按 5 题各 1 次，6 次往返预算里会有 5 次花在诊断上，只剩 1 次做练习——这正是实际发生的情况。

## 完成情况

- 开始: 成功（init + start，真实 LLM，无报错）
- 诊断或定位: **部分成功**。B1、C2 各答对并置 L1；但 5 题诊断与 20 分钟冲突，对话中“跳过”不生效，最后靠 `diagnose --skip` 收口，定位回退到 A1。
- 尝试与反馈: 成功（1 次微检查 + 1 次“为什么”推理；反馈具体，明确纠正 TypeError/KeyError，说明受助不升级）。
- 保存: 成功（`pause` 写 handoff、git committed；无远程时 `pushed: no` 如实说明）。
- 恢复: 部分成功（新进程能读出“停在 A1 讲解”，但“第 1 次提交已通过”与状态“未收口”矛盾；下一步仍是同一个 20 分钟阶段）。
- 切换导师: 未手动切换；阶段驱动自动 navigator → concept，`status` 有列出可切换导师。

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 说“只有二十分钟”，整场（含诊断）按 20 分钟排 | 诊断 6 分钟 + 任务 20 分钟 = 26 分钟；20 分钟只够“讲解”，没有动手 | 任务卡“预计：20 分钟”；`status`；时间相加 |
| 任务是一个 5–10 分钟的小活动，今晚能收尾 | A1 整段 explain 占满 20 分钟；实际动手只有 1 道口头微检查 | `diagnose --skip` 输出；`next --json` |
| 两周前学过 function calling，应从相关处继续 | 起点是 A1“Python 数据结构与异常”，且导师内容混着 dispatch（tool use） | 任务卡节点 A1；session 104–146 行 |
| 说“跳过剩下诊断”就跳过 | 对话说“诊断到此结束”，运行时仍 `诊断中 2/5`、下一步 Q3；必须自己找到 `diagnose --skip` | status；session 71–101 行 |
| 结束时给一个具体、可执行的“明天从哪继续” | 导师说“写 dispatch + max_steps 循环、跑 steps.jsonl”；系统/交接说“继续 A1 讲解，约 20 分钟”；两者不一致 | session 207 行；handoff；`status` |
| 不说分钟数时给一个合理默认（并说明） | 无默认：`minutes_budget: null`，不询问，直接开 5 题诊断 | `probe-default/.learnark/state/plan.json` |
| 结束后下次不再重复同一段 | 恢复后仍做 A1 explain，只是换了个讲解小主题；`next` 仍 estimated 20 分钟 | resume 输出；`next --json` |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据 |
| --- | --- | --- | --- | --- |
| 1 | 重要 | **20 分钟没有作为端到端预算**：诊断约 6 分钟 + 任务 20 分钟 = 26 分钟；且 20 分钟全部给 explain，没有任何 5–10 分钟可完成的小活动。 | `start --minutes 20` → 答 2 题 → `diagnose --skip` → 看“今日任务：预计 20 分钟”。 | `status`；`next --json`（estimated_minutes=20）；session 104–146 行 |
| 2 | 重要 | **对话里的“跳过诊断”不落状态**：导航导师说“剩下三题跳过/诊断到此结束”并给出 C2→tool use 的 15–18 分钟任务，但运行时仍停在诊断 2/5、下一步 Q3；该任务卡不是运行时任务。 | 第 3 次 say 后立即 `status`。 | `status`（诊断中 2/5，下一步 Q3）；session 71–101 行 |
| 3 | 重要 | **短时定位回退且内容与节点不符**：已答对 B1/C2，跳过后仍从 A1“Python 数据结构与异常”20 分钟 explain 起步；概念导师实际讲的是 dispatch/异常（tool use 内容）。返学者会觉得“又从最基础重来”。 | `diagnose --skip` 后看任务卡与导师正文。 | 任务卡 A1；session 104–146 行；`status` 薄弱 A1/B2/C1 |
| 4 | 重要 | **阶段不推进 + 两套“下一步”矛盾**：收尾后 `status` 仍“A1 explain 未收口”，`next` 仍“继续 A1 讲解 20 分钟”；恢复语却说“第 1 次提交已通过”，而 `plan.json` 为 `passed: false`；导师的 next（dispatch 循环）与系统 next（再讲 20 分钟）不同。 | `pause` → `status` → `start`（新进程）对比。 | `handoff/latest.md`；`plan.json` stage_progress；resume 输出 |
| 5 | 一般 | **教学示例自相矛盾**：先给的 `dispatch` 示例把 `except KeyError` 注释成“缺参数”（实际缺参是 TypeError），下一轮才纠正；新手可能先记住错的。 | 看第一版示例与随后的纠正。 | session 128–138 行 vs 161–163 行 |
| 6 | 一般 | **不给分钟数时没有默认预算，也不询问**：`start` 直接开 5 题诊断（约 6 分钟），`minutes_budget` 为 null；对“有点时间”的人没有时间框架。 | 新项目 `start` 不带 `--minutes`，看输出与 `plan.json`。 | `probe-default\.learnark\state\plan.json`（`minutes_budget: null`）；start 输出 |
| 7 | 一般 | **`diagnose --skip` 文案与地图不一致**：提示“全部节点按 L0 起算”，实际 `status` 仍有 2 个 L1（B1/C2）。 | 执行 `diagnose --skip` 后 `status`。 | 命令输出 vs `status`（等级 L1 2） |

> 说明：探针项目 `pause` 曾出现 `[exit=-1]`，那是我用 `Select-Object -First 5` 截断管道导致，**不是产品错误**；主项目所有命令 exit 0。全程无支付/HTTP 错误、无乱码。

## 使用负担

- 师生往返: **5 次**（预算 6）；其中 2 次用于同 1 个诊断探针，1 次用于请求压缩/跳过，真正练习只有 2 次。
- 命令数: **19 条**产品命令（主项目 15 条：init、start×3、say×5、status×2、diagnose --skip、pause×2、next；辅助探针 4 条）。另有读文件若干。
- 需要阅读的文档: 4 处（场景卡、`learner-brief.md`、`START_HERE.md`、`personas.md` 模板）；`AGENTS.md` 自动载入。
- 不清楚的地方:
  1. “跳过诊断”到底以对话为准还是以状态为准？为什么要另找 `diagnose --skip`。
  2. 同一轮里“C2 的下一站（15–18 分钟）”和“今日任务 A1（20 分钟）”哪个算数。
  3. 20 分钟是否包含 6 分钟诊断；为什么“预计 20 分钟”正好等于全部预算。
  4. “第 1 次提交已通过”指什么，为什么状态说“未收口”。
  5. 明天到底续 A1 讲解，还是写 dispatch 循环。

## 结论

- 是否完成场景目标: **部分完成**。开始、1 次真实尝试与具体反馈、保存、新进程恢复都做到了；但“20 分钟”只在话术里被承认，没有变成端到端预算：诊断就占 6 分钟，之后整段 20 分钟 explain 把预算用尽，没有任何可在 5–10 分钟内完成并收口的小活动。结束时出现了两套互相矛盾的“下一步”，返学者无法确定明天先做哪件事；虽然复习队列为空、没有“复习积压”，但 A1 回退 + 10 个 L0 节点仍带来明显的“进度落后”感。
- 最需要修的一件事: **让“20 分钟/只剩十几分钟/跳过诊断”这类对话约束真正驱动运行时**——把整场预算拆成“诊断 ≤2–3 分钟 + 一个 5–10 分钟可完成的活动 + 1 分钟收尾”，并保证导师话术、任务卡、`status`、handoff 的下一步是同一个、具体的动作（做什么、几分钟）。
