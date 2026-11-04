# 交接契约 handoff（direction C · Atelier）

运行时负责写交接（组装文件、校验、注入上下文），导师只负责读和提案。权威来源是正文末尾的 `handoff` 机器块；YAML 头只是给人看的摘要，不参与校验。

## 1. 不变量

- 切换导师前必须先落一份合法 handoff；没有它不得进新会话。
- 交接只写可核对的事实，每条能追到事件 id 或会话文件。
- 历史文件不改写，只追加新文件并重写 `latest.md`。
- 下一导师的上下文只注入 `latest.md`，不注入完整历史。

## 2. 触发条件

`switch`；`pause` / `stop`（from=to=self）；`examine`；`plan_change` 被应用；`start` 时 `latest.md` 缺失或超过 7 天（记 `stale_handoff` 后补）。

## 3. 文件与时间戳

路径 `.learnark/handoff/<YYYYMMDDTHHMMSS>-<from>-to-<to>.md`，例如 `20261104T201200-coach-to-examiner.md`。文件名时间戳去冒号以适配 Windows；ISO 时间（含 `+08:00`）只出现在文件内容与事件里。同一秒冲突以 `handoff_id` 为准，不覆盖旧文件。

文件头可放 YAML 摘要（from/to/why/created_at/plan_snapshot），仅作人读；内容字段一律以机器块为准，只写在 YAML 里视为缺失。

## 4. 机器块（权威）

```handoff
{"handoff_id":"H-0012","schema_version":1,"from":"coach","to":"examiner","why":"仅在一级提示下通过，需独立验证","known":["能写 tool schema","知道结果要回注消息"],"what_tried":["w2-tools-ex2 两次，第二次 help_level=1 通过"],"do_not_redo":["不再讲「函数+参数+结果回注」三段式"],"open_loops":[{"id":"OL-7","owner":"examiner","due":"2026-11-05","text":"独立完成一次迁移题","blocking":true}],"next":"换场景考一次幂等重试","created_at":"2026-11-04T20:12:00+08:00"}
```

必填 9+2：`from/to/why/known/what_tried/do_not_redo/open_loops/next/created_at`，加 `handoff_id`、`schema_version`。

分工（v0.2.1）：`handoff_id/from/to/created_at/schema_version` 由运行时写入，不接受模型值；`known/what_tried/open_loops/next/do_not_redo` 由运行时从 journal、会话与计划合成；导师只提供 `why`（缺省“用户点名”）。容量：known 与 what_tried 各 ≤5 条、每条 ≤120 字，do_not_redo 注入 ≤6 条（可为空），open_loops ≤5 条，next ≤200 字。

## 5. 好例与坏例

好例即上一节：why 说明切换的必要性，what_tried 记录做了什么与帮助等级，open_loops 有 owner 与 due，next 含动词与对象。

坏例：

```handoff
{"handoff_id":"H-0013","from":"coach","to":"examiner","why":"换一下","known":["学得不错"],"next":"继续加油"}
```

缺 `what_tried`、`do_not_redo`、`open_loops`、`created_at`、`schema_version`；`known` 是评价不是事实；`next` 无法执行。

## 6. 缺失字段怎么办

- 默认（v0.2.1）：运行时能合成全部内容字段，`switch/pause/examine/review` 默认成功；导师没有提案也只会缺 `why`，用默认理由。
- `say` 永不因交接失败丢回合：先落学习者消息、导师回复、会话，再处理可选交接；失败记 `handoff_rejected{reason,missing}` 并留在当前导师，退出码 0。
- 唯一严格路径：显式 `switch --strict` 要求导师提案含 `why/what_tried/open_loops/next`；缺任一 → 不写文件、不切换、退出码 3，列出缺项并记 `handoff_invalid{missing,raw_sha256}`。
- `--fill-missing` 仍可把严格模式缺项按记录补齐，标 `degraded:true` 并记 `handoff_degraded`；不得静默补齐。

## 7. do_not_redo 如何维护

- v0.2.1 只记录**明确说过**的条目（导师 `do_not_redo` 字段 / 学习者“不要再讲/讲过了”等原话），记 `do_not_redo_recorded`；空列表是正常的，不从未发生的事件推断。
- 追加不覆盖，条目带日期与出处（事件 id 或题目 id）。
- 合并：同主题只留最新一条，旧条标 `superseded-by:`。
- 过期：30 天未触及或 examiner 复测 `pass` 后可移入 `archived`；移除须写 `removed:<原因>` 并记 `dnr_retired`，不静默删除（归档/退役尚未实现，见 version-manifest）。
- 上限 12 条、注入 ≤6 条；超出归档且不再注入。
- 冲突：保留更晚的一条，开 `loop-dnr-conflict` 交 planner 裁定。
- 进入去重表（归一化哈希）：新导师首个任务或类比命中 → 重新生成一次，仍命中记 `repeat_detected`，要求换表征。
