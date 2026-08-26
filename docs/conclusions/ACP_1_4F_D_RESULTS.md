# ACP-1.4F-D：Benchmark Development Pool 结果

- 日期：2026-08-19
- 状态：`COMPLETE`
- 冻结 verdict：`BENCHMARK_SEMANTICS_NOT_SUPPORTED`
- ACP-1.4F v3：`NOT AUTHORIZED`
- R1/S1/B1：`FROZEN / NOT TESTED`

## 结论

24 个冻结 development cases 没有形成足够多样且稳定的 observed evidence-family coverage。只有 `search_like` 达到至少3个 qualified case；`read_like` 与 `structured_bash_like` 均为0。因此未达到预注册的两家族 subset 下限，更未达到三家族 holdout 下限。

这个 verdict 不评价 intervention generalization。Builder、collector、Hook mutation、Treatment 与 R1/S1/B1 均未启用；结果只否定当前 development pool 与冻结 qualification semantics 作为三家族 v3 benchmark 的充分性。

## 执行与自动停止

- Screen：72/72 completed；7 case 进入 Extension，17 case 被 Screen futility 拒绝。
- Extension 后总计：110 completed，0 failed；低于240-run硬上限。
- runner 在剩余 runs 已不可能形成第二个 supported observed family 时自动停止，没有机械跑满121。
- 沙箱内首次预检在0 completed result 时中断，已单独冻结为 aborted preflight，不计入110次正式 run。

## 主要结果

- correctness：110/110；
- evidence opportunity：110/110；
- compatible carrier：110/110；
- measurement unknown：0；
- unresolved truncation：0；
- qualified：4/24，全部为 `search_like`；
- rejected：20/24；
- reason codes：`F_EVIDENCE_TOO_SMALL` 20、`F_INTERVENTION_NOT_MEANINGFUL` 20、`F_TOOL_PATH_UNSTABLE` 1。

四个 qualified cases 均为稳定 `bash_rg → search_like`：

- `d_search_delta_maintenance_v1`：10/10；
- `d_search_delta_retired_v1`：10/10；
- `d_search_epsilon_archive_v1`：10/10；
- `d_search_zeta_quarantine_v1`：10/10。

其余三个 Screen-admitted cases 在 Extension 中触发 futility：

- `d_search_epsilon_legacy_v1`：4 runs 后 meaningful recurrence 已不可达；
- `d_search_zeta_retention_v1`：9 runs 后 meaningful recurrence 已不可达；
- `d_bash_zeta_status_v1`：6 runs 后 evidence family 为 `read_like 3 / search_like 3`，dominant recurrence 与 meaningful recurrence 均不可达。

## 科学解释边界

任务本身是稳定可答的，失败不来自 correctness 或 evidence identity。自然 Agent 基本将 Read、Search 和 Structured 设计意图都折叠成窄 `rg` 查询：24 case 中23个最终 dominant observed family 为 `search_like`，另1个没有唯一 dominant family。大量返回只有个位数或几十个 estimated tokens，低于冻结的200-token meaningful threshold。

因此当前证据支持：case-independent classifier 能找到 evidence opportunity，但这个任务池不能稳定诱发三个 intervention-relevant evidence families，也不能为多家族 reduction generalization 提供准入载体。

## 冻结决策

- 不创建 ACP-1.4F v3；
- 不建立新 holdout；
- 不修改、测试或解冻 R1/S1/B1；
- 不降低 meaningful threshold 或 family Gate；
- 不把 development cases 混入未来 formal statistics；
- 若继续研究，必须以新的科学问题和新 protocol version 重新立项，旧110 runs 只作 benchmark-development evidence。

冻结索引：`resources/acp1_4f_d_frozen_final_index.json`。
