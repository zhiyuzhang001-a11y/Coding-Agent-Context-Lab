# ACP-1.4F-R Native Path / Benchmark Semantics Audit Results

- 状态：`COMPLETE under read-only audit scope`
- 日期：2026-08-19
- 审计出口：`PROCEED_TO_BENCHMARK_DEVELOPMENT_POOL`
- 新 Agent runs：`0`

## 结论

ACP-1.4F v2.1 的 early stop 不是 intervention generalization failure。现有54次 completed Native run 显示：冻结 identity 与完整 trajectory Gate 比 request-related、intervention-compatible evidence recurrence 更严格，因而阻断了实验载体。

本审计不修改 v2.1 的 `INSUFFICIENT_NATIVE_COVERAGE`，也不重分类任何历史 case。它只支持建立独立 benchmark-development pool；不授权新的 Agent run。

## 总体事实

- completed/correct：`54/54`；
- measurement unknown：`0/54`；
- 唯一 request-related evidence opportunity：`54/54`；
- 唯一 intervention-compatible carrier：`54/54`；
- v2.1 candidate recurrence：`42/54`；
- identity false negative：`12/54`；
- 含工具发现或非 command-execution 元调用的 run：`19/54`。

公开结果不保存 raw command、raw output、final answer、run ID、绝对路径或私有正文。

## Read 诊断

四个 Read case 的40次 completed run 都只产生一个 request-related `bash_sed` evidence carrier，carrier recurrence 均为 `10/10`。

- `f_read_alpha_retry_v1`：历史 dominant path `9/10`，兼容 carrier `10/10`；
- `f_read_alpha_maintenance_method_v1`：历史 dominant path `7/10`，兼容 carrier `10/10`，3个 run 含额外元调用；
- `f_read_beta_result_limit_v1`：历史 dominant path `5/10`，兼容 carrier `10/10`，8个 run 含额外元调用；
- `f_read_gamma_batch_size_v1`：历史 dominant path `5/10`，兼容 carrier `10/10`，5个 run 含额外元调用。

后三个 case 标记为 `PATH_GATE_MISMATCH`：真正的读取 carrier 稳定，完整 trajectory 因工具发现/非执行调用数量不同而分裂。第一个 case 的历史 path Gate 已通过，因此只标记 `STABLE_AT_EVIDENCE_LEVEL`。

## Search 诊断

14次已完成 Search-family run 全部只产生一个 request-related `bash_rg` carrier。

- `f_search_alpha_maintenance_status_v1`：兼容 carrier `10/10`，v2.1 recurrence `2/10`，identity false negative `8/10`；
- `f_search_beta_archive_category_v1`：当前前缀兼容 carrier `4/4`，v2.1 recurrence `0/4`，identity false negative `4/4`。

false negative 来自冻结 identity 要求命令重复 project-form term，而自然 `rg` 经常以 `.` 表示 scope。审计器只有在 query term 出现在命令中，且 project-form path 出现在命令或结构化结果路径中时，才把 `.` scope 认作 request-related；没有通过最终答案或 scorer 反推。

第一个 Search case 同时标记 `IDENTITY_MISMATCH` 与 `PATH_GATE_MISMATCH`。第二个只有4次 completed prefix，因此保留 `INSUFFICIENT_DIAGNOSTIC_EVIDENCE`，不外推为10次 qualification 结果。

## 没有得到的结论

- 没有测试 R1/S1/B1；
- 没有证明任何 reduction rule 有效或无效；
- 没有证明所有等价 Host tools 都应归入同一 evidence family；当前观察实际只有 `sed` 与 `rg`；
- 没有 Bash-family Native path 诊断数据；
- 没有授权20–30个 development probes；
- 没有创建 v2.2 或 v3；
- 没有把54次历史 run 纳入未来正式统计。

## 工程修复设计

新增纯函数 `scripts/acp1_4f_futility.py`，为未来新版本 runner 提供两层计算：

1. case 内根据剩余 repetitions 计算 correctness、recurrence、ambiguity 与 dominant-path Gate 是否仍可达到；
2. case/family 间计算每 family 与 overall maximum achievable qualified count。

一旦冻结 coverage Gate 已数学上不可能，应返回 `STOP_FUTILITY`。该 helper 没有接入或修改 v2.1 runner，避免改变冻结执行路径。

## 下一阶段边界

下一步可以设计独立 benchmark-development pool，但开始任何新 Agent runs 前必须另行冻结：

- development sampling frame；
- tool family、evidence family 与 carrier taxonomy；
- correctness/evidence recurrence/path entropy/truncation 指标；
- development 与 future holdout 的物理隔离；
- 自动 futility checkpoint 与停止规则；
- development data 永不进入 future formal statistics。
