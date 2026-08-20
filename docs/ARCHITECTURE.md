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
  └── DeepSeekReviewPolicy（非思考 Tool Calls；v1.1 同题评测通过）
  ▼
CLI Agent Run JSON 输出
  │ 版本化合成场景 + 故障注入 + 预期终态
  ▼
Agent Evaluation Runner
  │ 事实一致性 + 护栏执行检查 + 聚合指标
  ▼
私有 Evaluation Report
  │ 只读取规范化活动、脱敏 Trace 与私有报告
  ▼
Local Chat Product（127.0.0.1）
  ├── 对话工作区：Activity → evidence snapshot → bounded history → answer
  └── 工程观测台：Activity → Skill → Trace → Evaluation
  │
  ▼
Training Cycle Foundation
  ├── Goal → weekly Plan → planned Sessions
  ├── Daily Check-in
  └── Change Proposal → user Confirmation → revisioned Plan
  │
  ▼
Recovery Context Builder
  │ assessed_at 边界 + Provider 过滤 + 7d/14d窗口 + next session
  ▼
assess-running-recovery Skill
  │ red flag > rest > reduce > proceed / insufficient_data
  ▼
RecoveryAssessmentResult
  └── evidence + missing data + input hash + plan_action（不直接写计划）
  │
  ▼
Weekly Training Memory Builder
  ├── formal Plan + applied Execution Confirmation
  ├── confirmed Activity + Check-in + approved Change
  └── input_hash + source_refs + active/superseded/invalidated
  │
  ▼
Planning Memory Store
  └── 最近有效完整周 → evidence + next Plan input_hash
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

### Web Product

位置：`src/runcrew/web/`

使用 Python 标准库 HTTP Server 提供本地聊天产品和工程观测台，不增加 Web 框架依赖，并固定绑定 `127.0.0.1`。`ChatService` 负责活动选择、会话持久化、首轮 Training Review Agent、证据快照和有界历史；`DemoDashboardService` 继续只读聚合活动、Trace 和最终评测报告。

聊天 POST API 只接收内部活动 ID、用户消息和显式模型开关。浏览器不接收 Provider 外部 ID、原始 payload、坐标、Token 或完整数据库对象；启用 DeepSeek 时只发送规范化活动视图、确定性复盘、最近 8 条消息和当前问题。静态页面、领域契约、Service 与 HTTP 适配层分离，可独立测试。

一次聊天轮次的数据流为：

```text
选择 Activity → 创建 Conversation
→ 首问触发 ReviewAgentHarness → review_running_training
→ 保存 immutable TrainingReviewResult + Trace 快照
→ Offline / DeepSeek GroundedChatPolicy
→ 自由正文 + response_mode + 分层 grounded_claims
→ 个人事实/推断 evidence 校验；通用知识/建议保持开放；医疗措辞边界
→ 保存消息、模型、置信度、缺失数据和本轮用量
→ 后续追问复用快照，只保留最近 8 条消息进入模型上下文
```

聊天回答不采用“所有句子都必须引用”的做法。`observed_fact` 与 `data_inference` 必须绑定合法 finding；`general_knowledge` 与 `coaching_suggestion` 可以没有个人 evidence。这样既避免模型编造用户事实，也不会把通用知识和训练思路压成机械的报告复述。`running-chat-eval/1.0` 分别评测事实依据、开放表达、安全和长历史聚焦。

### Skill

位置：`skills/review-running-training/`

负责告诉 Agent 如何选择规范化数据、调用确定性 Service、验证输入输出并解释 evidence。Skill 不直接计算指标，也不读取 COROS 原始文本。

`skills/assess-running-recovery/` 是第二个领域 Skill。它以显式评估时间构建有界 Context，分开处理运动安全红旗和 RunCrew 自定义保守阈值。其 `plan_action` 只表达下一步协作意图，不拥有正式课表写入权限。

### Agent Harness

位置：`src/runcrew/harness/`

负责一次 Agent Run 的状态循环、工具白名单、确认门、步骤和调用预算、有限重试、两级超时、输出校验、脱敏 Trace 和终止状态。策略层只接收 `ReviewAgentContext`，不能读取 Provider 原始数据或直接访问数据库。

当前默认策略为确定性 `DeterministicReviewPolicy`，只会在没有观察时调用 `review_running_training`，获得合法观察后请求结束。未来 LLM Policy 必须实现同一动作协议，不能绕过 Harness。

