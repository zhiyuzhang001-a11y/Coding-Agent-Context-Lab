# ACP-1.4F-0 Validation Scope

状态：`COMPLETE under frozen contract scope`

日期：2026-08-19

## 本阶段证明了什么

ACP-1.4F-0 已在任何新 Agent run 之前冻结 combined prospective generalization 的实验尺子。F-1 preflight 发现初版遗漏 Native candidate identity 后，在仍为 0 Agent run 时建立 `v2.1` 并重新冻结；旧 F-0 index 不用于运行数据：

- primary sampling frame 固定为 12 个新 case：Read/Search/Bash 各 4 个；
- case 固定跨 `alpha_service`、`beta_cli`、`gamma_pipeline` 三种 project form，每个 family 至少跨两个上下文；
- 所有 fixture file、contract、oracle registry、builder 与 verifier 进入 checksum chain；
- ground truth 已由独立离线审计复现；
- Treatment builder 只接受冻结的八字段 `TreatmentBuilderInput`；
- builder 不读取文件或 registry，不接收 `case_id`，并递归拒绝 expected、scorer、ground truth、target regex、历史 correctness 和 pilot result；
- R1/S1/B1 的 selector、passthrough 和 unknown 语义已固定；
- Native candidate identity 固定为 family/request-shape/success 规则，path signature 不公开原始 command/result；
- Native、offline activation、formal admission、correctness、behavior、overall denominator 和 366-run 硬上限已预注册；
- G0 泄漏会使整个 experiment version 失效，修复必须新建版本并从头运行。

只读 verifier 输出：

```text
phase=ACP-1.4F-0
status=pass
case_count=12
agent_run_count=0
```

定向测试：`9/9 PASS`。项目根目录全量回归：`405/405 PASS`。

## 本阶段没有证明什么

F-0 没有运行 Agent，因此没有证明：

- 12 个 case 的 Native correctness、candidate recurrence 或 path stability；
- R1/S1/B1 在自然 evidence 上可以达到 35% activation；
- Treatment 保持 correctness、tool path、model cycles 或 success semantics；
- Read/Search/Bash 已形成跨任务 generalization；
- 存在可避免 Token、session savings 或 production-safe reduction。

## 下一 Gate

下一步仅为 ACP-1.4F-1 Native qualification：每 case Native ×10，共 120 runs。builder 在 F-1 必须关闭；所有 Native evidence 都要冻结，不能按 correctness、体量或预期 activation 选择。

F-2、pilot 与 formal 仍未授权越级运行。Transparent Smart Read、production slicing、replacement 和实时 recommendation 继续冻结。
