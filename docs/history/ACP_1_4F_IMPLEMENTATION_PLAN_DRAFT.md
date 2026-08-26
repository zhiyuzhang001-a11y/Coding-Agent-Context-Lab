# ACP-1.4F 任务书：Combined Prospective Generalization Baseline v2

- 状态：`F-1 STOPPED — INSUFFICIENT_NATIVE_COVERAGE under frozen v2.1 scope / F-2 BLOCKED`
- 日期：2026-08-19
- 前置：ACP-1.4E `COMPLETE — ACTIVATION_RESOLVED under frozen v2 experiment scope`
- 建议定位：验证一组非 case-specific、无 oracle 的 evidence-reduction rule，能否在全新 Read/Search/Bash 自然任务上重复形成强 intervention，同时保持 Agent 行为

## 一句话目标

> 不再证明“为某道题量身定做的缩减能成功”，而是证明“同一套事前冻结、看不到答案的规则，可以在多类新任务上重复成功”。

本阶段仍是离线实验，不开发 production slicing、replacement 或实时 recommendation。

## 为什么需要 1.4F

ACP-1.4E 已证明三个历史 activation blocker 可以通过更合适的 v2 Treatment 解决，但证据仍是 case-specific：

- Read 规则知道应保留更早的窄区域；
- budget-stop Search 规则知道应保留哪类 assignment；
- token-router Search 规则知道目标常量行及需要消除的截断 scope。

这些结果证明“强 intervention 可以安全存在”，尚未证明系统能在不知道答案的情况下选择正确 evidence。1.4F 的首要风险不是 reduction 不够大，而是 **oracle leakage**：把 expected answer、scorer、目标行正则或人工看过结果后的知识写进 Treatment。

## 核心研究问题

1. 不读取 expected answer、ground truth 或 scorer 时，rule template 能否稳定识别应保留的 evidence？
2. 同一 template 能否服务多个任务，而不是每个 case 写一条新规则？
3. Read、Search、Bash 三个家族是否都能达到 `>=35%` model-visible evidence reduction？
4. 强 intervention 是否保持 correctness、tool path、model cycles 和 success semantics？
5. 哪些 evidence 类型天然适合缩减，哪些应明确 passthrough？

## 预注册架构

```text
fresh task universe
        ↓
Native qualification
        ↓
evidence identity + rule-template routing
        ↓
offline activation / no-oracle audit
        ↓
Control vs Treatment paired formal
        ↓
family/case verdict + applicability boundary
```

Treatment builder 必须只接受以下冻结输入合同：

```text
TreatmentBuilderInput
├── tool_family
├── request_shape
├── requested_path_identity
├── requested_range
├── query_shape
├── command_shape
├── structural_result
└── frozen_template_params
```

其中 `structural_result` 只含行、JSON key、测试段落、退出状态等工具结果自身的结构信息。外层 experiment harness 可以保存 `case_id` 用于 traceability，但不得把它传入 builder。

Treatment builder 禁止消费：

- expected answer、ground truth、scorer；
- benchmark 的 target line、答案正则或人工标注的“必须保留行”；
- Control/previous run 的 correctness；
- pilot/formal 结果；
- `case_id` 或任何 case ID 专用分支。

建议让 Treatment builder 在单独输入合同下运行，输入对象中根本不存在 expected/scorer 字段，而不只依赖代码审查约定。

## 建议 sampling frame

第一版建议使用 **12 个全新 prospective tasks**：

- Read：4；
- Search：4；
- Bash：4；
- 至少覆盖 3 个不同仓库或项目形态；
- 每个工具家族至少跨 2 个独立仓库或项目上下文；
- 旧 1.4/1.4E case 只进入独立 regression suite，不计入 primary generalization statistics。

建议覆盖的 evidence 形态：

- Read：常量/配置、函数或类定义、局部范围、较长单文件；
- Search：精确标识符、字符串/状态值、多文件 schema/config、较宽结果集；
- Bash：结构化 JSON、测试输出、命令摘要、失败/退出状态。

每个任务必须满足：答案唯一、ground truth 可审计、确实需要对应工具家族、命令不含标点歧义、Host 输出不在不可控截断区，或能明确标记 truncation coverage。

## Rule templates 草案

以下只是候选模板；在任务抽样和任何新 run 前必须冻结精确定义。

