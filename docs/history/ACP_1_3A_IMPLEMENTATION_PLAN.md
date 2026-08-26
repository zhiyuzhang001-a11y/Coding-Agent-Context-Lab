# ACP-1.3A 正式任务书：Host-Reported Model-Cycle Cost Analysis

- 状态：`ACP-1.3A Host-Reported Model-Cycle Cost Analysis — COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- 数据源：ACP-0.4a 冻结的 120 次 OFF/ON 私有 transcript
- 目标输出：`model-cycle-cost-analysis-v1`

## 目标

ACP-1.3A 只回答：在可靠的 host cumulative usage snapshot 中，各 cycle ordinal 的已观测增量和累计 Token 是多少？

```text
private frozen transcript + frozen run result
                  ↓ exact thread/session ID linkage
privacy-safe cycle observations
                  ↓ offline fact analysis
model-cycle-cost-analysis-v1
```

本阶段不判断 waste、necessity 或 avoidability，不执行删减、replacement、slicing 或 intervention。

## Cycle 与 usage 语义

1. cycle 是 transcript 中按文件顺序出现、且含有效 `event_msg.token_count.info.total_token_usage` 的 host usage snapshot。
2. 只有 `thread.started.thread_id == session_meta.id/session_id` 才关联 run 与 transcript；不用 timestamp、路径相似或内容猜测。
3. `cycle_increment[1] = cumulative_usage[1]`。
4. `cycle_increment[n] = cumulative_usage[n] - cumulative_usage[n-1]`。
5. 所有累计 counter 必须单调不减，最后 snapshot 必须与 frozen run result 一致。
6. `total_tokens = input_tokens + output_tokens`；`cached_input_tokens` 是 input 的子集，不再相加。
7. cached/uncached 不等于语义上的新内容/历史上下文；该分解保持 `unknown`。

## 分层与样本充分性

- OFF 60 runs 是 Native primary analysis。
- ON 60 runs 是 independent replication，不与 OFF 默认混池。
- 报告保留 arm 和 case 分层，不把任务难度差异当成 cycle 因果效应。
- ordinal、transition 或 cycle-count group 只有在单个 arm 内 `n >= 5` 时标为 `sufficient_descriptive_sample`，否则为 `insufficient_descriptive_sample`。
- 小样本仍完整列出，但不进入形状结论。

## 允许的事实指标

- cycle-count distribution 与各组 session total distribution；
- 每个 ordinal 的 cumulative/incremental usage；
- 同一 run 相邻 ordinal 的 incremental-cost delta 与 ratio；
- count / min / median / mean / max；
- exact linkage、usage identity、arm/case 覆盖与 unknown 状态。

`incremental cycle cost` 是 usage counter 差分，不是“强制增加一轮”的反事实因果成本。

## Gate

1. **Cycle semantics frozen**：cycle、counter identity、差分与 sufficiency 先于正式输出冻结。
2. **Exact linkage**：120/120 run 仅通过 thread/session ID 唯一关联。
3. **Privacy-safe extraction**：公开 artifact 不含 prompt、response、final answer、source body、绝对路径或 raw session ID。
4. **Stratified fact-only analysis**：OFF primary、ON replication 分开，不产生因果或 waste 判断。
5. **Unknown preserved**：新内容/历史上下文、necessity 和反事实成本保持 unknown。
6. **Determinism**：同一私有输入字节生成相同 observation、analysis 和 renderer 输出。
7. **Governance/traceability**：12 个 case 必须存在于 frozen registry，正式 artifact 进入 manifest/checksum chain。
8. **Frozen integrity**：collector、Hook 和 ACP-1.0/1.1/1.2 frozen artifacts 不变。

## 实施顺序

- [x] ACP-1.3A-0：冻结语义、隐私和分层合同。
- [x] ACP-1.3A-1：实现私有 transcript 只读 extractor 与事实 analyzer。
- [x] ACP-1.3A-2：实现 schema、fixture、renderer 与回归测试。
- [x] ACP-1.3A-3：生成 governed manifest-bound frozen baseline；index 为 `0715444a6d373727298b968ac6294ba57c1e794cf1e814b87359d2262c51b110`，manifest 为 `0bee7c218d1bbfe893473327ad577701536b588db5c607f8bb6c7810dcc33720`。
- [x] 更新 measurement contract、PROJECT_PLAN 和 STATUS，运行全量验收。

## 冻结结果

- 120/120 run 通过 exact thread/session ID 关联，共 287 个 host usage snapshot；
- OFF primary 的 cycle-count 分布为 `2:38 / 3:21 / 4:1`，ON replication 为 `2:37 / 3:22 / 4:1`；
- OFF cycle 1–4 incremental median 为 `15,549 / 15,958.5 / 16,969.5 / 23,042`；
- ON cycle 1–4 incremental median 为 `15,556 / 15,955 / 17,043 / 23,152`；
- OFF 1→2 / 2→3 同 run incremental ratio median 为 `1.025937891418 / 1.020076212141`；ON 为 `1.025928058203 / 1.022400270835`；
- cycle 4 每臂只有 1 run，标记 `insufficient_descriptive_sample`，不进入形状结论；
- 在冻结范围内，cycle 1–3 的已观测增量中位数为温和上升，没有证明快速加速的 amplification shape；
- 新内容/历史上下文、语义重复处理、因果增轮成本、necessity 与 avoidability 全部保持 unknown。

## 明确不做

- 不修改 collector 或 online Hook chain；
- 不用 timestamp 猜 cycle 或 run linkage；
- 不把 cached input 命名为历史上下文；
- 不输出 wasted/avoidable/potential-savings Token；
- 不执行 intervention，不重开 Transparent Smart Read。
