# Agent Token Manager：目标与实施计划

最后更新：2026-08-19

## 冻结决策

项目已于2026-08-19正式结项，状态为 `RESEARCH_COMPLETE / PRODUCT_NOT_VALIDATED / MAINTENANCE_ONLY`。本文保留为完整历史路线，不再代表活动 roadmap。项目总括、价值定位、已证明/未证明事项与重新开启条件见 `PROJECT_CLOSURE_AND_VALUE.md`。

Transparent Smart Read 产品线已经完成研究闭环并正式冻结：`status=BLOCKED_HOST_INTERFACE`、`algorithm_status=NOT_FALSIFIED`、`product_status=FROZEN`。当前宿主层缺少保持工具成功语义的通用模型可见结果替换接口，因此不进入 CO-2，也不再扩 shell parser 或寻找当前 Hook 的旁路 hack。完整结论、证据、停止范围和重启条件见 `TRANSPARENT_SMART_READ_FROZEN.md`。

本文下方尚未勾选的 M2/CO 条目均为历史路线记录，不再视为当前待办。ACP-0 至 ACP-1.3D 已完成冻结范围内的 measurement、attribution 与 candidate-specific causal validation。ACP-1.4 的历史 `INSUFFICIENT_COVERAGE` 保持冻结；ACP-1.4C 已修复 Bash benchmark coverage 并完成新的 8-case combined formal，但因 3 个 Read/Search Treatment 未达到冻结 activation Gate，联合结论仍为 `INSUFFICIENT_COVERAGE`。当前不将候选、cycle 体量、pilot 或局部实验差值外推为全局浪费或产品节省量。

长期治理约束见 `LONG_TERM_CONSTRAINTS.md`。每项新功能开始前必须回答其中的“开发前五问”，并在进入核心前完成真实任务、baseline、成本与消融记录。

## 总目标

减少编码 Agent 因无效、过宽和重复读取源码产生的上下文 token，同时以测试结果和源码证据保护任务质量。

第一阶段只解决“看清浪费发生在哪里”；第二阶段再引入智能读取和自动路由。所有节省数字都必须来自可复现实验，不采用上游项目的宣传数字作为本项目承诺。

## 产品原则

1. 最小证据：模型只接收当前决策需要的代码。
2. 渐进展开：项目地图 → 符号概要 → 关系 → 实现片段 → 必要时完整文件。
3. 本地优先：AST、LSP、哈希和 token 统计尽量在本地完成。
4. 可验证：准备修改前读取真实实现，高风险任务必须验证调用者和测试。
5. 隐私默认：审计日志默认不保存源码正文、完整命令或工具输出。
6. 失败开放：早期管理器故障不阻断 Agent 工作。

动态路标与上下文导航仍作为研究基础，见 `SMART_READ_DESIGN.md`。M2e 实验进一步证明显式多轮 Navigator 会产生系统级编排成本，而最多两次的 Compact 又无法保持导航 Recall；产品主线因此转为透明 Context Optimization Layer：保留 Codex 的语义循环，只优化每次进入模型的 read/search 上下文。正式决策见 `CO_0_IMPLEMENTATION_PLAN.md`。

## MVP 路线与状态

