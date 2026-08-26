# ACP-1.4D 正式任务书：Read/Search Treatment Activation Audit

- 状态：`COMPLETE under frozen audit scope`
- 日期：2026-08-19
- 前置：ACP-1.4C `BASH COVERAGE REPAIRED / GENERALIZATION INSUFFICIENT`
- 范围：只审计三个既有 INCONCLUSIVE case；不运行新 intervention，不改写 1.4/1.4C

## 目标

解释以下冻结 activation reduction 为何低于 `35%`：

- `read_context_router_limit_v1`：`28.519417%`
- `search_budget_stop_v1`：`5.679012%`
- `search_token_router_v1`：`0.628088%`

审计区分三层：Treatment 在 source 上实际改变了什么；host/model-visible evidence 中哪些部分被保留或截断；冻结 `candidate_visible_estimated_tokens` 分母如何得到。审计不重新解释 session usage，也不把 source deletion 当作 model-visible reduction。

## 冻结分类

每个 case 只能得到一个 primary classification：

- `RULE_MISMATCH`：规则过宽保留或只命中很小的可删区域；
- `FIXED_STRUCTURE_DOMINATED`：必要/固定结构已占据分母主体，当前规则没有足够空间；
- `MEASUREMENT_MISMATCH`：source-side action 与 model-visible denominator 之间存在截断、饱和或其他不可直接对应关系；
- `LIMITED_SAFE_REDUCTION`：在现有客观语义边界内没有 35% 安全空间；
- `INCONCLUSIVE`：现有 artifact 不足以判定。

`v2_eligibility` 独立记录。只有存在确定性、单变量且不依赖结果调参的 prospective rule 时，才允许标记 `eligible_after_preregistration`；这不等于 v2 已通过。

## Gate

1. 只消费 ACP-1.4C frozen formal chain 和冻结 spec；不重跑 Agent。
2. 35% activation Gate 原样保留，三个 verdict 仍为 INCONCLUSIVE。
3. 对 source change、command scope、host truncation 与 visible denominator 分层记账。
4. raw answer、raw tool output、绝对路径和原始命令不得进入公开 artifact。
5. 相同 frozen inputs 生成相同 canonical audit/hash。
6. 不修改 collector、Hook、ACP-1.4/1.4C artifacts。
7. 不实现 production slicing/replacement/实时推荐，不输出全局节省比例。

## 实施顺序

- [x] 冻结审计范围、分类与 Gate。
- [x] 实现只读 activation ledger 与 traceability。
- [x] 对三个 case 生成分类和 v2 eligibility。
- [x] 冻结 audit/index/manifest 并添加合同测试。
- [x] 更新 PROJECT_PLAN/STATUS，执行全量验收。

## 冻结结果

- `read_context_router_limit_v1`：`RULE_MISMATCH / eligible_after_preregistration`；70/93 行 prefix 保留过宽。
- `search_budget_stop_v1`：`RULE_MISMATCH / eligible_after_preregistration`；whole-file exemption 占 Control 可见字符约 73.75%，Treatment 只改变 1 行。
- `search_token_router_v1`：`MEASUREMENT_MISMATCH / eligible_after_preregistration_with_censoring_control`；每次改变 81 文件/456 行，但两臂 20/20 都被 host 截断，visible denominator 饱和。
- 没有新 Agent run；三个历史 verdict、35% Gate、1.4C formal result 与 collector/Hook 均未改变。

## 停止点

ACP-1.4D 结束于审计结论与 prospective eligibility。任何 v2 task prompt、Treatment 或正式运行必须另立版本、重新预注册并先做 Native qualification；不得把本阶段的离线设计建议混入 1.4C 正式统计。
