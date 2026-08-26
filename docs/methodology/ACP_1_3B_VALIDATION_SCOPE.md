# ACP-1.3B Validation Scope

- 状态：`COMPLETE under synthetic frozen experiment scope`
- 日期：2026-08-18
- Baseline ID：`acp1-3b-controlled-evidence-feasibility-v1`
- Index：`resources/acp1_3b_frozen_feasibility_index.json`
- Manifest：`resources/acp1_3b_frozen_experiment_manifest.json`

ACP-1.3B 只验证 prospective synthetic evidence replay 和 source-level evidence variant 的实验可行性。它不解锁生产 Hook replacement，不证明 ACP-1.2 的历史 candidates 可避免，不声称一般 Token savings。

## 已证明

- 同一 prompt、command、model、reasoning effort 与 success envelope 下，可以只替换运行前的合成 evidence source payload；
- Control-only `20/20` 正确且严格执行唯一命令，满足 replay qualification；
- paired Control/Treatment 各 `5/5` 正确，命令路径与 model-cycle count 一致，两臂均保持正常 tool success semantics；
- Treatment 的已观测 tool-result evidence estimate 比 Control 少 `49.757591%`，超过预注册 `40%` activation Gate；
- 30 个完成 run、公开紧凑结果、私有 result inventory、spec/runner 和环境 provenance 已进入 checksum chain。

正式运行前有 1 次 sandbox infrastructure preflight 在进入模型前超时：无 usage、无模型输出，失败 artifact 保留为私有环境诊断，未计入 20+10 的预注册样本。正式 30 次 run 在可访问模型服务的独立目录中全部完成，没有删除或重跑任何已启动的模型样本。

## 未证明

- 未对 ACP-1.2 的 5 个历史 high-cost call 进行 replay 或 ablation；
- `37,219 → 34,127` 的 session median 只是这个 synthetic case 的观测差，不是可避免成本估计；
- 未证明生产 Host 提供 success-preserving result rewrite；`decision:block` 失败语义结论未改变；
- 未开始 slicing、replacement、实时推荐、waste detector 或 candidate-specific intervention。

## 重新校准条件

model、reasoning effort、host binary/API、prompt、ground truth、evidence payload generator、runner/scorer 或 success-envelope 判定任一变化，都必须生成新 baseline；不得覆盖本次冻结结果。