### R1 — Read structural window

- 从请求中已有的 symbol/query/range 形成客观 anchor；
- 保留 anchor 的声明或命中区域、必要 header/import 与固定邻域；
- 没有唯一 anchor、需要全文件语义或输出低于门槛时 passthrough；
- 禁止使用 benchmark target line 或 expected answer 定位。

### S1 — Search structural grouping

- selector 顺序固定为 `stable path ordering → structural key ordering → first N`；
- 保留按上述顺序得到的确定性代表与所有明确冲突/歧义项；
- 结果已很小、处于截断饱和区或无法证明代表性时 passthrough/unsupported；
- 禁止通过“包含正确答案”选择代表行。
- 禁止使用“最佳”“最相关”等需要语义判断的排序标签。

### B1 — Bash structured projection

- 只处理能够可靠解析的 JSON、测试摘要或稳定分段输出；
- 保留 exit/success semantics、失败段、摘要、明确请求的结构字段；
- 未知命令、自由文本日志、交互命令和解析失败全部 passthrough；
- 不执行 shell rewrite，不改变被运行命令。

模板数量应保持最少。如果某个新 evidence type 需要 case-specific 例外，优先标记 unsupported，而不是新增隐蔽分支。

## 阶段设计

### 1.4F-0 — Contract / leakage barrier

状态：`COMPLETE`。冻结产物：

- `resources/acp1_4f_frozen_contract.json`：12-case universe、三类模板、全部 Gate、分母、预算与停止条件；
- `resources/acp1_4f_oracle_registry.json`：仅供 outer harness 使用的独立答案/scorer registry；
- `scripts/acp1_4f_treatment_contract.py`：只接受冻结八字段输入的离线确定性 builder；
- `resources/acp1_4f_f0_frozen_index.json`：0 Agent run 的 checksum chain；
- `tests/test_acp1_4f_f0_contract.py`：no-oracle、ground truth、hash、determinism、unknown/passthrough 与政策边界测试。

在任何 task result 可见前冻结：

- `generalization-v2-spec`；
- 12-case sampling procedure 和 case version；
- rule-template schema；
- no-oracle input allowlist；
- denominator、coverage、activation 与 behavior Gate；
- overall verdict；
- run budget 和停止条件。

必须提供自动测试证明 Treatment builder 无法访问 expected、scorer、case-specific target regex 或历史 correctness。

G0 是结构性、不可豁免的实验有效性条件。若任何 run 后发现 builder 输入或代码路径存在 oracle leakage，则整个 experiment version 失效；修复必须建立新版本（例如 `v2.1`）并从头重新执行，旧版本 run 不得复用。

F-0 已通过 9 项定向测试、只读 frozen-index verifier 与项目全量 405 项测试；本阶段 Agent run count 为 0。F-1 Native qualification 已具备输入条件，但仍未启动。

### 1.4F-1 — Native qualification

状态：`STOPPED — INSUFFICIENT_NATIVE_COVERAGE`。

在启动前发现 F-0 缺少 candidate identity 语义，因此在 0 Agent run 状态下升级并重新冻结为 `v2.1`；未复用运行数据。正式运行共 55 attempts：54 completed、1 个停止时 interrupted。全部 54 completed runs correctness 均正确，builder/collector/Hook/intervention 均未使用。

冻结停止证据：

- Read 四 case recurrence 均 10/10，但 dominant path 为 `9/10、7/10、5/10、5/10`，只有 1 个 qualified，已不可能达到每 family 至少 3 个；
- 首个 Search case 10/10 correct，但 recurrence 2/10，rejected；
- 第二个 Search case 前 4 次 correct 4/4、recurrence 0/4，最大可能只有 6/10，early rejected；
- Search 最多只可能得到 2 个 qualified，同样无法达到 family coverage Gate；
- 因 coverage 已数学上不可能，剩余 65 runs 未启动，F-2 不获授权。

runner 原设计在正常结束时才汇总 dominant path，因此 Read-family failure 在第 40 次已可判定，却到第 54 次才被人工识别并停止；额外 14 runs 全部保留，记录为 `DELAYED_AUTOMATIC_STOP`，不改变 verdict。

每 case Native ×10，共 120 runs。此阶段 builder 不运行，也不生成 Treatment：

