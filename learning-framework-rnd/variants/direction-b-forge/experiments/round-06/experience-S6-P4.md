# 体验报告 — direction-b-forge round-06 S6

- 版本: `direction-b-forge 0.2.3`（vendored `learncore 1.0.2`，state `schema_version 1`）
- 体验者: 独立子 Agent / deepseek-flash 上下文（模拟 P4 Tina；非研发者；未读源码/设计/课程/测试/其他方向；只读 round-06 任务卡、learner-brief、START_HERE、personas 模板与产品自身输出）
- 场景: S6 跨主题迁移（P4 Tina，非编程背景运营，目标 = 英文工作邮件写作，20 分钟）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r06-s6\proj`
- 入口: `python "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-b-forge\runtime\learn.py"`（真实 LLM，全程 `offline=false`，model=`deepseek-flash`，未使用 `--offline`）
- 交互预算: 场景卡要求 8 次；实际使用 **4 次学习者输入**（1 次 `say` + `start --ask` 的 3 个定位回答）

## 实际步骤（命令 + 关键输出摘要）

工作目录 `_sandbox\projects\b\r06-s6`，项目用 `--dir proj` 建在其下。

1. **建项目**
   `learn.py init --goal "英文工作邮件写作" --template email --minutes-per-week 2 --dir proj`
   → `已创建：...\proj`｜`目标：英文工作邮件写作｜模板：email｜每周 2 小时`｜`当前里程碑：E1｜下一步：do_task`｜git init 成功。
2. **看状态** `status --json`
   → `template: "email"`，三个里程碑全部是写作主题：`E1 道歉与补救`、`E2 跨部门请求`、`E3 拒绝并保住关系 + 作品集收尾`；rubric 四维 `structure/tone/clarity/scenario_fit`（25/25/20/30，阈值均 3）。**但** `next.slice_hint` 已经是编程措辞：「20 分钟切片：只做能跑的最小版本——一条真实输入 + 一次运行 + 打印结果；失败场景留到下次」。
3. **首次定位** `start --ask`（交互三问）
   → 三问原文：「能否自己跑通一次 DeepSeek API 调用？」「是否做过带工具调用的 Agent？」「这次想要什么？」——**前两问与写作完全无关**。我按提示「回车=1」直接回车，运行时记录
   `起点档案（已记录）：{"api": "能", "tools": "做过", "mode": "二十分钟见到东西"} → M1-first（standard，20 分钟切片…）`。
   （`M1-first` 也是 Agent 开发的里程碑名，出现在 email 项目里。）
   导师随后给的任务是写作：「用英文写一封 120 词以内的道歉邮件——第一句就说清『为什么道歉』，中间一段给补救措施和新的具体日期时间，最后一句写你请对方做什么」。
4. **看任务** `task`
   → 交付物 `artifacts/email/e1-apology.md`；`允许后缀：.py, .md, .json, .txt, .jsonl`；四条 rubric 标准全是写作标准（「主题句在前，一段一件事」「承认责任不辩解，不过度自责」「无 ASAP/尽快 这类无法执行的表述」「延期原因、补救措施、新时间与该客户场景一致」）。截图级证据：写作标准确实替换成功。
5. **交作品 v1**：写 `artifacts/email/e1-apology.md`（真实小邮件，见附录 A），
   `artifact add artifacts/email/e1-apology.md`
   → `已登记：a-E1-cb677a37 path=artifacts/email/E1/e1-apology.md sha256=cb677a37... assisted_level=1`（注意路径多了一层 `E1/`）。
6. **第一次评审** `review`
   → `structure 3 / tone 3 / clarity 2 / scenario_fit 2`，`加权 2.5｜达阈值=False`，开缺口卡 `g-E1-clarity`、`g-E1-scenario_fit`。反馈逐维引行号原文，例如
   `clarity 2：第 9 行「as soon as possible」不可执行，且与同句「Friday 6 November」自相矛盾`；
   `scenario_fit 2：第 7 行原因是「designer needs two more days for the final check」，第 9 行却先发两张 banner，未说明这两张为何已可交付`。
   下一步：`gap_learn（g-E1-scenario_fit）`。
7. **微课** `gap learn g-E1-scenario_fit`
   → 讲解本身正确（「场景一致 = 每个动作都能被原因解释」），**但「最小示例（独立可跑，看输出差异）」是一段 Python**：
   ```python
   def explain(reason, action, bridge):
       print("原因:", reason)
       ...
   explain("终检未完成", "先发两张 banner", "")
   ```
   同一段还写「把 bridge 写成『as soon as possible』——那不是衔接」。
8. **改 v2**：按修改项 1–3 重写（删 ASAP、补「已通过终检」衔接、拆段、主题行给结论），
   `artifact add artifacts/email/e1-apology.md`
   → `已登记：a-E1-9950bddf ... assisted_level=0 取代：a-E1-cb677a37`。
9. **复评** `review`
   → `structure 3 / tone 3 / clarity 3 / scenario_fit 3`，`加权 3.0｜达阈值=True`，
   `本次关闭缺口：g-E1-clarity, g-E1-scenario_fit（复评达标）`。反馈仍逐条引行号（第 3/7/9/11/13 行）。
10. **防御解释** `defend` → 三问是写作题：`e1-q1[scenario_fit] 如果延期是你们自己的排期失误，第一句你会怎么改？`、`e1-q2[tone] 客户回复「不能接受」时，这封信留了什么余地？`、`e1-q3[structure] 新时间放在哪一段，为什么不放开头？`。
    提示行却是 Agent 模板：`say "m1-q1：……（第 38 行）；m1-q2：……（第 27 行）；m1-q3：……（第 41 行）"`（题号是 `m1-`，我的邮件只有 16 行）。
    用 `say -` 按 `e1-q1..q3` 逐题带行号作答 → 导师三问全 ok；`[运行时] defense 3/3 问通过；最重维度 通过；判定：passed`；`里程碑 E1 通过（passed），已激活 E2`；`help_level=1`。
11. **看记录** `status`
    → `里程碑 E2「跨部门请求」 status=active`；`作品：2 件｜最新 a-E1-9950bddf ... assisted_level=0`；`帮助等级：最近 L1（critic）｜最高 L2（guide）`；**`最近评审：无`**（实际 2 次评审）；`上次会话：…（coach，3 轮），进行中`；`下一步：do_task E2`。
    `gap --all` 能看到两张卡 `closed`；`milestones` 能看到 E1 `passed / reviews 2 / weighted 3.0 / defense passed / evidence verified`。
12. **保存** `pause --note "20 分钟到了…"` → `交接写入 .learnark/handoff/latest.md`；`git state: no-remote (written=yes, committed=yes, pushed=no)`。
13. **新进程恢复**（父目录 + `--project proj`，全新 python 进程）`start`
    → `上次停在哪：coach → coach（pause）｜未决：E2…`；`结论：E2 还没有作品，本轮只做这一封`；
    `▶ 唯一动作：do_task — E2「跨部门请求」…写一封不超过 150 词的英文邮件…目的、范围、截止时间、你要对方做的下一步`。
    `next --json` → `"action": "do_task", "milestone": "E2"`。记录与下一步都在，且下一步仍是写作任务。

## 完成情况

- 开始: 成功（`init` + `start`，无格挡）
- 诊断或定位: 成功但**答非所问**——定位三问全是编程题，非编程学习者只能靠回车默认，结果档案被写成 `api=能, tools=做过`
- 尝试与反馈: 成功（v1 提交 → critic 逐行反馈 → 微课 → v2 修改 → 复评四维达标 → defense 3/3）
- 保存/恢复: 成功（`pause` written/committed=yes；新进程 `start` 恢复 E2 与写作下一步）
- 切换导师: 由流程自动切换（coach → critic → guide → coach），无需手写 `switch`；`status` 的「最近交接：critic → coach（defense_passed）」可查

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 换 `--template email` 后课程内容变成写作 | **达成**：三个里程碑、交付物、四条 rubric 全是写作（结构/语气/清晰/场景） | `status --json`、`task` 输出 |
| 反馈针对我的句子，而不是「写得好」 | **达成且超出**：逐维引行号、引原句、给可执行改法（删 ASAP → 给具体时刻；补一句「已通过终检」） | `review` 输出；`.learnark/state/reviews.json` |
| 诊断适配「非编程、零基础写作」 | **失败**：三问是 API 调用/工具调用 Agent；回车默认把学习者记成「能/做过」 | `start --ask` 输出；`status` 的起点档案 |
| 写作练习里不该出现代码 | **失败**：`gap learn` 的最小示例是 Python 函数；每次 `start/task/next/status` 都带「只做能跑的最小版本…一次运行 + 打印结果」 | `sessions/20261104-115946-coach.md` 第 28–40 行；各命令输出 |
| `status` 能看「能力/薄弱/下一步」 | **部分失败**：下一步清楚、`milestones`/`gap --all` 有分数与缺口；但 `status` 正文写「最近评审：无」（实际 2 次），且没有一页「我哪里弱」的汇总 | `status` vs `status --json.reviews.count=2`、`.learnark/state/reviews.json` |
| 记录独立、不与 Agent 开发混在一起 | **基本达成**：能力记录是 E1–E3 邮件里程碑 + 写作四维 + 两张写作缺口卡；混入的是**字段层残留**（`M1-first`、`slice_hint`、`.py` 后缀、`m1-q1` 示例），不是能力项 | `status --json`、`defend` 提示行 |
| 20 分钟内能完成一个小闭环并保存 | **达成**：E1 从 0 到 passed 共 13 步、4 次学习者输入 | 本报告步骤 1–13 |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | 重要（对 P4 接近阻塞） | `gap learn` 的写作微课用 **Python 代码块**当「最小示例（独立可跑，看输出差异）」：`def explain(reason, action, bridge): print(...)`。非编程学习者在这一步读不懂示例，只能靠后面的中文「回到作品」一句硬做 | `init --template email` → 交一封有 scenario_fit 缺口的邮件 → `review` → `gap learn g-E1-scenario_fit` | `_sandbox/projects/b/r06-s6/proj/sessions/20261104-115946-coach.md`（第 28–40 行）；同内容在终端输出 |
| 2 | 重要 | 20 分钟切片提示全程是编程语汇：「只做能跑的最小版本——一条真实输入 + 一次运行 + 打印结果」。它出现在 `start`/`task`/`next`/`status` **每一次**输出，是学习者最常看到的一行 | 任意 email 项目执行 `next --json` 看 `slice_hint`；或 `status` 看「切片：」行 | `status` / `next --json` 输出；`.learnark/state/brief.json` |
| 3 | 重要 | `status` 正文写 **「最近评审：无」**，而实际已有 2 次评审、E1 已 passed、`milestones` 显示 `reviews 2 / weighted 3.0`；`status --json` 的 `reviews.count=2` 但 `reviews.latest=null`（`.learnark/state/reviews.json` 里两条都在）。学习者按场景要求「用 status 看能力/薄弱」时看到的是「无」 | `review` 两次 → `status` → 对比 `milestones` 与 `gap --all` | `_sandbox/projects/b/r06-s6/proj/.learnark/state/reviews.json`；`status` / `status --json` / `milestones` 三份输出 |
| 4 | 重要 | 首次定位三问全部是编程题（DeepSeek API 调用、工具调用 Agent）；回车默认=1，于是一个非编程学习者被记成 `api=能, tools=做过`，且这条档案会显示在每次 `status` 顶部。没有任何一步问「你写作想练什么/写给谁」 | `init --template email` → `start --ask` → 三次回车 → `status` | `start --ask` 输出；`status` 的「起点档案」行；`.learnark/state/session.json` |
| 5 | 一般 | `task` 的「允许后缀：.py, .md, .json, .txt, .jsonl」把 `.py` 列在第一位（email 项目只需要 `.md`） | `task` | `task` 输出 |
| 6 | 一般 | `defend` 的作答格式示例是 Agent 模板：`m1-q1 …（第 38 行）`，而实际题号是 `e1-q1..q3`、我的邮件只有 16 行。照着示例写会得到错题号/不存在的行号 | `defend` | `defend` 输出 |
| 7 | 一般 | 生成的 `README.md` 规则段仍写「按『要答案 + 多步骨架/代码』推断」，email 项目里没有「代码」可给 | `init --template email` 后读 `README.md` | `proj/README.md` 第 36 行 |
| 8 | 一般 | E2 开场导师说「写完把文件存好，回来告诉我**「它现在能做什么、还差什么」**」——指代的是 Agent/程序，对一封邮件不通 | `pause` → 新进程 `start`（E2 已激活） | `start` 输出（新进程，12:01 那次） |
| 9 | 一般 | defense 通过后导师写「三问都答到了具体行号…**不是复述代码**」——写作场景里没有代码可复述 | `defend` → `say -` 作答 | `say -` 输出 |
| 10 | 一般 | 作品 `assisted_level=0`（独立）与 `status` 的「帮助等级：…最高 L2（guide）」并列出现，`status` 不解释「guide 微课不计入 assisted_level」，容易被读成自相矛盾 | 走一次 `gap learn` 再 `artifact add` | `status` 的「作品：…assisted_level=0」与「帮助等级」两行 |
| 11 | 一般 | 交付物路径漂移：`task` 要求 `artifacts/email/e1-apology.md`，`artifact add` 实际落到 `artifacts/email/E1/e1-apology.md`，第二版又变成 `e1-apology-9950bddf.md`。虽然最终通过，但学习者在文件管理器里对不上号 | `task` → `artifact add` → 看 `artifacts/email/` | `task` 输出；`artifacts/email/E1/` |
| 12 | 一般 | critic 有过度推断：v1 第 9 行已写「so your side can check the layout early」，critic 仍判「终检未完成却先发 banner，与场景冲突」。这属于评委主观（START_HERE 已声明无法消除），但会逼学习者为一个并不存在的矛盾改稿 | `review`（v1） | `review` 输出；`.learnark/state/reviews.json` 的 `r-E1-cb677a37` |

**说明**：问题 1/2/5/6/7/8 属于「模板只换了一半」的文本残留——**能力标准、任务、评审都是真写作**，残留集中在导师提示词、切片提示、示例与字段名。

## 使用负担

- 师生往返: **4** 次学习者输入（`say` 1 次 + 定位三问 3 个回答），预算 8；真正的写作对话只有 defense 那 1 轮，其余反馈由 `review` 一次性给出
- 命令数: **20** 次 `learn.py` 调用（其中 1 次失败：`start --help` 返回 `learn: 未知参数 --help`，退出码 2）＋ 2 次文件写入；最小闭环（不含探查）约 9 条
- 需要阅读的文档: 3 处（`START_HERE.md`、生成的 `README.md`、自动注入的 `AGENTS.md`）；普通用户至少 2 处
- 不清楚的地方:
  - 定位三问和「练英文邮件」没有关系，我不知道该选什么，只能回车
  - 为什么写作微课给我一段 Python
  - `artifacts/email/e1-apology.md` 被复制到 `artifacts/email/E1/`，下次该改哪个文件
  - `status` 说「最近评审：无」，可我刚评过两次
  - `assisted_level=0` 与「最高 L2」到底哪个算我的水平
  - 没有一页告诉我「已会什么/还差什么」，得自己拼 `milestones` + `gap --all`

## 结论

- **是否完成场景目标: 是**。`--template email` 建项目成功；任务是写作、rubric 是写作、critic 反馈逐行针对我的英文句子、`gap learn` 推进的是写作缺口、defense 三问是写作三问；E1 通过，`pause` 保存，新进程 `start` 恢复后下一步仍是写作（E2「跨部门请求」，≤150 词，要求目的/范围/截止/下一步）。能力记录在 E1–E3 邮件里程碑里，与 Agent 开发的能力项没有混在一起。
- **最需要修的一件事**: 把 email 模板的**导师提示词与微课载体**整体换成写作语汇——尤其 `gap learn` 的 Python「最小示例」和每次输出都出现的「能跑的最小版本…一次运行 + 打印结果」。这是学习者最需要帮助的那一刻唯一破功的地方：主题换了，教法还在讲代码。
- 次要但影响信任: 修 `status` 的「最近评审：无」（`reviews.latest` 在 JSON 里就是 `null`），并给写作学习者一个「能力/薄弱」汇总视图；否则场景要求的那一步「用 status 看记录」等于看不到。

---

## 附录 A · 两版邮件（原文）

### v1（`a-E1-cb677a37`，645 bytes，正文 113 词）

```
Subject: About the launch files

