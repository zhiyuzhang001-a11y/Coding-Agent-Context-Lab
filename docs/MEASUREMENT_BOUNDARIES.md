# Measurement Boundaries

## 核心判断

“监控 Token”不是单一能力。一个工具能够展示 Token 数字，不代表它能看到 Host 内部完整上下文、精确归因每个来源，或证明某项优化降低了总成本。

## 四个层级

### 1. Usage 汇总

数据来源通常是服务商响应中的 `usage`，或 Host 写入本地 transcript 的 input/output/cache 字段。对这些已暴露字段，汇总可以是确定性的；但它只说明日志记录了什么。

不可自动推出：

- Host 是否遗漏内部请求或重试；
- 订阅配额如何折算；
- 服务端是否追加未公开内容；
- 某个本地文件或工具结果贡献了多少 Token。

### 2. 货币成本估算

成本通常由 usage 与公开单价相乘。API 按量计费时可能接近账单；订阅、套餐、缓存阶梯、免费额度和动态价格会使它成为估算。

### 3. 请求内来源归因

要把输入拆分到 system prompt、tool schema、消息历史、工具结果和 MCP 内容，至少需要：

- 完整的模型实际请求；
- 稳定的块边界；
- 与服务商一致的 tokenizer 或可靠校准；
- cache read/write/fresh 的真实边界。

缺少任一条件时，应报告 `unknown`、范围或估算，不能把比例分摊表述成精确事实。本项目的 Host Hook 没有提供足够分类来完成全量精确归因。

### 4. 干预的因果收益

即使准确知道一次请求中的某段很大，也不能直接断言删掉它会节省整个任务。干预可能造成更多轮次、重复搜索、错误恢复或质量下降。需要在冻结任务和 Gate 下比较：

- 正确性和成功语义；
- 工具路径与任务轮次；
- model-visible evidence；
- session usage；
- 未知和缺失覆盖率。

M2d 的 `3.131x` 结果正说明局部 payload 下降与会话总量可能方向相反。

## 本项目实际覆盖

已覆盖：

- 当前 Bash/code-mode 观察路径的 raw result、Hook 和 transcript 关联；
- privacy-safe、coverage-aware 的事件规范化和事实报告；
- 冻结局部 evidence reduction 实验；
- benchmark qualification、registry 和自动 futility。

未覆盖或未证明：

- 当前 Host 隐藏上下文的完整重建；
- 所有来源的精确 tokenizer 级归因；
- 订阅/账单级成本真值；
- 跨模型、Host、工具家族的通用节省；
- 保持成功语义的透明通用 replacement。

因此最安全的表述是：

> 本项目提供可审计的上下文成本测量和干预评估基础，但不提供完整 Host 内部 Token 真值，也未验证生产级全局节省。
