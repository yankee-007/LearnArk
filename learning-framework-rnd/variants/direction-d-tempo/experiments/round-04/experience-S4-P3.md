# 体验报告 — direction-d-tempo round-04 S4（P3 Mia）

- 版本: direction-d-tempo 0.2.2（core 1.0.1，schema 1；`version` 输出）
- 体验者: 独立子 Agent（DeepSeek Harness / deepseek-flash 上下文；非研发者，只读公开入口与产品输出）
- 场景: S4 Git 同步 + 干净克隆恢复（P3 Mia：两周前学过 function calling，回来只记得大概；今天只有 20 分钟）
- 项目目录: 原机 `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r04-s4\proj`；新机模拟 `...\r04-s4\clone`；本地裸仓库 `...\r04-s4\remote.git`
- 入口: `python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-d-tempo\runtime\learn.py <cmd>`（**未加 `--offline`**；真实 API，输出显示“配置 deepseek-chat / 实际返回 deepseek-flash”）
- 交互预算: 8 次；实际使用 **5 次 `say`**（另有 1 次带“今天只有二十分钟”的 `start`；若把这句也计入则为 6 次）
- 时间: 2026-11-04 03:19–03:22（Asia/Shanghai，真实时钟）
- 前提声明: **本地 Git 流程验证，真实 GitHub 未验证**（本机裸仓库只是模拟远程）。未 force push、未删远程、未改产品代码；clone 只由 `git clone` 生成。
- 下文用 `SB` 指 `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r04-s4`，证据原始输出都在 `SB\evidence\`。

## 实际步骤（命令 + 关键输出摘要）

1. **建项目**（P3 自述只记录原话，不计等级）
   ```
   learn.py init --goal "能独立设计、实现并评测一个可用的 Agent 应用" --template agent-dev --minutes-per-week 600 --dir SB\proj --self-report "两周前跟着教程做过 function calling，现在只记得大概，想快点接着做。"
   ```
   输出：技能 10 个、卡片 12 张（今天到期）、每周 600 分钟、每次默认 20 分钟；`git init` + 初始提交 `547b989`（本地）。（`SB\evidence\01-init.txt`）

2. **开始 + 2 轮真实交流**（原机）
   ```
   learn.py start "今天只有二十分钟" --project SB\proj
   ```
   输出：本次 20 分钟（已用 0 / 剩余 20）；导师 `trainer`、会话 `20261104-031928-trainer`；模型实际返回 `deepseek-flash`；候选表 3 项，选中 5 分钟到期卡 `recall-card-0001`（agent-loop），理由“到期组该卡逾期 0 天，先清到期；5 分钟能在预算内做完”；开场问“Agent 循环的四个阶段/三种停止条件”。（`02-start1.txt`）
   ```
   learn.py say "大概是先想一下要做什么，然后决定要不要调用工具，调完看返回结果，再根据结果继续想。停止条件我记得是任务做完、达到最大步数，还有一个是工具报错就停。"
   ```
   反馈：四阶段判对；“工具报错就停”被指出不是通用停止条件，第三种应是“连续两次没有新信息”；继续追问三种停止条件；机器块记“提示级别 0 / 本题未判对”。（`03-say1.txt`）
   ```
   learn.py say "一是目标已经完成；二是循环次数到了设定的上限；三是连着两轮拿到的结果差不多，没有新信息，就该停。"
   ```
   反馈：三种停止条件说全；`agent-loop L0→L1`，卡片记 good、间隔 2 天（2026-11-06 到期）；活动完成。两次回答都不是照抄导师原句。（`04-say2.txt`）

3. **status（同步前）**
   ```
   learn.py status --project SB\proj
   ```
   摘要：预算 20 / 已用 5 / 剩余 15；已排 1/2 项；上次活动 recall_card · agent-loop（03:19）；本周块 `block-agent-dev-2026-W45` 步骤 0/3；下一步（现在）`concept_block · eval-harness`（10 分钟）；`同步：written=yes committed=no pushed=no（state=written）`；journal 16 条。（`05-status1.txt`）

4. **裸仓库 + 远程 + 第一次 sync**
   ```
   git init --bare SB\remote.git
   git -C SB\proj remote add origin SB\remote.git
   learn.py sync --project SB\proj
   ```
   输出：`git state: pushed (written=yes, committed=yes, pushed=yes)`；提交 7 个文件；`commit: 5250b85 分支: master`；remote 为本地裸仓库。（`07-sync1.txt`）
   核对：`git log --oneline` 为 `5250b85` / `547b989`；工作区干净；裸仓库 log 与 remote -v 均一致。（`08-gitlog-proj.txt`、`09-remote-check.txt`）

5. **克隆到 clone，只凭产品入口 `start`**
   ```
   git clone SB\remote.git SB\clone
   cd SB\clone
   learn.py start
   ```
   输出：**“上次停在哪：recall_card · agent-loop（2026-11-04 03:19）”**；沿用今天 20 分钟预算（已用 5 / 剩余 15）；导师 `trainer → coach`，并说明“按活动类型绑定导师（本次是概念块），不是随机切换”；选中本周块第 1 步（10 分钟）；提问“如果每次改动后都换一批新问题来测，会出什么问题？”。（`10-start-clone.txt`）
   说明：PowerShell 5.1 把 `git clone` 的进度 stderr 记为 NativeCommandError（表面 exit 1），实际 clone 成功；随后 `ls-files` 验证。非产品问题。
   克隆内容：`.gitignore`、`.learnark/`（journal/dedupe、events.jsonl、project.json、state×4）、`AGENTS.md`、`README.md`、`sessions/20261104-031928-trainer.md`；无未跟踪文件。（`09-remote-check.txt`）

6. **克隆目录继续 1 轮 + status + sync**
   ```
   learn.py say "那就没法比较了：这次分高可能只是题简单，分低也可能是题难，分不清是改动变好还是变差。所以每次都得用同一套题。"
   ```
   反馈抓到了核心，追问复述；机器块记“提示级别 0 / 本题未判对 / 证据 failed”，新建卡 `card-93a985`；活动仍未完成。（`11-say-clone.txt`）
   ```
   learn.py status
   ```
   摘要：已用 15 / 剩余 5 / 已排 2/2 项；“**未完成：concept_block · eval-harness**”；eval-harness L0 observed；下一步（下次）`recall_card · tool-contract`；`同步：written=yes committed=no pushed=no`。（`12-status-clone.txt`）
   ```
   learn.py sync
   ```
   输出：`pushed (written=yes, committed=yes, pushed=yes)`，提交 7 个文件，`commit: 50c7496`，分支 master。（`13-sync-clone.txt`）
   核对：裸仓库 log 现有 `50c7496 / 5250b85 / 547b989`；clone log 同步；`git remote -v` 指向同一裸仓库。

7. **（可选）分叉冲突实验（未 force push）**
   - 原机 `start`（本地状态仍是 03:19 的旧状态）→ 再答 1 轮 → `eval-harness L0→L1`，本周块第 1 步完成，活动完成。（`14-start-proj-conflict.txt`、`15-say-proj.txt`）
   - 原机 `sync`：
     ```
     git state: conflict (written=yes, committed=yes, pushed=no)
       提交文件：7 个 … commit: 5f82011  分支: master
       恢复建议：Remote changes conflict with local ones. Nothing was force-pushed; resolve the conflict manually (git status), then run sync again. detail: From SB\remote
        5250b85..50c7496  master -> origin/master
     Rebasing (1/1)
     error: could not apply 5f82011... learn(proj): 2026-11-04 03:20
     hint: Resolve all conflicts manually … git rebase --continue / --abort
     ```
     即 sync 先 fetch + `pull --rebase`，失败后 abort；当时**未**提示具体冲突文件。`git status` 之后显示：工作区干净、`master [origin/master: ahead 1, behind 1]`、无 `rebase-merge`/`rebase-apply`；reflog 有 `rebase (abort): returning to refs/heads/master`。**proj 本地提交 5f82011 保留，远程未被改写。**（`16-sync-proj-diverged.txt`、`17-git-state-proj.txt`）
   - 原机 `status`：只显示 `同步：written=yes committed=yes pushed=no（state=committed-local）`，**没有提“远程有新提交 / 已分叉 / 需处理”**，下一步照常给“下次”卡片。（`18-status-proj-conflict.txt`）
   - 克隆目录再答 1 轮（复述）并 `sync`：
     ```
     learn.py say "基线就是同一批固定题上次跑出来的分数……"
     learn.py sync
     ```
     导师文字说“一个缺口……请补一句”，机器块却记“判对 / 活动完成 / eval-harness L1”，并输出 `mentor_text_conflict` 术语；同步成功 `commit: 844a358`、8 个文件。（`19-say-clone2.txt`、`20-sync-clone2.txt`）
   - 回原机再次 `sync`：仍然 `state: conflict`、`pushed=no`，这次 `behind 2`，恢复建议原文不变；按建议跑 `git status` 仍是干净工作区，无冲突可解。**已复现两次，普通学习者无法照此恢复。**（`21-sync-proj-retry.txt`）
   - 分叉结果：远端历史为 `547b989 → 5250b85 → 50c7496 → 844a358`（线性，只增不减）；proj 的 `5f82011` 不在远端，但保留在本地。双方成果都未被覆盖，但也没有被合并到一处。

8. **克隆最终状态**（收尾核对）
   ```
   learn.py status
   ```
   摘要：已排 2/2、完成 2 项；eval-harness L1；本周块步骤 1/3；下一步（下次）`recall_card · tool-contract`；`同步：written=yes committed=yes pushed=yes（state=pushed）`；13 张卡到期。（`22-status-clone-final.txt`）

## 完成情况

| 项目 | 结果 | 说明 |
| --- | --- | --- |
| 开始（init/start） | 成功 | 真实 API；`deepseek-flash`；20 分钟预算生效 |
| 诊断或定位 | 成功 | 首次进入按到期卡自测；status 有上次活动与唯一下一步 |
| 尝试与反馈 | 成功 | 原机 2 轮、克隆 2 轮，均有具体反馈；有错误被指出（工具报错当停止条件） |
| 保存/恢复 | 成功 | sync 后由裸仓库 clone；新目录 `start` 恢复上次停留、预算、技能/卡片/会话、下一步与导师切换理由 |
| 切换导师 | 成功 | trainer → coach，输出说明按活动类型绑定，非随机 |
| 干净克隆（不手工拷贝） | 成功 | 只 `git clone`；clone 内无原路径报错 |
| 三态准确性 | 成功 | 5 次 sync 的 written/committed/pushed 均与本地/远端 git 实际一致 |
| 冲突处理 | **部分失败** | 未覆盖、未 force；但自动 rebase 失败后 abort，恢复建议与实际仓库状态不符，无法照做 |
| 失败恢复方法 | 失败 | 文字有，但“git status 找冲突再 sync”不可执行；重复 sync 同样报错 |

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| `sync` 报告的三态可信 | 5 次均与实际一致：推送成功时远端 log 有对应 commit；冲突时 pushed=no，远端未动 | `07/13/16/20/21` + `08/09` |
| clone 后 `start` 知道上次停在哪、下一步 | 正确显示 recall_card · agent-loop（03:19），并按计划选本周块第 1 步 | `10-start-clone.txt` |
| 会话/能力/下一步随项目过来 | 会话 md、技能 L1、11 张到期卡、本周块 0/3、20 分钟预算（已用 5）都在 | `12-status-clone.txt`、`09-remote-check.txt` |
| 新目录不依赖原路径 | 无报错；`.learnark` 内未发现原绝对路径串；clone 内旧会话文件与 proj 同名文件 `git hash-object` 相同 | `09-remote-check.txt`、本次 hash 比对 |
| 冲突时保留双方、要求人工处理、不 force | 双方 commit 都在（本地 5f82011 / 远端 844a358），未 force；但“人工处理”的建议不可执行 | `16/17/21` |
| 失败时给一条能照做的恢复方法 | 给了英文建议，但 rebase 已 abort，`git status` 无冲突；再 sync 循环 | `16/17/18/21` |
| 冲突时命令应表达失败（文档 exit 3=状态/并发冲突） | 实际 exit code 0；且 `state=conflict`/`state=committed-local` 不在公开文档的三态里 | `16/21` + START_HERE 退出码段 |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | **重要** | **冲突后的恢复建议不可执行**：`sync` 自动 fetch + `pull --rebase`，冲突后 abort，工作树干净、无冲突文件；却提示 “resolve the conflict manually (git status), then run sync again”。照做只会看到 `ahead 1, behind 1` 的分叉状态，再 `sync` 仍同样报错（复现 2 次），普通学习者无法恢复。 | 两台设备各自产生 commit；A 侧 `sync` 后，B 侧 `sync`；按提示 `git status`；再 `sync` | `SB\evidence\16-sync-proj-diverged.txt`、`17-git-state-proj.txt`、`21-sync-proj-retry.txt` |
| 2 | **重要** | **`status` 不暴露分叉/未推送原因**：冲突后只显示 `written=yes committed=yes pushed=no（state=committed-local）`，不提示远程有新提交或需要处理；与 `sync` 的 `state=conflict` 也不一致。只跑 status 的用户不知道同步失败在哪。 | 冲突发生后运行 `status`，对比同目录 `sync` 输出 | `18-status-proj-conflict.txt` vs `16-sync-proj-diverged.txt` |
| 3 | **重要** | **`sync` 冲突时退出码为 0**，与 START_HERE 的“3 = 状态/并发冲突”矛盾；同时新增的 `state=conflict`、`state=committed-local` 未在公开三态说明中出现。脚本/学习者无法用退出码判断失败。 | 冲突时执行 `sync; echo $LASTEXITCODE` | `16/21`（命令 exit 0）、START_HERE “退出码”段 |
| 4 | 一般 | **导师文字与机器块冲突**：导师说“一个缺口……请补一句”，机器块记“判对/活动完成”，并把内部术语 `mentor_text_conflict` 直接打给学习者；学习者不知道还要不要回答。 | 在 clone 中第二次 `say` | `19-say-clone2.txt` |
| 5 | 一般 | **部分正确但未完成的回答被记为 `failed` 证据**：导师说“你抓到了核心”，status 却是“未判对 · 证据类型 failed”，技能仍 L0。口头反馈与记录落差大。 | clone 第一次 `say` 后 `status` | `11-say-clone.txt`、`12-status-clone.txt` |
| 6 | 一般 | **候选表预算数字自相矛盾**：预算显示剩余 15 分钟，15 分钟活动却被标“超出剩余 5 分钟”（实际是排入 10 分钟第一项后第二项只剩 5 分钟），文字没说明是“第二项”限制。 | clone 中无分钟数 `start` | `10-start-clone.txt` 第 14–16 行 |

## 使用负担

- 师生往返: **5 次 `say`**（+1 次带分钟数的 `start`；若计入 6/8）
- 命令数: 20 次产品调用（含 1 次我漏写 `--project` 的用法错误重试；错误信息是 `learn: not inside a LearnArk project...`）+ 约 15 条 git 命令
- 需要阅读的文档: 3 处（`START_HERE.md`、场景卡、报告模板）；另读 `version-manifest.json` 和 `env.ps1` 各 1 次
- 不清楚的地方:
  - `sync` 会先 `pull --rebase`（公开命令表只写“只提交项目白名单；报告 written/committed/pushed”），rebase/冲突提示直接暴露给学习者；
  - `conflict` / `committed-local` 这两个状态文档里没有；
  - status 里“到期 11 张卡 · 0 个技能”中的“0 个技能”含义不明；
  - clone 中项目名仍显示 `proj`（目录已是 `clone`），只是显示层，无功能影响；
  - `committed` 在 `status`（HEAD 已提交）与 `sync`（本次是否新建 commit）里语义不同，容易误读。

## 结论

- **是否完成场景目标: 是**（核心链路全部跑通：建项 → 2 轮真实交流 → status → 裸仓库 + sync → git clone → 新目录 start 恢复 → 继续 1 轮 → sync；三态准确、克隆恢复完整、无原路径依赖）。分叉实验也完成，但暴露了冲突恢复路径的重要问题。
- **最需要修的一件事**: 给冲突一条**与实际仓库状态一致、普通学习者能照做**的恢复路径：既然 abort 后本地 commit 仍在、工作树干净，就不要再让用户 `git status` 找冲突；应明确说“本地提交已保留，远程有新提交，需要先合并/变基”并给出具体命令（或在 `sync` 中保留 rebase 进行态并列出冲突文件、提供 `--continue/--abort`），同时让 `status` 显示 diverged。当前这条建议会把用户困在重复 `sync` 的循环里。

## 附录

### A. `git log --oneline`

原机 `proj`（分叉实验后）:
```
5f82011 learn(proj): 2026-11-04 03:20
5250b85 learn(proj): 2026-11-04 03:19
547b989 learnark(proj): init agent-dev
```

克隆 `clone`（= 裸仓库最新）:
```
844a358 learn(proj): 2026-11-04 03:21
50c7496 learn(proj): 2026-11-04 03:20
5250b85 learn(proj): 2026-11-04 03:19
547b989 learnark(proj): init agent-dev
```

裸仓库 `remote.git` 的 `master` 与 clone 相同（4 个 commit，线性；proj 的 5f82011 不在远端）。

### B. `git remote -v`（proj / clone 相同）

```
origin  C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r04-s4\remote.git (fetch)
origin  C:\Users\YK\Desktop\LearnArk\_sandbox\projects\d\r04-s4\remote.git (push)
```

### C. 各次 `sync` 输出（原文关键行）

1. 原机第一次（有远程）:
```
git state: pushed (written=yes, committed=yes, pushed=yes)
  提交文件：7 个（样例：.learnark/journal/dedupe.json, .learnark/journal/events.jsonl, .learnark/project.json, .learnark/state/cards.json, .learnark/state/schedule.json）
  commit: 5250b85  分支: master
