# 术语表

## Agent

能够读取上下文、选择行动、调用工具、检查结果并继续循环的软件角色。不是简单的一次性聊天回复。

## MCP

Model Context Protocol。让 AI 客户端用统一方式发现和调用外部工具。本项目用 COROS MCP 读取跑步数据。

## Provider

外部数据来源适配器。它负责理解 COROS、FIT 或 Keep 的格式，再输出 RunCrew 统一数据模型。

## Schema

数据的明确结构和校验规则。例如一条活动必须有来源 ID、开始时间、运动类型和时长。

## ActivitySummary

一条活动的基础摘要：时间、距离、时长、配速、平均心率等。

## ActivityDetail

比 Summary 更详细的数据，通常包含分圈、步频、海拔和时间序列。

## Fixture

人工构造或脱敏的固定测试数据。它不依赖真实账号，可以稳定重复测试。

## 幂等同步

同一批数据同步多次，数据库仍只有一份活动，而不是每次都新增重复记录。

## 确定性分析

相同输入必然产生相同输出的普通代码规则。当前配速稳定性判断属于确定性分析，不使用 LLM。

## Evidence

支撑结论的数据证据。例如“配速稳定”的证据是分圈数量和配速变异系数。

## Finding

Training Review Skill 输出的一条结构化结论，由类型、等级、中文说明和 evidence 组成。当前固定包含训练完成度、负荷变化和训练异常三类。

## input_hash

对一次训练复盘的规范化输入计算出的 SHA-256。相同输入应得到相同 hash 和结果，用于回放与审计。

## ruleset_version

确定性训练规则的版本号。规则阈值发生变化时应升级版本，避免新旧结果无法区分。

## unknown + requires

数据不足时的标准降级方式。`unknown` 表示当前不能可靠判断，`requires` 明确列出还需要哪些数据；它不是系统异常。

## Harness Engineering

围绕 Agent 的运行环境工程，包括权限、状态、超时、重试、日志、追踪、预算、审批和故障隔离。

## Policy

Agent 的动作选择策略。M4 默认 `DeterministicReviewPolicy` 根据有界 Context 选择 `call_tool` 或 `finish`；未来可以替换为 LLM Policy，但仍必须输出同一 Action Schema。

## Action

Policy 请求 Harness 执行的结构化下一步。当前只有 `call_tool` 和 `finish` 两种，不能用自由文本绕过权限检查。

## Observation

工具执行后返回给 Policy 的已校验结果。当前 Observation 只能是 `TrainingReviewResult`，非法或目标活动不一致的结果不会进入下一轮。

## Trace

一次 Agent Run 的结构化事件序列，记录动作、权限检查、工具尝试、重试、验证、预算和退出原因。当前 Trace 不记录异常正文、外部活动 ID 或私人活动载荷。

## 逻辑工具调用与工具尝试

逻辑工具调用代表 Agent 作出的一次业务调用决策；工具尝试包含这次调用发生的重试。M4 将两者分开计数，避免瞬时错误重试错误地消耗第二次业务决策额度。

## Evaluation Suite

一组版本化、可重复执行的 Agent 场景。M5-A 使用 12 个无私人数据用例覆盖正常任务、故障、护栏和预算，不把几次手工演示当作稳定性证明。

## suite_hash

对规范化评测套件计算的 SHA-256。同一个 hash 表示模型或 Policy 面对的是同一批输入和预期，避免比较不同题集得到的指标。

## Fact Integrity

Agent 成功输出与确定性 Tool 结果是否完全一致。它用于发现 Policy 修改 finding、level、evidence 或目标活动等事实，而不只是检查 JSON 格式正确。

## Guardrail Pass Rate

越权、参数篡改、缺少确认或提前结束场景被正确拦截的比例。除了返回正确错误，还必须验证底层工具没有在拒绝后偷偷执行。

## Loop Engineering

设计 Agent 如何反复执行“观察—行动—验证—修正”，以及何时停止，防止无限循环或错误扩散。

## Context Engineering

决定给 Agent 哪些信息、以什么顺序和粒度提供，以及如何压缩历史同时保留关键事实。

## ADR

Architecture Decision Record，架构决策记录。用于说明做了什么选择、为什么、代价是什么。
