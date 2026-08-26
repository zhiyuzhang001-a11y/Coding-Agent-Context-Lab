# 项目状态

## 当前状态（2026-08-19）

项目已结项：`RESEARCH_COMPLETE / PRODUCT_NOT_VALIDATED / MAINTENANCE_ONLY`。不再以通用自动 Token 优化产品为活动目标；现有价值定位为 Agent 成本测量、上下文干预实验、benchmark qualification 与失败边界的研究原型和证据档案。完整结项说明见 `PROJECT_CLOSURE_AND_VALUE.md`。

`ACP-0 Measurement Foundation — COMPLETE under frozen validation scope`。中文：`ACP-0 测量基础完成：在冻结任务集、模型、collector、实验设计与预注册 Gate 范围内通过验证。` ACP-0.4 的 `FAILED_COST_NEUTRALITY` 与 ACP-0.4a 的 `INCONCLUSIVE / GRADUATION_FAIL` 均作为历史证据保留；ACP-0.4b 通过预注册 correctness closure 后完成工程意义上的阶段毕业。适用范围、限制和重新校准条件见 `ACP_0_VALIDATION_SCOPE.md`。

当前路线状态：ACP-0H 至 ACP-1.3D 保持冻结完成；ACP-1.4 与 ACP-1.4C 历史结论保持不变。ACP-1.4E 的三个 case-specific blocker 保持解决；ACP-1.4F v2.1 因 `INSUFFICIENT_NATIVE_COVERAGE` 冻结，F-R 只读审计随后授权独立 benchmark-development pool。ACP-1.4F-D 已在冻结 protocol 下完成：110/110 completed runs correctness 正确，但最终4个 qualified case 全部属于 observed `search_like`，Read/Structured 均为0，verdict 为 `BENCHMARK_SEMANTICS_NOT_SUPPORTED`。v3、新 holdout 与 R1/S1/B1 解冻均未获授权。详见 `ACP_1_4F_D_RESULTS.md`。

