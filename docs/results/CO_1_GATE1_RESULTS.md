# CO-1 Gate 1 结果：Python 完整语法切片

最后更新：2026-08-15

状态：**通过。CO-1 仍默认 observe；尚未运行真实 Codex correctness / 完整会话经济实验。**

## 1. 冻结实现

新增独立 `scripts/python_syntax_slice.py`，使用 Python 标准库 AST：

- 支持顶层 function、async function、class，以及 class 的直接 method / async method；
- 显式 symbol 支持 `name` 与 `Class.method`；
- `sed` 优先选择唯一相交的最具体 function/method，跨 sibling 时拒绝猜测；
- method 返回 enclosing class header 加完整 method；
- 切片保留 decorators、signature、docstring 与完整 body；
- 只补充 `from __future__` 和 decorators/signature/class bases 直接使用的 import；
- 返回 path、symbol、kind、lines、file hash、省略行数、未附带支持名称和 continuation；
- 语法单元不可拆，超预算、解析失败、歧义或替代不经济时 fail-open。

CO-1 通过 `AGENT_TOKEN_MANAGER_CO1_MODE=enforce` 显式启用；插件与 CO-0 一样继续默认 observe。裸 `cat` 不进入 CO-1 symbol 猜测。

## 2. 测试结果

源码版：

```text
python3 -W error -m unittest discover -s plugins/agent-token-manager/tests -p 'test_*.py'
Ran 113 tests
OK
```

安装版：

```text
<installed-plugin-path>
Ran 113 tests
OK
```

覆盖：

- function / async function / class / method / async method；
- decorators、docstring、多行 signature、完整控制流 body；
- method enclosing class header 与 sibling 排除；
- `__future__`、直接签名/装饰器 imports 与无关 import 排除；
- 唯一 `sed`、跨 sibling `sed`、重名 bare symbol；
- Python syntax error、source unavailable、over-budget；
- Hook `decision:block` 替代包与原始大 payload 排除；
- bare `cat` 保持 CO-0 路径；
- 105 项旧测试零回归。

严格 ResourceWarning-as-error 检查和插件规范验证均通过。源码与安装缓存逐文件一致。

## 3. 项目自身大文件离线 smoke

该 smoke 比较“整文件字符数”与“完整 CO-1 决策包字符数”，预算临时设为 12,000 字符，只用于确认切片本身是否有压缩空间：

| 目标 | 整文件字符 | 切片包字符 | 字符下降 |
| --- | ---: | ---: | ---: |
| `context_optimizer_hook.py::classify_command` | 16,577 | 2,417 | 85.42% |
| `context_optimizer_hook.py::evaluate_event` | 16,577 | 7,954 | 52.02% |
| `navigation_contract.py::Marker` | 6,589 | 2,127 | 67.72% |

中位字符下降为 **67.72%**。这不是 Gate 2 正式 Token 指标，因为：

- 比较基线是整文件，不是 Native Codex 在同一任务中的实际读取路径；
- 字符除以四仍只是 Token 粗估；
- 没有模型 correctness、重试、补偿工具调用或完整会话 usage；
- 使用 12,000 字符实验预算，高于 CO-1 当前默认 4,000 字符；`evaluate_event` 在默认预算下会正确 fail-open。

## 4. Gate 1 结论

Gate 1 通过：CO-1 已具备保守、完整、可预算、可回退的 Python 语法切片能力，并且没有破坏旧 CO-0、Navigator、Hook、Skill 或插件测试。

尚不能声称：

- 真实任务 correctness 已与 Native 持平；
- activated read Token 已稳定降低 40%；
- 完整会话达到 5%–10% 节省；
- `decision:block` 在 CO-1 较大语法包下仍然不会诱发补偿行为。

下一步是 Gate 2：冻结少量 Native/CO 配对任务，以模型最终可见内容验证 correctness、canary、重试、补偿调用和 activated read Token。Gate 2 前不加入 CO-2 缓存或 CO-3 搜索压缩。
