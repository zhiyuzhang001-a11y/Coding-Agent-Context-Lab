# ACP-1.4 Validation Scope

- 状态：`STOPPED — INSUFFICIENT_COVERAGE under frozen experiment scope`
- 日期：2026-08-18
- Experiment：`acp1-4-natural-ablation-generalization-v1`
- Qualification：`resources/acp1_4a_results.json`
- Registry：`resources/acp1_4a_candidate_registry.json`
- Family pilot：`resources/acp1_4b_pilot_results.json`

ACP-1.4 的 sampling frame、Treatment、qualification Gate 与 generalization verdict 在新数据前冻结。结果没有满足跨 Read/Search/Bash 的 formal coverage Gate，因此按预注册规则停止，没有运行 ACP-1.4B formal，也没有用新任务替换失败的 Bash case。

## Qualification funnel

```text
proposed                 8
native-qualified         6
rejected                 2
formal coverage gate  FAIL
formal cases run         0
generalization verdict   INSUFFICIENT_COVERAGE
```

家族结果：

- Read：3 proposed / 3 qualified；
- Search：3 proposed / 3 qualified；
- Bash：2 proposed / 0 qualified。

全部 Read/Search case 均为 Native `10/10` completed、correct、candidate recurrence 与 dominant path。两个 Bash case 均为 `10/10` completed，但 correctness `0/10`、candidate recurrence `5/10`、dominant path `5/10`，因此被拒绝而不是降阈值。

## Family pilot

- Read representative：全部 plumbing checks 通过，evidence reduction `60.096444%`；
- Search representative：全部 plumbing checks 通过，evidence reduction `44.117647%`；
- Bash：没有 qualified representative，明确为 missing/fail；
- pilot 4 runs 不进入正式统计，状态为 `inconclusive_plumbing`。

## 允许与禁止的结论

允许说：冻结任务集显示 Read/Search 的 Native qualification 与 family-level intervention plumbing 可行，但没有 Bash coverage，因此 ACP-1.4 没有建立跨工具家族的 generalization evidence。

不得说：

- 1.3D 正结果已经推广到 Read/Search/Bash；
- Read/Search pilot 等于多案例 formal causal validation；
- Bash evidence 不可缩减——这里只证明这两个 Native benchmark 不合格；
- ACP 可在线或生产缩减 evidence；
- 存在任何全局节省比例。

## 基础设施 preflight

首次沙箱内启动产生 2 个 240 秒 timeout，第三个在故障确认后中断；最小探针证明 DNS/WebSocket/HTTPS 均被沙箱网络限制阻断。该 epoch 没有完成模型响应，也未查看任务答案/correctness，作为 aborted preflight 保留，不进入 80-run qualification。恢复时 model、effort、spec、runner、Treatment 和 Gate 均未改变。

## 重新开放条件

下一版本若要补足 Bash coverage，必须作为新的 prospective sampling frame：先审计 Bash 题面和 Native 命令语义，再冻结新的 case/version，并完整报告旧 0/2 attrition。不得向本次 registry 追加替代 case，也不得覆盖 `INSUFFICIENT_COVERAGE` 结论。
