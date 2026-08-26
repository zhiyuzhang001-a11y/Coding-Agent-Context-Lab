# ACP-1.4C 正式任务书：Bash Benchmark Audit & Requalification

- 状态：`COMPLETE — BASH COVERAGE REPAIRED / GENERALIZATION INSUFFICIENT under frozen experiment scope`
- 日期：2026-08-19
- 前置：ACP-1.4 `STOPPED — INSUFFICIENT_COVERAGE`
- 范围：只修复 Bash benchmark coverage；不改写 ACP-1.4 历史，不修改 Read/Search case 或 Treatment

## v1 审计结论

旧 Bash v1 两个 case 的 `0/10 correctness` 来自 benchmark/runtime 不兼容：

1. 题面将句号紧跟在命令后，5/10 run 把 `.` 作为 unittest argv，结果为 `Ran 0 tests / NO TESTS RAN`；
2. 其余 run 正确执行 unittest，但冻结的 read-only sandbox 不提供可写 tempfile，测试以 `No usable temporary directory` 失败；
3. 因此 candidate recurrence/path 恰为 `5/10`，反映两种失败命令路径，不是 Treatment effect。

旧 case、旧 registry 与 ACP-1.4 `INSUFFICIENT_COVERAGE` 永久保留，不重评分。

## Bash v2 prospective sampling frame

所有命令均置于独立代码块语义中；句号不属于 argv。命令只读、无需 tempfile/cache/`__pycache__`。

- `bash_json_gate2_status_v2`：`python3 -m json.tool` 读取 CO-1 Gate 2 结果，唯一答案为顶层 `status`；Treatment 保留前三个 `pairs`。
- `bash_json_cost_schema_title_v2`：`python3 -m json.tool` 读取成本归因 schema，唯一答案为顶层 `title`；Treatment 将 `properties` 确定投影为两个冻结 key。
- `bash_python_schema_scan_v2`：`python3 -c` 确定性扫描所有脚本的 `schema_version` 行；唯一答案来自被完整保留的 `navigation_contract.py`；Treatment 只消融其他文件中 hash 选中的匹配行。

## Native qualification

- 每 case Native ×10，共 30 runs；
- completed with usage `10/10`；correct `>=9/10`；candidate recurrence `>=8/10`；ambiguous `=0`；dominant path `>=8/10`；
- 至少 2 个 Bash v2 case qualified 才允许恢复 formal；未通过者永久保留，不替换、不降 Gate。

## 恢复 formal 的条件

若至少 2 个 Bash v2 qualified：

1. 每个新 Treatment family 做 plumbing pilot；
2. pilot 通过后，新的 combined prospective baseline 消费 ACP-1.4 已 qualified 的 6 个 Read/Search case，以及全部 Bash v2 qualified case；
3. 每 case Control ×10 + Treatment ×10，AB/BA 平衡；
4. case Gate 沿用 ACP-1.4：evidence reduction median `>=35%`、correctness non-inferiority、path/cycle 不恶化、success semantics、完整样本与 no-overclaim；
5. 跨家族结论继续使用 `SUPPORTED_WITH_BOUNDARIES / MIXED / NOT_SUPPORTED / INSUFFICIENT_COVERAGE`。

## 实施顺序

- [x] 冻结 v1 审计结论与 v2 sampling frame。
- [x] 实现 v2 JSON/source Treatment 与合同测试。
- [x] 执行 30-run Native qualification，冻结 Bash v2 registry：2 qualified / 1 rejected。
- [x] 执行 4-run pilot 与 160-run combined formal。
- [x] 冻结 194-run artifact chain，更新 PROJECT_PLAN/STATUS，全量验收。

## 冻结结果

- Bash v2 formal：2/2 PASS；两臂 correctness 均为 10/10，path/cycle/success semantics Gate 全通过。
- 联合 8-case baseline：5 PASS / 0 FAIL / 3 INCONCLUSIVE。
- 3 个 INCONCLUSIVE 只因 Treatment evidence reduction 未达到冻结的 35% activation Gate；没有 behavioral failure。
- 最终 verdict：`INSUFFICIENT_COVERAGE`。Bash coverage 已修复，但当前 Treatment 设计尚未在全部 frozen case 上充分激活，因此不声明跨家族泛化。
- 详细适用范围见 `ACP_1_4C_VALIDATION_SCOPE.md`。

## 禁止事项

- 不修改/删除 Bash v1 失败；
- 不降低 correctness/recurrence/path/activation Gate；
- 不让 Read/Search 结果替 Bash 提供证据；
- 不实现 production slicing/replacement/实时推荐；
- 不输出全局节省比例。
