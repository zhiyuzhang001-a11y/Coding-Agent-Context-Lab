# M2e-0.1a 编排成本归因结果

最后更新：2026-08-15

## 结论

M2e-0.1a 已完成：现有四个有效 Native/M2d 配对可以在不重新运行 Codex 的情况下生成逐命令隐私 trace、三层成本归因、有效 evidence 关联和聚合比较。

归因强化了“编排成本”判断，但修正了原先对重复证据的解释：

> M2d 的直接工具 payload 确实更大，但它只解释全会话 Token regret 的很小一部分；更主要的嫌疑是 33 个额外工具结果引发的模型往返，以及累积上下文在后续推理中反复处理。

当前事件流只有最终累计 usage，无法直接观测每一次模型继续推理的 Token。因此这是描述性归因，不是因果证明；下一步仍需 compact roundtrip 消融。

## 诊断计数修正

M2e-0 原报告中的命令 `102 vs 36` 和重复结果 `48 vs 15` 存在诊断解析错误：解析器同时统计了 `item.started` 与 `item.completed`，并把 started 事件的空输出当成重复 payload。

修正后：

| 指标 | Native | M2d |
|---|---:|---:|
| 实际完成命令结果 | 18 | 51 |
| 精确重复的已完成 payload | 0 | 0 |
| 精确重复的源码读取命令 | 0 | 0 |

全会话 usage 取自最终累计 `input + output`，不依赖工具事件计数，因此 `3.131x` 的主要负面结论不受影响。

这意味着原先的 `duplicate model-visible payload -50%` 不能继续作为有效优化门槛：基线已经是 0。后续应改为减少导航/启动 payload 和外部协议往返，并保持精确重复为 0。

## 全会话与直接载荷

四次运行聚合：

| 指标 | Native | M2d | 差值 |
|---|---:|---:|---:|
| 模型全会话 Token | 378,514 | 1,258,760 | +880,246 |
| 中位 Token | 94,719.5 | 296,484.5 | — |
| 完成命令结果 | 18 | 51 | +33 |
| 一次性工具 payload 粗估 | 14,323 | 36,484 | +22,161 |

一次性 payload 差值只相当于模型 Token regret 的约 `2.52%`。这个比例不能解释为“其余 97.48% 都是推理”，因为工具结果会在后续模型调用中再次进入累积上下文；它只说明压缩一次性输出本身不足以解决 `3.131x`。

以额外 33 个完成命令结果做描述性折算，每个额外结果对应约 26,674 个模型 Token regret。该数字不是单次调用的真实成本，但说明 roundtrip ablation 是当前最有价值的实验。

## M2d 操作归因

四个 M2d 会话中的明确操作次数：

| 操作 | 次数 |
|---|---:|
| Skill bootstrap | 4 |
| index | 4 |
| start | 4 |
| next | 10 |
| expand | 8 |
| feedback | 6 |
| stop | 4 |
| context/source evidence 路由 | 10 |

没有显式 `discover`。Skill bootstrap 和 Navigator 操作共形成 36 个实际外部命令结果；其中不含 Skill bootstrap 的 Navigator 命令结果为 32。若 compact 路径在四个会话中最多各使用两次，理论上可把这类外部结果压到最多 8 次，下降至少 `77.8%`。

M2d 一次性 payload 粗估分布：

| payload 类别 | Token | M2d payload 占比 |
|---|---:|---:|
| source evidence | 15,112 | 41.4% |
| navigation metadata | 10,493 | 28.8% |
| Skill bootstrap | 4,288 | 11.8% |
| compound command | 3,515 | 9.6% |
| other | 2,938 | 8.1% |
| editing/tests | 138 | 0.4% |

`compound command` 同时包含两种操作，不能诚实地拆分到单项。仅 Skill bootstrap 与纯 navigation metadata 已占 M2d 直接 payload 的约 `40.5%`；若把 compound 全算作协议上界，则为约 `50.1%`。

## 有效 evidence 与隐私

归因器只用两种可核验信号标记潜在有效 evidence：

- 展开的 Marker 最终被 `stop --evidence` 引用；
- 输出命中校准 manifest 中的目标路径或 symbol。

该启发式在 M2d 中标记约 15,227 Token，在 Native 中标记约 6,278 Token。它只表示与最终目标可关联，不能替代人工正确性或证明每个字都必要。

私有 trace 只保存：

- 命令与输出 SHA-256；
- 字符数和估算 Token；
- 操作标签、payload 类别；
- 重复、最终 evidence 和 oracle 命中布尔值。

不保存命令正文或工具输出正文。原始 attribution JSON 位于被 Git 忽略的 `.agent-token-manager/m2e-calibration/m2e-0.1a-attribution.json`。

## 交付与复现

```bash
python3 scripts/run_m2e_cost_attribution.py --pretty \
  --output ../../.agent-token-manager/m2e-calibration/m2e-0.1a-attribution.json
```

已交付：

- `scripts/run_m2e_cost_attribution.py`：选择每个 case/repetition/arm 最新成功记录并生成归因；
- `resources/m2e_cost_attribution_schema.json`：版本化 trace schema；
- `tests/test_m2e_cost_attribution.py`：compound 操作、started/completed、evidence payload 和记录选择回归；
- `scripts/m2e_events.py`：修复 started 事件重复计数；
- 本结果文件：公开聚合，不保存源码正文。

## M2e-0.1a 验收

- [x] Skill bootstrap、index/start/next/expand/feedback/stop、源码证据与其他命令可分类；
- [x] 调用次数、估算 payload、全会话占比边界和 evidence 贡献可报告；
- [x] `duplicate_source_read` 与 `duplicate_model_visible_payload` 分开统计；
- [x] 每个会话生成逐事件隐私 trace；
- [x] 不可逐操作分配的模型 usage 明确标为 residual/unavailable；
- [x] 因果结论明确要求后续消融；
- [x] 原诊断重复计数问题已修复并增加回归测试；
- [x] 不修改 Ranker、Graph、Discovery、Feedback 或 M3。

## 下一步

进入 M2e-0.1b Compact Navigator，优先消除模型参与的 `next/expand/feedback` 往返：

1. 本地内部执行 TaskState、Feedback、排序、扩展、预算与停止；
2. 对 Codex 只返回一个 compact context package；
3. 只有修改前证据不完整时允许第二次 `verify`；
4. 先在离线 fixture 和 Navigator regression 上验证，再运行两个校准任务的完整 Codex 消融。

Activation Gate 仍放在 compact core 之后，避免用“不激活”掩盖激活路径自身的成本。
