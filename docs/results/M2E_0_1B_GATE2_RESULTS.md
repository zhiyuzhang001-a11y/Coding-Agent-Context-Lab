# M2e-0.1b Gate 2 结果

最后更新：2026-08-15

状态：**失败。Compact 满足最多两次协议结果和全部预算约束，但只保留冻结 M2d 原成功任务中的 2/9；停止 Gate 3 与端到端消融。**

## 1. 冻结条件

- M2d 冻结实现记录：commit `4af5900`；
- Serena：commit `3ad624f511511bb7a77447e413425198fc574349`；
- 同一组 10 个无 identifier 英文自然语言任务；
- 冻结成功集合：除 `environment-diagnostics` 外的 9 个任务；
- 每任务预算：total 8,400、navigation 2,400、expansion 6,000；
- Compact：model-visible 1,600、steps 8、fan-out 8、hops 2、source reads 8、elapsed 5,000 ms；
- 不启用 Activation Gate，不修改 Ranker 权重、Graph、Discovery Source 或任务文本。

Benchmark oracle 只在 Evidence 返回之后分类：目标 Evidence 和已冻结的相关中间 Evidence标为 accepted，无关 Evidence 标为 rejected。只有目标已在第一次 Evidence 中出现时才不提交 `missing_questions`；oracle 不进入 Query、候选生成、排序或补证提示。

## 2. 实现与计量

新增 `scripts/run_compact_gate2.py`：

- 每个任务建立独立 TaskState，共享同仓库的只读结构索引；
- 记录 `navigate`/`verify` phase、协议结果数、内部 steps、source reads、Evidence 数量与 Token、model-visible payload、预算、hop、Discovery、stop reason；
- correctness 只由最终模型可见 Evidence 的 path 与 symbol 命中判断，不能由 `evidence_sufficient` 自证；
- 明确区分 target selected/expanded 与 target packaged；
- 原成功任务任意一个失败即 Gate 失败，已知失败的新成功不能抵消回归。

原始无源码正文 JSON 保存在被 Git 忽略的：

```text
.agent-token-manager/compact-gate2.json
```

## 3. 最终结果

```text
任务数                         10
冻结原成功集合                  9
Compact 保留原成功              2 / 9
Compact 总正确                  2 / 10
协议违规                        0
单结果任务                      1
双结果任务                      9
最大模型可见协议结果             2
内部 selected steps             74
源码读取                        58
模型可见 payload                14,480 estimated tokens
原 rescue 案例保留               1 / 2
```

逐任务结果：

```text
optional-tool-selection       FAIL  verification_supplement_failed
configured-tool-validation   FAIL  verification_supplement_failed  rescue regression
read-only-tool-set           PASS  bounded-text target hit
symbol-reference-search      FAIL  evidence_not_packaged
project-activation           FAIL  evidence_not_packaged
task-state-persistence       FAIL  verification_supplement_failed
budgeted-file-routing        PASS  bounded-text target hit
private-audit-record         FAIL  evidence_not_packaged
environment-diagnostics      FAIL  frozen known failure
audit-summary                FAIL  verification_supplement_failed
```

冻结 Old M2d 的正式记录仍为 9/10。当前工作树上的显式 M2d runner 同环境复跑通过，甚至因仓库内容演进达到 10/10；该结果不替换 commit `4af5900` 的冻结 baseline，但确认任务集、Serena 索引和显式 Navigator 循环仍可工作。

## 4. 本轮发现并修正的编排错误

第一次运行为 0/9，暴露两个纯 Compact 问题：

1. structural signal 被错误当作语义充分性，产生 `false_structural_completion`；现在只有任务明确包含候选 symbol 时才允许结构直接完成；
2. 第一次调用占用几乎全部内部步骤；现在第一阶段只使用受限前置批次，把大部分统一预算留给唯一一次 verify。

随后又修正：

- accepted Evidence 表示“相关”，只有不存在 `missing_questions` 时才表示充分；
- 未经 Agent 接受的 compact structural 新词不能进入 Discovery Query，防止错误自强化；
- 第二个模型可见调用内可以执行多步但仍受同一 steps/source/hop/time/budget 上限；
- 第二阶段优先打包最新补证，并把单次展开重新限制为冻结 M2d 的 650 Token。

这些修改把冻结成功保留从 0/9 提升到 2/9，但仍远未达到验收线，因此没有继续调参。

## 5. 失败定性

Gate 2 否定了当前假设：

> 仅把旧循环放进本地，并依靠 structural feedback 加一次批量 semantic feedback，就能在最多两次模型可见结果内保留 M2d 的导航能力。

剩余失败分成两类：

- 4 个 `verification_supplement_failed`：一次批量反馈后，确定性内部循环仍无法复现 Old M2d 每步 semantic feedback 带来的路径选择；
- 3 个 `evidence_not_packaged`：目标 Marker 已 selected/expanded，但 650 Token 完整性、截断或 1,600 Token package 选择使目标源码未成为模型可见 Evidence。

这不是 Graph/Ranking 权重失败，也不能通过提高 Discovery boost 或扩大预算掩盖。真正矛盾是：Old M2d 的 9/9 部分依赖逐步 oracle/Agent 语义反馈，而当前 Compact 同时要求最多两次交互。

## 6. 决策与下一步

- Gate 2 标记失败；不进入 Gate 3、Gate 4 扩大验收或 Native/Old M2d/Compact 昂贵端到端消融；
- 不实现 Activation Gate；一个被激活后仍不保真的 Compact 不值得研究何时激活；
- 不为追 9/9 修改 Ranker、Graph、Discovery 或任务参数；
- 架构复审已选择透明 Context Optimization Layer：保留 Codex 原生语义循环，只优化模型可见的 read/search 结果；
- 新主线从 CO-0 Hook/interface feasibility 开始，先用 canary 证明原始大 payload 未进入模型可见输入，不先实现复杂优化算法；
- CO-0 使用严格命令白名单和可观测 fail-open。未知或失败路径回退 Native，但白名单 fallback 不计为优化成功；
- 通过后依次进入 Syntax-aware Read Slicing、Model-visible Evidence Dedup、Search Compression、Unified Visible-context Budget 与 Native/CO 完整会话 A/B；
- CO 主线不占 M3 编号，原 M3 长期记忆计划保留。详见 `CO_0_IMPLEMENTATION_PLAN.md`。

当前 Compact 与 Old M2d 均冻结为研究接口，不切换 Skill 默认路径、不删除历史实现。

## 7. 验证状态

- 开发插件版本：`0.1.0+codex.20260815122816`；
- Compact Gate 2 契约测试：3/3；
- 源码全套测试：90/90，ResourceWarning-as-error 通过；
- 安装缓存同版本 90/90 与 ResourceWarning-as-error 通过，源码和缓存逐文件一致；Skill 默认行为保持不变。
