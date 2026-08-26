# CO-1.1 计划：Hook-only Cost Isolation

最后更新：2026-08-15

状态：**6 场 Pilot 已完成；最小 observe 中位仅 +23 Token，rewrite 增量方向不一致。按停止规则不进入 27 场矩阵，详见 `CO_1_1_RESULTS.md`。**

## 唯一问题

> CO-1 Gate 2 中无补读任务稳定多出的约 0.7% 完整会话 Token，来自插件/Hook 固定加载，还是来自 `decision:block` replacement 语义？

## 三臂

1. `native`：不安装插件；
2. `observe`：安装 Hook-only 插件，PostToolUse 执行并记录，但不返回 decision；
3. `rewrite`：安装同一 Hook-only 插件，通过 `decision:block` 返回与原始 payload 正文等价的内容。

第三臂称为 equivalent-payload rewrite，不称为真正 no-op：Codex 当前会把 `decision:block` 呈现为 tool-error envelope，这正是待测成本。

Hook-only 插件只能包含 manifest、hooks 配置和一个标准库脚本；不得包含 Skill、Navigator、MCP、App、defaultPrompt、切片、缓存或搜索压缩。

## Pilot

- 复用冻结 `function_answer` 自包含任务；
- 同 commit、独立 detached worktree、每 arm 独立 `CODEX_HOME` 和会话；
- 2 repetitions，顺序轮换：`native→observe→rewrite`，`observe→rewrite→native`；
- correctness、模型可见正文和 tool call 必须一致；rewrite 允许 envelope 不同，但正文 canary 与答案必须一致；
- 保存完整会话 Token、assistant response cycles、tool call 数、累计 usage 序列和 Hook 状态。

## 解释

```text
observe - native
= 最小插件加载 + Hook 执行固定成本

rewrite - observe
= decision:block / replacement 协议成本
```

Pilot 不要求统计显著性，只判断计量链路和方向是否在两次重复中一致。只有 Pilot 可复现，才考虑 3 tasks × 3 repetitions 的 27 场正式矩阵。

## 停止条件

- correctness、tool call 或模型可见正文不一致；
- observe/rewrite 诱发额外读取；
- transcript 或 usage 无法稳定归因；
- 两次重复方向相反且差异落在普通 Native 波动内。

CO-1.1 不修改 `python_syntax_slice.py`，不实现 Compensation-risk Gate。
