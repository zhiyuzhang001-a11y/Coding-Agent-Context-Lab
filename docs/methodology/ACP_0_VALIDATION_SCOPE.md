# ACP-0 Validation Scope and Graduation Certificate

## Certificate

> **ACP-0 Measurement Foundation — COMPLETE under frozen validation scope**
>
> **ACP-0 测量基础完成：在冻结任务集、模型、collector、实验设计与预注册 Gate 范围内通过验证。**

- 生效日期：2026-08-18
- 产品线：Agent Cost Profiler
- 当前阶段：ACP-0 完成并冻结；ACP-1.0 已进入离线合同/实现阶段，ACP-0H 与其并行
- 结论性质：工程阶段毕业，不是全局零干扰证明或统计学因果证明

## 这项毕业结论表示什么

在下述冻结范围与已执行实验中，没有证据表明 ACP collector 造成超过预注册边界的 session 成本、执行路径、correctness 或 host-visible behavior 干扰。measurement、privacy、coverage、deterministic replay、fact-only reporting、observe-only、fail-open 和 prospective correctness parity 的阶段 Gate 已全部闭合。

因此 ACP 测量链可以作为后续离线成本分析的受控仪器使用，但所有报告仍必须携带 coverage/unknown，且不得把局部观察外推为全 Agent 成本。

## 冻结验证范围

- Subject commit：`b506818b3db87be62064ad64e62b1ad262d5a4b9`。
- 自然任务 fixture：`acp0-4-natural-paired-v1`，12 cases。
- Model：`gpt-5.6-sol`；reasoning effort：`medium`。
- Collector：`acp-collector-v0.1`，SHA-256 `81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2`。
- Hook manifest SHA-256：`797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd`。
- Measurement/privacy/coverage：`acp-measurement-v1`、`acp-privacy-v1`、`acp-event-v1` 与五态 coverage taxonomy。
- Normalizer/reporter：`acp-normalizer-v0.1`、`fact-report-v1`、`acp-reporter-v0.1`。
- Token estimation：`chars_div_4_v1`；session total 使用冻结 Codex cumulative usage 来源，不用工具输出估算冒充。
- 实验设计、runner、spec 和结果由 `resources/acp0_contract.json` 的 SHA-256 审计项锚定。

宿主说明：实验记录了实际使用的 Codex 执行路径和行为 probes，但没有在每个模型 run 中同时冻结并持久化宿主二进制版本或二进制 SHA-256。因此本证书不能表述为“宿主身份已被密码学冻结”，只能表述为在当时 observed host environment 中通过；宿主或 Hook API 变化会触发重新验证。

## 证据演进，不改写历史

### ACP-0.4

12 个 OFF/ON pair 的 correctness、host、collector activation、cycle/call 和 paired median Gate 通过，但 pooled Token ratio 为 `1.027420 > 1.02`。正式结论永久保留为 `FAILED_COST_NEUTRALITY`。

### ACP-0.4a

120 个全新 run 将 pooled ratio 复验为 `1.007010`，conditional ratio 为 `0.999022`，conditional path coverage 为 95%，且没有命中预注册 path-shift signal。由于一个 case 的 absolute correctness Gate 失败，正式结论永久保留为 `INCONCLUSIVE / GRADUATION_FAIL`。

这组证据与 Agent 自身运行方差相容，并削弱了 collector 存在系统性成本或路径干扰的怀疑；它不单独证明 0.4 的 outlier 具有唯一随机成因。

### ACP-0.4b

审计确认 `single_file_range_count` 的唯一 ground truth 为 `7`，但 Native/OFF-only 仅为 `14/20`，因此按预注册规则分类为 `stochastic_diagnostic`。随后全新 prospective OFF/ON 为 `12/20` 与 `13/20`，`accuracy_ON - accuracy_OFF = +0.05`，通过冻结工程下限 `-0.10`；host/fail-open、20/20 ON collector coverage 和固定 call/cycle 路径同时通过。

0.4b 通过的是 correctness parity，不是 absolute correctness。其额外 runs 没有进入 0.4a 的 cost/path Gate。