- ACP-1.0-0 已冻结 `cost-attribution-baseline-v1` schema、语义字典和 complete/partial/ambiguous/unsupported 验收 fixture；Top-K、HHI、p90、分母、unknown 与 repetition copy-only 规则均在 engine 输出前预注册。
- ACP-1.0-1 已实现纯离线只读 `acp-attributor-v0.1`：输出 session/tool-family/call attribution、Top-K/Top-percent、call/family HHI、distribution 与 repetition group observation volume；partial/ambiguous/unsupported 均不强制归因，cycle 继续 unknown。
- ACP-1.0-2 已实现 `acp-attribution-renderer-v0.1`：只消费 canonical attribution JSON，提供 Markdown/CLI text/canonical JSON；不回读 fact report/normalized/raw event，不新增指标，unknown/null/unsupported 原样展示。
- ACP-1.0-3 已生成 `acp1-0-co1-4-cost-attribution-v1`：G1 provenance、G2 governance、G3 determinism、G4 measurement integrity、G5 freeze integrity 全部通过；baseline index 为 `598bf7ea...65a186`，manifest 为 `b44a0ea...e113f`。
- ACP-1.1 已冻结 `repeated-evidence-analysis-v1`：within-session relation scope、半开 range convention、path content-stability unknown、封闭 evidence basis 和 unique later-call Token 去重规则均已进入合同。
- ACP-1.1 正式 CO-1.4 baseline 的 16 calls / 17,651 Tokens 顺序 coverage 完整，within-session relation/unique repeated Tokens 为 `0/0`；ACP-1.0 的 5,288 Token 是跨 session exact duplicate observation volume，保留不变。path/range/cycle/content stability 保持 unknown。
- ACP-1.2 冻结 `cost-necessity-hypothesis-catalog-v1`：仅从 ACP-1.0 canonical attribution 与 ACP-1.1 repeated-evidence facts 产生离线实验候选，高成本阈值为 call share `>= 0.10` 且 observed Tokens `>= 1000`，集中度阈值为 call HHI `>= 0.18` 或 Top-3 share `>= 0.60`；不从 raw event 读取或新增 correlation。
- ACP-1.2 正式 catalog 产生 5 个 `high_cost_call_candidate`、0 个 concentration candidate、0 个 repeat candidate；5 个唯一目标的 observed exposure 为 `10,735 Tokens / 60.8180839612%`。这是候选暴露体量，不是 waste 或 savings estimate；全部 `necessity=unknown`、`causal=untested`、validation feasibility `blocked`，未执行 intervention。
- ACP-1.3A 仅使用 ACP-0.4a 私有 transcript 中的 host cumulative usage snapshot；120/120 run 通过 exact thread/session ID 关联，共 287 snapshots，公开 artifacts 不含 prompt/response/final answer/raw session ID/绝对路径。
- OFF primary 与 ON replication 各 60 run 分开报告。OFF 的 1→2 / 2→3 within-run incremental ratio median 为 `1.025937891418 / 1.020076212141`，ON 为 `1.025928058203 / 1.022400270835`；当前 cycle 1–3 为温和上升，没有证明快速加速形状。cycle 4 每臂只有 1 run，保留为 `insufficient_descriptive_sample`。
- cached input 不冒充历史上下文；new/history decomposition、semantic reprocessing、counterfactual added-cycle cost、necessity 和 avoidability 均为 unknown。
- ACP-1.3B 新建 `controlled_evidence_ledger_lookup_v1` 合成 canary，不重放或修改 ACP-1.2 的 5 个历史候选。offline canary 只变更 evidence source payload，两臂都使用同一正常退出命令，未注册 Hook 或 replacement。
- Control-only qualification 为 `20/20` completed/correct/exact-command；paired Control/Treatment 均为 `5/5` correct/success/exact-command，每次 2 model cycles。target evidence estimate median 为 `3919 → 1969`，activation `49.757591%`；session total median `37,219 → 34,127` 只是 synthetic observation，不是 avoidable volume。
- ACP-1.3B G1–G8 全部通过；frozen index 为 `6397007c...0fc3`，manifest 为 `3cecfb99...7a87`。collector `81efee8b...6de2`、Hook manifest `797b72b6...4dd` 与 ACP-1.0–1.3A frozen artifacts 保持不变。
- ACP-1.3C 冻结 4 个 natural case ×20 Native runs；`80/80` completed with usage/correct，无 ambiguous identity。`natural_signature_limit_v1` 与 `natural_command_shape_v1` 以 recurrence/path `18/18` 与 `20/18` 准入 ACP-1.3D。
- `natural_truncate_budget_v1` 虽 recurrence `19/20`，但 dominant path 只 `13/20`，因此仅 `diagnostic_only`；`natural_navigation_counts_v1` recurrence/path 均 `13/20`，因此 `rejected`。不降低 `16/20` 阈值，不人工挑选 run。
- ACP-1.3C index 为 `a4c599bd...9090`，manifest 为 `ddf15ada...4a45c`；ACP-1.3D 只能消费 registry 中的 `qualified` case/version。
- ACP-1.3D 的 pilot 4/4 通过且未混入正式统计；formal 80/80 完成。两个 case 的 Control/Treatment correctness 均为 `20/20`，无 Treatment-only failure，G1–G8 全部通过。
- signature/command-shape 的 evidence reduction median 分别为 `62.609971%` / `49.696233%`，paired tool-call/cycle delta median 均为 0；session pooled ratio `0.967792` / `0.839889` 仅为冻结实验描述。
- signature case 的 1 个 Control non-recurrence、一个负 reduction pair，以及 command-shape Control max `83,851` Token 均保留，不删除、不补跑。1.3D index 为 `740dc39d...ee837`，manifest 为 `52c25023...675f2`。
- ACP-1.4A 完成 8 case × Native 10，共 80/80 valid runs：Read/Search 六个 case 全部 10/10 correct/recurrence/path；两个 Bash case 均 0/10 correct、5/10 recurrence/path，原样 rejected。
- ACP-1.4 family pilot 不进入正式统计：Read reduction `60.096444%`、Search `44.117647%` 且 plumbing checks 通过；Bash 无 qualified representative。正式 1.4B run count 为 0，verdict 为 `INSUFFICIENT_COVERAGE`。
- 首次沙箱内 epoch 的 2 个网络 timeout 与 1 个中断探针单独冻结为 aborted preflight，不混入 84 个有效 run；model/spec/runner/Gate 未改变。1.4 index 为 `67eccea1...0876`，manifest 为 `5716bd57...6419`。
- ACP-1.4C 审计确认旧 Bash v1 的 0/10 来自尾随句号进入 argv 和 read-only sandbox 无 tempfile；旧 case、registry 与 `INSUFFICIENT_COVERAGE` 未重评分。新的 Bash v2 sampling frame 为 3 proposed / 2 qualified / 1 rejected；rejected case 保留 0/10 recurrence，不替换、不调 identity。
- ACP-1.4C pilot 4 run 不进入正式统计；combined formal 160/160 完成。Bash 2/2 PASS，evidence reduction median 为 `38.730998%` 与 `84.795918%`；全部 8 case Control/Treatment correctness 均为 10/10，behavior Gate 全通过。
- 联合 formal 为 5 PASS / 0 FAIL / 3 INCONCLUSIVE。三个 inconclusive 的 reduction median 为 `28.519417%`、`5.679012%`、`0.628088%`，只失败于冻结的 `>=35%` activation Gate；session ratios 对未激活 case 不解释。30 qualification + 4 pilot + 160 formal 的 194-run chain 已冻结。
- ACP-1.4D 对其中 60 个 frozen formal run 做只读审计且没有新增 Agent run。Read case 的 70/93 行 prefix 过宽；budget-stop search 豁免整个目标文件，该部分占 Control visible chars `73.749228%`，Treatment 只改变 1 行；两者分类为 `RULE_MISMATCH`。
- token-router search 每次 Treatment 改变 81 文件/456 行，但 Control/Treatment 各 10/10 都触发 host output truncation，source deletion 未进入饱和后的 visible denominator，分类为 `MEASUREMENT_MISMATCH`。三个 case 均只标记 prospective v2 eligible，不改历史 INCONCLUSIVE。
- ACP-1.4E offline preflight 以 0 Agent run 得到三个 v2 reduction `82.563155% / 81.832797% / 99.065322%`；token-router Control 9,522 chars，低于冻结 30,000-char censoring ceiling。
- ACP-1.4E Native qualification 30/30 完成，三个 case 均 10/10 correct/recurrence/dominant path、ambiguous=0；pilot 6/6 通过且排除于正式统计。
- ACP-1.4E formal 60/60 完成；三个 case 均 Control/Treatment 10/10 correct、G1–G8 PASS，activation median `81.310680% / 76.190476% / 98.579189%`，tool/cycle median delta=0，无新 compensation path。96-run chain 已冻结，verdict 为 `ACTIVATION_RESOLVED`。
- ACP-1.4F-0 固定 12 个 fresh case：Read/Search/Bash 各 4，跨 `alpha_service / beta_cli / gamma_pipeline` 三个 project form；每个 family 至少跨两个上下文，旧 1.4/1.4E case 不进入 primary statistics。
- F-0 将 case/scorer 分离：主合同不含 expected/scorer，独立 oracle registry 只供 outer harness；builder 不接收 `case_id`，八字段输入会递归拒绝 oracle key，也不读取文件、registry 或执行工具。
- R1 使用唯一 request anchor 与固定邻域；S1 固定 `stable path → structural key → ordinal → first N`；B1 只投影冻结结构 kind，未知/free-text/parse failure 均 passthrough。G0 违规使整个实验版本失效且旧 run 不得复用。
- F-0 frozen-index verifier 与定向 `9/9` 通过，Agent run count 为 0；366-run 是后续 primary experiment 硬上限，不代表已运行。下一步仅为 F-1 Native 12×10，builder 必须关闭。
- F-1 preflight 发现 Native candidate identity 未冻结，在 0 Agent run 时升级为 v2.1 并重建 F-0 checksum chain；没有运行数据跨版本复用。
- F-1 正式 55 attempts：54 completed、1 interrupted、65 not started；54/54 correct，Treatment builder/collector/Hook/intervention 全部未使用。
- Read 四 case 均 recurrence 10/10，但 dominant path 只有 `9/10、7/10、5/10、5/10`，最多 1 个 qualified。Search 首 case 2/10 recurrence，第二 case 前 4 次 0/4，Search 最多 2 个 qualified；coverage Gate 已不可能通过。
- runner 延迟到正常结束才汇总 dominant path，导致 Gate 在 run 40 已可知、run 54 才人工停止；14 个额外 completed runs 原样保留，记录为 `DELAYED_AUTOMATIC_STOP`，v2.1 不得恢复。
- ACP-0H 已冻结 privacy-safe `experiment-manifest-v1`；环境只接受 allowlist/digest，artifact 路径不落盘，缺失状态显式，environment/artifact checksum chain 确定 `experiment_id`。
- ACP-0H H0.3 已冻结 calibration state/policy/decision：manifest-derived state 自动比较 23 个环境、online path、语义、组件、schema、fixture 与 expected-output 字段；离线变化触发 smoke，宿主/模型/Hook/collector/关键环境或测量语义变化触发 full paired。
- ACP-0H H0.4 已冻结 benchmark registry/governance：12个历史 case 全保留，11 active、1 diagnostic-only；新 stable case 要求20次 Native/至少19次正确，stochastic case 只能使用预注册 distribution parity；CO-1.4 replay 另以 active formal baseline input 准入。
- ACP-1.4F-R 冻结审计合同先拆分 task correctness、host trajectory、evidence opportunity 与 intervention-compatible carrier，再消费54份既有私有 result/transcript；公开 artifact 不保存 raw command/output、final answer、run ID 或绝对路径。
- Read 40/40 的兼容 carrier 均为 `bash_sed`，但三个 case 的完整 trajectory Gate 因额外工具发现/非执行元调用分裂为 `7/10、5/10、5/10`；标记为 `PATH_GATE_MISMATCH`，历史 verdict 不变。
- Search 已完成14/14 的兼容 carrier 均为 `bash_rg`；v2.1 只认出2/14，另12次因 `.` scope 等命令表面差异成为 `IDENTITY_MISMATCH`。第二个 Search case 只有4-run prefix，仍保留 `INSUFFICIENT_DIAGNOSTIC_EVIDENCE`。
- 新增未来 runner 使用的纯 futility helper，可计算 case 内与 family/overall maximum achievable qualification；未接入或修改 v2.1 runner。
- ACP-1.4F-D 冻结24个新 development cases：72-run Screen 后7个进入 Extension；automatic futility 在110/240 completed 时停止，0 failed。
- D 阶段110/110 均识别到唯一 evidence opportunity 与 compatible carrier，measurement unknown/truncation 均为0；20个 case 因 evidence-too-small/intervention-not-meaningful 被拒，另1个同时 tool-path unstable。
- D 最终4个 qualified case 全部为 observed `search_like`；这否定当前 benchmark/qualification 载体的多家族充分性，不评价未启用的 intervention。
- 当前验收：F-D 定向 `18/18`、项目全量 `442/442`、registry schema 与 frozen final artifact chain 均通过；F-2/pilot/formal 未运行，v3 未创建。

