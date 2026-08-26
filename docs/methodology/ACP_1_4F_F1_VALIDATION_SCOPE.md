# ACP-1.4F-1 Validation Scope

状态：`STOPPED — INSUFFICIENT_NATIVE_COVERAGE under frozen v2.1 scope`

日期：2026-08-19

## 结论

ACP-1.4F-1 没有进入 F-2。冻结的 Native coverage Gate 已数学上不可能满足：Read 最多 1 个 qualified，Search 最多 2 个 qualified，均低于每 family 至少 3 个的要求。

这不是 correctness 失败。54 个 completed runs 全部回答正确；失败来自 Native tool-path stability 与冻结 candidate identity 的 recurrence。

## 冻结运行范围

- 计划：12 case ×10，共 120 Native runs；
- attempted：55；
- completed and retained：54；
- interrupted at Gate stop：1；
- not started：65；
- Treatment builder、collector、Hook、intervention：全部未使用。

Read 的 40 个 runs 全部 correct 且 recurrence 10/10，但四 case dominant path 分别为 `9/10、7/10、5/10、5/10`。只有第一个达到 `>=8/10`。

Search 首个 case 为 10/10 correct、2/10 recurrence；第二个 case 在 4/4 correct、0/4 recurrence 后已经无法达到 8/10，因此停止。

## 客观解释边界

停止后的只读样本审计显示，自然 Search 命令经常用 `.` 表示 scope，而冻结 identity 要求命令重复 project-form term。该事实可以解释一部分 non-recurrence，但不能用于当前版本重分类或修改阈值。

当前证据只支持：

> 这组 v2.1 benchmark/identity 在 Native 条件下不足以形成预注册的跨 family causal experiment cohort。

它不支持：

- Treatment 无效；
- evidence reduction 不安全；
- Agent correctness 不稳定；
- 存在或不存在全局可节省 Token；
- production slicing/replacement/recommendation 可以启动。

## Process deviation

runner 只在正常结束时汇总 dominant path，导致 Read-family impossibility 在 run 40 已可判断、实际在 run 54 才人工停止。额外 14 个 completed runs 不删除、不选择性使用；deviation 不改变 coverage verdict，但 `v2.1` 不得恢复。

## 冻结证据

- `resources/acp1_4f_f1_early_stop.json`
- `resources/acp1_4f_f1_frozen_early_stop_index.json`
- private completed-result inventory：54 runs，公开只保存 logical ID 与 digest，不保存路径或正文。

F-2、pilot 与 formal 均未授权。任何后续尝试必须建立新版本并重新预注册，不得复用 v2.1 runs 作为新版本的正式统计样本。

验收：F-0/F-1 定向 `21/21 PASS`；项目全量 `417/417 PASS`。
