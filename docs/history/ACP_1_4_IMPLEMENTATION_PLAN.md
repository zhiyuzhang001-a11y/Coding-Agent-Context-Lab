# ACP-1.4 正式任务书：Natural Ablation Generalization

- 状态：`STOPPED — INSUFFICIENT_COVERAGE under frozen experiment scope`
- 日期：2026-08-18
- 前置：ACP-1.3D `COMPLETE under frozen experiment scope`
- 目标：prospective 验证 behavior-preserving evidence ablation 是否可跨自然任务、工具家族和 evidence 形态重复成立

## 阶段结构

### ACP-1.4A — Prospective Natural Task Qualification

- 在任何新 run 前冻结 8 个全新任务：Read 3、Search 3、Bash 2；
- 每 case Native ×10；要求 completed with usage `10/10`、correct `>=9/10`、candidate recurrence `>=8/10`、ambiguous `=0`、dominant path `>=8/10`；
- 全部 proposed case 都进入 qualification registry；未通过者保留为 diagnostic/rejected/unsupported，不替换；
- 至少 6 个 qualified，且 Read/Search/Bash 各至少 2 个 qualified，才满足 formal generalization coverage。

### ACP-1.4B — Multi-Case Ablation Generalization

- 所有且仅有 1.4A qualified case 进入 formal；
- 每 case Control ×10 + Treatment ×10，10 个 AB/BA 平衡 block；
- Pilot 每个 Treatment family 只做一对 plumbing run，pilot 不进入 formal；
- case Gate 沿用 1.3D：activation、correctness、path、cycle、success semantics、completeness、no-overclaim；
- 正式 threshold：Control/Tx correct `>=9/10`、accuracy delta `>=-0.10`、Tx-only failure `<=1`、两臂 recurrence `>=8/10`、path retention delta `>=-0.10`、tool/cycle delta median `<=0`、evidence reduction median `>=35%`。

## 冻结 sampling frame

| 家族 | Case | Evidence / Treatment |
|---|---|---|
| Read | `read_navigation_schema_v1` | 读取 navigation contract；保留前 70 行 |
| Read | `read_context_router_limit_v1` | 读取 router 常量；保留前 70 行 |
| Read | `read_workspace_database_v1` | 读取 workspace storage 常量；保留前 75 行 |
| Search | `search_schema_version_v1` | 广域 schema search；保留 navigation contract，确定性消融其他匹配行 |
| Search | `search_budget_stop_v1` | 广域 stop-reason search；保留 task navigator，确定性消融其他匹配行 |
| Search | `search_token_router_v1` | 三文件 token search；保留 context router，确定性消融其他匹配行 |
| Bash | `bash_task_navigator_tests_v1` | verbose unittest evidence；确定性保留约半数 test methods |
| Bash | `bash_m2e_calibration_tests_v1` | verbose unittest evidence；确定性保留约半数 test methods |

每个 Treatment 只修改 materialized frozen subject 的实验副本；prompt、expected answer、命令要求、model、sandbox 和 scorer 不变。

## Qualification funnel

必须完整报告：

```text
proposed → native-qualified → treatment-activated → PASS / FAIL / INCONCLUSIVE
```

不得删除或替换未 qualified、未 activation、失败或离群 case。

## Generalization verdict

- `SUPPORTED_WITH_BOUNDARIES`：至少 6 qualified；每家族至少 2 qualified；全部 qualified 均正式运行；case PASS rate `>=0.70`；每家族至少 1 PASS。
- `MIXED`：formal 完整且至少一个 PASS，但不满足上述支持条件。
- `NOT_SUPPORTED`：formal 完整且无 PASS，或 FAIL 占 qualified case 的多数。
- `INSUFFICIENT_COVERAGE`：qualification coverage 不足、qualified case 未全部运行，或 host/identity/completeness 阻断。

跨 case 主结论只报告漏斗、case verdict 和 family coverage；不把 Token 简单平均成产品节省率。

## 实施顺序

- [x] 冻结 sampling frame、Treatment families、qualification/final Gate 与总体 verdict。
- [x] 实现统一 1.4A/1.4B runner 与离线合同测试。
- [x] 执行 80-run Native qualification，冻结完整 registry。
- [停止] family pilot 中 Read/Search 通过、Bash 无 qualified representative；formal AB/BA 按 Gate 未启动。
- [x] 冻结 result/index/manifest，更新 PROJECT_PLAN/STATUS 并全量验收。

## 正式结论

- qualification：8 proposed → 6 qualified → 2 rejected；
- Read `3/3`、Search `3/3` qualified；Bash `0/2` qualified；
- 两个 Bash case 虽 10/10 completed，但 correctness 均为 `0/10`，recurrence/path 均为 `5/10`，不允许进入 Treatment；
- family pilot：Read evidence reduction `60.096444%`、Search `44.117647%`，两者 plumbing checks 全过；Bash missing；
- generalization verdict：`INSUFFICIENT_COVERAGE`；formal run count：0；
- index：`67eccea11c5488c6f2d225353506e9c5be3f8dcc269905d291d307fbebd70876`；
- manifest：`5716bd57de9d575088b32ae0608dc6be73f8d7705b7ad44e9d3954cb43a76419`。

本阶段没有证明跨工具家族 generalization。Read/Search pilot 也不是多案例 formal causal validation。详见 `ACP_1_4_VALIDATION_SCOPE.md`。

## 明确不做

- 不实现 online/production slicing、replacement 或实时 recommendation；
- 不重开 Transparent Smart Read Host rewrite；
- 不按 pilot/formal 结果修改 Treatment 或阈值；
- 不排除 FAIL/INCONCLUSIVE case；
- 不输出全局“可节省 X%”结论；
- 不让 ACP-2 policy 在本阶段参与 case 选择。
