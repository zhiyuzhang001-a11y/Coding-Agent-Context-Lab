# 基线实验记录

## B001：原生合并式文件读取

- 日期：2026-08-14
- Codex 任务 ID：`01a000f8-9861-7d93-ae65-b61c5ced0ad9`
- 工作目录：`plugins/agent-token-manager`
- 模式：只读；插件已安装；本次使用 `--dangerously-bypass-hook-trust` 运行经过审查的 Hook，未写入永久信任。
- 任务：分别读取 README、Hook 配置、审计脚本和状态文件并总结实现。
- 实际工具行为：Codex 将四次读取合并为一次 Bash `sed` 调用。

### Hook 观测

- 本地工具调用：1
- 工具：`Bash`
- 工具结果字符：5,695
- 工具结果字节：6,517
- 粗略估算结果 token：1,424
- 读取类结果占比：100%
- 完全相同结果重复次数：0

### Codex 会话 usage

- input tokens：34,107
- cached input tokens：26,112
- output tokens：603
- reasoning output tokens：146

### 初步结论

1. 插件 Hook 在真实 Codex 工具路径中正常触发，日志写入 `PLUGIN_DATA` 且权限为 `0600`。
2. 当前工具结果估算只覆盖文件读取返回内容，不应与整个会话 input tokens 直接比较；后者还包含系统提示、插件与技能说明、对话历史及缓存输入。
3. Codex 会主动合并多个文件读取，因此后续优化不能只按“工具调用次数”评价，还必须测量单次返回体积、实际使用符号和无关内容比例。
4. B001 是可用性基线，不是原生与 Smart Read 的对照实验；对照组需要在 `smart_read` 完成后使用同一任务重复运行。

### 可复现命令

```bash
codex exec --dangerously-bypass-hook-trust --sandbox read-only \
  --cd /path/to/plugins/agent-token-manager --json \
  '执行一次只读基线探索。请使用本地 shell 分别读取 README.md、hooks/hooks.json、scripts/audit_tool_output.py 和 STATUS.md，理解这个插件如何记录工具输出，然后给出简短总结。不要创建、修改或删除任何文件。'
```

## B002：Smart Read 首次调用烟雾实验

- 日期：2026-08-15
- Codex 任务 ID：`01a00104-7f1c-74b1-b61d-e61a5d2594bb`
- 插件版本：`0.1.0+codex.20260814160344`
- 任务：使用 `budgeted-code-reading` Skill，以 700-token 预算查询审计脚本中的 `build_record`、`is_read_like`、`append_record`、privacy 和 token，并说明实现。
- 结果：任务完成；AST 置信度高；完整返回 `build_record`、`is_read_like`，`append_record` 因预算截断，另省略 5 个区域。

### Token 观测

- Smart Read JSON 自报估算：688 token。
- Hook 观测 Smart Read 命令结果：964 token；其中包含系统 Python/xcrun 警告和 JSON 转义开销。
- 首次读取 Skill 说明：508 token。
- 首次调用两项工具结果合计：1,472 token。
- 目标源码全文件：4,314 字符，按同一方法粗估 1,079 token；这是静态参考，不是同会话原生对照。
- Codex usage：input 51,530，cached input 27,136，output 961，reasoning output 436。

### 结论

1. 核心选择结果 688 token，相对目标文件静态全量粗估减少约 36%；说明符号预算机制本身可工作。
2. Hook 实际看到的 Smart Read 返回为 964 token，相对静态全量仅低约 11%；运行时警告和 JSON 封装侵蚀了收益。
3. 首次加载 Skill 后合计 1,472 token，反而比静态全文件粗估高约 36%。Skill 加载成本可能在后续调用中摊销，但尚未通过实验确认。
4. B002 不是公平 A/B：它包含 Skill 首次加载，且缺少同一提示下的原生对照。不能据此宣称端到端节省。
5. 审计器原先未把 Python 启动的 `smart_read.py` 标为读取；已补测试并修复。

### 后续实验要求

