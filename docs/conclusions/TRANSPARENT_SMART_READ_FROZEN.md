# Transparent Smart Read：冻结研究里程碑

- 冻结日期：2026-08-16
- 最终状态：`BLOCKED_HOST_INTERFACE`
- 算法状态：`NOT_FALSIFIED`
- 产品状态：`FROZEN`
- 重新开启条件：`SUCCESS_PRESERVING_RESULT_REWRITE`

## 一句话结论

> Transparent Smart Read is blocked by the current Codex host interface, not falsified at the algorithmic level.

Smart Read 的结构切片与风险控制机制并未被否定；当前产品化路径因缺少“保持工具成功语义的模型可见结果替换接口”而冻结。

## 最初目标

在不改变 Codex 原生工作流、不增加模型语义回合、不降低 correctness 的前提下，透明减少进入模型的源码与搜索结果，最终降低完整会话 Token。

Smart Read 不应替代 Codex 的语义判断，也不应要求 Codex 驾驶显式导航器；它只应在结果进入模型前完成切片、压缩、去重和预算控制。

## 探索路线与结论

### M2：Agent-side navigation

- M2d 在 10 个无 identifier 任务中由 M2c 的 6/10 提升到 9/10，证明逐步语义反馈与结构导航能改善目标发现。
- M2e 完整会话 A/B 的 M2d/Native 配对 Token 比率中位数为 `3.131x`。局部证据读取节省没有覆盖显式导航协议、额外回合和上下文重放成本。
- Compact Navigator 把模型可见协议压到每任务最多两次，但冻结成功集合只保留 2/9，说明原来的 9/10 很大程度依赖多轮语义纠偏。

结论：导航智能有研究价值，但不适合作为模型显式驾驶的产品协议。

### CO-0：透明 Hook/interface 合成可行性

- 冻结接口矩阵 7/7 通过；四组合成 Native/CO 配对 correctness 一致，重试和补偿调用均为 0。
- 模型可见工具上下文净节省 75.95%；完整会话配对比率中位数为 `0.9931x`。

结论：合成白名单路径上的透明替换可行，但不能据此证明真实开发会话收益。

### CO-1：Syntax-aware Read Slicing

- Python function、async function、method 和 class 的 AST 完整切片成立；三个项目内大文件目标的离线字符下降中位数为 67.72%。
- Gate 2 中 6/6 correctness 一致，activated read 在补偿后仍节省中位数 42.715%。
- 但 0/4 activated 任务的完整会话优于 Native，总 Token 从 161,077 增至 178,805（+11.01%）。一次仅 28 Token 的全局常量补读，因增加模型回合使单任务完整 Token 增加 52.63%。

结论：语法切片有效；新增语义回合的成本可能远高于被省下的代码正文。

### CO-1.1 / CO-1.2：固定成本与补偿风险

- Hook-only observe 相对 Native 的固定成本中位数仅 +23 Token，约 +0.074%，不是主要问题。
- 确定性 compensation-risk gate 与 economic gate 已实现：外部常量、import/helper、class state、sibling method、动态语义、高风险意图、歧义和低收益均可解释地 fail-open；切片要求预计至少节省 200 Token 且比例至少 40%。

结论：可以做到“少切、保守切”，但仍需真实自然流量经过替换点。

### CO-1.3：冻结版自然行为 A/B

- 12 个任务、24 场 Native/CO 运行全部完成，correctness 12/12 一致。
- 实际 replacement 为 0/12；16 次 Hook 尝试中 12 次为 `unsupported_request`，4 次为 `non_unique_target`。
- 完整 Token pooled 比率为 `0.963061x`，配对中位数为 `0.999391x`，且 6 对下降、6 对上升。因为没有 replacement，差异不能归因于 Smart Read。

结论：自然 Codex 不遵循预设的单 symbol primitive read 协议；继续扩 AST 或解析更多 `sed` 不会解决宿主路径问题。

### CO-1.4：Host Path Reconnaissance

- 1.4a：12 个自然 CO 会话中的 16/16 个 code-bearing Bash 结果均被 PostToolUse 观察；17,651/17,651 模型可见 Token 与 raw→Hook→transcript 关联覆盖均为 100%。
- 1.4b：四种命令形态中，canary 4/4 进入模型可见 transcript，raw result 4/4 完整保留，每场仍为 1 次工具调用、2 个模型周期。
- 但四个 treatment 均被宿主包装为 `Script failed / Script error`，因为当前通用替换依赖 `decision:block`。

结论：统一观察点存在，替换内容也能进入模型；缺失的是不改变成功状态的通用结果替换能力。

## 已证明与未证明

已证明：

- 结构化、语法完整的局部切片能显著减少源码正文。
- 确定性的风险门和经济门可以保守 fail-open。
- 在本次自然 code-mode/Bash 数据集中，PostToolUse 能观察全部 code-bearing 结果。
- block-style replacement 能改变模型最终可见内容。

