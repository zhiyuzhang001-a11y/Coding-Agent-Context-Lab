# ACP-0.4a 正式任务书：Repeated Runs + Variance Attribution

- 状态：`INCONCLUSIVE / GRADUATION_FAIL`
- 日期：2026-08-17
- 重复次数：每 case 每 arm 固定 5 次
- 正式规模：12 cases × 2 arms × 5 repetitions = 120 runs
- 继承阈值：pooled session Token ratio `≤ 1.02`
- 冻结对象：`acp-collector-v0.1`、当前 Hook manifest、ACP-0.4 task set 与 ACP-0.4 失败结论
- 非目标：修改 collector、放宽 Gate、删除 outlier、重跑单个不利场次、replacement、slicing、recommendation 或 ACP-1 分析

## 目标

> 用预注册的完整重复矩阵，区分 Agent 自身路径方差与 collector 可能造成的系统性路径或条件成本变化。

ACP-0.4 的 `FAILED_COST_NEUTRALITY` 永久保留。run7 是提出本阶段问题的 pilot，不作为 ACP-0.4a repetition；0.4a 使用 120 个全新 run。

## 实验设计

- 同一 frozen subject commit、task manifest、model、reasoning effort、sandbox 和 expected oracle；
- 每个 repetition 都包含全部 12 cases 和 OFF/ON；不允许只重跑某个 pair；
- 奇数 repetition 沿用原 AB/BA，偶数 repetition 反转 arm 顺序；case 顺序按 repetition 确定性轮转；
- 所有 completed、failed、timeout、outlier 都进入 denominator 和结果记录；
- 在线路径仍只有逐字 hash 校验后的 collector 与 Hook manifest；Normalizer/Reporter 不进入 Agent loop。

## 两种 neutrality

### Path neutrality

冻结 path signature：

```text
tool_entry
tool_call_count
model_cycle_count
tool_family_sequence
```

报告每 case/arm 的 tool-entry rate、call/cycle 分布和 path-signature 频数。不得用完整命令、result body 或完整 result hash 定义路径。

预注册的 possible-systematic-path signal 为任一成立：

- pooled ON tool-entry rate 比 OFF 高至少 `0.10`；
- pooled ON mean tool calls 或 model cycles 比 OFF 高至少 `0.25`；
- 至少 8/12 cases 的 ON mean tool calls 或 cycles 高于 OFF。

这些是小样本证据分类阈值，不宣称统计显著性或因果证明。

### Conditional cost neutrality

仅在同 case、相同冻结 path signature 同时出现在 OFF/ON 时比较 Token。每个 stratum 取双方排序后前 `min(n_off,n_on)` 个 run，报告 matched coverage、Token distribution 和 ratio。

Conditional 分析是机制诊断，不能替代全部 run 的总体 pooled Gate；若 collector 改变路径概率，条件化可能掩盖总效应。

## 报告指标

- 每 case/arm：count、mean、median、min、max、MAD；
- tool-entry 次数/比例；tool-call、cycle 与 Token 分布；
- path signature 频数；
- all-run pooled Token ratio；
- case-balanced median-of-case-median ratio；
- comparable-path coverage 与 conditional pooled ratio；
-全部 outlier 和 invalid run 数，不静默过滤。

## 判定

硬门仍包括：120/120 runs 有 usage、60/60 ON tool calls 全被 collector 观察、correctness 零回归、host/fail-open 继续通过、collector 不发起工具调用。

输出两个正交结论：

1. `attribution_conclusion`
   - `likely_stochastic`：无预注册 path signal，且 comparable-path coverage ≥ 0.5；
   - `possible_systematic_effect`：出现预注册 path signal；
   - `inconclusive`：硬门不完整或 comparable-path coverage < 0.5。
2. `graduation_verdict`
   - `pass`：硬门通过、pooled ratio ≤1.02、无 path signal、attribution 非 inconclusive；
   - `fail`：硬门失败、pooled ratio >1.02 或出现 path signal；
   - `inconclusive`：成本 Gate 通过但路径可比证据不足。

只有 `graduation_verdict=pass` 才能冻结 `ACP-0 Measurement Foundation — COMPLETE`。`likely_stochastic` 本身不构成毕业。

## 正式执行结果（2026-08-18）

120/120 run 全部完成并纳入统计，OFF/ON 各 60 次；run7 pilot、outlier、失败 run 均未混入、删除或单独补跑。collector 与 Hook manifest hash 保持冻结。

- 成本：OFF `2,357,897`、ON `2,374,426` Token，pooled ratio `1.007010 ≤ 1.02`；case-balanced median ratio `1.000482`。
- 路径：tool-entry 均为 `60/60`；mean call delta 与 cycle delta 均为 `+0.016667`，五项预注册 systematic signal 全为 false。
- 条件成本：同 path signature 每 arm 匹配 57 次，coverage `0.95`，conditional pooled ratio `0.999022`。
- 透明性：84/84 ON tool calls 被 collector 观察；host hash、零 stdout/stderr 与 fail-open probes 全部通过；collector 总本地耗时 `7.362 ms`。
- correctness：11 个 case 为 OFF/ON 各 `5/5`；`single_file_range_count` 为 OFF `3/5`、ON `3/5`，四个错误 run 原样保留。因此 `correctness_zero_regression=false`。

正式结论为 `attribution_conclusion=inconclusive`、`graduation_verdict=fail`。重复数据支持“没有可见系统性路径漂移，成本比率通过冻结门槛”，但 correctness 硬门不允许用对称失败抵消或改判；ACP-0 仍不毕业，ACP-1 不开始。冻结结果见 `resources/acp0_4a_results.json`。
