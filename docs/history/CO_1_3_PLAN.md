# CO-1.3 实施计划：冻结版真实模型 A/B

最后更新：2026-08-16

状态：**已完成；结果为 Fail（0 次自然激活），见 `CO_1_3_RESULTS.md`。**

## 唯一问题

> Hook-only + Compensation-risk Gate 是否在不降低正确率、不诱发补偿行为的前提下，降低完整模型会话 Token？

完整会话 Token 是 primary metric，correctness 是硬门。model-visible code Token 只解释机制，不能单独证明成功。

## 冻结边界

- 被测仓库 commit：`b506818`；
- 被测实验插件：该 commit 内 `experiments/co1-hook-only/plugins/hook-only-cost-probe`；
- Gate：确定性规则、`200 Token + 40%` 经济门、严格 `sed` 白名单；
- 模型、reasoning effort、任务文本、顺序表和 manifest hash 在首场运行前记录；
- 不改 slicer、Gate、prompt、插件版本和任务集；
- 只允许修复 runner/usage parser 等实验设施 bug，修复后受影响场次全部重跑并更新 harness commit/hash。

实验设施与被测实现分开版本化；新增 runner 不改变 `b506818` 中的被测代码。

## 数据集与自然行为

固定 12 个当前真实仓库代码问答任务：6 个 Expected-hit、6 个 Expected-fail-open。Expected-hit 覆盖不同文件和 function/pure method；fail-open 覆盖 module import/global、external helper、class state、sibling method、dynamic semantics 和显式高风险 task intent。

Prompt 只给出目标 path/symbol 与问题，不指定 `cat/sed/rg`，不强迫命中 Hook。必须区分：

```text
eligible opportunity
→ actual supported read
→ Gate activated / fail-open
→ model-visible package
```

Expected-hit 是运行前的结构预期，不等同于实际激活；模型未进入严格白名单也是产品结果。

## 隔离与顺序

- Native 与 CO 使用同一任务、同一 commit、相同模型配置；
- 每场独立 detached worktree、独立会话；Native 与 CO 使用独立 `CODEX_HOME`；
- CO 只安装冻结 Hook-only 插件，不加载主 Agent Token Manager、Skill、Navigator 或 MCP；
- 六组 `Native→CO` 与六组 `CO→Native`，顺序由冻结 manifest 明确指定；
- 不复用上一任务 transcript；只共享同 arm 的认证与插件安装环境。

## 七项核心指标

1. correctness；
2. 完整会话 Token；
3. model-visible code Token；
4. model cycles；
5. tool calls；
6. retry/recovery；
7. Gate hit/fail-open reason。

结果分三层报告：全部任务（产品 ITT）、实际 activated 任务（机制）、实际 fail-open 任务（等价性/固定成本）。同时保存配对绝对差、配对比率、合计比率、中位数和最差案例。

## 冻结判定

- **Strong pass**：correctness 零回归；retry/recovery 不系统增加；model cycles 不系统增加；实际 activated 的 model-visible code 明显下降；全部任务完整会话 Token 的配对中位比率和合计比率均 `<= 0.95x`。
- **Weak signal**：correctness 零回归且两项完整会话比率均 `< 1.00x`，但未同时达到 `0.95x`；不进入下一功能，先增加重复或任务数。
- **Fail**：correctness 回归、任一完整会话主比率不低于 Native，或出现系统性补偿回合；停止扩展切片，转向 context replay、历史工具输出、cache 与 model-cycle 成本归因。

若 actual activation 为 0，不能以 fail-open 等价性宣布成功；应判为当前宿主/白名单没有形成有效产品覆盖。

## 明确不做

- 不做 CO-2 Evidence Dedup；
- 不扩大语言、Edge、缓存或 search compression；
- 不用 prompt 强迫读取命令；
- 不因中途结果调阈值或替换任务；
- 不把扩大安全切片类型错误命名为 CO-2；该工作若获准应属于 CO-1.4。

## 执行清单

- [x] 冻结目标、分层统计和三级判定；
- [x] 冻结 12-task manifest 与顺序；manifest SHA-256 `badf98fba553ddcae46cf479b8c3120f340d906e7c168ea837ed15826bbd2b9d`；
- [x] runner 预检、131 项单元测试和源码/实验插件规范校验通过；
- [x] 运行 24 场 Native/CO；12/12 correctness 一致，但 actual activation 为 0；
- [x] 保存结构化结果、失败案例和最终决策；判定 Fail，不进入 CO-2。
