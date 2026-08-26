# ACP-1.4C Validation Scope

- 状态：`COMPLETE — BASH COVERAGE REPAIRED / GENERALIZATION INSUFFICIENT under frozen experiment scope`
- 日期：2026-08-19
- Experiment：`acp1-4c-bash-requalification-v1`

ACP-1.4C 修复了 Bash benchmark 的代表性缺口，并完成新的 Read/Search/Bash 联合正式实验；它没有改写 ACP-1.4 的历史 `INSUFFICIENT_COVERAGE`。新联合 baseline 仍为 `INSUFFICIENT_COVERAGE`，但原因已从“没有合格 Bash case”转为“3 个 Read/Search Treatment 未达到冻结的 evidence activation Gate”。

## 审计与 qualification

- Bash v1 的失败来自题面尾随 `.` 被当作 argv，以及 read-only sandbox 无可写 tempfile；结论是 benchmark/runtime 不兼容，不是 Treatment failure。
- 旧 v1 case、0/2 qualified registry 和停止结论原样保留，未重评分。
- Bash v2：3 proposed，2 qualified，1 rejected。
- 两个 qualified case 均为 Native `10/10` completed、correct、candidate recurrence 与 dominant path。
- rejected case 虽为 `10/10` correct/path，但 candidate recurrence 为 `0/10`；未替换、未调 identity、未降低 Gate。

## Pilot 与 formal

```text
qualification       30 runs
pilot                4 runs (excluded from formal)
combined formal    160 runs
frozen chain       194 runs

formal cases         8
PASS                 5
FAIL                 0
INCONCLUSIVE         3
verdict       INSUFFICIENT_COVERAGE
```

家族结果：

- Bash：2/2 PASS；两个 Treatment 分别达到约 `38.73%` 与 `84.80%` evidence reduction；Control/Treatment correctness 均为 `10/10`，没有 path、cycle 或 success-semantics 退化。
- Read：2 PASS / 1 INCONCLUSIVE。
- Search：1 PASS / 2 INCONCLUSIVE。
- 三个 INCONCLUSIVE 都只因 evidence reduction median 低于预注册的 `35%`：约 `28.52%`、`5.68%`、`0.63%`；并非 correctness 或行为 Gate 失败。

## 允许与禁止的结论

允许说：Bash v2 benchmark 在冻结环境内可以稳定 qualification，两个 Bash prospective ablation case 均通过；当前 8-case baseline 中没有观察到行为失败，但只有 5 个 case 真正激活并通过 Treatment，因此尚不足以建立预注册意义上的跨家族泛化。

不得说：

- ACP 已证明可在 Read/Search/Bash 上普遍缩减 evidence；
- 未激活的 Treatment 等于安全或失败的 ablation；
- session Token 描述性差异等于全局节省率；
- 可以据此实现 production slicing、replacement 或实时推荐。

## 冻结边界

Collector 与 Hook hash 保持不变；ACP-1.4 的 frozen index/manifest 被作为 immutable upstream 绑定。公开 artifacts 不含原始回答、tool response 或用户绝对路径。任何后续工作必须建立新版本，不能覆盖本次 194-run chain。