- 合同版本：`acp-event-v1` / `acp-measurement-v1` / `acp-privacy-v1`；
- Token 估算固定为 `chars_div_4_v1`，四层成本不得互相冒充；
- coverage 固定为 `observed_and_matched`、`observed_not_matched`、`transcript_only`、`unsupported_tool_path`、`parse_unknown`；
- replay 保留 CO-1.4 的 12 sessions、16/16 observed-and-matched calls 与 17,651/17,651 model-visible Token，不含源码/输出正文、完整命令、prompt/transcript 或绝对路径；
- ACP Hook chain 现只注册 `scripts/acp_collector.py`；旧 audit/optimizer 研究代码保留但不进入执行链；
- collector 只持久化 `acp-event-v1` allowlist，session/path 使用 repository-domain-separated HMAC-SHA256，密钥与日志权限为 `0600`；
- collector 不返回 Hook decision，stdout/stderr 为空；不可写路径、malformed event、serialization/append failure、unknown tool 和缺失 metadata 均 fail-open；
- collector 冻结版：`acp-collector-v0.1` / `0.1.0+codex.20260817112704`。
- normalizer 只在 stable ID/session/tool-family/output-hash 唯一一致时关联 transcript；多候选、冲突或缺失保持 ambiguous/unknown，不用 timestamp 猜测；
- ledger 对 session、call、model-visible Token、linkage、raw chars 和 tool-family classification 分开记账，每个分母都包含来源/状态；
- normalizer/ledger 冻结版：`acp-normalizer-v0.1` / `0.1.0+codex.20260817141025`。
- reporter 保留冻结 A/B/C/D measurement layers；Session/Cycle/Call/Evidence-Coverage 仅作下钻，不替换合同；
- session total、model cycles 与未配对证明的 profiler 增量成本因输入无可靠来源而保持 unknown，不由 timestamp/call index 推断；
- JSON `fact-report-v1` 是唯一事实源，Markdown 只渲染；reporter 不重新关联，不改变 normalized/ledger；
- reporter 冻结版：`acp-reporter-v0.1` / `0.1.0+codex.20260817142604`。

ACP-0.4 正式 run7 完成 12 个 OFF/ON pair：24/24 runs 有 usage，12/12 pair correctness，16/16 ON tool calls 被 collector 记录；host result hash、零 stdout/stderr、五种 fail-open、cycle/call 统计门均通过。paired median session Token ratio 为 `0.999586`，但 pooled ratio 为 `1.027420`，超过冻结上限 `1.02`，因此最终状态为 `FAILED_COST_NEUTRALITY`。不删除最大正向 pair，不提高阈值，不进入 ACP-1。详见 `ACP_0_4_IMPLEMENTATION_PLAN.md` 与 `resources/acp0_4_results.json`。

ACP-0.4a 已按预注册设计完成 120/120 个新 run（OFF/ON 各 60）。pooled ratio `1.007010`、同路径 ratio `0.999022`（coverage 95%），tool-entry delta 为 0，call/cycle mean delta 均为 `+0.016667`，没有命中任何系统性路径信号；84/84 ON tool calls 被观察，host/fail-open 通过。但 `single_file_range_count` 在 OFF/ON 均只有 `3/5` correctness，四个错误 run 未删除或改判，故 correctness 硬门失败，结论只能是 `INCONCLUSIVE`，ACP-0 仍不毕业。详见 `ACP_0_4A_IMPLEMENTATION_PLAN.md` 与 `resources/acp0_4a_results.json`。

ACP-0.4b 对唯一 blocker 做独立审计：题目与 scorer 无歧义，Native/OFF-only 为 `14/20`，因此冻结为 stochastic diagnostic。随后全新 OFF/ON 各 20 次得到 `12/20` 与 `13/20`，accuracy delta `+0.05`，通过预注册下限 `-0.10`；40/40 run 完成，20/20 ON tool calls 被观察，两臂 tool calls/cycles 均为 1/2，host/fail-open 通过。correctness runs 未进入 cost/path Gate。组合 0.4a 已通过的 cost/path/host 证据后，ACP-0 正式毕业。详见 `ACP_0_4B_IMPLEMENTATION_PLAN.md` 与 `resources/acp0_4b_results.json`。

## Transparent Smart Read 冻结状态（2026-08-16）

Transparent Smart Read 研究已经正式结束并冻结：

- `status`: `BLOCKED_HOST_INTERFACE`
- `algorithm_status`: `NOT_FALSIFIED`
- `product_status`: `FROZEN`
- `next_reopen_trigger`: `SUCCESS_PRESERVING_RESULT_REWRITE`
- 冻结报告：`TRANSPARENT_SMART_READ_FROZEN.md`
- 冻结 tag：`smart-read-frozen-2026-08`
- 最终记录版插件：`0.1.0+codex.20260816145422`

