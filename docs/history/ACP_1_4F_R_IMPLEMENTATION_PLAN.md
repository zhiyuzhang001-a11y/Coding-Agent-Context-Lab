# ACP-1.4F-R：Native Path / Benchmark Semantics Audit

- 状态：`R-0/R-1 COMPLETE under read-only audit scope`
- 日期：2026-08-19
- 前置：ACP-1.4F v2.1 `STOPPED — INSUFFICIENT_NATIVE_COVERAGE`
- Agent run budget：`0`

## 一句话目标

> 判断 v2.1 Native qualification 的失败是在测量真实的 evidence-strategy instability，还是把具体 Host tool/trajectory 的随机性误当成 intervention-relevant evidence instability。

本阶段不是 intervention generalization test，不运行或修改 R1/S1/B1，不创建 v2.2/v3，不恢复 v2.1。

## 冻结科学边界

v2.1 的结论保持：冻结的 prospective sampling frame 与 Native qualification design 无法提供足够 coverage。由于 Builder、collector、Hook 和 intervention 均未使用，F-R 不得把该结论表述为 reduction rule 泛化失败。

F-R 只消费冻结的公开 artifact 与54份既有私有 completed-run artifact。旧 run 不重分类、不重评分、不进入未来正式统计。

## 为什么需要拆分分析层级

当前 v2.1 同时存在两种较强约束：

1. candidate recurrence 要求自然命令包含全部冻结 `required_command_terms`；
2. dominant path 哈希整个有序工具序列，包括 tool family、executable kind、candidate relation 和 success semantics。

因此 `Search(query)`、`Bash(rg query)`、使用项目名 scope 和使用 `.` scope 可能取得同类 evidence，却被判为不同 candidate 或不同路径。F-R 必须分别观察：

- task correctness；
- request-related evidence opportunity；
- intervention-compatible carrier；
- 具体 Host tool path。

## R-0 — Audit contract

审计合同位于 `resources/acp1_4f_r_audit_contract.json`，在展开私有命令/结果语义前冻结：

- closed evidence basis；
- forbidden inputs；
- evidence family 与 carrier allowlist；
- classification order；
- entropy、recurrence 与 dominant-frequency 指标；
- privacy-safe public output；
- 三种审计出口。

审计不得使用 oracle expected value、scorer 或最终答案来选择 evidence。请求中的 subject path、query、anchor 和 command intent 属于事前输入，可以用于建立 request relation。

## R-1 — Existing 54-run read-only audit

逐 run 解析既有 transcript 中已完成的本地工具调用，形成私有诊断记录；公开结果只保存聚合计数、标准 carrier label、reason code 与 digest。

必须回答：

1. v2.1 `candidate_recurred=false` 时，是否仍存在唯一 request-related compatible carrier；
2. path signature 不同时，compatible carrier/evidence family 是否仍相同；
3. 是否存在 correct-without-external-evidence；
4. 当前12个任务中，哪些只是 tool selection 自由，哪些是真正 evidence acquisition 不稳定；
5. 现有证据是否足以支持建立独立 benchmark-development pool。

历史 `8/10` 仅作为描述性参照，不用于重判 v2.1 qualification。

R-1 已完成，结果见 `ACP_1_4F_R_AUDIT_RESULTS.md` 与 `resources/acp1_4f_r_audit_result.json`。审计出口为 `PROCEED_TO_BENCHMARK_DEVELOPMENT_POOL`；该出口表示 development pool 的设计具备证据基础，不自动授权新 Agent runs。

## R-2 — Benchmark-development protocol（条件阶段）

只有 R-1 出口为 `PROCEED_TO_BENCHMARK_DEVELOPMENT_POOL` 且获得单独授权后，才建立20–30个候选任务的 development pool。

development registry 至少记录：

- correctness stability；
- tool-family recurrence；
- evidence-family recurrence；
- intervention-compatible carrier recurrence；
- dominant-path entropy；
- candidate recurrence；
- host truncation risk；
- oracle independence；
- qualification status。

development data 不进入未来 formal statistics。未来 formal universe 必须来自新的 holdout tasks，并在 sampling、identity、Gate 与 futility policy 冻结后才运行。

## Automatic futility stop 设计要求

未来 Native runner 必须在每次 completed attempt 后计算：

- 当前 case 在剩余 repetitions 全成功时是否仍可达到所有 case Gate；
- 每个 family 在剩余 cases 全 qualified 时的 maximum achievable qualified count；
- overall maximum achievable admitted count。

如果任一冻结 coverage Gate 已数学上不可能满足，应立即写入 checkpoint 并返回 `STOP_FUTILITY`。已完成、interrupted 与未开始 run 分开保留。该改进只进入未来新版本 runner，不修改或恢复 v2.1 runner。

## 审计出口

### `PROCEED_TO_BENCHMARK_DEVELOPMENT_POOL`

现有证据显示具体 Host path 不稳定，但 request-related、intervention-compatible evidence opportunity 具有可测量的跨 case 结构，值得建立独立 development pool。

### `BENCHMARK_SEMANTICS_UNSUITABLE`

自然任务无法在无 oracle、可预注册条件下形成稳定 evidence opportunity，或 Host 输出无法可靠区分相关载体；不应通过降低 Gate 继续。

### `INCONCLUSIVE`

54-run prefix 或 telemetry 不足以区分 identity/path mismatch 与 genuine evidence instability。

## 明确不做

- 不称 v2.1 为 generalization failure；
- 不修改 v2.1 verdict、Gate、case status 或 artifact；
- 不降低 `8/10` 让历史 case 通过；
- 不运行 Treatment、pilot 或 formal；
- 不把 Bash `rg` 自动视为 Search 等价，必须按冻结 carrier/relation 规则审计；
- 不用答案、scorer 或人工“正确行”定义 evidence；
- 不启动 development pool Agent runs，除非 R-1 支持且另行授权。
