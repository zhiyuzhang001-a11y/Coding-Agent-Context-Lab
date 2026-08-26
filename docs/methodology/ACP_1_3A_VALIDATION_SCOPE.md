# ACP-1.3A Validation Scope

- 状态：`ACP-1.3A Host-Reported Model-Cycle Cost Analysis — COMPLETE under frozen experiment scope`
- 范围：ACP-0.4a 冻结任务集、模型、reasoning effort 与 120 次历史 run
- Baseline ID：`acp1-3a-acp0-4a-host-cycle-cost-v1`
- Index：`resources/acp1_3a_frozen_baseline_index.json`
- Manifest：`resources/acp1_3a_frozen_experiment_manifest.json`

ACP-1.3A 只证明 host-reported cumulative usage snapshot 在 cycle ordinal 上的观测分布。它不证明 cycle 增加的因果效应，不证明历史上下文重复处理量，不证明任何 Token 可避免。

## 已证明的事项

- 120/120 run 仅通过 exact thread/session ID 完成唯一关联；
- 287 个 cumulative usage snapshot 均满足 counter 单调、Token identity 和 frozen result final-usage parity；
- OFF/ON 各 60 run 分开报告，12 个 case 保留 case strata；
- cycle 1→2 的 within-run incremental ratio median 在 OFF/ON 分别为 `1.025937891418 / 1.025928058203`；
- cycle 2→3 分别为 `1.020076212141 / 1.022400270835`；
- 因此在当前冻结范围的 cycle 1–3 中，观测增量只呈温和上升，不支持宣称已发现快速加速形状。

## 不足与 unknown

- cycle 4 每臂 `n=1`，仅保留为 insufficient-sample diagnostic；
- cycle count 与 session total 受任务难度、路径与自选择进入后续 cycle 的混杂，不是因果 slope；
- cached input 不是语义历史上下文；new/history decomposition 保持 unknown；
- 未执行 intervention，因此 counterfactual added-cycle cost、necessity、avoidability 和 savings 均未证明。

## 重新校准条件

host usage-event 语义、Token counter identity、模型、任务集、extractor 或 private source inventory 任一变化，必须重新生成 baseline；不得把本结论外推到未观测的更多 cycle。
