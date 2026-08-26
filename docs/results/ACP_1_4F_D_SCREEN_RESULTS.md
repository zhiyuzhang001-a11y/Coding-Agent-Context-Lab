# ACP-1.4F-D Screen Results

- 状态：`SCREEN COMPLETE under frozen development-protocol-v1`
- 日期：2026-08-19
- Screen：`72/72 completed`
- Screen admitted：`7/24`
- Screen rejected：`17/24`
- Development verdict：尚未生成，等待 Extension

## 结论

Screen 证明 task correctness 与 evidence opportunity identity 很稳定，但自然 Agent 行为强烈偏向窄 `rg` evidence。72/72 run 全部正确，72/72 都能无 oracle 地识别唯一 compatible carrier；17个 case 因 evidence payload 太小而自动失去 intervention benchmark 意义。

这不是 R1/S1/B1 的结果。Builder、collector、Hook mutation、Treatment 与 intervention 均未使用。

## Observed family

Design target 为 Read/Search/Structured Bash 各8，但 probing 后 dominant observed family 为：

- `search_like`：23 case；
- `read_like`：1 case；
- `structured_bash_like`：0 case。

Registry 没有把 case 强行留在 intended family。典型地，8个 intended Read case 全部自然使用窄 `rg`，被记录为 observed `search_like`。

## Admission

7个 case 在3-run Screen 后仍能数学上达到全部10-run Gate：

- `d_search_delta_maintenance_v1`
- `d_search_delta_retired_v1`
- `d_search_epsilon_archive_v1`
- `d_search_epsilon_legacy_v1`
- `d_search_zeta_retention_v1`
- `d_search_zeta_quarantine_v1`
- `d_bash_zeta_status_v1`

前6个 observed family 为 `search_like`。最后一个 intended Structured Bash case 自然表现为2次 `bash_sed`、1次 `bash_rg`，当前 dominant observed family 为 `read_like`；其10-run stability 尚待 Extension。

## Rejection

17个 case 同时命中：

- `F_EVIDENCE_TOO_SMALL`
- `F_INTERVENTION_NOT_MEANINGFUL`

这些 case 并非答错：全部3/3 correct、3/3 opportunity identified、3/3 compatible。问题是自然窄查询通常只返回4–41估算 Token，最多低于 meaningful evidence threshold；即使 identity 很稳定，也没有值得研究 reduction 的 payload。

## Process note

首次受限环境 probe 在产生 completed result 前因 Host connection stall 被中断，单独保存为 aborted preflight，不计入72次 Screen。以允许 Host 连接的同一冻结 runner 重启后72/72完成；task、protocol、pool、threshold 与执行顺序均未改变。

## Phase transition

冻结 contract 在 Screen 前将 Extension authorization 设为 false，以防跳过 phase Gate。现有 runner 没有独立 authorization overlay 参数，因此不能直接进入 Extension。合规转换必须新增只改变 phase authorization 的合同副本与 index，并自动证明除 `status/authorization` 外与冻结 protocol 完全一致；不得改变 runner、taxonomy、Gate、pool 或 admitted-case selection。
