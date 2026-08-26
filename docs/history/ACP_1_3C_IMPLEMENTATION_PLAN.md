# ACP-1.3C 正式任务书：Prospective Natural Candidate Qualification

- 状态：`ACP-1.3C Prospective Natural Candidate Qualification — COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- 前置：ACP-1.3B `COMPLETE under synthetic frozen experiment scope`
- 目标输出：`natural-intervention-candidate-registry-v1`

## 目标

ACP-1.3C 只回答：在 Native-only 条件下，自然任务的 correctness、目标高成本 call 与执行路径是否足够稳定，可以进入未来受控消融。

```text
frozen natural task + Native-only ×20
                    ↓
correctness / candidate recurrence / path stability
                    ↓
natural-intervention-candidate-registry-v1
```

本阶段不创建 Treatment，不更改 evidence，不估计 avoidable cost。

## Prospective case set

从已审计的 ACP-0 自然任务中，根据旧 Native transcript 的大输出出现情况，在新数据生成前固定 4 个 prospective case：

- `natural_signature_limit_v1`：单文件定位；
- `natural_truncate_budget_v1`：大输出读取；
- `natural_command_shape_v1`：多文件定义搜索；
- `natural_navigation_counts_v1`：跨文件 reasoning。

旧 transcript 只用于 case design，不进入 ACP-1.3C 资格统计。正式资格数据全部为任务书冻结后的新 Native run。

## Candidate identity

identity 固定为 `explicit-command-terms-plus-result-size-v1`：

1. 仅使用 transcript 中已完成 tool call；
2. normalized command 必须包含 case 预注册的全部 ASCII case-folded terms；
3. model-visible tool result 至少 `4000 chars`，对应冻结 `chars_div_4_v1 >= 1000 Tokens`；
4. result 不得包含失败 envelope；
5. 单个 run 恰好有一个 match 才记为 recurrence；多个 match 记为 ambiguous，不任选一个；
6. public registry 只保留 identity definition hash 和 logical target ID，不保留 command/result body。

这个 identity 识别“同一逻辑 evidence 目标”，不要求字节级命令完全相同，也不用 timestamp 或结果相似度猜测。

## Path semantics

`candidate-relative-path-v1` 是每个 run 的有序序列：

```text
(tool family, first executable kind, candidate/noncandidate/ambiguous)
```

- 不包含完整命令、文件名或 result hash；
- dominant path 指 20 次中频数最高的完整序列；
- 并列最高频时 `dominant_path_status=ambiguous`，不选一个；
- path stability Gate 为唯一 dominant path 至少 `16/20`。

## 预注册资格条件

每个 case 固定 Native-only ×20，不删除任何已启动 run。

- completed with usage：`20/20`；
- correctness：`>=19/20`；
- candidate recurrence：`>=16/20`；
- ambiguous candidate identity：`0/20`；
- unique dominant path frequency：`>=16/20`；
- target call 的 evidence estimate 只报告 distribution，不设“越大越好”的 Gate。

## Registry classification

- `qualified`：全部资格条件通过；
- `diagnostic_only`：completed/correctness/identity/recurrence 通过，仅 dominant path 不稳定；
- `rejected`：其他任一硬条件失败。

ACP-1.3D 只能消费 registry 中的 `qualified` case/version，不得临时挑选 run 或改变 identity。

## Gate

1. **G1 Natural task**：使用真实仓库代码与已审计问题，不是 synthetic ledger。
2. **G2 Ground-truth audited**：题面、答案、scorer 和 subject revision 冻结。
3. **G3 Replay stability**：Native correctness 按 `19/20` 评估。
4. **G4 Candidate recurrence**：可靠 logical identity 按 `16/20` 评估。
5. **G5 Path stability**：dominant candidate-relative path 按 `16/20` 评估。
6. **G6 Privacy/provenance**：公开输出无 prompt/answer/command/result/session/path body，私有 run 进入 inventory chain。
7. **G7 Native-only/no intervention**：无 Treatment、Hook、collector、replacement 或 evidence 改写。
8. **G8 Frozen integrity**：ACP-0/1.0–1.3B frozen artifacts 不变。

## 实施顺序

- [x] 冻结 task set、identity、path semantics、threshold 和 classification。
- [x] 实现 Native-only runner、compact result 与 registry generator。
- [x] 每个 case 运行 20 次 Native qualification。
- [x] 按预注册规则生成 registry，不人工挑选。
- [x] 冻结 manifest/index，更新 PROJECT_PLAN 和 STATUS，运行全量验收。

## 冻结结果

- 4 个 case 各完成 20 次 Native-only run，`80/80` completed with usage，`80/80` correct，无 ambiguous candidate match。
- `natural_signature_limit_v1`：`qualified`；candidate recurrence `18/20`，dominant path `18/20`，target visible estimate median `2,046`。
- `natural_command_shape_v1`：`qualified`；candidate recurrence `20/20`，dominant path `18/20`，target visible estimate median `4,115`。
- `natural_truncate_budget_v1`：`diagnostic_only`；recurrence `19/20`，但 dominant path 只有 `13/20`。
- `natural_navigation_counts_v1`：`rejected`；recurrence 和 dominant path 都为 `13/20`，低于冻结 `16/20`。
- ACP-1.3D 仅允许消费上述两个 `qualified` case；不得使用 diagnostic/rejected run。
- index 为 `a4c599bd1084429a16cd6977d5128d1031d1fbaa03b907d26b329cbf1ce59090`，manifest 为 `ddf15adaa883a16e192d7c4e2a53ba3a7a7ba3d51ceb43b029d98a0ebac4a45c`。

正式数据前的首次 harness invocation 因 archive subject 不是 trusted Git directory 而产生 80 个 0-usage host refusal；这些没有进入模型，私有保留为 infrastructure diagnostic，未计入正式 80-run registry。修复只增加 `--skip-git-repo-check` 和汇总语法修正，fixture、题面、identity 与 Gate 未改变。

## 明确不做

- 不修改 collector 或 Hook chain；
- 不生成 Treatment，不做 source-level 缩减；
- 不输出 wasted/avoidable/potential-savings Token；
- 不把历史 5 candidates 补造成 replay case；
- 不重开 Transparent Smart Read。
