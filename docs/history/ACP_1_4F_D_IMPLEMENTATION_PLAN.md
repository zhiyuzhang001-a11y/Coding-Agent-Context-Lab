# ACP-1.4F-D：Benchmark Development Pool

- 状态：`COMPLETE / BENCHMARK_SEMANTICS_NOT_SUPPORTED`
- 日期：2026-08-19
- 前置：ACP-1.4F-R `COMPLETE / PROCEED_TO_BENCHMARK_DEVELOPMENT_POOL`
- ACP-1.4F v3：`BLOCKED_BY_BENCHMARK_DEVELOPMENT`
- R1/S1/B1：`FROZEN`

最终执行 110/240 个有效 Agent runs 后触发 automatic futility stop：4个 case qualified，全部属于 observed `search_like`；`read_like` 与 `structured_bash_like` 均未形成支持集合。v3 与新 holdout 不获授权。详见 `ACP_1_4F_D_RESULTS.md`。

## 一句话目标

> 验证能否用 case-independent、无 oracle 的语义，稳定识别自然 Agent execution 中 intervention-compatible evidence opportunity。

本阶段开发 benchmark，不测试或调整 intervention。Development 数据、任务和观察不得进入未来 v3 formal statistics。

## 分析对象

```text
task
  ↓
evidence opportunity
  ↓
compatible carrier(s)
  ↓
observed Host path / tool call
```

qualification unit 始终是 `evidence opportunity`。具体 Host tool、carrier 与完整 trajectory 都是测量维度，不能取代 qualification unit。

## D-0 — Protocol freeze

在查看任何 development probing 结果前冻结：

- qualification semantics；
- intended form 与 observed family 的分离；
- carrier taxonomy 与 equivalence scope；
- identity、measurement unknown 与 truncation 规则；
- meaningful evidence volume；
- Screen/Extension futility；
- registry schema；
- leakage 与 holdout 隔离；
- verdict rules；
- 240-run 硬上限。

冻结产物应形成 `development-protocol-v1` checksum chain。协议冻结后不得根据 probing 结果修改 task、threshold、taxonomy 或 reason code；任何必要变更必须建立新 protocol version，旧 runs 不复用。

## D-1 — Development pool freeze

冻结24个新 development cases，design target 约为：

- Read-like：约8；
- Search-like：约8；
- Structured-Bash-like：约8。

这只是 design target。每个 case 的最终 family classification 由自然 probing 的 observed dominant evidence family 决定。Registry 同时保存 `intended_evidence_form` 与 `observed_dominant_family`，不得把观察强行归入设计标签。

任务要求：

- 答案唯一、scorer 可审计；
- prompt 不包含答案；
- 必须检查外部 evidence，不能合理地仅凭 prompt 回答；
- 不强迫具体 Host tool；
- evidence payload 有机会达到 meaningful threshold；
- 至少覆盖4种 project form；
- 不复用1.4F v2.1 cases；
- 任务和 subject 在首轮 Agent run 前冻结。

Oracle registry 与 development contract 物理隔离，只供 outer harness correctness scoring。Evidence classifier 不接收 expected/scorer/final answer。

## D-2 — Screen

固定运行 `24 × 3 = 72` Native probes。Builder、collector、Hook mutation、Treatment 与 R1/S1/B1 全部关闭。

每次 attempt 后写 checkpoint，并计算 case viability。Screen 结束后只有在所有最终 Gate 仍数学上可达时进入 Extension。不可达时使用冻结 reason code，不替换 case、不补任务。

## D-3 — Extension

对 Screen-admitted case 再运行7次，使每个 case 达到10次。Extension 不补跑失败样本。

最终 development qualification 至少要求：

- completed with usage `10/10`；
- correctness `>=9/10`；
- evidence-opportunity recurrence `>=8/10`；
- intervention-compatible carrier recurrence `>=8/10`；
- meaningful evidence recurrence `>=8/10`；
- dominant observed evidence family `>=8/10`；
- ambiguous identity `=0`；
- measurement unknown/truncation unresolved `=0`；
- oracle-free classifier；
- prompt inferability check 通过。

Host tool/path entropy、carrier distribution 和 equivalence scope 必须报告，但完整 trajectory entropy 不单独决定 admission。

## Futility reason codes

- `F_CORRECTNESS_UNSTABLE`
- `F_EVIDENCE_NOT_IDENTIFIABLE`
- `F_NO_COMPATIBLE_CARRIER`
- `F_TOOL_PATH_UNSTABLE`
- `F_TRUNCATION_UNRESOLVED`
- `F_EVIDENCE_TOO_SMALL`
- `F_AMBIGUOUS_IDENTITY`
- `F_PROMPT_INFERABLE`
- `F_INTERVENTION_NOT_MEANINGFUL`

任一 Gate 即使剩余 runs 全成功也无法达到时，立即记录 `STOP_FUTILITY`。Prompt inferable、ambiguous identity 或 unresolved measurement 属于不可通过的结构性原因。

## Registry

每个 case 以 `resources/acp1_4f_d_registry_schema.json` 为唯一输出合同，至少保存：

- design metadata；
- Screen/Extension run counts；
- correctness；
- Host tool family distribution、dominant family 与 entropy；
- evidence family distribution 与 recurrence；
- compatible carrier distribution 与 recurrence；
- identity stability、ambiguity 与 equivalence scope；
- evidence Token min/median/max；
- truncation与 measurement unknown；
- qualification state 与 reason codes。

正式 v3 只能程序化消费冻结 registry，不回读人工笔记或私有正文。

## D-4 verdict

### `READY_FOR_NEW_HOLDOUT`

Development 数据证明同一套 case-independent qualification semantics 能在至少三个 observed evidence families 中各形成至少3个 qualified case，并且不依赖 case-specific identity/selector oracle。

### `SUPPORTED_FOR_SUBSET_ONLY`

至少两个 observed evidence families 各形成至少3个 qualified case，但第三家族不足。后续科学问题必须缩小到已支持的 family subset，不能继续声称三家族泛化。

### `BENCHMARK_SEMANTICS_NOT_SUPPORTED`

少于两个 observed evidence families 达到上述开发支持，或 case-independent semantics 无法在无 oracle 条件下稳定识别 evidence opportunity。ACP-1.4F 冻结，不创建 v3。

## 明确不做

- 不修改或评估 R1/S1/B1；
- 不根据 development 观察新增 case-specific selector；
- 不把 intended form 当作 observed family；
- 不把具体工具 recurrence 当作 evidence-opportunity recurrence；
- 不让 development cases 进入 future formal；
- 不用 expected/final answer/scorer 识别 evidence；
- 不降低 Gate 让 task 通过；
- 不在 protocol 或 case pool 冻结前启动 Agent runs。
