# SkillMap 8 轮实验计划（0.1.0 基线）

对应 `../design.md` 第 12 节。每轮必须完成：提出可检验假设 → 改实现或场景 → 真实独立体验者按场景卡使用 → 反馈分诊 → 修复 → 由未参与修复者定向复测 → 落证据。只跑测试或只改文案不算一轮。

规则：
- 交互预算沿用 `shared/scenarios/personas.md`：每场景 ≤12 次师生往返，达到上限即停并记录未完成原因。
- 判据一旦写下不得为「通过」而放宽；证伪时按 `design.md` 第 2 节的替代解释改实现。
- 体验报告路径统一为 `experiments/<round>/experience-<场景>-<画像>.md`，原始证据放 `experiments/<round>/evidence/`。
- 模拟时间必须标注「模拟时间，仅证明调度逻辑」；模拟学习者数据只证明系统行为。

| 轮次 | 假设 | 实现变更 | 场景/画像 | 预期证据 | 收敛判据 |
| --- | --- | --- | --- | --- | --- |
| 1 | H1 前半 + H5：显式地图与可解释 `next` 能减少迷路；诊断 + 地图解释 ≤4 次往返、≤8 分钟 | v0.1 闭环：`init/start/say/status/pause`、12 节点 `map.json`、5 题诊断、`next` 输出 3 条理由与被排除节点、`map --json` | S1 / P1（30 分钟） | S1 体验报告、`journal/events.jsonl`（`diagnosis_probe`×5、`stage_entered`、`attempt`）、首个 `activity_id` | 12 轮内完成「诊断 → 1 次真实尝试 → 保存」；阻塞问题 ≤1 且已修复；诊断耗时 ≤8 分钟 |
| 2 | H3：只有 `help_level≤1` 的独立通过才升级，受助完成不虚高 | `learn-update` 字段校验、`assisted_completion` 事件、examiner 阶段零提示强制、`misconception` 写入 map、`level_cap` | S2 / P2（20 分钟，答错并接受反馈） | help_level 事件序列、`level_up` / `assisted_completion` 计数、map 中的错因、S2 报告 | 注入 `help_level=2` 正确尝试 2 例均无 `level_up`；`help_level=1` 独立通过恰好 +1；P2 的「把检索当记忆」被具体指出并入库 |
| 3 | H2：诊断结论能改变首个学习任务；四导师自动切换不产生冲突安排 | 四导师按阶段自动 switch + `handoff` 契约（from/to/reason/unresolved/context_digest）、`start` 恢复输出、`switch` 受限角色集 | S3 / P3（两段各 10 分钟，中间杀进程）；另加 P1、P2 两套诊断档案对照 | 前后两份 `handoff/latest.md`、两次 `sessions/`、切换前后 `map.json` 对比、两档案首个 `activity_id` | 切换后 0 条互相矛盾的安排；恢复不重复已完成内容；P1 与 P2 首个活动不同且前 3 个目标节点差 ≥2 |
| 4 | R4/R5：仅凭项目文件可恢复；同步三态报告准确 | `sync` 三态（written/committed/pushed）、干净克隆后 `find_project_root` 定位、`doctor` 自检项 | S4 / P3（本机裸仓库模拟远程） | 克隆目录 `start` 输出、`git log --oneline`、三态输出与 `git status` 对照 | 克隆目录 `start` 定位到同节点同阶段；written/committed/pushed 与 git 实际一致；无远程时明确说明未验证 |
| 5 | H1 后半：20 分钟会话能只推进一个阶段而不硬塞整课 | `--minutes` 预算裁到「一次一阶段」、跨会话续段提示、`stage_timeout` 落断点 | S5 / P3（严格 20 分钟）；加 P1 短时对照 | S5 报告、阶段完成率、`pause` 输出的下一步、`stage_timeout` 次数 | 20 分钟内完成 1 个阶段且 `pause` 给出可执行下一步；同一活动不在两次短会话重复出现 |
| 6 | R6：地图机制可迁移到非编程主题，而不是只换标题 | email 模板换成 6 节点写作地图（结构与语气、称呼、请求明确性、坏消息、简洁、校对）+ 写作 rubric 与写作诊断 3 题，沿用同一 L0–L3 门槛 | S6 / P4（20 分钟，非编程） | 邮件项目 `map.json`、诊断题、`sessions/`、评级证据 | 写作节点证据不含代码产物；`map` 与 `next` 输出全为写作节点；闭环「诊断→活动→反馈→保存→重开」成功 |
| 7 | 上一轮遗留的阻塞与重要问题可被修复且不回归 | 按 `issues.md` 优先级修复；不改阈值、不删测试；相邻流程补回归用例 | S7 定向复测（未参与修复的体验者），覆盖启动/保存/恢复 | 修复记录（问题编号→改动→复测）、S7 报告、回归结果 | 阻塞项全关闭且有独立复测证据；启动、保存、恢复三条相邻流程回归通过；无新增阻塞 |
| 8 | H4 + 复习全链：先修门控与 `[1,3,7,16,35]` 调度在时间推进下正确；新体验者仅凭入口可用 | `review` 到期队列、间隔前进/后退、降级与 `decayed`、`stuck` 检测、`gate_override` 上限锁 L1 | S8 全新体验者（全新上下文）+ S4/S5 回归 | S8 报告、A-S1–A-S6 逐项结果、模拟时间下的 `review` 输出 | S8 10 轮内完成「开始→活动→尝试→反馈→保存→新进程恢复」；A-S1–A-S6 全绿或给出有理由的不适用；独立验收无未关闭阻塞 |

## 轮次之外的固定动作

- 每轮结束更新 `issues.md`（记录来源、影响、责任人、修复版本、复测证据、状态）。
- 每 2 轮产出一次检查点记录（CP3–CP6），写清通过/失败/未测试，不隐藏失败轮次。
- 第 8 轮后由独立验收决定收敛；未通过的假设写入 `version-manifest.json` 的 `known_limits`。
