# CO-1 Gate 2 计划：Correctness 与补偿读取经济性

最后更新：2026-08-15

状态：**真实矩阵已完成，Gate 2 未通过：工具层和 correctness 通过，但 0/4 activated 任务完整会话低于 Native。停止 Gate 3，详见 `CO_1_GATE2_RESULTS.md`。**

## 1. 唯一判断

Gate 2 只判断：

> CO-1 首次语法切片减少的模型可见上下文，是否会因为缺少上下文而诱发 Codex 重试或补偿读取，并最终把节省吃回来？

Gate 2 不优化 activation rate，不扩大 slice，不调 ranking，不加入缓存或 search compression。

## 2. 配对隔离

每个任务的 Native 与 CO 必须：

- 使用完全相同的任务文本、repository commit、模型、推理等级、权限和测试命令；
- 分别运行在同一 commit 的独立 detached worktree；
- 使用独立 `CODEX_HOME`、独立会话、独立插件数据目录和独立 transcript；
- Native home 不安装 Agent Token Manager；
- CO home 只安装冻结版本 Agent Token Manager，并显式设置 CO-0/CO-1 enforce；
- 禁止复用前一 arm 的模型上下文、结构缓存、测试产物或已修改工作树；
- 交替 Native-first / CO-first，降低顺序偏差。

每次运行保存 commit、worktree、Codex/plugin 版本、完整任务文本、环境白名单、命令、模型 usage、transcript hash、Hook 记录、diff、测试结果和 stop reason。原始源码正文不复制进汇总报告。

## 3. 模型可见验证

每个激活任务在原始读取结果中放置唯一 canary，且 canary 位于 slice 应省略的区域。通过条件：

1. Native 的模型可见工具结果包含 canary；
2. CO 的对应模型可见工具结果包含 `[Smart Read CO-1 syntax slice]`；
3. CO 模型可见工具结果不包含原始 canary；
4. Hook 日志的原始/替代 hash、长度和策略与 transcript 一致；
5. 后续模型不能回答只存在于省略 canary 区域的问题，除非 transcript 中存在可归因的补偿读取。

只看到 Hook `optimized` 记录不能算通过；必须检查 transcript 中最终进入模型的 `function_call_output`。

## 4. 固定任务矩阵

Gate 2 v0 固定为 6 个任务，不在运行途中增删：

1. **明确顶层函数定位**：宽 `sed` 唯一映射到一个 function，答案完全位于函数内；
2. **明确 class method 定位**：宽 `sed` 唯一映射到一个 method，依赖 class header，但不依赖其他方法；
3. **缺失全局上下文风险**：目标 method body 引用 module constant 或 helper，正确回答必须确认其定义；用于观察主动补读；
4. **修改并测试**：初始 slice 足以完成一个局部修改，要求运行固定测试并核验 diff；
5. **歧义范围 fail-open**：`sed` 同时跨越两个 sibling，Native/CO 必须看到相同原始结果；
6. **超预算 fail-open**：单个完整语法单元超过冻结预算，Native/CO 必须看到相同原始结果。

前四项属于 activated economics；后两项只属于 fail-open correctness，不混入 activated-read 节省中位数。

如果显式 known-symbol 路径需要单独验证，可作为第 1 项的固定调用方式，不能临时增加第 7 个任务。

## 5. Correctness 判定

定位/回答任务使用机器可判定的精确答案；修改任务同时要求：

- 只修改允许的文件；
- diff 满足冻结断言；
- 固定测试命令退出码为 0；
- Native 与 CO 都完成任务；
- 不接受“最终答案看起来合理”代替测试或结构化判定。

Correctness 是硬门：任一 Native 成功而 CO 失败，即使 Token 更低也判 Gate 2 失败。

## 6. 调用归因

从 transcript 的已完成 tool call 与 `function_call_output` 建立一一对应，至少分类：

```text
initial_activated_read
same_intent_retry
adjacent_context_compensation
other_read_or_search
edit
test_or_build
other
```

### same-intent retry

命令规范化后再次读取同一路径、相同范围或相同 symbol，且意图没有改变。

### adjacent-context compensation

首次 slice 后，为补充同文件或直接相关文件中的 helper、constant、import、class sibling、caller/callee 而新增的 `cat/sed/rg` 或已知 symbol 读取。

测试、构建和编辑命令不能仅因产生 tool output 被误计为补偿读取。所有自动分类保留命令 hash、path、kind 和归因原因；不在公开汇总保存完整命令中的敏感参数。

## 7. 主经济指标

```text
Net activated-read saving
= Native 对应模型可见 read/search Token
- (
    CO 首次 syntax slice Token
    + same-intent retry 的模型可见 Token
    + adjacent-context compensation 的模型可见 Token
    + 其他由 slice 不足触发的 read/search Token
    + decision:block / Hook 错误反馈 Token
  )
```

若 CO 的模型可见 read/search 总量已经包含上述项目，不得重复扣除。

计量优先使用 transcript 中模型可见 `function_call_output`；字符除以四必须继续标记为 `chars_div_4_v1`，不能称为账单精确 Token。完整会话 `input + output` usage 作为次要传导指标单独报告。

## 8. Fail-open 统计

每个 CO 运行记录：

- 尝试激活次数；
- 成功 slice 次数；
- fail-open 次数；
- 枚举 reason；
- 原始/所需/预算字符；
- fail-open 后 correctness 与 Native 可见结果 hash 是否一致。

预期的 `syntax_range_ambiguous` 与 `syntax_slice_over_budget` 不算产品错误，但必须正确 passthrough。activated economics 不得用 fail-open 样本稀释或美化。

## 9. Gate 2 通过门槛

- [ ] 6 个任务的 Native/CO correctness 完全一致；
- [ ] 修改任务两组固定测试均通过且 diff 合规；
- [ ] 4 个 activated 任务的 Native canary 可见，CO canary 不可见且 syntax package 可见；
- [ ] activated-read 的 `Net saving` 中位数至少为 40%；
- [ ] same-intent retry 中位数为 0，任一任务不超过 1；
- [ ] 至少 3/4 activated 任务在计入全部补偿读取后仍为净节省；
- [ ] 歧义与超预算 fail-open 均返回 Native 等价结果，并有正确枚举原因；
- [ ] 至少一个 activated 任务完整会话 Token 低于 Native；
- [ ] 不出现预算绕过、Hook 循环或无法归因的额外读取。

完整会话配对比率中位数 `<=0.95x` 仍是 CO-1 Gate 3 的真实仓库目标，不强行作为六任务合成 Gate 2 的硬门。

## 10. 失败后的处理

- 若 correctness 下降：停止，不通过扩大包掩盖；先记录缺失证据类型和适用边界；
- 若补偿读取吃掉节省：标记触发场景，优先让该场景 fail-open，而不是自动加入更多上下文；
- 若 canary 仍可见：视为宿主/Hook 失败，停止经济计量；
- 若错误来自 runner 归因：只修 runner，保持切片实现和任务冻结；
- 若 Gate 2 通过：进入真实仓库 Gate 3；仍不自动开始 CO-2。

## 11. 明确不做

- 不修改 `python_syntax_slice.py` 的选择、import 或预算策略；
- 不调 Navigator/Ranker/Graph/Discovery；
- 不加入 cache、evidence dedup、search compression、embedding 或长期记忆；
- 不增加复杂 Shell parser；
- 不用 fail-open 样本冒充 activated saving；
- 不用首次 slice 大小替代补偿后净模型可见成本；
- 不在结果出来前宣称真实开发会话节省。