- 用同一任务分别运行原生读取与 Smart Read，区分首次/热调用。
- 消除系统 Python 警告或改用无额外噪声的启动方式。
- 分别报告核心 payload、工具结果、Skill 加载和整个会话 usage，避免混用指标。

## B003：Serena 真实源码同任务 A/B（第一轮）

- 日期：2026-08-15
- 目标：`upstream/serena/src/serena/agent.py` 中 `ToolSet.apply` 与 `without_editing_tools`，并追踪 `ToolRegistry.check_valid_tool_name`。
- 评价：两组均正确覆盖 fixed、optional include、exclude、旧名映射、已删除/未知名称，以及两个方法的不变性与差异；答案质量在本轮视为相当。

### 原生组

- Codex 任务 ID：`01a00108-ac9e-7ff0-9547-2b1c829056b9`
- 行为：一次 `nl | sed` 读取 1–260 行，一次 `rg -C 8` 追踪校验函数。
- 工具结果粗估：3,028 + 441 = 3,469 token。
- 会话 usage：input 55,728，cached input 38,144，output 915，reasoning output 196。

### Smart Read 组

- Codex 任务 ID：`01a00109-7344-7323-bdbc-1ae1d62fa319`
- 插件版本：`0.1.0+codex.20260814160812`
- 行为：首次读取 Skill；outline；两次目标读取；`rg` 定位跨文件符号；再读取校验函数和旧名映射。
- 工具结果粗估：Skill 510 + 其余读取 2,692 = 3,202 token。
- 会话 usage：input 131,056，cached input 116,992，output 2,860，reasoning output 873。

### 结论与修正

1. 冷启动工具结果比原生少约 7.7%；若 Skill 已加载，读取结果少约 22.4%。
2. Smart 组轮次和说明文字过多，整个会话 usage 显著更差；这比单看 payload 更重要。
3. 不必要的 outline、重复返回 `ToolSet.apply`、单符号多次调用是主要浪费。
4. 已新增可重复的 `--symbol` 精确选择参数，可在一次调用中返回多个具名符号；Skill 改为“符号已知则跳过 outline、单次批量读取、不重复读取完整符号”。
5. 原生组的 `nl | sed` 曾被归类为非读取，说明第一版只检查命令首词不够；审计器现会识别流水线任意读取命令，并新增测试。

## B004：多符号批量读取优化复跑

- 日期：2026-08-15
- Codex 任务 ID：`01a0010e-483f-7c31-b851-8b16f227c5f0`
- 插件版本：`0.1.0+codex.20260814161356`
- 任务与质量标准：和 B003 完全相同；答案仍正确覆盖全部要求。
- 行为：Skill 加载一次；一次调用同时读取 `ToolSet.apply` 与 `ToolSet.without_editing_tools`；一次 `rg` 定位跨文件定义；一次精确读取 `ToolRegistry.check_valid_tool_name`。没有 outline 和重复符号读取。

### 结果

- Skill 说明：480 token。
- Smart Read 与定位结果：989 + 56 + 292 = 1,337 token。
- 冷启动工具结果合计：1,817 token。
- 相对 B003 原生组 3,469 token：冷启动约减少 47.6%，已加载 Skill 后约减少 61.5%。
- 相对 B003 第一版 Smart 组 3,202 token：冷启动约减少 43.3%。
- 会话 usage：input 88,586，cached input 78,592，output 1,586，reasoning output 471。

### 结论

1. 精确多符号批量读取显著降低了工具返回和调用数量，验证了“具名符号跳过 outline”的设计。
2. 整个会话 input 仍比原生组高约 59%，output 也更高；端到端尚未胜出。
3. 后续重点应从继续压缩单个 payload 转向：减少 Agent 说明文字、合并跨文件定位与读取、持久化符号索引、避免每次重新加载 Skill。
4. B003/B004 证明必须同时报告工具结果与整个会话 usage；只公布 payload 节省会产生误导。

## B005：M1 默认缓存首次真实验证（失败）

