# M2e 实施计划：端到端 Codex 验证

最后更新：2026-08-15

状态：M2e-0 测量与隔离校准、M2e-0.1a 编排成本归因已完成；M2e-0.1b 策略已冻结、实现待确认，M2e-1 pilot 暂缓。结果见 `M2E_CALIBRATION_RESULTS.md`、`M2E_0_1_ATTRIBUTION_RESULTS.md`，策略见 `M2E_0_1B_COMPACT_STRATEGY.md`。

## 1. 结论与定位

M2e 符合当前路线，而且是 M2d 冻结后最应该进行的工作。M2d 已证明受限候选救援能改善 Navigator 的目标到达率，但尚未证明它能降低真实 Codex 开发会话的总 Token。M2e 只验证这件事，不继续增加检索能力。

核心问题：

> 在正确性不下降的前提下，Smart Read M2d 是否能减少完成真实代码任务所需的 Codex 全会话 Token；如果不能，额外成本发生在哪里？

M2e 是测量与验证里程碑，不是新的导航功能里程碑。

## 2. 相对参考任务书的必要修改

保留：

- 冻结 M2d 导航逻辑；
- 比较原生 Codex 与 Smart Read；
- 同时观察正确性、总 Token、重复读取、步骤和尾部失败；
- 保存任务、版本、参数、原始记录和失败案例；
- 在结果明确前不进入 M3 长期记忆。

修改：

1. **删除 `git reset --hard` 与 `git clean -fd`。** 每次运行使用锁定 commit 的独立 detached worktree 或一次性副本，不能破坏用户工作区。
2. **主实验由四个全会话组收敛为两个。** A 为 Native + 中立测量层，D 为 M2d + 同一测量层。Static Top-K 与 M2c 继续作为同任务集的离线/诊断 baseline；只有主结果无法解释时才增加全会话消融，避免把 12–20 个任务直接放大成 48–80 次昂贵会话。
3. **不把工具输出估算重复加到模型 usage。** 工具结果会进入后续模型输入，通常已经反映在全会话 input usage 中。Smart Read payload、Hook 估算和源码证据 Token 只作为诊断分项，不再与模型 usage 相加形成伪造的“总 Token”。
4. **先校准可测字段，再承诺指标。** 当前 `codex exec --json` 能提供 JSONL 事件流，但 CLI 帮助没有保证具体 usage 字段。M2e-0 必须固定实际 schema、字段语义和缺失值策略；不能以估算值冒充精确全会话 Token。
5. **修正任务数量矛盾。** 不要求把 M2d 的 10 个定位任务全部塞进 12 个任务且又要求一半修改。v0 选择 6 个代表性定位任务，再新增至少 6 个修改/测试任务；完整 10 任务 M2d 集仍保留为离线 regression。
6. **小样本不把 p90 作为硬门槛。** 12 个任务的 p90 只由极少样本决定。主报告使用逐任务配对差、median、max/最差案例；样本达到 20 后才把 p90 作为描述性指标。
7. **加入实验处理合规检查。** Native 不能误用 Smart Read，M2d 必须确实加载冻结安装版并调用导航能力；两组都必须使用同一套只观察、不改变策略的测量层。

## 3. 冻结范围

M2e 期间默认冻结：

- Marker、Edge、Navigator、Discovery、Feedback、停止策略；
- Query evolution、ranking 权重、Hard Token Budget；
- Provider 路由和 M2d 激活说明；
- 插件功能代码与 Skill 行为。

只允许修复以下问题：

- 导致实验无法执行的安装、日志、解析或隔离缺陷；
- 测量层本身改变 Agent 行为；
- 两实验组配置不等价；
- usage 字段被错误解析或重复计数。

所有修复必须单独记录，重新开始受影响的配对运行；不得借“修仪表”调整排名和导航策略。

## 4. 实验组

### 主实验

- **A — Native + Measurement**：原生 Codex 文件探索；Smart Read 路由、Skill 和任务导航不可用，但保留与 D 完全相同的中立审计层。
- **D — M2d + Measurement**：加载冻结的 M2d 插件/Skill，允许 Task Navigator、关系图和 bounded-text rescue；审计层与 A 相同。

### 持续 baseline

- **B — Static Top-K**：在固定地图和预算下运行离线 baseline。
- **C — M2c Navigator**：关闭 M2d discovery rescue 的离线消融。

B/C 必须在同一任务清单上保留可比较结果，但不要求每个修改任务都运行完整 Codex 会话。若 A/D 差异来自未知目标发现且无法解释，再选择相关失败任务运行 C 的全会话消融。

## 5. M2e-0：测量与隔离校准

这是下一项具体任务，完成前不得启动正式批量 benchmark。

### 5.1 最小校准集

