# M2e-0.1b Gate 1 验收结果

最后更新：2026-08-15

状态：**通过固定 Fixture Gate 1；尚未进入 M2d 9/9 Gate 2，也未运行昂贵 Codex 端到端会话。**

## 1. 本轮目标

本轮只实现 Compact Navigator 的离线协议与安全边界，不调整 Ranker、Graph 权重、Discovery 策略或 Skill 默认行为。目标是把原来模型可见的 `start → next → expand → feedback → ... → stop` 循环收进本地代码，并把一个任务限制为：

```text
compact_navigate
→ optional compact_verify
→ terminal
```

## 2. 已实现

- 新增 `scripts/compact_navigator.py`，提供 `navigate` 与 `verify` 两个 CLI/API 操作；
- `TaskState` 持久记录 compact phase、成功外部调用次数、verification 使用状态、双预算、五项内部上限、Evidence 元数据与请求幂等记录；
- 第一次调用在内部执行受限候选选择、源码展开、structural feedback、重排和停止判断；
- 第一次未能保守确认时返回 `needs_verification`，第二次只接收一批带 Evidence hash 的 semantic feedback；
- 第二阶段只占用一次模型可见调用，可在剩余统一预算和内部上限内完成受限补证，随后无条件进入 `completed` 并形成明确 `stop_reason`；
- 成功模型可见结果最多两次；非法 phase、非法反馈、未知或过期 Evidence 不扣调用次数；
- 相同 `request_id` 重试不重复索引探索、不重复扣预算，并能在任务后续终止后重放原阶段语义；
- internal exploration 与 model-visible package 分别执行 Hard Budget；同时限制 steps、fan-out、graph hops、source reads 与 elapsed time；
- Evidence 正文只存在于当次返回包；TaskState、SQLite 和幂等记录只保存 ID、hash、范围与成本等元数据；
- 审计器与 M2e 事件解析器已识别 `compact_navigator.py` 为 Smart Read/read-like 操作。

## 3. 固定 Fixture 与结果

Gate 1 使用三个本地 Python Fixture：登录过期判断、无语义标识符调用链、发票事件路由。10 项 Compact 专项测试覆盖：

- 第一次直接完成；
- 第一次请求验证、第二次确认完成；
- 第二次无确认时以 `verification_inconclusive` 终止；
- 第二阶段一次预留补证；
- navigate/verify 幂等重试；
- 非法反馈、非法 phase 与第三次调用拒绝；
- stale Evidence hash/源码变化拒绝且不消耗调用；
- internal/model-visible Hard Budget 与 source-read/hop 上限；
- Evidence Package 不暴露完整 ranking trace；
- SQLite 与 TaskState 不持久化源码隐私哨兵。

验证命令：

```bash
python3 -m unittest tests/test_compact_navigator.py -v
python3 -W error::ResourceWarning -m unittest discover -s tests
```

结果：Compact 专项 `10/10` 通过；源码态与安装缓存全套旧新测试均为 `87/87` 通过，且 ResourceWarning-as-error 通过。插件与 Skill 规范验证通过，源码和安装缓存逐文件一致。安装版本为 `0.1.0+codex.20260815111325`。

## 4. 本轮没有证明什么

- 没有证明冻结 M2d 的 9 个成功任务在 Compact 下仍为 `9/9`；
- 没有证明真实 Codex 完整会话 Token 已下降；
- 没有证明 `3.131x` 已下降到 `≤1.25x`；
- 没有启用 Activation Gate；
- 没有把 Compact Navigator 切换为安装后 Skill 的默认路径；
- 没有调整检索质量、Graph 类型或排序权重。

因此当前只能称为 **Compact 协议与本地执行内核 Gate 1 通过**，不能称为 M2e-0.1b 或端到端节省目标完成。

## 5. 下一步

1. [失败] 冻结 M2d 的 10 个无 identifier 任务已运行；Compact 只保留原成功集合的 `2/9`，虽然协议结果均不超过 2 且预算无违规，因此停止后续 Gate，见 `M2E_0_1B_GATE2_RESULTS.md`；
2. 若 Gate 2 通过，再做隐私、预算和协议 payload 的 Gate 3/4 消融；
3. 前四个离线 Gate 通过后，才运行 Native / Old M2d / Compact 的相同两任务完整配对；
4. Compact 证明值得激活后，才实现默认关闭的廉价 Activation Gate。