```
2. 克隆目录第一次:
```
git state: pushed (written=yes, committed=yes, pushed=yes)
  提交文件：7 个 …
  commit: 50c7496  分支: master
```
3. 原机冲突时:
```
git state: conflict (written=yes, committed=yes, pushed=no)
  提交文件：7 个 … commit: 5f82011  分支: master
  恢复建议：Remote changes conflict with local ones. Nothing was force-pushed; resolve the conflict manually (git status), then run sync again. detail: From …\remote
   5250b85..50c7496  master     -> origin/master
Rebasing (1/1)
error: could not apply 5f82011... learn(proj): 2026-11-04 03:20
```
4. 原机再次 sync:
```
git state: conflict (written=yes, committed=no, pushed=no)
  commit: 5f82011  分支: master
  恢复建议：Remote changes conflict with local ones. Nothing was force-pushed; resolve the conflict manually (git status), then run sync again. detail: From …\remote
   50c7496..844a358  master     -> origin/master
Rebasing (1/1)
error: could not apply 5f82011...
```
5. 克隆目录第二次:
```
git state: pushed (written=yes, committed=yes, pushed=yes)
  提交文件：8 个 …
  commit: 844a358  分支: master
```

### D. 克隆目录 `status` 摘要

- 第一次（03:20:19）：已用 15 / 剩余 5 / 已排 2/2；`未完成：concept_block · eval-harness`；eval-harness L0 observed；下一步（下次）`recall_card · tool-contract`；`同步：written=yes committed=no pushed=no`。
- 最终（03:22:16）：完成 2 项；eval-harness L1；本周块 1/3；下一步（下次）`recall_card · tool-contract`；`同步：written=yes committed=yes pushed=yes（state=pushed）`。

### E. 证据文件

- `SB\evidence\01-init.txt` ～ `SB\evidence\22-status-clone-final.txt`（按步骤编号）
- 关键: `07-sync1.txt`、`10-start-clone.txt`、`12-status-clone.txt`、`13-sync-clone.txt`、`16-sync-proj-diverged.txt`、`17-git-state-proj.txt`、`18-status-proj-conflict.txt`、`20-sync-clone2.txt`、`21-sync-proj-retry.txt`、`22-status-clone-final.txt`
- 项目状态: `SB\proj\.learnark\`、`SB\clone\.learnark\`、`SB\proj\sessions\`、`SB\clone\sessions\`
- 对话原文: `SB\proj\sessions\20261104-031928-trainer.md`、`SB\proj\sessions\20261104-032043-coach.md`、`SB\clone\sessions\20261104-031928-trainer.md`、`SB\clone\sessions\20261104-032007-coach.md`
