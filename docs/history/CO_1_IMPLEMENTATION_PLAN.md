# CO-1 实施计划：Syntax-aware Read Slicing

最后更新：2026-08-15

状态：**Gate 1 已通过；Gate 2 策略与六任务矩阵已冻结，runner 与固定数据待实现。详见 `CO_1_GATE2_PLAN.md`。**

## 1. 唯一问题

CO-1 只回答：

> 当 Codex 已经给出明确代码目标，或一个 `sed` 范围能够无歧义地映射到单一 Python 语法单元时，能否用完整语法切片替代粗粒度文本结果，在不降低任务正确性的前提下减少模型可见上下文？

CO-1 不负责发现未知目标，也不替代 Codex 的语义判断。

## 2. 支持范围

v0 仅支持 Python：

- 顶层 `function`；
- 顶层 `async function`；
- `method` / `async method`；
- `class`。

支持两条激活路径：

1. 已知文件加**唯一显式 symbol**；
2. 严格白名单 `sed -n 'START,ENDp' file.py`，且该范围唯一映射到一个语法单元。

裸 `cat file.py` 不猜测 symbol，默认不激活 CO-1。CO-0 的通用压缩能力与 CO-1 语法切片分开计量。

## 3. 完整性契约

一个成功切片必须保持目标语法单元不可分割，并返回：

- decorators；
- 完整 signature；
- docstring；
- 完整函数、方法或类主体；
- 方法所属 class 的 decorators 与 class header；
- `from __future__`；
- decorators、signature、类型注解、默认值或 class bases 直接引用的 import；
- 精确 path、symbol、kind、起止行、内容 hash；
- 明确的省略范围、未解析支持名称和 continuation 提示。

局部 import 已包含在完整主体中，不额外复制。v0 不尝试追踪普通全局变量的数据流；无法由直接 import 解析的名称只作为 `support_names` 元数据提示。

## 4. 选择规则

### 显式 symbol

- 支持 `name` 与 `Class.method`；
- bare name 出现多个定义时判为歧义并 fail-open；
- symbol 不存在、文件不是 Python 或语法解析失败时 fail-open；
- 请求具体 method 时返回 class header 加完整 method；
- 请求 class 时只有完整 class 包能落入预算才切片。

### `sed` 范围

- 范围完全处于单个函数/方法内时选择该最具体节点；
- 范围与单个函数/方法相交且不跨越其他同级语法单元时选择该节点；
- 同时跨越多个 sibling、只能定位到过大的 class、或映射不唯一时 fail-open；
- 不用“最像”的节点猜测目标。

## 5. Hard Visible-context Budget

CO-1 使用独立的模型可见字符预算，并继续记录字符除以四的粗估 Token。预算规则是：

- 语法单元不可截断；
- 完整决策包小于原始工具结果且不超过预算时才替换；
- 超预算记录 `required_chars` 后 fail-open，允许 Native 原始结果继续；
- 不允许为了命中预算删除 decorators、signature、docstring 或函数主体。

## 6. Fail-open 与默认状态

插件继续默认 `observe`，不自动打开 enforce。以下情况均保持 Native 行为：

- 命令或 symbol 解析不明确；
- 文件越界、无法读取或不是 `.py`；
- Python AST 解析失败；
- symbol 重名或 `sed` 跨多个候选；
- 完整切片超过预算；
- 替代包不比原结果小；
- Optimizer 内部异常或超时。

Fail-open 必须落入结构化日志，且不能把 fallback 计作优化成功。

## 7. 验收门

### Gate 1：离线完整性与回归

- [x] function、async function、method、async method、class 均能返回完整语法单元；
- [x] decorators、docstring、signature、完整 body 不丢失；
- [x] method 带 enclosing class header；
- [x] 只加入 `__future__` 与签名/装饰器直接需要的 imports；
- [x] 显式 symbol、唯一 `sed`、歧义 `sed`、重名 symbol、语法错误和超预算均有测试；
- [x] bare `cat` 不触发语法猜测；
- [x] 所有旧测试继续通过。源码与安装态均为 113/113，详见 `CO_1_GATE1_RESULTS.md`。

### Gate 2：冻结小型 correctness / saving 矩阵

- 激活场景 correctness 不低于 Native；
- activated model-visible read Token 中位数至少降低 40%；
- 相同意图重试次数中位数不超过 1；
- canary 证明原始大 payload 未进入模型工具消息；
- passthrough 与 fail-open 场景不改变 Native 结果。

Gate 2 的正式隔离、任务、归因公式和通过门槛见 `CO_1_GATE2_PLAN.md`。其首要风险指标是计入相同意图重试与相邻上下文补偿后的 `Net activated-read saving`，而不是首次 slice 的表面大小。

### Gate 3：真实仓库小型经济实验

- 固定 repo commit、任务、插件版本、模型和预算；
- 至少一个真实任务完整会话 Token 低于 Native；
- 完整会话配对比率中位数目标不高于 `0.95x`；
- 若工具层明显节省但完整会话没有下降，记录为“价值未传导”，不进入 CO-2 掩盖结果。

## 8. 明确不做

- 不做缓存或模型可见证据去重；
- 不做 `rg` 搜索结果压缩；
- 不做 Graph、Ranker、Discovery、embedding 或长期记忆；
- 不做复杂 Shell parser；
- 不支持非 Python 语言；
- 不做普通全局变量/动态 import/运行时反射的数据流分析；
- 不调整 Old M2d 或 Compact Navigator；
- 不因单一 synthetic case 宣称完整开发会话节省。

## 9. 停止条件

出现以下任一情况时停止扩展 CO-1 并复审宿主或激活规则：

- 为保持 correctness 必须频繁返回接近整文件的包；
- `decision:block` 引发明显重试或补偿读取；
- syntax slice 经常因上下文缺失导致新增失败；
- 真实任务的完整会话收益无法稳定转正。