- 1 个无 identifier 的代码定位任务；
- 1 个需要修改代码并运行测试的任务；
- A/D 各至少重复 2 次，并平衡先后顺序。

### 5.2 必须验证

- `codex exec --json` 的实际事件 schema、会话结束事件和 usage 字段；
- input、cached input、output、reasoning/内部计算与 event-native total 的语义；
- 同一会话的事件是否会重复上报累计 usage；
- 中立外部 JSONL 测量层能否在 A/D 中以同一版本、同一配置运行且不向模型输出提示；
- A 中没有 Smart Read Skill/脚本调用，D 中确实加载固定插件版本并使用 Smart Read；
- 独立 worktree、任务状态、审计日志和模型会话不会串线；
- 修改任务能够保存最终 diff、测试结果、退出状态与 stop reason；
- 模型、reasoning effort、CLI 版本、sandbox、approval、网络条件和用户干预规则完全相同。

### 5.3 Token 计量合同

原始字段必须原样保存。主指标优先使用 Codex 事件中明确提供的 session/turn usage，不推测缺失字段。

- `model_input_tokens`
- `model_cached_input_tokens`（若可用，单独报告，不擅自判断是否已包含在 input）
- `model_output_tokens`
- `model_reasoning_tokens`（若可用）
- `model_total_tokens`（只使用事件原生 total，或在 schema 校准后采用唯一、文档化公式）

诊断字段：

- `estimated_tool_result_tokens`
- `estimated_read_result_tokens`
- `smart_read_navigation_tokens`
- `smart_read_evidence_tokens`
- `duplicate_result_count`

诊断字段不得再次加进 `model_total_tokens`。若精确 usage 无法稳定取得，M2e 可以继续验证读取行为，但必须标记为“测量阻塞”，不得发布完整会话节省比例。

### 5.4 隔离与缓存政策

- 每个 arm/run 从同一锁定 commit 创建独立 detached worktree；禁止重置或清理用户工作区。
- 主结果采用“预建稳定地图 + 全新 TaskState”的实际使用场景；索引构建时间、索引大小和增量成本单独报告。
- M2e-0 另做一次冷启动，记录首次索引和加载延迟，不把本地索引计算折算成模型 Token。
- 每个配对任务平衡 A/D 运行顺序，降低服务波动、提示缓存和时间漂移影响。
- 不允许人工中途提示；超时、审批失败和工具故障按预先定义的 infra failure 处理，不偷偷重跑最好结果。

### 5.5 M2e-0 完成条件

- [x] 两类校准任务均完成 A/D 配对运行；
- [x] usage schema、计量公式与缺失字段策略固定；
- [x] 中立测量层已证明不会改变两组策略；
- [x] worktree、日志、TaskState 和缓存隔离通过；
- [x] 实验组行为合规可自动检查；
- [x] 能生成一份不重复计数的端到端结果记录；
- [x] 校准中发现的基础设施问题已修复并复跑。

## 6. M2e-1：正式配对 benchmark

M2e v0 至少 12 个任务，建议逐步扩展到 20 个；至少覆盖 3 个不同结构的真实仓库，避免 Serena 与项目自身过拟合。

### 6.1 任务分层

- 6 个定位/解释任务：从冻结的 M2d 10 任务中预先选择，包含成功、rescue 和已知失败类型；
- 至少 6 个修改/测试任务：包含单文件修改、跨文件修改、调用/继承/reference 导航与自然语言未知目标；
- 至少一半任务不在提示中泄露目标路径或符号；
- 每个任务固定 prompt、commit、允许修改范围、目标测试、超时、成功判据和隐藏 oracle。

定位任务的成功必须包含可核验的文件、符号和证据；修改任务不能只看“测试通过”，还要检查目标行为、最终 diff、越界修改与隐藏/针对性测试。

### 6.2 重复与顺序

- 先以 6 个任务完成 pilot；仪表稳定后扩展到至少 12 个；
- 每个 arm/task 最少 2 次独立运行；
- A/D 顺序采用配对平衡或预先生成的随机顺序；
- 失败、超时和离群值全部保留，复跑必须带明确原因，不能用复跑替换原始失败。

## 7. 指标与判定

### 7.1 主指标

1. **任务正确性非劣化**：M2d 不得增加配对任务失败；失败需区分 task failure 与 infra failure。
2. **每个成功任务的端到端 Token**：优先比较两组都成功任务的逐任务配对差与比率。
3. **端到端 Token 中位数**：报告 Native、M2d 与配对节省率，不只报告平均值。

只有正确性门槛先通过，Token 节省才可作为正面结论。

### 7.2 次指标

