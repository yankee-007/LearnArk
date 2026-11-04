# RESUME — 断点续跑说明

> 最近更新：2026-11-04 13:35（核心 1.0.5 统一验证后）

## 当前真实状态

- **direction-a-skillmap** v0.2.4 core 1.0.5: 体验报告 6 份（R1–R6），修复记录 6 份，可靠性测试 yes，CP2 有
- **direction-b-forge** v0.2.4 core 1.0.5: 体验报告 6 份（R1–R6），修复记录 6 份，可靠性测试 yes，CP2 有
- **direction-c-atelier** v0.2.4 core 1.0.5: 体验报告 6 份（R1–R6），修复记录 6 份，可靠性测试 yes，CP2 有
- **direction-d-tempo** v0.2.6 core 1.0.5: 体验报告 6 份（R1–R6），修复记录 6 份，可靠性测试 yes，CP2 有

## 已通过的最终验证（core 1.0.5）

- 核心自测 24/24。
- A: run_tests 51/51, reliability 24/24。
- B: reliability 27/27（完整 42/42 在 1.0.4 上通过；1.0.5 只改密钥正则）。
- C: reliability 36/36（完整 80/80 在 1.0.4/1.0.3 上通过；1.0.5 只改密钥正则）。
- D: reliability 25/25（完整 50/50 在 1.0.4 上通过；1.0.5 只改密钥正则）。
- vendor_core --check-all: core 1.0.5 全部一致。

## 未完成

1. R7 定向复测、R8 最终新体验者、独立验收报告（4 份）。
2. 在最终提交上重跑 B/C/D 的完整套件（1.0.5 只改 SECRET_PATTERNS，仍要留最终证据）。
3. 总入口 START_HERE、comparison、final-report、issues 汇总。
4. 框架仓库 push 到本地裸仓库 + 干净克隆验证；真实 GitHub/跨设备未验证。

## 已知计数

- 每方向有效轮次 = 6（R1–R6 均有独立体验 + 修复 + 复跑）；R7/R8 未开始，不虚报。
- 研发岗位 16 个均已创建；4 个可靠性 Agent 已产出测试/文档/CP2。
- 体验者 24 人次；其中 B 的 S5 误读禁读报告，已披露。
