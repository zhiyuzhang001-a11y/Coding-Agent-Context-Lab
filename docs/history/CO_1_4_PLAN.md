# CO-1.4 计划：Host Path Reconnaissance

最后更新：2026-08-16

状态：**已完成；1.4a Observe 通过，1.4b 可替换但 success semantics 失败，透明 Smart Read 按停止门暂停。见 `CO_1_4_RESULTS.md`。**

## 唯一问题

> 自然 Codex 中，真正进入模型可见上下文的代码结果，在哪个最靠近模型的层面可以被稳定观察和替换？

CO-1.4 不优化内容、不追求 Token 节省。它只寻找统一宿主节点；找不到就停止透明 Smart Read，转为 Agent cost profiler / observability。

## 两道门

### CO-1.4a Observe

优先复用 CO-1.3 的 24 场 artifacts，不新增模型调用。重建：

```text
Agent custom tool decision
→ nested exec_command / Bash request
→ CLI command_execution raw result
→ PostToolUse Hook observation
→ transcript custom_tool_call_output
→ next model cycle
```

每条路径只保存：run/call 序号、command family、request/result hash、raw/model-visible chars、是否截断、Hook 是否观察、raw 是否进入 model-visible result、下一 cycle 序号。不保存命令正文或源码。

冻结分母：

- call coverage：自然 code-bearing result 调用数；
- weighted coverage：按 model-visible Token 加权；
- correlation：request → raw → Hook → transcript 的成功关联率。

Observe 通过门：call coverage `>=90%`、weighted coverage `>=90%`、correlation `>=95%`，且不依赖具体 `rg/sed/awk` 模式才能观察结果。

### CO-1.4b Replaceability Micro-probe

仅在 Observe 通过后运行。使用 command-independent canary wrapper，不切片、不压缩、不解析 shell：

```text
[CO14_HOST_CANARY]
<完整原始结果>
```

固定少量 `rg`、复合 `rg && sed`、`sed`/code-mode 任务，验证 canary 进入 transcript、原始结果仍完整、correctness 不下降、model cycle 不增加。失败或不支持时 fail-open。

Replaceability 通过门：至少 80% 被测 code-bearing result 可替换；关联率 >=95%；correctness 零回归；无补偿工具调用；model cycle 不增加。

## 停止门

- 统一观察或替换覆盖不足，不继续扩 shell pattern；
- 不把 CLI 原始输出误当模型输入；
- 不因单一 Bash 路径成功声称覆盖 read_file/MCP/LSP；未观测路径单独列为未知；
- 找不到覆盖自然主要流量的统一节点，透明 Smart Read 到此停止。

## 后续语义要求（本阶段不实现）

```text
Known-target read → complete symbol slice
Exploratory read → bounded region / structural context
```

`non_unique_target` 是自然探索行为，不得强制压成单 symbol。

## 明确不做

- 不扩 AST 或 shell parser；
- 不进入 CO-2；
- 不缓存、去重、压缩搜索结果；
- 不用更多功能换覆盖率；
- 不声称官方接口存在通用 model-visible adapter；该能力必须由观察与 canary 实验证明。
