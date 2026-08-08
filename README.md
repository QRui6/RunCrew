# RunCrew

RunCrew 是一个以真实跑步数据为驱动的 Agent 工程项目。当前阶段只实现可靠的数据竖切：Provider 数据接入、统一领域模型、SQLite 持久化和确定性活动复盘。

> AI 或新开发者开始工作时，请先阅读 [AGENTS.md](AGENTS.md)，然后阅读 [当前状态](docs/CURRENT_STATE.md)。

## 当前能力

- 将 Provider 数据转换为统一的 `ActivitySummary` / `ActivityDetail`；
- 原始数据和规范化数据分层保存；
- 通过 `provider + external_id` 幂等同步；
- 用确定性规则生成可审计的单次跑步复盘；
- 使用脱敏 fixture 进行离线开发和回归测试。

## 文档导航

| 想了解什么 | 文件 |
|---|---|
| 项目为什么存在 | [项目上下文](docs/PROJECT_CONTEXT.md) |
| 目前做到哪里、下一步是什么 | [当前状态](docs/CURRENT_STATE.md) |
| 模块如何协作 | [系统架构](docs/ARCHITECTURE.md) |
| 后续阶段 | [开发路线图](docs/ROADMAP.md) |
| 每阶段做了什么 | [进展索引](docs/PROGRESS.md) |
| 为什么做这些技术选择 | [ADR 索引](docs/adr/README.md) |
| 术语是什么意思 | [术语表](docs/GLOSSARY.md) |
| 如何参与开发 | [开发约定](CONTRIBUTING.md) |
| 私人数据如何处理 | [安全与隐私](SECURITY.md) |
| 项目发生过哪些变化 | [变更日志](CHANGELOG.md) |

## 本地运行

```powershell
python -m pip install -e ".[dev]"
.\.venv\Scripts\runcrew.exe init-db
.\.venv\Scripts\runcrew.exe sync --provider fixture --days 30
.\.venv\Scripts\runcrew.exe status
.\.venv\Scripts\runcrew.exe activities list
.\.venv\Scripts\runcrew.exe activities review --latest
.\.venv\Scripts\python.exe scripts\verify.py
```

默认数据库位于 `data/runcrew.db`。真实 COROS 接入将在统一 Provider 接口之上实现，不会让业务层依赖 COROS 的原始文本格式。

## 同步真实 COROS 数据

```powershell
runcrew sync --provider coros --days 30 --detail-limit 1
runcrew activities review --latest --provider coros
```

命令会打开 COROS 官方授权页，并在 `127.0.0.1:8765` 临时接收 PKCE 回调。当前里程碑不持久化访问令牌或刷新令牌，因此每次真实同步都需要重新授权。

如果 COROS 的活动详情工具临时不可用，活动列表仍会入库，CLI 会返回 `completed_with_warnings` 和 `detail_errors`。系统不会把 summary 伪装成 detail，也不会因为一条详情失败而回滚整批活动。
