# M2e-0.1b 策略：Compact Navigator

最后更新：2026-08-15

状态：策略已冻结；固定 Fixture Gate 1 通过，但 Gate 2 只保留冻结成功集合的 2/9，已失败并停止后续昂贵验证。结果见 `M2E_0_1B_GATE1_RESULTS.md` 与 `M2E_0_1B_GATE2_RESULTS.md`；Ranker、Graph、Discovery 与 Skill 默认行为保持冻结。

## 1. 目标

Compact Navigator 不继续优化“读什么”，而是压缩“让模型重新参与多少次”。

> 保留 TaskState、结构 Feedback、Graph、Hard Budget 和 Stop Policy，但把确定性的导航循环放进插件内部，只让 Codex 看到最多两次高价值结果。

它不是把旧的 `start/next/expand/feedback/stop` 命令机械串联，也不试图把 Codex 的语义判断搬进插件。

## 2. 两阶段状态机

```text
new
 ↓
compact_navigate
├─ completed
│    └─ evidence_sufficient → 结束
│
└─ needs_verification
       ↓
compact_verify
       └─ completed → 必须结束并给出 stop_reason
```

硬约束：

- `compact_navigate` 每个 Task 只接受一次；
- `compact_verify` 最多接受一次，且只能从 `needs_verification` 进入；
- 第二次被接受的调用必须终止任务；
- 不允许重新暴露 `next → expand → feedback → next` 模型循环；
- `TaskState` 持久记录 `phase`、`external_call_count`、`verification_used`、预算与最终 `stop_reason`；
- 一个任务对模型可见的 Compact 结果最多两个。

### 2.1 幂等与错误边界

两次限制按“成功接受并发生状态转换的请求”计数，而不是按网络尝试次数计数：

- 每个请求携带 `request_id`；
- 相同 `request_id` 的重试返回缓存的相同结果，不重复探索、不重复扣预算；
- 错误 phase、未知 Evidence 或格式错误不启动探索；
- Task 已终止时，相同请求返回稳定终态；新的不同请求返回控制层错误。

以下是协议状态，不是任务语义 `stop_reason`：

```text
invalid_phase
external_call_limit_reached
stale_evidence
invalid_feedback
```

这样不会用“第三次调用失败”覆盖任务已经形成的真实停止原因。

## 3. Feedback 边界

### 3.1 插件内部：structural_feedback

插件只允许自动产生可确定计算的结构信号：

- calls、inherits、references 与受限 Graph 邻接；
- 新 Symbol 与路径发现；
- 任务词和标识符覆盖；
- Evidence 完整性、截断与 hash；
- 是否形成可核验调用链；
- 是否存在未解析的高价值依赖；
- Discovery 来源、成本与结构置信度。

这些信号可以重排候选，但不能声称“源码已经真正解释用户问题”。结构置信度是可解释信号，不包装成模型级正确概率。

### 3.2 第二阶段：一次批量 semantic_feedback

第一次调用不能保守确认 `evidence_sufficient` 时，返回少量待确认 Evidence。Codex 只在第二次调用中提交一次：

```text
accepted_evidence[]
rejected_evidence[]
uncertain_evidence[]
missing_questions[]
```

约束：

- 三组 Evidence ID 必须互斥；
- Evidence ID 必须来自第一次返回包；
- Feedback 同时携带 Evidence hash，hash 变化时返回 `stale_evidence`，不使用过期判断；
- `missing_questions` 最多 2 条，每条有长度上限；
- 不接受新的开放式任务替换原任务；
- semantic feedback 只影响第二阶段有限补证，不能开启第三轮。

暂不引入本地小模型、额外 LLM、embedding semantic judge。结构判断尽量内部化，语义判断最多跨越一次模型边界。

## 4. 双硬预算与安全上限

### 4.1 internal_exploration_budget

限制插件内部：

- 候选生成与结构排名；
- Graph expansion；
- structural feedback；
- Marker 解析；
- 局部源码展开；
- 第二阶段补证。

继续复用现有 navigation/expansion/remaining 账户和同一估算方法，不允许 Compact 路径绕过原 Hard Budget。

### 4.2 model_visible_budget

限制真正进入 Codex 上下文的：