- completed with usage `10/10`；
- correct `>=9/10`；
- candidate recurrence `>=8/10`；
- ambiguous `=0`；
- dominant path `>=8/10`。

Native correctness/path qualification 与 evidence 收集是两个独立结果：所有 10 次 run 的自然 evidence 都冻结进入 ledger，不能只保留正确、最大或看起来最有用的 run。

### 1.4F-2 — Offline activation qualification

对每个 case 的全部 10 份冻结 Native evidence 执行纯离线 rule routing，0 Agent runs。builder 不能接收 correctness 或 scorer 结果：

- `eligible`：可靠 candidate identity `>=8/10`，模板可确定性应用，输出非空、未截断且 median reduction `>=35%`；
- `passthrough`：结果已小、无唯一 anchor 或没有可支持的结构；
- `unsupported`：格式/工具路径不在模板合同内；
- `measurement_unknown`：Host truncation 或 denominator 不可靠。

离线阶段不能用答案判断“保留得对不对”，也不能挑选 correct、最大或人工判断有用的 Native evidence；只验证结构合同、确定性、activation feasibility 和 coverage。所有 12 个 case 都进入 ledger，不替换低 activation 或 unsupported case。

case 只有同时满足 Native-qualified 与 offline-eligible 才能进入 formal admission registry。

formal admission coverage Gate：

- 至少 9/12 formal-admitted；
- Read/Search/Bash 各至少 3 个 formal-admitted；
- primary sampling frame 不补任务、不替换 rejected case。

### 1.4F-3 — Pilot

- 每个 rule template 选择一个事前冻结 representative；
- 每个 representative 只运行 Control ×1 / Treatment ×1；
- pilot 只检查 plumbing、实际 activation、identity、success semantics；
- pilot 不计入 formal，不用于修改阈值或模板。

任一必需 template pilot 失败则停止 formal，建立新版本而不是现场修规则。

### 1.4F-4 — Paired formal

所有且仅有 formal-admitted case 进入 formal：

- 每 case Control ×10 / Treatment ×10；
- AB/BA 平衡；
- 不补跑失败样本；
- 不删除 outlier；
- 每个 case 独立判定，再做 family/overall 汇总。

若按最低 9 个 case 进入 formal，预计正式运行 180 次；若 12 个全部进入，则为 240 次。

## Case Gate 草案

### G0 No-oracle

Treatment input 和代码路径中不存在 expected/scorer/answer-derived selector；case-specific branch 数为 0。

### G1 Eligibility / completeness

case 为 frozen Native-qualified + offline-eligible；20/20 formal runs 均完成且有 usage。

### G2 Activation

model-visible evidence reduction median `>=35%`；至少 8/10 Treatment run 命中同一可靠 candidate；截断或 denominator unknown 不得判 PASS。

### G3 Correctness

- Control correct `>=9/10`；
- Treatment correct `>=9/10`；
- accuracy delta `>=-0.10`；
- confirmed projection-induced semantic regression `=0`。

Treatment-only 单次错误不能自动归因给 projection。formal 完成后，按冻结规则将异常分为：

- `confirmed_projection_induced`：同一 scorer-defined semantic error 至少出现在 2 个 Treatment blocks；对应 paired Controls 正确；事后独立审计证明被删除 evidence 直接支持缺失事实；且不存在 identity、path、telemetry 或 host confound；
- `possible_or_unknown`：证据不足以确认或排除 projection 因果作用，该 case 判 `INCONCLUSIVE`，不得判 PASS；
- `not_supported`：没有证据支持 projection-induced regression，继续按上述 correctness parity Gate 判定。

该事后审计可以读取 scorer 以分类错误，但 scorer 永远不得进入 Treatment builder。任何 `confirmed_projection_induced` 都使该 case FAIL，并阻止 overall verdict 成为 `SUPPORTED_WITH_BOUNDARIES`。

### G4 Path stability

- dominant-path retention delta `>=-0.10`；
- paired tool-call delta median `<=0`；
- 不出现至少重复 2 次的新 compensation path。

### G5 Cycle stability

paired model-cycle delta median `<=0`。

### G6 Success semantics

不得改变 command exit/success/failure 语义；解析或 projection 故障必须在离线 harness 中显式 fail-open/passthrough。

### G7 Cost interpretation

只有 G0–G6 全通过时才描述 session usage；不把 evidence reduction 直接称为 session savings。