- 日期：2026-08-15
- Codex 任务 ID：`01a0033e-ed62-73d1-9724-dd56868efc26`
- 插件版本：`0.1.0+codex.20260815022701`
- 任务：同一 Serena 大文件分两次读取不同符号，验证第二次缓存命中。
- 结果：两次均正确路由为 `named_symbols`，输出约 864 和 299 token；但两次 `cache_status` 均为 `disabled`。
- 原因：普通 Skill shell 没有继承 Hook 使用的 `PLUGIN_DATA`，第一版没有其他默认缓存目录。
- 会话 usage：input 70,268，cached input 45,056，output 1,084，reasoning output 257。
- 处理：不将 M1 标记完成；增加权限受限的系统临时缓存回退后复测。

## B006：M1 路由与缓存修复验证（通过）

- 日期：2026-08-15
- Codex 任务 ID：`01a00341-4e45-7cb3-8c1b-2e9dc7a0a202`
- 插件版本：`0.1.0+codex.20260815022937`
- 任务：与 B005 相同；未显式传递缓存目录。
- 第一次 `ToolSet.apply`：`named_symbols`、cache miss、863 token。
- 第二次 `ToolSet.without_editing_tools`：`named_symbols`、cache hit、298 token。
- Hook 成功提取白名单元数据，报告累计 1 miss、1 hit；审计和缓存均未保存源码正文。
- 会话 usage：input 70,605，cached input 55,296，output 929，reasoning output 253。

### 结论

1. 小/大文件路由、多符号选择、内容哈希失效和跨调用缓存的 M1 最小闭环成立。
2. 缓存命中不会减少返回符号正文的 token；它当前减少的是本地重复解析，并为后续持久化符号图提供基础。
3. 无插件数据环境时缓存位于权限为 `0700` 的临时目录，文件为 `0600`；它可能被操作系统清理，尚不等同于可靠的长期索引。
4. 下一步要降低端到端 token，必须把跨文件“搜索 → 定位 → 读取”合成更少的调用，Serena 最小适配器是下一实验。

## B007–B009：Serena 原生最小后端

- B007（任务 `01a00349`）：首次启动失败，原因是上游目录被根 `.gitignore` 忽略，随后语言服务器又缺少 Node PATH。usage：input 148,710，cached 131,072，output 1,481，reasoning 697。
- B008（任务 `01a0034c`）：裁剪工具与描述后仍失败，原因是 MCP PATH 缺少 `uv/uvx`。usage：input 52,089，cached 44,288，output 424，reasoning 163。
- B009（任务 `01a0034d`）：补齐 uv 与 Node PATH 后成功。`find_symbol` 正确返回 `route_read` 第 15–48 行，`find_referencing_symbols` 正确返回 `main/result` 第 68 行这一处引用。
- B009 两次工具结果粗估分别为 385 与 113 token；usage：input 70,283，cached 61,440，output 588，reasoning 151。

结论：裁剪后的原生 Serena 接口可用，但 B009 完整 input 与 M1 的 B006（70,605）接近，没有达到至少 20% 的核心接纳门槛。

## B010–B012：单工具 `context_bundle` 适配器（阻塞）

- B010（任务 `01a00352`）：适配器按调用启动 Serena 子进程，约 20 秒后工具被取消。usage：input 33,304，cached 27,136，output 340，reasoning 102。
- B011（任务 `01a00353`）：MCP 启动和工具超时均配置为 120 秒，仍约 20 秒取消。usage：input 33,354，cached 27,136，output 417，reasoning 160。
- B012（任务 `01a00357`）：改为 FastMCP lifespan 启动时预热并复用 Serena 子进程，仍约 20 秒取消。usage：input 33,341，cached 27,136，output 378，reasoning 100。

结论：连续三次失败说明当前“Codex MCP → Python 适配器 → Serena stdio MCP”结构存在生命周期或外层取消问题。B010–B012 没有返回有效答案，其较低 input 不能算节省。纯合并器与预算测试保留，坏的 `context_bundle` 不在已安装插件中暴露；下一轮改评估单进程扩展或不同图谱后端。