## 已证明与未证明

已在冻结范围内获得证据支持：

- collector 保持 observe-only，不返回 replacement/block，不修改 host-visible result；
- collector 故障 fail-open，stdout/stderr 为空；
- 默认持久化满足 closed allowlist、HMAC pseudonymization 与正文禁存要求；
- CO-1.4 replay 保持 12 sessions、16/16 calls、17,651/17,651 model-visible estimated Tokens；
- normalization/correlation/ledger/report 可确定性复算，unknown 不被填补；
- 0.4a cost/path Gate 与 0.4b prospective correctness parity Gate 通过。

本证书没有证明：

- 所有任务、语言、工具类型、仓库规模或随机运行下绝对零干扰；
- correctness 绝对正确或每次重复均一致；
- hosted tools、MCP、LSP、direct read 或宿主未暴露成本得到完整覆盖；
- `chars_div_4_v1` 等于供应商账单 tokenizer；
- 模型内部隐藏上下文、system prompt、缓存或供应商计费分解可被 ACP 观测；
- 20×2 correctness closure 是统计学非劣效性或因果证明；`-0.10` 是预注册工程 Gate。

## Unknown 与报告义务

`unknown` 是合法且必须保留的测量结果。缺少可靠来源时，session/cycle/call/linkage/coverage 维度不得互相推算；unsupported path 不得按已观察比例外推。事实报告必须同时展示 denominator、coverage status、unknown volume 与来源。

## 重新校准触发条件

以下任一变化均使本证书不能自动外推，至少需要 targeted regression；影响 online path、measurement semantics 或宿主行为时需要完整 ACP-0.4a/0.4b 等价复验：

- collector、Hook manifest、Hook event/decision API 或 fail-open 语义变化；
- Codex 宿主、模型、reasoning effort、sandbox、usage/transcript 格式变化；
- event/privacy/measurement/coverage schema 或 Token 口径变化；
- normalizer correlation 假设、ledger denominator 或 reporter 事实计算变化；
- task fixture、oracle、scorer、Gate 阈值、重复次数或 arm scheduling 变化；
- 新增 MCP/LSP/direct-read/hosted-tool 等覆盖声明；
- 回归监测发现 correctness、path、cost、host hash 或 collector coverage 漂移。

## ACP-0 冻结后的硬化候选

这些候选已整理为有限、非阻塞的 `ACP-0H Measurement Hardening v1`，详见 `ACP_0H_IMPLEMENTATION_PLAN.md`。ACP-1.0 可以并行开始；两轨交付边界与首次正式实验前置条件以该任务书为准。

以下改进有价值，但不是追溯修改本次毕业结果的理由：

1. **P0 环境 provenance**：未来每个 run 记录 Codex version、宿主/CLI binary hash、OS/architecture、sandbox/config digest 与运行时间块。
2. **P0 artifact chain of custody**：为私有 run manifest、summary、runner、fixture 和公开 compact result 生成统一不可变 checksum manifest。
3. **P1 低成本 revalidation**：拆分每次提交可跑的 deterministic/schema/privacy smoke，与宿主/模型变化时才跑的昂贵 paired suite。
4. **P1 分时段重复实验**：未来用跨时间 block、AB/BA 平衡和预注册置信区间补充当前工程阈值，降低单时段服务漂移影响。
5. **P1 benchmark 治理**：保留 stochastic diagnostic 历史 case，同时新增经 Native 校准的稳定 v2 cases；不删除旧 fixture。
6. **P2 coverage 扩展**：只在宿主确实暴露稳定事件与 linkage evidence 后增加新 tool path；否则继续标 unknown。
7. **P2 profiler operational metrics**：持续记录 local latency、log bytes、append failures 与 coverage drift，不把它们解释为 waste。

下列内容不属于 ACP-0 硬化，应留给 ACP-1 或独立实验：wasted/avoidable Token、duplicate-read 必要性判断、context amplification、优化机会、实时 recommendation、slicing、replacement 或自动压缩。