最终结论：Transparent Smart Read is blocked by the current Codex host interface, not falsified at the algorithmic level。结构切片、风险门和观察点均已得到局部验证；当前通用结果替换会被宿主包装为 `Script failed / Script error`，不能满足透明且保持成功语义的产品要求。因此不进入 CO-2、不扩 shell parser、不继续当前 Hook 旁路实验，研究代码与全部 benchmark 保留。

独立的 `ACP-0 — Agent Cost Profiler` 已在冻结验证范围内完成并冻结；ACP-0H v1 至 ACP-1.3D 也已完成。ACP-1.4F v2.1 已在 F-1 因 Native coverage 不足停止，F-2–F-4 未运行；当前路线记录版仍为 `0.1.0+codex.20260819230000`。ACP 不继承 Transparent Smart Read 的优化承诺。下方内容是完整历史记录，不再代表 Transparent Smart Read 的活动待办。

## 长期治理约束（2026-08-15）

- [x] 新增长期约束清单 `LONG_TERM_CONSTRAINTS.md`。
- [x] 固化开发前五问、功能准入、统一 Token 口径、失败分类和版本冻结规则。
- [x] 明确 Smart Read 不做完整静态分析器，不提前混入 M3 长期记忆，不在缺少语义 Recall 证据时过早引入 embedding。
- [x] 要求后续 Edge、Feedback、停止策略和检索信号以真实任务、固定 baseline 和消融实验证明价值。
- [x] 从 README、设计文档和项目计划建立入口，后续开发前可直接复查。

## 2026-08-15

状态：M2c 关系导航与统一 Provider 报告已完成；下一项为 M2d 语义候选与无 oracle Provider 路由。Serena 精确取证探针 5/5 通过，Codebase-Memory CLI 当前未安装并安全降级。

M2d 进展：已将外部参考整理为 `M2D_IMPLEMENTATION_PLAN.md`，明确以可替换 Discovery Router 为交付，不把 Serena 预设为核心。M2d-0 已重跑锁定 Serena 仓库：M2c 仍为 3/5 正确，“配置工具名校验”和“只读工具集合”均以 `low_expected_gain` 错误停止；两项目标 Marker 已存在，当前归类为 Ranking/Stop 失败。

M2d v0 实现：新增轻量 `DiscoverySource/DiscoveryHit/DiscoveryResult` 和 `BoundedTextSource`；源码只在本地扫描，TaskState 只保存 Marker 命中、匹配词、置信度和成本。连续两个无关候选后触发一次预算化 rescue，相同 Query 去重，无关 Feedback 派生词失效，`low_expected_gain` 不能绕过仍可用的低成本救援。

M2d v0 benchmark：Serena 与 Agent Token Manager 两仓库共 10 个无 identifier 任务，Static Top-K 0/10、M2c 6/10、M2d 9/10，修复 3 个原失败且零正确性回归。Serena 两项遗留失败均修复；全部 Discovery 成本折算每个反事实 rescue 约 748.7 Token。仍有 1 个 Ranking 失败保留为 regression。详细口径见 `M2D_RESULTS.md`。

Serena 无 oracle 发现探针：Recall 1/5，5/5 超过 800 Token 预算，启动约 2.1 秒，未证明相对 BoundedText 的独立贡献。因此 Serena 不进入发现核心，继续用于已知目标后的精确符号/引用核验。

M2d 安装态：开发版 `0.1.0+codex.20260815075609` 已重新安装。首次缓存复跑发现并修复 `doctor` 对非 Git 安装目录的错误硬依赖；当前源码与安装缓存均为 59/59 测试通过，ResourceWarning、Skill 和插件规范校验全部通过。

M2d v0 导航层已在 commit `4af5900` 冻结。尚未完成的是原生 Codex 同一 10 任务完整会话 A/B；在此之前只报告 Navigator 管理载荷，不声称完整开发会话节省比例。

M2e 计划评审：已将外部参考任务书整理为 `M2E_IMPLEMENTATION_PLAN.md`，确认其目标与 M2d 的未完成项一致。正式版删除 `git reset --hard`/`git clean -fd`，改用隔离 worktree；主实验收敛为 Native vs 冻结 M2d，Static Top-K/M2c 保留为离线诊断 baseline；修正任务数量矛盾、工具载荷重复计量和小样本 p90 问题。下一步是 M2e-0：先校准 Codex JSONL usage、两组中立测量、实验组行为合规与运行隔离，再启动正式 benchmark。

M2e-0 已完成：建立两个独立临时 `CODEX_HOME`、detached worktree、外部 JSONL usage 解析、行为合规、diff/test/stop reason 与隐私 artifacts。定位和修改两类任务各完成 2 次顺序平衡配对，8/8 正确；Native total 中位数 94,719.5，M2d 296,484.5，配对比率中位数 3.131x，当前激活/导航循环是稳定负优化。后续 M2e-0.1a 已将实际完成命令修正为 M2d 51 vs Native 18，并确认原重复结果来自 started 空输出误计。详见 `M2E_CALIBRATION_RESULTS.md`。

M2e 安装态：校准后发现只读插件缓存目录无法创建仓库内持久缓存，已增加权限受限的系统临时回退。M2e-0.1a 当前版本 `0.1.0+codex.20260815102427` 已从 personal marketplace 重装；源码版与安装缓存均为 76/76 测试通过，Navigator 3/3、ResourceWarning-as-error 与插件规范验证通过，安装态归因结果可复现。

M2e-0.1 计划已固定：当前负优化归类为显式 Navigator 编排成本，不在此阶段调整检索。成本归因已完成；下一步实现本地内部循环的 one-shot/two-stage Compact Navigator，再加默认关闭的廉价 Activation Gate。进入 M2e-1 pilot 前要求正确性不下降、配对 Token 比率中位数不高于 1.25x、协议调用与启动/导航载荷至少下降 50%，且至少一个任务优于 Native；Ranker、Graph、Discovery 与 M3 保持冻结。

接口边界已重新核验：按 2026-08-15 官方 Hooks 文档，`PreToolUse` 可改写受支持本地工具输入，`PostToolUse` 可用 Hook 反馈替代原始模型可见结果；但任意 `updatedMCPToolOutput`、hosted tools 和选择退出默认 Hook 路径的特殊工具仍不受完整支持。因此透明优化具有受限可行性，必须通过真实模型可见 canary 实验确认，不能只依据 Hook 执行成功。