- Compact Context Package 包络；
- Evidence 源码；
- verification request；
- 第二阶段补证结果。

两个预算分别强制执行、分别报告。相同 Evidence 在内部读取并最终返回时不机械相加成一个伪造的模型 Token 总数；端到端主指标仍使用 Codex 原生 usage。

### 4.3 非 Token 硬限制

必须同时存在：

```text
max_steps
max_fanout
max_hops
max_source_reads
max_elapsed_ms
```

`max_elapsed_ms` 仅作为安全熔断器，不参与候选排名；benchmark 单独报告因机器速度造成的熔断，避免不可复现的质量漂移。

## 5. 第一次调用的保守停止规则

`compact_navigate` 只有满足可测试的结构闭合规则，才允许直接 `completed`。

### A. 高置信叶子实现

- 找到实际实现而非仅入口、声明或协议；
- 任务词或结构路径与源码 Evidence 对应；
- 没有影响判断的截断；
- 不存在更高价值的未解析直接依赖。

### B. 完整行为链

形成可核验的：

```text
入口 → 中间关键节点 → 最终实现
```

关键 Edge 均有结构证据，关键节点源码完整。

### C. 修改目标闭合

- 修改目标区域明确且完整；
- 必要依赖已经取得；
- 在受限 hop/fan-out 范围内，没有高置信未知 caller 或 dependency 会改变修改判断；
- “闭合”只针对已声明的有界图，不声称理解整个仓库。

### D. 预定义规则通过

`evidence_sufficient` 必须由证据覆盖、结构闭合、完整性与未解析风险共同决定，不能仅因单个 Ranking Score 较高而通过。

只要仍有实质语义不确定性，就进入 `needs_verification`。

## 6. 第二次调用

`compact_verify`：

- 只在 `phase = needs_verification` 时接受；
- 使用唯一一批 semantic feedback；
- 只补最关键的证据缺口；
- 仍服从剩余 internal/model-visible budget 和全部安全上限；
- 当前调用内完成最终排序、补证和停止；
- 不要求 Codex 再次反馈。

任务终止原因采用结果导向的枚举：

```text
evidence_sufficient
verification_inconclusive
budget_exhausted
low_expected_gain
source_exhausted
internal_limit_reached
error
```

不采用 `verification_completed` 这类只描述流程结束、不说明结果质量的原因。即使证据仍不足，也必须以 `verification_inconclusive` 明确结束。

## 7. Compact Context Package

Codex 只看到决策包，不看到内部运行日志：

```text
schema_version
task_id
phase
decision
evidence[]
why_it_matters[]
confidence
uncertainties[]
omissions[]
budget
stop_reason
verification_request
```

`verification_request` 在 `completed` 时为空，在 `needs_verification` 时只包含少量 Evidence ID 和至多两个问题。

### 7.1 Evidence

每项至少包含：

```text
evidence_id
path
symbol
lines
hash
complete
truncated
source
reason
structural_confidence
code
```

要求：

- `code` 是可判断、定位和编辑的必要源码，不用模型摘要代替；
- 编辑前关键目标区域必须完整；
- Evidence 正文只在当前返回包中瞬时存在；
- TaskState、索引和私有 trace 不持久化源码正文；
- TaskState 只保存 Evidence ID、hash、范围、成本和状态；
- hash 改变时旧 semantic feedback 失效。

## 8. 私有 Trace

以下内容默认不进入 Codex 上下文：

- 全部候选和每轮完整分数；
- 临时候选、被淘汰节点和完整 Graph trace；
- 每一步 structural feedback；
- 中间 Hypothesis；
- Provider 原始返回；
- 详细内部预算流水。

Trace 只用于 Debug、benchmark、ablation 和 regression，并继续遵守不保存源码正文的隐私约束。

## 9. 阶段职责

```text
compact_navigate
= 结构导航
+ 候选发现
+ 低成本源码取证
+ structural_feedback
+ Evidence 组织
+ 保守 evidence_sufficient 判断
```

```text
compact_verify
= 接收一次 semantic_feedback
+ 针对缺口有限补证
+ 最终 Context Package
+ 强制停止
```

## 10. 验证门

