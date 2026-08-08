# 系统架构

## 当前数据流

```text
COROS 官方服务
  │ OAuth + PKCE
  ▼
CorosMcpClient
  │ MCP initialize / tools/call
  ▼
CorosActivityProvider
  │ 原始文本或结构
  ▼
Coros Parser
  │ ActivitySummary / ActivityDetail
  ▼
Sync Service
  ├── RawProviderEvent
  ├── ActivityRecord
  └── SyncRunRecord
  ▼
Activity Review Service
  │ 确定性规则 + evidence
  ▼
CLI JSON 输出
```

## 分层职责

### Domain

位置：`src/runcrew/domain/`

只描述 RunCrew 自己理解的业务对象：活动、分圈、健康、恢复和复盘。不知道 COROS、MCP、HTTP 和 SQLite 的存在。

### Provider

位置：`src/runcrew/providers/`

负责外部世界：授权、协议调用、厂商字段和格式解析。Provider 的最终输出必须是 Domain 模型。

### Storage

位置：`src/runcrew/storage/`

负责数据库结构与查询，不负责业务判断。当前使用 SQLite + SQLAlchemy。

### Services

位置：`src/runcrew/services/`

组合 Provider、Repository 和确定性规则，定义同步和复盘流程。未来 Skill 应建立在 Services 和 Domain 之上。

### CLI

位置：`src/runcrew/cli.py`

负责接收参数和展示结果，不承担解析和业务规则。

## 数据模型

### activities

保存已经转换为 RunCrew Schema 的规范化活动。唯一键：

```text
provider + external_id
```

因此重复同步不会创建重复活动。

### raw_provider_events

保存 Provider 原始返回，用于：

- 解析器回归；
- 格式变化排查；
- 重新解析；
- 审计数据来自哪里。

### sync_runs

保存每次同步的状态和统计，用于区分：

- `completed`；
- `completed_with_warnings`；
- `failed`。

## 失败语义

| 情况 | 行为 |
|---|---|
| OAuth 失败 | 整次同步失败，不写入活动 |
| 活动列表失败 | 整次同步失败 |
| 单条活动详情失败 | 列表数据保留，记录 warning |
| Parser 无法识别格式 | 明确报错；仅显式调试时保存私有载荷 |
| 缺少分圈 | 不生成配速稳定性结论 |
| 缺少部分基础字段 | 降低 data quality confidence |

## 未来 Agent 边界

Agent 不应直接调用 COROS 文本解析器。正确关系为：

```text
Agent
→ Skill
→ Service / Domain View
→ Provider 或 Repository
```

这样才能替换 COROS、增加 FIT 或 Keep，而不重写所有 Agent Prompt。