M2e-0.1a 已完成：新增版本化隐私 trace 和成本归因器，复用现有四个配对、不重跑 Codex。归因发现旧解析器把 `item.started`/`item.completed` 双计，并把 started 空输出当重复；修正后实际完成命令为 M2d 51 vs Native 18，精确重复完成 payload 和精确重复源码命令均为 0。M2d 一次性工具 payload 比 Native 多 22,161 Token，只相当于 880,246 模型 Token regret 的约 2.52%；这进一步指向额外模型往返与累积上下文重处理。下一步 M2e-0.1b 实现 Compact Navigator，Activation Gate 继续后置。详见 `M2E_0_1_ATTRIBUTION_RESULTS.md`。

M2e-0.1b Gate 1 已完成：新增两阶段 Compact Navigator，把候选、展开、structural feedback、重排和停止循环收进本地；第二阶段只接受一次带 Evidence hash 的批量 semantic feedback，并在剩余统一预算内完成受限补证。TaskState 记录 phase、成功调用数、双预算、五项内部上限和幂等元数据，源码正文不持久化；非法 phase/feedback、第三次调用和 stale Evidence 均有协议测试。Compact 专项 10/10、源码全套 87/87 通过，尚未切换 Skill 默认行为、运行冻结 M2d 9/9 Gate 2 或昂贵 Codex 会话。详见 `M2E_0_1B_GATE1_RESULTS.md`。

M2e-0.1b 安装态：版本 `0.1.0+codex.20260815111325` 已从 personal marketplace 重装。插件与 Skill 规范验证通过，源码和安装缓存逐文件一致；两边均为 87/87 测试通过，且 ResourceWarning-as-error 通过。

M2e-0.1b Gate 2 已运行并失败：新增无 oracle Compact runner，以返回后 Evidence path/symbol 判定 correctness，并固定 10 任务、预算与参数。Compact 的外部协议结果全部 ≤2，预算/hop/stop reason 无违规，但冻结原成功集合只保留 2/9；read-only 与 budgeted routing 成功，另有 4 个 verify 补证仍未到达目标、3 个目标已 selected/expanded 但未成为模型可见 Evidence。显式 M2d runner 同环境仍通过，说明回归来自 Compact 编排而非任务集失效。停止 Gate 3/4、Activation Gate 与昂贵端到端消融，先做架构复审。详见 `M2E_0_1B_GATE2_RESULTS.md`。

M2e-0.1b Gate 2 开发版本：`0.1.0+codex.20260815122816`。源码与安装缓存全套 90/90、ResourceWarning-as-error、插件和 Skill 规范验证均通过；Compact 仍为实验接口，Skill 默认路径未切换。

架构复审已完成：Old M2d 与 Compact Navigator 冻结为研究分支，产品主线转为 `CO-0` 透明 Context Optimizer 接口可行性。CO-0 只验证严格白名单内的 `cat`、明确范围 `sed -n`、简单 `rg` 与已知 symbol 读取，验收依据是原始 canary payload 未进入模型可见输入并被更小结果替代。复杂 shell、测试、构建和脚本 passthrough；Optimizer 失败必须可观测地 fail-open，白名单 fallback 不计为成功。CO 不占 M3 编号，长期记忆计划保留。详见 `CO_0_IMPLEMENTATION_PLAN.md`。

CO-0 首个真实 Gate 曾先验证简单 `cat`：原始 1,304 字符被 232 字符替代包取代，transcript 的模型 `function_call_output` 不含 canary，模型回答 `NOT_VISIBLE`。同时发现 CLI `--json` 事件仍记录原始 shell 输出，不能冒充模型输入；`continue:false + stopReason` 真实消融未替代模型结果，只有 `decision:block` 有效但呈现 tool error 形态。该阶段结论随后由完整冻结矩阵补齐，见下方最终结果。

CO-0 原型阶段安装版本曾为 `0.1.0+codex.20260815131016`；最终冻结版本已更新为 `0.1.0+codex.20260815134154`。Hook 仍默认 observe，未在普通会话启用 enforce。

CO-0 v0 最终矩阵已通过并冻结：接口门 `cat/sed/rg/known-symbol/code mode/passthrough/fail-open` 7/7；四组 Native/CO 短任务 correctness 一致，CO 相同意图重试与补偿调用均为 0。Native 模型可见工具上下文 1,601 Token，CO 计入重试后为 385，净节省 1,216（75.95%）；完整会话合计减少 1,110 Token，配对比率中位数 `0.9931x`。结果只适用于每场景一个配对的合成矩阵，插件仍默认 observe。当前开发/安装版本为 `0.1.0+codex.20260815134154`，最终测试和安装同步完成后更新。详见 `CO_0_RESULTS.md`。

CO-1 已开始：范围冻结在 Python function/async function/method/class 的完整语法切片。v0 只由显式唯一 symbol 或唯一 `sed` 范围激活；裸 `cat` 不猜测，方法携带 class header，语法单元不可拆，歧义、解析失败、超预算或替代不经济时 fail-open。CO-1 不加入缓存、搜索压缩、Graph、embedding 或长期记忆。离线完整性 Gate 完成前不运行真实 Codex 经济实验。详见 `CO_1_IMPLEMENTATION_PLAN.md`。

CO-1 Gate 1 已通过：新增独立 Python AST 切片器并接入 Hook，完整覆盖 function/async function/class/method/async method、直接 imports、唯一范围和全部 fail-open 边界；105 项旧测试零回归。源码与安装缓存均为 113/113，ResourceWarning-as-error 和插件规范验证通过，当前 Gate 2 runner 版本 `0.1.0+codex.20260815142913`。项目自身三个大文件目标的离线字符下降为 85.42%、52.02%、67.72%，中位 67.72%；该结果不是完整会话 Token 结论。下一步为 Gate 2 小型 Native/CO correctness 与模型可见 saving 矩阵。详见 `CO_1_GATE1_RESULTS.md`。

CO-1 Gate 2 策略已冻结：Native/CO 使用同任务同 commit、独立 detached worktree、独立 `CODEX_HOME` 与会话；固定 4 个 activated economics 和 2 个 fail-open 任务。主指标改为计入 same-intent retry、相邻 helper/constant/import 补读及 Hook 错误反馈后的 `Net activated-read saving`。正确率必须一致，canary 必须证明模型看到 slice 而非原始大段；不调 ranking、不改切片、不加入缓存或 search compression。下一步只实现 runner 与固定数据。详见 `CO_1_GATE2_PLAN.md`。

CO-1 Gate 2 runner 与固定数据已完成：六项离线路由为 4 个 `syntax_unique_range`、1 个 `syntax_range_ambiguous`、1 个 `syntax_slice_over_budget`；实现同 commit 独立 worktree/home、transcript call/output 配对、重试/补偿/测试分类、canary、correctness、diff、usage 与净节省汇总。当前全套 118/118、ResourceWarning-as-error 通过。真实运行分两段：先跑 `function_answer` 单案例配对验证宿主与归因，再启动其余五项。详见 `CO_1_GATE2_READINESS.md`。

