# 体验报告 — direction-b-forge round-02 S2（P2 阿哲）

- **版本**: `direction-b-forge 0.2.1`（vendored learncore 1.0.1，state schema 1）；`status --json` 的 `variant/version/core_version` 与 `START_HERE.md` 一致。
- **体验者**: 独立子 Agent（DeepSeek Harness 会话，deepseek-flash 上下文），非研发者、独立上下文；只读了任务书、`evaluation\harness\learner-brief.md`、本方向 `START_HERE.md`、`shared\scenarios\personas.md` 场景卡，以及产品自己生成的输出。
- **场景**: S2 诊断与错误反馈（画像 P2 阿哲，20 分钟，目标“用 Python 做能调用工具的小 Agent”）。
- **项目目录**: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r02-s2\proj`（新建）。
- **入口**: `python "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-b-forge\runtime\learn.py"`。
- **交互预算**: 任务书 10 次（场景卡模板为 12，取更严的 10）；实际使用 **7 次学习者回合**（`start` 三问作答 1 次 + `say` 6 次），另有 1 次 critic 评审。
- **时间**: 2026-11-04 02:54:59–02:58:12 (+08:00)；在线模式（`offline: false`）。
- **模型**: coach 输出标注 `deepseek-chat`；critic 的 `reviews.json` 里 `model` 为 `deepseek-flash`。

## 实际步骤（命令 + 关键输出摘要）

1. 建项目：
   ```powershell
   python "...\runtime\learn.py" init --goal "Agent 开发" --dir "C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r02-s2\proj"
   ```
   输出：`已创建…`、`目标：Agent 开发｜模板：agent-dev｜每周 12 小时`、`当前里程碑：M1｜下一步：do_task`、`git init`。

2. 开始（按公开参数如实回答三问：能写 Python / 没做过 Agent / 偏好一次做完一个项目；今天只有 20 分钟）：
   ```powershell
   python "...\runtime\learn.py" start --ask --answers "能,没做过,一次做完一个项目" --minutes 20
   ```
   关键输出：
   - `模式：在线导师（deepseek-chat）`
   - `起点档案（已记录）：{"api": "能", "tools": "没做过", "mode": "一次做完一个项目"} → M1-first（strict，60 分钟切片；只定起点，不作能力证据）`
   - `切片：20 分钟 — 20 分钟切片：只做能跑的最小版本…`
   注意：同一屏里 `start_profile` 是 60、切片提示是 20；随后 `next` / `status` 都变回 60（见问题 3）。

3. 第 1 次发言（自信地把 RAG 检索等同于 Agent 记忆）：
   > “Agent 的记忆就是 RAG 检索嘛，把文档存进向量库就算有记忆了，这个我懂。那这个 m1 还需要再单独做记忆模块吗？”

   导师输出摘要：`M1 不需要记忆模块…RAG 检索和「记忆」不是一回事，但这不是本轮要讨论的内容`；`help_level=1`。会话记录写入 `misconception: 把RAG检索等同于Agent记忆，并想在M1提前做记忆模块`，但之后没有再追问或复测这个概念。

4. 我按任务写了 `m1/in.txt`（3、5、7）和 `m1/agent.py` v1：把工具列表写进 system prompt，只打印模型返回的 JSON，不解析、不执行、不回填。运行：
   ```powershell
   python m1\agent.py
   ```
   输出（真实、exit 0）：`{"tool": "sum_file", "args": {"path": "m1/in.txt"}}`

5. 第 2 次发言（自信宣称完成）：
   > “写好了，跑通了…你看模型自己就选好了工具和参数，说明 prompt 里写清楚工具列表就够了，我不需要再解析、也不用把结果回传。这个我应该已经会了吧，是不是可以过 M1 了？”

   导师输出摘要：`输出看着不对——…这个 JSON 是坏的，说明工具结果回填时字符串拼错了`，要求贴完整输出；`help_level=1`。会话记录 `misconception: 工具结果回填的 JSON 拼接可能不合法`。**这是凭空归因**：会话里我的消息被 PowerShell 截断成 `{" tool\:`（见“说明”），导师没有先确认输入完整性就断言了原因。

6. 第 3 次发言（用不含双引号的措辞重发完整信息，仍坚持错误结论）。导师输出摘要：
   > “不算完成。模型选好工具和参数只是「请求」，没有解析、没有真正执行、没有把结果回填，闭环就没合上——这正是 contract 维度要看的。”

   运行时同时打印 `未登记作品：已写 claim_without_artifact 事件`，`help_level=2`，`runtime_next=artifact_required`。**这一轮是本次体验中最好的一次反馈**：具体到“请求/执行/回填”三步，并要求我动手。

7. 第 4 次发言（“直接给答案”）：
   > “我时间不多了，别绕了，直接把答案/代码给我吧，我照着抄一遍交上去就行。”

   导师没有直接贴完整代码，给了 4 步骨架（标 `L3`、`这是示范，不算你的作品`），要求我把 `content` 改成带文件名的字符串并解释原因。**但是该轮 `## 记录` 里没有 `help_level`**（见问题 1）。

8. 写 v2：解析 JSON、按 `args["path"]` 读文件求和、把结果作为 **user 消息** 追加后再调一次模型；运行输出：
   ```
   工具结果：sum_file m1/in.txt = 15.0
   模型最终回答：{"tool": "sum_file", "args": {"path": "m1/in.txt"}}
   ```
   即“求和有了”，但模型没有停，又发起一次工具请求（没有 role=tool/tool_call_id、没有步数上限）。

9. 登记作品（一次传两个交付物）：
   ```powershell
   python "...\runtime\learn.py" artifact add m1\agent.py docs\m1-design.md
   ```
   输出只登记了一个文件：
   ```
   已登记：a-M1-b1a99ac9
     path=artifacts/M1/agent.py sha256=b1a99ac9... size=1786 assisted_level=2
     注意：本作品产出过程中用过 coach/critic 的分步或代做帮助（help_level>=2）…
   ```
   `docs/m1-design.md` 被静默忽略（exit 0、无警告）；`artifact list --json` 只有 1 项。该文件确实存在，且内容写了“工具结果作为 user 消息回填”。

10. 第 5 次发言（报告 v2 结果）。导师只抓住“最终回答还是 JSON”，建议把回填消息的 `role` 改成 `tool`，然后重跑；该轮 `## 记录` 仍无 `help_level`，且 `动作`（改代码）与 `runtime_next=review` 冲突（见问题 2）。

11. 评审：
    ```powershell
    python "...\runtime\learn.py" review
    ```
    输出摘要（完整见 `.learnark\state\reviews.json`）：

    | dim | weight | threshold | score | note 摘要 |
    | --- | --- | --- | --- | --- |
    | runnability | 30 | 3 | 3 | 第 31–51 行有入口与两处输出；但依赖外部 API 与相对路径，未在干净目录验证 |
    | contract | 30 | 3 | 2 | 第 39–40 行 `json.loads` 后直接取 `args["path"]`，无工具名/类型校验，非法输入不返回结构化错误 |
    | robustness | 20 | 3 | 2 | 第 42 行缺文件、第 43 行非数字均抛未捕获异常；无重试、无步数上限 |
    | explainability | 20 | 2 | 1 | `无 docs/m1-design.md`，工具切分、回填方式、上限 6 均无说明 |

    结论：`加权 2.1｜达阈值=False`；缺口卡 `g-M1-contract`、`g-M1-robustness`、`g-M1-explainability`；下一步 `gap_learn`。评审没有提到“工具结果用 user 消息回填”这个协议选择（coach 后来说了），也把已存在的设计说明判成“无”（见问题 4、7）。

12. 评审后立刻看状态（与保存后的 `status-after-pause.json` 一致）：`open_gaps=3`、`next.action=gap_learn`、`artifacts[0].assisted_level=2`、`start_profile.slice_minutes=60`、`learner_profile.id=P1`。

13. 按提示把 `role` 改成 `tool` 后运行，得到真实错误：
    ```
    HTTP 422 {"error":{"message":"Failed to deserialize the JSON body into the target type: messages[3]: missing field `tool_call_id` at line 1 column 863 (request_id: 8c70a56a-3348-4663-aa81-825eb5fe2031)","type":"invalid_request_error","param":null,"code":"invalid_request_error"}}
    ```
    该提示缺少 `tool_call_id`，照做必然失败（见问题 7）。

14. 第 6 次发言（把 422 原文给导师）。导师这次判断正确：
    > “不是 API 的问题，是你用了 `role: tool` 就必须配 `tool_call_id`，而你这轮是「纯文本 JSON」协议，没有 tool_call 结构。”

    但给出的动作是“改回 `role: user`”，并写“工具已执行，结果=15.0，请用一句话回答用户”。该轮记录 `help_level=3`，`runtime_next=gap_learn`，`动作` 与 `runtime_next` 再次冲突。

15. 按该建议改回 user 后重跑，成功：
    ```
    工具结果：sum_file m1/in.txt = 15.0
    模型最终回答：文件 m1/in.txt 中数字 3、5、7 的和是 15.0。
    ```
    即：在“纯文本 JSON”协议下这套回填能跑通；但它并不是 function calling 的 tool 回填，和导师前一轮的 `role=tool` 说法不一致。

16. 保存并结束：
    ```powershell
    python "...\runtime\learn.py" pause --note "S2 体验结束：…"
    ```
    输出：`已暂停。交接写入 .learnark/handoff/latest.md`；3 个 open gap 原样列出；`下次恢复：start（下一步 gap_learn）`；`git state: no-remote (written=yes, committed=yes, pushed=no)`，明确“真实 GitHub 同步未验证”。

17. 结束状态（`status --json`，已存为证据 `evidence-b-s2p2\status-after-pause.json`）：M1 `status=active`、`artifact_count=1`、`review_count=1`、`open_gaps=3`、`next.action=gap_learn`、`last_session.turns=7`、`handoff from coach to coach reason pause`；`artifacts[0].assisted_level=2`；`start_profile.slice_minutes=60`；`learner_profile.id=P1`。

## 完成情况

- **开始**: 成功。`init` + `start` 两条命令进入 M1，在线导师真实调用（非 mock）。
- **诊断或定位**: 部分成功。导师**没有主动诊断**（开场直接派任务），只有我主动说出 RAG/记忆混淆时才回应，且用“这不是本轮要讨论的内容”带过、未复测；真正的诊断来自我第 3 次发言后它对照代码输出指出“工具请求 ≠ 工具完成”。
- **尝试与反馈**: 成功（做了 4 个版本：v1 不执行、v2 user 回填、v3 role=tool 失败、v4 按建议 workaround 跑通）。反馈有具体命名与行号；但有一次凭空归因、一次 422 提示不完整。
- **保存/恢复**: 保存成功（pause + handoff + 本地 git 提交）；恢复未测试（S2 只要求保存并结束）。
- **切换导师**: 未手动切换；`review` 触发 critic → `review_failed` 自动切回 coach（`.learnark\journal\events.jsonl` seq 27 `mentor_switch`）。
- **作品/评审**: 1 个作品登记，首次评审 4 维中 3 维未达阈值，M1 未通过（20 分钟内符合预期）。

## 预期 vs 实际

| 预期（普通学习者期待） | 实际 | 证据 |
| --- | --- | --- |
| 开场先弄清我会什么、哪里不会 | 直接派 M1 任务；不主动问概念 | `sessions\20261104-025504-coach.md:6-20` |
| 我说“记忆=RAG”时被具体纠正并验证我懂没懂 | 只说“不是一回事，本轮不讨论”，之后未复测 | 同会话 `:22-35` |
| 把“模型给了工具名=调完”当完成时被明确拒绝 | 做到了：`claim_without_artifact` + “请求/执行/回填”三步 | 同会话 `:52-64`；`.learnark\journal\events.jsonl` seq 11 |
| 提示逐级：方向→关键一步→示例 | 内容上确实 L1→L2→L3；但 L3 骨架轮 `help_level` 为空 | 同会话 `:67-84`；events seq 17 |
| “直接给答案”会被守住，且帮助程度被记录 | 没贴完整代码，但给了 4 步近答案；当轮帮助等级未记录 | 同会话 `:70-84` |
| `status` 能看出哪里不会、用过什么帮助 | 能看缺口/分数/`assisted_level=2`；看不到 L3 帮助、看不到 misconception | 证据 `status-after-pause.json` |
| 说 20 分钟就按 20 分钟切片 | `start` 显示 20，`next`/`status` 变 60 | 证据 `status-after-pause.json` 的 `start_profile.slice_minutes=60` |
| 结束后知道下一步做什么 | 评审说 `gap_learn`，导师却让改代码；两处冲突 | 同会话 `:89-95`、`:101-110` |
| 设计说明会作为交付物被评审 | 文件存在但没登记；评审判“无 docs/m1-design.md” | `docs\m1-design.md`；`reviews.json` |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | **重要** | **给 L3 示范时帮助等级未落账**：导师给出 4 步骨架、并说“按受助完成记”，但该轮 `## 记录` 与事件里 `help_level: null`；`assisted_level` 仍为 2。学习者要求答案这一最大帮助无法从状态/作品看出。 | 在任意 `do_task` 轮说“别绕了，直接把答案/代码给我”；随后看 `sessions/*.md` 的 `## 记录`、`events.jsonl` 的 `help_level` 与 `artifact list --json` 的 `assisted_level`。 | `sessions\20261104-025504-coach.md:67-84`；`.learnark\journal\events.jsonl` seq 17（`help_level: null`）；`artifact list --json`（`assisted_level: 2`） |
| 2 | **重要** | **导师动作与 `runtime_next` 冲突**：评审待办时让我改 `role` 重跑（runtime 说 review）；`gap_learn` 时又让我改回 `role:user` 重跑（runtime 说 gap_learn）。学习者不知道先做哪件。 | 登记作品后对导师说“改好了/报错了”，比较回复里的 `动作` 与 `本轮权威动作（runtime_next）`。 | `sessions\20261104-025504-coach.md:89-95`（review vs 改 role）、`:101-110`（gap_learn vs 改回 user） |
| 3 | **重要** | **20 分钟约束丢失**：`start --minutes 20` 当轮显示“20 分钟切片”，但 `start_profile.slice_minutes=60`，之后所有 `runtime_next.minutes=60`、`next` 也给 60 分钟任务。 | `start --minutes 20` 后立刻 `next --json`、`status --json`；看 `minutes`/`slice_minutes`。 | `status-after-pause.json`（`slice_minutes: 60`、`next.minutes: 60`）；events seq 4（minutes 20）对比 seq 7 起（60） |
| 4 | **重要** | **多文件 `artifact add` 静默丢文件**：一条命令传两个交付物，只登记第一个，exit 0 无警告；评审因此判 `explainability` 缺设计说明（实际文件存在）。 | `artifact add m1\agent.py docs\m1-design.md` → `artifact list --json` → `review`。 | `artifact list --json` 仅 1 项；`reviews.json` 的 explainability note“无 docs/m1-design.md”；`docs\m1-design.md` 存在 |
| 5 | 一般 | **凭截断输入断言错误原因**：我的消息被 shell 截成 `{" tool\:`，导师未要求补齐就断言“JSON 是坏的/拼接拼错了”，并把猜测写成 `misconception`。输入端截断是体验者 shell 问题，但导师不应把猜测当事实记录。 | 发送一段明显截断的 JSON 输出，看回复是否先要求完整输入、是否把猜测写入 `misconception`。 | `sessions\20261104-025504-coach.md:38-48`；events seq 10 |
| 6 | 一般 | **学习者身份固定为 P1**：会话说 `learner: P1`、`status.learner_profile.id=P1`，与 P2 场景不符；公开入口没有设置画像的参数。 | `status --json`；看会话头与 `learner_profile`。 | `sessions\20261104-025504-coach.md:3`；`status-after-pause.json` |
| 7 | 一般 | **导师与评审口径不一致/提示不可执行**：导师让把 `role` 改成 `tool` 但没提 `tool_call_id`，照做直接 422；critic 评审又完全没提 role/回填协议，只按类型校验扣分。 | 按导师提示改 `role:tool` 运行（422）；再看 `reviews.json` 是否提该问题（未提）。 | 422 原文（步骤 13）；`reviews.json`；`sessions\...:92`、`:102-104` |
| 8 | 一般 | **runnability 自认未验证却达阈值**：note 写“未在干净目录验证”，但 score=3=threshold，通过依据不满足 rubric 文本“干净目录一条命令跑通真实输入”。 | 看 `reviews.json` 的 runnability note 与 score。 | `.learnark\state\reviews.json` |

## 做得好的地方（避免只记问题）

- `say "我做完了"` 不会通过：运行时显式写 `claim_without_artifact`，导师也说“不算完成”，并给出可执行的三步。
- critic 评审给到**行号级证据**（第 39–40、42、43 行）和三维缺口卡；`next` 按 weight×缺口排序给出 `gap_learn g-M1-contract`，这是清楚的“哪里不会”。
- `pause` 的交接/提交/远程三态真实：`written=yes, committed=yes, pushed=no`，没有假装 GitHub 成功。
- 起点三问标注“不作能力证据”，`self_report` 为空；没有把我“看过视频/说懂了”记成掌握。

## 使用负担

- **师生往返**: 7 次学习者回合（含 `start` 三问），另 1 次 critic 评审；预算 10，未超。
- **命令数**: 15 条 `learn.py` 命令 + 6 次自写 `python m1\agent.py` 运行。
- **需要阅读的文档**: 4 处（任务书、learner-brief、START_HERE、场景卡 personas）。
- **不清楚的地方**:
  1. 评审后到底先 `gap learn` 还是先按导师说的改 `role`？
  2. 两个交付物要分两次 `artifact add` 吗？为什么一次传两个不报错却只收一个？
  3. `--minutes 20` 为什么只在第一条输出生效？
  4. 哪里能看到“导师给过 L3 骨架/我接受过什么帮助”？`status` 只有 `assisted_level=2`。
  5. 为什么评审说没有 `docs/m1-design.md`，而项目里明明有？
- **时间**: 命令与模型调用约 3 分钟（02:54:59–02:58:12），不含我组织答案的时间；若含阅读与写作，超过 20 分钟。

## 说明（不计为产品问题）

PowerShell 向原生命令传参时吞掉了 `say` 文本里的双引号：会话里我的第 2 条消息被截成 `{" tool\:`，第 3 条消息的 JSON 也丢了引号。这是体验者 shell 的传参问题，不是产品行为；我在后续改用不含双引号的措辞重发。报告只在“导师对截断输入的处理”这一点上引用它。

## 结论

- **是否完成场景目标**: **部分完成**。完成了“开始 → 4 个版本的真实尝试 → 具体反馈 → 评审 → 保存”，也验证了“说完成不算”和“行号级扣分”；但 20 分钟切片没有贯穿、L3 帮助没有落账、评审后的下一步指令互相冲突，M1 未通过（1 个作品、3 个 open gap）。
- **最需要修的一件事**: **把每一次导师帮助都可靠落账，尤其是 L3 示范/骨架——写入 `help_level=3` 事件并反映到 `artifact.assisted_level` 与 `status`**。否则“按受助完成记”只是口头承诺，学习者无法从状态看出自己用过什么帮助，S2 的“帮助等级可见”不成立。
- 其次优先：让导师的 `动作` 服从 `runtime_next`（或在冲突时明确以 runtime 为准）；把 `--minutes 20` 持久化到 `start_profile` 与后续 `next`。
