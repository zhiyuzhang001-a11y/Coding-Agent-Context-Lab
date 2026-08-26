# ACP-0.1 实施计划：Privacy-safe, behavior-preserving collector migration

- 状态：`COMPLETE`
- 日期：2026-08-17
- 冻结 collector 版本：`acp-collector-v0.1` / `0.1.0+codex.20260817112704`
- 前置合同：`ACP_0_0_CONTRACT.md`
- 事件合同：`acp-event-v1`
- 非目标：replacement、slicing、压缩、实时 recommendation、浪费判定和优化机会识别

## 目标

> 不证明 ACP 很聪明，只证明 collector 没有撒谎，也没有碰 Agent。

ACP-0.1 只把观测层从旧 optimizer 实验线中抽离，将宿主事件在内存中脱敏为闭合 allowlist telemetry 后持久化。

```text
ephemeral host event
        ↓
privacy normalization
        ↓
persisted normalized telemetry
        ↓
offline correlation / derived metrics (later stages)
```

ACP-0.1 最多做到 persisted normalized telemetry。原始 Hook event、工具输入/输出正文、命令和 transcript 不落盘。

## Gate

### Gate A — Execution isolation

- ACP `PostToolUse` chain 只注册 collector。
- `context_optimizer_hook.py` 等冻结研究代码保留，但不进入 ACP 执行链。
- 不依赖“默认 observe”或环境开关证明隔离。

### Gate B — Privacy enforcement

- 持久化字段与 `acp-event-v1` allowlist 完全一致。
- session/path ID 使用 repository-scoped HMAC-SHA256；密钥独立 `0600` 保存。
- project-relative path 只是内存中的 HMAC 输入，不持久化 basename、相对路径或绝对路径。
- 缺失 session metadata 时生成事件级伪名，并记录 unknown reason，不伪造可跨事件关联的 session。

### Gate C — Replay parity

同一 CO-1.4 fixture 每次 replay 必须产生字节稳定的 JSON，并保留：

- 12 sessions；
- 16 calls；
- 17,651 model-visible estimated tokens；
- 16/16 linkage 与 100% call/Token-weighted coverage。

Collector 直接记录的只是 raw result 层 `raw_chars/estimated_tokens`。model-visible 指标来自冻结 fixture 的离线关联，不由 collector 外推。

### Gate D — Behavioral transparency

- collector 不返回 block、replacement、additional context 或其他 Hook decision。
- collector stdout/stderr 始终为空。
- collector ON/OFF 不改变工具状态和 host-visible result content/hash。
- 正式自然任务 correctness/model-cycle/tool-call A/B 仍属于 ACP-0.4，不扩张 ACP-0.1。

### Gate E — Fail-open

下列故障可丢失 telemetry，但不得改变或终止宿主工具流：

- 日志/密钥目录不可写；
- malformed/non-object event；
- serialization/append failure；
- unknown tool；
- 缺失 session/tool metadata。

## 停止条件

Gate A–E 全部通过后立即停止 ACP-0.1，不因代码量少而追加功能。通过后可冻结 collector 版本；normalizer/correlator 扩展、事实报告和正式 no-interference benchmark 仍按 ACP-0.2–0.4 执行。

## 完成与验收（2026-08-17）

- [x] Gate A：`hooks/hooks.json` 只注册 `scripts/acp_collector.py`；冻结 optimizer 未进入 ACP chain。
- [x] Gate B：事件严格等于 `acp-event-v1` allowlist；session/path 使用 repository-domain-separated HMAC-SHA256，密钥与日志为 `0600`；原始 session、命令、正文和路径不持久化。
- [x] Gate C：确定性 replay 字节稳定，复现 12 sessions、16 calls、17,651 model-visible estimated tokens 和 100% frozen linkage/coverage。
- [x] Gate D：collector 不修改输入 event，不输出 stdout/stderr/Hook decision，保留原始 result hash。正式自然任务 A/B 仍留在 ACP-0.4。
- [x] Gate E：不可写路径、malformed event、append/serialization failure、unknown tool 和缺失 session metadata 均失败开放。

验收记录：专项 24/24，仓库全套 154/154，`py_compile`、JSON 解析和 `git diff --check` 通过。ACP-0.1 到此停止，未加入 slicing、replacement、recommendation 或 derived waste metrics。