未证明：

- 当前 Codex 接口可执行保持成功语义的通用本地工具结果替换。
- Transparent Smart Read 能在真实开发任务中稳定降低完整会话 Token。
- 当前观察覆盖可推广到 direct read、MCP、LSP、hosted tool 或其他模型/宿主路径。
- 本次小规模任务和模型结果具有普遍性。

## 正式停止范围

以下工作自本里程碑起冻结：

- M2 Navigator 产品化、Compact Navigator 与 Activation Gate。
- 当前 AST slicer、compensation-risk gate、economic gate、benchmark 与 Hook/probe 实验线。
- CO-2 Evidence Dedup、CO-3 Search Compression、CO-4 Unified Budget 与 CO-E2E。
- 为覆盖更多自然命令而扩写 shell parser。
- 针对当前 Codex Hook 继续寻找旁路 hack。

不删除任何研究代码、固定任务、结构化结果或原始私有 artifact。冻结表示停止投入，不表示算法无效。

## 重新开启条件

只有满足下列至少一项，Transparent Smart Read 才重新进入实施计划：

- Codex 提供 success-preserving tool-result rewrite。
- 出现稳定、统一的 model-visible result adapter。
- Hook/API 支持替换结果同时保持原工具成功状态。
- 发现新的宿主层 interception point，并用 canary 证明其不增加模型周期、不改变工具语义。

重新开启时不得直接继续 CO-2。应先复跑 CO-1.4 的观察覆盖与替换 canary，确认正常 success envelope，再恢复 CO-1.2 Gate，并重新执行完整会话 A/B。

## 保留资产

设计与约束：

- `SMART_READ_DESIGN.md`
- `LONG_TERM_CONSTRAINTS.md`
- `UPSTREAM_CAPABILITY_REVIEW.md`
- `PROJECT_PLAN.md`

关键结论：

- `M2D_RESULTS.md`
- `M2E_CALIBRATION_RESULTS.md`
- `M2E_0_1B_GATE2_RESULTS.md`
- `CO_0_RESULTS.md`
- `CO_1_GATE1_RESULTS.md`
- `CO_1_GATE2_RESULTS.md`
- `CO_1_1_RESULTS.md`
- `CO_1_2_OFFLINE_RESULTS.md`
- `CO_1_3_RESULTS.md`
- `CO_1_4A_RESULTS.md`
- `CO_1_4_RESULTS.md`

结构化结果：

- `resources/co0_matrix_results.json`
- `resources/co1_gate2_results.json`
- `resources/co1_1_pilot_results.json`
- `resources/co1_3_results.json`
- `resources/co1_4_observe_results.json`
- `resources/co1_4_results.json`

实现与复现入口：

- `scripts/python_syntax_slice.py`
- `scripts/run_co1_gate2.py`
- `scripts/run_co1_1_pilot.py`
- `scripts/run_co1_3_ab.py`
- `scripts/run_co1_4_host_probe.py`
- `scripts/run_co1_4_replace_probe.py`
- `../../experiments/co1-hook-only/plugins/hook-only-cost-probe/scripts/compensation_risk_gate.py`
- `../../experiments/co1-hook-only/plugins/hook-only-cost-probe/scripts/hook_probe.py`

私有原始会话保存在被 Git 忽略的 `.agent-token-manager/co1-3/` 与 `.agent-token-manager/co1-4b/`，不得为了整理报告而提交源码正文或完整 transcript。

## 可复现锚点

- M2d 冻结：`4af5900`
- CO-1.2 Gate：`b506818`
- CO-1.3 harness / results：`ebac9b6` / `d693547`
- CO-1.4 probe / experiment / matrix / results：`26e51d2` / `920a033` / `d4b0cf0` / `b75b434`
- CO-1.3 manifest hash：`badf98fba553ddcae46cf479b8c3120f340d906e7c168ea837ed15826bbd2b9d`
- CO-1.4b manifest hash：`7463921d7318ca0e26171d1b0eb08146bb2e6454e8b41f33f3b0a838c3132ed7`
- 真实模型实验：`gpt-5.6-sol`，reasoning `medium`
- 完整会话 Token：Codex 累计 usage；工具正文估算：`chars_div_4_v1`
- 最终记录版插件：`0.1.0+codex.20260816145422`
- 最终冻结 Git tag：`smart-read-frozen-2026-08`

## 后续方向

`ACP-0 — Agent Cost Profiler` 可作为独立的新里程碑研究已有的 100% Bash 观察能力，但它不是 Transparent Smart Read 的继续实现，也尚未开始。目标、验收标准、隐私边界和新对话交接入口已整理到 `ACP_0_IMPLEMENTATION_PLAN.md`，不能自动继承 CO 的产品承诺。

本报告和 `smart-read-frozen-2026-08` 是恢复现场的唯一入口。除非重新开启条件成立，否则本项目不再继续优化 Transparent Smart Read。
