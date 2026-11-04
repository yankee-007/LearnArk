# 体验报告 — direction-b-forge 0.2.2 round-04 S4（Git 同步 + 干净克隆恢复）

- 版本: `direction-b-forge 0.2.2`（vendored learncore 1.0.1，schema_version 1；见 `version-manifest.json`）
- 体验者: 独立子 Agent（DeepSeek Harness / deepseek-flash 独立上下文，非研发者）；模拟画像 P3 Mia
- 场景: S4（P3：两周前学过 function calling，今天只有 20 分钟，想在另一台电脑继续）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r04-s4\proj`
  - 克隆目录: `...\b\r04-s4\clone`；裸仓库（模拟远程）: `...\b\r04-s4\remote.git`
- 入口: `python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-b-forge\runtime\learn.py <命令>`（cwd = 项目目录）
- 交互预算: 上限 8 次学习者往返（本任务），实际使用 **6 次 `say`**（start 三问用一条 `--answers` 非交互提交，未逐条计往返）；约 24 条产品命令 + 30+ 条只读 git 核对命令
- 真实 LLM: `deepseek-chat`（无 `--offline`）；本机裸仓库只是模拟远程，**本地 Git 流程验证，真实 GitHub 未验证**

## 实际步骤（命令 + 关键输出摘要）

1. **建项目**
   `init --goal "Agent 开发" --dir . --minutes-per-week 10 --self-report "python=会一点,api=调用过 function calling"`
   → `已创建…目标：Agent 开发｜模板：agent-dev｜当前里程碑：M1｜下一步：do_task`，并 `git init`（`EXIT=0`）。
2. **首次进入 + 20 分钟切片**
   `start --ask --answers "大概能,做过一次demo没跑通,今天只有20分钟" --minutes 20`
   → `起点档案（已记录）：{"api": "大概能", "tools": "做过一次demo没跑通", "mode": "今天只有20分钟"} → M1-first（standard，20 分钟切片）`；
   → 首轮布置：读 `in.txt` 数字求和的最小可跑版，`▶ 唯一动作：do_task`。
3. **第 1 轮真实交流（含第 1 次尝试）**
   学习者真实写了 `m1/agent.py`（读 `in.txt` 逐行 `int` 求和）与 `in.txt`（17、25），运行
   `python m1/agent.py` → `42`（`EXIT=0`）。
   `say "<命令+输出+两周前 function calling 的模糊记忆+tool_call_id 422 的旧错>"`（参数方式）发送；
   → 导师：`先写工具定义，不接模型…加 TOOLS 列表与非法输入返回 {"error": …}`；`help_level=2`，`▶ do_task`。
4. **第 2 轮真实交流（第 2 次尝试）**
   学习者改写 `m1/agent.py` 增加 `TOOLS`（`add_numbers`，a/b 为 number）与 `add_numbers()` 校验函数，本地验证：
   `json.dumps(TOOLS)` 正常、`{"a":2,"b":3} → {'result': 5.0}`、`{"a":"abc","b":3} → {'error': 'a and b must be numbers'}`。
   第 2 轮 `say`（内联 `say TEXT`）被 PowerShell 5.1 吞掉双引号并截断在 `description: Return`；
   导师按「截断输入不猜原因」规则要求用 `say -` 从 stdin 重发（**第 3 轮=重发**）。重发后导师：
   `可以登记，但先补一处——arguments 是 JSON 字符串`，仍 `▶ do_task`。
5. **登记作品 + 记录状态**
   `artifact add m1/agent.py` → `a-M1-364cbe89  sha256=364cbe896e9b  size=964  assisted_level=2`，下一步 `review`。
   `status` → 作品 1 件、上次会话 4 轮、`git：branch=- remote=无 changed=18 ahead=0 behind=0`、下一步 `review`。
6. **裸仓库 + 远程 + 第一次 sync**
   `git init --bare …\remote.git`；项目内 `git remote add origin …\remote.git`；`git remote -v` 指向该路径。
   `sync --message "M1 最小工具定义"` →
   ```
   git state: pushed (written=yes, committed=yes, pushed=yes)
     written=yes（文件已落盘） committed=yes（fcca44d） pushed=yes
     本次提交 18 个文件  remote=…\remote.git
   ```
   核对：`git log --oneline` 为 `fcca44d (HEAD -> master, origin/master)`；`git ls-remote origin` 与裸仓库 `log` 均为
   `fcca44d`；上游 `origin/master` 已建立。**三态与事实一致**。
   但 sync 结束瞬间 `git status -sb` 即为脏：`M .learnark/journal/{dedupe.json,events.jsonl,journal.lock} ?? .learnark/usage.jsonl`
   ——sync 自身写入的事件没有进入本次提交。
7. **干净克隆（模拟另一台电脑）**
   `git clone …\remote.git …\clone` → `fcca44d`，18 个受版本控制文件齐全（无手工复制）。
   在 clone 目录**只运行产品入口** `start` →
   ```
   Forge · Agent 开发
   模板 agent-dev｜当前里程碑 M1「工具调用闭环」 status=active
   ▶ 唯一动作：review（a-M1-364cbe89）
   下一步：review｜作品 a-M1-364cbe89（artifacts/M1/agent.py）已登记但未评审
   切片：20 分钟 … 交付物：m1/agent.py + docs/m1-design.md
   ```
   `status`（clone）→ 起点档案、学习者自述、`帮助等级：最近 L1｜最高 L2｜推断 1 次`、作品 1 件与 sha、
   `上次会话：…（coach，4 轮）`、`git：branch=master remote=…remote.git changed=5 ahead=0 behind=0`、下一步 `review`。
   检索 clone 内 `.learnark/`、`sessions/`，**未出现原项目绝对路径**；`start/status` 无任何路径报错。
   但仅一次 `start` 就把干净工作区变成 5 个改动（`project.json` 的 `updated_at/version`、`state/*.json`、`state.lock`）。
8. **克隆目录继续 1 轮 + sync（第 4 轮交流，干净恢复验证）**
   `say -`（“我换到另一台电脑了… start 显示 M1 与 review a-M1-364cbe89…”）→ 导师：`是，直接 review…`，`▶ review`。
   `sync --message "clone 设备：M1 作品待 review"` → `pushed (written=yes, committed=yes, pushed=yes) c7447bf，10 files`；
   远程与 clone 均为 `c7447bf → fcca44d`。**三态与事实一致**。
9. **模拟冲突（可选步骤，第 5、6 轮交流）**
   - 原项目（落后 1 个提交）第 5 轮 `say -` 补记 `arguments 需要 json.loads`；导师回复与状态**矛盾**：
     说“这台设备上我没看到 artifact add 的记录”，但同项目 `artifact list` 明确有 `a-M1-364cbe89`，`status` 也显示作品 1 件。
   - 原项目 `sync --message "旧设备补记 arguments 解析"` →
     ```
     git state: conflict (written=yes, committed=yes, pushed=no)
       written=yes（文件已落盘） committed=yes（5730be8） pushed=no
       本次提交 9 个文件
       恢复：Remote changes conflict with local ones. Nothing was force-pushed; resolve the conflict manually (git status), then run sync again. detail: Rebasing (1/1)
     error: could not apply 5730be8... 旧设备补记 arguments 解析
     [git 的 rebase 提示：… git rebase --continue / --abort …]
     ```
     实际状态：reflog 显示 **`rebase (abort): returning to refs/heads/master`**，`rebase-merge/` 不存在，
     `git ls-files -u` 无任何冲突文件，`git status -sb` = `[ahead 2, behind 2]`。即产品已中止 rebase，
     但恢复文案却让人“解决冲突后重跑 sync”。
   - 按提示重跑 `sync` → 又生成提交 `6af80cc`（`重试`，只含 journal/lock 噪声）并再次 `conflict … detail: Rebasing (1/2)`，再 abort。
     重试没有解决冲突，只是让本地多背一个提交，`detail` 从 1/1 变 1/2。
   - 原项目 `doctor` 在 `ahead=2 behind=2`、sync 连续失败的情况下 → `[ok] git …`、`自检通过：0 个错误，0 个提示。下一步：review`（`EXIT=0`）。
   - 克隆目录第 6 轮 `say -` 补记 review 证据诉求（导师回答合理，仍 `▶ review`），`sync` →
     `pushed (written=yes, committed=yes, pushed=yes) c56c9bd，9 files`；远程变为线性 `c56c9bd → c7447bf → fcca44d`，
     **没有 force push、没有改写历史**。原项目本地 `5730be8/6af80cc` 仍在，双方成果都未被覆盖，但原项目永远无法推上去。
10. **克隆后能否继续（补充验证）**
    在 clone 执行 `▶ 唯一动作 review` → 成功产生 `r-M1-364cbe89`（runnability/contract/robustness=2，explainability=1，4 张缺口卡），
    说明“继续学习”主流程可走；但同一 clone 上 `doctor` 却报
    `[FAIL] 作品文件：a-M1-364cbe89 sha256 与记录不一致（文件被改回或篡改）（退出码 3）`。
    核对：原项目 `artifacts/M1/agent.py` sha=`364CBE89…`（0 个 CRLF），clone 同文件 sha=`E5408097…`（41 个 CRLF）；
    系统 `C:/Program Files/Git/etc/gitconfig` 为 `core.autocrlf=true`，仓库没有 `.gitattributes`。**review 能用，doctor 判“被篡改”，两套结论矛盾。**

## 三态与事实核对（逐次）

| # | 位置 | sync 报告 | 事实核对 | 结论 |
| --- | --- | --- | --- | --- |
| 1 | proj | written=yes, committed=yes(fcca44d), pushed=yes | 本地/远程/裸仓库均为 fcca44d | 准确 |
| 2 | clone | written=yes, committed=yes(c7447bf), pushed=yes | 远程 log 含 c7447bf | 准确 |
| 3 | proj | written=yes, committed=yes(5730be8), pushed=no | 远程无 5730be8；本地有 | 准确（但恢复文案不可执行） |
| 4 | proj 重试 | written=yes, committed=yes(6af80cc), pushed=no | 远程仍无；本地多一提交 | 准确（重试导致提交膨胀） |
| 5 | clone | written=yes, committed=yes(c56c9bd), pushed=yes | 远程 log 含 c56c9bd | 准确 |

结论：**written/committed/pushed 三个布尔值本身没有说谎**；问题在“committed=yes ≠ 工作区干净”和冲突后的恢复指引。
`git remote -v`（两处）均指向 `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r04-s4\remote.git`；
`git log --oneline` 见附录。

## 完成情况

- 开始: **成功**（init + start，三问写入 start_profile，20 分钟切片生效）
- 定位/恢复: **成功**（clone 中仅 `start` 即恢复 M1、review、作品 sha、切片、上次会话；无原路径依赖、无报错）
- 尝试与反馈: **成功**（2 次真实尝试：求和脚本、TOOLS+校验；导师分别给出 schema 任务与 JSON 字符串入口提醒；help_level 2/1 可见）
- 保存/同步: **成功**（5 次 sync 三态经 git 核对）
- 克隆后继续: **基本成功**（review 可执行）；但 doctor 对作品 sha 误报，克隆的“完整性健康”不可信
- 冲突: **失败**（不覆盖、不 force push 做到了；但产品内无法恢复，重试循环，doctor 仍全绿）
- 切换导师: 不适用（S4 未要求）

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| sync 明确告诉我哪些落盘、哪些提交、哪些推到远程 | 五个布尔值均与 git 事实一致，还给出 commit hash | 14-sync-1 / 20 / 24 / 25 / 28 |
| 干净克隆后 `start` 能接着上次学，知道下一步 | 恢复 M1、review、作品 sha、20 分钟切片、4 轮会话；无原路径报错 | 17-clone-start / 18-clone-status |
| 克隆后能继续真实学习动作 | `review` 成功产出评分与缺口卡 | 33-clone-review |
| sync 后仓库是干净的 | 每次 sync 后 `git status` 都有 journal/lock/usage 改动；`committed=yes` 但工作区脏 | 15-git-verify / 30-clone-status-after |
| 两个设备都改过时，产品告诉我在哪冲突、怎么解 | 报 conflict 后立即 abort rebase，无冲突文件，`git status` 无可解决项；重试只增加提交、再次失败 | 24 / 25 / 34 |
| 失败后跑 `doctor` 能得到诊断 | 分叉 + sync 连续失败时 `doctor` 报「自检通过：0 个错误」 | 26-doctor-proj |
| 干净克隆后作品 sha 校验通过 | Windows autocrlf 把 LF 换 CRLF，clone 作品 sha 与记录不符，doctor exit 3 | 35-sha-crlf / 31-doctor-clone |
| `status` 的 behind 能反映远程新提交 | clone 推送后、未 fetch 前仍显示 `behind=0`，手工 `git fetch` 后为 `behind=1` | 23-proj-status-before-divergence-sync |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | **阻塞**（跨设备冲突恢复） | `sync` 遇远程分叉会 `pull --rebase` 后 abort，保留本地；但恢复文案要求“resolve the conflict manually (git status), then run sync again”。abort 后 `git status` 没有任何 `UU` 冲突文件，无法按提示操作；重跑 `sync` 只新增本地提交并再次 abort（detail 1/1→1/2），形成死循环。没有 `sync --ours/--theirs`、`pull`、`merge` 或任何产品级解法，普通学习者只能手工合并 `.learnark/state/*.json`。 | 设备 A `sync` 推送 → 设备 B clone 后 `say`+`sync` 推送 → 设备 A `say`+`sync` → 观察 conflict/abort → 再 `sync` | `_evidence\24-sync-proj-divergence.txt`、`25-sync-proj-retry.txt`、`34-rebase-evidence.txt` |
| 2 | **重要** | 同步事实状态误导：`status` 的 `behind` 用本地缓存的 remote ref，clone 推送后仍显示 `behind=0`（需手工 fetch 才变 1）；`doctor` 在 `ahead=2 behind=2` 且 sync 连续失败时仍 `[ok] git` + 「自检通过：0 个错误」。用户无法从产品判断“我落后/分叉了”。 | 在 clone 里 `sync` 推送；回到 proj 立即 `status`（behind=0）→ `git fetch`（behind=1）；冲突后 `doctor`（0 错误） | `_evidence\23-proj-status-before-divergence-sync.txt`、`29-proj-status-after.txt`、`26-doctor-proj.txt` |
| 3 | **重要** | Windows 干净克隆后作品 sha256 与登记值不一致：`autocrlf=true` 把 `artifacts/M1/agent.py` 从 LF 换成 CRLF，`doctor` 报「文件被改回或篡改」exit 3；仓库无 `.gitattributes`。同一 clone 上 `review` 却能正常使用该作品，完整性结论自相矛盾。 | `git clone` 到新目录 → `doctor`；对比 proj/clone 文件 sha 与 CRLF 数 | `_evidence\31-doctor-clone.txt`、`35-sha-crlf.txt` |
| 4 | **重要**（仓库卫生，放大冲突） | `journal.lock`、`state.lock` 被 git 跟踪，且每次命令都变；`.gitignore` 的 `.learnark/*.lock` 匹配不到嵌套 `journal/journal.lock`，`.learnark/state/usage.jsonl` 也与实际 `.learnark/usage.jsonl` 不符。后果：`start` 一次就让干净 clone 变 5 个改动，每次 sync 都“自愿”提交锁文件，冲突时这些噪声也参与 rebase。 | clone 后只跑 `start` → `git status --porcelain`（5 项）；`git ls-files` 查 lock；`git check-ignore -v .learnark/usage.jsonl` | `_evidence\15-git-verify.txt`、`30-clone-status-after.txt`、`35-sha-crlf.txt` |
| 5 | 一般 | 导师第 5 轮说“这台设备上我没看到 artifact add 的记录”，与同项目 `artifact list`/`status` 的 `a-M1-364cbe89` 明确矛盾；虽 `▶` 行动行仍为 review，但可能诱导学习者重复登记作品。 | proj 已有作品后 `say`（换设备/补记类消息）→ 对比导师文本与 `artifact list` | `_evidence\21-proj-say-divergence.txt`、`22-proj-artifact-list.txt` |
| 6 | 一般（摩擦，非缺陷） | PowerShell 5.1 下内联 `say TEXT` 含双引号/花括号时被吞引号并截断（本次存成半句 `description: Return`）；产品按规则 8 要求 stdin 重发，恢复正确，但浪费 1 次往返。START_HERE 已建议长文本用 `say -`。 | `say "含 {\"a\": 1} 的文本"` → 查看 `sessions/*.md` 存储内容 | `_evidence\07-say-2.txt`、`sessions\20261104-031928-coach.md` |

## 使用负担

- 师生往返: **6 次 `say`**（上限 8；其中 1 次因 PowerShell 截断重发）+ start 三问一条命令  产品命令: 约 24 条  只读 git 核对: 30+ 条
- 需要阅读的文档: 3 处产品文档（`START_HERE.md`、生成的 `README.md`、`AGENTS.md`）+ 任务卡/personas/brief
- 不清楚的地方:
  - 冲突后到底该跑什么命令？文案说“手动解决”，但 `git status` 里没有可解决的冲突。
  - `doctor` 全绿是否代表可以继续跨设备？实际它在分叉时仍全绿，在干净 clone 上又误报作品被篡改。
  - `status` 的 behind 何时刷新？看起来只有 sync/fetch 之后才准。
  - 锁文件为什么在版本库里？每次启动都让工作区变脏。

## 结论

- 是否完成场景目标: **主线完成，冲突恢复未完成**。
  - 已验证：本地裸仓库的三态输出真实；干净 clone 后只凭 `start` 能恢复里程碑/下一步/作品/切片/会话，且不依赖原路径；`review` 能在 clone 中继续；全程没有 force push、没有改写远程历史，双方提交都保留。
  - 未完成：两个设备都产生学习记录后，产品无法在自身命令内合并/恢复；重试 `sync` 只会反复 abort 并堆提交；`doctor` 与 `status` 在关键时刻给出的健康/同步状态不可信。真实 GitHub 推送与远程分叉仍未验证（本次仅为本地裸仓库模拟）。
- 最需要修的一件事: **给 `sync` 一个可执行的冲突恢复路径**（例如产品级合并/选择保留策略、或至少把 rebase 保持在可解决状态并给出具体文件与命令），同时让 `doctor/status` 如实报告 ahead/behind 与冲突态。

## 附录

### A. `git log --oneline`

```
# 裸仓库 remote.git
c56c9bd clone 设备：补记 review 证据诉求
c7447bf clone 设备：M1 作品待 review
fcca44d M1 最小工具定义

# 原项目 proj（分叉，ahead 2 / behind 2）
6af80cc (HEAD -> master) 重试
5730be8 旧设备补记 arguments 解析
fcca44d M1 最小工具定义

# 克隆 clone
c56c9bd (HEAD -> master, origin/master, origin/HEAD) clone 设备：补记 review 证据诉求
c7447bf clone 设备：M1 作品待 review
fcca44d M1 最小工具定义
```

### B. `git remote -v`（proj 与 clone 相同）

```
origin  C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r04-s4\remote.git (fetch)
origin  C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r04-s4\remote.git (push)
```

### C. 克隆目录 `status` 摘要（`start` 后、继续前）

```
Forge · Agent 开发
模板 agent-dev｜当前里程碑 M1「工具调用闭环」 status=active｜导师 coach｜离线=否
起点档案：{…"mode": "今天只有20分钟"} → M1-first（standard，20 分钟切片；answered=True）
学习者自述：{"python": "会一点", "api": "调用过 function calling"}
帮助等级：最近 L1（coach）｜最高 L2（coach）｜推断 1 次
作品：1 件｜最新 a-M1-364cbe89 … sha=364cbe896e9b assisted_level=2
最近评审：无
上次会话：20261104-031928-coach（coach，4 轮），进行中
git：branch=master remote=…\remote.git changed=5 ahead=0 behind=0
下一步：review｜作品 a-M1-364cbe89 已登记但未评审
切片：20 分钟 …
```

### D. 关键证据文件（均在 `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\b\r04-s4\_evidence\`）

`01-init`、`02-start`、`05-say-1`、`06-tools-check`、`07-say-2`（截断）、`08-say-3-stdin`、`09-artifact-add`、
`14-sync-1`、`15-git-verify`、`17-clone-start`、`18-clone-status`、`19-clone-say-1`、`20-sync-clone-1`、
`21-proj-say-divergence`、`22-proj-artifact-list`、`23-proj-status-before-divergence-sync`、
`24-sync-proj-divergence`、`25-sync-proj-retry`、`26-doctor-proj`、`27-clone-say-2`、`28-sync-clone-2`、
`29-proj-status-after`、`30-clone-status-after`、`31-doctor-clone`、`32-all-logs`、`33-clone-review`、
`34-rebase-evidence`、`35-sha-crlf`。