- [x] 建立 Codex 插件骨架。
- [x] 实现 `PostToolUse` 审计 Hook，记录本地工具输出大小、估算 token、哈希、工具名和明确路径字段。
- [x] 实现首个汇总报告：总工具调用、读取类输出占比、按工具统计和相同结果重复次数。
- [x] 添加离线单元测试，验证隐私约束和重复结果检测。
- [x] 浅克隆并锁定 Codebase-Memory、Serena、Repomix 的当前 commit，供后续评估；排除 Codebase-Memory 的大型 vendored grammar 工作树。
- [x] 建立仓库内 `personal` 开发 marketplace，并将插件调整为标准 `plugins/agent-token-manager` 布局。
- [x] 安装插件并通过一次性审查绕过验证 Hook，采集第一个真实基线会话 B001。
- [ ] 在 Codex Hooks 界面完成人工审查和永久信任；该安全确认不自动代替用户执行。
- [ ] 增加精确 tokenizer；已确认官方精确计数接口，但生产 Hook 默认不上传源码，当前环境也无 API key。日志已明确标记 `chars_div_4_v1`，后续实现显式 opt-in 校准器。
- [x] 建立 `smart_read(path, query, budget)`，支持文件概要、目标符号和完整源码三级读取；已提供自动发现 Skill 和 3 项专项测试。
- [x] 完成 M1 智能路由与结构缓存：小文件直读、大文件按目标分流、内容哈希失效、缓存 hit/miss 审计；B006 真实验证通过。
- [x] 跑通 Serena 原生最小后端：只暴露符号查找和引用查找，B009 正确完成同类任务。
- [ ] 单次 `context_bundle`：合并与预算逻辑已完成，但嵌套 MCP 在 B010–B012 中持续被取消，当前标记为阻塞且不对外暴露。
- [ ] 识别 `cat`、`sed`、`rg` 等大范围读取并先给出建议，不强制阻断。（候选检测与报告已完成；Agent 可见建议待完成）
- [ ] 在 10–20 个真实任务上比较原生读取与 Smart Read 的 token、时间和测试通过率。
- [x] 完成 Serena、Codebase-Memory、Aider Repo Map、Stacklit、AgentMemory 与 Repomix 的能力和 token 机制拆解；记录采用顺序与统一接纳门槛。

## 后续阶段

### 阶段 1.5：环境与接口基线（M2a 前置）

- [x] 建立首个 Git 基线 `0608150`；上游源码、运行缓存和本机 Serena 覆盖配置均已排除。
- [x] 定义最小 Provider 契约：`index`、`query`、`expand`、`invalidate`，统一版本化请求、Marker/Edge、证据与错误格式。
- [x] 建立项目级私有持久数据目录、稳定仓库身份和 SQLite v1 schema；显式参数和插件数据目录按仓库隔离。
- [x] 建立 `doctor.py` 环境自检：Python、Git、仓库、数据权限、忽略规则和可选后端。
- [x] 建立 `run_benchmarks.py` 与版本化用例，记录质量、预算、路由、缓存和本地延迟。
- [x] 移除默认插件中写死本机路径的 Serena MCP；Serena保留为后续运行时发现的可选 Provider。

### 阶段 2：预算化智能读取

- Tree-sitter 提取文件结构、符号签名和语法边界。
- 任务相关排序与硬 token 预算。
- [已完成基础] 内容哈希结构缓存和重复读取检测；diff-aware 增量返回待实现。
- 输出省略说明、置信度、行号和 continuation handle。

### 阶段 2.5：稀疏导航地图与任务导航器

- [已完成前置] 定义版本化 Marker/Edge schema，包含身份、证据、版本、置信度、价值和展开成本。
- [x] M2a：复用当前 AST 与哈希缓存生成结构节点、包含关系和导入关系，并写入 SQLite。
- [x] 在 token 预算内按任务、符号和路径返回 Top-K 路标及可解释评分，不保存源码正文或批量生成长摘要。
- 维护已读节点、待验证假设、风险与剩余预算，形成“选择 → 读取 → 更新 → 停止”的导航循环。
- 后续把 Serena 和 Codebase-Memory 作为可替换 Marker Provider 接入统一契约。

#### M2b v0 验收标准

