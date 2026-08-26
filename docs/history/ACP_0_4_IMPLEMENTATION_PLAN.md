# ACP-0.4 正式任务书：No-Interference Graduation Gate

- 状态：`FAILED_COST_NEUTRALITY`
- 日期：2026-08-17
- 结果记录版：`0.1.0+codex.20260817162046`
- 在线被测对象：冻结 `acp-collector-v0.1`
- 离线对象：Normalizer / Correlator / Coverage Ledger / Fact Reporter
- 输出合同：`acp0-4-no-interference-v1`
- 非目标：新 profiler 功能、replacement、slicing、实时 recommendation、waste/avoidable 判定、ACP-1 分析

## 核心问题

> 打开 ACP measurement stack，会不会改变 Agent 原本的行为和成本？

在线干预面只有 observe-only collector。Normalizer、Correlator、Ledger 和 Reporter 在任务结束后离线运行，不进入 Agent loop。ACP-0.4 不把离线计算伪装成在线开销。

## 两层验证

### A. Deterministic host hard gates

- collector 进程始终成功退出且 stdout/stderr 为空；
- controlled tool result 的 OFF/ON/recorded SHA-256 一致；
- unknown tool、缺失 metadata、malformed JSON 和 audit 不可写全部 fail-open；
- Hook manifest 不加载 optimizer、rewrite、Skill、App、MCP 或 reporter。

任一失败即 Gate fail。

### B. Natural paired observations

固定 12 个自然只读任务，覆盖 single-file、multi-file search、Bash/tests、debugging、cross-file reasoning、large output 和 tool failure。每个任务在同一 subject commit、独立 detached worktree、独立 CODEX_HOME 下运行 OFF/ON；顺序为 6 个 AB 和 6 个 BA。

硬门：

- 任一 OFF/ON correctness 不成立即失败；
- collector 自身发起工具调用即失败；
- controlled host result hash 改变即失败。

统计门：

- model-cycle delta 中位数不大于 0，正向任务不超过半数；
- tool-call delta 中位数不大于 0，正向任务不超过半数；
-完整 session Token 的 paired median ratio 与 pooled ratio 均不超过冻结上限 `1.02`。

自然 Agent 有随机性，因此逐任务调用序列和 result 序列只做观察，不作为硬门；不得把单对差异直接归因于 collector。所有 Token 差异必须完整记录，不静默忽略。

## 冻结与可复现

- Runner 运行时从 ACP contract 读取 collector hash，复制冻结字节到最小测试插件并再次校验 SHA-256。
- ON 插件只含 plugin manifest、PostToolUse manifest 和 collector；无默认 prompt、Skill、MCP、App、optimizer 或 rewrite Hook。
- 原始 Codex JSONL、stderr、collector events、逐场结果和 summary 保存在私有、Git ignored artifact 目录。
- `resources/acp0_4_cases.json` 冻结任务、expected、AB/BA 顺序、subject commit 和阈值。

## Gate

- G1 Isolation：在线路径只有冻结 collector。
- G2 Host transparency：result hash、stdout/stderr 和工具状态不变。
- G3 Fail-open：故障注入不终止或改变宿主工具流程。
- G4 Correctness：12 个 OFF/ON pair 均正确。
- G5 Behavioral neutrality：cycle/call 无系统性增量。
- G6 Cost neutrality：paired median 与 pooled session Token ratio 均不超过 1.02。
- G7 Reproducibility：commit、collector、manifest、model、reasoning、usage source 与逐场 artifact 完整记录。

## 停止条件

G1–G7 全部通过后，冻结 `ACP-0 Measurement Foundation — COMPLETE` 并停止扩展 ACP-0。若失败，则保持 ACP-0.4 failed/blocked，不能用提高阈值、删除不利 pair 或填补 unknown 的方式通过。

## 执行结果（2026-08-17）

正式证据集：`.agent-token-manager/acp0-4-natural-20260817-run7`；摘要冻结为 `resources/acp0_4_results.json`。

- [x] G1 Isolation：ON 最小插件逐字复制冻结 collector 与 Hook manifest；16 个 ON tool calls 记录 16 个 collector events。
- [x] G2 Host transparency：controlled OFF/ON/recorded result SHA-256 一致，collector stdout/stderr 均为空。
- [x] G3 Fail-open：unknown tool、缺 metadata、malformed JSON、audit 不可写均成功退出且无输出。
- [x] G4 Correctness：12/12 OFF 与 12/12 ON 均正确。
- [x] G5 Behavioral neutrality：cycle delta 中位数 0（1 lower / 10 equal / 1 higher）；tool-call delta 同样为 0（1/10/1）。
- [ ] G6 Cost neutrality：paired median ratio `0.999586` 通过，但 pooled ratio `1.027420` 超过冻结上限 `1.02`，因此失败。
- [x] G7 Reproducibility：subject/harness commit、model、reasoning、manifest/collector/hooks hashes、usage source 和逐场私有 artifact 已记录。

最大正向 pair 为 `debug_dynamic_join`：OFF 在无工具调用下正确回答，ON 使用 2 个工具调用后正确回答，完整 session Token 为 15,407→47,622（+32,215）。这是自然行为差异，不能单对归因给 collector；但冻结 pooled Gate 不允许删除或忽略它。

无效预运行 run2–run6 只用于修复 harness：分别暴露 Git worktree sandbox、非 ASCII 继承环境、未激活 Hook 和 read-only `py_compile` oracle 问题，均未作为正式 Gate 证据。run7 在 Hook 实际激活硬门加入后从头运行全部 24 场。

结论：ACP-0.4 已实施但未通过，`ACP-0 Measurement Foundation` 不标记 COMPLETE，不进入 ACP-1。若未来复验，必须新建预注册协议；不得重跑或删除单个不利 pair 来改写本次结论。
