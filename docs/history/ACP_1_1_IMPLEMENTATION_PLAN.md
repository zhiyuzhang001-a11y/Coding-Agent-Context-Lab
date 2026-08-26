# ACP-1.1 正式任务书：Repeated Context / Evidence Analysis

- 状态：`ACP-1.1 Repeated Context / Evidence Analysis — COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- 前置：`ACP-1.0 Cost Attribution Baseline — COMPLETE under frozen experiment scope`
- 目标输出：`repeated-evidence-analysis-v1`

## 不可改动的原则

> **ACP-1.1 只证明“重复发生了”，不证明“重复是不必要的”。**

该阶段只建立客观 evidence relation、去重后的再次观测体量、coverage 与 traceability。必要性、可避免性和节省估计必须留给独立的后续 hypothesis/intervention 阶段。

## 输入边界

只消费冻结 canonical 层：

```text
normalized-event-v1 batch
coverage-ledger-v1
cost-attribution-baseline-v1
        ↓
repeated-evidence-analysis-v1
```

- 不读 raw Hook event、transcript、prompt 或工具输出正文；
- 不重做 call/session/path correlation；
- 只使用 normalizer 已冻结的 session/call linkage、path identity、explicit range 和 output hash；
- 不修改 ACP-1.0 frozen artifacts，ACP-1.1 输出是可重建的独立派生层。

## 1.1-0 冻结语义

### Relation scope 与顺序

- `relation_scope = within_session`；跨 session 不创建 relation；
- earlier/later 只由同 session 内唯一、可靠的 `call_index` 决定；缺失或冲突则保持 unknown；
- `cross_cycle = true | false | unknown`；当前输入无冻结 cycle linkage，必须输出 `unknown`，不得默认 false。

### Range 数学语义

normalized source range 是 1-based 闭区间 `[start_line, end_line]`。ACP-1.1 在不修改源事件的前提下确定性转换为 1-based 半开区间：

```text
[start_line, end_line_exclusive)
end_line_exclusive = source_end_line_inclusive + 1
```

- `exact_range_repeat`：两个 canonical interval 起止完全相同；
- `range_contains`：一个 interval 严格包含另一个，exact 不重复计为 contains；
- `range_overlap`：交集非空，且不属于 exact 或 contains；
- 同一 range 不代表同一内容。

### Path 与 payload 语义

- `same_path_repeat` 只证明脱敏 path identity 相同；
- v1 没有可靠 file version identity，所有 path/range relation 的 `content_stability = unknown`；
- `observed_payload_equality` 仅表示两次工具结果 hash 是否相同，不冒充整个文件的内容稳定性；
- 同 path/range 但不同 payload hash 记为 `observed_payload_equality=false` 且 `content_stability=unknown`。

### Relation 多重匹配与 Token 去重

一个 later call 可同时满足 `exact_payload_repeat`、`same_path_repeat` 和 `exact_range_repeat`：

- `relation_count` 保留全部客观 relation；
- `unique_repeated_observation_tokens` 对 later call 去重，每个 later call 只计一次；
- relation 维度不得分别累加 later Tokens 并冒充去重体量。

对每个 session：

```text
V_repeat_unique = sum(T_c for c in R)
```

`R` 是“至少存在一个可靠 earlier evidence relation 的 eligible later calls”集合。

```text
RepeatedObservationShare = V_repeat_unique / V_eligible_observed
```

名称只能是 `repeated observation share`，不得命名为 waste/savings ratio。

### Evidence basis

`evidence_basis` 使用封闭值：

- `output_hash`
- `path_identity`
- `explicit_range`

多种 basis 用数组表示，不用自由文本猜测证据强度。

## 输出结构

```text
repeated-evidence-analysis-v1
├── source_and_scope
├── denominator_and_coverage
├── repeat_groups
├── call_relations
├── unique_repeated_observations
├── path_repeat_facts
├── range_relation_facts
├── observation_volume
├── unknowns
├── traceability
└── policy
```

relation 至少包含稳定 ID、relation type、session、earlier/later call、evidence basis、path/range 证据、payload equality、content stability、cycle state、Token 和 source refs。

## Fixture

必须覆盖：

- exact payload complete；
- same path / different payload；
- exact range、strict contains、partial overlap 与 disjoint ranges；
- path/range identity 缺失；
- ambiguous/unmatched、unsupported 和 null Token；
- 一个 later call 匹配多种 relation，但 Token 只计一次；
- same path / same range / changed payload hash；
- 两个 session 的相同 payload 不建立 relation。

## Gate

1. **Source purity**：只消费冻结 canonical ACP 层。
2. **No re-correlation**：不用 timestamp/hash 重新猜 call/session/cycle linkage。
3. **Relation correctness**：relation 满足冻结数学与证据定义。
4. **Unique-volume integrity**：多重 relation 下 later call Token 只计一次。
5. **Unknown preservation**：证据不足不强制建立 relation，cycle/content stability 不默认 false/same。
6. **Coverage-aware**：所有体量标明 denominator、status 与 unknown reason。
7. **Determinism/traceability**：同一输入字节稳定，relation 可下钻到源 call/event。
8. **No diagnosis**：不存在 waste、avoidable、savings、necessity verdict 或 recommendation。
9. **Read-only/offline**：不修改输入，不注册 Hook，不进入 Agent loop。
10. **Baseline integrity**：ACP-1.0 frozen artifacts 与 collector/Hook hash 保持不变。

## 实施顺序

### ACP-1.1-0 Contract and fixtures

- [x] 冻结 relation scope、range convention、path stability unknown、evidence basis、Token 去重公式和 fixture。

### ACP-1.1-1 Offline relation engine

- [x] 实现只读离线 `acp-repeated-evidence-v0.1`；只消费 normalized batch、coverage ledger 与 canonical attribution，不读 raw event 或注册 Hook。

### ACP-1.1-2 Coverage validation

- [x] 验证 complete/partial/ambiguous/unsupported、多 relation 去重、跨 session 隔离与 unknown 传递；合成 fixture 的 11 relations 对应 6 个 unique later calls，330/660 Tokens 只按 call 计一次。

### ACP-1.1-3 Renderer and frozen baseline

- [x] `acp-repeated-evidence-renderer-v0.1` 只消费 canonical analysis JSON 生成 Markdown/CLI，不新增指标；
- [x] 生成 governed manifest-bound frozen baseline；五个 Gate 全部通过，baseline index 为 `034630b6a8474f1b6d0e7f245fa60098edab0a393642c97762b426123cb43fb9`，manifest 为 `79f6add0c42cbc357e308d0c317d933c98ffca4ee09602d544af32d08735364a`。

正式 CO-1.4 基线结论：16 calls / 17,651 eligible observed visible estimated Tokens 的 relation-order coverage 完整；within-session objective relation 为 0，unique repeated observation Tokens 为 0。ACP-1.0 的 5,288 Token exact duplicate observation volume 是跨 session 事实，保留不变且不进入 1.1 的 within-session relation。path/range/cycle/content stability 保持 `unknown`。适用范围见 `ACP_1_1_VALIDATION_SCOPE.md`。

## 明确不做

- 不做 fuzzy/semantic similarity；
- 不判断 duplicate read 是否必要；
- 不输出 wasted/avoidable/potential savings/optimization opportunity；
- 不做 recommendation、replacement、slicing 或实时反馈；
- 不修改 collector、Hook、ACP-0 或 ACP-1.0 冻结语义与 artifact。
