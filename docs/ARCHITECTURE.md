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
  ├── Coros Parser（详情 / 分圈）
  └── FIT URL → private cache → Garmin FIT Parser
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
Training Context Builder
  │ 目标活动时间锚定 + 7/28 天历史 + input_hash
  ▼
Training Review Service
  │ completion / load change / anomaly
  ▼
review-running-training Skill
  │ Schema 验证 + evidence 解释
  ▼
Review Agent Harness
  │ 有界 Context + Action Schema + 权限 + 预算 + 重试 + Trace
  ├── DeterministicReviewPolicy（离线基线）
  └── DeepSeekReviewPolicy（非思考 Tool Calls；当前仅 Mock 验证）
  ▼
CLI Agent Run JSON 输出
  │ 版本化合成场景 + 故障注入 + 预期终态
  ▼
Agent Evaluation Runner
  │ 事实一致性 + 护栏执行检查 + 聚合指标
  ▼
私有 Evaluation Report
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

### Skill

位置：`skills/review-running-training/`

负责告诉 Agent 如何选择规范化数据、调用确定性 Service、验证输入输出并解释 evidence。Skill 不直接计算指标，也不读取 COROS 原始文本。

### Agent Harness

位置：`src/runcrew/harness/`

负责一次 Agent Run 的状态循环、工具白名单、确认门、步骤和调用预算、有限重试、两级超时、输出校验、脱敏 Trace 和终止状态。策略层只接收 `ReviewAgentContext`，不能读取 Provider 原始数据或直接访问数据库。

当前默认策略为确定性 `DeterministicReviewPolicy`，只会在没有观察时调用 `review_running_training`，获得合法观察后请求结束。未来 LLM Policy 必须实现同一动作协议，不能绕过 Harness。

M5-B1 已新增 `DeepSeekReviewPolicy`：通过官方 Chat Completions + 普通 Tool Calls 选择动作，使用 `httpx`、环境变量和 `SecretStr` 管理调用；模型 API 重试与业务工具重试分离。Harness 只接收模型名、Token、耗时和解析错误等白名单元数据，Prompt、响应正文、Key 和工具参数不进入 Trace。

真实首次 Smoke 证明首轮 Tool Call 可用，但第二轮仅传 Context JSON 会让模型重复调用工具。当前修复在单次 Run 内保留 assistant Tool Call，并以相同 `tool_call_id` 回传已校验 Tool Result，形成标准 `assistant(tool_calls) → tool(result)` 对话。该修复已通过 Mock，真实复验待完成。

### Evaluation

位置：`src/runcrew/evaluation/` 和 `evals/review_agent/`

负责加载版本化无私人数据场景、为 Tool/Policy 注入可重复故障、运行真实 Harness、比较预期终态和确定性业务事实，并聚合任务完成、护栏、Schema、事实一致性、调用成本、延迟和退出原因指标。

评测套件可以进入 Git，生成报告只允许写入 `data/private/`。M5-B 的真实 LLM Policy 必须通过相同 `default_policy_factory` 接口进入评测器，不能创建一套只为模型演示服务的旁路。

Evaluation Report 1.1 已增加通用 Policy Usage：模型调用数、API 尝试、动作解析错误、缓存命中/未命中 Token、输入/输出/思考 Token、带价格版本的估算费用和模型耗时。确定性 Policy 的这些字段固定为零。

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
| COROS 详情/分圈失败 | 最多请求一条 FIT；优先复用私有缓存 |
| FIT URL 过期、超时或服务限额 | 删除不可解析缓存；列表数据保留并记录 warning |
| FIT CRC 或 Schema 无效 | 不写入伪详情；删除不可用缓存并记录 warning |
| Parser 无法识别格式 | 明确报错；仅显式调试时保存私有载荷 |
| 缺少分圈 | 不生成配速稳定性结论 |
| 缺少部分基础字段 | 降低 data quality confidence |
| 缺少训练计划 | `training_completion=unknown` 并返回 `requires` |
| 两个七天窗口缺少训练负荷 | `load_change=unknown`，不推断负荷趋势 |
| 缺少分圈和同类型历史配速 | `training_anomaly=unknown` |

## 未来 Agent 边界

Agent 不应直接调用 COROS 文本解析器。正确关系为：

```text
Agent
→ Skill
→ Service / Domain View
→ Provider 或 Repository
```

这样才能替换 COROS、增加 FIT 或 Keep，而不重写所有 Agent Prompt。

当前实际执行关系进一步收紧为：

```text
Policy
→ call_tool / finish Action Schema
→ Harness 权限与预算检查
→ review_running_training
→ TrainingReviewResult 校验
→ observation
→ Policy
→ finish
→ Agent Run Result + Trace
```
