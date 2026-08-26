# Agent Token Manager：项目结项与价值定位

- 结项日期：2026-08-19
- 项目状态：`RESEARCH_COMPLETE / PRODUCT_NOT_VALIDATED / MAINTENANCE_ONLY`
- 对外定位：Coding Agent 上下文成本的测量、干预实验与边界研究原型
- 非定位：生产级自动 Token 优化器、通用上下文压缩产品、已验证的全局节省方案

## 执行摘要

Agent Token Manager 起初试图减少编码 Agent 在源码读取、搜索和工具结果中消耗的无效上下文。项目最终没有证明一个能够在当前 Codex Host 上透明运行、保持成功语义、并跨 Read、Search、Structured Bash 自然泛化的自动优化产品。

这不意味着项目没有产出。项目完成了三个更基础、也更可复用的工作：

1. 建立了一套 privacy-safe、coverage-aware、可追溯的 Agent 成本测量基础；
2. 用冻结协议和对照实验证明若干特定 evidence reduction intervention 确实能够在不降低正确性的条件下显著缩小目标 evidence；
3. 识别并实证了通用产品化的三个主要边界：编排成本、Host replacement 语义，以及自然 benchmark/evidence-family coverage。

因此，本项目应作为一个已经完成的研究原型和证据档案保存，而不是作为等待补完的产品半成品继续推进。

## 最终定位

推荐的一句话介绍：

> Agent Token Manager 是一套用于测量 Coding Agent 上下文成本、构造可审计干预实验并识别优化边界的研究原型；它证明了局部 evidence reduction 可行，同时证明当前证据不足以支持通用、透明、跨工具家族的自动 Token 优化产品。

项目最适合服务三类用途：

- Agent observability 与 eval 基础设施参考；
- 上下文干预、工具结果压缩和 benchmark qualification 的研究方法参考；
- 关于“局部 Token reduction 为什么不自动等于端到端产品收益”的负结果与工程案例。

## 项目回答了什么

### 1. 稀疏导航能否减少源码读取

结构化 Marker/Edge、持久 TaskState、Feedback 排序、重复证据抑制和硬预算导航均已实现。M2d 在无代码标识符的冻结任务上将自然语言导航提升到 `9/10`，说明稀疏结构图和受限文本救援具有检索价值。

但端到端校准显示，显式多轮导航产生了明显编排成本：M2d 相对 Native 的配对 Token 比率中位数为 `3.131x`。将协议压缩为最多两次调用的 Compact Navigator 后，冻结成功集合只保留 `2/9`。结论是：

> 检索质量、交互轮数和端到端上下文成本之间存在真实张力；较少返回源码不等于较少会话 Token。

### 2. 能否透明替换模型可见工具结果

Host reconnaissance 证明当前 code-mode/Bash 路径具有完整观察点：16/16 个自然 code-bearing 结果与 `17,651/17,651` 个模型可见估算 Token 均能从 raw result 关联到 Hook 和 transcript。

但当前通用 replacement 依赖 `decision:block`，4/4 canary 均被 Host 包装为 `Script failed / Script error`。因此透明 Smart Read 被判定为：

- `algorithm_status=NOT_FALSIFIED`；
- `status=BLOCKED_HOST_INTERFACE`；
- `product_status=FROZEN`。

结论是：

> 观察能力已经成立，但当前 Host 接口不足以承载保持工具成功语义的通用透明替换。

### 3. 能否可靠测量 Agent 成本

ACP-0 建立并验证了测量基础：

- privacy-safe collector 与封闭字段 allowlist；
- session/path HMAC 伪名化；
- fail-open、零 Hook 输出和 host-result integrity；
- normalized event、transcript linkage 与 coverage ledger；
- Session、Cycle、Call、Evidence-Coverage 四层事实；
- canonical JSON、Markdown/CLI renderer；
- provenance、manifest、calibration 和 checksum chain。

该基础能够显式保留 `unknown`、ambiguity、unsupported path 和 denominator，而不以推断填补缺失数据。这是项目最接近可独立复用的软件资产。

### 4. Evidence reduction 本身是否真实存在

在冻结的局部实验范围内，答案是肯定的：

- synthetic canary：目标 evidence estimate median `3919 → 1969`，reduction `49.757591%`；
- 两个 prospective natural cases：paired evidence reduction median `62.609971%` 与 `49.696233%`；
- 三个修复后的 prospective v2 cases：activation median `81.310680% / 76.190476% / 98.579189%`；
- 对应正式实验保持冻结范围内的 correctness、success semantics、tool path 和 cycle Gate。

这些结果证明局部 intervention 可以工作，但不能被解释为生产环境全局节省：case 数量有限，session ratio 只作描述，且 Host replacement 与自然泛化仍未成立。

### 5. 通用跨家族泛化是否成立

没有成立，而且项目在正确的层级停止了。

ACP-1.4F v2.1 的54个 completed Native runs 全部回答正确，但 Read/Search family coverage 在 intervention 前已数学上不可达。只读审计进一步发现，54/54 都存在唯一、兼容的 evidence carrier，说明旧 Gate 混入了完整 trajectory 和命令表面差异。

随后建立全新的24-case benchmark-development pool，并在冻结 protocol 下完成110个有效 Native runs：

- 110/110 correct；
- 110/110 evidence opportunity identifiable；
- 110/110 compatible carrier identifiable；
- measurement unknown 与 unresolved truncation 均为0；
- 最终只有4个 qualified case，且全部属于 observed `search_like`；
- `read_like=0`，`structured_bash_like=0`。

