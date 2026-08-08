# Changelog

本项目使用阶段化变更记录。当前处于早期开发阶段，尚未发布稳定版本。

## 2026-08-08

### Added

- 创建 RunCrew Python 项目和本地 `.venv`；
- 增加 Activity、Health、Recovery 和 Review 领域模型；
- 增加 ActivityProvider 协议与 fixture Provider；
- 增加 COROS OAuth + PKCE、MCP 客户端和格式化文本解析；
- 增加 SQLite activities、raw events、sync runs；
- 增加幂等同步与详情错误隔离；
- 增加确定性活动复盘；
- 增加 CLI：`init-db`、`status`、`sync`、`activities list/review`；
- 增加 9 项自动化测试；
- 增加 AI 项目入口、当前状态、路线图、架构、ADR、进展索引和安全文档；
- 增加统一自检脚本 `scripts/verify.py`。
- 初始化独立 Git 仓库，默认分支为 `main`。

### Verified

- fixture 重复同步不会生成重复活动；
- 真实 COROS 活动列表可以授权、解析、入库和复盘；
- Token 未持久化；
- COROS 详情服务异常时列表数据不会回滚。

### Known Issues

- COROS `getActivityDetail` 和 `queryActivityLapData` 当前返回服务端异常；
- 尚未实现 FIT 详情兜底；
- 尚未实现 Token 加密缓存和数据库迁移。
