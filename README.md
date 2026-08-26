# Coding Agent Context Lab

> A reproducible study of context-cost measurement, evidence reduction, and the limits of transparent intervention in coding agents.

本仓库是 **Agent Token Manager** 项目的结项研究归档。项目最初希望通过缩短源码读取、搜索结果和工具输出，降低编码 Agent 的 Token 消耗。实验最终没有验证出一个能够在当前 Host 上透明运行、保持工具成功语义，并降低端到端总成本的通用产品。

这不是一个“自动节省 Token”的成品，也不作生产或账单级节省承诺。它保留的是一套可复现的测量方法、干预实验、失败边界和研究工具。

## 最重要的结论

1. **局部文本变短，不等于整个任务更省。** 冻结校准中，M2d 虽减少了单次返回的源码，但增加了导航往返；相对 Native 的配对会话 Token 比率中位数为 `3.131x`。
2. **可观察不等于可透明替换。** 当前 Hook 可以关联 Bash/code-mode 的模型可见结果，但通用 replacement 会被 Host 包装为失败，无法保持原工具的成功语义。
3. **日志总量不等于精确来源归因。** Host 日志或服务商 `usage` 可以给出请求/会话级数字；如果 Host 没有暴露系统提示、工具 schema、缓存边界或内部追加内容，就不能从 Hook 精确还原每一部分 Token 花在哪里。
4. **正确任务不一定是合格 benchmark。** 最终 development pool 中 `110/110` 次回答正确，但只有 `4/24` 个 case 达到 qualification，且全部是 `search_like`；因此不能支持 Read/Search/Structured Bash 的跨家族泛化结论。
5. **局部 evidence reduction 确实存在。** 若干冻结 case 在保持对应 correctness/behavior Gate 的同时，将目标 evidence 缩小约 `49.7%–98.6%`；这个结果只在指定 case 和测量口径内成立。

## “Token 监控”能够准确到什么程度

本项目区分四种常被混用的能力：

- **日志统计**：读取 Host 已写入的 input/output/cache usage；对已记录字段可以准确汇总。
- **成本估算**：将 usage 乘以模型价格；受价格、订阅制计费和缓存规则影响。
- **来源归因**：把 Token 分到 system prompt、schema、消息或具体工具结果；只有原始请求完整可见且 tokenizer/边界已知时才可能接近精确，否则是估算。
- **因果节省**：证明删减某部分后，完整任务质量不降且总 Token/账单下降；必须通过配对或随机化实验，不能由监控面板直接推出。

本仓库验证了部分日志观察、coverage-aware 测量和受控局部归因；没有获得当前 Host 内部所有隐藏分类，也没有证明账单级因果节省。

## 项目状态

`RESEARCH_COMPLETE / PRODUCT_NOT_VALIDATED / MAINTENANCE_ONLY`

- 不继续宣称或开发通用自动 Token optimizer。
- 不创建 ACP-1.4F v3，不解冻未测试的 R1/S1/B1。
- 维护仅限安全、兼容性、可复现性和文档修复。
- 新的本地代码库索引项目是独立后继项目，不属于本仓库。

## 仓库内容

```text
.
├── README.md
├── LICENSE
├── CITATION.cff
├── SECURITY.md
├── CONTRIBUTING.md
├── docs/
│   ├── INDEX.md
│   ├── MEASUREMENT_BOUNDARIES.md
│   ├── REPRODUCING.md
│   ├── conclusions/       # 最终结论与冻结 verdict
│   ├── methodology/       # 验证范围、合同与测量边界
│   ├── results/           # 各阶段结果和 readiness 记录
│   └── history/           # 实施计划、路线和历史状态
├── scripts/               # collector、归因、导航和实验 runner
├── resources/             # schema、fixtures、registries、冻结索引
├── tests/                 # 离线测试
├── skills/                # 预算化代码阅读 Skill
├── hooks/                 # observe-only Hook 配置
└── .codex-plugin/         # 历史插件 manifest
```

根目录少量 `ACP_*.md` 符号链接是冻结合同的兼容入口；可读文档的规范位置仍在 `docs/`。`plugins/agent-token-manager/resources` 同样只为旧 fixture 路径提供兼容链接，不是第二份数据副本。

完整阅读入口见 [`docs/INDEX.md`](docs/INDEX.md)。

## 快速验证

项目核心脚本以 Python 标准库为主；公开离线测试使用 pytest：

```bash
python3 -m pip install pytest
python3 -m pytest -q
```

公开测试会明确跳过依赖未发布私有实验库存或原开发仓库 commit 的历史重建检查，详见 [`tests/README.md`](tests/README.md)。

环境自检和内置 benchmark：

```bash
python3 scripts/doctor.py --root /path/to/repository
python3 scripts/run_benchmarks.py --pretty
python3 scripts/check_publication.py
```

运行时产生的私有数据默认写入 `.agent-token-manager/`，该目录不应提交。

## 建议引用

引用本项目时，请将它描述为编码 Agent 上下文测量与干预边界研究，而不是已验证的 Token 节省产品。机器可读引用信息见 [`CITATION.cff`](CITATION.cff)。

## License

MIT License。冻结结果和文档可以复核，但其数字只能在各自预注册范围内解释。
