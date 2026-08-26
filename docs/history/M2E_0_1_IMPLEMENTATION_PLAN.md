# M2e-0.1 实施计划：编排成本归因与协议压缩

最后更新：2026-08-15

状态：M2e-0.1a 成本归因已完成；M2e-0.1b 策略已冻结、尚未实施，不修改 Ranker、Graph、Discovery 或 M3。归因结果见 `M2E_0_1_ATTRIBUTION_RESULTS.md`，正式策略见 `M2E_0_1B_COMPACT_STRATEGY.md`。

## 1. 结论与架构决策

M2e-0 已经证明两件不同的事：

- M2d 的局部 Navigator 能在固定管理预算内改善未知目标到达率；
- 当前由 Codex 显式驾驶 `index → start → next → expand → feedback → ... → stop` 的方式，在两个校准任务上产生稳定的系统级负优化。

四个有效配对中，M2d 与 Native 均正确，但 M2d/Native 配对 Token 比率中位数为 `3.131x`。M2e-0.1a 修正诊断解析后，实际完成命令为 `51 vs 18`；原先的 `102 vs 36` 同时计算了 started/completed，`48 vs 15` 则是 started 空输出造成的伪重复。这不改变全会话负优化，也说明问题不是精确重复源码，而是更密集的协议往返和累积上下文处理。

因此 M2e-0.1 的核心目标从“继续改进检索”改为：

> 在不降低任务正确性的前提下，消除显式 Navigator 的模型往返和重复可见载荷，使 Smart Read 只在预期收益高于启动成本时工作。

近期采用的产品方向是：

> Codex 最多发起一次发现和一次核验；TaskState、Feedback、排序、去重与预算循环由本地确定性代码内部执行。

长期更理想的形态是透明的底层 `search/read` 优化器，但当前插件只有结果返回后的 `PostToolUse` 审计能力，不能据此宣称可替换已经返回给模型的原生工具结果。透明拦截作为独立接口研究，不阻塞 compact API。

## 2. 成本模型

先按三个可行动层归因，再按具体操作细分：

1. **固定启动成本**：Skill bootstrap、插件提示、索引检查和 TaskState 初始化；
2. **协议往返成本**：每次 `next/expand/feedback/stop` 触发的新一轮模型推理，以及累积上下文被再次处理的成本；
3. **模型可见载荷成本**：候选、排名解释、源码证据、重复证据和状态回显进入上下文的成本。

操作标签固定为：

```text
skill_bootstrap
index
start
next
expand
feedback
discover
stop
source_evidence
duplicate_source_read
duplicate_model_visible_payload
normal_codex_reasoning
editing_and_tests
other
```

每类至少报告：

- 调用次数；
- 模型可见 input/output 载荷估算；
- 占会话总 Token 比例；
- 是否贡献最终有效 evidence；
- 首次出现与最后一次出现位置；
- 相同或等价 payload 的重复次数。

### 2.1 计量边界

`codex exec --json` 当前只提供会话累计 usage，不能把精确模型 Token 无歧义地逐条分配给同一轮中的每个工具操作。因此：

- 全会话 `input + output` 继续作为唯一主指标；
- 工具 payload 使用同一估算器做诊断，不再次加进全会话 total；
- 能从事件边界取得的 usage 增量标记为 `observed_interval_usage`；
- 无法直接观测的普通推理成本作为残差，不伪装成精确归因；
- “某一项造成多少成本”的因果结论必须由消融实验确认，不能只凭描述性百分比。

## 3. M2e-0.1a：完整成本归因

复用 M2e-0 的原始 JSONL、命令、Hook 审计和 artifacts，先新增离线 trace 归因器，不启动新的 Codex 会话。

交付物：

- 版本化的 operation/roundtrip/payload trace schema；
- 每个校准会话的逐事件归因记录；
- 四个配对的聚合成本报告；
- 有效 evidence 与无贡献步骤的关联；
- `duplicate_source_read` 与 `duplicate_model_visible_payload` 分开统计；
- 对不可精确归因字段明确标记 `estimated`、`residual` 或 `unavailable`。

完成前不得优化协议。没有归因数据，不允许靠直觉删除 Feedback 或调整调用顺序。

## 4. M2e-0.1b：Compact Navigator

把当前显式循环收进本地实现，首个稳定接口建议为：

```text
context(task, total_budget, optional_hints)
→ decision
→ compact evidence package
→ omissions
→ confidence
→ stop_reason
→ cost summary
```

只有证据不完整或修改前需要补齐真实上下文时，允许第二阶段：

```text
verify(evidence_ids | symbols, remaining_budget)
→ verified evidence package
→ stop_reason
```

要求：

- 单个自然语言任务仍有独立 TaskState；
- 内部仍执行 Feedback、候选扩展、去重和 Hard Token Budget；
- Codex 不参与逐步 `next/expand/feedback` 调度；
- 详细排名轨迹只写入本地私有 trace；
- 模型只看到高价值 evidence、简短选择原因、遗漏和停止原因；
- 同一证据不在一个 package 或两阶段之间重复可见；
- Navigator 外部可见协议调用最多 2 次。

## 5. M2e-0.1c：Activation Gate

