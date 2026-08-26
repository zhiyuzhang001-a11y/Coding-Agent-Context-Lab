# CO-0 实施计划：透明 Context Optimizer 接口可行性

最后更新：2026-08-15

状态：**v0 验收完成并冻结。冻结接口门 7/7、经济门全部通过；结论只适用于当前合成小矩阵，不外推为一般开发会话节省。结果见 `CO_0_RESULTS.md` 与 `resources/co0_matrix_results.json`。**

## 1. 架构决策

M2d 与 Compact Navigator 转为冻结研究分支：

- Old M2d 保留为“多轮语义纠偏有效”的正向研究基线；
- Compact Navigator 保留为“最多两次模型可见交互无法保持原导航 Recall”的负向实验；
- 不删除实现、不切换默认 Skill、不继续 Gate 3/4、Activation Gate 或昂贵端到端消融。

产品主线转为 **Context Optimization Layer**，第一阶段命名为 **CO-0**，不占用原 M3 编号。M3 继续用于长期记忆。

最高设计原则：

> Smart Read 不替代 Codex 的语义判断，不要求 Codex 驾驶导航器；只负责在源码和搜索结果进入模型前完成切片、压缩、去重和预算控制。任何优化失败都应可观测地回退到 Native 行为。

## 2. CO-0 唯一问题

CO-0 只回答：

> 能否可靠拦截一部分高成本 read/search，并确保原始大 payload 不再进入模型可见输入，而由更小的结果替代？

CO-0 不以“Hook 成功执行”作为通过证据。每个门控测试必须构造包含唯一 canary 的可识别大段原始 payload，并核验模型最终可见的内容。

## 3. 官方接口边界

按 2026-08-15 的 Codex Hooks 官方文档：

- `PreToolUse` 可观察、阻止或改写 Bash、MCP 和其他受支持本地函数工具的输入；
- `PostToolUse` 可在工具运行后以 Hook 反馈替代原始模型可见结果，但不能撤销工具副作用；
- `updatedMCPToolOutput` 与 `suppressOutput` 当前尚不受支持，不能假定可以任意重写工具返回结构；
- Hosted tools 和部分选择退出默认 Hook 路径的特殊工具不在完整覆盖范围内。

因此“透明”只对 CO-0 明确验证过的本地工具路径成立，不扩张为对所有 Codex 工具的承诺。

官方依据：<https://learn.chatgpt.com/docs/hooks>

## 4. 严格白名单

第一版只识别可无歧义解析的简单形式：

```text
cat -- path
cat path
sed -n 'START,ENDp' path
rg 'pattern' path
已知 path + symbol 的 Smart Read 读取
```

命令名称相同不等于命中白名单。以下一律 passthrough：

```text
复杂 pipeline
重定向和命令替换
复杂 glob
find -exec
任意 shell / Python 脚本执行
测试、构建和部署命令
无法安全解析的 quoting 或选项组合
```

`sed -n` 已经是范围读取；CO-0 对它主要验证拦截、模型可见计量和未来去重接口，不强行再次切片。

## 5. Fail-open 与可观测性

Context Optimizer 的解析、匹配、切片、压缩、预算或 Hook 执行失败时，必须允许原始 Native 行为继续。此 fail-open 只适用于上下文优化，不替代安全策略或权限控制。

每次调用必须落入以下一种状态：

```text
optimized
passthrough_unsupported
passthrough_not_beneficial
passthrough_observe
fallback_optimizer_error
fallback_budget_or_timeout
```

并记录结构化 `fallback_reason`。产品运行时允许 fallback；CO-0 门控中发生 passthrough 或 fallback 的白名单用例不能计为拦截成功，也不能被混入优化收益。

日志继续遵循隐私原则：保存事件状态、长度、估算 Token、hash、canary 检查结果和原因，不保存不必要的源码正文。

## 6. 模型可见证据等级

每个 CO-0 测试至少保存以下证据：

1. Hook 记录原始 payload 的 hash、长度、估算 Token 和唯一 canary；
2. 模型可见事件或可靠会话记录包含优化后的替代结果；
3. 模型可见输入中不存在原始 canary 和被移除的大段正文；
4. 受控下一轮只能依据替代结果作答，不能引用被删除的隐藏内容。

前两项只能证明 Hook 做过处理；第三、四项才用于证明原始 payload 未进入模型可见上下文。`transcript_path` 不是稳定接口，若使用它只能作为实验观测，不可直接成为长期产品依赖。

## 7. 固定测试矩阵

CO-0 使用固定仓库、commit、模型、插件版本、命令和 payload：