## B013：阶段 1.5 环境与本地基准

- 日期：2026-08-15
- Git 基线：`0608150`。
- doctor：Python、Git、仓库身份、SQLite 数据目录与 ignore 检查全部通过；0 个必需错误。Serena 已发现；Codebase-Memory CLI 和 Repomix CLI 未安装，仅作为可选警告。
- 本地基准：2/2 用例通过。`audit-core-symbols` 返回两个预期符号，粗估结果 829 token；`router-entrypoint` 返回预期小文件区域，粗估结果 988 token。
- 本地延迟：本机本轮观测均约 0.6 ms；该数字只用于检测明显性能回退，不代表跨机器承诺。
- 离线测试：26 项通过。

结论：M2a 前置环境闭环成立。持久目录和 SQLite 当前只保存 schema、仓库元数据与解析结构缓存，尚未构建仓库级 Marker/Edge 地图；B013 也不包含 Codex 完整会话 usage，不能用于宣称端到端 token 节省。

## B014：M2a Serena 稀疏导航地图验证（通过）

- 日期：2026-08-15。
- 目标仓库：锁定的 Serena 工作树；发现 430 个 Python 文件。
- 索引结果：7,191 个 Marker、8,187 条 Edge，其中 1,426 条本地 import 关系；失败文件 0。
- 增量行为：修复重复定义稳定 ID 冲突后，补全索引耗时 0.90 秒；立即复跑时 changed=0、unchanged=430，耗时 0.17 秒。
- 查询任务：定位 `ToolSet.apply` 与 `ToolSet.without_editing_tools`，理解工具集合过滤与转换。
- 500-token 查询预算下正确返回两个目标方法、路径、签名、行号、证据哈希、展开成本和评分分解；结果粗估 364 token，耗时 0.30 秒。
- 对两个路标执行 Smart Read 完整证据展开，结果 1,021 token；定位加证据共 1,385 token。
- 隐私检查：SQLite 与查询结果不保存源码正文；单元测试以秘密正文哨兵验证。
- 质量反例：移除明确符号、只保留自然语言任务时，前两名为泛化 Tool 类，而非两个目标方法。

### 对照与结论

1. 单看首次精确定位载荷，364 相对 B003 原生工具结果 3,469 token 约少 89.5%；定位加完整证据共 1,385 token，约少 60.1%。
2. 如果文件和符号本来已经知道，B004 直接 Smart Read 为 1,337 token；增加地图查询后反而多约 3.6%。Skill 因此规定：未知位置或跨文件任务才查地图，已知精确位置直接展开。
3. M2a 达成结构索引、增量失效、解释性、隐私和硬预算目标；尚未达成自然语言语义检索，也未测量独立 Codex 任务的完整 input usage，不能宣称端到端节省已成立。
4. M2b 首先加入任务状态、已读去重、假设/反馈和停止规则，并把自然语言候选质量设为验收项。

## B015：M2b Task Navigator v0（固定基准通过，真实探针受限）

- 日期：2026-08-15。
- 固定基准：3 个不含文件名、类名或函数名的自然语言任务；静态 Top-K 与 Navigator 使用相同稀疏地图和预算。
- 正确率：静态与 Navigator 均为 3/3。
- stale-login：静态 2 次展开，Navigator 2 次，持平；Navigator 管理载荷 793 token。
- discount-charge：静态 3 次展开，Navigator 2 次；管理载荷 693 token。
- search-relevance：静态 3 次展开，Navigator 2 次；管理载荷 706 token。
- 总结：2/3 更少展开、1/3 持平，满足预先固定的“多数任务改善且正确率不降”验收标准。

### Serena 非门控真实探针

