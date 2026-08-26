# 上游项目记录

下载日期：2026-08-14

这些仓库仅用于接口研究、算法比较和后续集成验证，不直接复制进插件发布包。`upstream/` 已在外层仓库的 `.gitignore` 中排除。

各项目具体解决的 token 层次、可复用能力、限制和推荐采用顺序见 `UPSTREAM_CAPABILITY_REVIEW.md`。

## 当前已下载

- Codebase-Memory MCP
  - 地址：https://github.com/DeusData/codebase-memory-mcp
  - commit：`a6afd156b7599e3ddc67f672d80c4d10d3b72ae2`
  - 用途：结构图谱、调用关系和 MCP 接口评估。
  - 说明：浅克隆原始工作树约 1.3 GB；已使用 sparse checkout 排除两处 vendored grammar 目录，保留核心源码和文档，当前约 126 MB。被排除内容可由 Git 恢复。

- Serena
  - 地址：https://github.com/oraios/serena
  - commit：`3ad624f511511bb7a77447e413425198fc574349`
  - 用途：符号读取、引用导航和精确编辑接口评估。
  - 本地验证环境：通过 uv 安装锁定 commit 的开发版，`serena --version` 为 `1.7.1.dev0`；已初始化本地语言服务器配置。

- Repomix
  - 地址：https://github.com/yamadashy/repomix
  - commit：`e3b15a406ed78d8a463620a032a059ce911bfc0e`
  - 用途：token 统计、压缩输出和实验基线。

## 暂不下载

- AgentMemory：工作记忆属于后续阶段，当前观测 MVP 不依赖。
- Stacklit：与静态 Repo Map 和结构索引存在重叠，等基线数据出来后再决定。

## 更新原则

上游版本不自动滚动。升级前先记录新 commit、检查接口和许可证变化，并重新运行本项目基准测试。
