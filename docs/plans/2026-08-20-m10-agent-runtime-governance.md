# M10 Agent Runtime Governance 实施方案

> 状态：M10-A/M10-B/M10-C 已完成
> 创建日期：2026-08-20  
> 范围负责人：RunCrew 本地 Agent Runtime

## 1. 为什么要做

RunCrew 已经在 Review Agent 与 Coach Orchestrator 中分别实现了工具白名单、职责权限、人工确认、参数完整性、Schema 校验、超时、重试、预算和 Trace。这些能力有效，但目前分散在两套 Harness 中：

- 同一种“能不能调用工具”的判断使用不同的数据模型与 Trace 字段；
- 工具的职责、风险、读写性质、输入输出 Schema 和运行上限没有统一清单；
- 新增工具时容易只接入执行逻辑，却漏掉权限、确认、脱敏或输出校验；
- 当前 Trace 适合解释单次运行，但尚未形成跨 Harness 的统一运行/Span 契约和聚合指标。

因此 M10 不再增加业务 Agent，而是在现有 Agent 之下增加一层 **Agent Runtime Governance**：让每个工具先声明能力，再由统一 Guardrail 作出可审计决策，最后把运行事实沉淀为可查询的 Run/Span。

## 2. 架构边界

```text
Policy / Orchestrator
        ↓ 提议结构化 Action
Tool Capability Registry
        ↓ 找到版本化 Tool Manifest
Runtime Guardrail Engine
        ↓ 校验职责、访问级别、确认、参数完整性与运行上限
Existing Harness Executor
        ↓ 继续负责预算、超时、重试和状态机
Output Schema Guardrail
        ↓ 拒绝非法或越界输出
Trace / Run / Span
        ↓ 记录脱敏决策与运行指标
Deterministic Domain Service
```

通用治理层只判断“能否执行、结果能否使用”，不替代以下业务不变量：

- 计划激活与 Coach 审批的服务端重放；
- `input_hash`、`workflow_hash`、`base_revision` 与版本冲突检查；
- 用户确认后才能写入正式计划、执行结果和长期记忆；
- 恢复风险与训练建议的确定性规则。

## 3. 分阶段实施

### M10-A：Tool Manifest 与统一 Guardrail

目标：把当前真实存在的四个 Agent 工具注册为版本化能力，并让两套 Harness 复用同一套前置与后置校验。

首批工具：

| 工具 | 责任角色 | 访问级别 | 副作用 | 风险 |
|---|---|---|---|---|
| `review_running_training` | `review_agent` | `read` | 无 | 低 |
| `compare_training_execution` | `execution_agent` | `read` | 无 | 低 |
| `assess_running_recovery` | `recovery_agent` | `read` | 无 | 敏感 |
| `adjust_running_plan` | `plan_agent` | `prepare_change` | 只生成提案 | 敏感 |

交付物：

- `ToolManifest`、`GuardrailDecision`、`ToolInvocationGuardrailResult`；
- 默认 Registry，拒绝重复名称和未知工具；
- 统一校验职责、访问级别、持久化/审批能力、确认、参数 Hash 与运行上限；
- 统一输出 Schema 校验结果；
- Review/Coach Trace 增加同构、脱敏的治理字段；
- JSON Schema、专项测试和故障注入测试。

验收标准：

- 四个 Manifest 全部可导出且 Schema 稳定；
- 未注册工具、角色越权、访问级别越权、参数篡改、缺少确认、超出运行上限均在工具执行前被拒绝；
- 非法输出在进入 Agent 状态前被拒绝；
- Trace 不记录原始训练数据、身体反馈正文、Token 或完整参数；
- 既有 181 项测试保持通过。

### M10-B：持久化 Runtime Run / Span

目标：将短生命周期内存 Trace 规范化为跨 Harness 可查询的运行记录。

计划交付：

- `agent_runtime_runs` 与 `agent_runtime_spans`；
- Run 记录工作流、终态、预算、总耗时和版本；
- Span 记录 Guardrail、Policy、Tool/Node、Retry、Validation、Handoff；
- 默认仅保存 Hash、错误类型、计数和脱敏元数据；
- 单次运行详情与父子 Span 时间线 API。

已冻结的实现边界：