- 任务：不提供代码标识符，询问可选工具如何加入或排除活动工具集合；已知正确区域为 `ToolSet.apply`，但不向初始查询注入。
- Navigator 先选择 `RemoveProjectTool`，再选择 `SerenaInfoTool`；人工 Feedback 均判定无关，累计管理载荷 1,607 token 后以 `low_expected_gain` 停止，剩余 1,993 token，未找到目标。
- 原因：当前图只有 contains/imports；证据暴露 `ToolMarkerOptional` 继承标记，但没有继承或引用边把它连接到处理集合的逻辑。
- 探针发现小文件回退全文问题：已知 Marker 的第一次展开返回 694 token 且截断。新增 `forced_named_symbols` 后复测同一 Marker 为 306 token、未截断，下降约 55.9%。

### 结论

1. 八项 M2b v0 机制与固定验收全部通过；40 项离线测试覆盖任务隔离、持久化、去重例外、反馈排序、预算、停止、隐私和对照基准。
2. 固定合成任务只能证明反馈闭环有效，不能代表大型真实仓库的语义导航已经解决。
3. 下一步不继续堆词法权重；M2c 先补继承、调用/引用关系，并用同一 Serena 任务作为回归门槛。
4. 仍未运行独立 Codex 任务的完整 usage 对照，因此不宣称端到端 input 已节省。

## B016：M2c 关系导航与统一 Provider 报告（通过）

- 日期：2026-08-15。
- 目标仓库：Serena commit `3ad624f511511bb7a77447e413425198fc574349`，430 个 Python 文件。
- 索引：7,191 个 Marker、16,370 条可解析 Edge；其中 imports 1,426、inherits 372、calls 4,408、references 3,403；失败文件 0。
- 增量：立即复跑 `changed=0`、`unchanged=430`；删除测试确认 outgoing/incoming 同步失效且无悬空 Edge。
- 低置信线索：26,524 个未解析外部或歧义关系单独保留，不进入高置信图传播。它们增加本地数据库大小但不直接注入模型上下文，M2d 需要继续压缩其存储范围。

### B016a：首次门控失败与修正

第一版把所有关系的原始边数直接加入中心性，5 个真实任务中 M2b 错误停止 4 个、M2c 5 个，明确退化。随后依次修正：限制语义中心性、区分关系方向、降低未验证自动名称权重、让无关节点的自动发现线索失效，并为任务词加入稀有词与保守前缀匹配。失败结果未用于验收。

### B016b：5 个真实自然语言任务

- 所有任务不含文件名、类名或函数名；两组使用同一索引、任务、正确目标和硬预算规则。
- M2b：正确 2/5，错误停止 3/5。
- M2c：正确 3/5，错误停止 2/5；减少 1 个，即 33.3%，正确率未下降。
- B015 可选工具任务：M2b 8 次候选后错误停止，管理载荷 5,221 token；M2c 5 次候选到达 `ToolSet.apply`，管理载荷 3,169 token，关系驱动步骤 4 次。
- 其余两项共同通过：符号引用查询、项目激活。仍失败：配置工具名校验、只读工具集合；这两项固定为 M2d 回归目标。

### 统一 Provider 报告

- 内置 AST：执行完整自然语言导航门控并通过上述错误停止改善标准；冷索引约 2.02 秒，本次临时 SQLite 约 34.4 MB。
- Serena：在同一 5 个目标、1,200-token 单次预算下，使用 benchmark oracle 路径和符号完成精确取证 5/5；启动约 2.75 秒，单次约 107–133 ms，返回 175–1,166 token。
- Serena 为避免目标仓库额外 TypeScript server 的 npm 依赖，在临时源码快照中只启用 Python LSP；不修改锁定工作树。
- Codebase-Memory：CLI 未安装，统一报告为 `skipped`，内置 Provider 仍通过。

结论：M2c 的关系增量、预算、B015 与真实错误停止门槛成立。Serena 的 5/5 只证明“已知目标后的精确取证”有效，不能和内置自然语言导航正确率直接比较；Codebase-Memory 也尚无实际性能结果。因此下一步是 M2d 的无 oracle Provider 路由与剩余语义候选修复，而不是宣称所有后端已等价接入。
