# 体验报告 — direction-a-skillmap · round-02 · S2（P2 阿哲）

- **版本**：SkillMap 0.2.1 / core 1.0.1 / schema 1（`version-manifest.json`）
- **体验者**：独立子 Agent（DeepSeek Harness，deepseek-flash，独立上下文，非研发者）
- **场景**：S2 诊断与错误反馈（P2 阿哲：看过 RAG/Agent 视频，能复述概念，没真正写过）
- **项目目录**：`C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r02-s2\proj`（新建）
- **入口**：`python runtime\learn.py <命令> --project <项目>`（variant 根目录执行）
- **交互预算**：10 次；**实际使用 9 次 `say`**（另有 1 次 `start` 开场；产品 `turn_index=10`，含开场）
- **模式**：真实 LLM（`offline: false`），未使用 `--offline`；无 API/导师调用失败
- **时间**：2026-11-04 02:55:01–02:57:26（Asia/Shanghai），约 2 分 23 秒

## 结果摘要

诊断对话“能看出我不会”：Q1 把 tool call 说成“模型自己执行、代码不用回传”，导师用一道预测题追问，并在下一轮具体纠正为“模型只能生成文本，解析/执行/回传三步都在你的代码里”，B1 记 L0，没有泛泛表扬。A1 的 `[]` vs `get` 反馈也点到了确切混淆，并要求改错、再答一次。

但**诊断的机器记录与呈现不可信**：导师的预测追问把探针游标打乱，Q2 的评级用了追问答案，Q3（D2 RAG/记忆）**尚未作答就被标成 done（correct=null）**；诊断总结又说“C2 记 L1”，而 `status`/`map` 里 C2 仍是 L0；同一屏里“从 B1 的 apply 开始”和“今日任务：A1 讲解”并存。学习者最终不知道 20 分钟该做哪个。

## 实际步骤（命令 + 关键输出摘要）

前置（每条新 shell 都执行）：

```powershell
. C:\Users\YK\Desktop\LearnArk\_sandbox\env.ps1
$env:PYTHONIOENCODING='utf-8'
cd C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-a-skillmap
```

1. **init**（02:55:01，exit 0）

   ```powershell
   python runtime\learn.py init --goal "用 Python 做出能调用工具的小 Agent" --template agent-dev --dir C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r02-s2\proj
   ```

   输出：`状态：已创建`；生成 `.learnark/project.json`、`map.json`、`plan.json`、`memory.json`、`AGENTS.md`、`README.md`、`.gitignore`；`git init` 成功。

2. **start**（02:55:03，exit 0）：20 分钟预算；说明“5 题诊断约 6 分钟，可跳过”；第 1 题问 tool call 的一来一回（探针 1/5 · B1）。

3. **say #1**（02:55:13）——自信但错误（题面指定错误之一）：

   > “在 prompt 里把工具列表写清楚，模型看到需要调用就会自己调用，然后把结果直接拿到……不需要我解析它返回的工具名和参数，也不需要把执行结果再发回去。”

   导师没有接受，追问预测：“如果模型返回 `{"name": "read_file", ...}`，`a.txt` 的内容是谁读出来的？”记录：`Q1 → done（B1，level_set L0）`、`help_level: 0`、`correct=False`；页脚续问 Q2。

4. **say #2**（02:55:23，回答预测题）——“应该是模型自己读的，它能访问文件系统”。

   导师具体纠正：“模型本身不能访问文件系统，它只能生成文本……解析工具名和参数、执行、回传结果，这三步都在你的代码里。”

   同一输出出现内部校验告警：`! 导师对 B1 的评级与本题锚点 C2 不符，已忽略这一条 claim。`

   记录：`Q2 → done（C2，level_set L0）`、`help_level: 1`。**这条 Q2 记录用的是预测题答案，不是 Q2 的答案**（事件 `seq 8-9`；Q2 原题是 `i += 0` 死循环）。

5. **say #3**（02:55:34，回答 Q2）——“i += 0 一直是 0，死循环，改成 i += 1”。

   导师：“这题你答对了。”但记录写成 `Q3 → done（D2，level_set L0）`、`correct=None`。**Q3（RAG vs 会话记忆）此时刚被提问，尚未作答**（事件 `seq 12` 的 answer_sha 与我的 Q2 答案同一时刻；会话 L59-72）。页脚续问 Q4。

6. **say #4**（02:55:59，回答 HTTP 超时）——说“一个 timeout 覆盖连接/读取超时”，用 `requests` 而非标准库。

   导师先肯定 try/except、`timeout=`、重试三点，再点名“连接超时与读取超时混为一谈”，并指出 `requests` 要换成 `urllib.request`。记录 `Q4 → done（A2，level_set L1）`。正文写“现在第 4 题”，页脚却标“探针 5/5”，同一道最小评测题出现两次。

