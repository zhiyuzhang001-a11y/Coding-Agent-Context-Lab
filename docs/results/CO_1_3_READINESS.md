# CO-1.3 Readiness：冻结版真实模型 A/B

最后更新：2026-08-16

状态：**Ready；可以运行 12 个任务 × Native/CO 的 24 场冻结配对。**

## 冻结身份

- 被测实现 commit：`b506818b3db87be62064ad64e62b1ad262d5a4b9`；
- 被测插件：该 commit 的独立 `hook-only-cost-probe`；
- manifest SHA-256：`badf98fba553ddcae46cf479b8c3120f340d906e7c168ea837ed15826bbd2b9d`；
- 数据集：6 Expected-hit + 6 Expected-fail-open；
- 顺序：6 个 Native→CO + 6 个 CO→Native；
- 默认模型：`gpt-5.6-sol`，reasoning effort `medium`。

## 预检结果

- 12/12 目标 symbol 在冻结 commit 中唯一；
- 6/6 Expected-hit 离线 reason 为 `low_compensation_risk` 且通过经济门；
- 6/6 fail-open 分别覆盖 `external_dependency_risk`、`external_helper_risk`、`class_state_risk`、`sibling_method_risk`、`dynamic_semantics_risk` 和 `task_intent_risk`；
- Prompt 不指定任何 shell 命令，只指定真实仓库 path/symbol 与问题；
- runner 分开记录 eligible、supported read、actual activation、package visibility、retry 和 activation 后 recovery；
- 源码测试 131/131 通过，`-W error`；主插件与实验插件规范校验通过。

## 执行边界

正式 artifacts 目录必须为空，runner 拒绝混入旧结果。每场使用独立 detached worktree 和新会话；CO Home 只从冻结 worktree 安装 Hook-only 插件。若 runner/usage parser 出错，只修实验设施，并重跑所有受影响场次，不修改 manifest 或被测实现。

运行结束前不开始 CO-2，不调整 Gate 阈值，不根据早期场次替换任务。