- [x] 每个自然语言任务使用独立稳定 `task_id` 和持久化 `TaskState`，任务之间状态不互相污染。
- [x] 区分并记录 `seen`、`selected`、`expanded` 与 `verified` Marker。
- [x] 相同 `marker_id + evidence_hash + region` 默认不重复返回源码；哈希变化、上次截断或显式 `force_expand` 可重读。
- [x] 每次读取后保存结构化 Feedback：相关性、信息增益、支持/否定假设、新符号/路径、下一步提示和消耗 token。
- [x] Feedback 可观测地改变下一轮候选排序，并输出 `feedback_boost`、`already_expanded_penalty` 等原因。
- [x] Navigator 管理的地图结果与证据展开严格遵守 `total/navigation/expansion/remaining` Hard Token Budget。
- [x] 所有终止状态都有枚举化 `stop_reason`、停止证据、剩余预算和未解决假设。
- [x] 3 个无文件名、类名和函数名的固定任务上，与相同初始地图和预算的静态 Top-K 对照；3/3 正确，2/3 更少展开，1/3 持平。真实 Serena 非门控探针仍暴露关系覆盖不足，见 B015。

### 阶段 3：结构和语义适配器

- 评估 Codebase-Memory 作为结构图谱后端。
- 评估 Serena 作为符号读取、引用和精确编辑后端。
- 借鉴 Aider Repo Map 的动态预算与依赖图排名。
- 将 Repomix 用作 token 统计和基准输入工具，而非核心运行时。

#### M2c 验收标准

- [x] 支持 `inherits`：仓库内基类解析为 Marker，外部名称保留但降低置信度，Edge 带文件、行号和证据哈希。
- [x] 支持 `calls`：覆盖可静态解析的仓库内直接函数、同类方法和明确属性调用；动态调用不得伪装成高置信关系。
- [x] 高价值 `references` 仅覆盖类型注解、装饰器、明确符号导入、继承及注册表/构造器中直接传递的类或函数对象。
- [x] 新关系支持内容哈希增量索引、源文件 outgoing 清理、目标删除 incoming 清理和零悬空 Edge；立即复跑 changed=0。
- [x] Edge 计入 navigation payload，不破坏 total/navigation/expansion/remaining Hard Token Budget；预算不足明确省略或停止。
- [x] Feedback 确认相关节点后，其关系邻居按 Edge 类型和方向动态升序，输出 `relationship_boost`、关系类型和来源；无关分支及其自动发现线索不扩散，证据仍去重。
- [x] B015 Serena 断路任务在 3,600 总预算内到达 `ToolSet.apply`；固定门控复跑管理载荷 3,169 token，低于 M2b 错误停止时的 5,221 token。
- [x] 5 个真实无代码标识符任务中，M2c 相比 M2b 错误停止从 3 降到 2（减少 1 个，33.3%），正确率不下降。
- [x] 内置 AST、Serena、Codebase-Memory 使用相同 Serena commit、5 个任务和预算口径生成统一报告；Serena 5/5 精确取证通过但明确不冒充自然语言导航，Codebase-Memory CLI 缺失时跳过且不阻断内置 Provider。
- [x] 全部旧测试继续通过，并新增继承、调用、reference 白名单、低置信动态调用、增量删除、无悬空 Edge、关系排序/方向、Edge 预算、不可展开节点、B015 与 benchmark schema 测试。

### 阶段 4：工作记忆

- 保存目标、架构决策、已修改符号、测试结果、失败方案和未完成项。
- 根据文件哈希、Git commit 和事实类型设置失效策略。
- 压缩前保存最小 checkpoint，避免恢复整个会话源码。

### CO 产品主线：透明上下文优化

