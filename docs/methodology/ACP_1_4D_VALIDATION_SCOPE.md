# ACP-1.4D Validation Scope

- 状态：`COMPLETE under frozen audit scope`
- 日期：2026-08-19
- Agent runs：`0`
- Private formal source subset：`60` frozen ACP-1.4C runs

ACP-1.4D 只解释三个既有 INCONCLUSIVE Treatment 为什么没有达到 `35%` activation Gate。它没有改写 ACP-1.4/1.4C verdict、没有运行新 intervention，也没有把 source-side deletion 当作 model-visible savings。

## 结论

### `read_context_router_limit_v1` — RULE_MISMATCH

Treatment 只从 93 行文件中删除末尾 23 行，仍保留前 70 行；目标声明位于早期区域。Control/Treatment 的冻结 model-visible estimate 为 824/589 Tokens，因此真实 reduction 只能达到 `28.519417%`。这是 v1 prefix 过宽，不是固定结构已证明不可缩减。

状态：`eligible_after_preregistration`。prospective v2 可以研究更窄、确定性的 range projection，但必须重新预注册和 Native qualification。

### `search_budget_stop_v1` — RULE_MISMATCH

v1 规则豁免整个 `task_navigator.py`，其匹配内容占 Control 可见字符约 `73.749228%`；Treatment 实际只改变 1 个 non-target match。命令还在全部 20 个正式 run 中带入额外 root scope。规则保留粒度太粗，导致 reduction 只有 `5.679012%`。

状态：`eligible_after_preregistration`。v2 必须采用无歧义 scope，并把“保留整个文件”改为客观的 line-selective target preservation。

### `search_token_router_v1` — MEASUREMENT_MISMATCH

Treatment 每次实际改变 81 个文件、456 个 source match 行，但 Control/Treatment 各 10/10 都出现 host output truncation。两臂仍处于输出饱和区，source deletion 没有等比例进入 model-visible denominator，最终 median 只有 `0.628088%`，且 pair 有正有负。

这里的“measurement mismatch”不表示 `candidate_visible_estimated_tokens` 算错；它表示上游 source action 与被 host 截断后的可见 evidence 不是可直接比较的同一量。

状态：`eligible_after_preregistration_with_censoring_control`。v2 必须先消除 scope 歧义，并保证两臂处于可测量、非饱和的输出范围，再研究更强的 non-target projection。

## 冻结边界

- 35% Gate 保持不变；三个历史 verdict 仍为 INCONCLUSIVE。
- 不替换 case，不补跑，不删除 outlier。
- v2 eligibility 只是实验准入建议，不是 activation 或安全性 PASS。
- session cost 继续不解释；不声明 waste、avoidable volume 或全局 savings。
- 不实现 production slicing、replacement 或实时 recommendation。
