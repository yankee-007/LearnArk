# 体验报告 — direction-c-atelier round-02 S2 诊断与错误反馈

- 版本: 0.2.1（core 1.0.1，schema 1；见 `variants/direction-c-atelier/version-manifest.json`）
- 体验者: 独立子 Agent（DeepSeek Harness · deepseek-flash 模型上下文；独立上下文，非研发者）
- 场景: S2 诊断与错误反馈（P2 阿哲：看过 RAG/Agent 视频、能复述概念、没真正写过）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r02-s2\proj`
- 入口: `python "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-c-atelier\runtime\learn.py"`
- 交互预算: 10 次（本任务）/ 12 次（场景卡上限），实际使用 **9 次 say**
- 时间: 2026-11-04 03:01:52–03:02:58（+08:00），全程真实 API（`offline_last_turn=false`、`synthetic_turns=0`），未用 `--offline`
- 只读了允许的公开材料：`round-02.md`、`evaluation/harness/learner-brief.md`、本方向 `START_HERE.md`、`shared/scenarios/personas.md`、`version-manifest.json`；未读源码/design/mentors/tests/其它 experiments，未改产品

## 实际步骤（命令 + 关键输出摘要）

每条新 PowerShell 先 `. C:\Users\YK\Desktop\LearnArk\_sandbox\env.ps1` 并设 `$env:PYTHONIOENCODING='utf-8'`。
`$LA = "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-c-atelier"`，`$PROJ` 为上述项目目录。

1. **建项目**
   `python "$LA\runtime\learn.py" init --goal "用 Python 做出能调用工具的小 Agent" --template agent-dev --dir $PROJ`
   → `已创建 Atelier 学习项目… 模板：Agent 开发 · 四周最小闭环（agent-dev）· 计划 plan-v1 v1（10 步）`，退出码 0。

2. **开始**（新进程，`cd $PROJ`）
   `python "$LA\runtime\learn.py" start --minutes 20`
   → `进度 0/10`；`这一轮该找谁：策划导师 planner`；给出 3 道诊断题 probe-d1（工具调用失败先看什么）/ d2（检索与记忆差在哪）/ d3（凭什么说改好了），均注明「诊断题，不提供参考答案」。

3. **第 1 轮 say（诊断作答，含故意错误）**
   `say "三个都能答。probe-d1：工具调用失败第一步先看 temperature…probe-d2：检索和记忆其实就是一回事，把文档存进向量库就算有记忆了…probe-d3：能跑通、不报错就算改好了。"`
   → planner 回复：`这三条里有两处是需要先纠正的误解，但纠正它们不是我今天的活`；点名 d1 归因 temperature、d3「不报错=改好」、d2「向量库=记忆」不完整；**但不解释**，转去问周时长；`本轮记录：帮助等级：独立完成`。
   同时有一句正面表现：`你自评「都熟」，但证据是 0 条`——没有把自述当掌握。

4. **第 2 轮 say（回答时长）**
   `say "12 小时是名义值，实际工作日每天能挤 20 分钟…今天我就只有 20 分钟"` → planner 重排第 1 周（plan v2），要求写「模型→工具→观察→再决策」四句。

5. **第 3 轮 say（第一次尝试，含错误）**
   `say "…模型→工具：在 prompt 里把工具列表写清楚，模型就会自动调用，不需要我解析和回传结果。工具→观察：工具返回的内容就当成用户消息再发给模型…"`
   → planner：`其中「模型会自动调用，不需要我解析和回传结果」这句把关键环节省掉了`，`判定与修改建议归 coach 和 examiner，我不替他们讲`；记录仍为「独立完成」。**指出了错句，但没有纠正/讲解，也没有触发交接。**

6. **第 4 轮 say（伪代码尝试，含同一类错误）**
   `say "def run(question): … if reply.has_tool: result = call(...); return llm(result)   # 把工具结果当用户消息再问一次 …"`
   → planner：`你的 run 只回传一次工具结果就返回，没有回到「再决策」…这是四步里第四步缺失`；并把计划验收标准改为「至少两次工具调用」（plan v4）。同样不教、不判。

7. **第 5 轮 say（要求换 coach）**
   `say "行，那这步我该怎么补？你让 coach 来带我吧，我需要有人给我点具体的。"`
   → 自动交接：`已切换到 练习导师 coach（交接单 H-0001 已保存）`。coach 给出**一级提示**（按「谁在决策/依据什么/做什么/结果去哪」各写一句，≤25 字，不许出现 `def`、`prompt`），要求我写四句；同时出现
   `! 机器块无效，本轮按“无证据”处理（missing learn-update machine block）`、`帮助等级：未标注`。
   coach 还问「上次那个报错还在吗？」——此前**没有任何报错**（幻觉前情）。

8. **第 6 轮 say（要求直接给答案/代码）**
   `say "别绕了，直接把答案/代码给我吧。我照着抄一遍就会了，提示我看了但没时间自己推。"`
   → coach 守住边界：`答案我不给，给了你抄一遍也不会变成你的…我最多给到分步引导，通过与否也不由我判`，并把任务缩到「只写第一句」。**拒绝得好**，但本轮再次 `机器块无效 → 帮助等级：未标注`。

9. **第 7 轮 say（第二次尝试，四句）**
   `say "1) 谁在决策：模型在决策。2) 决策依据什么：依据 prompt 里写清楚的工具列表。3) 决策后做什么：需要工具就调用工具。4) 结果去哪：工具结果当成用户消息再喂回模型。"`
   → coach：`四句都在点上，尤其第 4 句「当成用户消息再喂回模型」——这正是 Agent 和单次问答的分水岭，你抓住了`；只把第 2 句改宽为「依据对话上下文和可用工具」。
   `本轮记录：帮助等级：小提示 ｜ 尝试：w1-agent-loop（对）`，`能力记录：w1-agent-loop 现在为 1 级（来源 observed）`，并出现 `安全拦截：本轮有一项越界请求被拒绝（已记录，未改状态）`。

10. **第 8 轮 say（改写第 2 句 + 问记忆）**
    `say "第 2 句改成：决策依据对话上下文和可用工具。另外确认…Agent 的记忆就是 RAG 检索吧？把文档存进向量库就算有记忆了…"`
    → coach 这次**具体纠正**：`RAG 是「按需检索外部文档」，记忆是「保留这次会话里已经发生的状态」…把文档塞进向量库，模型下次仍不知道上一轮调了什么工具`，但补一句「归 concept 讲，我不展开」；要求回答四句里哪句对应记忆。本轮又是 `机器块无效 → 帮助等级：未标注`。

11. **第 9 轮 say（回答哪句是记忆）**
    `say "第 4 句吧——工具结果喂回模型，模型不就等于记住了吗？"`
    → coach：`对，就是第 4 句…你指对了`；`帮助等级：小提示`；`能力记录：w1-agent-loop 现在为 2 级（来源 observed）`；再次打印 `安全拦截…`。随后宣告收工，`等 examiner 用独立题验`。

12. **看状态**
    `python "$LA\runtime\learn.py" status --json`（另跑了一次无 `--json` 的可读版）
    → `capability.nodes`: `w1-agent-loop level=2「受助接触」evidence=2`；`w2-tools / w3-memory / w4-eval` 全 `level=0、evidence=0`、`last_fail=null`；`plan.steps_done=0`；`pending_exam=null`；`current_mentor=coach`；`next.mentor=concept`。
    可读版：`循环与边界：受助接触（证据 2 条）`、`状态与记忆：未验证（证据 0 条）`、`进度 0/10`。

13. **保存结束**
    `python "$LA\runtime\learn.py" pause --note "今天 20 分钟到了，四要素我先背下来，但循环代码还没自己写出来"`
    → `已保存：.learnark\handoff\20261104T030258-coach-to-coach.md`；`交接：H-0002`；`git state: no-remote (written=yes, committed=yes, pushed=no)`，并明确提示无 remote。

14. **新进程恢复**
    `python "$LA\runtime\learn.py" start --minutes 20`
    → `plan-v1 v4 · 进度 0/10`；`上次停在哪：H-0002 coach→coach（just now） · 未决 1 条`；`这一轮该找谁：概念导师 concept`。恢复可用。

## 完成情况

- 开始: **成功**（init/start 各一次，退出码 0，输出明确）
- 诊断或定位: **部分成功**——3 道诊断题都答了，planner 点出了 3 处问题且坚持「自述≠证据」；但没有给出解释或更正，也没自动转交，需要学员自己说「让 coach 来」
- 尝试与反馈: **部分成功**——3 次真实尝试（四步叙述、伪代码、四要素复述）；coach 给了 1 级提示并拒抄答案；但**关键错误被判为「对」并升级能力**（见问题 1），第二次反馈反而强化了错误
- 保存/恢复: **成功**（pause 写 H-0002 + 本地提交；新进程 start 恢复计划/交接/未决）
- 切换导师: **成功**（点名 coach → 自动写 H-0001，上下文按交接单续接）
- 帮助等级: **部分可见**——2 个回合记到「小提示」，3 个回合因机器块缺失为「未标注」，planner 4 回合全是「独立完成」；`status` 看不到「用过哪级帮助」，只看到证据条数

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 说错「工具结果=用户消息」时被指出 | 被夸成「这正是 Agent 和单次问答的分水岭，你抓住了」，记为 correct | `proj/sessions/20261104-030221-coach.md` 第 60、66 行；`journal/events.jsonl` seq 38 |
| 诊断能区分「听过」和「会做」 | 做到了一半：`你自评「都熟」，但证据是 0 条`；但把「能说四句」当成已通过，能力升到 2 级 | `sessions/20261104-030152-planner.md` 第 13–24 行；`capability.json` 第 5–31 行 |
| 帮助等级会记录，status 能看出用了什么帮助 | 9 个回合里 3 个 `help_level=None`（含「直接把答案给我」那轮），status 只显示「证据 2 条」 | `sessions/20261104-030221-coach.md` 第 22、42、86 行；`status` 输出 |
| status 能看出「哪里不会」 | 「状态与记忆」仍是 `未验证 / 证据 0 条`，RAG≠记忆的误解没有落到任何节点或 `last_fail` | `capability.json` 第 33–41 行；`status` 输出 |
| 每轮有可核对的证据 | 能力证据写的 `artifacts/w1-agent-loop.md` 不存在，`artifacts/` 为空 | `capability.json` 第 13、22 行；目录列表 |
| 下一步明确 | coach 说「等 examiner 用独立题验」，但 `pending_exam=null`；`status/start` 让 `switch concept` | `status --json` 的 `capability.pending_exam`、`next`；`sessions/…coach.md` 第 101 行 |
| 提示逐级 | 只观察到一级（方向型）提示，之后直接收窄任务；因预算内我照做，未看到二/三级 | `sessions/20261104-030221-coach.md` 第 17、37 行 |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | 重要 | **明确的概念错误被判为正确并写入能力证据。** 我把「工具结果当成用户消息再喂回模型」当答案，coach 回「四句都在点上…你抓住了」，`attempt correct=True`，`w1-agent-loop` 从 0→1→2 级（受助接触，2 条证据）。S2 的核心目的（看出我不会）在这里失效，且错误被强化 | `say` 第 7、9 轮按上述原话作答；看 `status` 的「受助接触（证据 2 条）」 | `proj/sessions/20261104-030221-coach.md` 第 58–68、97–109 行；`proj/.learnark/state/capability.json` 第 5–31 行；`proj/.learnark/journal/events.jsonl` seq 38、39、49、50 |
| 2 | 重要 | **3/9 回合机器块缺失，帮助等级与尝试未记录。** 其中恰好包含「别绕了，直接给答案」这一关键回合；运行时只打印一行 `! 机器块无效`，无重试/兜底，`status` 无法反映这些回合用过帮助 | 连续 `say` 三轮（换 coach 后第 1、2、4 轮）；观察 `帮助等级：未标注` 与 session 里 `help_level: None` | `journal/events.jsonl` 中 `mentor_update_invalid`：seq 29、33、44；`sessions/20261104-030221-coach.md` 第 22、42、86 行 |
| 3 | 重要 | **`status` 看不出「哪里不会」。** `w3-memory` 始终 `未验证/证据 0`，`last_fail` 全为 null；RAG=记忆这个被 coach 亲口纠正的误解，没有成为任何节点的失败证据或待复习项。可读 status 只有「受助接触（证据 2 条）」 | `status --json`；对照第 8 轮纠正内容 | `capability.json` 第 33–41 行；`proj/sessions/20261104-030221-coach.md` 第 81 行；`status` 输出 |
| 4 | 一般 | **能力证据指向不存在的产物。** 两条 evidence 的 `artifact` 都是 `artifacts/w1-agent-loop.md`，但 `artifacts/` 目录为空，全项目搜不到该文件；「证据 2 条」无法核验 | 看 `capability.json`；`Get-ChildItem $PROJ\artifacts -Recurse` | `capability.json` 第 13、22 行；`proj/artifacts/`（空） |
| 5 | 重要 | **下一步冲突。** coach 说「四句已提交，等 examiner 用独立题验」，但 `pending_exam=null`，没有生成考试；`status`/`start` 又让 `switch concept`。学员不知道该等还是该找 concept，20 分钟结束时没有明确可执行的下一步 | 第 9 轮 say 后看 `status --json`；再 `start` | `status --json` 的 `capability.pending_exam: null`、`next.command: learn.cmd switch concept`；`sessions/20261104-030221-coach.md` 第 101、108 行 |
| 6 | 一般 | **「安全拦截」提示归因不清。** 该行实际由 coach 在机器块里请求 `mastery_delta` 触发（`authority_violation`），却出现在我催答案之后的第 7、9 轮里，容易被学员读成「我的请求被拦」，也看不出被拦的是导师越权 | 第 7、9 轮 say 后观察 CLI 该行；对照 journal 事件 | `journal/events.jsonl` seq 37、48（`kind=mastery_delta_requested`）；CLI 第 7、9 轮输出末行 |
| 7 | 一般 | **交接单 `what_tried` 被截断。** H-0002 只有 5 条，且第 4 条丢正文（`…Agen…`），`handoff_truncated fields=["what_tried"]`；跨导师续接会丢细节（例如我错在「工具结果=用户消息」的原话） | `pause` 后看 `latest.md` 与 journal | `journal/events.jsonl` seq 52；`proj/.learnark/handoff/latest.md` 第 17–22 行 |
| 8 | 一般 | **新导师脑补前情且与事实相反。** coach 一上来称「你上一轮已经写出四步循环伪代码」（planner 刚说缺第四步循环），并问「上次那个报错还在吗？」——全程没有报错。交接只给片段，模型自行补全，造成前后判断不一致 | 第 5 轮 say 后读 coach 首轮 | `sessions/20261104-030221-coach.md` 第 15、19 行；`sessions/20261104-030152-planner.md` 第 84 行 |
| 9 | 一般 | **诊断结论不触发交接，学员要自己点名导师。** planner 连续 4 轮「指出但不纠正、不判」，d1（temperature）/d3（不报错=改好）到结束都没人解释；第 5 轮我说「让 coach 来」才切换，9 轮预算里前 4 轮没有拿到一条更正 | 前 4 轮均用 `say`；观察 planner 每轮以「归 coach/examiner」结束 | `sessions/20261104-030152-planner.md` 第 13–24、33–42、55–64、75–84 行；`journal/events.jsonl` seq 23（H-0001，why=用户点名） |

## 使用负担

- 师生往返: **9 次**（预算 10）；产品命令: **15 条**（init 1、start 1、say 9、status 2、pause 1、恢复 start 1）
- 需要阅读的文档: **4 处**（场景卡、learner-brief、START_HERE、personas 模板）+ 自动注入的 `AGENTS.md`；读数约 350 行
- 实际耗时: 约 4 分钟（9 次真实 API 往返，每次约 4–8 秒）
- 不清楚的地方:
  - 「第 4 句」到底算对还是错：coach 先说「你抓住了」，随后又补「喂回去的是会话内的东西，会话结束就没了」；我离开时仍不确定「当用户消息」这个说法是否要改
  - 结束时该等 examiner 还是 `switch concept`（`pending_exam` 为空，提示互相矛盾）
  - `status` 里的「受助接触（证据 2 条）」到底证明我会了什么；点不开证据，产物文件不存在
  - 「安全拦截」拦的是我、还是导师；连续两轮重复出现，像是遗留状态
  - 「帮助等级：未标注」是没记录，还是记为零；如果是没记录，那一轮算不算数
  - d1/d3 两处被点名的错误，全程没人解释，是否已经被系统记住

## 结论

- **是否完成场景目标: 否（部分完成）。** 流程闭环走通了（开始→诊断→三次尝试→反馈→保存→新进程恢复），而且有两处做得比预期好：planner 明确「自述不算证据」；coach 拒绝直接给答案/代码并守住「不能代替你完成」。但 S2 要验证的「它能不能看出我不会」**只完成一半**：它看出了 3 处疑点，却把我最关键的错误（工具结果当用户消息）判成正确、写进能力证据并升级到 2 级；同时 3 个回合丢失帮助等级，`status` 也看不出「哪里不会」。9 次往返结束时，我没有拿到可运行的小 Agent，也不确定下一步找谁。
- **最需要修的一件事:** 把「尝试正确 / 能力升级」从导师机器块的自评改为**必须经 examiner 独立核验**（或至少在 `correct=true` 时强制记录被纠正的具体错误点）；否则像本轮这样，一个被场景卡定义为典型误解的答案，会以「受助接触 2 条证据」的形式被永久记成进展。

## 证据索引

- 计划/项目: `proj/.learnark/state/studio.json`（plan v4）、`proj/.learnark/project.json`
- 会话原文: `proj/sessions/20261104-030152-planner.md`（4 轮）、`proj/sessions/20261104-030221-coach.md`（5 轮）
- 能力证据: `proj/.learnark/state/capability.json`（w1 level=2、2 条 evidence、w3 空）
- 事件流: `proj/.learnark/journal/events.jsonl`（seq 29/33/44 `mentor_update_invalid`；37/48 `authority_violation`；38/49 `attempt correct=true`；52 `handoff_truncated`）
- 交接: `proj/.learnark/handoff/20261104T030221-planner-to-coach.md`、`20261104T030258-coach-to-coach.md`、`latest.md`
- 同步: `pause` 输出 `written=yes committed=yes pushed=no`（无 remote）
- 说明: 本报告不含推测结论；除「学员离开时仍不确定」这类主观陈述外，所有判断都能对应到上述文件或命令输出。
