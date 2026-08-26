# ACP-0 实施计划：Agent 成本计量合同与覆盖基线

- 状态：`ACP_0_MEASUREMENT_FOUNDATION_COMPLETE_UNDER_FROZEN_VALIDATION_SCOPE`
- 计划日期：2026-08-16
- 前置冻结点：`smart-read-frozen-2026-08` / `4878b62`
- ACP-0.0 计划记录版：`0.1.0+codex.20260816150255`
- ACP-0.1 collector 冻结版：`0.1.0+codex.20260817112704`
- ACP-0.2 normalizer/ledger 冻结版：`0.1.0+codex.20260817141025`
- ACP-0.3 fact reporter 冻结版：`0.1.0+codex.20260817142604`
- ACP-0.4 结果记录版：`0.1.0+codex.20260817162046`
- ACP-0.4a 方差归因记录版：`0.1.0+codex.20260818000714`
- ACP-0.4b correctness closure / ACP-0 冻结版：`0.1.0+codex.20260818012740`
- ACP-0 validation-scope certificate 记录版：`0.1.0+codex.20260818093126`
- 产品线：Agent Cost Profiler（独立于 Transparent Smart Read）

正式毕业含义、适用范围、限制与重新校准条件见 `ACP_0_VALIDATION_SCOPE.md`。`COMPLETE` 只在冻结验证范围内成立，不表示全任务、全宿主版本或所有随机运行下绝对零干扰。

## 1. 决策背景

Transparent Smart Read 已因当前 Codex 宿主缺少 success-preserving tool-result rewrite 而冻结。冻结不否定已有算法资产，但 ACP-0 不重新开启透明替换，也不继承“自动节省 Token”的产品承诺。

现有研究证明了四类可复用资产：

1. Hook 观察层：CO-1.4a 中 16/16 个自然 code-bearing Bash 结果、17,651/17,651 模型可见 Token 被同一 PostToolUse 观察。
2. AST/slicer：能生成语法完整的 Python 局部上下文候选。
3. risk/economic gate：能解释何时不应切片，以及预计收益是否值得承担补读风险。
4. benchmark harness：能配对记录 correctness、完整会话 Token、模型周期、工具调用与补偿行为。

ACP-0 只复用第一类和必要的 benchmark 基础设施，先建立可信测量。其余资产保留给后续独立阶段，不在 ACP-0 中混入。

## 2. 核心目标

ACP-0 只回答：

> 在不改变 Agent 行为的前提下，能否稳定、隐私安全、可复现地说明一次自然 Codex 任务中“观察到了哪些成本，哪些成本尚不可见”？

第一版是计量器和覆盖账本，不是优化器、推荐器或自动压缩器。

## 3. 最高原则

1. **Observe only**：不得返回 `decision:block`，不得改写工具输入、输出或成功状态。
2. **不增加模型参与**：Profiler 不向任务中注入提示，不新增模型周期和补偿工具调用。
3. **分层计量**：原始结果、模型可见结果和完整 session Token 必须分别报告，不能相互冒充。
4. **Unknown 是合法结果**：未覆盖的工具路径必须标记为 unknown，不按已观察比例外推。
5. **隐私默认**：默认不保存源码正文、完整命令、完整工具输出、prompt 或 transcript。
6. **可复算**：相同的脱敏事件输入应稳定生成相同报告。
7. **先测量再诊断**：ACP-0 不输出“应该少读什么”的实时建议。

## 4. 明确不做什么

ACP-0 不做：

- Transparent Smart Read 的重新开启或任何 result replacement。
- AST slicing、自动压缩、缓存、搜索结果裁剪或 Context Budget。
- 在线推荐、Agent prompt 注入或行为干预。
- 精确 tokenizer 的网络上传；默认继续使用明确标注的 `chars_div_4_v1` 估算。
- 对 MCP、LSP、direct read、hosted tool 做未经验证的覆盖声明。
- 完整 shell parser、shell 命令语义重建或源码级数据流分析。
- “节省百分比”产品宣传；Profiler 只报告观察和归因。

