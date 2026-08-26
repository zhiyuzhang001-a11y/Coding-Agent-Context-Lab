# CO-1 Gate 2 结果：补偿读取后仍省，但端到端门失败

最后更新：2026-08-15

状态：**Gate 2 未通过。停止进入 Gate 3，不调整任务或通过门槛。**

冻结 commit：`e0495d61737f01a4528d27c5ce39b4163e93bb22`

插件版本：`0.1.0+codex.20260815142913`

模型：`gpt-5.6-sol`，reasoning effort `medium`

## 1. 总结

Gate 2 的透明接口、正确性、语法切片和 fail-open 均成立；补偿读取后的工具层经济性也达到门槛。但四个 activated 任务没有任何一个实现完整会话 Token 低于 Native，因此按冻结验收标准判定失败。

```text
correctness                         6/6 Native/CO 一致
activated model visibility         4/4 通过
activated visible read Token       1,429 → 775
aggregate visible read saving      654（45.77%）
median per-task saving             42.715%
same-intent retries                0
activated tasks net-positive       4/4
expected compensation reads        1
fail-open Native-equivalent        2/2
activated full-session lower       0/4
activated full-session aggregate   161,077 → 178,805（+11.01%）
```

## 2. 各任务结果

### function_answer

- correctness 一致；
- model-visible read：`492 → 186`，节省 `62.20%`；
- 0 retry，0 compensation；
- full session：`31,982 → 32,211`，CO 高 `0.72%`。

### method_answer

- correctness 一致；
- model-visible read：`329 → 191`，节省 `41.95%`；
- 0 retry，0 compensation；
- full session：`32,026 → 32,245`，CO 高 `0.68%`。

### global_context

- correctness 一致；
- 首次 syntax slice 为 188 Token，随后通过一次 `rg` 补充 module constant，新增 28 Token；
- 补偿后 read：`286 → 216`，仍节省 `24.48%`；
- full session：`32,006 → 48,850`，CO 高 `52.63%`。

这是本轮最重要的失败：补偿读取正文很小，但它增加一个模型语义回合，使完整 input 从 `31,851` 增至 `48,548`。因此正文 Token 不能代表 roundtrip 成本。

### local_edit

- correctness、diff 与固定测试一致；
- model-visible read：`322 → 182`，节省 `43.48%`；
- 0 retry，0 compensation；
- full session：`65,063 → 65,499`，CO 高 `0.67%`。

### ambiguous_range

- `syntax_range_ambiguous`；
- Native/CO model-visible output hash 一致；
- correctness 一致，未产生替代包。

### over_budget

- `syntax_slice_over_budget`；
- Native/CO model-visible output hash 一致；
- correctness 一致，完整语法单元未被截断。

## 3. Gate 检查

通过：

- correctness equal；
- activated canary/package model visibility；
- median net saving ≥40%；
- median retry = 0，单任务 retry ≤1；
- 至少 3/4 activated net-positive，实际为 4/4；
- fail-open Native-equivalent；
- fail-open reasons match。

失败：

- `one_complete_session_lower`：实际为 `0/4`。

因此总状态必须为 `failed`，不得用工具层 45.77% 节省改写为 Gate 通过。

## 4. 架构解释

数据同时暴露两个独立成本：

1. **固定插件/Hook 启动成本**：三个不补读任务的 CO 完整会话仍稳定高约 0.67%–0.72%；
2. **补偿回合放大**：全局常量任务只补回 28 个模型可见 Token，却增加约 16.8k 完整会话 Token。

因此 CO-1 的局部语法切片是有效的，但当前产品包和缺失上下文策略没有证明端到端收益。尤其不能把“补读正文很少”误解为“补读成本很小”。

## 5. 后续约束

- 不进入真实仓库 Gate 3；
- 不开始 CO-2 或 CO-3 掩盖失败；
- Old M2d、Compact 和 CO-1 实现继续保留为研究基线；
- 下一步先做架构复审，而不是立即改切片算法。

架构复审至少比较：

1. Context Optimizer 是否应从包含 Navigator Skill 的大插件中拆成 Hook-only 最小产品，以移除固定 prompt/bootstrap 成本；
2. 能否在本地静态检测 body 中未包含的 module globals/helper，并对高补读风险场景直接 fail-open；
3. 更底层的 read-result rewrite 是否能避免 `decision:block` 的 tool-error 语义；
4. 只有原始读取足够大、预期净收益覆盖固定成本时才激活的透明 Gate 是否值得单独实验。

任何后续实验必须继续报告完整会话 Token，不能只优化首次 slice 或工具载荷。

## 6. 可复现记录

去源码化结构结果保存于 `resources/co1_gate2_results.json`。原始 Codex JSONL、transcript、Hook 日志、diff 和测试输出位于私有目录：

```text
.agent-token-manager/co1-gate2-full
```

Token 口径：模型可见工具输出使用 `chars_div_4_v1` 粗估；完整会话使用 Codex `input_tokens + output_tokens`。两者不可混称。
