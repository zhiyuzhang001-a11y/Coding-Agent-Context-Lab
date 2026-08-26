# ACP-0.2 实施计划：Normalizer + Coverage Ledger

- 状态：`COMPLETE`
- 日期：2026-08-17
- 冻结插件版本：`0.1.0+codex.20260817141025`
- 前置版本：`acp-collector-v0.1`
- 输入合同：`acp-event-v1` / `transcript-call-v1`
- 输出合同：`normalized-event-v1` / `coverage-ledger-v1`
- Normalizer 版本：`acp-normalizer-v0.1`
- 非目标：waste metrics、duplicate-read interpretation、recommendation、slicing、replacement、压缩、实时 Agent 提示和正式自然任务 A/B

## 目标

> 把 ACP-0.1 的可信采集结果转换成语义稳定、隐私安全、覆盖可审计、确定性可回放的标准测量数据。

```text
acp-event-v1
    ↓ validation / canonicalization
normalized-event-v1
    ↓ privacy-normalized transcript correlation
coverage-ledger-v1
```

`acp-event-v1` 已是隐私归一化 telemetry，不是 raw host event。ACP-0.2 不重新解析已被删除的命令/路径/正文，不修改冻结 collector。

## 合同决策

### Normalized event

- 保留 collector 事实：event/session ID、tool family/shape、raw chars/Token 估算、result hash、脱敏 path/range 和 collector duration。
- `source_coverage_state` 不可改写；离线关联结果写入独立 `coverage_state/linkage_status`。
- `call_id`、`call_index`、model-visible chars/Token 只在唯一稳定关联后填入，否则为 `null`。
- 不保存 `input_size_bytes`：冻结 collector 未采集，Normalizer 不得猜测。
- 不保存 `output_size_bytes`：`raw_chars` 不能在丢失正文后逆推 Unicode 字节数。
- 不从 raw result 量外推 model-visible Token。

### Correlation

匹配只使用隐私安全 metadata：

1. session pseudonym 一致；
2. stable call/event ID 一致，且 tool family/output hash 一致；或
3. stable ID 不可用时，session + tool family + output hash 只有唯一未占用候选。

任一稳定信号冲突、重复 event ID 或多候选都进入 `ambiguous`，不用 timestamp 猜测顺序，不为追求 100% 强行匹配。

### Coverage ledger

每个 coverage metric 必须包含：

```text
status
numerator
denominator
ratio
unit
denominator_source
```

`denominator` 不可得或为 0 时，状态为 `unknown_denominator`且 ratio 为 `null`。Ledger 同时报告 session、call、model-visible Token、event linkage、raw-char linkage 和 tool-family classification coverage，以及 tool family/command shape 维度和 unknown 的 count/raw/model-visible 体量与 reason。

Call coverage 与 linkage coverage 严格区分：

- call coverage：成功强关联的 collector event / transcript completed calls；
- linkage coverage：成功强关联的 collector event / collector supported events。

## Fixtures

### CO-1.4 paired replay

`resources/acp0_co1_4_replay_fixture.json` 只验证脱敏 paired metadata→Normalizer→Ledger，不冒充 raw host-event replay。Fixture 显式声明 session 内 event order 来自 transcript call order，`call_id` 来自冻结一对一关联，timestamp 是回放用合成值。

### Synthetic host-event pipeline

`resources/acp0_2_synthetic_host_events.json` 只含明确标记的虚构 session、命令、路径和正文，用于验证 host event→冻结 collector→Normalizer→Ledger 接口与隐私回归。该 fixture 不用于 CO-1.4 基线归因。

## Gate

- G1 Schema：`normalized-event-v1`、`transcript-call-v1`、`coverage-ledger-v1` JSON Schema 和语义字典冻结。
- G2 Determinism：同一 paired/synthetic fixture 多次输出字节一致。
- G3 Baseline parity：CO-1.4 稳定复现 12 sessions / 16 calls / 16 unique linkages / 17,651 model-visible estimated tokens。
- G4 Explicit coverage：unmatched、ambiguous、transcript-only、unsupported、parse/rejected 不静默丢弃，分母来源显式。
- G5 Privacy：normalized/ledger/diagnostics 不引入 raw ID、命令、正文、basename 或路径。
- G6 Isolation：不加入 slicing、replacement、recommendation、waste/avoidable/optimization 判定。

## 停止条件

G1–G6 全部通过后立即停止 ACP-0.2。用户可读 cost attribution report 属于 ACP-0.3；正式 Native/Profiler 自然任务 no-interference A/B 属于 ACP-0.4。

## 完成与验收（2026-08-17）

- [x] G1 Schema：三个 JSON Schema 与完整字段语义字典已冻结，JSON Schema Draft 2020-12 实际验证通过。
- [x] G2 Determinism：paired 和 synthetic pipeline 重复运行字节一致，canonical JSON 键排序固定。
- [x] G3 Baseline parity：CO-1.4 复现 12/12 sessions、16/16 calls/linkages 和 17,651/17,651 model-visible estimated tokens。
- [x] G4 Explicit coverage：唯一稳定匹配、多候选 ambiguous、stable-ID 冲突、unmatched、transcript-only、unknown denominator 和 malformed record 均有独立测试与 ledger 口径。
- [x] G5 Privacy：合成 host fixture 的 raw session、命令、正文、basename 和绝对路径均未进入 normalized/ledger；坏记录只保留 fingerprint/reason。
- [x] G6 Isolation：输出不包含 waste、avoidable、optimization、recommendation、replacement 或 slicing 指标。

验收记录：ACP-0.2 专项 10/10，仓库全套 165/165，`py_compile`、JSON 解析、JSON Schema 验证与 `git diff --check` 通过。Normalizer 及 schema/dictionary/synthetic fixture 的 SHA-256 已记录在 `resources/acp0_contract.json`。ACP-0.2 到此停止。
