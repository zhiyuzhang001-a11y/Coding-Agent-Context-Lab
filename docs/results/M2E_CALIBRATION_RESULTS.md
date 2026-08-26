# M2e-0 测量与隔离校准结果

最后更新：2026-08-15

## 结论

M2e-0 的目标已经完成：Native 与 M2d 可以在隔离环境中运行同一任务，稳定取得不重复计数的 Codex 全会话 usage，并自动核验插件行为、代码改动、测试、stop reason 与 worktree 清理。

校准同时给出明确负面信号：在当前两个小型任务、四个有效配对中，M2d 与 Native 正确性相同，但 M2d 的配对 Token 比率中位数为 `3.131x`，即中位增加约 `213.1%`。主要伴随更多导航命令和重复结果。该结果不足以代表大型真实开发任务，但足以说明不应立刻扩大到 12–20 个昂贵会话；下一步应先分析并限制不必要的 Smart Read 激活与导航循环。

## 固定条件

- Codex CLI：`0.148.0-alpha.9`。
- 模型：`gpt-5.6-sol`。
- reasoning effort：`medium`。
- 插件版本：`0.1.0+codex.20260815090917`。
- 有效运行 commit：定位第一次 `5f32796`；定位第二次与修改任务 `86ec1fc`。两者之间只增加反向顺序续跑参数，不改变 Smart Read 功能。
- 每个运行使用独立 detached worktree、私有 Manager 数据目录和 ephemeral Codex 会话。
- Native 与 M2d 使用独立临时 `CODEX_HOME`；两者共享同一认证来源，Native 不安装插件，M2d 只安装当前 Agent Token Manager。
- `codex debug prompt-input` 预检确认 Native 无 `budgeted-code-reading`，M2d 有该 Skill。
- 两组使用相同 prompt、模型、reasoning、workspace-write 自动审批、输出 schema、超时和外部 JSONL 测量层。
- 原始 JSONL、diff 和测试输出只保存在被 Git 忽略的 `.agent-token-manager/m2e-calibration/`，本文件不保存源码正文。

## 固定计量合同

当前 `codex exec --json` 在会话结束时产生一次 `turn.completed.usage`：

- `input_tokens` 是完整 input；
- `cached_input_tokens` 是 input 子集，不再次相加；
- `output_tokens` 是完整 output；
- `reasoning_output_tokens` 是 output 子集，不再次相加；
- 当前 exec 事件不提供原生 `total_tokens`，因此固定使用 `input_tokens + output_tokens`；
- 中间事件不相加，只选择最后一个累计 usage；
- Hook/JSONL 估算的工具结果、读取结果和 Smart Read 管理载荷只作诊断，不能再加入全会话 total。

解析器还会拒绝 cached 大于 input、reasoning 大于 output、原生 total 与 input + output 不一致以及累计事件倒退等情况。

## 四个有效配对

| 任务 | 次数 | Native total | M2d total | M2d / Native | 正确性 |
|---|---:|---:|---:|---:|---|
| 定位审计汇总实现 | 1 | 81,755 | 252,584 | 3.090x | 两组正确 |
| 定位审计汇总实现 | 2 | 83,179 | 425,400 | 5.114x | 两组正确 |
| 修复空审计读取占比 | 1 | 107,320 | 340,385 | 3.172x | 两组正确、测试通过 |
| 修复空审计读取占比 | 2 | 106,260 | 240,391 | 2.262x | 两组正确、测试通过 |

汇总：

- 8/8 会话通过任务判定、usage、行为合规和隔离检查；
- Native total 中位数：94,719.5；M2d：296,484.5；
- 配对 Token 比率中位数：3.131x；
- 初版诊断曾报告 Native 命令 36、M2d 102，重复结果 15、48；M2e-0.1a 发现该计数同时包含 `item.started` 与 `item.completed`，并将 started 空输出误作重复；修正后实际完成命令为 Native 18、M2d 51，两组精确重复的已完成 payload 均为 0；
- Native 总 wall time 198.643 秒，M2d 422.743 秒；
- 修改任务四个 diff 都只包含 `audit_report.py`，运行器独立复验全部通过；
- 所有有效运行均有明确 `evidence_sufficient` 或 `change_verified` stop reason；
- 所有 worktree 均正常移除，没有 cleanup error。

校准完成后的安装态复验又发现只读插件缓存目录不能创建仓库内持久缓存。该问题不影响上述冻结数据；已增加权限受限的系统临时缓存回退并发布 `0.1.0+codex.20260815093914`，当时源码版与安装缓存均为 70/70 测试通过。M2e-0.1a 后当前安装版本与测试状态见 `STATUS.md`。

## 校准阶段发现并修复的问题

1. 单纯传入 `plugins."agent-token-manager@personal".enabled=false` 后，模型提示仍列出 Smart Read Skill。改为两个独立临时 `CODEX_HOME`，并在运行前检查模型可见提示。
2. 任务提示中的“使用环境可用导航能力”会让 Native 主动发现并调用仓库里的 `task_navigator.py`。已删除该诱导语，两个 arm 使用不提 Smart Read 的相同自然语言任务。
3. `read-only` sandbox 即使加入 `--add-dir`，Manager 私有数据仍不可写。两组统一使用 `--approve-for-me` 提供的 workspace-write 环境，同时由 evaluator 强制定位任务零改动。
4. 当前 CLI 不允许同时传 `--sandbox workspace-write` 与 `--approve-for-me`。最终只传后者。
5. 合规检查曾把命令输出中出现的 Smart Read 文件名误判为 Native 使用。现只依据实际执行命令，并将非零 Smart Read 命令、`PermissionError` 和 `write_failed` 判为集成失败。
6. 子进程 stdin 现固定为 `/dev/null`，避免外层终端输入影响非交互运行。

所有失败批次均保留在私有 artifacts 中，没有替换或删除；修复后从固定新 commit 重跑。

## M2e-0 验收

- [x] 定位与修改两类任务均完成 A/D 各两次、顺序平衡的配对运行；
- [x] usage schema、`input + output` 公式与缺失字段策略固定；
- [x] 中立外部 JSONL 测量层对两组完全相同，不向 Agent 输出提示；
- [x] worktree、日志、TaskState、Manager 数据和 Codex Home 隔离通过；
- [x] Native 无 Skill/命令、M2d 有 Skill/成功命令的行为合规可自动检查；
- [x] 能生成不重复计数、带原始 artifacts 哈希的端到端结果；
- [x] 校准发现的 stdin、提示污染、数据目录权限、CLI 参数和误判问题均已修复并复跑；
- [x] 修改任务 diff、测试和 stop reason 可自动核验。

## 局限与下一步

- 这只是 2 个任务、4 个配对的测量校准，不能声称所有任务都会增加 213.1%，也不能代替 M2e-1 多仓库 benchmark。
- 修改任务是确定性的校准 fixture，不是真实大型仓库任务。
- 当前每个 M2d 运行使用冷的 Manager 数据目录；M2e-1 仍需按计划区分预建地图与冷启动成本。
- 当前信号已经足够否决“直接扩大样本而不检查激活开销”。M2e-0.1a 已完成归因并修正 started/completed 诊断重复计数；直接 payload 差值只相当于模型 Token regret 的约 2.52%，下一步优先压缩模型往返而不是删除并不存在的精确重复 payload。详见 `M2E_0_1_ATTRIBUTION_RESULTS.md`。
- 只有诊断证明一个小而可消融的激活/循环修正后，才运行 6 任务 M2e-1 pilot；否则继续批量运行只会重复已知负优化。
