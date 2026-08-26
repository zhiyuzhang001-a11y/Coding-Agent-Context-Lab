# ACP-0.0 冻结合同：计量、隐私与覆盖

- 状态：`FROZEN`
- 冻结日期：2026-08-17
- 合同版本：`acp-event-v1` / `acp-measurement-v1` / `acp-privacy-v1`
- Token 估算：`chars_div_4_v1`，即 `ceil(chars / 4)`
- 基线来源：`resources/co1_4_observe_results.json`
- 机器可读合同：`resources/acp0_contract.json`
- 脱敏回放：`resources/acp0_co1_4_replay_fixture.json`

## 1. 产品边界

Transparent Smart Read 继续保持 `FROZEN / BLOCKED_HOST_INTERFACE`。ACP-0 是独立的 observe-only 计量线，不执行 result replacement、AST slicing、压缩、prompt 注入或实时推荐。

## 2. 现有实现核对

`scripts/audit_tool_output.py` 是失败开放的 observe-only audit v1：它不返回 Hook decision，不保存工具输出正文，并使用 `chars_div_4_v1` 估算结果 Token。但它不是 ACP 事件收集器，因为当前仍持久化原始 `session_id` 和 `explicit_paths`，且字段名与 ACP 合同不同。

ACP-0.0 核对时，`hooks/hooks.json` 同时注册了上述 audit 和冻结研究用 `context_optimizer_hook.py`；后者在非默认模式可以返回 `decision:block`，因此当时整个 Hook chain 不能作为 ACP collector 验收。该缺口已在 ACP-0.1 解决：当前 manifest 只注册 `acp_collector.py`，冻结 optimizer 代码不再进入 ACP 执行链。

CO-1.4 fixture 已确认 12 个 session、16 个 natural code-bearing Bash result、17,651 个模型可见估算 Token；调用覆盖、Token 加权覆盖与 raw→Hook→transcript 关联均为 100%。这只是已冻结数据集上的 Bash 观察基线，不外推到 direct read、MCP、LSP 或 hosted tools。

## 3. Measurement contract

每份报告必须并列保留四层，不得互相推算或替代：

1. `observed_tool_result_cost`：`raw_output_chars`、`estimated_raw_tokens`、`tool_result_count`、`code_bearing_result_count`。
2. `model_visible_tool_context`：`model_visible_chars`、`estimated_model_visible_tokens`、`matched_tool_result_count`、`unmatched_tool_result_count`。只有 `observed_and_matched` 可进入强归因。
3. `session_level_cost`：`session_total_tokens`、`model_cycles`、`tool_calls`、`usage_source`。未观测到时为 `null/unknown`，不由工具输出量外推。
4. `profiler_cost`：Hook 次数/耗时、日志/报告字节、Profiler 额外 model cycle/tool call/error。不干扰目标为 0。

重复事实分开报告：`exact_payload_duplicate`、`same_file_repeat`、`range_overlap`。后两者在没有脱敏文件标识或可靠显式范围时必须为 unknown；重复不等于浪费。

## 4. Privacy schema

持久化事件只能使用机器合同的 allowlist 字段，额外字段一律拒绝。禁止源码/工具输出正文、完整命令、prompt/回答/transcript、未脱敏 session/turn/tool-use ID、凭据和 URL query、原始绝对路径与用户主目录。

Session 和 path 标识使用仓库作用域的秘密 salt 生成 64 位 SHA-256；salt 以 `0600` 保存于事件日志之外，不写入报告。path 只对规范化的 project-relative 标识做哈希，绝对仓库根不进入事件。原始调试 artifact 必须显式 opt-in，写入 Git-ignore 且权限受限的私有目录，不属于 ACP 默认数据。

## 5. Coverage taxonomy

每个结果必须且只能使用一个状态：

- `observed_and_matched`：Hook 事件与 transcript result 稳定关联；可强归因。
- `observed_not_matched`：Hook 看到结果，但无法稳定关联 transcript；model-visible 成本 unknown。
- `transcript_only`：transcript 存在结果，但无 Hook 事件；raw 成本 unknown。
- `unsupported_tool_path`：已知工具路径不在 collector 支持边界内。
- `parse_unknown`：观测存在，但命令形态、文件或范围不能保守解析。

覆盖汇总同时报告 call coverage、raw/model-visible 字符或 Token 加权覆盖、按 tool family/command shape 的覆盖，以及每种 unknown 的数量、体量和 reason。分母必须是实际观测集，不得对未覆盖 Agent 路径外推。

## 6. ACP-0.0 验收结论

- [x] Transparent Smart Read 冻结边界复核；未实现 replacement、slicing 或实时推荐。
- [x] 四层计量口径、Token 方法、重复定义已冻结。
- [x] 事件 allowlist、哈希规则、默认隐私禁区已冻结。
- [x] 五种 coverage state 及强归因边界已冻结。
- [x] CO-1.4 脱敏 replay 保留 16/16 与 17,651/17,651 基线，且不含正文/命令/路径。
- [x] 合同测试检查版本、枚举、隐私 allowlist、fixture 来源 hash 与精确汇总。
- [x] ACP-0.1 已将 observe-only collector 从冻结 optimizer 链抽离，并落实本合同的隐私 allowlist。
- [ ] 关联/report/正式 no-interference 验收仍属于 ACP-0.2–0.4，不在 ACP-0.1 提前实现。