- [x] CO-0：验证白名单 read/search 的 Hook/interface 可行性，以模型最终可见内容而非 Hook 执行为验收依据；冻结矩阵接口门 7/7、完整会话配对中位比率 `0.9931x`。
- [x] CO-1 研究线完成并冻结：Syntax-aware Read Slicing 的 Gate 1 通过；Gate 2 为否定结果，6/6 correctness 一致、补偿后 activated read 中位节省 42.715%，但 0/4 activated 任务完整会话低于 Native。后续 1.1–1.4 已把阻塞定位到宿主接口。详见 `CO_1_GATE2_RESULTS.md` 与 `TRANSPARENT_SMART_READ_FROZEN.md`。
- [x] CO-1.1：Hook-only Cost Isolation。6 场 Pilot correctness/tool calls/model cycles 一致；observe−native 为 +36/+10，中位 +23 Token（约 0.074%）；rewrite−observe 为 +105/−25，方向不一致。最小 Hook 不是原 0.7% 的主要固定成本嫌疑，按停止规则不进入 27 场矩阵。详见 `CO_1_1_RESULTS.md`。
- [x] CO-1.2 离线 Gate：在独立 Hook-only 实验宿主中加入确定性 compensation-risk 分类，只对局部语义闭包充分且同时满足绝对 200 Token/40% 比例门槛的读取切片；module global/import/helper、class state/sibling method、动态语义、显式高风险意图、歧义和低收益均可解释 fail-open。离线回归通过，真实 Native/CO A/B 尚未运行。详见 `CO_1_2_PLAN.md` 与 `CO_1_2_OFFLINE_RESULTS.md`。
- [x] CO-1.3：冻结 `b506818` 的 Hook-only+Gate 完成 12 任务、24 场自然行为 A/B。correctness 12/12 一致，但实际激活 0/12；16 次尝试为 12 次 unsupported request 和 4 次 non-unique target。完整 Token 配对中位 `0.999391x`，pooled `0.963061x`，但因无 replacement、6 对下降/6 对上升而不可归因为优化。判定 Fail，不进入 CO-2，下一步调查自然 read/search 宿主层。详见 `CO_1_3_RESULTS.md`。
- [x] CO-1.4 Host Path Reconnaissance：1.4a 对 16/16 自然 code-bearing result、17,651/17,651 模型可见 Token 和 raw→Hook→transcript 均达 100%，确认统一观察点；1.4b 4/4 canary 可见、raw 完整、无新增 cycle/tool call，但通用替换依赖 `decision:block`，4/4 被包装为 `Script failed / Script error`。透明成功语义 Gate 失败，暂停透明 Smart Read，不进入 CO-2；保留 100% Bash 观察覆盖用于 Agent Cost Profiler。详见 `CO_1_4_RESULTS.md`。
- [冻结，未开始] CO-2：Model-visible Evidence Dedup。
- [冻结，未开始] CO-3：Search Compression。
- [冻结，未开始] CO-4：Unified Visible-context Budget。
- [冻结，未开始] CO-E2E：Native vs CO 完整会话 A/B。

CO 主线不占用 M3；M3 继续用于长期记忆。Old M2d 与 Compact 均冻结为研究分支，不删除、不切换默认 Skill。

### 独立候选主线：Agent Cost Profiler

- [x] ACP-0：Agent 成本计量合同与覆盖基线。`ACP-0 Measurement Foundation — COMPLETE under frozen validation scope`；适用范围、限制与重新校准条件见 `ACP_0_VALIDATION_SCOPE.md`。
  - [x] ACP-0.0：冻结 `acp-event-v1` / `acp-measurement-v1` / `acp-privacy-v1`、五种 coverage state 与 CO-1.4 脱敏 replay fixture；保留 16/16 call、17,651/17,651 model-visible Token 基线。
  - [x] ACP-0.1：独立 privacy-safe collector migration；ACP Hook chain 只注册 collector，HMAC 伪名/closed allowlist/replay parity/无输出/fail-open 五个 Gate 通过。
  - [x] ACP-0.2：冻结 `normalized-event-v1` / `transcript-call-v1` / `coverage-ledger-v1`；唯一稳定关联、unknown/denominator ledger、paired/synthetic deterministic replay 六个 Gate 通过。
  - [x] ACP-0.3：冻结 `fact-report-v1` / `acp-reporter-v0.1`；四层 fact、下钻、traceability、coverage-aware JSON/Markdown 与 CO-1.4 parity 六个 Gate 通过。
  - [失败] ACP-0.4：12/12 pair correctness、host/fail-open、真实 activation、cycle/call 和 paired-median Token 门通过；pooled session Token ratio `1.027420` 超过冻结上限 `1.02`，因此 ACP-0 不毕业。
  - [不确定] ACP-0.4a：120/120 重复 run 完成；pooled ratio `1.007010`、conditional ratio `0.999022`、95% 同路径覆盖且无预注册路径信号，但一个 case 在 OFF/ON 均为 `3/5` correctness，硬门失败，ACP-0 仍不毕业。
  - [x] ACP-0.4b：审计确认争议题唯一但 Native 本身随机；OFF-only `14/20` 冻结为 stochastic diagnostic，随后全新 OFF/ON 为 `12/20` 与 `13/20`，accuracy delta `+0.05` 通过预注册 `-0.10` Gate。组合 0.4a cost/path/host 证据后 ACP-0 毕业。