M5-B1 已新增 `DeepSeekReviewPolicy`：通过官方 Chat Completions + 普通 Tool Calls 选择动作，使用 `httpx`、环境变量和 `SecretStr` 管理调用；模型 API 重试与业务工具重试分离。Harness 只接收模型名、Token、耗时和解析错误等白名单元数据，Prompt、响应正文、Key 和工具参数不进入 Trace。

真实首次 Smoke 证明首轮 Tool Call 可用，但第二轮仅传 Context JSON 会让模型重复调用工具。修复后在单次 Run 内保留 assistant Tool Call，并以相同 `tool_call_id` 回传已校验 Tool Result，形成标准 `assistant(tool_calls) → tool(result)` 对话。该链路已通过真实 Smoke 和 v1.1 完整同题评测。

### Evaluation

位置：`src/runcrew/evaluation/`、`evals/review_agent/`、`evals/running_chat/` 与 `evals/coach_agent/`

负责加载版本化无私人数据场景、为 Tool/Policy 注入可重复故障、运行真实 Harness、比较预期终态和确定性业务事实，并聚合任务完成、护栏、Schema、事实一致性、调用成本、延迟和退出原因指标。

评测套件可以进入 Git，生成报告只允许写入 `data/private/`。M5-B 的真实 LLM Policy 必须通过相同 `default_policy_factory` 接口进入评测器，不能创建一套只为模型演示服务的旁路。

Evaluation Report 1.1 已增加通用 Policy Usage：模型调用数、API 尝试、动作解析错误、缓存命中/未命中 Token、输入/输出/思考 Token、带价格版本的估算费用和模型耗时。确定性 Policy 的这些字段固定为零。

`coach-agent-eval/1.0` 直接运行真实 `CoachOrchestratorHarness`，用合成类型化节点结果建立 ground truth，并注入节点故障、非法动作、Handoff 篡改、跨目标输出与预算耗尽。它额外校验 Recovery→Plan 证据血缘和 `persisted=false / approved=false` 的确认中断。批准前 stale 场景运行真实 `TrainingOperationsService + 临时 SQLite`，因此写入安全没有被简化成 Mock。当前18场景确定性基线用于未来 LLM Coach Policy 同题比较。

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

### chat_conversations / chat_messages

`chat_conversations` 把一次连续对话绑定到一个 RunCrew 内部活动 ID，并保存首次 Agent 运行产生的 Training Review 与脱敏 Trace 快照。`chat_messages` 按顺序保存用户/助手消息、evidence 引用、置信度、缺失数据、模型和用量。两张表只存在于本地 SQLite，不提交 Git。

### training_goals / training_plans

保存用户明确声明的训练目标与按周组织的计划。计划课作为 `TrainingPlan` 的规范化 JSON 一并保存；同一目标同一周只能存在一份计划。草稿计划可以编辑，激活后必须通过变更提案修改。

### daily_check_ins

每天最多保存一份主观反馈，包括疲劳、酸痛、睡眠质量、准备度和可选疼痛描述。这些字段只作为恢复风险输入，不构成医疗诊断。

### plan_change_proposals / user_confirmations

保存 Agent 或用户提出的结构化计划调整，以及用户最终批准/拒绝结果。提案携带基础修订号，批准时若计划已经变化则标记为 `stale`，不覆盖新状态。

### training_execution_confirmations

保存用户对计划课执行事实的确认：关联实际 Activity、标记跳过或清除错误状态。候选匹配本身不落库；确认携带基础 revision，成功后提升计划 revision，过期操作只记录为 `stale`。

### coach_runs

保存可恢复的 Coach 编排审计，包括运行请求、受 Schema 校验的完整结果、workflow hash、Planning output hash、审核状态、正式 proposal ID 和决定时间。记录只存在于本地 SQLite；浏览器读取的是产品 DTO，不获得 Provider 原始载荷。拒绝不会创建正式提案，批准前必须重放并核对草案。

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
| Agent 尝试直接修改激活计划 | Service 拒绝，要求提交变更提案 |
| 用户批准旧 revision 的提案 | 提案标记 `stale`，计划保持不变 |
| 休息课仍包含距离或时长 | Domain Schema 拒绝矛盾状态 |
| 缺少当天或前一天身体反馈 | `insufficient_data`，不默认正常训练 |
| 出现心肺红旗 | 覆盖普通负荷判断，停止自动训练建议并提示专业帮助 |
| 训练负荷覆盖不足 | 使用时长变化代理并显式标记 method；无历史则保留缺失项 |
| 没有实际活动候选 | `unmatched`，不自动判定为 skipped |
| 多个候选接近或一条活动竞争多课 | `ambiguous`，等待用户选择 |
| 执行确认使用旧 revision | 记录 `stale`，不修改计划课 |
| 确认未来活动或提前跳过未来课 | Service 拒绝写入 |

