# 运行时核心 `learncore` 1.0.5 规范

位置：`shared/core-v1/learncore/`。每个方向在 `variants/<id>/runtime/learncore/` 内置一份**逐字拷贝**，由 `shared/vendor_core.py` 写入，禁止手改；方向逻辑写在自己的模块里。`CORE_VERSION` 必须出现在 `version-manifest.json`。

> 1.0.1：`GitSync.run()` 不再 `strip()` 整个 porcelain 输出（否则第一行状态列空格被吃、第二次同步必坏）。
>
> 1.0.2：分叉恢复——`sync()` 失败后尝试 `recover_diverged()`，只对 journal 做并集合并（按事件 id、重排 seq、重建 dedupe），快照冲突中止并返回真实文件列表；`--recover` 显式入口；生成 `.gitattributes`（`* -text`）与锁/用量忽略项。
>
> 1.0.3：`append_jsonl()` 在追加前修复残尾——若文件末尾缺换行（崩溃留下的半行），只丢弃该不完整尾行；否则新事件会拼到半行上并静默丢失，随后读取报 `StateCorrupt`。
>
> 1.0.5：进一步收紧陷阱——`notes_token.txt`/`tokens.json` 这类以 token 结尾的文件视为凭据并排除，`token-budget.md` 这类“关于 token 的文档”仍可提交。
>
> 1.0.4：`SECRET_PATTERNS` 按**文件名/凭据形状**匹配，不再对整条路径做 `token|secret` 子串搜索——`artifacts/token-budget.md` 这类合法产物可正常提交，`.env`、`*credential*`、`*secret*`、`*.key/*.pem`、`tokens*.json`、`usage.jsonl`、`sync-log.jsonl`、锁/临时文件仍被排除。

## 1. 模块

| 模块 | 提供 |
| --- | --- |
| `fsutil` | `atomic_write_text`、`write_json/read_json`、`load_json_state`（可自 `.bak` 恢复）、`append_jsonl/read_jsonl`、`file_lock`、`find_project_root`、异常 `LearnError/StateCorrupt/StaleWrite/LockTimeout` |
| `clock` | `now/now_iso/today/days_between/add_days/human_age/is_simulated`；`LEARNARK_NOW` 模拟时钟，事件自动标记 `simulated` |
| `events` | `Journal(path).append(kind, payload, dedupe_key=…)`（重复键返回 `None`）、`all/of_kind/last/has/integrity` |
| `store` | `Document(path, default_factory).load/save(expected_version=…)/update(fn)`，CAS 冲突抛 `StaleWrite` |
| `llm` | `LLM`（OpenAI 兼容）、`MockLLM`（按脚本顺序回复并标注 mock）、`from_env()`：`LEARNARK_LLM=api|mock|auto` |
| `mentor` | `run_turn`、`extract_update`、`build_messages`、`validate_updates`、`UPDATE_HELP` |
| `sync` | `GitSync(root, include=[...]).sync(msg)` 返回 `SyncReport(state, written, committed, pushed, files, remote, recovery)`；`ensure_repository`、`commit`、`pull_rebase`、`push`、`status` |
| `cli` | `main(handler)` 统一错误出口、`setup_stdio`（UTF-8）、`table/kv_block/emit_json` |

## 2. 项目目录约定

```
<project>/
  .learnark/                 # 标记目录，git 跟踪
    project.json             # 目标、模板、约束、学习者档案、schema_version
    state/                   # 方向自有快照（Document）
    journal/events.jsonl     # 权威事件流
    journal/dedupe.json      # 幂等索引（可重建）
    handoff/                 # 交接记录（至少 latest.md）
    usage.jsonl              # LLM token 用量（不提交）
  sessions/                  # 每次会话一份 markdown（提交）
  artifacts/                 # 作品/练习产物（提交）
  AGENTS.md                  # 交给 DSH/其他 Agent 的入口说明（生成）
  README.md                  # 给学习者的一页说明（生成）
  .gitignore
```

## 3. CLI 契约（所有方向一致的最小命令面）