## 5. v0 支持边界

### 5.1 已支持并需要冻结复验

- 本地 `PostToolUse` / Bash 路径。
- 自然 code-bearing 结果的观察与结果大小计量。
- 当前 JSONL/transcript harness 中的工具调用、模型周期和累计 usage 解析。
- 精确结果哈希去重。

### 5.2 仅作为分类，不宣称完整理解

- `cat`、`sed`、`rg`、复合 shell 中的代码读取/搜索结果。
- 测试、构建、脚本执行和其他工具结果。
- 文件身份、显式行范围和命令族；无法安全解析时记录 unknown。

### 5.3 暂不覆盖

- direct read API、MCP、LSP、hosted tools。
- 模型内部隐藏上下文、system prompt 和宿主缓存。
- 供应商计费明细与精确 per-message Token 分解。

## 6. 统一计量合同

每份报告必须并列区分以下层级：

### A. Observed tool-result cost

- `raw_output_chars`
- `estimated_raw_tokens`
- `estimation_method`
- `tool_result_count`
- `code_bearing_result_count`

这是 Hook 可观察的结果量，不等于模型实际计费。

### B. Model-visible tool context

- `model_visible_chars`
- `estimated_model_visible_tokens`
- `matched_tool_result_count`
- `unmatched_tool_result_count`

只有能够通过稳定 ID、顺序与哈希关联到 transcript 的结果才进入已匹配统计；其他结果进入 unknown。

### C. Session-level cost

- `session_total_tokens`
- `model_cycles`
- `tool_calls`
- `usage_source`

该层来自 Codex 累计 usage 或冻结 harness，不得通过工具输出大小推算。

### D. Profiler cost

- Hook 执行次数与本地执行时间。
- 日志和报告字节数。
- Profiler 引起的额外模型周期、工具调用或错误；预期必须为 0。

报告不得把 A/B 层的下降称为完整会话节省，除非 C 层配对实验独立证明。

## 7. 事件与隐私数据模型

v0 事件建议至少包含：

```text
schema_version
session_id_hash
event_id
timestamp
tool_family
command_shape
result_status
path_hashes
explicit_ranges
raw_chars
estimated_tokens
estimation_method
output_sha256
code_bearing
coverage_state
coverage_reason
duration_ms
```

默认禁止持久化：

- 源码正文和工具输出正文；
- 完整 shell 命令；
- prompt、模型回答和完整 transcript；
- 环境变量值、凭据、URL query 和用户主目录原文。

路径使用稳定项目内相对标识或 salted hash。命令只保存命令族和结构形态，例如 `rg_then_sed`，不保存参数原文。调试原始 artifact 必须显式启用、写入 Git ignore 的私有目录并限制权限。

## 8. 成本分类与重复定义

ACP-0 先提供保守分类：

- `code_read_result`
- `code_search_result`
- `test_or_build_result`
- `script_or_other_result`
- `unknown_result`

重复分三层，不能混合报告：

1. `exact_payload_duplicate`：相同规范化结果哈希。
2. `same_file_repeat`：同一文件被再次读取，但范围可能不同。
3. `range_overlap`：同一文件显式行范围发生重叠，报告重叠行数/比例；无法可靠解析范围时为 unknown。

“重复”不自动等于“浪费”。ACP-0 只记录重复事实；是否必要留给后续诊断阶段。

## 9. 覆盖账本

每个结果必须拥有一个覆盖状态：

- `observed_and_matched`
- `observed_not_matched`
- `transcript_only`
- `unsupported_tool_path`
- `parse_unknown`

汇总同时报告：

- 调用覆盖率；
- 结果字符加权覆盖率；
- 模型可见 Token 估算加权覆盖率；
- 按工具族/命令形态的覆盖；
- unknown 数量、体量和原因。

