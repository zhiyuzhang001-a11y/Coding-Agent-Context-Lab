# Contributing

本仓库处于 maintenance-only 状态。欢迎提交：

- 安全与隐私修复；
- Host 或 transcript 格式兼容修复；
- 冻结 artifact 的可复现性修复；
- 对结论边界、未知字段或实验编号的文档澄清。

不会在原实验编号下接受通过降低 Gate、删除失败 case 或后验重分类来制造正结果的变更。新的科学问题应使用新 protocol、独立任务池和独立统计边界。

提交前请运行：

```bash
python3 -m pytest -q
```

任何 fixture 变更都必须重新检查真实路径、凭据、用户身份、源码正文和 transcript 内容。
