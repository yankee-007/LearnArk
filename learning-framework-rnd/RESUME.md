# RESUME — 断点续跑说明

> 状态：2026-11-04 用户要求主动收尾停止。这不是“全部完成”，而是“在安全点停下并交付”。

## 已交付（可核验）

- 四个方向可运行：A SkillMap 0.2.4、B Forge 0.2.4、C Atelier 0.2.4、D Tempo 0.2.6；core 统一 1.0.6。
- 每方向 R1–R6：6 份真实 LLM 独立体验报告 + 6 份修复记录（共 24 + 24）。
- 每方向可靠性套件：`tests/test_reliability.py`、`docs/recovery.md`、`experiments/CP2-reliability.md`。
- 最终验证（core 1.0.6）：核心 25/25；A 51/51+24/24；B 42/42+27/27；C 80/80+36/36；D 50/50+25/25；`check_variant --all` 18/18×4；`vendor_core --check-all` 一致。
- GitHub `main` 已推送；干净克隆 247 文件，克隆内 core 24/24 且 A 离线 E2E 通过。

## 未完成（不得虚报）

1. R7 定向复测、R8 最终新体验者（0 次）——每方向有效轮次为 6/8。
2. 独立验收报告 0 份；`shared/acceptance.md` A1–A11 未执行。
3. `comparison.md`、`final-report.md`、总入口 `START_HERE.md` 未写。
4. 真实 GitHub 学习项目同步、真实跨设备、真人学习效果均未验证。
5. 各方向 `issues.md` 的一般改进项未逐条复测。

## 续跑顺序

1. `evaluation/prompts/round-07.md` → 用各方向 `issues.md` 的“已修复”阻塞/重要项做复测。
2. `evaluation/prompts/round-08.md` → 全新上下文，只读 `START_HERE.md`。
3. `evaluation/harness/acceptance-brief.md` + `shared/acceptance.md` → 四份 `acceptance-report.md`。
4. `comparison.md`、`final-report.md`、总入口；学习项目单独建 GitHub 仓库验证跨设备。

## 历史与决策

- 两次中断已记录在 `orchestration/agents.json` `incidents`：API 402（5 个子 Agent 失败，失败不计完成）、C 方向写冲突（已冻结可靠性写入）。
- `learning-framework-rnd` 原独立 git 历史：`_sandbox/archive/learning-framework-rnd-history.bundle`（本地，未推送；`_sandbox` 不入 Git）。
- 核心修复史见 `shared/spec-core.md`：porcelain 前导空格 → 分叉 journal 合并 → 残尾追加 → 密钥匹配收紧 → 嵌套仓库隔离。
