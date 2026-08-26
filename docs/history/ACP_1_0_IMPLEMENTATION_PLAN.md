# ACP-1.0 正式任务书：Cost Attribution Baseline

- 状态：`ACP-1.0 Cost Attribution Baseline — COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- 前置：`ACP-0 Measurement Foundation — COMPLETE under frozen validation scope`
- 并行依赖：ACP-0H v1 非阻塞；首次昂贵正式实验前要求 H0.1/H0.2 完成
- 冻结输出目标：`cost-attribution-baseline-v1`

## 核心问题

> **Where did the observed tokens go?**

ACP-1.0 只建立成本结构与客观重复 evidence baseline，不回答：

> **Which tokens were unnecessary?**

后一个问题必须等 attribution、coverage 和复算稳定后另立阶段。

## 输入边界

只消费 ACP-0 冻结层：

```text
acp-event-v1
  → normalized-event-v1
  → coverage-ledger-v1
  → fact-report-v1
  → cost-attribution-baseline-v1
```

ACP-1.0 不修改 collector、normalized events、ledger 或 fact report；输出是可丢弃、可重新生成的离线派生 artifact。

## 允许的事实指标

### Session / observed scope

- observed calls、observed model-visible estimated tokens、raw/output chars；
- attributed、unattributed、unsupported 与 parse-unknown volume；
- session total/model cycles 仅在存在冻结可靠来源时展示，否则为 `unknown`。

### Tool-family attribution

- call count by tool family；
- observed model-visible estimated tokens by tool family；
- family 内 min/median/max，样本量足够时可提供 p90；
- 每项同时携带 denominator、coverage status 与 traceability refs。

Tool-family Token share 的分母只能是 `observed model-visible tool context`，不得称为完整 session Token share。

### Concentration

- Top-1/Top-3/Top-K call share；
- tool-family concentration；
- 可选 HHI/Gini 等确定性 concentration 指标，但必须注明输入集合、分母和 unknown，不赋予优化含义。

“某 call 很大或高度集中”是事实，不等于“该 call 不必要”。

### Cycle structure

- 可靠 cycle identity 存在时：每 cycle call count、tool-family mix 与 observed Token；
- cycle linkage 缺失时：`cycle_coverage=unknown`，不得用 timestamp 或 call index 重新猜测。

### Objective repetition facts

- `exact_payload_duplicate`：相同规范化 output hash；
- `same_file_repeat`：同一脱敏 path identity 的再次读取；
- `range_overlap`：可靠显式范围的重叠行数/比例；
- 无可靠 path/range/linkage 时保持 unknown。

这些指标不得命名为 waste、avoidable、redundant mistake 或 optimization opportunity。

## 输出合同

`cost-attribution-baseline-v1` 至少包含：

```text
schema_version / schema_id
source_fact_report_sha256
measurement_contract_id
scope_and_denominators
coverage_summary
tool_family_attribution
top_calls_and_concentration
cycle_structure_or_unknown
objective_repetition_facts
unknown_volume_and_reasons
traceability_index
generator_version
```

JSON 是唯一事实源；Markdown/CLI 只渲染 JSON，不另行计算。

## Gate

1. **Fact-only**：不存在 wasted/avoidable/recommendation/optimization judgment。
2. **Traceability**：每个数值可追到 fact report、ledger 或 normalized event。
3. **Coverage-aware**：关键指标携带 denominator、coverage 与 unknown。
4. **No re-correlation**：不得用 timestamp/hash 新猜 cycle 或 call linkage。
5. **Layer safety**：tool-visible share 不冒充 session total share。
6. **Determinism**：同一冻结输入字节稳定或语义等价。
7. **Privacy**：无正文、完整命令、prompt/transcript、绝对路径或原始 session ID。
8. **Baseline parity**：CO-1.4 的 12 sessions、16 calls、17,651 visible estimated Tokens 保持一致。
9. **No online effect**：不修改 collector/Hook，不进入 Agent loop。

## 实施顺序

### ACP-1.0-0：Contract and fixture

- [x] 冻结 `acp1_0_semantic_dictionary.json`、`cost-attribution-baseline-v1` schema、denominator 和 unknown 规则；
- [x] 使用现有脱敏 replay 加入 complete/partial/ambiguous/unsupported contract cases；
- [x] 在 attribution engine 和正式 baseline 输出前固定 Top-K、HHI、nearest-rank p90、12 位小数与 repetition copy-only 规则。

0 阶段验收记录（2026-08-18）：CO-1.4 complete case 保持 12 sessions、16 calls、17,651 observed matched visible estimated Tokens；partial case 保持 14/24 Token coverage，ambiguous 不选候选，unsupported 不外推。合同测试同时冻结 cycle unknown/no-inference、tool-visible denominator 不冒充 session share、隐私哨兵与输入 hash。

合同澄清 1.0-0a（在首个 engine 输出冻结前）：partial fixture 揭示 `transcript_only` 虽有已知 transcript Token，但不能进入 attributed numerator。故 eligibility 明确为 `observed_event + matched + non-null visible tokens`；同时按正式 1.0-1 验收加入 session/call attribution、Top 10%/20%、call HHI 与 repetition group observation volume。既有 denominator、coverage taxonomy 与 fixture baseline 不变，unsupported Token 继续为 `null/unknown` 而不是零。

### ACP-1.0-1：Offline attribution engine

- [x] `scripts/acp_attributor.py` 只从冻结 `fact-report-v1` 生成 canonical `cost-attribution-baseline-v1` JSON；不读取 raw Hook event，不调用 normalizer/correlator，不进入 online path；
- [x] 输出 session、tool-family、call、Top-1/3/10、Top 10%/20%、call/family HHI、distribution、cycle unknown 与 objective repetition volume；
- [x] complete/partial/ambiguous/unsupported、traceability、coverage、read-only、privacy、determinism 与 schema 测试通过；unknown 不隐式归入 Other，unsupported 不写成零成本；
- [x] 不生成 diagnosis、waste、avoidable、recommendation 或 optimization 文本。

### ACP-1.0-2：Readable baseline

- [x] `acp-attribution-renderer-v0.1` 只接受 canonical `cost-attribution-baseline-v1` JSON，拒绝 fact report、normalized event 或 raw event；
- [x] JSON 保持唯一事实源，renderer 仅提供 canonical JSON、Markdown 与 CLI text，不计算 attributor 未定义的新指标；
- [x] 展示 session summary、concentration、tool-family map、Top calls、repetition facts、coverage/unknown 与 traceability；
- [x] Source purity、determinism、no-new-metrics、unknown preservation、no-diagnosis、traceability 六个 Gate 通过。

1.0-2 完成不自动等于 ACP-1.0 冻结。仍按既有 1.0-3 执行首份正式 baseline、experiment manifest 与最终 Gate；ACP-0H H0.3/H0.4 必须在该冻结点前完成。

### ACP-1.0-3：Frozen baseline

- [x] 以 registry 中已准入的 `co1_4_observe_replay@1` 在冻结派生环境中完整运行 normalized → ledger → fact report → attribution → renderer；
- [x] 保存 baseline spec、calibration state、canonical JSON、Markdown/CLI、baseline index 与 `experiment-manifest-v1`；raw private artifact 显式为 `not_produced`；
- [x] G1 provenance complete with declared unknowns、G2 governance valid、G3 end-to-end determinism、G4 measurement integrity、G5 freeze integrity 全部通过；
- [x] 首份基线保持 12 sessions、16 calls、17,651 observed matched visible estimated Tokens、complete coverage、cycle/session total unknown 与 5,288 exact-repeat observation volume；
- [x] baseline index SHA-256 为 `598bf7ea4ee98f17de483b5f818c68d9ea95f5fc444736f1bac1efa34b65a186`，manifest SHA-256 为 `b44a0eae1ad88ca36d3280f73dad37e517ac3c2302db94a443bd44ee6c4e113f`。

完成声明只在冻结 experiment scope 内有效；源 observation 的 model/reasoning、Hook API、session total 与 model cycles 保持显式 `unknown`，不伪造 provenance 或全局精确性。适用范围见 `ACP_1_0_VALIDATION_SCOPE.md`。

## 明确不做

- 不做 wasted/avoidable Token；
- 不判断 duplicate read 是否必要；
- 不输出“应该 Search 而不是 Read”；
- 不做 context amplification score 或 optimization opportunity；
- 不做实时 recommendation、prompt injection；
- 不做 slicing、replacement、自动压缩；
- 不改变 ACP-0 collector、privacy schema 或历史结果。

## ACP-1.0 完成定义

所有 Gate 已通过并冻结首份 coverage-aware、traceable、deterministic 的 `cost-attribution-baseline-v1`。完成只表示在冻结实验范围内，成本去向与客观重复事实得到稳定描述；不表示已识别浪费，也不表示对其他宿主、模型或 fixture 全局有效。
