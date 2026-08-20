# ADR-0028：以 best-effort 独立事务持久化统一 Runtime Run/Span

## 状态

接受

## 背景

M10-A 已让 Review 与 Coach 共用 Tool Manifest 和 Guardrail，但两套 Trace 仍分别附着在运行结果中。聊天只保存首轮 Review Trace 快照，Coach 另存完整业务审核 JSON，无法用同一契约查询一次运行的 Policy、Guardrail、Handoff、工具尝试、重试和校验时间线。观测属于辅助能力，不能因为 SQLite 锁、表缺失或序列化失败改变训练结论。

## 决策

1. 新增 `RuntimeRun / RuntimeSpan / RuntimeRunCapture` 版本化领域契约，统一 Review 与 Coach 的工作流、终态、预算、耗时、调用/重试计数、父子时间线与 Trace Hash。
2. 使用 `agent_runtime_runs` 和 `agent_runtime_spans` 两张 SQLite 表；Run 保存索引字段与规范 JSON，Span 保存父子关系、偏移/持续时间、工具/节点和白名单 attributes。
3. 原 Trace 映射为一个根 Run Span 加内部事件 Span；工具/节点开始事件计算到对应成功/失败事件的持续时间，其余事件保留为零时长时间点。
4. 产品业务关联只保存 `scope_ref_hash`。Prompt、模型响应、用户消息、工具参数、活动/目标/计划 ID、身体反馈和 Provider 数据不进入 Runtime 表。
5. 相同 `run_id + trace_hash` 重复写入幂等；相同 run_id 的不同 Trace 拒绝覆盖。
6. `RuntimeTraceService` 使用独立短事务 best-effort 写入并吞掉异常正文，只返回错误类型；观测失败不得改变 Review/Coach 返回值或业务审计状态。
7. Runtime 记录默认保留30天，在下一次写入时清理过期 Run/Span；查询也过滤过期记录。
8. M10-B 只接入聊天首轮 Review 和训练运营 Coach 两条产品路径。离线 Evaluation 不写产品 Runtime 表，避免测试运行污染观测数据。
9. 暴露只读 `GET /api/runtime/runs` 与 `GET /api/runtime/runs/{run_id}`；指标聚合和可视化留给 M10-C。

## 原因

- 统一契约使两个 Harness 可以复用查询、保留和后续指标逻辑；
- 独立事务把观测可用性与训练业务正确性隔离；
- Hash 关联足以做本机排障，不需要复制业务主键和私人上下文；
- 先持久化可回放事实，再做聚合大盘，避免只展示无法核对的数字。

## 后果

- 产品真实 Review/Coach 运行可以查询统一父子时间线；
- CLI 与 Evaluation 默认不持久化，当前 Runtime 数据量不代表系统所有运行；
- best-effort 失败不会阻塞业务，但当前也不会主动告警，只能从返回 outcome 或后续 M10-C 指标发现；
- SQLite `DateTime(timezone=True)` 读回可能丢失 tzinfo，单条过期判断必须使用规范 JSON 恢复的 aware datetime，数据库时间列只用于索引/批量清理；
- 当前没有分布式 Trace、OpenTelemetry exporter、跨进程传播或生产级保留策略。

## 替代方案

### 直接把两套 Trace JSON 复制到一张表

无法统一查询字段、父子关系和保留策略，拒绝。

### 在 Harness 内直接依赖 SQLAlchemy

会破坏 Harness 与存储边界，也让评测和 CLI 被动写库，拒绝。

### 观测写入失败时让 Agent Run 失败

会让辅助能力覆盖训练业务终态，拒绝。

### 立即接入外部 Trace SaaS 或 OpenTelemetry Collector

当前本地优先产品没有部署与外部数据传输需求，会扩大隐私和运维范围，拒绝。