Smart Read 默认关闭。v0 Gate 不使用 LLM，只使用便宜、可解释的特征：

- 任务是否已给出明确文件或 symbol；
- 仓库和候选文件规模；
- 是否明显需要跨文件定位；
- 任务中代码标识符的存在与确定性；
- Native 首次窄搜索是否已经高置信命中；
- 是否已经发生低置信搜索、过宽读取或重复读取；
- Smart Read 的预计固定启动和返回成本。

输出必须包含：

```text
route = native | smart_read
reason
estimated_startup_cost
observed_trigger
```

v0 优先采用延迟激活：明确目标和小范围任务直接走 Native；只有原生窄搜索低置信、任务明显跨文件，或已经出现重复/过宽探索时才启用 Smart Read。

Gate 在 compact core 之后验证，避免通过“少激活”掩盖 Smart Read 自身仍然昂贵。两任务校准集只能检查明显 routing regret，不能证明普遍不存在错误拒绝；更完整的 false activation 与 missed activation 评估留给 M2e-1 pilot。

## 6. 消融顺序

所有消融保持检索结果、Hard Budget、模型、任务、正确性判据和实验隔离不变：

1. `M2d Full`：冻结的当前实现；
2. `- repeated model-visible payload`：只压缩重复回显；
3. `- feedback roundtrips`：Feedback 仍可在内部产生，不再逐次交给 Codex；
4. `- explicit next/expand loop`：本地内部循环，一次返回 compact package；
5. `two-stage verify`：只在证据不足时允许第二次调用；
6. `+ activation gate`：简单任务默认 Native，困难任务按廉价信号激活。

先使用 M2e-0 trace 做离线重放和 payload 消融；只有有希望的变体才运行昂贵的完整 Codex 配对。每次只改变一个主要因素，保留失败和离群值。

## 7. M2e-0.1 通过门槛

该阶段不要求立刻达到 M2e v0 的 15% 端到端节省，只要求把系统级负优化压回可继续验证的范围：

- [ ] 与 Native 相比任务正确性不下降，修改任务测试继续通过；
- [ ] M2d/Native 配对 Token 比率中位数 `≤ 1.25x`；
- [ ] 至少一个校准任务达到 `M2d < Native`；
- [ ] Smart Read 外部协议调用数相对 Full 下降至少 50%，compact 路径最多 2 次；
- [ ] Skill bootstrap 与导航 metadata 可见 payload 相对 Full 下降至少 50%，精确重复 payload 保持为 0；
- [ ] Hard Token Budget、stop reason 和证据完整性继续成立；
- [ ] Gate 对当前明确简单任务不产生错误激活；
- [ ] 全部旧测试继续通过，源码版与安装版一致；
- [ ] 所有版本、参数、trace、消融和失败均可复现。

`≤1.25x` 是进入 6-task M2e-1 pilot 的工程门槛，不是产品成功声明。如果无法达到，应暂停显式 Skill workflow，重新评估 Smart Read 是否只能作为 SDK/宿主层或其他可拦截读取路径中的透明优化器。

## 8. 明确不做

- 不修改 Ranker 权重、Graph Edge、Discovery Source 或停止阈值；
- 不加入 embedding、Tree-sitter 多语言、长期记忆或 M3；
- 不为两个校准任务添加特例；
- 不把 payload 估算与模型 usage 重复相加；
- 不把 Activation Gate 当作掩盖昂贵激活路径的手段；
- 不在官方或实测接口能力未确认前声称可透明拦截 Codex 原生工具；
- 不直接扩大到 12–20 个昂贵会话。

## 9. 实施顺序与当前进度

- [x] 根据 M2e-0 结果将问题定性为 orchestration cost，而非 retrieval quality；
- [x] 固定三层成本模型、操作标签、重复证据分类和计量边界；
- [x] 固定 compact one-shot/two-stage、Activation Gate 和消融方案；
- [x] 固定 `≤1.25x`、协议调用与启动/导航载荷下降 50% 的阶段门槛；
- [x] M2e-0.1a 已实现离线 trace/cost attribution，并生成四个配对的归因报告，见 `M2E_0_1_ATTRIBUTION_RESULTS.md`；
- [x] M2e-0.1b 两阶段状态机、Feedback 边界、双预算、Evidence Package、幂等规则和五层验证门已冻结，见 `M2E_0_1B_COMPACT_STRATEGY.md`；
- [x] Compact Navigator 固定 Fixture Gate 1 已实现并通过；最多两次成功调用、批量 hash Feedback、预留一次补证、双预算、五项安全上限、幂等和隐私契约均有离线测试，见 `M2E_0_1B_GATE1_RESULTS.md`；
- [x] Gate 2 已运行并得到否定结果：协议与预算合规，但冻结成功集合只保留 2/9；不进入后续 Gate 或端到端消融，先做架构复审，见 `M2E_0_1B_GATE2_RESULTS.md`；
- [ ] M2e-0.1c 实现廉价 Activation Gate；
- [ ] 对胜出变体运行相同两任务完整配对；
- [ ] 达标后进入 6-task M2e-1 pilot，否则启动透明接口可行性评审。
