# ACP-0.3 正式任务书：四层事实报告

- 状态：`COMPLETE`
- 日期：2026-08-17
- 冻结插件版本：`0.1.0+codex.20260817142604`
- 输入合同：`normalized-event-v1` / `coverage-ledger-v1`
- 输出合同：`fact-report-v1`
- Reporter 版本：`acp-reporter-v0.1`
- 非目标：优化判断、浪费判断、避免性判断、新关联猜测、recommendation、slicing、replacement、实时 Agent 提示

## 目标

> 将标准化遥测和覆盖账本转换为确定性、带覆盖状态的四层事实报告，同时不引入任何优化判断、浪费判断或新的关联猜测。

ACP-0.3 是 disposable report layer。它只消费 ACP-0.2 的 normalized batch 与 coverage ledger，不修改上游 artifact；JSON 是唯一事实源，Markdown 只是 JSON report 的确定性 renderer。

## 冻结结构

正式 measurement layers 延续 ACP-0.0，不重新定义：

1. A — Observed tool-result cost
2. B — Model-visible tool context
3. C — Session-level cost
4. D — Profiler cost

用户可读结构作为下钻视图：Session / Run、Model Cycle、Tool Call、Evidence / Coverage。现有输入没有 cumulative session usage 或 cycle identity，因此相应字段必须为 `unknown`；不得用 timestamp、call index 或调用间隔推断 cycle。

## 事实指标

- observed events、transcript calls、matched calls、transcript-only calls 分开报告；
- raw volume 使用字符与 `chars_div_4_v1` 估算，不伪称 bytes；
- model-visible 总量只报告成功关联部分并携带 coverage；
- tool family 不重新分类，沿用 `bash/local_read/mcp/hosted/other`；
- distribution v1 只含 count/min/median/max，不加入 p90；
- Top calls 分为 largest matched visible calls 与 largest observed raw results；
- exact payload duplicate、same-file repeat、range overlap 只作为重复事实，不构成必要性或可操作性结论。

## Traceability

每个四层汇总事实必须携带 `source_refs`，引用输入 artifact 与 JSON Pointer；生成信息冻结 normalized batch 与 ledger 的 canonical SHA-256。Reporter 不导入 correlator，也不重新执行关联。

## Gate

- G1 Fact-only：报告无优化、浪费、避免性或建议字段。
- G2 Traceability：每个四层数字可追溯到 normalized event 或 ledger。
- G3 Coverage-aware：所有关键总量携带 status，unknown 不被补算。
- G4 No re-correlation：report 层只消费 ACP-0.2 的 linkage 结果。
- G5 Determinism：同一 frozen fixture 的 JSON 与 Markdown 输出稳定。
- G6 Baseline parity：CO-1.4 继续复现 12 sessions、16 calls、17,651 matched model-visible estimated tokens。

## 停止条件

G1–G6 全部通过即结束 ACP-0.3。正式 collector ON/OFF 自然任务 no-interference A/B、完整 session usage 与 profiler 增量成本证明属于 ACP-0.4。

## 完成与验收（2026-08-17）

- [x] G1 Fact-only：JSON 只包含测量事实、coverage 和重复关系；无 waste/avoidable/optimization/recommendation 等解释性 metric key。
- [x] G2 Traceability：四层每个 fact 均携带 artifact、JSON Pointer 和可用 event IDs；输入 batch/ledger canonical SHA-256 固定。
- [x] G3 Coverage-aware：CO-1.4 为 complete；synthetic fixture 保留 partial、transcript-only 与 unknown volume；session total、cycle 和未测 profiler 成本明确为 unknown。
- [x] G4 No re-correlation：`acp_reporter.py` 不导入 Normalizer、不调用 correlator，只消费已关联的 pipeline。
- [x] G5 Determinism：paired/synthetic 的 fact JSON 和 Markdown renderer 重复输出一致；JSON 为唯一事实源。
- [x] G6 Baseline parity：CO-1.4 复现 12 sessions、16 transcript calls、16 matched calls、17,651 matched model-visible estimated tokens。

冻结产物：`fact-report-v1`、`acp-reporter-v0.1`、JSON Schema、语义字典与 artifact hashes。验收记录：reporter 专项 9/9（含 JSON Schema）；normalizer+reporter schema 专项 19/19；仓库全套 175/175（系统 Python 缺少 jsonschema 的 2 项另由含 jsonschema 的冻结环境通过）；`py_compile`、JSON 解析与 `git diff --check` 通过。ACP-0.3 到此停止。