### Gate 1 — 固定 Navigator Fixture

3 个固定 Fixture，验证：

- 第一次直接完成；
- 第一次请求验证、第二次完成；
- 幂等重试、非法 phase 和第三次调用拒绝；
- 双预算与内部安全上限；
- Evidence Package、隐私和 stop reason。

### Gate 2 — M2d 无 Identifier Benchmark

运行已有 10 个任务。要求：

- 冻结 M2d 原本成功的 9 个任务零回归；
- 已知 1 个失败可保持或改善，不能用另一任务的新成功掩盖原成功回归；
- 每个任务外部 Compact 调用不超过 2；
- 报告内部 steps、源码读取、Evidence 数量和 model-visible payload。

Gate 2 固定补充约束：

- Compact 实现、Serena 仓库、任务集、预算和参数全部锁定；不临时修改 Ranker、Graph、Discovery、stop threshold 或 Compact 参数；
- Benchmark oracle 只在 Navigator 返回 Evidence 后判断 accepted/rejected 与最终 target hit，不进入任务文本、候选生成、Query、排序或补证提示；
- `stop_reason=evidence_sufficient` 不是正确性证据，最终 Evidence 必须命中冻结的 expected path/symbol；错误自动完成按 false completion 计为失败；
- 每个任务使用独立 TaskState；同一仓库可以复用只含结构元数据的索引，但索引时间和任务导航成本分开报告；
- 离线 Gate 2 的 `external_calls` 表示模型可见协议结果数，不冒充真实 Codex 模型调用；
- 特别保留并检查原 M2d 的 bounded-text rescue 修复任务；原 `environment-diagnostics` Ranking 失败不在本门调权修复。

若发生回归，固定分类为：

```text
candidate_not_reached
evidence_not_packaged
false_structural_completion
verification_supplement_failed
evaluator_mismatch
```

### Gate 3 — Serena Regression

覆盖配置工具名校验、只读工具集合、`ToolSet.apply` 等已有失败/修复案例，不得重新出现已修复错误停止。

### Gate 4 — 全部旧测试

- 全部既有测试；
- Privacy Sentinel；
- ResourceWarning-as-error；
- CLI、Skill、源码插件与安装插件一致。

### Gate 5 — Codex End-to-End Ablation

前四门全部通过后，才在相同任务、commit、模型和顺序平衡条件下运行：

```text
Native
vs Frozen Old M2d
vs Compact
```

Old M2d 必须锁定 commit、插件版本、Skill 和参数，不能用当前开发目录冒充冻结 baseline。

## 11. 指标

主指标：

```text
correctness
total_model_tokens
```

辅助指标：

```text
completed_commands
external_navigator_calls
model_visible_payload_tokens
source_reads
internal_steps
wall_time
stop_reason
```

当前 JSONL 只有最终累计 usage：只报告实际最终 usage，不推测逐轮 Token，不把工具 payload 冒充模型 input。若未来事件提供多个可靠累计 usage，才记录 `usage_growth_sequence`；否则明确为 `unavailable`。

本阶段验证的因果问题是：

> 外部调用下降是否近似转化为全会话 Token 下降。

如果调用压到每任务最多 2 次且正确性保持，但完整 Token 仍显著高于 Native，才进入“透明 Context Optimizer”架构复审。

## 12. Activation Gate

Activation Gate 不属于 M2e-0.1b 核心验收。顺序固定为：

```text
先证明 Compact 被激活后不再昂贵
再研究什么时候激活 Compact
```

不能同时改变 Navigator 协议与 Activation Policy，否则无法归因收益来源。

## 13. 成功条件与明确不做

进入完整 Codex 消融前必须同时满足：

```text
external_calls <= 2 / task
frozen_success_cases = 9/9
all_offline_gates_passed
```

本阶段不做：

- 不修改 Ranker、Edge、Discovery Source 或 M3；
- 不引入 LLM、embedding 或本地语义模型；
- 不实现 Activation Gate；
- 不把内部 trace 返回给模型；
- 不用一次调用率替代正确性；
- 不在离线门失败时继续烧完整 Codex 会话。

核心原则：

> 结构判断尽量内部化，语义判断最多跨越一次模型边界。
