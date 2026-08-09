# RunCrew

RunCrew 是一个以真实跑步数据为驱动的 Agent 工程项目。当前已经形成可靠数据竖切和第一个可回放 Training Review Skill。

> AI 或新开发者开始工作时，请先阅读 [AGENTS.md](AGENTS.md)，然后阅读 [当前状态](docs/CURRENT_STATE.md)。

## 当前能力

- 将 Provider 数据转换为统一的 `ActivitySummary` / `ActivityDetail`；
- 原始数据和规范化数据分层保存；
- 通过 `provider + external_id` 幂等同步；
- COROS 详情失败时按“详情 → 分圈 → FIT”降级，并缓存私有 FIT；
- 用确定性规则生成可审计的单次跑步复盘；
- 用 `review-running-training` Skill 复盘训练完成度、七天负荷变化和训练异常；
- 通过 `input_hash + ruleset_version` 回放同一结论；
- 使用不含位置的合成 FIT 进行离线开发和回归测试。

## 文档导航

| 想了解什么 | 文件 |
|---|---|
| 项目为什么存在 | [项目上下文](docs/PROJECT_CONTEXT.md) |
| 项目各阶段如何实施、面试如何讲 | [项目实施全景与面试说明](docs/RunCrew-项目实施全景与面试说明.md) |
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
.\.venv\Scripts\runcrew.exe training review --latest --provider fixture
.\.venv\Scripts\python.exe scripts\verify.py
```

默认数据库位于 `data/runcrew.db`。真实 COROS 接入位于统一 Provider 接口之下，业务层不依赖 COROS 的原始文本格式。

## 同步真实 COROS 数据

```powershell
runcrew sync --provider coros --days 30 --detail-limit 1
runcrew activities review --latest --provider coros
```

命令会打开 COROS 官方授权页，并在 `127.0.0.1:8765` 临时接收 PKCE 回调。当前里程碑不持久化访问令牌或刷新令牌，因此每次真实同步都需要重新授权。

如果 COROS 的活动详情与分圈工具临时不可用，Provider 会请求一条 FIT 下载地址，并使用 Garmin 官方 SDK 确定性解析。FIT 缓存在 `data/private/fit/`，文件名不含 LabelId；缓存命中时不会再次消耗下载额度。若三级详情来源均失败，活动列表仍会入库，CLI 返回 `completed_with_warnings` 和 `detail_errors`，不会把 summary 伪装成 detail。

只读查看某个 COROS MCP 工具的当前 schema：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_coros_tool.py queryActivityFitFileDownloadUrls
```

## 运行 Training Review Skill

```powershell
.\.venv\Scripts\runcrew.exe training review --latest --provider coros
```

如果已知本次训练计划，可以显式传入目标：

```powershell
.\.venv\Scripts\runcrew.exe training review --latest --provider coros `
  --planned-distance-km 8 --planned-duration-minutes 45
```

缺少计划或历史训练负荷时，Skill 会返回 `unknown` 和所需数据，不会猜测结论。