ACP-0.0–0.4b 均未执行结果替换、slicing、实时推荐或 waste/avoidable 判定。ACP-0.4 的失败与 0.4a 的 inconclusive 保持冻结；0.4b 未删除错误 run、未放宽 Token Gate，correctness runs 未混入 cost/path Gate。旧 audit v1 和 optimizer 研究代码继续保留，但已从 ACP Hook 执行链移除。

- [x] ACP-0H v1：`COMPLETE`。provenance、artifact chain、recalibration automation、benchmark governance 与 ACP-1 首份正式 manifest 集成已全部验收。详见 `ACP_0H_IMPLEMENTATION_PLAN.md`。
- [x] ACP-1.0：`COMPLETE under frozen experiment scope`。canonical attribution JSON、Markdown/CLI renderer、governed baseline index 与 experiment manifest 已冻结；JSON 仍是唯一事实源，不新增 diagnosis。详见 `ACP_1_0_IMPLEMENTATION_PLAN.md` 与 `ACP_1_0_VALIDATION_SCOPE.md`。
- [x] ACP-1.1：`COMPLETE under frozen experiment scope`。只建立 within-session objective evidence relation，多 relation 不重复计 Token，path/range/cycle/content unknown 不填补，不判断重复是否必要。详见 `ACP_1_1_IMPLEMENTATION_PLAN.md` 与 `ACP_1_1_VALIDATION_SCOPE.md`。
- [x] ACP-1.2：`COMPLETE under frozen experiment scope`。仅输出 high-cost、concentration 与 repeated/overlapping evidence 实验候选；正式 catalog 含 5 个 high-cost call candidate，其 observed exposure 为 10,735 Tokens，全部保持 necessity unknown、causal untested、validation blocked，未产生 waste/avoidable/savings 估计或 recommendation。详见 `ACP_1_2_IMPLEMENTATION_PLAN.md` 与 `ACP_1_2_VALIDATION_SCOPE.md`。
- [x] ACP-1.3A：`COMPLETE under frozen experiment scope`。120/120 私有历史 run 精确关联到 287 个 host cumulative usage snapshot，OFF primary/ON replication 分开；cycle 1–3 增量中位数温和上升，未证明快速加速，cycle 4 因每臂 n=1 标记 insufficient。新/历史上下文与因果成本保持 unknown。详见 `ACP_1_3A_IMPLEMENTATION_PLAN.md` 与 `ACP_1_3A_VALIDATION_SCOPE.md`。
- [x] ACP-1.3B：`COMPLETE under synthetic frozen experiment scope`。以新的 replay-qualified synthetic evidence case 验证 source-level intervention harness：Control-only 20/20，paired 两臂各 5/5 正确且 success semantics/tool path/cycles 一致，evidence estimate activation 为 `49.757591%`。未验证历史 candidates，生产 Host rewrite 仍 blocked，不得声称 savings。详见 `ACP_1_3B_IMPLEMENTATION_PLAN.md` 与 `ACP_1_3B_VALIDATION_SCOPE.md`。
- [x] ACP-1.3C：`COMPLETE under frozen experiment scope`。4 个 prospective natural case 各运行 Native ×20，80/80 correct/completed；按冻结 recurrence/path Gate 得到 2 qualified、1 diagnostic-only、1 rejected。ACP-1.3D 仅可消费 `natural_signature_limit_v1` 和 `natural_command_shape_v1`，本阶段未执行 intervention。详见 `ACP_1_3C_IMPLEMENTATION_PLAN.md` 与 `ACP_1_3C_VALIDATION_SCOPE.md`。
- [x] ACP-1.3D：`COMPLETE under frozen experiment scope`。只对 1.3C 的两个 qualified case 执行预注册 source-level Treatment；formal Control/Treatment 各 40 run，两个 case 均为 20/20 vs 20/20 correct，G1–G8 全通过。evidence reduction median 为 `62.609971%` 与 `49.696233%`，tool/cycle delta median 均为 0；session ratio 只作冻结 scope 描述，不构成 production/global savings claim。详见 `ACP_1_3D_IMPLEMENTATION_PLAN.md` 与 `ACP_1_3D_VALIDATION_SCOPE.md`。
- [停止] ACP-1.4：`INSUFFICIENT_COVERAGE under frozen experiment scope`。8 个 prospective case 完成 Native ×10：Read 3/3、Search 3/3 qualified，Bash 0/2；不新增替代任务、不降低 Gate。Read/Search family pilot 激活并通过，Bash 无 representative，故 formal generalization 未启动。详见 `ACP_1_4_IMPLEMENTATION_PLAN.md` 与 `ACP_1_4_VALIDATION_SCOPE.md`。
- [x] ACP-1.4C：`COMPLETE — BASH COVERAGE REPAIRED / GENERALIZATION INSUFFICIENT under frozen experiment scope`。Bash v1 历史失败不重评分；prospective v2 得到 2/3 qualified，两个 Bash formal case 均 PASS。新的 8-case combined formal 为 5 PASS / 0 FAIL / 3 INCONCLUSIVE；三个 inconclusive 都是 evidence reduction 未达 35% activation Gate，没有 correctness/path/cycle/success-semantics failure。194-run chain 已冻结，仍不声明跨家族泛化或全局节省。详见 `ACP_1_4C_IMPLEMENTATION_PLAN.md` 与 `ACP_1_4C_VALIDATION_SCOPE.md`。
- [x] ACP-1.4D：`COMPLETE under frozen audit scope`。不运行新 Agent，只审计 1.4C 的 60 个既有 Control/Treatment run：Read prefix 与 budget-stop search 为 `RULE_MISMATCH`；token-router search 为 host output saturation 导致的 `MEASUREMENT_MISMATCH`。35% Gate 与三个 INCONCLUSIVE 不变；三者只获得 prospective v2 准入建议，尚未运行 v2。详见 `ACP_1_4D_IMPLEMENTATION_PLAN.md` 与 `ACP_1_4D_VALIDATION_SCOPE.md`。
- [x] ACP-1.4E：`COMPLETE — ACTIVATION_RESOLVED under frozen v2 experiment scope`。三个 prospective v2 case 全部 Native 10/10 correct/recurrence/path；6-run pilot 排除于正式统计；60-run formal 中三个 case 均 10/10 vs 10/10 correct、G1–G8 PASS，activation median 为 `81.310680% / 76.190476% / 98.579189%`。这只解决三个历史 blocker，不重评分 v1，也不构成 combined/global generalization。详见 `ACP_1_4E_IMPLEMENTATION_PLAN.md` 与 `ACP_1_4E_VALIDATION_SCOPE.md`。
- [x] ACP-1.4F-0：`COMPLETE under frozen contract scope`。在 0 Agent run 下冻结 12 个全新 prospective case（Read/Search/Bash 各 4）、3 个 project form、独立 oracle registry、八字段 no-oracle builder 输入合同、R1/S1/B1 确定性模板、formal admission/overall denominator、G0 版本失效规则与 366-run 硬上限；定向 9/9、frozen-index verifier 与全量 405/405 通过。F-1 Native qualification（120 runs）已具备条件但尚未启动，不声明 activation 或 generalization。详见 `ACP_1_4F_IMPLEMENTATION_PLAN_DRAFT.md` 与 `ACP_1_4F_F0_VALIDATION_SCOPE.md`。
- [停止] ACP-1.4F-1：`INSUFFICIENT_NATIVE_COVERAGE under frozen v2.1 scope`。F-1 前在 0 Agent run 时补齐 candidate identity 并重新冻结 v2.1；正式 55 attempts 中 54 completed 且 54/54 correct，1 次在停止时 interrupted。Read 四 case dominant path `9/10、7/10、5/10、5/10`，最多 1 个 qualified；Search 首 case recurrence 2/10，第二 case 前 4 次 0/4，最多只能形成 2 个 Search qualified。两家族均不可能达到 `>=3/family`，因此剩余 65 runs 不启动，F-2/pilot/formal blocked。详见 `ACP_1_4F_F1_VALIDATION_SCOPE.md`。
- [x] ACP-1.4F-R：`COMPLETE under read-only audit scope / PROCEED_TO_BENCHMARK_DEVELOPMENT_POOL`。以 0 Agent run 审计 v2.1 的54份 completed artifact：54/54 均有唯一 request-related、intervention-compatible carrier；Read 40/40 为 `bash_sed`，Search 14/14 为 `bash_rg`。发现12个 Search identity false negative，以及19个含工具发现/非执行元调用、会分裂完整 trajectory 的 run。结论只支持设计独立 development pool，不重分类 v2.1、不授权新 runs、不测试 R1/S1/B1。未来 runner 的 case/family futility 纯函数与测试已加入，但未修改冻结 v2.1 runner。详见 `ACP_1_4F_R_IMPLEMENTATION_PLAN.md` 与 `ACP_1_4F_R_AUDIT_RESULTS.md`。
- [停止] ACP-1.4F-D：`COMPLETE / BENCHMARK_SEMANTICS_NOT_SUPPORTED under frozen development protocol`。冻结24个全新 development cases 后完成72-run Screen，并对7个准入 case 执行 Extension；automatic futility 在总计110/240 completed、110/110 correct 时停止。4个 qualified case 全部为 observed `search_like`，Read/Structured 均为0，未达到至少两个 supported families 的 subset 下限。R1/S1/B1 与 intervention 未使用；不创建 v3、不建立新 holdout。详见 `ACP_1_4F_D_RESULTS.md`。

