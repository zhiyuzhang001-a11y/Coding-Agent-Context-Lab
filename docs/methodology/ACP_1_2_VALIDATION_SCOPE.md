# ACP-1.2 Validation Scope

- 状态：`ACP-1.2 Cost Necessity Hypothesis Framework — COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- Baseline ID：`acp1-2-co1-4-cost-necessity-hypothesis-catalog-v1`
- Catalog：`resources/acp1_2_frozen_catalog.json`
- Index：`resources/acp1_2_frozen_catalog_index.json`
- Manifest：`resources/acp1_2_frozen_experiment_manifest.json`

## 已证明的事项

在冻结 CO-1.4 attribution、ACP-1.1 relation facts 与 ACP-1.2 candidate policy 内：

- 5 个 call 满足 high-cost candidate 预注册门槛；
- 没有 concentration candidate，因为 call HHI 与 Top-3 share 未达到冻结门槛；
- 没有 repeated/overlapping candidate，因为 ACP-1.1 within-session unique relation 为 0；
- 5 个 unique target calls 的 observed exposure 为 10,735 Tokens，占 frozen denominator 的 `0.608180839612`；
- catalog、renderer、index 和 manifest 可确定性重生并完整追溯。

## 尚未证明的事项

- 10,735 Tokens 不是 avoidable volume、potential savings 或 waste estimate；
- high-cost candidate 不是 anomaly，也不证明 call 不必要；
- 没有执行 suppression、reduction、replacement、slicing 或任何其他 intervention；
- 没有 correctness、tool path、model cycle 或 Token delta 的因果证据；
- 不声称这五个 call 在其他任务、模型或宿主中仍是实验候选。

## 为什么 validation feasibility 是 blocked

ACP-1.0/1.1 canonical artifacts 不包含可重放的任务上下文、ground truth 或经过验证的成功语义保持 intervention interface。因此所有 candidate 都保持：

```text
necessity_status = unknown
causal_status = untested
validation_feasibility = blocked
```

该 blocked 状态是对证据边界的记录，不是 candidate 失败，也不授权重开 Transparent Smart Read。

## 后续触发条件

ACP-1.3 只能在独立任务书中启动，并必须先解决可重放 task/ground truth 与受控 intervention interface。它不得修改 collector，不得以 ACP 名义重开冻结的产品 replacement/slicing 路线，且必须使用独立 OFF/ON paired design、correctness Gate 与 manifest chain。