- 总读取调用、读取结果估算 Token、重复结果数；
- files/symbols expanded、导航 steps、stop reason；
- Smart Read 管理载荷及其占总模型 usage 的诊断比例；
- time-to-first-correct-target（只有日志能可靠识别时才报告）；
- wall time、索引时间、存储和异常工具调用；
- median、逐任务最大 regret、失败任务成本；样本达到 20 后再报告描述性 p90。

### 7.3 M2e v0 验收标准

- [ ] 主实验为 Native 与冻结 M2d 的同任务、同配置配对；
- [ ] 至少 3 个真实仓库、12 个任务，至少 6 个修改/测试任务；
- [ ] 每个 arm/task 至少 2 次运行，顺序平衡；
- [ ] 能取得经过校准且不重复计数的 Codex 全会话 usage；
- [ ] M2d 正确性不低于 Native，全部失败有分类和原始记录；
- [ ] M2d 的配对中位端到端 Token 低于 Native；
- [ ] 只有配对中位节省达到 15% 且正确性不下降时，才表述为“具有实质端到端节省”；低于该值只能称为小幅或不确定改善；
- [ ] 工具读取、重复结果、管理载荷和最差案例均被报告，不以局部工具输出代替总 usage；
- [ ] Static Top-K 与 M2c 同任务诊断 baseline 仍可复现；
- [ ] M2d 功能保持冻结，全部旧测试通过，源码版与安装版一致；
- [ ] 保存 commit、CLI/模型/插件版本、任务 manifest、运行顺序、配置、原始 JSONL、审计日志、diff、测试结果和汇总脚本。

## 8. 失败分类与决策

- **Measurement failure**：usage 缺失、事件重复、A/D 仪表不等价；先修测量，不评价 Smart Read。
- **Integration failure**：Skill 未加载、版本错误、Hook/配置串线；先修安装与隔离，不调 Ranker。
- **Routing regret**：明确目标或小文件本可直接读取，却被 Smart Read 增加步骤；优先改激活条件，不扩图。
- **Ranking/Stop failure**：目标在地图或候选中，但选不到或过早停止；记录为后续回归，不在 M2e 内调权重。
- **Graph/Discovery failure**：目标不可达或候选源未命中；进入下一个导航里程碑评估，不在 M2e 偷加新 Edge。
- **Task failure**：最终答案、补丁或测试不正确；必须计入正确性，不得只比较成功会话的漂亮 Token。

决策：

- 正确性不下降且节省达到实质阈值：冻结 M2e v0 结果，进入发布/激活策略与 M3 规划；
- 正确性不下降但节省不足：按任务类别分析 routing regret 和管理开销，优先收紧激活策略；
- 正确性下降：不发布端到端优势声明，保留 M2d 离线结果并把失败加入 regression；
- 测量不可靠：M2e 保持未完成，不能用估算载荷替代结论。

## 9. 明确不做

- 不增加 embedding、长期记忆、新 Edge 或新 Provider；
- 不为了 benchmark 任务微调 query term、ranking 权重或 stop threshold；
- 不把 Serena 重新引入默认 Discovery；
- 不用聊天摘要充当 Git/diff/test 事实；
- 不把局部代码读取节省宣传成完整开发会话节省；
- 不删除、重置或清理用户工作区来制造可重复环境。

## 10. 当前进度与下一步

- [x] 评审外部 M2e 任务书并确认与 M2d 冻结结论一致；
- [x] 修正危险环境重置、四组成本、任务数量矛盾、Token 重复计量和小样本尾部指标；
- [x] 将 M2e 纳入项目正式计划；
- [x] M2e-0 测量与隔离校准完成，结果见 `M2E_CALIBRATION_RESULTS.md`；
- [x] M2e-0.1 已固定三层成本归因、compact one-shot/two-stage、Activation Gate、消融顺序与 `≤1.25x` 阶段门槛，见 `M2E_0_1_IMPLEMENTATION_PLAN.md`；
- [x] M2e-0.1a 已完成；修正 started/completed 重复计数，实际完成命令为 M2d 51 vs Native 18，精确重复 payload 均为 0；直接 payload 差值只相当于模型 Token regret 的约 2.52%，见 `M2E_0_1_ATTRIBUTION_RESULTS.md`；
- [x] M2e-0.1b 最多两次交互、批量 semantic feedback、双硬预算、幂等与离线 Gate 策略已冻结；
- [x] Compact Gate 1 已实现并通过；本轮未运行昂贵端到端会话，见 `M2E_0_1B_GATE1_RESULTS.md`；
- [x] Compact Gate 2 已运行但失败：冻结成功集合只保留 2/9；后续 Gate 与昂贵端到端会话停止，见 `M2E_0_1B_GATE2_RESULTS.md`；
- [ ] 诊断和最小消融通过后冻结 M2e-1 benchmark manifest；
- [ ] 运行 6 任务 M2e-1 pilot，再决定是否扩展到 12–20 个任务。