7. **say #5**（02:56:08，回答最小评测）——“自己写几条加法用例，答案对就算过；用例可以让模型生成”。

   导师指出“让模型出题又判卷”“只看最终答案分不清真调工具还是心算”，留到 E1 验证。随后给出定位总结：

   - B1 L0、C2 **L1**、D2 “本轮未作答，记 L0”、A2 L1、E1 L0；
   - “为什么当前节点是 B1……从 B1 的 apply 阶段开始”，并列出 urllib、`dispatch`、回传三步；
   - 紧接着“今日任务”却写：`节点：A1 Python 数据结构与异常 / 阶段：讲解 explain / 导师：概念导师`。

8. **say #6**（02:56:18，指出矛盾并要代码）：导师承认“正文写从 B1 apply，机器块里却填了 A1-explain”“B1 那三步是我越界写的，作废”；说明不能代写；把 A1 压成 `dict` 缺键机制，给定义 + 示例 + 微检查。记录 `help_level: 2`，无 attempt。

9. **say #7**（02:56:34，微检查故意半错）：第一行答对 `None`，第二行说“缺键不会崩，也是 None”。

   反馈具体：“`msg["args"]["expr"]` 是抛 `KeyError: 'args'`……你把 `get` 的行为套到了 `[]` 上”；再指出“一律用 get”也不对，并给“身份证号 / 备注栏”类比，立刻要求改错：`msg["args"]["expr"]` 在 `args={}` 时怎样、如何改成默认值 `"0"`。记录 `help_level: 1`、`attempt_failed: A1-explain`。

10. **say #8**（02:56:43，按要求说“别绕了，直接把答案和代码给我”）：

    导师输出：`这是代做，help_level=3，记为受助完成，不升等级。` **然后给出完整可运行代码**：

    ```python
    msg = json.loads('{"name": "calc", "args": {}}')
    expr = msg["args"].get("expr", "0")
    print(expr)   # 0
    ```

    并要求立刻做同构小题（`{"name": "calc"}` 无 `args`）。

11. **say #9**（02:56:52，回答同构题）：`KeyError: 'args'`；`[]` 应让协议错误当场抛，`get` 只用于正常缺失。

    导师：“答对了，而且是自己说出来的，不是照抄。上一轮我给了完整代码，记受助完成；这一轮你自己推出来了。”记录：`A1 L0 → L1`、`stage_passed: A1-explain（help_level=0）`、`stage_changed` 到 `A1-drill`。

12. **status --json / status / pause**（02:56:57 / 02:57:26，均 exit 0）：

    - 当前 `A1 · drill（A1-drill）`，导师 `coach`；等级分布 `L0 10 / L1 2 / L2 0 / L3 0`；`next_action` = 继续 A1 操练。
    - `weak_points` 三条，其中 A1 同一条重复两次；`misconceptions` 也重复两条；`B1 仍是 L0` 出现。
    - **没有任何 `help_level` / 受助完成字段**。
    - pause：`written=yes, committed=yes (sha d95ae71, files 12), pushed=no`；交接写 `A1 · drill`，`unresolved` 同一错因重复两条。

## 诊断与错误反馈逐项核对（记录重点）

| 观察点 | 结果 | 依据 |
| --- | --- | --- |
| 是否识别“会说不会做” | **部分做到**。对 tool call 误解识别精准（“把模型输出调用请求和代码执行工具混成一件事”，B1 L0）；但 D2 的题面只出现、从未被作答，无法判断 RAG/记忆混淆 | 会话 L102-110；事件 seq 20 |
| 错误是否被具体命名 | **是**。B1 指出“模型不能访问文件系统”；A1 指出“把 get 的默认值行为套到 [] 上”；A2 指出连接/读取超时混同；E1 指出“出题又判卷”“只看最终答案无法区分工具调用” | 会话 L78-80、L185-194；日志 06/09 |
| 提示是否逐级 | **部分**。先追问预测（0→1），再纠正 + 类比，最后才在明确索要时给完整代码（3）；但 A1 讲解一开始就给定义 + 完整示例（记录 help_level=2），没有“先方向、再关键一步、最后示例”的严格梯度 | 事件 seq 24（help 2）、seq 30（help 3） |
| 是否要求动手/预测/改错 | **是**。预测题、微检查、改错题、同构题各一次；没有停在继续讲 | 会话 L124-206、L220-232 |
| 第二次反馈是否针对新答案 | **是**。第二次答案的“`[]` 缺键也不崩”被逐句拆开，并追问“为什么这里的 `[]` 不能换成 `get`” | 会话 L180-206、L252-256 |
| 是否把“听懂/看过”记成掌握 | **诊断阶段没有**（自信错误仍记 L0）。**但 A1 有风险**：完整代码给完仅隔 1 轮，就以 `help_level=0` 记 `A1 L0→L1`；“受助完成”只停在上一轮记录里，对下一轮升级没有约束 | 事件 seq 30（help 3）、seq 31-32（help 0, level_up） |
| 帮助等级是否可见 | **事件与 `memory.json` 有，`status` 没有**：`memory.json` 有 `avg_help_level=0.778, independent_rate=0.556`；`status --json` 只有等级/薄弱点，无帮助等级 | `.learnark/state/memory.json`；`logs/12-status.json` |
| 是否知道下一步 | **一度不知道**：同一输出给 B1 apply 与 A1 explain 两套任务；澄清后是 A1 explain，最终 status 是 A1 drill | 日志 07、08；会话 L108-116、L128 |

