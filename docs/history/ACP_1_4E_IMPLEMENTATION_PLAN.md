# ACP-1.4E 正式任务书：Prospective v2 Treatment Validation

- 状态：`COMPLETE — ACTIVATION_RESOLVED under frozen v2 experiment scope`
- 日期：2026-08-19
- 前置：ACP-1.4D `COMPLETE under frozen audit scope`
- 范围：只验证 1.4D 准入的三个 versioned v2 case；不覆盖 v1，不宣称全局泛化

## 目标

为三个历史 activation blocker 预注册单变量、确定性的 v2 Treatment，并按以下顺序验证：

1. 离线 activation preflight；
2. 每 case Native ×10 qualification；
3. 每 case Control/Treatment plumbing pilot；
4. 只有 3/3 qualified 且 3/3 pilot 通过，才运行每 case Control/Treatment 各 10 次 formal。

## v2 设计

- `read_context_router_limit_v2`：任务命令保持宽 read，Treatment 从 70-line prefix 收紧为 24-line prefix；目标声明仍完整保留。
- `search_budget_stop_v2`：命令 scope 明确且禁止附加参数；Treatment 不再豁免整个目标文件，只保留第一个客观 assignment match。
- `search_token_router_v2`：命令只包含三个明确文件且禁止附加 root scope；Treatment 只保留目标常量行，必须先证明 Control 输出未进入 host truncation 区。

## Gate

### Offline

- 三个 Treatment 均为 deterministic、single-variable；
- evidence reduction `>=35%`；
- Control/Treatment 输出均包含唯一答案证据；
- token-router Control/Treatment 均低于预注册 censoring ceiling；
- 不运行 Agent，不修改 frozen artifact。

### Native qualification

- 每 case `10/10` completed with usage；correct `>=9/10`；candidate recurrence `>=8/10`；ambiguous `=0`；dominant path `>=8/10`；
- 必须 3/3 qualified 才允许 pilot/formal，不替换失败 case、不降 Gate。

### Formal

- 每 case Control/Treatment 各 10 次，AB/BA 平衡；
- activation median `>=35%`；accuracy delta `>=-0.10`；Treatment-only failure `=0`；
- tool-call/cycle median delta `<=0`；无重复出现的新 compensation path；success semantics 与完整样本通过；
- session usage 只有行为 Gate 全过后才作 case-specific 描述；不形成全局 savings claim。

## 实施顺序

- [x] 冻结 v2 case、Treatment 与 Gate。
- [x] 实现 runner、offline preflight 与合同测试。
- [x] 执行 30-run Native qualification 并冻结 registry：3/3 qualified。
- [x] 执行 6-run pilot 与 60-run formal：3/3 PASS。
- [x] 冻结 96-run artifact chain，更新 PROJECT_PLAN/STATUS，全量验收。

## 冻结结果

- Offline reduction：`82.563155% / 81.832797% / 99.065322%`，token-router 低于 censoring ceiling。
- Native：三个 case 均 10/10 correct/recurrence/path，ambiguous=0。
- Pilot：`81.310680% / 76.190476% / 98.579189%`，排除于 formal。
- Formal：三个 case 均 Control/Treatment 10/10 correct，activation 与 G1–G8 全通过；tool/cycle median delta=0，无新 compensation path。
- Verdict：`ACTIVATION_RESOLVED`，仅限三个 frozen v2 case；不构成 combined/global generalization。

## 禁止事项

- 不修改 v1 prompt/Treatment/result/verdict；
- 不放宽 35% Gate；
- 不从 pilot 调参；
- 不只补跑失败样本或删除 outlier；
- 不实现 production slicing/replacement/实时 recommendation；
- 不将三个 v2 case 外推为 Read/Search/Bash 全局泛化。
