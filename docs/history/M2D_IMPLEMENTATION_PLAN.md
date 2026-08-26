# M2d 实施计划：多源候选导航与未知目标发现

最后更新：2026-08-15

## 阶段目标

在自然语言任务不包含目标文件、函数或类名时，用可替换、受预算约束的候选发现源缩小搜索空间，并取得可核验源码证据。

M2d 交付的是 `Discovery Router` 与有数据支持的 Source 选择策略，不预先承诺 Serena 必须进入核心。

## 开发前五问

1. 多源发现只在本地排名低置信或即将错误停止时调用，用于减少未知目标搜索空间。
2. 它增加查询、序列化、延迟和候选误读成本；全部计入统一预算与 benchmark。
3. 本阶段主要解决 Ranking 与 Stop 失败；只有诊断证明目标不可达时才归为 Graph 失败。
4. 使用固定真实任务、M2c、受限文本源、Serena 和完整组合的消融对照证明价值。
5. 删除某 Source 后结果不明显变差，该 Source 不进入核心。

## 明确不做

- 不加入 embedding、Vector Database 或 LLM 查询重写。
- 不增加新的 AST Edge，不做完整类型推断或数据流分析。
- 不加入 Git、Decision Memory 或跨 Session Memory。
- 不自动修改代码，不增加 IDE UI。
- 不建立与现有 `NavigationProvider`、`Marker`、`TaskState` 平行的核心模型。
- 不允许无限外部查询、无限候选、无法核验的 external-only 目标或预算外 reserve。

## 实施阶段

### M2d-0：失败诊断与能力探针

- [x] 在锁定的 Serena 仓库重跑 M2c 五任务基线。
- [x] 确认“配置工具名校验”和“只读工具集合”仍为 2 个错误停止。
- [x] 确认两项目标 Marker 已存在，主要属于 Ranking/Stop 失败，而不是地图缺少目标节点。
- [x] 确认现有 `NavigationProvider` 和 `TaskState` 可复用，不新增平行 Candidate 状态机。
- [x] 无 oracle 探测 Serena 的实际候选 Recall、返回成本与延迟；Recall 1/5，5/5 超过 800 Token 预算，因此不进入发现核心。

基线：M2c 3/5 正确，两个失败均以 `low_expected_gain` 结束；5 项任务全部不含目标代码标识符。

### M2d-1：最小 Discovery Router

- [x] 定义轻量 `DiscoveryHit/DiscoveryResult/DiscoverySource`，最终映射到现有 Marker。
- [x] 实现 `BoundedTextSource`，只检索受限源码标识符、字符串、docstring 和注释，不返回源码正文。
- [x] Source 提供触发条件、实际成本、查询上限和可解释原因。
- [x] Discovery、导航与源码证据共同服从现有 `total/navigation/expansion` Hard Budget。
- [x] 每个任务最多两次 discovery 记录；当前自动策略只在连续两个无关候选后 rescue 一次，相同查询不重复执行。

### M2d-2：候选融合与安全 Feedback

- [x] Discovery 只接受现有稳定 Marker ID，不创建长期 external-only 身份；行号不参与新身份。
- [x] 候选来源与 Feedback 排名信号分离，避免重复计分。
- [x] v0 只有一个外部发现源，不引入无证据的 agreement bonus。
- [x] Feedback term 保留来源；无关 Marker 的派生词失效，自动词仅在 Agent 确认相关后进入 Query。
- [x] active query term 上限为 16，低置信词不能无限自强化。
- [x] 无现有 Marker 与真实源码展开的命中不能成为 `target_found`。

### M2d-3：Serena 可选 Source

- [x] Serena 在无目标路径/Symbol 时完成独立发现探针，不使用 benchmark oracle。
- [x] Serena 不接入默认 Navigator，因此未安装、启动失败或超时不阻断内置导航。
- [x] 探针记录启动/查询延迟、返回 payload、候选数、Recall 和预算状态。
- [x] Serena 相对受限文本源无独立贡献，保留为精确核验 Provider，不进入发现核心。

### M2d-4：停止策略与 Benchmark

- [x] `low_expected_gain` 在连续低收益且仍有预算的 rescue 可用时拒绝过早停止；不遍历全部 Source。
- [x] 新增 `no_profitable_candidate_source` 与 `external_discovery_exhausted` 诊断枚举/结果。
- [x] 保留 B1/B2 为永久 regression case。
- [x] 运行 10 个 identifier-free 真实任务，覆盖 Serena 与 Agent Token Manager 两个仓库。
- [ ] 已比较 Static Top-K、M2c、BoundedText，并单独探测 Serena；原生 Codex 同任务 A/B 尚未完成。
- [x] 通过 M2c（Source 关闭）与 M2d（Source 开启）完成 Source 消融；v0 未加入 agreement，Query Evolution 防污染由专项测试覆盖。
- [x] 记录 `marginal_cost_per_rescue`、`routing_regret`、最差 Token、错误 stop 和逐任务延迟。

## M2d 完成标准

- [x] 复用现有 Marker、Provider 和 TaskState，不建立平行核心状态。
- [x] Built-in Graph 与 BoundedText 两个可替换 Source 完成无 oracle 候选发现；Serena 完成探针后被拒绝进入核心。
- [x] 候选规范化、去重、解析和统一排序可解释。
- [x] Query Evolution 支持来源、负反馈和派生词撤销；v0 自动词必须经 Agent 确认相关。
- [x] 所有核心 Source 受统一 Hard Budget、调用次数、候选数和 Query 长度限制。
- [x] B1/B2 两个已知失败全部修复。
- [x] 10 个跨仓库真实任务从 M2c 6/10 提升为 M2d 9/10，原成功任务零回归。
- [x] BoundedText 通过关闭/开启消融证明 3 个独立 rescue；Serena 因无独立贡献被排除。
- [x] 59 项源码与安装缓存测试、隐私哨兵、ResourceWarning、Skill 和插件校验全部通过。
- [x] 实现 commit `4af5900`、插件版本、任务文本、仓库版本、预算、参数及完整结果已保存；M2d v0 导航层冻结。

## 当前下一步

补原生 Codex 同任务 A/B；在完成前不把 M2d v0 的管理载荷改善外推为完整会话节省。完整结果见 `M2D_RESULTS.md`。