CO-1 Gate 2 已运行并按冻结标准失败：6/6 correctness 一致，4/4 activated canary/package 验证通过，0 retry，4/4 补偿后 read 仍净节省，中位 42.715%、合计 1,429→775；两项 fail-open 与 Native 输出 hash 一致。但 0/4 activated 完整会话低于 Native，合计 161,077→178,805（+11.01%）。全局常量任务仅补读 28 Token，却因新增模型回合从 32,006 增到 48,850（+52.63%）。停止 Gate 3，不开始 CO-2/CO-3；下一步做 Hook-only 拆分、补读风险 fail-open 与更底层 rewrite 宿主的架构复审。详见 `CO_1_GATE2_RESULTS.md`。

CO-1 Gate 2 结果记录版插件更新为 `0.1.0+codex.20260815144432`；冻结实验本身仍来自结果文件记录的 `0.1.0+codex.20260815142913` 与 commit `e0495d6`，不得混淆或回写实验元数据。

CO-1.1 已开始：新增独立 Hook-only 实验 marketplace/plugin，除 manifest、PostToolUse Hook 和标准库记录脚本外不含 Skill、MCP、App、Navigator 或优化逻辑；schema 强制的 `defaultPrompt` 使用空数组。三臂为 Native、observe、equivalent-payload rewrite，Pilot 固定 1 个任务×3 arms×2 repetitions，并记录完整 Token、assistant cycles、tool calls 与累计 usage。离线 121/121 和实验插件规范验证通过，下一步建立冻结 commit 后运行 6 场 Pilot。详见 `CO_1_1_PLAN.md`。

CO-1.1 Pilot 已完成：6/6 correctness、单工具调用、canary 和两个累计模型周期一致。Hook-only observe 相对 Native 为 +36/+10，中位 +23 Token（约 0.074%），远小于完整插件约 0.7%；equivalent rewrite 相对 observe 为 +105/−25，方向不一致，未证明稳定 rewrite 税。assistant message 在工具前可缺省，已修正为累计 usage 事件计模型周期，当前 121/121 通过。按冻结停止规则不进入 27 场矩阵，下一步讨论 Compensation-risk Gate。详见 `CO_1_1_RESULTS.md`。

CO-1.1 结果记录版 Agent Token Manager 为 `0.1.0+codex.20260815151017`；实验 Hook-only 插件保持独立，不进入 personal marketplace 或普通产品加载路径。仓库专用实验结构测试在安装包中显式 skip，其余安装态测试正常执行。

CO-1.2 离线 Gate 已完成：独立 Hook-only 实验插件加入确定性补读风险分类与经济门，只切自包含 function/纯 method；module constant/import/helper、class field/sibling method、动态语义、显式 edit/debug/execute/compute 意图、歧义和低收益均 fail-open，并输出稳定 reason/evidence。真实 Hook 测试确认低风险 replacement 排除 raw canary、高风险不阻断 Native。源码 128/128 通过；实验插件与主结果记录版本均为 `0.1.0+codex.20260816135037`，主插件默认行为未切换。尚未运行真实模型 A/B，因此不声称完整会话节省。下一步只跑冻结的最小 Native vs Hook-only+Gate 矩阵，不加入缓存或搜索压缩。详见 `CO_1_2_OFFLINE_RESULTS.md`。

CO-1.3 Ready：被测 Hook-only+Gate 固定为 `b506818b3db87be62064ad64e62b1ad262d5a4b9`，新增自然行为 runner 与 12-task manifest，不用 prompt 强迫 `sed`。数据集为 6 Expected-hit/6 Expected-fail-open，顺序为 6 AB/6 BA；离线 12/12 分类匹配，manifest hash 为 `badf98fba553ddcae46cf479b8c3120f340d906e7c168ea837ed15826bbd2b9d`，源码 131/131 和插件规范通过。下一步运行 24 场并按 all/actual-activated/fail-open 三层给出 Strong pass、Weak signal 或 Fail；运行前不开始 CO-2。详见 `CO_1_3_READINESS.md`。

CO-1.3 已完成并判定 Fail：24/24 场完成，Native/CO correctness 均 12/12，retry/recovery 无增加，但自然行为 actual activation 为 0。16 次 Hook 尝试中 12 次为 unsupported request、4 次为 non-unique target；Codex 主要使用 `rg`、复合 `rg && sed` 和跨多个 symbol 的范围。完整 Token Native 475,489、CO 457,925，pooled `0.963061x`、配对中位 `0.999391x`，且 6 对下降/6 对上升；由于没有 replacement，差异不能归因于 Smart Read。code-mode parser 与零激活 verdict 逻辑已只在 harness 层修正并从原 transcript 重算，模型场次未重跑或替换。结果记录版主插件为 `0.1.0+codex.20260816141855`，冻结被测插件不变。停止 CO-2，下一步调查自然 read/search 的透明宿主层。详见 `CO_1_3_RESULTS.md`。

CO-1.4a Observe 已通过：复用 CO-1.3 的 12 个 CO 会话，16 个自然 code-bearing 结果（11 compound shell、1 rg、4 sed）全部被同一 PostToolUse/Bash Hook 观察；调用覆盖、17,651 model-visible Token 加权覆盖、raw→Hook→transcript 关联均为 100%。这证明旧问题是 replacement Gate 没有流量，不是 Hook 看不到结果；结论仅覆盖当前 code-mode/Bash 路径。CO-1.4b command-independent canary Hook 与 4-case 微实验 runner 已通过离线测试，冻结版本后运行，不做切片或压缩。详见 `CO_1_4A_RESULTS.md`。

CO-1.4b 已完成：4 个命令形态、8 场 observe/canary 中，canary 4/4 进入模型可见 transcript，4/4 保留完整 raw result，每场保持 1 tool call/2 model cycles，correctness 无 treatment 回归，说明 PostToolUse/Bash 可命令无关地阻断替换。但 4/4 treatment 均呈现 `Script failed / Script error`，因为通用替换依赖 `decision:block`；因此 success-preserving 透明宿主 Gate 失败。透明 Smart Read 暂停，不进入 CO-2、不扩 shell parser；已证明的 100% Bash 观察能力转为 Agent Cost Profiler / Observability 候选。结果记录版主插件为 `0.1.0+codex.20260816143944`。详见 `CO_1_4_RESULTS.md`。

已完成：