只允许对 `observed_and_matched` 数据做强归因。

## 10. 架构边界

```text
Codex natural task
    ↓
PostToolUse observe-only collector
    ↓
privacy normalizer + event ledger
    ↓
offline transcript/usage correlator
    ↓
coverage + cost attribution
    ↓
session report
```

Collector 必须保持最小、同步、失败开放。关联、聚合和报告尽量离线运行，避免在 Agent 工作时增加成本。

## 11. 分阶段任务

### ACP-0.0：冻结合同与 fixture

- [x] 固定 schema、成本层级、覆盖状态、隐私禁区和 Token 口径。
- [x] 复用 CO-1.3/1.4 的脱敏结构化结果建立 replay fixture，不复制私有源码正文。
- [x] 保存版本、commit、任务集和计量方法。

冻结产物（2026-08-17）：

- `ACP_0_0_CONTRACT.md`：人可读 measurement/privacy/coverage 合同与现有 Hook 差距。
- `resources/acp0_contract.json`：`acp-event-v1`、`acp-measurement-v1`、`acp-privacy-v1` 机器合同。
- `resources/acp0_co1_4_replay_fixture.json`：CO-1.4 脱敏 12-session/16-event replay，冻结 17,651 个模型可见估算 Token。
- `tests/test_acp0_contract.py`：检查合同枚举、隐私 allowlist、来源 hash 和基线汇总。

核对结论：旧 `audit_tool_output.py` 是 observe-only 且不保存 result 正文，但其原始 `session_id`/`explicit_paths` 不满足新隐私合同；当前 manifest 仍包含冻结研究用 optimizer Hook，整个 chain 不能作为 ACP collector 验收。两项均留给 ACP-0.1，本阶段未改 collector 或启用 replacement。

### ACP-0.1：Observe-only collector

- [x] 从现有 audit Hook/CO-1.4 probe 中提取最小 collector。
- [x] 强制禁止 block/rewrite 字段，ACP manifest 不加载 optimizer/rewrite Hook。
- [x] 写入权限受限、按 repository domain 隔离的 HMAC 伪名元数据日志。
- [x] CO-1.4 replay parity、无 stdout/stderr、result hash 保留与故障注入 fail-open 专项通过。

实施与 Gate 记录见 `ACP_0_1_IMPLEMENTATION_PLAN.md`。ACP-0.1 在五个 Gate 通过后已停止；不包含离线 correlator/report 或正式自然任务 no-interference A/B。

### ACP-0.2：Normalizer 与 coverage ledger

- [x] 验证并保留 collector 的保守 tool family、command shape、脱敏文件/范围事实，不从已删除的命令重新推断。
- [x] 将不确定解析、unmatched、ambiguous、unsupported、transcript-only、unknown denominator 和 rejected input 显式记账。
- [x] 仅使用脱敏 stable ID/session/tool-family/output-hash 建立 Hook event 与 transcript result 的可复现一对一关联。
- [x] 冻结 `normalized-event-v1`、`transcript-call-v1`、`coverage-ledger-v1`、语义字典与 paired/synthetic 回放。

详见 `ACP_0_2_IMPLEMENTATION_PLAN.md`。ACP-0.2 在六个 Gate 通过后已停止；用户可读报告和 derived interpretation 未提前实现。

### ACP-0.3：Cost attribution report

- [x] 输出冻结的 A/B/C/D 四层事实与 Session/Cycle/Call/Evidence-Coverage 下钻视图。
- [x] JSON 是唯一事实来源；Markdown/CLI 只渲染 fact report，不重新关联或计算 pipeline。
- [x] CO-1.4 baseline、synthetic partial/privacy、traceability、determinism 和 fact-only 六个 Gate 通过。

详见 `ACP_0_3_IMPLEMENTATION_PLAN.md`。ACP-0.3 在六个 Gate 通过后已停止；完整 session usage、cycle identity 和正式 no-interference paired evidence 仍保持 unknown，留给 ACP-0.4。