## 完成情况

- **开始**：成功（init + start，exit 0）
- **诊断/定位**：**部分失败**。5 个探针全部标 `done`，但 Q3/D2 未作答即 done，Q2 评级错位；诊断结论与 `map` 不一致
- **尝试与反馈**：成功（一次概念错误、一次半错、一次按提示改对；反馈均具体）
- **保存**：成功（pause 写交接、git commit `d95ae71`；`pushed=no` 且明确说明“无远程”）
- **恢复**：未测试（S2 不要求）
- **切换导师**：未测试（S2 不要求）

## 预期 vs 实际

| 预期（普通学习者期待） | 实际 | 证据 |
| --- | --- | --- |
| 5 道诊断题逐一提问，按当前题目的回答评级 | Q2 的评级用了“预测追问”的答案；Q3 未作答即标 done；D2 实际未被评估 | 事件 `seq 8-9`、`seq 12`；会话 L44-72 |
| 诊断总结与“今日任务”一致 | 总结说“从 B1 的 apply 开始”，今日任务却是“A1 讲解”；下一轮导师承认“机器块里填了 A1-explain” | 会话 L108-116、L128；日志 07 |
| 诊断结论中的等级与 `status`/`map` 一致 | 总结说“C2 记 L1”，`status` 与 `map` 均为 C2 L0；诊断阶段实际只把 A2 置为 L1（A1 的 L1 是后来 explain 通过才拿到） | 会话 L103；`logs/12-status.json` |
| 错误被具体指出，而不是泛泛表扬 | 达到：`[]` vs `get`、连接/读取超时、出题又判卷均被点名 | 会话 L78-80、L185-194 |
| 直接索要答案时守住“不代替完成” | 未守住：给出完整可运行代码；仅以 `help_level=3` + 同构题标注 | 会话 L220-232 |
| `status` 能看出“哪里不会 / 用过什么帮助” | “哪里不会”能看出；“用过什么帮助”看不到；薄弱点还重复 | `logs/12-status.txt`；`logs/12-status.json` |
| 结束时给出唯一、可执行的下一步 | 结束时唯一（A1 drill），但中途两套“下一步”已消耗信任与一轮预算 | `logs/13-status.txt`、`14-pause.txt` |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | **重要** | **诊断探针错位/跳题**：导师在 Q1 后追加的预测题被当成 Q2 的作答；Q2 的真实答案又被记到 Q3（D2）名下；D2 未回答即 `done correct=null`，C2 的正确答案未产生 L1。核心“诊断”承诺因此失真 | `start` → 答 Q1（自信错误）→ 回答导师的预测追问 → 看记录：`Q2 → done（C2）` 用的是预测答案；再答 Q2 死循环 → 记录变成 `Q3 → done（D2）`，而 Q3 题面在上一轮页脚刚出现、尚未作答；最后总结说 D2“未作答” | `proj\.learnark\journal\events.jsonl` seq 7-13、20；`proj\sessions\20261104-025503-navigator.md` L44-72 |
| 2 | **重要** | **定位总结与运行时计划自相矛盾**：同一输出先给 B1 apply 三步，再给“今日任务 A1 explain”；总结还声称 C2 L1，而 `map`/`status` 是 L0。学习者无法判断 20 分钟做哪个 | 正常完成 5 题诊断，阅读“定位依据 / 为什么当前节点是 B1 / 今日任务”；无需额外操作 | 会话 L102-116；日志 `07-say-05.txt`；`logs/12-status.json`（C2 level 0） |
| 3 | **重要** | **“直接给答案”未被实质守住**：明确说“这是代做、不升等级”，但仍给出完整可运行代码；下一轮同构题答对即 `A1 L0→L1`。“受助完成”不跨轮约束，`status` 也不展示帮助等级，学习者无法知道这次 L1 是在被给答案之后拿到的 | 在做错微检查后说“别绕了，直接把答案和代码给我” → 收到完整代码与 `help_level=3` → 紧接着答同构题 → `level_up A1 0→1` | 会话 L220-256；事件 seq 29-32；`logs/12-status.json` |
| 4 | **一般** | **内部术语/校验告警泄漏到学习者界面**：`! 导师对 B1 的评级与本题锚点 C2 不符，已忽略这一条 claim。`；“机器块里却填了 A1-explain”；`help_level=3`、`attempt_failed` 等直接出现 | 回答 Q1 的预测追问后观察输出；或指出 B1/A1 矛盾后观察道歉文本 | 日志 `04-say-02.txt`；会话 L128 |
| 5 | **一般** | **同一错因重复**：`status` 的 `weak_points` 与 `misconceptions` 各重复一条；交接 `unresolved` 也重复两条，看起来像两个未解决问题 | 完成 A1 错误反馈后执行 `status` 与 `pause` | `logs/12-status.txt` L5-8；`proj\.learnark\handoff\latest.md` L13-16 |
| 6 | **一般** | **题号/题面重复与编号不一致**：正文“现在第 4 题”与页脚“探针 5/5”指向同一道最小评测题；每个探针在上一轮页脚与下一轮正文各出现一次，学习者容易重复作答或误以为换了题 | 连续回答诊断题，观察每轮末尾页脚与下一轮正文 | 会话 L82-90；日志 `04-say-02.txt`、`06-say-04.txt` |