最终 verdict 为 `BENCHMARK_SEMANTICS_NOT_SUPPORTED`。它否定的是当前 benchmark/qualification 载体对多家族泛化的充分性，不是对未运行的 R1/S1/B1 intervention 作失败判定。

## 已证明、未证明与已否定

### 已证明

- 当前 Bash/code-mode 工具结果可以被完整、隐私受控地观察和关联；
- Agent 成本可以按多层事实、coverage 和 uncertainty 进行可审计测量；
- 若干确定的、受控的 evidence reduction 在冻结 case 上保持正确性并显著缩小目标 evidence；
- benchmark development 必须区分 task、evidence opportunity、compatible carrier 与 observed Host path；
- automatic futility 能在 Gate 数学上不可达时停止实验并节约运行预算。

### 未证明

- 端到端或账单级全局 Token 节省；
- reduction 后的长期任务质量不下降；
- Read/Search/Structured Bash 三家族通用规则；
- 对不同模型、Host 版本、语言和仓库的外部效度；
- 一个值得部署的 Search-only 产品。

### 已否定或阻塞

- 显式多轮 Navigator 在当前形态下具有端到端成本优势；
- Compact Navigator 能同时维持低交互次数和冻结导航 Recall；
- 当前 Host `decision:block` 可作为保持成功语义的透明通用 replacement；
- 当前 ACP-1.4F development pool 可支持三家族或两家族 formal generalization。

## 项目的核心价值

### 方法价值

项目形成了一条比“看起来少了多少文本”更严格的评估路径：

```text
可观察性
  → 测量完整性与隐私
  → Native qualification
  → intervention activation
  → correctness / path / cycle / semantics
  → generalization coverage
  → 才可能讨论产品收益
```

这条路径揭示了常见误区：source-level reduction、model-visible reduction、session Token 和实际成本不能互相冒充。

### 工程价值

可复用资产包括：

- privacy-safe collector、normalizer、coverage ledger 和 reporter；
- experiment manifest、recalibration policy、frozen artifact index；
- Native qualification、paired experiment、automatic futility 和 registry schema；
- 稀疏 Marker/Edge 导航、TaskState、反馈排序和预算控制；
- 大量关于 Host、Hook、tool path 和 transcript linkage 的可复现实验 fixture。

这些组件更适合作为内部研究基础或 Agent eval 工具箱，而不是以当前整体形态直接发布为终端产品。

### 负结果价值

项目提供了三个很难仅靠设计推演得到的负结果：

1. 更少的工具 payload 可能因为增加模型轮次而产生更高的会话 Token；
2. 能观察和改写结果，不代表 Host 会保持工具成功语义；
3. 任务100%正确，不代表它是稳定、足量、可干预的 reduction benchmark。

这些结论能阻止未来团队重复投入同类错误路线。

### 治理价值

项目坚持保留失败 run、inconclusive case、unknown 字段和冻结阈值；没有通过降低 Gate、替换失败任务或后验重分类制造成功。对于 Agent 系统这种高方差实验，这套治理本身具有示范意义。

## 为什么现在结项

继续推进需要至少改变一个根本前提：

- Host 提供保持成功语义的模型可见结果替换接口；
- 新 benchmark 能客观要求稳定且足量的 Read/Structured evidence；
- 科学问题明确缩小为 Search-only subset；
- 或产品目标从自动 reduction 改为 observability/eval。

这些都不是当前路线的自然增量，而是新项目或新 protocol。继续在原编号下优化任务、selector 或阈值，只会模糊已经得到的边界结论。

## 结项后的维护原则

- 默认不启动新的 Agent runs；
- 不创建 ACP-1.4F v3，不解冻 R1/S1/B1；
- 不再把 README、STATUS 或计划写成等待下一阶段的 active roadmap；
- 保留现有代码、测试、fixtures、registries 和 frozen indexes；
- 只接受安全修复、可复现性修复、文档澄清和依赖兼容性维护；
- 新研究必须另立目标、版本、任务池和统计边界，不复用旧 development runs 作正式统计。

## 重新开启条件

只有出现以下明确变化之一，才建议重启相关研究：

1. Host 新增并验证可保持 success semantics 的结果替换接口；
2. 有独立来源的新任务池稳定形成至少两个或三个 observed evidence families；
3. 用户明确接受 Search-only 的缩小外推范围，并愿意建立全新 formal protocol；
4. 项目被重新定义为 Agent Cost Profiler / Eval Toolkit，而不再承诺自动优化。

独立的非 Token 后继方向已经作为单独仓库启动。它以本地文件分类、符号索引、关系图和统一查询为目标，不属于本研究归档，也不改变本项目的结项状态。

## 推荐引用入口

- 总结与定位：本文；
- 当前项目状态：`STATUS.md`；
- 完整历史路线：`PROJECT_PLAN.md`；
- Transparent Smart Read 边界：`TRANSPARENT_SMART_READ_FROZEN.md`；
- Cost Profiler 测量范围：`ACP_0_VALIDATION_SCOPE.md`；
- 局部自然干预证据：`ACP_1_3D_VALIDATION_SCOPE.md`、`ACP_1_4E_VALIDATION_SCOPE.md`；
- 最终 benchmark-development 结论：`ACP_1_4F_D_RESULTS.md`。

## 最终结论

Agent Token Manager 没有成为最初设想的通用自动优化产品，但它完成了一个有明确终点的研究任务：证明什么局部有效、什么系统条件缺失、什么 benchmark 语义不成立，以及怎样在不夸大结果的情况下测量这些差异。

项目的最终价值不是一个“省多少 Token”的产品数字，而是一套可信的证据链、可复用的实验基础设施，以及对 Coding Agent 上下文优化边界的清晰认识。
