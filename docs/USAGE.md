# Usage Guide

## 先选择你的目的

本仓库有四种使用方式。不要从历史实验 runner 开始；先选择与你的目标匹配的入口。

```text
只想了解研究结论
  → 阅读结项报告，不需要安装

想确认公开证据和代码仍可运行
  → 克隆仓库，运行 publication check 和 pytest

想在本地代码库中尝试预算化读取
  → 直接运行 context_router 或 Task Navigator

想在 Codex 中启用 observe-only 审计和读取 Skill
  → 通过仓库 marketplace 安装插件
```

## 1. 阅读研究结论

不需要安装任何程序。按以下顺序阅读：

1. `docs/conclusions/PROJECT_CLOSURE_AND_VALUE.md`
2. `docs/MEASUREMENT_BOUNDARIES.md`
3. `docs/conclusions/TRANSPARENT_SMART_READ_FROZEN.md`
4. `docs/conclusions/ACP_1_4F_D_RESULTS.md`

适合：Agent 工程师、eval 设计者，以及评估“缩短上下文是否真的省 Token”的研究者。

## 2. 验证公开仓库

```bash
git clone https://github.com/zhiyuzhang001-a11y/Coding-Agent-Context-Lab.git
cd Coding-Agent-Context-Lab
python3 -m pip install pytest
python3 scripts/check_publication.py
python3 -m pytest -q
```

公开 profile 只运行其输入已经发布的离线检查。依赖私有 transcript 派生库存或原开发仓库 commit 的历史重建测试会被明确跳过；详见 `tests/README.md`。

适合：复核 schema、collector、归因、导航、qualification、futility 和冻结 artifact 合同。

## 3. 对本地代码库使用预算化读取

先确保目标仓库忽略私有索引：

```gitignore
.agent-token-manager/
```

环境检查：

```bash
python3 plugins/agent-token-manager/scripts/doctor.py \
  --root /path/to/target-repository
```

已知文件、按任务查询：

```bash
python3 plugins/agent-token-manager/scripts/context_router.py \
  /path/to/target-repository/src/example.py \
  --query "authentication dependency" --budget 800 --pretty
```

已知符号：

```bash
python3 plugins/agent-token-manager/scripts/context_router.py \
  /path/to/target-repository/src/example.py \
  --symbol Service.run --budget 1000 --pretty
```

跨文件、自然语言任务使用 Task Navigator：

```bash
python3 plugins/agent-token-manager/scripts/navigation_map.py \
  index /path/to/target-repository

python3 plugins/agent-token-manager/scripts/task_navigator.py \
  start /path/to/target-repository \
  --task "locate stale credential validation" \
  --total-budget 3000 --navigation-budget 800 --expansion-budget 2200
```

`start` 返回 `task_id`。随后依次使用 `next` 取候选、`expand` 展开证据、`feedback` 反馈相关性，证据足够时用 `stop` 结束。完整命令可运行各脚本的 `--help` 查看。

这一模式的作用是限制和组织返回证据，不代表整个 Agent 会话一定减少 Token。修改代码前仍应读取完整目标区域和必要上下文。

## 4. 安装 Codex 插件

要求当前 Codex CLI 支持 `codex plugin` 命令。

添加 GitHub marketplace 并安装：

```bash
codex plugin marketplace add \
  zhiyuzhang001-a11y/Coding-Agent-Context-Lab --ref main

codex plugin add agent-token-manager@coding-agent-context-lab
```

安装后请新建一个 Codex 任务，使 Skill 和 Hook 被重新加载。可以这样请求：

```text
Use budgeted-code-reading to locate the implementation of request validation.
```

或者：

```text
Summarize my observed tool-result payloads and explain the measurement limits.
```

插件包含 observe-only `PostToolUse` collector。数据保存在 Codex 分配的私有插件数据目录，不上传云端。报告只覆盖被 Hook 观察到的工具结果，并使用 `字符数 / 4` 估算 payload；它不是完整请求 Token、账单成本或精确来源归因。

更新插件：

```bash
codex plugin marketplace upgrade coding-agent-context-lab
codex plugin add agent-token-manager@coding-agent-context-lab
```

卸载：

```bash
codex plugin remove agent-token-manager@coding-agent-context-lab
```

## 5. 使用实验资产

如果目的是设计新的 Agent eval，可复用：

- `acp_collector.py`、`acp_normalizer.py`、`acp_reporter.py`：coverage-aware 测量链；
- `build_experiment_manifest.py`：artifact 与 checksum manifest；
- `validate_benchmark_registry.py`：benchmark registry 检查；
- `acp1_4f_futility.py`：qualification 的数学 futility 判断；
- `resources/*schema.json`：事件、registry、结果和归因 schema。

新的实验必须使用新的 protocol、任务池和统计边界。不要把本仓库 development runs 当作新实验的 formal holdout，也不要通过降低旧 Gate 改写结论。

## 输出应该怎样解释

- `estimated_response_tokens`：工具结果字符数的粗略换算。
- `provider usage`：若 Host 日志提供，可用于请求或会话汇总，但不自动给出来源细分。
- `source attribution`：取决于可见请求、tokenizer 和 cache 边界；缺失时必须保留 unknown。
- `evidence reduction`：只说明指定 evidence 变小。
- `end-to-end savings`：必须另做保持质量的配对或随机化实验，本项目没有证明通用成立。
