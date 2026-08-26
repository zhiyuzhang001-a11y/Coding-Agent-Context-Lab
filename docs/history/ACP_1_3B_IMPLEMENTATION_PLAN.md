# ACP-1.3B 正式任务书：Controlled Evidence Intervention Feasibility

- 状态：`ACP-1.3B Controlled Evidence Intervention Feasibility — COMPLETE under synthetic frozen experiment scope`
- 日期：2026-08-18
- 前置：ACP-1.2 与 ACP-1.3A 均 `COMPLETE under frozen experiment scope`
- 目标：建立一个不依赖 Hook replacement 的 prospective controlled-evidence 实验装置

## 范围

ACP-1.2 的 5 个历史 high-cost candidate 没有可重放 prompt、ground truth 或原始 evidence，因此 ACP-1.3B 不声称直接验证它们。本阶段创建一个新的 prospective replay-qualified synthetic evidence case，只证明因果实验装置是否可行。

```text
same prompt + same command + same success semantics
                    ↓
        control evidence / treatment evidence
                    ↓
 correctness, tool path, cycles, usage observations
```

## 实验装置

- Case ID：`controlled_evidence_ledger_lookup_v1`
- 唯一命令：`sed -n '1,9999p' evidence_ledger.txt`
- 问题：从 evidence ledger 返回 `deployment_key` 的精确值；只输出答案。
- Ground truth：`ORCHID-7319`
- Control：目标事实 + 120 条确定性不相关 ledger 记录。
- Treatment：相同目标事实 + Control 的前 60 条不相关记录。
- Treatment 是 Control 的确定性子集；不在运行中分析或切片任何真实源码。
- 每个 run 使用独立空 Codex home，不安装插件或 Hook。
- arm 选择在运行前通过私有 fixture 内容完成；prompt、命令和 tool request 不暴露 arm。

## 预注册设计

### Replay qualification

- Control-only ×20；
- 20/20 run 必须 completed 且 usage 可用；
- correctness 至少 19/20；
- 至少 19/20 只有一个 tool call，且 normalized command 与冻结命令一致；
- 所有完成的目标 call 均保持正常 success envelope，不含 `Script failed` / `Script error`。

### Paired feasibility

- Control ×5、Treatment ×5，按 repetition 交替运行；
- 不删除失败或异常 run；
- 命令 hash、prompt hash、model、reasoning effort 和 host configuration 必须一致；
- Control/Treatment 均为 exit code 0 的源头输出，不使用 `decision:block`；
- Treatment model-visible evidence estimate 必须比 Control 预注册小至少 40%，只作 activation Gate，不叫 savings；
- correctness、tool path、model cycles 与 total usage 只报告，不设置“必须更便宜”的 Gate。

## 状态分离

```text
mechanism_feasibility
replay_qualification
candidate_correctness_effect
candidate_cost_effect
production_intervention_availability
```

mechanism pass 不表示 evidence 可避免；synthetic canary pass 不表示生产 Host 具备任意 tool-result rewrite。

## Gate

1. **G1 Replay stability**：Control 通过 20-run 预注册准入。
2. **G2 Intervention isolation**：除 evidence payload/hash/size 外，冻结实验输入一致。
3. **G3 Success semantics**：两臂目标命令均以正常成功语义返回。
4. **G4 Activation**：Treatment evidence hash 改变且 model-visible estimate 下降至少 40%。
5. **G5 Outcome completeness**：10/10 paired runs 的 correctness/tool path/cycles/usage 完整。
6. **G6 Privacy/provenance**：公开结果只保留 hash、尺寸、分类与统计，不保留 transcript body。
7. **G7 No product mutation**：collector、Hook 和 frozen artifacts 不变。
8. **G8 Stop rule**：若只能依赖 `decision:block` 或无法保持 success envelope，立即停止。

## 明确不做

- 不修改或注册 Hook，不使用 replacement API；
- 不对历史 5 candidates 声称 causal validation；
- 不输出 avoidable/wasted/potential-savings Token；
- 不把 synthetic harness 写成 production capability；
- 不在本阶段开始 candidate-specific ACP-1.3C。

## 实施顺序

- [x] 冻结 spec、payload generator、scorer 与停止规则。
- [x] 实现 offline canary 和隔离 runner。
- [x] 运行 Control ×20 qualification。
- [x] 通过后运行 Control/Treatment 各 ×5。
- [x] 冻结结果、manifest/checksum chain 和项目状态。

## 冻结结果

- offline canary 两臂均正常退出，同一命令，未使用 Hook/replacement；Treatment 是 Control 的确定性子集，`chars_div_4_v1` evidence estimate 降低 `49.897646%`。
- Control-only qualification 为 `20/20` completed with usage、`20/20` correct、`20/20` exact single command；每次均为 2 model cycles。
- paired validation 为 Control `5/5` 与 Treatment `5/5` correct/success/exact-command，每臂均为 2 model cycles。
- target evidence estimate median 为 `3919 → 1969` Token，已观测 activation ratio 为 `49.757591%`。session total median 为 `37,219 → 34,127`，仅作 synthetic paired observation，不是 avoidable/savings estimate。
- G1–G8 全部通过；index 为 `6397007ce8fdb2229b45490249be70ad4017adf0df41388135d71be04bb10fc3`，manifest 为 `3cecfb99652eeabcfd0709aa5df7b8f55400ce9179bd33dedbc1239887467a87`。
- 历史 5 个 ACP-1.2 candidate 仍为 `not_validated`；生产 Host intervention 仍为 `blocked`；Transparent Smart Read 继续冻结。
