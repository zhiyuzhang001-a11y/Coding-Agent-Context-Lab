# ACP-1.2 正式任务书：Cost Necessity Hypothesis Framework

- 状态：`ACP-1.2 Cost Necessity Hypothesis Framework — COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- 前置：ACP-1.0 与 ACP-1.1 均 `COMPLETE under frozen experiment scope`
- 目标输出：`cost-necessity-hypothesis-catalog-v1`

## 目标与边界

ACP-1.2 只将已冻结事实转换为“值得未来做因果验证的实验候选”。它不执行 intervention，不判断 necessity，不估计 avoidable volume。

```text
ACP-1.0 cost attribution
ACP-1.1 repeated-evidence facts
          ↓
offline hypothesis catalog
          ↓
future ACP-1.3 controlled validation（本轮不执行）
```

> 事实层只说明“发生了什么”；ACP-1.2 只说明“哪些对象满足预注册实验候选条件”。

## Hypothesis taxonomy

1. `high_cost_call_candidate`：单个 call 满足冻结 exposure 门槛，necessity 未知。
2. `cost_concentration_candidate`：冻结 concentration metric 达到候选门槛，集中是否合理未知。
3. `repeated_or_overlapping_evidence_candidate`：ACP-1.1 存在可靠 within-session unique repeated observation，necessity 未知。

candidate 不得称为 anomaly、problem、waste 或 recommendation。

## 预注册候选门槛

### High-cost call

- `visible_token_share >= 0.10`；
- `observed_exposure_tokens >= 1000`；
- 按已冻结 rank、call ID 确定性排序；
- 最多保留 5 个 call；
- 门槛只用于限制实验队列，不是异常或低效判定线。

### Cost concentration

任一冻结条件满足时生成一个 catalog-level candidate：

- `call_hhi >= 0.18`；或
- `top3_share >= 0.60`。

该门槛也只是实验队列 policy，不表示 concentration 不合理。

### Repeated / overlapping evidence

- ACP-1.1 `unique_repeated_observations` 中每个 later call 最多生成一个 candidate；
- 多 relation 不重复生成候选或重复计 Token；
- relation 必须是 within-session 且来自 ACP-1.1 canonical output；
- 当 unique relation 为 0 时，该类 candidate 必须为 0。

## 输出合同

```text
cost-necessity-hypothesis-catalog-v1
├── source_and_scope
├── candidate_generation_policy
├── hypothesis_candidates
├── candidate_summary
├── unknowns
├── traceability
└── policy
```

每个 candidate 必须包含：

```text
hypothesis_id
hypothesis_type
target_scope
target_call_ids
observed_exposure_tokens
observed_share
factual_basis
necessity_status = unknown
causal_status = untested
required_validation
validation_feasibility
source_refs
```

`observed_exposure_tokens` 只是候选对象的已观测 exposure，不是 avoidable/savings estimate。

## Required validation 与 feasibility

candidate 只记录未来实验所需步骤：

1. `construct_isolated_paired_task_replay`
2. `apply_controlled_evidence_intervention_in_experimental_harness`
3. `compare_correctness`
4. `compare_tool_path_and_model_cycles`
5. `estimate_delta_only_if_correctness_is_preserved`

当 canonical 输入不含可重放 task、ground truth 或安全 intervention interface 时：

```text
validation_feasibility.status = blocked
reason_codes = [missing_replayable_task_context, missing_controlled_intervention_interface]
```

blocked 不会删除 candidate，也不会被改写成 unnecessary=false。

## 空 catalog 语义

若没有任何预注册 trigger，必须输出：

```text
catalog_status = empty_no_preregistered_trigger
hypothesis_candidates = []
```

不得为了产生“发现”而降低门槛或强制生成 candidate。

## Gate

1. **Source purity**：只消费 ACP-1.0 attribution 和 ACP-1.1 analysis。
2. **Frozen policy**：taxonomy、threshold、cap、排序和空结果语义在 engine 正式输出前冻结。
3. **No causal verdict**：所有 candidate 保持 necessity unknown / causal untested。
4. **Exposure integrity**：只复制 frozen observed exposure，不计算 avoidable/savings。
5. **Coverage/unknown preservation**：不可验证或证据缺失显式 blocked/unknown。
6. **Determinism/traceability**：同一输入字节稳定，candidate 可下钻到 source call/metric/relation。
7. **No diagnosis/recommendation**：不存在 waste、avoidable、potential savings、anomaly verdict 或 Agent recommendation。
8. **Offline/read-only**：不修改输入，不注册 Hook，不执行 intervention。
9. **Baseline integrity**：ACP-1.0/1.1、collector 与 Hook frozen hashes 保持不变。

## 实施顺序

### ACP-1.2-0 Contract and fixture

- [x] 冻结 taxonomy、threshold、cap、空 catalog、unknown/untested 和 feasibility 语义。

### ACP-1.2-1 Offline generator

- [x] 实现纯离线 `acp-hypothesis-catalog-v0.1`；只消费 ACP-1.0 attribution 与 ACP-1.1 repeated-evidence analysis。

### ACP-1.2-2 Coverage and renderer

- [x] 验证 threshold boundary、cap、空结果、repeat-zero、unknown/blocked、确定性与只读；
- [x] `acp-hypothesis-renderer-v0.1` 只展示 canonical catalog，不新增候选或指标。

### ACP-1.2-3 Frozen catalog

- [x] 生成 governed manifest-bound catalog；五个 Gate 全部通过，catalog index 为 `e9aa0310cbf6eea4dc33bfe9ba3c8987097919e0956fbc8f801885d30dd24975`，manifest 为 `5528690350304f62d666acd7aa47288ce922c5b50511b9c09dadbdf5365ade61`。

正式 CO-1.4 catalog 结论：5 个 `high_cost_call_candidate`，0 个 concentration candidate，0 个 repeated/overlapping candidate。五个 unique target calls 共涉及 10,735 observed exposure Tokens（share `0.608180839612`）；该数字只是实验对象 exposure，不是可节省量。全部 candidate 保持 necessity `unknown`、causal `untested`、validation feasibility `blocked`；本阶段未执行 intervention。适用范围见 `ACP_1_2_VALIDATION_SCOPE.md`。

## 明确不做

- 不执行 suppress/reduce/block/replacement/slicing；
- 不重开 Transparent Smart Read 或修改 online collector；
- 不实时向 Agent 推荐工具路径；
- 不输出 avoidable/wasted/potential-savings Token；
- 不在本阶段启动 ACP-1.3 或 ACP-2。
