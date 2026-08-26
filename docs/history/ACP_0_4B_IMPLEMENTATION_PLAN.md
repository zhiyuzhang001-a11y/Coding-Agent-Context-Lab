# ACP-0.4b 正式任务书：Correctness Gate Audit and Redefinition

- 状态：`COMPLETE / ACP_0_GRADUATION_PASS`
- 日期：2026-08-18
- 唯一审计 case：`single_file_range_count`
- 冻结前提：ACP-0.4 `FAILED_COST_NEUTRALITY` 与 ACP-0.4a `INCONCLUSIVE / GRADUATION_FAIL` 永久保留
- 非目标：修改 collector、重算旧结果、删除失败 run、改变 Token `1.02` Gate、replacement、slicing、recommendation、waste metrics 或 ACP-1

## 目标与顺序

0.4b 只关闭 0.4a 暴露的 correctness benchmark validity 缺口：

1. 冻结题目、ground truth、scorer、答案形态 taxonomy 与 Native 分类阈值；
2. 运行 `single_file_range_count` Native/OFF-only ×20；
3. 冻结 `empirically_stable_gate` 或 `stochastic_diagnostic` 分类；
4. 在分类冻结后，只对该 case 运行全新 OFF/ON 各 20 次 correctness closure；
5. 结合 0.4a 已冻结的 cost/path/host 证据判断 ACP-0 是否毕业。

## Specification audit

冻结 subject commit 为 `b506818b3db87be62064ad64e62b1ad262d5a4b9`。`merged_line_count` 的两处 `end - start + 1` 明确使用闭区间，`start <= current_end + 1` 明确合并重叠或相邻区间。输入 `(1,3),(4,5),(9,10)` 的两个贡献为 5 和 2，唯一返回值为 `7`。

题目问给定函数调用的返回值，0/1-based 行号与空行均不影响结果。scorer 对最后一个 agent message 做首尾空白剥离后与字符串 `"7"` 精确比较。审计结论固定为 `unambiguous_existing_case`；不创建 v2，不修改原 fixture。

## 0.4b-1：Native calibration

- 只运行 OFF，不加载 ACP marketplace、Hook 或 collector；
- 原问题、oracle、commit、model、reasoning effort 保持不变；
- 固定 20 次，completed、failed、timeout、异常答案与 Token outlier 全进 denominator；
- 不允许只重跑某个错误样本；
- 每次保存 answer、correctness、tool calls、model cycles、Token 与观察性 answer-shape category。

答案形态只描述可见最终答案，不推断隐藏 reasoning：`correct`、`off_by_one_like`、`first_cluster_only_like`、`endpoint_like`、`other_integer`、`malformed_or_missing`、`execution_failure`。

在读取结果前冻结分类：

- correct count `19–20/20`：`empirically_stable_gate`；
- correct count `0–18/20`：`stochastic_diagnostic`。

这是工程分类，不声称 20 次样本构成统计学稳定性证明。

### Native calibration 冻结结果

OFF-only 20/20 run 完成并全部进入统计：correct `14/20`，因此按预注册边界分类为 `stochastic_diagnostic`。错误答案形态为 `endpoint_like=3`、`off_by_one_like=2`、`first_cluster_only_like=1`；20/20 run 均为 1 tool call、2 model cycles。结果冻结于 `resources/acp0_4b_native_calibration_results.json`，不补跑错误样本。

## 0.4b-2：Prospective correctness closure

只对该 case 产生全新 OFF/ON 各 20 次，repetition 内交替 AB/BA 顺序；全部 run 进入 denominator。

- 若为 `empirically_stable_gate`：要求 ON correct count `≥19/20` 且不低于 OFF correct count；
- 若为 `stochastic_diagnostic`：要求 `accuracy_ON - accuracy_OFF ≥ -0.10`；
- 两类均报告答案形态、tool-call、cycle 与 Token 分布，但这些 correctness runs 不进入 cost/path Gate；
- ON 必须观察全部实际 tool calls，collector 不发起工具调用，host transparency/fail-open 必须继续通过。

最终 graduation 组合使用：0.4a 已冻结且通过的 `pooled ratio ≤1.02`、无预注册 path signal 和 host/collector 证据，加上本阶段 prospective correctness criterion。0.4a 的旧 verdict 与四个错误 run不改写；0.4b 是新的独立 closure evidence。

## Prospective closure 冻结结果

40/40 个全新 run 完成并进入统计：OFF `12/20=0.60`，ON `13/20=0.65`，`accuracy_ON - accuracy_OFF = +0.05 ≥ -0.10`，prospective correctness Gate 通过。两臂每次均为 1 tool call、2 model cycles；20/20 ON tool calls 被 collector 观察，collector 未发起工具调用，host transparency/fail-open 通过。

本轮 correctness runs 未进入 cost/path Gate。组合 0.4a 的 pooled ratio `1.007010 ≤1.02`、无预注册 path signal、95% conditional path coverage 与 host Gate 后，ACP-0 graduation 为 `PASS`，正式冻结 `ACP-0 Measurement Foundation — COMPLETE`。

该结论是预注册工程 Gate 的通过，不声称 20×2 小样本构成统计学因果证明。ACP-0.4 的失败和 ACP-0.4a 的 inconclusive 均保留为历史事实；详见 `resources/acp0_4b_results.json`。
