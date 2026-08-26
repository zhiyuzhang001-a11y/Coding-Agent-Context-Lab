# CO-1.4 最终结果：Host Path Reconnaissance

最后更新：2026-08-16

结论：**部分成立，但透明宿主 Gate 失败。当前 PostToolUse/Bash 节点可 100% 观察、也能 100% 阻断式替换，却不能保持正常工具成功语义；按停止门暂停透明 Smart Read。**

## CO-1.4a Observe：通过

复用 CO-1.3 的 12 个自然 CO 会话：

- code-bearing result：16；
- family：11 compound shell、1 rg、4 sed；
- model-visible code result：约 17,651 Token；
- Hook call coverage：16/16，100%；
- Token-weighted coverage：17,651/17,651，100%；
- request → CLI raw → Hook hash → transcript 关联：100%。

因此 PostToolUse/Bash 确实站在当前 code-mode shell 结果流上。CO-1.3 的 0 replacement 来自旧 Gate，而不是 Hook 没看到流量。

## CO-1.4b Replaceability：技术替换通过，透明性失败

冻结身份：

- 任务源码 commit：`d693547c355820da7a78ad4dd31dd92a1c203978`；
- Hook-only plugin commit：`920a0330de2fb17c3314420efe70ae9530b38969`；
- plugin version：`0.1.0+codex.20260816143338`；
- 结果记录版主插件：`0.1.0+codex.20260816143944`；
- manifest SHA-256：`7463921d7318ca0e26171d1b0eb08146bb2e6454e8b41f33f3b0a838c3132ed7`；
- 4 个命令形态 × observe/canary，共 8 场。

结果：

- canary model-visible：4/4；
- 完整 raw result 保留：4/4；
- replaceability coverage：100%；
- observe/canary 均每场 1 次 tool call、2 个 model cycles；
- cycle delta 中位数：0；
- correctness：observe 3/4、canary 4/4，不存在 treatment 回归；
- 补偿工具调用：0。

但 4/4 canary transcript 均呈现：

```text
Script failed
...
Script error:
[CO14_HOST_CANARY]
<完整原结果>
```

当前通用替换依赖 `decision:block`，因此结果被宿主标为工具失败。它没有在这 4 个短任务中增加回合，但不满足透明优化层必须保持正常成功语义的要求。

## 结论边界

- 已证明：当前 code-mode nested exec/Bash 路径存在统一观察点；
- 已证明：该点可用阻断语义改变模型最终所见结果；
- 未证明：存在 success-preserving 的通用本地工具结果 rewrite API；
- OpenAI 官方文档检索也未确认通用 model-visible adapter；已知支持形态不能替代本次实测；
- 未覆盖 direct read_file、MCP、LSP、hosted tools。

## 决策

按预先冻结的停止门：

- 不进入 CO-2；
- 不扩 shell parser、AST 或更多命令模式；
- 不将 `decision:block` 包装成生产透明优化；
- 透明 Smart Read 暂停，直到宿主提供或发现 success-preserving result replacement；
- 当前可继续产品化的方向是 **Agent Cost Profiler / Observability**：利用已证明的 100% Bash 观察覆盖，报告 model-visible result 成本、重复、命令族、cycle amplification 和高成本读取，不改变 Agent 行为。

若未来出现正式的 success-preserving output rewrite 接口，可直接复用现有 slicer、risk Gate、覆盖分析和 benchmark，不需要重做 CO-1。

结构化结果见 `resources/co1_4_results.json`；私有原始 artifacts 位于 `.agent-token-manager/co1-3/` 与 `.agent-token-manager/co1-4b/`。
