# CO-1.2 离线结果：Compensation-risk Gate

最后更新：2026-08-16

状态：**离线 Gate 通过；未运行真实 Codex Native/CO A/B。**

## 结论

确定性风险 Gate 已接入独立 Hook-only 实验插件。它只在“唯一完整语法单元、局部绑定闭包、无显式高风险任务意图、预计绝对节省至少 200 Token 且比例至少 40%”同时成立时返回 slice；其余情况不返回 replacement，让 Native 结果继续。

这一步证明的是分类、fail-open 和 Hook 输出契约成立，不证明完整会话 Token 已降低。

## 冻结离线矩阵

| 场景 | 期望 | 实际 reason | 结果 |
| --- | --- | --- | --- |
| 自包含 function | activate | `low_compensation_risk` | 通过 |
| 纯 method | activate | `low_compensation_risk` | 通过 |
| module constant | fail-open | `external_dependency_risk` | 通过 |
| module import | fail-open | `external_dependency_risk` | 通过 |
| external helper | fail-open | `external_helper_risk` | 通过 |
| class field | fail-open | `class_state_risk` | 通过 |
| sibling method | fail-open | `sibling_method_risk` | 通过 |
| `getattr` 等动态语义 | fail-open | `dynamic_semantics_risk` | 通过 |
| 显式 edit/debug/execute/compute 意图 | fail-open | `task_intent_risk` | 通过 |
| 节省不足 | fail-open | `insufficient_expected_saving` | 通过 |
| 目标范围歧义 | fail-open | `analysis_uncertain` | 通过 |

真实 Hook 子进程测试进一步确认：低风险读取返回 `decision:block` 的精简语法包，raw-only canary 不进入 replacement；高风险读取无 Hook 输出并记录可解释拒绝原因。

## 回归结果

- 源码测试：128/128 通过，使用 `-W error`；
- CO-1.2 实验插件版本：`0.1.0+codex.20260816135037`；
- 主插件结果记录版本：`0.1.0+codex.20260816135037`，默认行为未切换；
- 主 Ranker、Navigator、Skill、缓存与搜索压缩均未修改；
- Hook analyze/输出异常仍采用 fail-open；
- 记录只包含路径、哈希、估算与风险元数据，不保存源码正文。

## 尚未证明

- 没有运行模型，因此尚未证明补偿读取或新增模型回合下降；
- 没有证明完整会话 Token 中位数不高于 Native；
- 没有为提高激活率调阈值，也没有加入模型分类器。

## 下一门

使用同任务、同 commit、独立 worktree/CODEX_HOME 跑最小 Native vs Hook-only+Gate 配对。冻结门槛：correctness 零回归；高风险场景与 Native 工具结果 hash 一致；低风险场景无补偿读取和新增模型周期；activated-read 中位节省不少于 40%；完整会话 Token 配对中位数不高于 Native。若失败，保持 fail-open 并复审宿主层，不扩大功能。
