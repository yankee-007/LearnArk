# 体验报告 — direction-a-skillmap(SkillMap) round-03 S3（导师切换与中断恢复）

- 版本: SkillMap v0.2.2（core 1.0.1 / schema 1，见 `START_HERE.md` 与 `status --json` 的 `core_version`）
- 体验者: 独立子 Agent（DeepSeek Harness 会话，deepseek-flash 上下文；非研发者，未参与该方向开发）
- 场景: S3（P3 Mia：两周前学过一点 function calling，只记得“模型会返回工具调用”，细节忘了；今天两段各 10 分钟，不想从头学）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r03-s3\proj`
- 入口/命令: `python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-a-skillmap\runtime\learn.py <cmd>`（在项目目录内运行，靠向上查找 `.learnark/` 自动发现项目）
- 交互预算: 10 次；**实际 8 次**（第一段 5 次，第二段 3 次）
- 真实性: 全程真实 LLM（两个会话头都是 `offline: false`，无 `[离线脚本导师]`，未用 `--offline`）；密钥来自 `_sandbox\env.ps1`
- 读过的材料（仅公开）: `evaluation\prompts\round-03.md`、`evaluation\harness\learner-brief.md`、`variants\direction-a-skillmap\START_HERE.md`、`shared\scenarios\personas.md`（只取报告模板）；项目内 `AGENTS.md` 由产品自动注入。未读源码/design/mentors/tests/experiments。

---

## 1. 实际步骤（命令 + 关键输出摘要）

两次会话的每个命令都在**独立的 PowerShell 进程**里执行（harness 每次调用即新进程）；第二段开始时显式确认 `LEARNARK_PROJECT=''`、`PID=35612`，只 `cd` 到项目目录后 `start`，不带 `--project`。

### 第一段（03:12:13–03:13:54，实际墙钟 98 秒）

1. **建项目**
   ```
   python ...\runtime\learn.py init --goal "能用 Python 做出能调用工具的小 Agent" --template agent-dev --dir ...\r03-s3\proj
   ```
   → `SkillMap 项目…模板：agent-dev（12 个节点，诊断 5 题）…git init`，exit 0。
   （证据：`evidence\01-init.txt`）

2. **start（预算 10 分钟）**
   ```
   python ...\learn.py start --project ...\proj --minutes 10
   ```
   → 导航导师开场：“先做一次诊断，一共 5 题，大约 6 分钟，可以跳过” + 第 1 题（锚点 B1）。
   （证据：`evidence\02-start1.txt`）

3. **say ×5：诊断 Q1–Q5（P3 的真实作答，不是编的）**
   | 题 | 锚点 | 我的回答要点 | 判定 |
   | --- | --- | --- | --- |
   | Q1 | B1 | 模型返回“函数名+参数”，代码执行后把结果发回；但回传结构与 `id` 配对记不清 | L1，正确 |
   | Q2 | C2 | `i += 0` 导致 `i` 恒 0、条件恒真；改步长或按 `done` 退出 | L1，正确 |
   | Q3 | D2 | RAG=外部检索，记忆=上下文历史；各自失效场景 | L1，正确 |
   | Q4 | A2 | `ConnectTimeout`/`ReadTimeout` 分层、只对超时+5xx 退避重试、非幂等 POST 谨慎 | L1，正确 |
   | Q5 | E1 | 手写用例 + 调用/参数/结果三层判定 + 批量跑通过率 | L1，正确 |

   每答一题我都在新进程里用 stdin 贴真实答案（`Get-Content answer-0N.txt -Raw -Encoding UTF8 | python ...\learn.py say -`），避免 PowerShell 5.1 吞引号。
   （证据：`evidence\04-say1.txt` … `08-say5.txt`，答案原文 `evidence\answer-01..05.txt`）

4. **诊断收尾**（Q5 的回答里）
   → “诊断结束…**定位：B1 由探针 Q1 判定 L1，先修 A2 L1 已就绪 → 跳过讲解与操练，直接从 apply 开始**”；随后只给“今日任务”元信息：节点 B1、阶段 apply、导师操练导师、活动 B1-apply、**预计 20 分钟（本次预算 10 分钟）**、下一步“继续 B1 的应用，约 20 分钟”。
   **注意：这里没有任何题目正文**；导师原文是“下一轮运行时会给你的具体起点和任务”。
   （证据：`evidence\08-say5.txt`）

5. **status（看它在哪、下一步）**
   ```
   python ...\learn.py status --project ...\proj
   ```
   → `当前：B1 消息结构与角色 · apply（B1-apply） · 导师 coach`；`等级：L0 7 · L1 5`；`帮助：…独立通过 0 次`；`最近等级变化：E1 L0 → L1（独立通过）`；`下一步：继续 B1 的应用（B1-apply），约 20 分钟`；`同步：dirty`。
   （证据：`evidence\09-status-before-pause.txt`、`09b-status-before-pause.json`）

6. **结束第一段（pause）**
   ```
   python ...\learn.py pause --note "上午只有十分钟，做完诊断先到这里，晚上继续" --project ...\proj
   ```
   → `已收工。交接已写入 .learnark/handoff/latest.md`；停在 B1·apply；未决“B1 的应用阶段未收口”；`git … committed: yes (sha 99b6caf)`；`pushed: no`（无远程）。
   （证据：`evidence\10-pause1.txt`）

   第一段交接原文（`handoff/latest.md`）摘要：
   - from coach / to coach，`what_tried: 本会话 6 轮对话`，`unresolved: B1 的应用阶段未收口`，`next: 继续 B1 的应用（B1-apply），约 20 分钟`
   （证据：journal 事件 seq 31，副本 `evidence\20-handoff1-from-journal.json`）

### 第二段（**新 PowerShell 进程**，03:14:04–03:15:19，墙钟 75 秒）

7. **新进程直接 start，不带 `--project`**
   ```
   cd ...\proj
   python ...\runtime\learn.py start --minutes 10
   ```
   → 开头“晚上好，接着上午的诊断往下走。**今天二十分钟**，目标就一个：交出一个能跑的 `build_messages.py`”，随后给出**完整题目**（两条消息 role=system/user；system 只放稳定规则；user 只放本次数据；`ensure_ascii=False` 打印），最后一行才是“上次停在 B1 的应用（诊断定位起点），**还没有产生 attempt**；今天续做 B1-apply，约 20 分钟”。
   （证据：`evidence\11-start2-resume.txt`）

8. **写产物并真实运行**（写在 `proj\artifacts\build_messages.py`；第一版故意保留 P3 的真实错误：把“明天下午三点开会”这句本次数据混进 system，且 `json.dumps` 没加 `ensure_ascii=False`）
   ```
   python artifacts\build_messages.py
   ```
   → 输出是 `\u4f60\u662f…` 转义（中文没直出）。sha256=`7C7963FE…7FEC0B`。
   （证据：`evidence\12-artifact-run.txt`）

9. **提交尝试**（第 6 次往返）：把代码 + 真实输出贴回。
   → 导师只点一个错：“**system 里混进了本次的数据**……换一句话 system 就得跟着改，那它就不是规则了”，并追问三问；记录 `本次未通过：B1-apply / 提示等级：1`。
   （证据：`evidence\13-say6-apply1.txt`）

10. **回答三问**（第 7 次往返）→ “三个问题都答对了，而且第 3 问点到了要害”；要求改 `system_text`/`user_text` + 加 `ensure_ascii=False` 后重跑贴输出；仍未通过（`attempt` 事件 correct=false）。
    （证据：`evidence\14-say7-answers.txt`）

11. **换导师（先试错）**
    ```
    python ...\learn.py switch concept
    ```
    → 拒绝：“不能切到 concept：当前阶段是 apply（应用），只允许 navigator, coach。”（PowerShell 把它渲染成红色 `NativeCommandError`，显示 `[exit code: 1]`；`START_HERE.md` 写门控退出码 2，未单独读到产品真实退出码）
    （证据：`evidence\15-switch-concept-console.txt`）

    ```
    python ...\learn.py switch navigator
    ```
    → 成功，exit 0。导航导师先复述交接：“节点 B1…阶段 apply…当前 L1/目标 L3；已做 `artifacts/build_messages.py` 能跑通、role 结构正确；错因：把本次数据写进 system…；未收口：改完的版本还没跑、没贴输出”，再给同样的下一步（改两处 + `ensure_ascii=False` + 重跑），并承诺“改完这一版，我给你一道变式题收口”。
    （证据：`evidence\16-switch-navigator.txt`）

12. **与切换后的导师交流**（第 8 次往返）：说明“今晚只剩几分钟，明天会不会重新诊断/重讲”。
    → “不用重新诊断，也不用重讲 B1……明天打开就是接着走 B1 应用这一步，具体动作只有一个：改 `system_text` 和 `user_text` 两处……跑一次贴输出。然后我做一道变式题收口”；本轮明确“没有作答，只记录对话，不产生能力证据”。
    （证据：`evidence\17-say8-navigator.txt`）

13. **status（切换后）**
    → `当前：B1…apply（B1-apply） · 导师 navigator`；`等级：L0 7 · L1 5`；`薄弱` 多出“B1：把本次数据写进 system，规则与数据未分离”；`上次交接：coach → navigator（…原因：学习者要求切换到 navigator）`；`下一步：继续 B1 的应用（B1-apply），约 20 分钟`。
    （证据：`evidence\18-status-after-switch.txt`、`18b-status-after-switch.json`）

14. **再结束一次（pause）**
    ```
    python ...\learn.py pause --note "晚上也只有十分钟，代码没改完，明天从修改 build_messages.py 接着来"
    ```
    → 停在 B1·apply；未决两条：“B1 未澄清的错因：把本次数据写进 system…”与“B1 的应用阶段未收口”；`committed: yes (sha 72240a8)`；`pushed: no`。
    （证据：`evidence\19-pause2.txt`、终版交接 `proj\.learnark\handoff\latest.md`（副本 `evidence\21-handoff2-final.md`））

15. **只读复核 status**（收工后，不消耗往返）
    → `当前…导师 navigator`；`上次交接：navigator → coach`；`同步：clean`。
    （证据：`evidence\22-status-final.txt`、`22b-status-final.json`）

---

## 2. 会话与交接证据

| 内容 | 路径 |
| --- | --- |
| 第一段会话 | `...\proj\sessions\20261104-031216-navigator.md` |
| 第二段会话 | `...\proj\sessions\20261104-031404-coach.md` |
| 终版交接 | `...\proj\.learnark\handoff\latest.md`（副本 `evidence\21-handoff2-final.md`） |
| 第一段交接 | journal `events.jsonl` seq 31（副本 `evidence\20-handoff1-from-journal.json`） |
| 切换事件/交接 | journal seq 43；`evidence\16-switch-navigator.txt` |
| 全部控制台输出 | `...\_sandbox\projects\a\r03-s3\evidence\`（01–22，含每题答案原文） |

### 切换前后 status 摘要

| 时点 | 节点/阶段 | 导师 | 等级 | 上次交接 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| 第一段结束（pause 后） | B1 / apply | coach | L0 7 · L1 5 · L2 0 | —（首次交接 coach→coach） | 继续 B1 应用，约 20 分钟 |
| 切换前（会话 2 内，coach 最后一条之后） | B1 / apply | coach | L1×5 | — | 改 system/user + `ensure_ascii=False` 后重跑（来自 say7 输出与 `plan.json` 的 `session_mentor=coach`） |
| 切换后（`18`） | B1 / apply | navigator | L1×5 | coach → navigator（03:14:57） | 继续 B1 应用，约 20 分钟 |
| 第二段结束（`22`） | B1 / apply | navigator | L1×5 | navigator → coach（03:15:19） | 继续 B1 应用，约 20 分钟 |

---

## 3. 完成情况

- **开始**: 成功（`init` + `start` 一次到位，无需研发者指导）
- **诊断或定位**: 成功（5/5 判 L1；`placement_applied` 把 B1 直接放到 apply，跳过讲解与操练，符合“不想从头学”）
- **尝试与反馈**: 成功（1 个真实产物 + 真实运行输出；2 次 `attempt` 均 correct=false，错因具体到 system/user 混装，非泛泛表扬）
- **保存/恢复**: 成功（`pause` 写交接并本地提交；**新进程、仅凭项目文件**恢复出“B1 apply、还没产生 attempt”，未重跑诊断、未重讲）
- **切换导师**: 部分成功（concept 被门控拒绝；navigator 切换成功，且**引用交接**逐条复述已做/错因/未收口）
- **是否把未完成说成完成**: 否（L2=0、`apply passed=false`、交接保留两条 unresolved）

---

## 4. 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 新进程 `start` 只说上次停在哪、下一步 | 说对了（B1 apply、还没有产生 attempt、下一步改代码）；但开场先说“接着上午的诊断往下走”，与“诊断已完成、定位到 B1 apply”不符 | `evidence\11-start2-resume.txt` |
| 不重复已学内容 | 没重跑诊断、没重讲 B1，直接给 apply 任务 | 同上 |
| 不把未完成说成完成 | L2=0；`B1-apply` 两次未通过；交接 unresolved 两条 | `19-pause2.txt`、`21-handoff2-final.md` |
| 切换有交接记录，新导师引用它 | 有 `handoff/latest.md` + journal 事件；导航导师开头逐条复述节点/阶段/已做/错因/未收口 | `16-switch-navigator.txt` |
| 两位导师对“下一步”说法一致 | 一致：改 `system_text`/`user_text`、加 `ensure_ascii=False`、重跑贴输出，之后一道变式题收口 | `14-say7-answers.txt`、`16-switch-navigator.txt`、`17-say8-navigator.txt` |
| 10 分钟能推进一个阶段 | 第一段 5 次往返全花在诊断；第二段只完成 1 次提交 + 1 次切换确认。10 分钟预算实际没有约束住任何东西 | `02…08`、`11`、`project.json constraints.short_session_minutes=20` |
| 能换到“讲概念”的导师（我忘了细节，想要 concept） | 被拒；apply 阶段只允许 navigator/coach，且可用值只能从报错里知道 | `15-switch-concept-console.txt` |

---

## 5. 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | **重要** | **10 分钟预算与产品时长模型冲突**：`start --minutes 10` 后导师开口“今天二十分钟”，任务卡同时写“预计：20 分钟（本次预算 10 分钟）”；项目模板 `constraints.short_session_minutes=20`。P3 只有 10 分钟，不知道该按哪个时间收工，也看不出“一个阶段”能否在 10 分钟内收口 | `init` 后 `start --minutes 10`，看导师开场与“今日任务”块 | `evidence\11-start2-resume.txt`；`proj\.learnark\project.json`；`evidence\22b-status-final.json`（`minutes_budget:10`） |
| 2 | **重要** | **第一段 10 分钟被 5 题诊断占满，零节点练习**：P3 的“两周前学过、不想从头学”只有 5 题诊断这一条路能换来定位；若跳过诊断（`START_HERE.md` 允许 `diagnose --skip`），诊断前 `status` 给出的 `next` 是 A1 讲解，等于从头学（skip 未实测，属推测）。两段场景下，第一段完全没有产出作品 | 新项目 `start`，选“做诊断”并答完 5 题 | `evidence\02…08`；`09b-status-before-pause.json` |
| 3 | **重要** | **切换导师不可发现且被阶段锁死**：想换 concept（讲概念）被拒，只允许 navigator/coach；`status` 只显示当前导师，公开命令里没有 `studio`/`plan` 之类可列可选值，只能试错。P3 的真实需要（“细节忘了，想听人再讲一遍”）恰好落在被禁止的那个角色上 | 在 B1 apply 阶段执行 `switch concept` | `evidence\15-switch-concept-console.txt`；`16-switch-navigator.txt` |
| 4 | **重要** | **“下一个导师是谁”三个来源不一致**：`status` 当前导师=navigator；`handoff` 写 `navigator → coach`；`plan.json` 里 `mentor_override=navigator` 而 `session_mentor=coach`；自动生成的 `AGENTS.md` 又说 apply 阶段导师应为 coach。下次 `start` 到底谁接，无法从公开输出确定（本次未做第三段实测，属推测） | 切换 navigator → pause → 看 `status`、`handoff/latest.md`、`plan.json` | `evidence\22-status-final.txt`；`21-handoff2-final.md`；`proj\.learnark\state\plan.json` |
| 5 | 一般 | **`start`/`switch` 被记成“学习者发言”并计入轮次**：会话 1 的 turn 2 是“开始学习”，会话 2 的 turn 5 是“switch navigator”；于是交接写“本会话 6 轮/5 轮”，实际 `say` 只有 5 次/3 次。轮次预算无法从记录核实 | 任意 `start`、`switch` 后看 `sessions\*.md` 与 `handoff` 的 `what_tried` | `sessions\20261104-031216-navigator.md`、`sessions\20261104-031404-coach.md`、`20-handoff1-from-journal.json` |
| 6 | 一般 | **会话记录里导师/阶段归属错位**：会话 1 最后一轮是导航导师的诊断收尾总结，却标成“导师 · 操练导师 · B1-apply”；会话 2 文件名与标题固定为 coach，切换后两轮导航导师仍写在同一文件里。按导师/阶段找记录会找错 | 诊断收尾后看会话 1 末尾；切换后看会话 2 文件名 | 同上两个 `sessions\*.md` 文件 |
| 7 | 一般 | **status 自相矛盾**：“独立通过 0 次”与“最近等级变化 E1 L0 → L1（独立通过）”同屏；5 个 L1 来自诊断，算不算“独立通过”看不出来 | 诊断后执行 `status` | `evidence\09-status-before-pause.txt`、`22-status-final.txt` |
| 8 | 一般 | **恢复开场措辞与事实不符**：“接着上午的诊断往下走”，但诊断已完成并已定位到 B1 apply；紧接着的运行时摘要又写“诊断定位起点、还没有产生 attempt”。恢复瞬间会怀疑它是不是又要诊断 | 新进程 `start` 恢复 | `evidence\11-start2-resume.txt` |
| 9 | 一般 | **诊断收尾只给任务元信息，没有题目正文**：第一段结束时只知道“B1 apply、预计 20 分钟”，不知道要写什么；必须再 `start`（新会话）才拿到题目。第一段若还有几分钟，也没法做 | 答完第 5 题看输出末尾 | `evidence\08-say5.txt` vs `evidence\11-start2-resume.txt` |

**观察（不计为问题）**：
- journal 出现 **7 次 `mentor_update_retried`**（真实 LLM 漏 `learn-update` 机器块后的静默补问），每轮多一次 API 往返；体验上只是慢几秒，结论未受影响。
- 两段实际墙钟只有 98 秒 + 75 秒，远低于 10 分钟预算：10 分钟不是被 LLM 延迟吃掉的，而是被诊断题量和 20 分钟任务设计吃掉的。
- `map_status_drift`（B1 缓存 available → 派生 in_progress）在 journal 反复出现，读时重算，学习者不可见。
- 产物 `artifacts/build_messages.py` 是真实运行过的文件（sha256 `7C7963FE…7FEC0B`）；未通过时 `stage_progress.apply_artifact` 仍为 null，符合“未通过不记 L2”。

---

## 6. 使用负担

- 师生往返: **8 次**（第一段 5，第二段 3；总预算 10）
- 命令数: **23 条产品命令**（1 × init、2 × start、8 × say、2 × pause、2 × switch、7 × status、1 × 产物运行），另加读会话/交接文件
- 需要阅读的文档: **4 处**（round-03 场景卡、learner-brief、START_HERE、personas 模板）+ 项目自动注入的 `AGENTS.md`
- 卡住/需要猜的地方:
  1. apply 阶段能换哪些导师？（`status` 不列，只能被拒一次才知道）
  2. “20 分钟”从哪来？我明明给了 `--minutes 10`
  3. 收工后到底谁接我？`status` 说 navigator，`handoff` 说 coach
  4. “本会话 N 轮”怎么算的？`start`/`switch` 也算我说的话吗？
  5. 诊断结束后我要做什么？题目正文没有，只有“预计 20 分钟”
- 是否需要研发者介入: **不需要**；所有命令一次跑通（唯一失败是 `switch concept`，属产品门控，不是环境问题）

---

## 7. 结论

- **是否完成场景目标: 是（带条件）**。恢复（新进程、只凭项目文件）、切换（有交接且被引用）、保存（交接 + 本地提交）三条主线都成立且可核验；未把未完成说成完成。**未达成的部分**：P3 的“两个 10 分钟碎片”在产品里不成立——第一段被 5 题诊断吃满，任务按 20 分钟排；切换也不能换到想听讲解的 concept。
- **最需要修的一件事**: **让 `--minutes` 真正约束导师开场与任务分配**（要么明确拒绝 <20 分钟的会话并说明“请留 20 分钟”，要么按 10 分钟给一个 5–8 分钟能收口的最小单元），否则 P3 这类“碎片时间 + 两周前学过”的用户，第一段永远只剩诊断。
