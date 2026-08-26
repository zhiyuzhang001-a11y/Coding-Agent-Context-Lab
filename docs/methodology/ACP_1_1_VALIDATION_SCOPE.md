# ACP-1.1 Validation Scope

- 状态：`ACP-1.1 Repeated Context / Evidence Analysis — COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- Baseline ID：`acp1-1-co1-4-within-session-repetition-v1`
- 证据入口：`resources/acp1_1_frozen_baseline_index.json`
- Manifest：`resources/acp1_1_frozen_experiment_manifest.json`

## 证明范围

在冻结 CO-1.4 replay、ACP-1.0 canonical artifacts、`relation_scope=within_session` 与 ACP-1.1 v1 语义内：

- 16 个 eligible calls 的 earlier/later call order coverage 完整；
- 未找到任何可靠的 within-session exact-payload/path/range relation；
- unique repeated observation count/Tokens 均为 0；
- 同一输入可字节级重生 analysis、Markdown 和 CLI artifact；
- manifest 绑定 index，index 绑定上游 ACP-1.0、registry、spec、engine、renderer 和全部派生产物。

## 重要区分

ACP-1.0 报告的 5,288 Token exact repeated evidence observation volume 来自不同 session 的相同 payload hash。ACP-1.1 v1 明确不建立跨 session relation，因此 within-session 结果为 0 不会删除、否定或重写 ACP-1.0 事实。

## 未证明的事项

- 不证明 Agent 在其他任务中不会重复观测 evidence；
- 不证明跨 session duplicate 是必要或不必要的；
- 不证明无 path/range relation；当前 fixture 没有可靠 path/range identity，因此 coverage 是 `unknown`；
- 不证明文件内容稳定，当前无 file version identity；
- 不证明 cycle relation，cycle linkage 保持 `unknown`；
- 不证明任何 Token 是 wasted、avoidable 或 potential savings。

## 重新生成条件

normalized/ledger/attribution、relation semantics、range convention、engine、renderer 或 governed input 变化时，必须生成新 baseline ID/version 与 manifest chain，不覆盖本基线。collector、Hook、host/model 或关键 measurement semantics 变化时，还必须执行 ACP-0H 规定的重新校准。
