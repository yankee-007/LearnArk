# 真人试用脚本（约 18 分钟）

目的：让你亲自检查四个版本是否可以真的开始、教、记住、恢复和同步。
本脚本**不预写你的反馈**，只给动作和观察点。任何一步卡住都算有效发现，请记下来。

## 0. 准备（2 分钟）

- Python 3.10+ 可用；设置导师密钥（只需一次，当前 PowerShell 会话）：
  ```powershell
  $env:DEEPSEEK_API_KEY = "你的 key"
  $env:PYTHONIOENCODING = "utf-8"
  ```
  如果只想看流程不调用模型，可加 `--offline`（会明确标注“离线脚本导师”，教学内容有限）。
- 从 `START_HERE.md` 选一个方向；下文以 `variants/<id>` 代指。四个方向可以各试一次，也可以只试推荐版本。

## 1. 建一个学习项目（2 分钟）

```powershell
cd C:\Users\YK\Desktop\LearnArk\_sandbox
python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\<id>\runtime\learn.py init `
  --goal "能用 Python 独立做出带工具调用、记忆和错误处理的小 Agent" `
  --minutes-per-week 15 --dir my-learning
cd my-learning
```

观察点：
- 生成了哪些文件？`.learnark/`、`sessions/`、`README.md`、`AGENTS.md` 是否可读？
- `README.md` 是否能在 1 分钟内告诉你“现在该输入什么”？

## 2. 一句话开始（3 分钟）

```powershell
python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\<id>\runtime\learn.py start
```

- 它是否直接告诉你“今天做什么”，还是先问一堆问题/让你读文档？
- 第一屏是否出现“上次停在哪 / 为什么学这个 / 预计多久”中的至少一项？
- 记录：你需要几次操作才真正开始学。

## 3. 学一个小单元（6 分钟）

按导师要求回答；`say "你的回答"`。
- 故意答错一次（例如把 RAG 检索说成 Agent 的记忆模块），看它是否具体指出错在哪、是否给分级提示。
- 故意说“我大概懂了，直接给我答案”，看它是否守住“不能替你完成”。
- 观察：回复长度是否适合 20 分钟；有没有把“看过/听懂”记成“掌握”；能否看到当前帮助等级。

```powershell
python ...\learn.py say "我觉得 Agent 记忆就是 RAG 检索"
python ...\learn.py status
```

## 4. 暂停、离开、回来（3 分钟）

```powershell
python ...\learn.py pause
# 关闭终端（或至少新开一个 PowerShell）
cd my-learning
python ...\learn.py start
```

- 它是否知道上次停在哪、下一步是什么？
- 是否重复已学过的内容、是否把你没做完的任务标成完成？
- `status` 里能否找到“哪里不会 / 用过什么帮助”。

## 5. 换导师（2 分钟）

```powershell
python ...\learn.py status        # 看可选导师
python ...\learn.py switch <导师>
python ...\learn.py say "继续"
```

- 新导师是否知道之前发生了什么？有没有重复解释？
- 两个导师的安排是否冲突（例如一个说复习、一个说开新题）？
- 方向 C 还会让你查看 `handoff` 记录；方向 D 会让你比较 `--minutes 5` 与 `--minutes 30` 的选择差异。

## 6. 同步与换设备（2 分钟，可选）

```powershell
python ...\learn.py sync
```

- 输出是否明确区分“已写入文件 / 已本地提交 / 已推送远程”？
- 没有配置远程时，是否说清楚而不是假装同步成功？
- 如果想验证换设备：把目录复制/克隆到另一个路径，在新路径 `start`，确认能继续。

## 7. 记录（3 分钟）

请只记录事实，不用客气：

| 检查项 | 结果（通过/失败/说不清） | 卡在哪 / 证据 |
| --- | --- | --- |
| 1 分钟内知道该输入什么 | | |
| 首屏给出了明确下一步 | | |
| 答错时得到针对性反馈 | | |
| 没有把“听懂/看过”记成掌握 | | |
| 暂停后新进程能正确恢复 | | |
| 换导师不重复、不冲突 | | |
| 同步状态真实（written/committed/pushed） | | |
| 愿意明天再用一次（1–5 分） | | |

把这张表和一句“最想先修什么”发给研发负责人即可；也可以直接写进 `variants/<id>/experiments/human-trial.md`。

## 说明

- 本脚本用于真人手动试用，不替代模拟体验者的自动记录。
- 如果你使用 `--offline`，教学文本来自脚本而非模型，只用于检查流程；不要据此评价教学质量。
- 你的真实学习记录与研发测试数据分开存放（建议 `_sandbox/my-learning`），不会混入研发证据。
