# Round 04 体验任务 — S4 Git 同步与干净克隆恢复（P3 Mia）

你是**独立体验者**（模拟学习者），不是研发者。读完再开始。

## 情境

- 你换了一台电脑，想继续同一个学习项目。
- 没有真实的 GitHub 账号可用，因此用**本机裸仓库**模拟远程与“另一台设备”。
- 目标：确认同步状态真实、克隆后能继续、冲突不会静默覆盖。

## 基本信息

| 项目 | 值 |
| --- | --- |
| 轮次 | round-04 |
| 场景 | S4 Git 同步 + 干净克隆 |
| 交互预算 | 8 次师生往返以内（多数是命令） |
| 导师模式 | 真实 LLM API（少量对话即可），不要 `--offline` |
| 原始项目 | `_sandbox\projects\<a\|b\|c\|d>\r04-s4\proj` |
| 克隆项目 | `_sandbox\projects\<a\|b\|c\|d>\r04-s4\clone` |
| 裸仓库 | `_sandbox\projects\<a\|b\|c\|d>\r04-s4\remote.git` |
| 报告 | `variants\<方向目录>\experiments\round-04\experience-S4-P3.md` |

路径表：A=`direction-a-skillmap`，B=`direction-b-forge`，C=`direction-c-atelier`，D=`direction-d-tempo`。

## 开始前

```powershell
. C:\Users\YK\Desktop\LearnArk\_sandbox\env.ps1
$env:PYTHONIOENCODING='utf-8'
```

只读：本文件、`learner-brief.md`、`START_HERE.md`。禁止读源码/设计/测试/历史报告。

## 任务

1. 新建项目，`start` 并做 2 轮真实交流（至少 1 次尝试），`status` 记录当前状态。
2. 新建裸仓库并配置远程（在项目目录）：
   ```powershell
   git init --bare <remote.git 路径>
   git remote add origin <remote.git 路径>
   ```
3. 用产品命令 `sync`。记录它如何描述 written / committed / pushed。
4. 克隆到 `clone` 目录（`git clone <remote.git> <clone>`），在新目录中只凭产品入口 `start`，检查：
   - 是否知道上次停在哪、下一步是什么；
   - 是否把记录带过来了（会话/能力/下一步）；
   - 是否有任何依赖原路径的东西报错。
5. 在克隆目录继续 1 轮交流，再 `sync`。
6. （可选，若时间允许）模拟冲突：在原始项目改一条学习记录并 `sync`，回到克隆目录先本地改另一条再 `sync`，观察是否保留双方、是否要求人工处理、是否 force push（不允许）。
7. 记录：三态是否准确、克隆后恢复是否完整、失败时是否给出恢复方法、是否覆盖了任何一方成果。

## 注意

- 本机裸仓库只是**模拟远程**，报告中必须写“本地 Git 流程验证，真实 GitHub 未验证”。
- 不要手工把文件复制到 clone 里；必须走 git 克隆。
- 不要 force push、不要删远程、不要改产品代码。

## 报告

使用 `personas.md` 模板。附：`git log --oneline`、`git remote -v`、各次 `sync` 输出、克隆目录 `status` 摘要。
阻塞 → 记录原文并停止。

完成后回复：报告路径、完成与否、三态是否准确、Top 3 问题、往返次数。≤250 字。
