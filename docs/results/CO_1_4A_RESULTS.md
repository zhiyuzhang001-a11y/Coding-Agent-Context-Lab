# CO-1.4a 结果：Host Path Observe

最后更新：2026-08-16

结论：**通过；PostToolUse/Bash 在已观测的自然 code-mode shell 路径上形成统一可观察节点，可以进入 CO-1.4b replaceability 微实验。**

## 数据来源

- 复用 CO-1.3 的 12 个 CO 会话，不新增模型调用；
- 16 个自然 code-bearing tool result；
- command family：11 个 `compound_shell`、1 个 `rg`、4 个 `sed`；
- 模型可见代码结果估算合计 17,651 Token。

## 覆盖结果

- Hook observation call coverage：16/16，`100%`；
- model-visible Token weighted coverage：17,651/17,651，`100%`；
- request → CLI raw → Hook hash → transcript output 关联率：`100%`；
- 所有结果均由同一 `PostToolUse`/`Bash` Hook 观察，观察本身不依赖解析 `rg/sed` 语义。

CO-1.3 的 0 activation 与本结果并不矛盾：Hook 看到了全部结果，但旧 Gate 只允许严格单 `sed`，因此没有 replacement。真正的统一候选节点是“Bash PostToolUse 原始结果”，不是 shell command parser。

## 边界

- 只证明当前 Codex code-mode → nested `exec_command` → Bash 路径；
- 未证明 direct read_file、MCP、LSP 或 hosted tool 也经过同一节点；
- 只证明观察，不证明 generic result replacement；
- 官方 OpenAI 文档检索未确认公开的通用 model-visible adapter，因此 replaceability 仍必须由 canary 实验验证。

结构化结果见 `resources/co1_4_observe_results.json`。下一步 CO-1.4b 只在完整 raw result 前加入 canary，不切片、不压缩、不解析命令。