| 命令 | 作用 | 要求 |
| --- | --- | --- |
| `init --goal TEXT [--minutes-per-week N] [--template agent-dev\|email] [--dir PATH] [--name SLUG]` | 建立项目、写 project.json、生成 AGENTS.md/README.md、初始化 git | 可重复执行不破坏已有状态 |
| `start [--minutes N]` | 一句话入口：恢复或开始，输出 mentor 开场 + 当前任务 | 首次进入含诊断；返回码 0 |
| `say TEXT` | 学习者发言，得到 mentor 回复并记录 | 自动写会话记录、事件、帮助等级；`say -` 从 stdin 读 |
| `status [--json]` | 当前状态：目标、上次会话、能力/薄弱、下一步、同步状态 | 含“下一步做什么” |
| `pause [--note TEXT]` | 结束本次学习：写 handoff、保存、sync | 输出 restored/next 提示 |
| `switch MENTOR` | 切换导师/会话，写 handoff 契约 | 未知导师要报错并列出可选值 |
| `sync [--message TEXT]` | git 同步，真实报告三态 | 无远程时明确说明 |
| `doctor` | 自检：状态可读、日志完整、锁、git、API 配置 | 输出问题列表与修复建议 |
| `export --out FILE` | 导出可读学习档案（Markdown） | 不泄密 |
| `probe`/`next`/`review` 等 | 方向特有 | 必须在 START_HERE 中说明 |

全局约定：
- 在项目内可省略 `--project`；从任意子目录通过 `.learnark/` 向上定位。
- `--json` 至少 `status` 支持。
- 离线模式：`LEARNARK_LLM=mock` 或 `--offline`；输出必须标注“离线脚本导师”。
- 退出码：0 成功；2 用法错误；3 状态/并发冲突；4 环境/网络。
- 所有写操作使用 `dedupe_key`；重复执行不重复计数。

## 4. 导师更新块（机器可读）

```learn-update
{
  "help_level": 0,
  "attempt": {"activity_id": "node-2-apply", "correct": true},
  "misconception": null,
  "next": "下一轮做一次独立迁移题",
  "mastery_delta": 1,
  "artifact": "artifacts/xxx.py"
}
```

- 运行时用 `mentor.extract_update` 提取；`validate_updates` 至少校验 `help_level` 0–3、`attempt` 为对象。
- 非法/缺失 → 记 `mentor_update_invalid` 事件（含 `raw_sha256`、原因），并按“无证据”处理。
- 方向可扩展字段（如 `probe`、`rubric`、`gap`），但必须有 schema 校验和测试。
- 回复正文不得包含该块。

## 5. 会话文件格式（建议）

```markdown
# 2026-11-04 20:12 — SkillMap · 概念导师
- session: <id>  mentor: concept  activity: node-2-explain
- learner: P3/Mia  goal: agent-dev  offline: false

## 学习者
…

## 导师
…

## 记录
- help_level: 1
- attempt: correct=false (activity node-2-apply)
- misconception: 把 RAG 检索当成 Agent 的长期记忆
- next: 用“没有向量库”的约束重讲工具调用
```

## 6. 模拟时钟

- 测试用：`$env:LEARNARK_NOW='2026-11-20T19:00:00+08:00'`。
- 事件会标 `simulated: true`；报告必须写“模拟时间，仅证明调度逻辑”。

## 7. 测试钩子

- `LEARNARK_LLM=mock` + `LEARNARK_MOCK_SCRIPT=<jsonl>`：确定性导师。
- `LEARNARK_PROJECT=<path>`：显式项目根。
- `LEARNARK_DEBUG=1`：打印 traceback。
- 禁止为测试在代码里写死绝对路径或绕过锁。

## 8. 自检命令（每个方向交付前必须全绿）

```powershell
python tests/run_tests.py
python learn.py init --goal "Agent 开发" --dir <tmp>
python learn.py start --offline
python learn.py say "我不太确定 RAG 和 Agent 记忆的区别" --offline
python learn.py status
python learn.py pause
python learn.py sync
python learn.py doctor
```