## Agent 边界

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

M7 后续的写入型协作必须遵循：

```text
专业 Agent
→ 读取最小 TrainingCycleSnapshot
→ 调用确定性 Risk / Plan / Execution Skill
→ 提交 PlanChangeProposal（只有建议权）
→ Coach Orchestrator 汇总冲突
→ 用户 approve / reject
→ TrainingCycleService 校验 revision 并应用
```

M7-C 当前可执行关系为：

```text
DeterministicCoachPolicy（只做路由）
  ├── Execution Agent → compare_training_execution（read）
  ├── Recovery Agent  → assess_running_recovery（read）
  └── Plan Agent      → adjust_running_plan（prepare_change）
                         │
                         └── change proposal draft
                              → Harness 暂停
                              → 用户审核（当前不自动写入）
```

Policy 只接收完成状态、恢复路由、下一节点类型化请求和剩余预算。Harness 负责固定参数、工具白名单、目标/计划范围、Recovery `input_hash` 血缘、Schema、重试、超时和退出条件。跨节点 Handoff 只记录字段名与请求哈希，避免把身体反馈和活动详情复制进 Trace。

M7-D 产品审核链：

```text
训练闭环抽屉
  → 结构化身体反馈（本地 SQLite）
  → Coach Run（保存请求、结果与 planning hash）
  → 用户 approve / reject
       ├── reject：只关闭 Coach Run，不创建正式提案
       └── approve：服务端以原请求重放 Coach
              ├── 结果变化 → stale，不写计划
              └── 结果相同 → 创建正式提案 → revision 校验 → 应用
```

Decision API 不接受任何计划 patch。浏览器只表达决定，变更内容必须来自服务端保存并重新验证的 Coach 结果。

M7-E 评测链：

```text
versioned synthetic case
  → real CoachOrchestratorHarness
  → typed node fixture / fault injection
  → Run Result Schema + fact + lineage + confirmation judgement
  └── approval_stale → real TrainingOperationsService + temporary SQLite
  → aggregate metrics + suite_hash
  → private evaluation report
```

## M9 可审计训练记忆

```text
网页 / CLI 显式确认
  → AthletePreferenceSubmission（confirmed 必须为 true）
  → Athlete Memory Service
       ├── 相同值：幂等返回当前版本
       ├── 新值：旧版本 superseded + 新版本 supersedes_id
       └── 停用：archived，不硬删除
  → athlete_preferences / SQLite
  → Planning Preference Store（按 as_of、status、有效期检索）
  → Weekly Plan Draft
       ├── 当前目标 available_weekdays 优先
       ├── 偏好可用时安排 long_run
       └── preference id/source/schema/applied → evidence + input_hash
  → 用户激活前服务端重放；偏好变化则拒绝旧草案
```

当前 Memory 分层为：

| 层 | 当前实现 | 作用范围 |
|---|---|---|
| 对话上下文 | 最近8条消息 | 当前会话短期连续追问 |
| Evidence Snapshot | 不可变复盘结果与 Hash | 当前活动事实锚点 |
| 训练业务状态 | 目标、计划、执行、Check-in、Coach Run | 跨会话确定性状态 |
| Agent Working State | Coach 单次运行状态与 Handoff | 单次编排 |
| 待确认候选 | 原消息引用/Hash、类型化值、置信边界、有效期和决定状态 | 聊天到正式偏好的人工确认缓冲区 |
| 长期偏好 | 已确认长跑星期、来源、时效、替代链 | 跨会话/跨目标默认偏好 |
| 周训练记忆 | 正式计划、已确认执行、反馈、版本与来源 | 跨周复盘和下一周 Planning 基线 |

周训练记忆链路为：

