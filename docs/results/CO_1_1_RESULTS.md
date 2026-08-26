# CO-1.1 Pilot 结果：最小 Hook 成本很小，rewrite 成本未稳定显现

最后更新：2026-08-15

状态：**Pilot 计量链路通过；不进入 27 场正式矩阵。**

冻结 commit：`544ea69d87bd04589ca4c1f966bac6265559ae7b`

## 结果

6/6 correctness 一致，6/6 只有一个工具调用，6/6 canary 可见。observe 均不返回 decision，rewrite 均通过 `decision:block` 返回等价正文。所有会话各有两条累计 usage 事件，即“模型→工具→模型”两个计算周期；工具调用前是否出现可见 assistant message 不稳定，因此不再把 assistant message 数冒充模型周期。

```text
median Native                 31,268.5
median Hook-only observe      31,291.5
median equivalent rewrite     31,331.5

observe - native              +36, +10
median fixed Hook delta       +23 Token（约 +0.074%）

rewrite - observe             +105, -25
median rewrite delta          +40 Token
rewrite direction             不一致
```

## 判断

最小 Hook observe 的固定成本两次均为正，但只有 10–36 Token，明显小于 CO-1 Gate 2 中完整 Agent Token Manager 稳定出现的约 0.7%。这支持、但尚未单独证明：较大的固定成本主要来自完整插件加载内容或其上下文，而不是 PostToolUse Hook 执行本身。

equivalent rewrite 没有增加工具调用或模型周期，但两次相对 observe 的方向相反，`+105/-25` 落在当前短任务波动范围内。因此不能声称 `decision:block` 存在稳定的固定 Token 税，也不能声称它完全免费。

按预先冻结的停止规则，方向不一致时不扩展到 27 场正式矩阵。继续堆重复次数只能回答很小的固定差异，当前产品风险更集中在“缺失上下文导致新增模型周期”的数量级放大。

## 下一步

进入 Compensation-risk Gate 之前，建议先把它定义为纯本地静态风险判定：

- body 引用了 slice 未包含的 module global、helper 或 sibling；
- 方法依赖 class fields，但 slice 只有 class header；
- 任务要求执行、计算或修改，而不是仅解释目标局部；
- 预计首次节省不足以覆盖一个额外模型周期。

高风险直接 fail-open，低风险才允许 syntax slice。下一阶段不追求更高压缩率。

结构化结果见 `resources/co1_1_pilot_results.json`；原始 transcript 与 usage 位于私有 `.agent-token-manager/co1-1-pilot`。
