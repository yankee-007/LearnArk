# 体验报告 — direction-a-skillmap round-04 S4（Git 同步 + 干净克隆恢复）

- 版本: 0.2.2（core 1.0.1 · schema 1，见 `version-manifest.json`）
- 体验者: 独立子 Agent（DeepSeek Harness 子会话，独立上下文，非研发者）
- 场景: S4 Git 同步与干净克隆恢复（P3 Mia：两周前学过一点 function calling，只记得大概；今天只有 20 分钟，想快速继续、不想重头学）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r04-s4\proj`
  克隆目录: `...\r04-s4\clone`；裸仓库: `...\r04-s4\remote.git`
- 入口: `python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-a-skillmap\runtime\learn.py`（`START_HERE.md` 与生成的 `README.md` / `AGENTS.md` 一致）
- 交互预算: 8 次（本任务卡；personas 模板默认 12 次），实际使用 **8 次**（5 次诊断 + 2 次 B1-apply + 1 次克隆内续聊）；另有 **4 次由 `start` 自动写入的「开始学习 / 继续学习」伪回合**，不是学习者发出的，未计入预算
- 时间: 2026-11-04 03:11–03:21（Asia/Shanghai）
- 导师模式: 真实 LLM（DeepSeek API，key 由 `_sandbox/env.ps1` 注入环境变量，未落盘、未打印）；全程未用 `--offline`

> **同步方式声明：本机裸仓库只是「模拟远程 / 另一台设备」。本文验证的是本地 Git 流程，真实 GitHub 远程与真实跨设备均未验证。全程未使用 force push、未删除远程、未修改产品代码或测试。**

---

## 实际步骤（命令 + 关键输出摘要）

1. **建项目**（03:12）
   ```powershell
   python runtime\learn.py init --goal "能独立做出带工具调用的最小可用 Agent" --template agent-dev --dir ...\proj
   ```
   输出：`状态：已创建`、生成了 `.learnark/*`、`AGENTS.md`、`README.md`、`.gitignore`，`git：git init`。
   此时 `git log` 报 `does not have any commits yet`，工作区全部 untracked（`init` 只初始化仓库，不提交）。

2. **start（首次，自动进入 5 题诊断）**
   ```powershell
   python runtime\learn.py start --project ...\proj --minutes 20
   ```
   开场即说明目标、12 节点地图与「5 道诊断题，约 6 分钟」，随后逐题提问（tool call 往返 / 循环终止 bug / RAG 与会话记忆 / HTTP 超时 / 最小评测）。

3. **诊断 5 轮**（`say -` 读 UTF-8 stdin 文件，避免 PowerShell 5.1 吞引号；这是 `START_HERE.md` 明确教的用法，有效）
   - 5 题都判 `正确（diagnose）`，B1/C2/D2/A2/E1 均置 L1（诊断上限）。
   - 结束语：`定位：B1 由探针 Q1 判定 L1，先修 A2 L1 已就绪 → 跳过讲解与操练，直接从 apply 开始。`
   - 任务卡：`节点：B1 消息结构与角色（L1 → 目标 L3）· 阶段：应用 apply · 活动：B1-apply`。

4. **status（诊断后）**
   ```
   当前：B1 消息结构与角色 · apply（B1-apply） · 导师 coach
   等级：L0 7 · L1 5 · L2 0 · L3 0
   下一步：继续 B1 的 应用（B1-apply），约 20 分钟
   同步：dirty（written=yes committed=no pushed=no）
   ```

5. **再 start 取应用题目**（产品在诊断结束的同一轮只给了任务卡，没给题面；学习者只能再 `start` 一次）
   题面：写 `artifacts/build_messages.py`，system 只放稳定规则、user 只放本次数据、可 `json.dumps`、role 正确；贴脚本 + 真实运行输出。

6. **第 1 次 apply 尝试**：写了脚本并运行，输出 2 条 message；但把「本次要算的是 17 和 25」放进了 system。
   导师（coach）未判分，给了 **提示等级 1**：「约束与数据混层」，要求回答「卡在哪 / 期望什么 / 实际看到什么」三问。

7. **第 2 轮（修订）**：把数字移到 user（`json.dumps({"a": 17, "b": 25})`），重跑贴输出，并答三问。
   结果：`阶段通过：应用（B1-apply）`、`等级：B1 L1 → L2（独立通过）`、`作答：正确`。同时导师追加变式（a=-3.5、b=0）但**未等回答就通过了阶段**。

8. **status**：B1 L2，`下一步：继续 B1 的 检查（B1-check）`，`同步：dirty（written=yes committed=no pushed=no）`。

9. **建裸仓库 + 配远程**（按场景卡）
   ```powershell
   git init --bare ...\remote.git
   git remote add origin ...\remote.git
   ```
   `git remote -v` 正常显示 origin 的 fetch/push 两条。

10. **sync（原始项目，远程为空）**
    ```
    git state: pushed (written=yes, committed=yes, pushed=yes)
    written: yes
    committed: yes (sha ad79489, files 11)
    pushed: yes
    remote: ...\remote.git
    ```
    独立核对：`HEAD=ad794896…`、`git ls-remote origin` 的 `refs/heads/master` 同为 `ad79489`；提交内含 11 个文件（`.gitignore`、`AGENTS.md`、`README.md`、`artifacts/build_messages.py`、`sessions/…md`、`.learnark/…`），`.learnark/usage.jsonl` 与锁文件按 `.gitignore` 排除。提交文件里没有 API key 字样。

11. **克隆**（03:15）
    ```powershell
    git clone remote.git clone
    ```
    `clone` 目录只含项目文件（无 `.git` 之外的额外物），`git log` 与远程一致（`ad79489`）。

12. **在克隆目录只用产品入口 start**
    ```
    刚才那步还没交证据，先把变式跑完再往下走——不然这一轮等于没做。
    就差一步：把数据换成 a = -3.5、b = 0，重跑，贴两样东西……
    上次停在 B1 的 检查，第 1 次提交已通过；今天续做 B1-check，约 20 分钟。
    —— 今日任务 —— 节点：B1 · 阶段：检查 check · 导师：考核导师 · 活动：B1-check
    ```
    **恢复信息本身是对的**：知道停在 B1、阶段 check、下一步 B1-check，等级/薄弱点与原始项目一致（B1 L2、A1/B2/C1 仍 L0）。会话记录、事件、等级、薄弱点、产物都在克隆里被读到了（克隆当时还没有 `handoff/`，交接文件是克隆后自己 `pause` 才生成的）。
    **但导师话术与阶段矛盾**：运行时报「检查 check / 考核导师」，考核导师开口却要求补交上一阶段的「变式」，并说「刚才那步还没交证据」。

13. **克隆目录 status**
    ```
    当前：B1 消息结构与角色 · check（B1-check） · 导师 examiner
    等级：L0 7 · L1 4 · L2 1 · L3 0
    帮助：上次提示等级 0 · 独立通过 1 次 · 受助完成 0 次
    下一步：继续 B1 的 检查（B1-check），约 20 分钟
    同步：dirty（written=yes committed=no pushed=yes）
    ```
    内容（节点、阶段、等级、薄弱、下一步）与原始项目一致；无任何「原路径不存在」类报错（`.learnark/*.json` 内不含绝对路径，grep `r04-s4` 无命中）。唯一的路径依赖在生成的 `README.md` / `AGENTS.md` 里硬编码了本机 variant 路径，文档自己提示换机要改。

14. **克隆内继续 1 轮**：按导师要求把数据改成 `a=-3.5, b=0`，重跑并贴「改动行 + 真实输出」。
    导师（考核导师）答：「独立题这关过了……现在换场景」并给出迁移题。
    但运行时记录是：`本轮没有作答，只记录对话，不产生能力证据`；`check_correct` 仍为 0。

15. **克隆内 sync**
    ```
    git state: pushed (written=yes, committed=yes, pushed=yes)
    committed: yes (sha c913bfb, files 6)
    pushed: yes
    ```
    核对：远程 `refs/heads/master = c913bfb`，克隆工作区干净；提交里包含 `artifacts/build_messages.py` 的改动与新增会话/事件。此时原始项目落后 1 个提交（`ad79489`）。

16. **（可选）冲突模拟 —— 原始项目侧**
    ```
    python runtime\learn.py pause --note "原机器收个尾：今天先到这"
    ```
    输出（节选）：
    ```
    git state: conflict (written=yes, committed=yes, pushed=no)
    committed: yes (sha e8bf8e5, files 5)
    pushed: no
    recovery: Remote changes conflict with local ones. Nothing was force-pushed; resolve the conflict manually (git status), then run sync again.
    detail: ... Rebasing (1/1)
    error: could not apply e8bf8e5... learn(proj): pause 2026-11-04 03:16
    ```
    现场核对：`git status` 显示 `Your branch and 'origin/master' have diverged, and have 1 and 1 different commits`、`nothing to commit, working tree clean`；未留下半成品 rebase（产品把 rebase 回滚了），本地 `e8bf8e5` 完好。

17. **按提示「再 sync 一次」**（验证恢复建议是否可执行）
    ```
    git state: conflict (written=yes, committed=yes, pushed=no)
    committed: yes (sha 6631373, files 2)
    recovery: ... resolve the conflict manually (git status), then run sync again. detail: Rebasing (1/2)
    error: could not apply e8bf8e5...
    ```
    退出码 **3**。每次重试都会多产生一个本地提交（这次是 `dedupe.json` + `events.jsonl` 的同步事件），分叉从 1/1 变成 2/1，然后再次失败。**`git status` 里没有可解的冲突文件，只有分叉提示**，学习者按字面照做无法前进。
    冲突不是偶然：两边提交都改了同一批文件——克隆侧 `c913bfb` 改了 `journal/dedupe.json`、`journal/events.jsonl`、`state/plan.json`（另含 memory、artifacts、session），原始项目侧 `e8bf8e5` 改了同一组 `dedupe.json` / `events.jsonl` / `plan.json`（另含 handoff）。append-only 事件流与整文件 JSON 状态天然会在同一位置撞车。

18. **（可选）冲突模拟 —— 克隆侧**
    ```
    python runtime\learn.py pause --note "克隆这边也收尾：迁移题还没答完"
    ```
    输出：`git state: pushed (written=yes, committed=yes, pushed=yes)`、`committed: yes (sha 59a338f, files 5)`、`pushed: yes`。
    远程 `refs/heads/master` 变为 `59a338f`；克隆干净且 up to date。原始项目的 `e8bf8e5`/`6631373` 不在远程（`git merge-base --is-ancestor e8bf8e5 origin/master` 返回非 0，远程树里 grep 不到原始项目的交接备注），但**本地两条记录都还在**。

19. **两侧 status / doctor**
    - 原始项目：`同步：clean（written=yes committed=yes pushed=no）` —— 工作区干净但 2 个提交未推送、且与远程分叉，状态词显示为 `clean`。
    - 克隆：`同步：clean（written=yes committed=yes pushed=yes）`。
    - `doctor`（原始项目，分叉 + 2 个未推送提交）：`[ok] git 仓库: branch=master changed=0 remote=…`，结论 **`全部检查通过。`**

---

## 完成情况

- 开始: **成功**（`init` + `start` 一次进入诊断，开场说明清楚）
- 诊断或定位: **成功**（5 题、真实 LLM、如实记录；定位到 B1-apply 并说明依据）
- 尝试与反馈: **成功**（第 1 次给了分级提示 L1 而非直接给答案；第 2 次判正确并升到 L2；`help_level`/独立通过次数在 status 可见）
- 保存/恢复（克隆）: **部分成功**。克隆后节点/阶段/等级/下一步/会话/事件/薄弱点/产物都回来了，无路径报错（交接文件是克隆后 `pause` 才生成的，克隆当时本就没有）；但恢复后的第一段导师话术要求补上一阶段的活，与运行时宣布的 check 阶段冲突；且 `start` 会把「开始学习 / 继续学习」写成学习者发言。
- 同步三态: **准确**（逐项独立核对 5 次，5 次相符；详见下表）
- 冲突处理: **给出人工处理提示、未 force push、双方本地记录都在**；但「再 sync 一次」的建议会重复失败并累积新提交，`status` 与 `doctor` 都不会报出「未推送/分叉」，对普通学习者不可执行
- 切换导师: 本场景未要求手动 `switch`；阶段推进时产品自动从 navigator → coach → examiner，切换本身无报错

---

## 三态核对（written / committed / pushed）

| 场景 | written | committed | pushed | 独立核对 |
| --- | --- | --- | --- | --- |
| 原始项目首次 sync（远程为空） | yes | yes `ad79489`，11 files | yes | `HEAD == ls-remote refs/heads/master == ad79489` ✓ |
| 克隆内 sync | yes | yes `c913bfb`，6 files | yes | 远程 `master == c913bfb`；克隆工作区干净 ✓ |
| 原始项目 pause（冲突） | yes | yes `e8bf8e5`，5 files | no | `e8bf8e5` 不是 `origin/master` 的祖先；远程无该提交 ✓ |
| 原始项目 sync 重试 | yes | yes `6631373`，2 files | no | 同上，且 exit 3 ✓ |
| 克隆 pause | yes | yes `59a338f`，5 files | yes | `ls-remote master == 59a338f` ✓ |

结论：**sync 输出里的 written / committed / pushed 逐项都与事实相符（5/5）**，commit sha、文件数、远程 ref 都对得上；`pushed: no` 没有含糊其辞，也明确写了 `Nothing was force-pushed`。
不准确的是 `status` 的**汇总措辞**（见问题 4）：克隆首次 `dirty` 与 `pushed=yes` 并列；原始项目冲突后 `clean` 与 `pushed=no` 并列。

---

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 新电脑 clone 后 `start` 直接知道停在哪、下一步做什么 | 知道：B1 / check / 下一步 B1-check，等级与薄弱点都对 | 步骤 12/13，`logs\15-clone-start.log`、`logs\16-clone-status.log` |
| 克隆后导师直接给「检查」题 | 考核导师先要求补交上一阶段的变式，说「刚才那步还没交证据」，与「阶段：检查」矛盾 | `logs\15-clone-start.log` 第 1–8 行 |
| 克隆后学习记录完整带过来 | 节点、等级、会话、事件、薄弱点、产物都在，无原路径报错（克隆当时没有 handoff，交接是克隆后自己 pause 生成的） | 步骤 13、`clone\.learnark\*`、`clone\sessions\*` |
| sync 的 written/committed/pushed 可信 | 5 次 sync 全部逐项核对通过 | 上表、`logs\14-sync1.log`、`logs\19-clone-sync.log` |
| 没配远程时要明确说「未推送」 | 早期 status 明确 `pushed=no`；README 也写了「没有远程 → pushed=no」 | 步骤 4、8 |
| 两台机器各改各的，冲突不会静默覆盖 | 没覆盖：双方提交都在本地，未 force push；但要求手工 git 处理，且「再 sync」循环失败 | 步骤 16–18，`logs\20`、`logs\21`、`logs\22` |
| 冲突时 status/doctor 能告诉我出了问题 | status 显示 `clean`；doctor 显示「全部检查通过」 | 步骤 19，`logs\23`、`logs\26` |
| 会话记录里只有我说过的话 | `start` 自动写入「开始学习」「继续学习」共 4 次，并计入轮次 | 步骤 5、12；`logs\01-start.log`、`08-start2.log`、`15-clone-start.log`、`27-clone-start-after-pause.log` |

---

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | 重要 | **克隆恢复后导师话术与运行时阶段矛盾**：运行时报 `阶段：检查 check · 导师：考核导师`，考核导师却要求补交上一阶段 apply 的「变式」，并称「刚才那步还没交证据」；同一段输出又写「上次停在 B1 的 检查，第 1 次提交已通过」。学习者无法判断该做旧题还是检查题 | 完成 apply → sync → `git clone` → 在 clone 里 `start` | `logs\15-clone-start.log`；`clone\sessions\20261104-031247-navigator.md` 第 278–294 行 |
| 2 | 阻塞（冲突路径） | **冲突恢复建议不可执行且会循环**：sync 提示 `resolve the conflict manually (git status), then run sync again`，但 `git status` 显示 `nothing to commit, working tree clean` + `diverged`，没有可解冲突；再次 sync 只多生成一个提交（`6631373`）并再次失败（exit 3），分叉从 1/1 变 2/1。冲突根源是两边都改了 `.learnark/journal/events.jsonl`、`dedupe.json`、`.learnark/state/plan.json`（append-only 事件流 + 整文件 JSON），普通学习者不可能手工合并 | 两台设备各 `pause` 一次（或本地提交 + 远程前进）后 `sync`，按提示再 `sync` | `logs\20-proj-pause.log`、`logs\21-proj-sync-retry.log`、`logs\25-git-evidence.txt` |
| 3 | 重要 | **`start` 伪造学习者发言并写进权威会话记录**：会话里出现 `## 学习者 · turn 2 · diagnose / 开始学习`、`turn 8 · B1-apply / 继续学习`、`turn 11 · B1-check / 继续学习`、`turn 2 · B1-check / 开始学习` 共 4 次，学习者从未说过；交接里因此写「本会话 11 轮对话」；且活动标签错位一格（诊断第 5 题被标成 `B1-apply`，apply 修订被标成 `B1-check`） | 任意一次 `start` 后查看 `sessions\*.md` | `proj\sessions\20261104-031247-navigator.md` 第 5、112、131、217 行；`clone\sessions\20261104-031247-navigator.md` 第 278、296 行；`clone\sessions\20261104-031746-examiner.md` 第 5 行 |
| 4 | 一般 | **status 同步摘要措辞矛盾**：克隆首次 `dirty（written=yes committed=no pushed=yes）`（dirty 却 pushed=yes）；原始项目分叉 + 2 个未推送提交时显示 `clean（written=yes committed=yes pushed=no）`。三态数值本身对，但 `clean/dirty` 与 pushed 组合会让人误以为「没事」 | 克隆后未 sync 时跑 `status`；冲突后跑 `status` | `logs\16-clone-status.log`、`logs\23-proj-status-diverged.log` |
| 5 | 重要 | **check 阶段「口头通过」但不落证据**：考核导师说「独立题这关过了」，记录却是 `本轮没有作答，只记录对话，不产生能力证据`，`check_correct` 仍为 0。学习者以为过关，运行时并未记分；若之后只看 status，会发现自己还在原地 | 克隆内按导师要求交变式答案，然后看 `### 记录` 与 `plan.json` 的 `check_correct` | `logs\18-clone-say.log`；`clone\.learnark\state\plan.json`（`check_correct: 0`、`turn_count: 2`） |
| 6 | 一般 | **恢复摘要里的计数与事实不符**：check 阶段 0 通过时显示「第 1 次提交已通过」；任务卡「理由 3」仍写「B1 当前 L1」，而实际已是 L2（定位时生成的旧文案未刷新） | clone 里 `start` 看最后 10 行 | `logs\15-clone-start.log` 第 18–20 行；`logs\27-clone-start-after-pause.log` 第 20–30 行 |
| 7 | 一般 | **doctor 在同步已坏时仍报「全部检查通过」**：只检查 `branch/changed=0/remote`，不检查 ahead/behind 与未推送提交；学习者失去最后一个自检手段 | 原始项目分叉、2 个未推送提交时跑 `doctor` | `logs\26-proj-doctor.log` |
| 8 | 一般 | **项目内说明硬编码本机路径**：生成的 `README.md` / `AGENTS.md` 写死 `C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\...\runtime\learn.py`；换机器必须手改。产品文档已提示「把上面路径换成那台机器的」，克隆（同机）因此没报错 | 打开 clone 里的 README/AGENTS | `clone\README.md` 第 8、15–16 行；`clone\AGENTS.md` 第 7–11 行 |

> 未发现：force push、静默覆盖、密钥入库、原路径导致的启动报错、`--offline` 误用。

---

## 使用负担

- 师生往返: **8 次**（预算 8；5 诊断 + 2 apply + 1 克隆）；另有 4 次产品自动写下的伪学习者回合
- 产品命令: **23 次**（init 1、start 4、say 8、status 5、sync 2、pause 2、doctor 1），另有 3 条手工 git 命令（init --bare / remote add / clone）
- 需要阅读的文档: 4 处（`START_HERE.md`、生成的 `README.md`、`AGENTS.md`、报告模板）
- 不清楚的地方:
  - 诊断结束后只给「今日任务」卡片、不给题面，必须再 `start` 一次才看到题（多一次往返观感）
  - `start` 每次都会写一条「开始学习/继续学习」，让人以为记录里有别人的操作
  - 克隆后到底该做「补变式」还是「B1 检查」，两段话互相打脸
  - 冲突后照着 recovery 做没有出路；`git status` 没有冲突文件可解

---

## 结论

- **是否完成场景目标: 是（主链路）/ 否（冲突恢复）**。
  主链路成立：真实 LLM 学了两轮、`sync` 三态逐项属实、`git clone` 后仅凭项目文件 `start` 能恢复节点/阶段/等级/下一步/会话/事件/产物，且无原路径报错、无密钥入库、无 force push、双方成果都未被覆盖。
  冲突路径不成立：产品只给通用英文 git 提示，重试会循环并累积提交，`status`/`doctor` 都显示「一切正常」，普通学习者无法自行恢复。
- **最需要修的一件事**: 让 `sync` 的冲突恢复成为「可执行的一步」——至少做到 (a) 先 fetch 再判断 ahead/behind，不盲目 rebase 本地提交；(b) 冲突时把要处理的文件列出来并给出「放弃本地/保留本地/合并」三选一的人话步骤，或提供 `sync --abort` / `sync --prefer-local` 这类安全出口；(c) 让 `status` / `doctor` 在分叉或未推送时明确报警，而不是 `clean` / 「全部检查通过」。其次是克隆恢复时不要让考核导师去补做上一阶段的应用题。

---

## 附录 A：`git log --oneline`

原始项目（与远程分叉后）:
```
* 6631373 learn(proj): sync 2026-11-04 03:16
* e8bf8e5 learn(proj): pause 2026-11-04 03:16
| * c913bfb 从克隆继续：变式+迁移题
|/
* ad79489 learn(proj): sync 2026-11-04 03:15
```

克隆目录:
```
59a338f learn(proj): pause 2026-11-04 03:16
c913bfb 从克隆继续：变式+迁移题
ad79489 learn(proj): sync 2026-11-04 03:15
```

## 附录 B：`git remote -v`

原始项目:
```
origin  C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r04-s4\remote.git (fetch)
origin  C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r04-s4\remote.git (push)
```

克隆目录:
```
origin  C:/Users/YK/Desktop/LearnArk/_sandbox/projects/a/r04-s4/remote.git (fetch)
origin  C:/Users/YK/Desktop/LearnArk/_sandbox/projects/a/r04-s4/remote.git (push)
```

## 附录 C：各次 `sync` 原文

1) 原始项目首次（`logs\14-sync1.log`）
```
git state: pushed (written=yes, committed=yes, pushed=yes)
written: yes
committed: yes (sha ad79489, files 11)
pushed: yes
remote: C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r04-s4\remote.git
```

2) 克隆内（`logs\19-clone-sync.log`）
```
git state: pushed (written=yes, committed=yes, pushed=yes)
written: yes
committed: yes (sha c913bfb, files 6)
pushed: yes
remote: C:/Users/YK/Desktop/LearnArk/_sandbox/projects/a/r04-s4/remote.git
```

3) 原始项目 `pause` 触发的冲突（`logs\20-proj-pause.log` 节选）
```
git state: conflict (written=yes, committed=yes, pushed=no)
written: yes
committed: yes (sha e8bf8e5, files 5)
pushed: no
recovery: Remote changes conflict with local ones. Nothing was force-pushed; resolve the conflict manually (git status), then run sync again. detail: From ...\remote
   ad79489..c913bfb  master     -> origin/master
Rebasing (1/1)
error: could not apply e8bf8e5... learn(proj): pause 2026-11-04 03:16
```

4) 原始项目按提示重试（`logs\21-proj-sync-retry.log`，退出码 3）
```
git state: conflict (written=yes, committed=yes, pushed=no)
committed: yes (sha 6631373, files 2)
pushed: no
recovery: ... detail: Rebasing (1/2)
error: could not apply e8bf8e5...
同步未完成，但本地成果已保存；按 recovery 提示处理后重试（不会 force push）。
```

5) 克隆 `pause` 后自动同步（`logs\22-clone-pause.log`）
```
git state: pushed (written=yes, committed=yes, pushed=yes)
written: yes
committed: yes (sha 59a338f, files 5)
pushed: yes
```

## 附录 D：克隆目录 `status` 摘要（首次 `start` 后，`logs\16-clone-status.log`）

```
SkillMap · 能独立做出带工具调用的最小可用 Agent
项目：proj（template agent-dev）  离线：no
当前：B1 消息结构与角色 · check（B1-check） · 导师 examiner
等级：L0 7 · L1 4 · L2 1 · L3 0
帮助：上次提示等级 0 · 独立通过 1 次 · 受助完成 0 次
最近等级变化：B1 L1 → L2（独立通过）
薄弱：
  - A1 仍是 L0（Python 数据结构与异常）
  - B1：约束与数据混层：把本次数据写进 system
  - B2 仍是 L0（结构化输出与解析）
  - C1 仍是 L0（工具 schema 定义）
下一步：继续 B1 的 检查（B1-check），约 20 分钟
同步：dirty（written=yes committed=no pushed=yes）
```

与原始项目同刻 `status`（`logs\13-status2.log`）对照：节点、阶段、等级分布（L0 7 / L1 4 / L2 1）、薄弱项、下一步逐行一致；只有「帮助：上次提示等级」从 1 变成 0（克隆内 `start` 又写了一轮 help_level=0 的导师回复）和「同步」行不同。说明记录确实随克隆恢复。

## 附录 E：证据文件清单（均在沙盒内，可复现）

| 文件 | 内容 |
| --- | --- |
| `...\r04-s4\logs\01-start.log` … `06-say5.log` | 首次 start 与 5 轮诊断 |
| `...\logs\08-start2.log` … `12-say7-apply2.log` | 应用题面、2 次 apply 尝试与反馈 |
| `...\logs\13-status2.log`、`16-clone-status.log`、`23-proj-status-diverged.log`、`24-clone-status-paused.log` | 各次 status |
| `...\logs\14-sync1.log`、`19-clone-sync.log`、`20-proj-pause.log`、`21-proj-sync-retry.log`、`22-clone-pause.log` | 各次 sync / pause |
| `...\logs\15-clone-start.log`、`27-clone-start-after-pause.log` | 克隆内 start（含矛盾话术） |
| `...\logs\25-git-evidence.txt` | git log / status / remote / ls-remote 汇总 |
| `...\logs\26-proj-doctor.log` | 分叉状态下的 doctor |
| `...\proj\.learnark\`、`...\clone\.learnark\`、`...\proj\sessions\`、`...\clone\sessions\` | 产品自身状态、事件、会话 |
| `...\r04-s4\remote.git` | 本地裸仓库（模拟远程） |

---

**备注（诚实性）**：以上每个「通过」都对应实际命令输出或文件，未读源码/设计/测试/历史报告，未修改产品；克隆目录只用 `git clone` 生成，未手工拷贝文件；未执行 force push。唯一无法验证的是真实 GitHub 远程与真实第二台设备。冲突现场按原样保留：原始项目最后停在「与远程分叉、2 个提交未推送」，克隆停在 `59a338f` 且干净；未做任何手工合并，方便研发复查。
