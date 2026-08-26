# CO-1 Gate 2 Runner 就绪记录

最后更新：2026-08-15

状态：**离线就绪。真实实验采用“单案例探针 → 六任务矩阵”两段执行。**

## 已完成

- 固定六任务 manifest：4 个 activated economics、2 个 fail-open；
- 固定单一 Python fixture 与修改任务测试；
- Native/CO 独立 `CODEX_HOME`；
- 每次运行使用同一 commit 的独立 detached worktree；
- Native/CO 顺序交替；
- transcript 中 tool call / output 配对；
- `initial / retry / compensation / other read / edit / test` 归因；
- canary、syntax package、correctness、diff、测试、usage 与 fail-open reason 记录；
- 补偿后 `Net activated-read saving` 和 Gate 2 汇总判定。

## 冻结离线路由

```text
function_answer   syntax_unique_range
method_answer     syntax_unique_range
global_context    syntax_unique_range
local_edit        syntax_unique_range
ambiguous_range   syntax_range_ambiguous
over_budget       syntax_slice_over_budget
```

前四项 slice 均小于原始 `sed` payload 且不包含各自 canary；后两项均不产生替代 decision。

## 验证

```text
python3 -W error -m unittest discover -s plugins/agent-token-manager/tests -p 'test_*.py'
Ran 118 tests
OK
```

新增测试覆盖 manifest 冻结、marker 范围、真实 Hook 路由、transcript call/output 配对、补偿归因与 Gate 汇总公式。旧测试继续通过。

## 分段执行

1. 先只运行 `function_answer` 的 Native/CO 配对；
2. 核验两个独立 worktree/home、transcript 可用、Native canary 可见、CO slice 可见、Token 与 usage 非零、命令归因正确；
3. 探针若为 runner/接口失败，只修 runner，不修改 slice 或任务；
4. 探针通过后再运行其余五项；
5. 汇总前检查所有 12 场均来自同一冻结 commit。

原始 transcript、stderr、diff 和 Hook 日志只保存在私有 `.agent-token-manager/co1-gate2`，版本库只保存去源码化汇总。
