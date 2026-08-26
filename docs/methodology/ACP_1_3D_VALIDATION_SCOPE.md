# ACP-1.3D Validation Scope

- 状态：`COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- Baseline ID：`acp1-3d-qualified-natural-controlled-ablation-v1`
- Formal result：`resources/acp1_3d_results.json`
- Index：`resources/acp1_3d_frozen_ablation_index.json`
- Manifest：`resources/acp1_3d_frozen_experiment_manifest.json`

ACP-1.3D 只证明：在冻结 repository revision、host/model、两个由 ACP-1.3C 准入的自然任务、预注册 Treatment 和 Gate 范围内，确定性的 source-level evidence ablation 激活后保持了冻结的 correctness、tool-path、cycle 与 success-semantics 要求。它是 causal experiment harness 的局部证据，不是 production slicing，也不是全局节省证明。

## 已证明

- 4 个 plumbing pilot run 通过且未混入正式统计；
- 正式实验完成 2 case × Control 20 + Treatment 20，共 80/80 run；
- 两个 case 的 Control/Treatment correctness 均为 `20/20`，Treatment-only failure 均为 0；
- `natural_signature_limit_v1` 的 paired evidence reduction median 为 `62.609971%`，tool/cycle delta median 均为 0；
- `natural_command_shape_v1` 的 paired evidence reduction median 为 `49.696233%`，tool/cycle delta median 均为 0；
- 两个 case 的 G1–G8 均通过，因此 verdict 均为 `PASS`；
- session-cost effect 与 behavior verdict 分开：pooled Treatment/Control ratio 分别为 `0.967792` 与 `0.839889`，只标记为冻结实验中的 `observed_reduction`；
- collector、Hook manifest 与 ACP-1.3C registry/index/manifest 哈希保持不变。

## 必须保留的异常与限制

- `natural_signature_limit_v1` 有 1/20 Control 未出现 qualified logical target，故 comparable pair 为 19；该 run 未删除或补跑；
- 同一 case 有一个 Native 小输出路径，使单 pair evidence reduction 为负，最小值 `-3.135135`；预注册 Gate 使用完整样本的 median，异常点保留在正式 result；
- `natural_command_shape_v1` 的 Control session Token 有高成本分支，max `83,851`；未因其放大观察差异而剔除；
- Treatment 是冻结 source tree 的实验投影，不是 Host tool-result replacement；结果不能推出在线 intervention 可行；
- 历史 ACP-1.2 的 5 个 high-cost candidates 没有被验证；
- 两个 task、一个 commit、一个 model/host/time block 的结果不能外推为 Agent 的通用节省率。

## 允许的结论

可以说：

> 在两个冻结自然任务与预注册 Treatment 下，实验支持部分 observed evidence volume 可能可避免，同时未观察到冻结 Gate 所定义的任务行为恶化。

不得说：

- ACP 可在生产环境节省 `3.22%`、`16.01%` 或任意合并比例；
- 所有 high-cost evidence 都不必要；
- slicing/replacement 已可安全上线；
- 结果证明全局零 correctness 风险。

## 重新校准条件

subject commit、host binary/API、model/reasoning effort、题面/scorer、candidate identity、Treatment projection、配对顺序、样本数、Gate/统计公式或 success semantics 任一变化，都必须生成新的 experiment version；不得覆盖本次结果。
