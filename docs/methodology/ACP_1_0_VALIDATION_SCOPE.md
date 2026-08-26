# ACP-1.0 Validation Scope

- 状态：`ACP-1.0 Cost Attribution Baseline — COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- Baseline ID：`acp1-0-co1-4-cost-attribution-v1`
- 证据入口：`resources/acp1_0_frozen_baseline_index.json`
- Manifest：`resources/acp1_0_frozen_experiment_manifest.json`

## 该完成声明证明什么

在冻结 CO-1.4 脱敏 replay fixture、冻结 measurement semantics、已准入 benchmark registry 与 manifest 中记录的派生环境内：

- ACP-0 → ACP-1.0 离线链可字节级确定性重放；
- 12 sessions、16 calls 与 17,651 observed matched visible estimated Tokens 保持基线一致；
- coverage、unknown、privacy、traceability 语义未被 attribution 或 renderer 改写；
- manifest 绑定 baseline index，index 绑定 fixture、spec、runner、registry、组件与派生产物 hash；
- 报告仅描述成本去向、集中度与客观重复 evidence volume，不生成 waste、avoidable 或 recommendation 判断。

## 该完成声明不证明什么

- 不证明对其他 fixture、宿主版本、模型或 sandbox 全局有效；
- 不证明 exact repeated evidence 是浪费或可删除；
- 不证明 tool-visible Tokens 等于完整 session Token；
- 不填补源 observation 中不可靠的 model/reasoning、Hook API、model cycles 或 session total；
- 不授权 replacement、slicing、实时推荐或任何 online collector 扩展。

## 显式 unknown

- `environment.hook_api_version`
- `source_observation.model_identifier`
- `source_observation.reasoning_effort`
- `attribution.session_total_tokens`
- `attribution.model_cycles`

unknown 是合同的有效输出，不是零、不是空默认，也不影响已观测 tool-visible scope 内的 complete coverage 结论。

## 重新校准与失效条件

host/model/Hook API、collector online path、关键 measurement semantics、OS/architecture/config/sandbox 等 full-paired 字段变化时，必须按 ACP-0H policy 重新执行 full paired recalibration。normalizer/reporter/attributor/renderer、schema、fixture 或 expected canonical output 变化时，至少执行 smoke recalibration。新结果不覆盖该 baseline，而是以新 ID/version 生成新 manifest chain。
