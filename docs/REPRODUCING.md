# Reproducing the Archive

## Requirements

- Python 3.11 or later (`tomllib` is used by the frozen protocol checks)
- Git
- pytest

Serena 等外部 Provider 只用于历史可选实验，不是核心测试的前置条件。

## Test suite

```bash
python3 -m pip install pytest
python3 -m pytest -q
```

公开 profile 会明确跳过需要未发布私有库存或原开发仓库 commit 的历史重建测试。跳过清单及其原因见 `tests/README.md` 和根目录 `conftest.py`；这不会把缺失的私有证据伪装为可公开重放。

## Repository health

```bash
python3 scripts/doctor.py --root .
python3 scripts/run_benchmarks.py --pretty
python3 scripts/check_publication.py
```

## Frozen evidence

`resources/` 中的 `*_frozen_*_index.json` 将协议、输入、结果和 checksum 串联起来。正式解释应优先读取冻结索引指向的 artifact，不要将未冻结 pilot 或 development 数据混入正式统计。

## Privacy and local data

运行 collector、navigation map 或 experiment runner 时，可能产生本地 transcript 派生数据、SQLite 索引或工作树信息。这些内容必须保留在 `.agent-token-manager/`、`.evaluation-data/` 或其他被忽略的本地目录。

公开 fixture 应满足：

- 不含真实提示、源码正文或原始 transcript；
- session、path 和 repository identity 已伪名化；
- 未知字段不通过推断补齐；
- checksum 与冻结索引仍可验证。

## Historical runs

部分 runner 依赖特定 Host 版本、Codex 本地 transcript 格式或已经结束的实验环境。测试通过只证明离线合同和 fixture 可复现，不承诺历史在线 Agent run 可以在未来 Host 上逐字重放。