### ACP-0.4：No-interference Gate

- [x] Native/Profiler 使用相同任务、commit、隔离 worktree/home 与 6 AB / 6 BA 顺序完成 12 个 pair。
- [x] Host transparency、fail-open、12/12 correctness、真实 collector activation 和 cycle/call 统计门通过。
- [ ] Cost neutrality 未通过：paired median ratio `0.999586`，pooled ratio `1.027420 > 1.02`。

详见 `ACP_0_4_IMPLEMENTATION_PLAN.md` 与 `resources/acp0_4_results.json`。ACP-0.4 已实施但失败；ACP-0 不标记 COMPLETE，不进入 ACP-1。

### ACP-0.4a：Repeated Runs + Variance Attribution

- [x] 冻结 collector、Hook manifest、原 task set、run7 失败结论与 `1.02` Cost Gate。
- [x] 完成 12 cases × 2 arms × 5 repetitions，共 120 个全新 run；不删除 outlier、不补跑单个 case。
- [x] pooled ratio `1.007010` 与 conditional ratio `0.999022` 通过成本证据；95% run 可按冻结 path signature 配对。
- [x] tool-entry rate delta 为 0，mean call/cycle delta 均为 `+0.016667`，无预注册系统性路径信号。
- [ ] correctness 硬门未通过：同一 case OFF/ON 均为 `3/5`，合计四个错误 run 原样保留。

因此 0.4a 结论冻结为 `INCONCLUSIVE / GRADUATION_FAIL`，不能把成本证据单独提升为 ACP-0 毕业。详见 `ACP_0_4A_IMPLEMENTATION_PLAN.md` 与 `resources/acp0_4a_results.json`。

### ACP-0.4b：Correctness Gate Audit and Redefinition

- [x] 审计确认 `single_file_range_count` ground truth 唯一为 `7`，原 scorer 明确，不修改历史 fixture。
- [x] Native/OFF-only 20/20 完成，correct `14/20`，按预注册阈值冻结为 `stochastic_diagnostic`。
- [x] 全新 prospective OFF/ON 各 20 次完成：OFF `12/20`、ON `13/20`，accuracy delta `+0.05 ≥ -0.10`。
- [x] 20/20 ON tool calls 被 collector 观察；两臂 tool calls/cycles 均固定为 1/2，host/fail-open 通过。
- [x] correctness runs 不进入 cost/path Gate；组合 0.4a 已通过的 cost/path/host 证据后，ACP-0 graduation 为 `PASS`。

ACP-0.4 与 0.4a 的旧 verdict 永久保留。0.4b 是预注册后的新 closure evidence，不追溯重算旧结果。详见 `ACP_0_4B_IMPLEMENTATION_PLAN.md`、`resources/acp0_4b_native_calibration_results.json` 与 `resources/acp0_4b_results.json`。

## 12. ACP-0 验收标准

以下全部满足才可进入 ACP-1：

- [x] Hook 始终 observe-only，不包含 `decision:block` 或结果替换。
- [x] CO-1.4a 冻结 replay 中自然 Bash code-bearing 覆盖不低于 16/16 和 17,651/17,651 Token。
- [x] 每项已归因成本可追溯到明确 event/tool call/model cycle；无法关联的内容进入 unknown。
- [x] 原始结果、模型可见结果、完整 session Token 和 Profiler 自身成本分层输出。
- [x] 能区分 exact payload、same-file repeat 和显式 range overlap。
- [x] 默认日志不含源码正文、完整命令、prompt、模型回答、凭据或完整绝对路径。
- [x] 相同 fixture 连续复算产生字节稳定或语义等价的 JSON 报告。
- [x] 自然任务 correctness 采用 benchmark-validity-aware、预注册的 prospective OFF/ON criterion 并通过。
- [x] Profiler 不新增 model cycle、tool call、retry/recovery 或工具错误状态。
- [x] 报告明确列出 unsupported/unknown 路径，不将局部覆盖宣传为全 Agent 覆盖。
- [x] 全部旧测试继续通过，新增 schema、隐私、关联、重复和 no-interference 回归测试。