```text
完整正式训练周 + as_of
  → 只读取 applied 执行确认及其 Activity
  → 聚合 Check-in 与已批准计划变更
  → stable input_hash + source_refs + missing_data
  → active version（旧版本 superseded，或人工 invalidated）
  → Planning 读取最近有效版本
  → memory id/version/hash 进入 evidence 和计划 input_hash
```

按职责 Memory Context 链路为：

```text
全部长期偏好与周训练记忆候选
  → 按 role / goal_id / as_of / target_week_start / status 过滤
  → 按职责投影允许字段
  → 按条数与字符预算确定性截断
  → context_hash（仅业务可见上下文）+ audit_hash（完整选择审计）
  → Execution / Recovery / Plan 结果、Evidence、Trace 与网页审计视图
```

| 职责 | 允许的正式记忆 | 固定预算 | 边界 |
|---|---|---:|---|
| Execution | 无 | 0条 / 0字符 | 只比较当前处方与已确认 Activity，历史记忆全部按 `role_not_allowed` 审计排除 |
| Recovery | 周训练记忆 | 2条 / 1400字符 | 只读取负荷、完成度与恢复聚合，不读取偏好，也不改变安全阈值 |
| Plan | 长期偏好 + 周训练记忆 | 5条 / 1800字符 | 读取排课偏好和训练基线，不接收疼痛等级、急性症状等恢复敏感字段 |

`context_hash` 只覆盖真正进入 Agent 的职责投影，因此新增一条无关或失效候选不会制造业务 Hash 漂移；`audit_hash` 覆盖所有选中/排除决定与预算使用量，因此审计仍能发现候选集合变化。

聊天 Memory Candidate 写入链路为：

```text
用户消息
  → 高精度规则识别受支持的长期偏好
  → pending Candidate（message_id + source_text_hash + candidate_hash + 7天有效期）
  → 用户确认 / 拒绝 / 新候选替代 / 自动过期
  → 确认时服务端重算 Candidate Hash 并重读原消息
  → 从 Candidate 重建 confirmed=true 的正式提交
  → Athlete Preference Service 幂等写入或版本替代
  → 下一次 Plan Memory Context 才能读取
```

浏览器只提交决定和预期 Candidate Hash，不提交候选值；候选表不复制用户消息正文。M9 不允许普通聊天或 LLM 直接写入正式记忆。

M9-E 评测链为：

```text
evals/memory/cases.json（输入 + 固定期望）
  → Candidate 纯规则场景
  → 隔离 SQLite 中的正式 Repository / Candidate / Preference / 来源重放服务
  → 正式 Memory Context Builder 的职责召回与注入场景
  → 逐场景 Observation + Checks
  → 召回 / 拒绝 / 生命周期 / 来源 / 确认 / 职责 / 注入 / Schema 指标
  → Suite Hash + 私有 Report
```

Suite Hash 只绑定版本化题集，不绑定机器耗时；报告中的 P95 仅作本次运行诊断。无关或不可用 Memory 可以改变 Audit Hash，但不得改变实际 Context Hash。当前16场景全部满足期望，结构化过滤没有暴露检索瓶颈，因此仍不引入向量数据库。

M9-F Memory 控制面链路为：

```text
用户打开“记忆档案”
  → GET /api/memory/overview（按需加载）
  → MemoryControlService 聚合 Candidate / Preference / Weekly Memory
  → 通过原消息 ID 生成最小来源摘要，不复制正文或 Provider 标识
  → 对每个激活目标运行正式 Execution / Recovery / Plan Context Builder
  → 展示生命周期、条数/字符预算、选中与排除原因
  → 用户确认 / 停用 / 标记失效
  → 复用 ChatService / TrainingOperationsService 的完整性与确认状态机
  → 后续 Context Builder 自动排除不可用版本并保留审计
```

控制面不是新的 Memory Store，也不允许硬删除或 LLM 直接写入。普通聊天首屏不预取该总览，避免把跨目标聚合成本加入每轮对话。

## 可讲解的系统视图

用于求职演示的两份精简图不替代本文，而是把实现压缩为面试时可以快速讲清的视图：

- [系统架构图](demo/system-architecture.md)：Provider、Domain、Memory、Skill、Harness、Trace 与 Evaluation 的分层关系；
- [训练闭环时序图](demo/training-loop-sequence.md)：活动确认、三职责 Agent 协作、用户审核、服务端重放和 stale 防护的完整顺序。