- `RuntimeRun` 统一 Review 与 Coach 的工作流、终态、退出原因、预算、持续时间、调用/重试计数、Trace Hash、记录时间和30天保留期；
- `RuntimeSpan` 使用根 Span 加原 Trace 事件映射，保存父 Span、事件偏移/持续时间、职责节点、工具、尝试次数和白名单 attributes；
- 原始 Prompt、模型响应、工具参数、活动/目标/计划 ID、用户消息、身体反馈与 Provider 数据不落 Runtime 表；业务关联只保存不可逆 `scope_ref_hash`；
- Mapper 是确定性纯函数；Repository 对相同 `run_id + trace_hash` 幂等，对相同 run_id 的不同 Trace 拒绝覆盖；
- `RuntimeTraceService` 使用独立短事务 best-effort 写入，任何建表缺失、锁冲突或序列化错误只返回脱敏失败类型，不得改变 Review/Coach 结果；
- M10-B 首先接入聊天首轮 Review 与训练运营 Coach 两条真实产品路径；离线 Evaluation 不写产品 Runtime 表，避免回归运行污染观测数据；
- `/api/runtime/runs` 与 `/api/runtime/runs/{run_id}` 只允许 GET，默认过滤到期记录，不在 M10-B 增加指标大盘。

验收标准：

- Review 与 Coach 生成相同顶层 Run 契约；
- 失败、超时、重试和人工确认中断都能还原时间线；
- Trace 写入失败不能改变业务终态；
- 保留期和清理策略明确。

### M10-C：跨运行指标与治理评测

目标：证明治理层不是“多一层模型”，而是可测量地发现越权、异常与性能退化。

计划交付：

- 工具调用成功率、拒绝率、重试率、P50/P95 延迟、预算耗尽率；
- 按工具、角色、工作流版本和退出原因聚合；
- 未注册工具、参数篡改、确认绕过、输出污染、Trace 写入失败等版本化场景；
- 工程观测台只读治理视图；
- 求职证据包中的指标口径和仓库证据映射。

已冻结的实现契约：

- 指标只读取未过期的 `agent_runtime_runs / agent_runtime_spans`，允许查询1—30天窗口，单次最多聚合500条 Run；超过上限必须显式标记 `truncated`，不能把部分样本冒充完整总体；
- Run 成功率按 `succeeded / 全部 Run` 计算；Guardrail 拒绝率按 `blocked Guardrail Span / 全部 Guardrail Span` 计算；工具成功率按成功终态 / 调用开始计算；重试率按 Retry Span / 调用开始计算；预算耗尽率按 `budget_exhausted / 全部 Run` 计算；
- P50/P95 使用确定性的 nearest-rank 口径，只统计 Run 总耗时；零样本时返回 `null`，不返回伪造的0毫秒；
- 聚合提供 workflow、workflow version、tool、role 与 termination reason 五类分组；role 只由 Review workflow 或 Coach Span 的 node 确定性派生，不调用模型推断；
- Runtime 表写入失败不会留下可聚合记录，因此产品指标必须携带覆盖边界说明；该失败隔离只在版本化治理评测中验证，不能声称观测数据100%完整；
- `/api/runtime/metrics`、最近 Run 与单次时间线全部只允许 GET；工程观测页只消费这些脱敏接口，不增加删除、重放、审批或训练写入能力；
- 治理套件固定覆盖未注册工具、参数篡改、确认绕过、非法输出和观测写入失败五类场景；报告明确标记为确定性合成防线评测，不代表真实 LLM 攻防效果。

## 4. 明确不做

本阶段不引入：

- 新的“审核 Agent”或“Critic Agent”；
- 向量数据库、语义记忆和无依据的自学习；
- 消息队列、Kubernetes、跨机器调度或 A2A 网络协议；
- 为短流程强行增加节点级 Durable Checkpoint；
- 让通用 Guardrail 直接决定医疗风险或修改训练计划。

只有运行时长、恢复成本或评测证据证明当前同步 Harness 不够时，才单独立项 Durable Execution。

## 5. 文档同步规则

每完成一个子阶段必须同步：

1. `docs/CURRENT_STATE.md`：只记录已验证事实；
2. `docs/ROADMAP.md`：勾选验收项；
3. `docs/ARCHITECTURE.md`：更新真实代码路径与数据流；
4. `docs/adr/`：记录关键且不可轻易逆转的决策；
5. `docs/progress/` 与 `docs/PROGRESS.md`：记录文件、测试、错误和下一入口；
6. `CHANGELOG.md`：记录用户或开发者可感知变化；
7. `docs/job/`：只写有测试或运行报告支撑的表述。

## 6. 当前执行入口

M10-A/B/C 已通过专项与202项全量验证。M10 主线已收尾；下一入口为本机视觉/点击验收，真实 DeepSeek 连续聊天同题评测仍是独立付费收尾项。
