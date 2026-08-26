# ACP-1.3C Validation Scope

- 状态：`COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- Baseline ID：`acp1-3c-natural-intervention-candidate-registry-v1`
- Registry：`resources/acp1_3c_candidate_registry.json`
- Index：`resources/acp1_3c_frozen_registry_index.json`
- Manifest：`resources/acp1_3c_frozen_experiment_manifest.json`

ACP-1.3C 只证明在冻结 repository revision、model、reasoning effort、题面、candidate identity 和 Native-only 运行设计下，两个自然任务具备进入 ACP-1.3D 的资格。它没有执行 intervention，不证明任何 evidence 可避免。

## 已证明

- 80 个正式 Native run 均 completed with usage 且 correctness 通过；
- 4 个 case 均使用预注册的 logical identity，没有 ambiguous multiple-match；
- `natural_signature_limit_v1` 以 recurrence/path `18/20 / 18/20` 通过；
- `natural_command_shape_v1` 以 recurrence/path `20/20 / 18/20` 通过；
- `natural_truncate_budget_v1` 因 path `13/20` 仅为 diagnostic；
- `natural_navigation_counts_v1` 因 recurrence/path `13/20 / 13/20` 被拒绝；
- registry 不允许 ACP-1.3D 消费 diagnostic/rejected case。

## 未证明

- 未创建 Control/Treatment pair，未删减或改写 tool evidence；
- target visible Token 分布只是资格事实，不是 wasted/avoidable volume；
- 历史 ACP-1.2 candidates 仍不可 replay；
- production Host rewrite 仍 blocked，Transparent Smart Read 仍冻结；
- 两个 qualified case 只在当前冻结范围有效，不表示其他任务也可稳定消融。

## 重新校准条件

subject commit、model/reasoning effort、host binary/API、题面/ground truth、identity terms/size threshold、path semantics、runner/scorer 或资格阈值任一变化，都必须生成新 registry version；不得覆盖本次分类。
