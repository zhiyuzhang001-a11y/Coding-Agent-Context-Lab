# ACP-1.3D 正式任务书：Candidate-Specific Controlled Ablation

- 状态：`COMPLETE under frozen experiment scope`
- 日期：2026-08-18
- 前置：ACP-1.3C `COMPLETE under frozen experiment scope`
- 目标：在两个 qualified natural case 上验证确定性 source-level evidence ablation 是否保持任务行为

## 范围与资格

ACP-1.3D 只允许：

- `natural_signature_limit_v1`；
- `natural_command_shape_v1`。

`natural_truncate_budget_v1` 为 diagnostic-only，`natural_navigation_counts_v1` 已 rejected，两者不得进入 pilot 或 formal run。历史 ACP-1.2 candidates 仍不补造 replay。

## 单变量 Treatment

Control 使用冻结 subject commit 的原始源树。Treatment 使用同一 commit 的确定性 source projection；prompt、ground truth、model、reasoning effort、tool binary、sandbox 和 scorer 不变。

### signature case

- 只修改 `smart_read.py` 的实验副本；
- 保留原文前 100 行，删除之后的 evidence source；
- `signature_from_content` 的完整定义、题面所需常量与行序保留；
- 不改 prompt、命令或工具退出语义。

### command-shape case

- 完整保留 `run_co1_gate2.py`；
- 对其他 UTF-8 文本文件中含 `command_shape` / `CO-1` / `Gate 2` 的行，以 `sha256(repo-relative-path + ':' + one-based-line)` 的奇偶性决定是否将这三个 search term 替换为不匹配占位符；
- 仅当 digest 的第一字节为偶数时替换，因此为固定约 50% 的非目标 search-evidence ablation；
- 不改目标定义文件或 shell tool。

Treatment 是离线实验 source fixture，不是 production slicing/replacement。

## Logical candidate identity

1.3D 将 identity 与 high-cost qualification 分开：

```text
logical candidate = frozen command terms + logical target + normal success envelope
high-cost qualification = 1.3C result >= 4000 chars
treatment activation = same logical candidate + changed result hash + evidence reduction >= 35%
```

Treatment 成功变小后不再受 4000-char 下限限制。单 run 多个 logical match 仍记 ambiguous，不任选。

## Pilot

- 每 case 只运行 1 Control + 1 Treatment；
- 只验证两臂正常退出、logical identity 唯一、Treatment hash 改变且 evidence reduction `>=35%`、scorer/transcript/usage 可用；
- pilot 数据不进入正式统计，不用于修改 Treatment 或 Gate；
- pilot 不通过则停止为 `INCONCLUSIVE_PLUMBING`。

## Formal design

- 每 case Control ×20 + Treatment ×20，共 80 runs；
- 20 个 block 采用 AB/BA 交替：奇数 block `Control→Treatment`，偶数 block `Treatment→Control`；
- 每 run 使用 fresh Codex home 与 fresh frozen source tree；
- 不补跑失败样本，不删除 outlier，不混入 pilot。

## 预注册 Gate（每 case 单独计算）

1. **G1 Eligibility**：case/version 必须在 ACP-1.3C registry 中为 qualified。
2. **G2 Activation**：20/20 Treatment 有唯一 logical candidate；paired target evidence median reduction `>=35%`，且 Control/Treatment result hash 不同。
3. **G3 Correctness**：Control `>=19/20`，Treatment `>=19/20`，`AccuracyTx-AccuracyControl >= -0.05`，Treatment-only failure `<=1`。
4. **G4 Tool path**：相对 1.3C frozen dominant-path 的 Tx retention 比 Control 降低不超过 `0.10`；两臂 target recurrence 均 `>=16/20`；paired median tool-call delta `<=0`；不存在 Tx-only 且频数 `>=4` 的新 compensation path。
5. **G5 Cycle**：paired model-cycle delta median `<=0`。
6. **G6 Success semantics**：两臂所有唯一 target call 均为正常成功 envelope，无 `Script failed/error`。
7. **G7 Outcome completeness**：40/40 formal runs completed with usage，全部 block 与 run order 保留。
8. **G8 No overclaim/frozen integrity**：不修改 collector/Hook/ACP-1.3C registry，不产生全局 savings 结论。

## Verdict 与 cost effect

- `PASS`：G1–G8 全部通过；
- `FAIL`：G2 activation 通过，但任一 behavior Gate G3–G6 失败；
- `INCONCLUSIVE`：activation、completeness、host/environment 或 identity 无法验证。

Session-cost effect 与 behavior verdict 分开，仅在 G2–G7 通过后解释：

- `observed_reduction`：pooled ratio `<0.98` 且 paired median delta `<0`；
- `neutral`：pooled ratio 在 `[0.98, 1.02]`；
- `observed_increase`：pooled ratio `>1.02` 且 paired median delta `>0`；
- 其他为 `inconclusive`。

即使 PASS，也只能说“该 frozen case 与 Treatment 下存在 experimentally supported potentially avoidable observed evidence volume”；不等于端到端 savings。

## 实施顺序

- [x] 冻结 eligible cases、Treatment、identity、schedule、Gate 与 verdict。
- [x] 实现 deterministic source projection 和 pilot/formal runner。
- [x] 运行 4-run plumbing pilot；通过后才运行 formal 80 runs。
- [x] 生成每 case behavior verdict 与独立 session-cost effect。
- [x] 冻结 result/index/manifest，更新 PROJECT_PLAN 与 STATUS，全量验收。

## 正式结果

- Pilot 4/4 通过且未进入正式统计；formal 80/80 完成；
- 两个 qualified case 的 Control/Treatment correctness 均为 `20/20`，G1–G8 全部通过，verdict 均为 `PASS`；
- `natural_signature_limit_v1` 的 evidence reduction median 为 `62.609971%`，session pooled ratio 为 `0.967792`；
- `natural_command_shape_v1` 的 evidence reduction median 为 `49.696233%`，session pooled ratio 为 `0.839889`；
- 两个 case 的 paired tool-call/cycle delta median 均为 0，无 Treatment-only failure；
- index：`740dc39d0786702a4073e034fe48d64fe4b44aefb79d339e5c4f71cc6eaee837`；
- manifest：`52c25023070f6b4b253ff7b3be6507be3d8501d2d383819918ac911f9b7675f2`。

允许结论仅限于两个冻结 case/Treatment 下的 behavior-preserving evidence ablation。session Token ratio 是局部描述事实，不是生产节省承诺。完整适用范围与异常点见 `ACP_1_3D_VALIDATION_SCOPE.md`。

## 明确不做

- 不实现 production slicing/replacement/real-time recommendation；
- 不使用 Hook `decision:block`或修改 tool success envelope；
- 不更改 prompt/tool/model 以配合 Treatment；
- 不合并两个 case 的 correctness Gate；
- 不输出全局节省比例。