ACP-0 不设置“节省 5%”之类指标，因为它不执行优化。通过标准是计量可信、覆盖诚实、行为无干扰。

## 13. 失败与停止条件

出现以下任一情况，应暂停 ACP-0 扩展并记录失败：

- observe-only Hook 改变工具成功状态或产生模型可见反馈；
- 自然 Bash 覆盖显著低于冻结基线且无法解释；
- session usage 无法稳定关联，报告却必须依赖推算；
- 隐私目标要求保存源码正文或完整 transcript 才能成立；
- Profiler 自身成本或错误使 Agent 行为发生系统性变化。

不得通过增加 shell pattern、保存更多敏感正文或注入模型提示来掩盖失败。

## 14. 后续路线，但不提前实施

只有 ACP-0 通过后再讨论：

### ACP-1：Cost Attribution & Session Report

形成面向用户的会后报告，例如代码读取占比、重复事实、最高成本工具族和 unknown 覆盖缺口。诊断必须展示证据和置信度。

### Context Analyzer v0

把 slicer/risk gate 封装为独立离线库：输入 path/target/task，输出候选上下文、外部依赖、风险原因、预计缩减和 fail-open reason。它不宣称生成“最小充分上下文”，也不自动接管 Agent 读取。

### Optimization Regression Lab

将现有 Native/treatment harness 泛化，用于验证 repo map、cache、context pruning、prompt compression 等新想法，primary metric 仍为 correctness 和完整 session Token。

### Recommendation Experiment

第一版只生成会后建议。只有稳定证明某类浪费存在后，才单独 A/B 测试实时提示；不得假设提示本身免费。

长期产品链路建议为：

```text
Observe → Measure → Attribute → Diagnose → Recommend
```

`Compress` 是旁路的独立能力，不是默认链路的必然最后一步。

## 15. 可复用资产入口

- 冻结结论：`TRANSPARENT_SMART_READ_FROZEN.md`
- 长期约束：`LONG_TERM_CONSTRAINTS.md`
- Host 观察证据：`CO_1_4A_RESULTS.md`
- Host 替换阻塞：`CO_1_4_RESULTS.md`
- 自然行为数据：`resources/co1_4_observe_results.json`
- 替换实验数据：`resources/co1_4_results.json`
- 当前审计 Hook：`scripts/audit_tool_output.py`
- 当前报告器：`scripts/report_audit.py`
- 事件解析基础：`scripts/m2e_events.py`
- CO-1.4 观察 runner：`scripts/run_co1_4_host_probe.py`
- A/B harness 参考：`scripts/run_co1_3_ab.py`

## 16. 新对话启动说明

新对话应先读取：

1. `ACP_0_IMPLEMENTATION_PLAN.md`
2. `TRANSPARENT_SMART_READ_FROZEN.md`
3. `LONG_TERM_CONSTRAINTS.md`
4. `CO_1_4A_RESULTS.md`
5. `CO_1_4_RESULTS.md`

建议给新对话的启动请求：

> 继续 Agent Token Manager 项目。先读取 `ACP_0_IMPLEMENTATION_PLAN.md`、`TRANSPARENT_SMART_READ_FROZEN.md` 和 `LONG_TERM_CONSTRAINTS.md`。确认 Transparent Smart Read 保持冻结，不实现 replacement、slicing 或实时推荐。本轮只执行 ACP-0.0：核对现有 audit Hook、事件格式和 CO-1.4 fixture，冻结 measurement contract、privacy schema 与 coverage taxonomy；完成后更新计划和 STATUS，并按验收标准检查本轮目标。

第一项实施任务固定为 **ACP-0.0**。除非发现合同无法成立，否则不要在新对话中重新讨论 Transparent Smart Read 架构。
