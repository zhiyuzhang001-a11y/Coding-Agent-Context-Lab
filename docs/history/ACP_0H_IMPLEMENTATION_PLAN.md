# ACP-0H 正式任务书：Measurement Hardening v1

- 状态：`ACP-0H Measurement Hardening v1 — COMPLETE`
- 日期：2026-08-18
- 与主线关系：可与 ACP-1.0 并行；不是重新打开 ACP-0
- 完成形态：有限的 `ACP-0H v1 COMPLETE`，不是永久 `ONGOING`
- Online collector：冻结；除安全、数据损坏或宿主兼容性故障外不得修改

## 目标

> 在不增加分析能力、不改变测量语义和 online collector 行为的前提下，提高实验 provenance、artifact chain of custody、重新校准与 benchmark 治理的可信度。

ACP-0H 只让仪器更容易复验和追责，不回答“Token 为什么浪费”或“应该怎样优化”。

## 与 ACP-1 的并行规则

- ACP-1.0 的合同、schema、fixture 和离线实现可以立即开始，不等待 ACP-0H。
- H0.1 Environment Provenance 与 H0.2 Artifact Chain 必须在 ACP-1 第一次昂贵、正式、需要冻结结论的模型实验之前完成。
- H0.3 Recalibration Automation 与 H0.4 Benchmark Governance 可和 ACP-1.0 离线 baseline 并行，但必须在 `ACP-1.0 COMPLETE` 冻结前完成。
- ACP-0H 任务不得占用 ACP-1 的语义设计权限，也不得以“仪器还能更完美”为理由无限阻塞主线。

## H0.1 Environment provenance

正式 experiment manifest 至少记录：

```text
experiment_id
started_at / completed_at / time_block
codex_version
host_binary_sha256
model_identifier
reasoning_effort
os / architecture
hook_api_version_or_unknown
config_digest
sandbox_digest
environment_allowlist_digest
collector_sha256
normalizer_sha256
reporter_sha256
```

隐私规则：只保存允许字段和 digest；不得保存完整环境变量、凭据、用户名、绝对 home path 或原始 config 正文。无法可靠取得的版本必须写 `unknown`，不得猜测。

## H0.2 Artifact chain of custody

建立版本化 `experiment-manifest-v1`，至少关联：

```text
fixture_sha256
runner_sha256
spec_sha256
environment_manifest_sha256
collector_sha256
raw_private_artifact_sha256
normalized_result_sha256
coverage_ledger_sha256
fact_report_sha256
public_compact_result_sha256
```

私有 artifact 只在 Git ignored、权限受限目录中保存；公开 manifest 可以保存 hash 和语义状态，但不得复制 transcript、prompt、源码或完整命令。manifest 生成必须确定性，缺失阶段显式为 `not_produced` 或 `unknown`。

实施记录（2026-08-18）：已冻结 `resources/acp0h_experiment_manifest_schema.json` 的 `experiment-manifest-v1`，并由 `scripts/build_experiment_manifest.py` 生成。生成器只接受封闭 environment allowlist；本地 artifact/host binary 路径只用于计算 SHA-256，不进入输出。环境摘要、artifact 状态与 checksum chain 决定稳定 `experiment_id`，测试覆盖确定性、路径不落盘、未知字段拒绝、缺失状态和内容变更传播。

## H0.3 Automatic recalibration

分两档：

1. `smoke-calibration-v1`：collector/normalizer/reporter、schema 或 deterministic pipeline 代码变化时运行，覆盖 hash、privacy allowlist、fixture replay、determinism、fail-open 和 traceability。
2. `paired-no-interference-v1`：仅在 host/model/Hook API/online collector path/关键 measurement semantics 变化时运行，复验 cost、path、correctness parity、host transparency 和 collector coverage。

触发器必须由 manifest diff 判定，不用人工记忆。昂贵 suite 不在每次文档或离线 reporter 修改时运行。

实施记录（2026-08-18）：已冻结 `acp-calibration-state-v1`、`acp-recalibration-policy-v1` 与 `recalibration-decision-v1`。`scripts/decide_recalibration.py` 从 `experiment-manifest-v1` 加封闭组件摘要派生无路径 calibration state，并确定性比较前后状态。normalizer/reporter/attributor/renderer、schema、fixture 或 expected canonical output 变化触发 `smoke-calibration-v1`；host/model/Hook API/OS/architecture/config/sandbox/environment allowlist/collector online path/measurement semantics/collector 变化触发 `full_paired`，且自动包含 smoke。25-case 合成矩阵覆盖 unchanged、全部单字段变化、unknown transition 与 smoke/full 混合优先级；所有变化原因均保留，不 cherry-pick。

## H0.4 Benchmark governance

每个正式 case 必须携带：

```text
benchmark_role
native_qualification_status
native_repetitions
oracle_and_scorer_version
expected_coverage_path
allowed_gate_usage
```

`benchmark_role` 只允许：

- `stable_gate`
- `stochastic_diagnostic`
- `coverage_probe`
- `failure_injection`

新增 case 必须先 Native qualification，再进入正式 Gate。旧 case 永久保留；如需 v2，创建新 ID，不覆盖历史 fixture。stochastic case 只能使用预注册 distribution/parity criterion，不能作为 absolute 100% correctness Gate。

实施记录（2026-08-18）：已冻结 `acp-benchmark-registry-v1` 与 `acp-benchmark-governance-v1`。当前12项历史 case 全部迁移且未删除：8 `stable_gate`、2 `coverage_probe`、1 `failure_injection`、1 `stochastic_diagnostic`；11项 active，`single_file_range_count` 为 diagnostic-only。新 stable case 必须依次完成 ground-truth audit、20次 Native calibration（至少19次正确）、分类、registry freeze 后才能 suite admission。旧11项 5/5 证据只作为 registry `1.0.0` 的一次性历史迁移例外；stochastic case 禁止进入 absolute correctness、cost 或 path Gate。validator 校验 fixture/question/answer/evidence hash、版本身份、supersedes/retirement、qualification 与 gate usage。H0.4a 集成补充将 `co1_4_observe_replay@1` 作为独立 `formal_baseline_input` 完成 hash qualification 与 active admission，不借用 no-interference case 身份。

## 明确不做

- 不新增或修改 collector 分析逻辑；
- 不修改 `acp-event-v1` 的语义来承载实验环境正文；
- 不做 cost attribution、waste、avoidable、recommendation；
- 不做 replacement、slicing 或实时 Agent 反馈；
- 不追溯改写 ACP-0.4/0.4a/0.4b verdict。

## ACP-0H v1 完成标准

- [x] provenance schema、manifest 生成器与隐私测试完成；
- [x] `experiment-manifest-v1`、确定性 checksum chain 与缺失状态测试完成；
- [x] smoke/full recalibration 触发矩阵可机器判定，并已用完整合成 change matrix 验证；
- [x] benchmark role/qualification schema 与当前 12-case 迁移记录完成；
- [x] ACP-1 首次正式实验已生成完整 manifest，且 manifest 直接绑定 baseline index，index 再绑定所有派生 artifact；
- [x] 全部 ACP-0 冻结 hash、collector 行为和历史结果保持不变；collector 与 Hook manifest 分别保持 `81efee8b...96de2` 与 `797b72b6...4dd`。

全部通过，状态冻结为 `ACP-0H v1 COMPLETE`。以后环境变化触发的是重新校准操作；只有发现 hardening 合同缺口时才规划新的 ACP-0H v2。