## 当前完成定义

“输出审计 Hook”在以下条件全部满足时视为完成：

- 插件包含可发现的 `hooks/hooks.json`。
- Hook 对所有受支持的本地 `PostToolUse` 事件运行。
- 默认不保存原始工具输入和输出。
- 能汇总估算输出 token 与重复结果。
- 离线测试通过。

实现已满足以上代码和离线测试要求。真实 Codex 会话验证仍是下一步，不混入本条完成状态。

## 历史待办（项目已结项，不再执行）

以下内容保留当时的路线语境，不构成当前授权或活动计划。

1. 在 Codex Hooks 界面审查并永久信任插件 Hook。
2. [已完成] 更新已安装插件并运行 Smart Read 烟雾实验 B002；结果显示首次调用开销仍需优化，详见 `BASELINES.md`。
3. [已完成] 已消除启动警告，完成同任务原生/Smart A/B 与优化复跑 B004；工具结果显著下降，但端到端 usage 尚未胜出。
4. [进行中] 大范围读取候选检测与报告已完成；下一步添加低噪声的 Agent 可见提示，不强制阻断。
5. 在具备显式 API 授权或跨平台本地 tokenizer 后完成精确计数校准。
6. [已完成] Serena 原生 `find_symbol` 与 `find_referencing_symbols` 最小后端及 B009 验证。
7. [暂停] 嵌套 MCP `context_bundle` 连续三次被取消；不再沿当前包装结构投入时间。
8. [已完成] 阶段 1.5：Git 基线、Provider 契约、持久数据目录、环境自检和自动基准入口。
9. [已完成] M2a `Sparse Navigation Map v0`：Python AST/哈希稀疏结构地图、增量 SQLite 和预算化可解释 Top-K 查询；B014 通过。
10. [已完成] M2b `Task Navigator v0`：持久任务状态、证据去重、结构化反馈、动态排序、硬预算和停止原因；B015 固定基准通过。
11. [已完成] M2c 关系覆盖与后端比较：补齐继承、直接调用和高价值引用；5 个真实任务错误停止减少 1 个，B015 修复，统一报告跑通内置 AST 与 Serena，Codebase-Memory 缺失时安全降级。
12. [采用策略] M2a 借鉴 Aider 的任务加权排名与 Stacklit 的紧凑/增量地图；M2c 优先通过 CLI 小范围试接 Codebase-Memory，Serena 负责源码核验，Repomix负责基准，AgentMemory推迟到 M3。
13. [v0 已实现，完整会话基线待补] M2d 多源候选与未知目标发现：复用现有 Marker/TaskState 完成轻量 Discovery Router 与受限文本 rescue；10 个跨仓库任务由 M2c 6/10 提升到 9/10、零正确性回归。Serena 无 oracle Recall 1/5 且全部超预算，因此不进入发现核心。源码与安装态 59/59 测试通过；原生 Codex 同任务 A/B 尚未完成。详细见 `M2D_IMPLEMENTATION_PLAN.md` 与 `M2D_RESULTS.md`。
14. [M2e-0 已完成，M2e-1 pilot 暂缓] Native/M2d 两类任务共 4 个有效配对、8/8 正确；usage、独立 Codex Home/worktree、行为合规、diff、测试和 stop reason 均可自动核验。但 M2d 配对 Token 比率中位数为 3.131x，不能直接扩大昂贵 benchmark。详细见 `M2E_IMPLEMENTATION_PLAN.md` 与 `M2E_CALIBRATION_RESULTS.md`。
15. [M2e-0.1a 已完成] 将问题定义为编排成本而非检索质量；归因修正了 started/completed 重复计数，实际完成命令为 M2d 51 vs Native 18，两组精确重复 payload 均为 0。M2d 一次性 payload 多 22,161 Token，只相当于模型总 regret 的约 2.52%，主要嫌疑转向额外往返和累积上下文重处理。下一步把显式循环收进最多两次调用的 Compact Navigator；阶段门槛仍为正确性不下降、配对比率中位数不高于 1.25x、启动/导航载荷与协议调用至少下降 50%、至少一个任务优于 Native。详见 `M2E_0_1_IMPLEMENTATION_PLAN.md` 与 `M2E_0_1_ATTRIBUTION_RESULTS.md`。
16. [M2e-0.1b Gate 2 失败] Compact 两阶段协议、双硬预算和安全上限成立，但冻结 M2d 原成功集合只保留 2/9；失败由 4 个 verify 后仍未到达目标和 3 个目标已展开但未进入 Evidence Package 组成。停止 Gate 3/4、Activation Gate 和昂贵端到端消融，下一步先复审“两次交互”与“逐步语义导航能力”的架构矛盾。详见 `M2E_0_1B_GATE2_RESULTS.md`。
17. [CO-0 v0 已完成并冻结] 真实接口门 `cat/sed/rg/known-symbol/code mode/passthrough/fail-open` 7/7 通过；四组 Native/CO 经济门 correctness 一致，CO 重试与补偿均为 0，净可见上下文合计节省 1,216 Token，完整会话配对比率中位数 `0.9931x`。这只证明合成小矩阵中的架构可行性；插件继续默认 observe，不宣称一般开发会话节省。下一项为 CO-1 Syntax-aware Read Slicing。详见 `CO_0_RESULTS.md` 与 `resources/co0_matrix_results.json`。
