# M2d v0 实验结果

最后更新：2026-08-15

## 结论

受限文本候选源作为低收益导航后的 rescue 有明确净贡献，可以进入 Smart Read v0 核心。Serena 的无 oracle 子串发现 Recall 低且返回成本超预算，不进入候选发现核心，继续保留为已知目标后的精确核验 Provider。

这不是“完整开发会话节省”结论。下列 Token 仅指 Navigator 可控制的候选、导航元数据和源码证据载荷，估算方法仍为 `chars_div_4_v1`。

## 固定条件

- M2d v0 实现 commit：`4af5900`。
- 插件版本：`0.1.0+codex.20260815075609`。
- 主仓库：锁定 Serena commit `3ad624f511511bb7a77447e413425198fc574349`。
- 第二仓库：`agent-token-manager` 当前实现仓库。
- 任务：10 个不含目标路径、类名或函数名的英文自然语言任务。
- 每任务预算：total 8,400；navigation 2,400；expansion 6,000。
- 最大选择步骤：8；单次源码展开上限：650。
- Benchmark oracle 只用于离线判定相关性与正确目标，不进入 Navigator 的任务输入或候选查询。

## 10 任务结果

```text
Static Top-K          0 / 10
M2c Navigator         6 / 10
M2d bounded rescue    9 / 10
```

- 修复 3 个 M2c 失败任务；没有让 M2c 原本成功的任务失败。
- Serena 仓库的两个遗留失败全部修复：
  - 配置工具名校验：5,056 → 3,175 管理载荷 Token；
  - 只读工具集合：4,854 → 1,708 管理载荷 Token。
- 两项 Serena 遗留任务的纯 discovery payload 分别为 385 和 353 Token。
- 全部 10 项中，平均每个反事实 rescue 的 discovery 成本为约 748.7 Token；该数包含失败和非必要查询，避免只报告最好看的成功调用。
- 原本成功任务触发了 2 次候选查询；两项最终总载荷均未高于 M2c，因此 `routing_regret_tokens=0`，但 `routing_regret_queries=2` 继续保留为路由优化指标。
- 仍有 1 个失败：“检查环境依赖、可选后端和私有数据目录”。目标已被候选源命中但未在 8 步内选中，归类为 Ranking 失败并保留为 regression case。

## Serena 无 oracle 探针

固定条件：最多 4 个从自然语言自动选择的子串查询，每任务预算 800 Token，不注入目标路径或 Symbol。

结果：

- 启动约 2,126 ms；
- target Recall 为 1/5；
- 5/5 返回载荷均超过 800 Token 预算；
- 单任务返回约 1,059–9,878 Token；
- 只在“只读工具集合”任务找到目标，但受限文本源已经以更低成本找到同一目标；
- 没有证明相对受限文本源的独立贡献。

因此 Serena 不实现为默认 DiscoverySource。这样删除 Serena 发现能力不会让当前 M2d 结果变差，也避免重新引入 MCP 启动、LSP 和大候选列表成本。

## 机制与安全边界

- `BoundedTextSource` 本地扫描现有 Marker 的源码范围，只把 Marker ID、匹配词、分数、置信度和成本写入 TaskState，不保存或返回源码正文。
- 连续两个 Agent 判定为无关的候选后才自动触发一次 rescue；原本顺利沿图推进的任务不调用 Source。
- 相同 Source 与 Query 去重；每个任务最多两次 discovery 记录；Query term 最多 16 个。
- 无关 Feedback 的派生词不进入后续 Query；自动提取词只有所在 Marker 被 Agent 确认相关后才可进入。
- Discovery Token 计入现有 navigation 与 total budget，不建立预算外账户。
- Discovery 只提供排名 boost，不能绕过真实源码展开与证据验证。

## 局限与未完成项

- 10 个任务足够作为 M2d v0 功能验收，不支持普遍有效结论。
- 第二仓库是项目自身，仍需增加独立 Web、CLI 或库仓库，避免自测过拟合。
- 当前只覆盖 Python AST Marker。
- Static Top-K 是同一地图前 8 个候选，不等同于完整原生 Codex 会话。
- 尚未在同一 10 任务集上运行原生 Codex A/B；因此不能冻结“完整会话节省”结论。
- `environment-diagnostics` Ranking 失败尚未修复，不应通过继续提高 discovery boost 盲目过拟合。

## 安装态验证

- 开发版：`0.1.0+codex.20260815075609`。
- 源码工作区：59/59 测试通过，ResourceWarning 作为错误。
- 安装缓存：59/59 测试通过，Skill 与插件规范校验通过。
- 安装态首次复跑发现 `doctor` 错把非 Git 插件缓存目录视为必需错误；现已改为可选警告，并允许显式数据目录下使用稳定路径身份，新增回归测试。

M2d v0 的导航实现与管理载荷 benchmark 在 commit `4af5900` 冻结。完整原生 Codex 会话 A/B 是下一项独立验证，不修改或夸大本冻结结论。