1. 直接 `cat` 大文件读取；
2. 明确范围的 `sed -n`；
3. 简单 `rg pattern path` 大结果；
4. 已知 symbol 的读取；
5. 非白名单复杂命令 passthrough；
6. 注入解析错误、Optimizer 异常和超时，验证 fail-open；
7. 同一调用分别覆盖直接工具调用与 code mode 嵌套调用。

每个用例记录：命中状态、原始/替代模型可见大小、估算 Token、canary 是否可见、延迟、错误、fallback reason、任务正确性和工具副作用。

## 8. 验收标准

- [x] 白名单内四类 read/search 路径均可由严格解析器稳定识别；真实 Codex 路径仍需逐项 Gate。
- [x] 优化成功时，冻结 `cat/sed/rg/known-symbol/code mode` 的原始 canary 不进入模型工具消息。
- [x] 模型看到明确、可用且更小的替代结果，冻结任务 correctness 与 Native 一致。
- [x] 非白名单复杂 pipeline 在 Native/CO 中模型可见结果 hash 一致，不被误改写或阻断。
- [x] 单元故障注入覆盖 error/timeout；真实 Codex optimizer error 可观测地 fail-open 并返回 Native canary。
- [x] 所有 passthrough/fallback 都有枚举状态和结构化原因。
- [x] 冻结矩阵不改变工具副作用或任务正确性；更广泛任务质量留给后续真实 benchmark。
- [x] Optimizer 记录原始/替代长度、hash、估算可见 Token、状态和原因；冻结矩阵已完成配对完整会话计量。
- [x] 直接场景与 code mode 嵌套调用均有 transcript 实测记录，嵌套路径未绕过 Hook。
- [x] 实验保存插件版本、CLI 版本、任务、参数、hash 和汇总结果；实现冻结 commit 为 `4b03f7d`。

### 8.1 冻结行为矩阵

CO-0 剩余工作只运行以下真实路径，不再加入优化功能：

```text
cat            已通过；保留为回归
sed -n         验证明确范围读取替代
rg             验证大搜索结果替代
known-symbol   验证精准符号读取路径
passthrough    验证测试、构建和复杂 shell 不受影响
code mode      验证嵌套实际调用路径不绕过 Hook
```

每个用例同时保存 Native 与 CO 结果，记录原始/替代 payload、canary、命令数、相同意图重试、补偿性读取/搜索、模型工具输出、correctness、stop reason 和完整会话 usage。

### 8.2 Net visible-context saving after retries

主经济指标固定为：

```text
Net visible-context saving
= Native 模型可见 read/search 上下文
- (
    CO 首次替代结果
    + decision:block 错误反馈
    + 重试命令与结果
    + 补偿性读取/搜索结果
  )
```

若 CO 的模型可见上下文统计已经包含重试与补偿结果，不得再次扣除。所有计量以 transcript 的 `response_item/function_call_output` 为准；CLI `command_execution.aggregated_output` 只用于工具执行诊断，不冒充模型输入。

接口门：

- 支持路径的原始 canary 不进入模型工具消息，替代包可见；
- passthrough 与 Native 结果一致；
- code mode 不绕过 Hook；
- Optimizer 故障可观测地 fail-open；
- correctness 不低于 Native。

经济门：

- 聚合及中位 `Net visible-context saving > 0`；
- 不出现重复读取循环；相同意图重试次数中位数不超过 1；
- 至少 `rg` 和一个代码读取任务完整会话 Token 低于 Native；
- CO/Native 完整模型 Token 配对比率中位数不高于 `1.0x`。

接口门通过但经济门失败时，结论是当前 `decision:block` 不适合作为产品宿主；停止 Hook enforce 扩展，评估更底层 Agent host 或显式低摩擦 MCP/read 接口。不得进入 CO-1 掩盖协议负优化。

## 9. CO-0 明确不做

- 不修改 Ranker、Graph、Discovery、Navigator 或 Compact 参数；
- 不开发 embedding、语义检索、长期记忆或复杂 Shell parser；
- 不默认接管测试、构建、部署、脚本和 hosted tools；
- 不把本地缓存命中直接等价为模型 Token 节省；
- 不在接口可行性通过前实现完整 Read Slicing、Evidence Dedup 或 Search Compression；
- 不因白名单用例 fallback 而阻断 Codex，也不把 fallback 计为优化成功。

## 10. 通过后的路线

只有 CO-0 通过后才按顺序进入：

```text
CO-1  Syntax-aware Read Slicing
CO-2  Model-visible Evidence Dedup
CO-3  Search Compression
CO-4  Unified Visible-context Budget
CO-E2E  Native vs CO 完整会话 A/B
```

如果 CO-0 不能证明原始大 payload 被可靠替代，则停止 Hook 透明层扩展，转而评估显式但低轮次的 MCP `smart_read/smart_search`，或更底层的 Agent host/tool registry；不得用算法优化掩盖接口不可行。
