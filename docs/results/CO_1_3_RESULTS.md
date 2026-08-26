# CO-1.3 结果：冻结版真实模型 A/B

最后更新：2026-08-16

结论：**Fail——正确性无回归，但自然 Codex 行为下实际激活为 0，无法证明 session-level saving。**

## 冻结身份

- 被测实现：`b506818b3db87be62064ad64e62b1ad262d5a4b9`；
- harness：`ebac9b6d25834ee5e6d107d437d35b22b1ed006e`；
- 结果记录版主插件：`0.1.0+codex.20260816141855`（不改变冻结被测插件）；
- manifest SHA-256：`badf98fba553ddcae46cf479b8c3120f340d906e7c168ea837ed15826bbd2b9d`；
- 模型：`gpt-5.6-sol`，reasoning effort `medium`；
- 12 个真实仓库问答任务，6 Expected-hit/6 Expected-fail-open，6 AB/6 BA，共 24 场。

## 核心结果

- correctness：Native 12/12，CO 12/12；
- actual Gate activation：0/12；
- Hook 尝试：16；其中 12 次 `unsupported_request`，4 次 `non_unique_target`；
- retry/recovery：两组 exact retry 均为 0，activation 后 recovery 为 0（因为没有 activation）；
- model cycles：CO 合计比 Native 少 1；tool calls 合计少 1；
- 修正 code-mode parser 后，model-visible code Token 配对中位比率为 `1.0000x`；
- 完整会话 Token：Native 475,489，CO 457,925，pooled ratio `0.963061x`；配对中位 ratio `0.999391x`，中位绝对差 −25.5 Token；
- 12 对中 6 对 CO 较低、6 对较高；最小 ratio `0.622046x`，最大 `1.427839x`。

`0.963061x` 不能解释为 3.69% 产品节省：本轮 Hook 没有一次 replacement，CO 与 Native 的大幅正负变化来自自然模型循环波动。冻结 primary gate 也要求配对中位与 pooled 同时 `<=0.95x` 且 actual activation 非零，本轮均未满足。

## 为什么没有激活

自然 Codex 大量使用：

```text
rg ...
rg ... && sed ...
rg -C ...
宽范围 sed → 较窄范围 sed
```

CO-1.2 只接受单独、严格、简单的 `sed -n`。复合 `rg && sed`、单独 `rg` 和其他 code-mode 调用均安全 fail-open；进入严格 `sed` 的 4 次范围又同时覆盖多个函数，因此为 `non_unique_target`。离线 Expected-hit 12/12 分类成立，但那只证明“给定唯一 symbol 与大原始 payload 时 Gate 会怎样”，没有证明 Agent 会自然产生这种请求。

这将问题从 AST slicing 收敛为宿主覆盖问题：

> 切片器可以工作，但当前 PostToolUse + 严格 shell 白名单没有位于自然 Codex 读取路径上。

## 归因器修复

首轮汇总发现当前 code mode 使用未加引号的 JavaScript object keys，旧 parser 将部分命令记为空。harness 随后只修复 command 解析并从原 transcript 重算二级指标，没有重跑、替换或调整任何模型场次。另修复 verdict：零实际激活必须为 Fail，不能因随机 Token 波动得到 Weak signal。完整会话 usage、correctness 和 0 activation 结论从未受 parser 问题影响。

## 决策

- CO-1.3 实验完成，判定 Fail；
- 不进入 CO-2 Evidence Dedup；
- 不继续优化 AST slicer 或提高压缩率；
- 不直接放宽为复杂 shell parser，因为复合命令的结果边界和错误语义仍不透明；
- 下一步先做宿主层调查：统计自然读取路径，评估直接 read/search result interception、PreToolUse 输入改写或更底层 model-visible result adapter；只有找到能覆盖自然命令且保持 fail-open 的宿主后，才设计 CO-1.4。

结构化摘要见 `resources/co1_3_results.json`；私有原始 transcript 与每场 artifacts 保留在 `.agent-token-manager/co1-3/`，不提交源码内容。