Hi Chen,

I am sorry that the launch files will be late. Our designer needs two more days for the final check, so we cannot send the complete set on Thursday 5 November.

We will send the complete set on Monday 9 November before 5 pm. To help your team, I will send you the two key banners on Friday 6 November as soon as possible, so your side can check the layout early. If the layout needs a change, we can fix it on Monday morning.

I am sorry again for this trouble. Please tell me if Monday 9 November at 5 pm still works for your launch plan.

Best regards,
Tina
```

### v2（`a-E1-9950bddf`，745 bytes，正文 118 词，四维达标）

```
Subject: Two-day delay to your launch files — new date 9 November

Hi Chen,

I am sorry that the launch files will be two days late. Our designer needs two more days for the final check, so we cannot send the complete set on Thursday 5 November.

The two key banners have already passed that check, so I will send them to you by 12 pm on Friday 6 November.

Please send me your layout comments by Monday 9 November at 10 am, and I will send the revised banners back the same day. The complete set will follow by 5 pm on Monday 9 November.

Thank you for your patience. Please tell me if Monday 9 November at 5 pm still works for your launch plan.

Best regards,
Tina
```

（文件顶部各有一行我自己的中文小标题，critic 引用的行号即按含标题行的整文件计算：v1 第 7/9/11 行，v2 第 3/7/9/11/13 行。）

## 附录 B · 导师反馈摘要

**v1 critic（`r-E1-cb677a37`，加权 2.5）**

| dim | 分 | 反馈要点（原文摘录） |
| --- | --- | --- |
| structure | 3 | 第 7 行主题句在前；但第 9 行一段塞了两件事（发 banner + 改版式），「一段一件事」未完全做到 |
| tone | 3 | 第 7 行「I am sorry that…」承认责任不辩解；第 11 行「sorry again」略重复，未过度自责 |
| clarity | 2 | 第 9 行「as soon as possible」不可执行，与同句「Friday 6 November」自相矛盾；「we can fix it」未说明谁改、改到什么程度 |
| scenario_fit | 2 | 第 7 行原因（终检未完成）与第 9 行补救（先发两张 banner）脱节，未说明这两张为何已可交付 |

修改项（按优先级）：① 删「as soon as possible」，改「by 12 pm on Friday 6 November」；② 补一句说明两张 banner 已通过终检；③ 第 9 行拆成两段，说清版式反馈谁在何时改。

**gap 微课（`g-E1-scenario_fit`）**：结论正确（「场景一致 = 每个动作都能被原因解释」），但示例是 Python `def explain(reason, action, bridge)` + `print`；「回到作品：只改第 9 行一处…改完重新 `artifact add` 并 `review`」这句可用。

**v2 critic（`r-E1-9950bddf`，加权 3.0，四维 3 分，`达阈值=True`，关闭 `g-E1-clarity`、`g-E1-scenario_fit`）**：逐维引第 3/7/9/11/13 行，确认「已通过终检」衔接补上、ASAP 已移除；仍给 3 条可选改进（`the same day` 收紧为 `on 9 November`；加一句「If not, tell me your preferred date」；补 banner 的验收标准）。

**defense（`d-E1-9950bddf`）**：`3/3 问通过；最重维度 通过；判定：passed`。三问是 scenario_fit/tone/structure 的写作换约束题，不是代码题。

## 附录 C · `status` 摘要（结束态，新进程内）

```
Forge · 英文工作邮件写作
模板 email｜里程碑 E2「跨部门请求」 status=active｜导师 coach｜离线=否
起点档案：{"api": "能", "tools": "做过", "mode": "二十分钟见到东西"} → M1-first（standard，20 分钟切片；answered=True）
帮助等级：最近 L1（coach）｜最高 L2（guide）
作品：2 件｜最新 a-E1-9950bddf artifacts/email/E1/e1-apology-9950bddf.md sha=9950bddf25d2 assisted_level=0
最近评审：无
最近交接：coach → coach（pause）｜do_task：E2「跨部门请求」还没有作品；交付物：artifacts/email/e2-request.md
上次会话：20261104-120147-coach（coach，1 轮），进行中
git：branch=master remote=无 changed=7 ahead=0 behind=0

下一步：do_task｜E2「跨部门请求」还没有作品；交付物：artifacts/email/e2-request.md
切片：20 分钟 — 20 分钟切片：只做能跑的最小版本——一条真实输入 + 一次运行 + 打印结果；失败场景留到下次
当前交付物：artifacts/email/e2-request.md
```

`milestones` 交叉核对：

```
E1  道歉与补救            passed  2  2  3.0  passed  verified
E2  跨部门请求            active  0  0  -    -       -
E3  拒绝并保住关系 + 作品集收尾  locked  0  0  -    -       -
```

`gap --all`：`g-E1-scenario_fit closed（2/3，w30）`、`g-E1-clarity closed（2/3，w20）`。
