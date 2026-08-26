# ACP-1.4E Validation Scope

- 状态：`COMPLETE — ACTIVATION_RESOLVED under frozen v2 experiment scope`
- 日期：2026-08-19
- Offline：3 cases / 0 Agent runs
- Native qualification：30 runs
- Pilot：6 runs，排除于正式统计
- Formal：60 runs

ACP-1.4E 只验证 ACP-1.4D 准入的三个 prospective v2 Treatment。它证明这些 versioned rule 能在三个冻结自然任务上稳定形成强 intervention，同时保持 correctness、tool path、model cycles 与 success semantics；它没有重写 v1 的三个 INCONCLUSIVE，也没有建立跨 Read/Search/Bash 的全局泛化。

## Qualification 与 pilot

- 三个 v2 case 均为 Native `10/10` completed、correct、candidate recurrence、dominant path；ambiguous `0/10`。
- Native target evidence 分别固定为 824、168、2,393 estimated Tokens；token-router 已脱离旧的 host truncation 区。
- pilot 三个 case 均通过，reduction 分别为 `81.310680%`、`76.190476%`、`98.579189%`；pilot 6 run 不进入 formal。

## Formal

三个 case 均为：

- Control/Treatment `10/10` correct；
- candidate recurrence `10/10` vs `10/10`；
- Treatment-only failure `0`；
- tool-call 与 cycle paired median delta `0`；
- 无新的 repeated compensation path；
- G1–G8 全通过。

正式 activation：

- `read_context_router_limit_v2`：`81.310680%`；
- `search_budget_stop_v2`：`76.190476%`；
- `search_token_router_v2`：`98.579189%`。

Session pooled ratio `0.980305 / 0.997374 / 0.940595` 只作三个 frozen case 的描述；它不是全局节省估计，也不是本阶段 PASS 的必要条件。

## 允许与禁止的结论

允许说：1.4D 定位的三个 activation blocker 在预注册 v2 rule 下得到 case-specific causal resolution；强 intervention 可以在这三个任务中形成，且未观察到冻结 Gate 所定义的行为退化。

不得说：

- ACP 已建立跨工具家族或一般 Agent 任务的缩减泛化；
- 这些 source-level Treatment 可以直接部署为 production slicing/replacement；
- session ratio 是产品节省承诺；
- v1 INCONCLUSIVE 已被重评分为 PASS。

任何 combined generalization 更新必须另立 prospective baseline，不能把本次三个 v2 case 与旧 case 临时拼接后宣称总体通过。

## Qualification 汇总 plumbing 记录

30/30 Native run 完成后、查看任何 case 结果之前，首次汇总暴露两个旧 aggregator 字段名不匹配：`completed_with_usage_required`/`dominant_path_min` 应为 `completed_with_usage`/`dominant_path_frequency_min`。只修正了键名，冻结数值仍为 10/10 与 8/10；随后以 `--resume` 聚合同一批 30 个 result，没有新增或重跑模型会话。该 plumbing 修正不改变 Treatment、prompt 或 Gate 语义。