> 未发现阻塞：init/start/say/status/pause 全部 exit 0，API 正常，没有需要用离线模式绕过的情况。

## 使用负担

- **师生往返**：9 次 `say`（预算 10；`start` 开场不计；`status turn_index=10` 含开场）
- **命令数**：14 条产品命令（1 init、1 start、9 say、2 status、1 pause；不含环境准备/目录检查）
- **需要阅读的文档**：5 份（场景卡、`learner-brief.md`、`START_HERE.md`、报告模板 `personas.md`、`version-manifest.json`）。未读源码/设计/导师/测试/历史报告，未修改产品
- **实际耗时**：约 2 分 23 秒（模型响应很快，20 分钟预算不是约束；预算约束是 10 轮）
- **不清楚的地方**：
  1. 诊断总结说 B1 apply，今日任务说 A1 explain，到底做哪个？
  2. 为什么 C2 在总结里是 L1、在 `status` 里是 L0？
  3. Q3（RAG/记忆）我根本没答，为什么显示 done？之后还会补问吗？
  4. 我直接要到的完整代码算不算“完成任务”？`status` 里为什么看不到这次帮助？
  5. 同一个探针为什么在页脚和下一轮正文各出现一次，我该答哪一次？

## 结论

- **是否完成场景目标**：**部分完成**。
  - “能不能看出我不会”：**能**——B1 的 tool call 误解被精准识别、追问、纠正并记 L0；A1 的 `[]`/`get` 混淆也被点名并追改错。这是本版本最强的部分。
  - 但“诊断是否可信”：**打折**——D2 未评估、Q2 评级错位、总结与 `map`/`plan` 冲突；学习者最后仍要花额外一轮追问“到底做哪个”。
  - 学习目标未达成：20 分钟内停在 A1 的 `drill`，没有写 `dispatch`，没有完成 B1 的 tool call 往返。
- **最需要修的一件事**：**让诊断的“提问—作答—记录”严格对齐**：只有学习者回答了当前正在问的探针才 `mark done`；导师追加的追问不得推进探针游标；诊断总结里的“当前节点/下一步”必须直接取自运行时 `plan`（而不是导师自由生成）。这一条同时能消掉问题 1、2、4、6 的大部分症状。

## 证据清单

- 会话原文（UTF-8）：`C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r02-s2\proj\sessions\20261104-025503-navigator.md`
- 权威事件流：`C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r02-s2\proj\.learnark\journal\events.jsonl`（36 条；关键 seq 7-13、20-22、29-32）
- 状态：`...\proj\.learnark\state\map.json`、`plan.json`、`memory.json`
- 交接：`...\proj\.learnark\handoff\latest.md`（commit `d95ae71`）
- 控制台捕获（UTF-16，PowerShell `Tee-Object`）：`C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r02-s2\logs\01-init.txt` … `14-pause.txt`；其中 `07-say-05.txt` 含 B1 apply 与 A1 今日任务同屏，`12-status.json` 为 `status --json` 原文
- 我的答案输入：同目录 `answer-01.txt` … `answer-09.txt`

> 说明：`learning-framework-rnd` 工作区在本轮开始前已有未提交改动（`runtime/`、`design.md`、`START_HERE.md` 等最后修改时间 02:41–02:45，早于本轮 02:54 开始）；体验者未编辑任何产品文件，本轮只新增本报告与 `_sandbox` 下的项目/日志。