### G8 Integrity

所有样本、unsupported、passthrough、inconclusive 和 outlier 进入 frozen manifest/checksum chain；旧 artifacts 与 collector/Hook hash 不变。

## Overall verdict 草案

### `SUPPORTED_WITH_BOUNDARIES`

- G0 no-oracle 通过；
- formal coverage Gate 通过；
- 所有 formal-admitted case 都已正式运行；
- overall PASS rate `N_PASS / N_formal_admitted >=0.75`；
- Read/Search/Bash 各至少 2 个 PASS；
- confirmed projection-induced semantic regression `=0`；
- 没有某个家族出现系统性 path/cycle/success-semantics degradation。

`INCONCLUSIVE` 保留在 formal-admitted 分母中，不得从 PASS rate 排除。例如 9 个 admitted case 中需至少 7 个 PASS，12 个 admitted case 中需至少 9 个 PASS。

### `MIXED`

formal 完整且至少一个 case PASS，但未满足 family coverage、PASS rate 或零 confirmed projection-induced regression 条件。

### `NOT_SUPPORTED`

多数 formal case FAIL，或观察到预注册意义上的系统性 correctness/behavior degradation。

### `INSUFFICIENT_COVERAGE`

Native qualification、offline eligibility、template pilot、Host telemetry、identity 或完整性不足，无法启动或解释 formal。

整体 verdict 不输出平均“可节省 X%”。只报告漏斗、case/family verdict、activation distribution、unknown 和 applicability boundary。

## 预计实验成本

按 12 个候选 case 估算：

- offline：0 Agent runs；
- Native qualification：120 runs；
- pilot：约 6 runs（假设 3 个模板）；
- formal：180–240 runs；
- 合计：约 306–366 Agent runs。

primary experiment 的硬上限冻结为 **366 Agent runs**，不得通过补跑失败样本、增加替代任务或延长某个 arm 超支。

以下条件触发停止：

- Native admission coverage Gate 不通过；
- 任一必需 family/template pilot 失败；
- telemetry、identity 或 denominator 无法可靠测量；
- 发现 G0 oracle leakage。

其中 G0 违规不是普通停止，而是使整个 experiment version 无效；修复后必须新建版本、重新冻结并从头运行，旧 run 不得进入新版本统计。

## 明确不做

- 不进入 ACP-2 policy learning；
- 不训练或调优自动推荐模型；
- 不实现在线 slicing/replacement/recommendation；
- 不重开 Transparent Smart Read Host rewrite；
- 不把 1.4E case 混入 primary statistics；
- 不针对失败 case 现场新增 regex、target line 或特殊分支；
- 不以 evidence reduction 冒充完整 session savings；
- 不宣称对所有仓库、模型或 Host 版本有效。

## 通过后意味着什么

如果 `SUPPORTED_WITH_BOUNDARIES`，项目可以进入 ACP-2.0 的离线 policy specification：总结哪些 evidence 类型应尝试 reduction、哪些应 passthrough，以及需要哪些 coverage/uncertainty signals。

它仍不授权生产部署。生产化必须另行解决 Host success-preserving replacement 接口、在线 fail-open、延迟、隐私和重新校准。

## 审阅决策（已解决）

1. 第一版固定采用 12 case（4 Read / 4 Search / 4 Bash），不扩大到 15 case；
2. 强制覆盖至少 3 个独立仓库/项目形态，且每个 family 至少跨 2 个上下文；
3. formal admission coverage Gate 固定为至少 9/12、每家族至少 3；
4. `SUPPORTED_WITH_BOUNDARIES` 固定采用 admitted-case PASS rate `>=0.75`、每家族至少 2 PASS、confirmed projection-induced semantic regression 为 0；
5. primary experiment run budget 硬上限固定为 366；
6. no-oracle barrier 是不可豁免的结构性 G0，违规使整个 experiment version 失效。

## 当前授权边界

`v2.1` 已停止并冻结：

- 不得恢复剩余 65 次 Native runs；
- 不得修改 identity 后重分类现有 runs；
- F-2、pilot 与 formal 均 blocked；
- 如要继续，必须先审计 benchmark/path semantics，建立全新版本并重新预注册；
- 不得创建会利用当前结果为单个 case 调参的后验模板或 identity。
