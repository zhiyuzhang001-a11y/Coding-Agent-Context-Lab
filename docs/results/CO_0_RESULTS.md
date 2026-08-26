# CO-0 阶段结果：Hook/interface feasibility

最后更新：2026-08-15

状态：**CO-0 v0 验收完成并冻结。真实接口门 7/7、retry-aware 经济门全部通过；插件继续默认 observe，结果仅证明当前小矩阵中的接口与净收益可行性。**

## 1. 已实现

- 新增独立 `PostToolUse` Context Optimizer handler，保留原审计 Hook；
- 默认 `observe`，只有显式设置 `AGENT_TOKEN_MANAGER_CO0_MODE=enforce` 才替代结果；
- 严格识别简单 `cat`、明确范围 `sed -n`、简单 `rg pattern path` 与已知 symbol 的 Smart Read 命令；
- pipeline、重定向、命令替换、glob、测试、构建和未知命令 passthrough；
- 状态覆盖 `optimized`、unsupported/not-beneficial/observe passthrough、optimizer error 与 budget/timeout fallback；
- 日志只保存状态、原因、长度、估算 Token、hash 和 canary 布尔值，不保存源码正文；
- 增加可复现的隔离 Codex Gate runner、fixture、故障注入和隐私测试。

## 2. 真实 `cat` Gate

固定条件：

- 插件版本：`0.1.0+codex.20260815130237`；
- Codex CLI：`0.148.0-alpha.9`；
- 工作区只读；
- 命令：`cat -- plugins/agent-token-manager/resources/co0_canary_fixture.txt`；
- 原始 payload：1,304 字符；
- 替代 payload：232 字符，粗估 58 Token；
- 原始 canary：`CO0_RAW_PAYLOAD_CANARY_5F8A27D1`。

`decision:block` Gate 结果：

- Hook 原始输入包含 canary；
- Hook 替代结果不含 canary；
- transcript 的 `function_call_output` 包含 `Smart Read CO-0 optimized result`；
- 同一模型工具输出不含 canary；
- 模型最终严格回答 `NOT_VISIBLE`；
- 替代 payload 相对原始字符数下降约 82.2%；
- Codex 正常退出，未执行第二条命令。

因此已经证明：

> 对当前 Codex 的简单 Bash `cat` 路径，PostToolUse Hook 可以在原始大 payload 进入模型工具消息前，以更小结果替代它。

这只证明接口可行性，不证明完整任务 Token 节省、信息质量或对全部读取路径有效。

## 3. 测量口径修正

真实实验发现 `codex exec --json` 的 `command_execution.aggregated_output` 仍会记录原始 shell 输出，包括 canary；但 transcript 的模型工具消息收到的是 Hook 替代结果，模型也无法复述 canary。

因此：

- CLI UI/event stream 是工具执行观测，不等同于模型输入；
- CO-0 Gate 必须检查 transcript 中 `response_item/function_call_output`；
- `transcript_path` 只在显式 Gate 环境记录，不能成为长期产品依赖；
- `--ephemeral` 运行的 Hook 没有可用 transcript path，只能作为较低等级的行为证据。

## 4. 协议消融

### `decision:block`

- 成功阻止原始 canary 进入模型工具输出；
- 替代包进入模型，模型回答 `NOT_VISIBLE`；
- Codex 内部将替代反馈记录为 tool/router error。

### `continue:false + stopReason`

- Hook 自身生成的替代包不含 canary；
- 真实 transcript 的模型工具输出仍为原始 payload；
- 模型准确复述 canary；
- 当前 Codex 路径下判定为替代失败，已从实现撤回。

这说明当前唯一实测有效的替代方式具有“错误形态”副作用。后续必须验证它是否导致普通任务重试、额外轮次或错误判断；在此之前保持默认 `observe`。

## 5. 测试状态

- CO-0 Hook/Gate 专项：11/11；
- 插件全套：105/105；
- `ResourceWarning` 作为错误：通过；
- 插件 manifest 验证：源码与安装态均通过；
- 最终安装版本：`0.1.0+codex.20260815134154`；
- 最终安装缓存与源码逐文件一致，安装态 105/105 与 `ResourceWarning` 检查通过。

## 6. 剩余 Gate

- [x] 简单 `cat` 模型可见 canary Gate；
- [x] 明确范围 `sed -n` 的真实 Gate；
- [x] 简单 `rg pattern path` 的真实 Gate；
- [x] 已知 symbol 读取的真实 Gate；
- [x] 非白名单复杂 pipeline 的 Native 等价性；
- [x] 单元 error/timeout 与真实 optimizer error fail-open；
- [x] code mode 嵌套调用；
- [x] `decision:block` 重试、补偿调用和完整会话成本归因；
- [x] 固定接口门与经济门全部通过。

最终经济门主指标为 `Net visible-context saving after retries`：Native 模型可见 read/search 上下文减去 CO 首次替代、错误反馈、全部重试与补偿性读取/搜索结果。完整公式和去重规则见 `CO_0_IMPLEMENTATION_PLAN.md`；当前冻结矩阵的该指标与完整会话 Token 门均已通过。

## 7. 当前决策

- 保留 `decision:block` 作为实验性 enforce 路径；当前四组 CO 任务相同意图重试与补偿调用均为 0；
- 默认始终为 `observe`，在更广泛真实任务验证前不自动改变用户 Native 行为；
- CO-0 已证明 Context Optimizer 路线在当前宿主上可行，下一阶段可以进入 CO-1 Syntax-aware Read Slicing；
- 不把冻结矩阵的 75.95% 工具可见上下文下降或约 0.69% 完整会话中位改善表述为一般开发会话节省；
- `decision:block` 的错误语义继续作为 CO-1/真实 benchmark 回归指标，若重试成本重新出现则重新评估 Agent host 或 MCP/read 接口。

## 8. 冻结矩阵最终结果

接口门：`cat`、`sed`、`rg`、`known-symbol`、`code mode`、`passthrough`、`fail-open` 共 7/7 通过。

经济门四个配对均正确，且 CO 无重试、无补偿调用：

```text
scenario       Native visible   CO visible   net saving   CO/Native total
cat                       361           92          269             0.9930
sed                       361           93          268             0.9932
rg                        286           97          189             0.9934
known-symbol              593          103          490             0.9871
```

- Native 可见工具上下文合计：1,601 Token；
- CO 计入重试后的可见工具上下文：385 Token；
- `Net visible-context saving after retries`：1,216 Token，约 75.95%；
- 净节省中位数：268.5 Token；
- 相同意图重试中位数：0；
- 完整会话 CO/Native 配对比率中位数：`0.9931x`；
- 完整会话合计由 132,874 降至 131,764 Token，减少 1,110 Token。

机器可读结果见 `resources/co0_matrix_results.json`。当前只有每场景一个配对、任务为合成短回答，结果只能作为 CO-0 架构门，不能支持普遍效率结论。

CO-0 实现与验收已冻结在 commit `4b03f7d`；后续文档记录不得改写该实验基线。
