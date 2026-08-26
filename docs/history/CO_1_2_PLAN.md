# CO-1.2 计划：Compensation-risk Gate

最后更新：2026-08-16

状态：**离线实现与分类 Gate 已完成；真实模型矩阵尚未运行。**

## 产品目标

> 只在局部语义闭包充分、补读风险低且预计收益足够高时启用 syntax slicing；高风险或低收益读取直接 fail-open。

CO-1.2 不追求激活率。实验宿主固定为独立 `Hook-only + slicer + risk gate` 插件，不加载 Agent Token Manager Skill、Navigator、MCP、App、缓存或搜索压缩。

## 确定性 Gate 顺序

```text
strict sed request
→ unique complete syntax unit
→ code dependency risk
→ explicit task-intent risk（仅有可靠元数据时）
→ expected saving gate
→ activate / fail-open
```

### 风险原因

- `external_dependency_risk`：body 读取 slice 外 module global/constant/import；
- `external_helper_risk`：body 调用 slice 外 module helper/class；
- `class_state_risk`：method 读取或写入 `self/cls` field；
- `sibling_method_risk`：method 调用 `self/cls` sibling method；
- `dynamic_semantics_risk`：反射、动态名称或运行时代码访问；
- `task_intent_risk`：可靠显式元数据标记 edit/debug/execute/compute；
- `analysis_uncertain`：语法、范围或绑定分析不明确；
- `insufficient_expected_saving`：绝对节省或节省比例未同时过门。

未知任务意图不能用自然语言关键词猜测；v0 只接受显式实验元数据，避免依赖不稳定 `transcript_path`。

## 经济门

v0 冻结：

```text
estimated absolute saving >= 200 Token
estimated saving ratio >= 40%
```

估算继续使用 `chars_div_4_v1`，并同时保存 raw/slice chars、估算 Token 和比例。运行途中不调阈值。

## 输出契约

每次决定记录：

```text
activate_slice
reason
risk_evidence
estimated_native_tokens
estimated_slice_tokens
estimated_saving_tokens
estimated_saving_ratio
```

风险或低收益一律不返回 replacement decision，让 Native 结果继续。分析器异常 fail-open 为 `analysis_uncertain`。

## 离线验收

- [x] 自包含 function 与纯 method 可在足够收益时激活；
- [x] module constant/import、external helper、class field、sibling method 分别正确 fail-open；
- [x] 动态语义、显式高风险任务、歧义和低收益 fail-open；替代超预算由既有 CO-1 Gate 保持 fail-open；
- [x] 每个拒绝都有稳定 reason 和最小 evidence；
- [x] 低风险 slice 保持完整语法单元与 canary 排除；
- [x] 不修改主 Agent Token Manager 的 Ranker、Navigator 或 Skill；
- [x] 全部旧测试继续通过（源码 128 项，见 `CO_1_2_OFFLINE_RESULTS.md`）。

离线通过后才设计 Native vs minimal CO-1.2 真实矩阵。真实门要求 correctness 零回归、高风险 hash 与 Native 一致、低风险补偿/新增周期为 0、activated-read 中位节省至少 40%，完整会话中位不高于 Native。