- 保存项目目标、原则、阶段计划和完成定义。
- 创建 `agent-token-manager` Codex 插件骨架。
- 创建审计所有受支持本地工具结果的 `PostToolUse` Hook。
- 日志仅保存元数据、哈希和估算 token，不保存源码正文。
- 创建汇总报告脚本和单元测试。
- 下载并记录 Codebase-Memory、Serena、Repomix 的锁定版本；上游目录不提交到本项目。
- 建立仓库内 `personal` marketplace，插件移动到标准 `plugins/agent-token-manager` 位置并再次通过验证。
- 将 `personal` marketplace 注册到 Codex，安装并启用 `agent-token-manager@personal`。
- 通过一次性 Hook 信任绕过运行只读真实任务，确认 Hook 触发并写入权限为 `0600` 的日志。
- 生成并保存首份真实基线 B001；工具结果粗估 1,424 token，完整记录见 `BASELINES.md`。
- 核对官方精确 token count 接口；当前环境无 API key，且默认上传源码不符合隐私原则，因此日志新增明确的估算方法字段，不虚标为精确 token。
- 实现无第三方运行时依赖的 `smart_read.py`：支持 outline、symbol、full 三级读取、查询排序和硬输出预算。
- Python 读取使用 AST 精确符号边界，其他文本使用保守模式；输出携带哈希、行号、置信度、省略数和截断状态。
- 修复预算裁剪后残留空区域的问题；500-token 实测仅返回最高相关符号，粗估输出 460 token。
- 新增自动可发现的 `budgeted-code-reading` Skill，规定“概要 → 目标符号 → 必要时完整实现”的读取流程，并明确编辑前必须补齐真实上下文。
- Smart Read 与审计功能共 5 项离线测试通过，插件完整验证通过。
- 插件更新至 `0.1.0+codex.20260814160344` 并重新安装，真实 Agent 成功发现和遵循 `budgeted-code-reading` Skill。
- 完成 B002：核心 payload 688 token，相对目标源码静态全量粗估约少 36%；计入运行噪声为 964 token，计入首次 Skill 加载则为 1,472 token，暂不能宣称端到端节省。
- 修复 Smart Read 经 Python 启动时未被审计器归类为读取的问题；当前共 6 项测试通过。
- 完成 Serena 真实源码同任务 A/B（B003）：两组答案质量相当；Smart Read 冷启动工具结果约少 7.7%，热读取约少 22.4%，但因轮次过多导致整个会话 usage 更差。
- 针对 B003 新增 `--symbol` 多符号精确批量读取；Skill 在符号已知时跳过 outline，并禁止重复读取完整符号。
- 审计器现能识别 `nl | sed` 等读取流水线；Smart Read 与审计共 8 项测试通过。
- 完成优化复跑 B004：答案质量不变；冷启动工具结果相对原生约少 47.6%，已加载 Skill 后约少 61.5%，但完整会话 input 仍高约 59%。
- 完成大读取候选检测与报告：默认阈值 1,000 粗估 token，可通过环境变量调整；只记录元数据，不保存内容或阻断工具。
- 当前共 9 项离线测试通过。
- 最新开发版 `0.1.0+codex.20260814161839` 已通过插件验证、安装并启用。
- 完成 M1 智能路由：粗估不超过 800 token 的小文件直接读取，大文件按具名符号、任务查询或概要自动分流。
- 完成内容哈希结构缓存：只保存符号元数据，不保存源码正文；文件变化自动失效，Hook 可汇总 hit/miss 和路由原因。
- B005 发现普通 Skill shell 无 `PLUGIN_DATA` 导致缓存禁用；修复后 B006 真实验证获得 `miss → hit`，失败与修复均已记录。
- 当前共 18 项离线测试通过；Skill 与插件验证通过。
- 安装 Serena `1.7.1.dev0`，并将 MCP 上下文裁剪为 `find_symbol` 与 `find_referencing_symbols` 两个只读工具。
- B009 原生 Serena 查询成功，正确找到目标符号与唯一引用；两次工具返回粗估约 498 token。
- 完成 `context_bundle` 的预算合并逻辑、单工具 FastMCP 原型及测试。
- B010–B012 的组合适配器均在约 20 秒被 Codex 取消；增加配置超时与启动时预热没有改变结果，已停止继续试错。
- 为避免交付坏接口，已安装配置恢复为 B009 跑通的原生 Serena 两工具后端；组合适配器只保留为实验代码。
- 最终 18 项测试、Skill 与插件验证均通过；开发版 `0.1.0+codex.20260815025803` 已重新安装。
- 保存 `SMART_READ_DESIGN.md`：将 Smart Read 正式定义为动态路标与上下文导航系统，补充路标数据契约、任务状态、信息增益排序、动态分辨率、质量门和停止规则。
- 架构决策：先建立自己的统一 Marker/Edge 契约；Serena、Codebase-Memory、AST、LSP 和 Git 作为可替换数据源，不让产品绑定某个上游接口。
- 完成 `UPSTREAM_CAPABILITY_REVIEW.md`：区分索引、上下文、编排和跨 session 四类成本，逐项记录六个相关项目实际做法、节约机制、限制和可复用位置。
- 上游采用结论：M2a 借鉴 Aider 排名和 Stacklit 稀疏增量地图；M2c 小范围试接 Codebase-Memory CLI；Serena 用于精确核验；Repomix用于基准；AgentMemory推迟到 M3。
- 环境审计发现 M2a 前置缺口：项目尚无首个 Git 基线、Serena MCP 写死本机路径、临时缓存不适合长期导航索引、Provider 契约和自动基准入口尚未建立。
- 完成阶段 1.5：创建首个 Git 基线 `0608150`；定义 `navigation_contract.py`；建立仓库级私有 SQLite v1 数据目录；新增 `doctor.py` 和 `run_benchmarks.py`。
- Provider 统一为 `index/query/expand/invalidate`，Marker/Edge包含版本、证据哈希、置信度、价值、展开成本和稳定 ID。
- Smart Read 无显式环境变量时改用目标仓库持久解析缓存；目录不可写时保持失败开放并回退临时缓存。
- 默认插件已移除写死本机路径的 Serena MCP，恢复可移植性；Serena实验代码和配置资源仍保留，后续通过运行时发现 Provider 接入。
- 当前共 26 项离线测试通过；doctor 必需项 0 错误，两个可选警告是尚未安装 Codebase-Memory CLI 与 Repomix CLI。
- 可移植开发版已更新为 `0.1.0+codex.20260815035511`。
- 完成 M2a `python-ast` Provider：增量索引模块、类、函数、方法、包含关系与本地导入关系；只保存结构证据，不保存源码正文。
- 新增 `navigation_map.py index/query/status`；Top-K 同时考虑符号、路径、任务词、中心性、公开程度和展开成本，并返回逐项评分解释与硬预算结果。
- 修复真实仓库中重复定义/overload 的稳定 ID 冲突，最终语义定义覆盖前序声明；新增回归测试。
- B014 在 Serena 430 个 Python 文件上建立 7,191 个路标与 8,187 条关系：补全索引 0.90 秒，第二次 430/430 文件未变化、0.17 秒。
- B014 精确定位两个目标方法返回 364 token；随后展开两个完整实现为 1,021 token，定位加证据共 1,385 token。相对 B003 原生工具结果 3,469 token 约少 60.1%，但比已知文件/符号直接读取 B004 的 1,337 token 多约 3.6%。
- 仅自然语言任务查询未稳定返回目标方法，明确列为 M2b 首要质量问题；未据此宣称端到端会话 token 已改善。
- 当前共 31 项离线测试通过，ResourceWarning 作为错误检查也通过。
- M2a 开发版已更新为 `0.1.0+codex.20260815053507`，Skill 与插件规范验证通过。
- 完成 M2b 持久 `TaskState`：稳定 task_id、任务隔离、seen/selected/expanded/verified、假设、预算和停止证据均写入仓库私有 SQLite。
- 完成证据去重：`marker_id + evidence_hash + region` 未变化且未截断时返回 `duplicate_suppressed`、消费 0 token；哈希变化、截断与 `--force` 可重读。
- 每次展开自动提取调用名形成结构化 Feedback；Agent 可补充相关性、信息增益、支持/否定假设、新路径/符号和下一步提示。
- Feedback 通过 `feedback_boost`、`relationship_boost`、`already_selected_penalty`、`already_expanded_penalty` 和 `irrelevant_penalty` 改变候选排序并可观测解释。
- 建立 total/navigation/expansion/remaining 四个硬预算账户；Navigator 控制的 Marker 和证据载荷累计不得越界，所有终止任务保存枚举化 stop_reason。
- B015 固定自然语言基准 3/3 正确，2/3 从静态 3 次展开降为 2 次，1/3 持平；正确率未下降。
- Serena 真实非门控探针未找到目标：两次错误候选展开后以 `low_expected_gain` 停止，说明 contains/imports 不足以跨越继承/引用关系。探针同时发现并修复已知 Marker 在小文件退化为全文读取：单次证据由 694 降至 306 token，且不再截断。
- 当前共 40 项离线测试通过，Navigator 基准、隐私哨兵与 ResourceWarning-as-error 检查通过。
- M2b 开发版已更新为 `0.1.0+codex.20260815060820`，Skill 与插件规范验证通过。
- 完成 M2c 关系索引：新增 372 条 `inherits`、4,408 条直接 `calls` 和 3,403 条白名单 `references`；Serena 430 个 Python 文件共 7,191 个 Marker、16,370 条可解析 Edge，失败文件 0。
- 无法解析的外部或歧义关系保留在独立低置信度表，不参与高置信传播；删除源/目标文件同步清理，立即复跑 `changed=0`、`unchanged=430`、零悬空 Edge。
- Navigator 关系排序区分方向和类型，输出 `relationship_boost`、`direction`、来源与置信度；语义中心性有上限，避免新增 Edge 把高连接节点推成万能答案。
- 修复两项硬预算稳健性缺口：元数据包络超过小预算时显式返回 `omitted`；局部嵌套符号无法按限定名展开时返回 `unavailable`，任务不崩溃也不越预算。
- Agent 把节点判为无关后，该节点先前自动抽取出的名称线索一并失效，避免无关分支残留污染后续排序。
- B015 回归已修复：`ToolMarkerOptional → ToolRegistry.__init__ → ToolRegistry → ToolCommands.list（排除）→ ToolSet.apply`；同一 3,600 总预算内到达目标。
- B016 真实门控使用 5 个不含代码标识符的 Serena 任务：M2b 错误停止 3/5，M2c 2/5，减少 1 个（33.3%），正确率不下降；B015 管理载荷从失败时 5,221 降为成功时 3,169 token。
- 统一 Provider 报告锁定 Serena commit `3ad624f511511bb7a77447e413425198fc574349`：内置 AST 自然语言导航门控通过；Serena 在 oracle 路径/符号下精确取证 5/5、175–1,166 token、均低于 1,200-token 预算；报告明确两者质量不可直接等价比较。
- Codebase-Memory CLI 缺失时统一报告记录 `skipped` 且不阻断内置 Provider；仍未宣称完成其实际性能比较。
- 当前 50 项离线测试全部通过，包括 ResourceWarning-as-error；固定 Navigator benchmark 3/3 正确、2/3 少一次展开；doctor 必需项 0 错误。
- 插件与 Skill 规范验证通过，M2c 开发版 `0.1.0+codex.20260815070814` 已从 personal marketplace 重新安装。

当前限制：

- token 使用字符数除以 4 粗略估算，不代表账单中的精确 tokenizer 结果。
- Hosted tools（例如 WebSearch）不经过本地工具 Hook 路径。
- Hook 已端到端验证，但尚未在 Codex Hooks 界面完成人工审查和永久信任。
- CO-0 替代路径已实现并通过冻结 canary 矩阵，但默认仍为 observe；当前有效的 `decision:block` 具有工具错误语义，必须持续监控重试和完整会话成本。
- Smart Read 对非代码文件和非 Python 语言还没有 Tree-sitter 级别的精确结构支持；Python 跨文件关系仍限于静态可解析子集。
- 临时目录缓存可能被操作系统清理；缓存命中只减少本地解析，不直接减少返回给模型的源码 token。
- Serena 当前统一探针仍依赖 benchmark 提供已知路径/符号，不是自然语言 Provider；M2d 需要实现无 oracle 路由。
- 原生 Serena B009 的完整 input 与 B006 接近，尚未达到相对现有方案至少降低 20% 的接纳门槛。
- `context_bundle` 的阻塞点是 Codex 到适配器再到 Serena 的嵌套 stdio 生命周期/取消行为；失败调用没有有效结果，不能把较低 input 误报为节省。
- 当前关系图没有数据流、多语言 Tree-sitter 或 embedding 语义检索；反射、动态分派和歧义属性调用只保留为低置信线索或不建边。
- 5 个真实任务仍有“配置工具名校验”和“只读工具集合”2 个错误停止，说明词法候选生成仍是 M2d 首要瓶颈。
- Codebase-Memory 源码已锁定但 CLI 未安装，尚无实际同口径性能数据。

CO-0 实现与验收已冻结在 commit `4b03f7d`，安装版本为 `0.1.0+codex.20260815134154`。

下一步：CO-0 已完成，可以制定 CO-1 Syntax-aware Read Slicing 的最小任务与验收标准。`decision:block` 重试、完整会话 Token 与 passthrough 等价性继续作为每阶段回归指标。
