# ADR-0027：用版本化 Tool Manifest 统一 Agent Runtime 治理

## 状态

接受

## 背景

Review Agent 与 Coach Orchestrator 已分别实现工具白名单、职责权限、人工确认、参数或 Handoff 完整性、输出 Schema、超时、重试、预算和脱敏 Trace。但相同安全语义分散在两套 Harness 中，工具的责任角色、访问级别、副作用、风险、输入输出契约和运行上限也没有统一事实来源。继续复制判断会让新增工具容易漏接确认、权限或输出校验。

## 决策

1. 为当前真实存在的四个 Agent 工具建立 `tool-manifest/1.0`，声明责任角色、输入/输出 Schema、访问级别、副作用、风险、确认要求、持久化/审批能力、幂等性、超时/重试上限和敏感字段名。
2. 使用只读 `ToolCapabilityRegistry` 管理 Manifest；重复名称在启动时失败，未注册工具在执行前拒绝。
3. 使用统一 `RuntimeGuardrailEngine` 检查注册、角色、访问级别、能力上限、确认、参数 Hash 和运行上限，并返回版本化 `GuardrailDecision`；Trace 只保存 Manifest Hash、参数是否匹配、规则 ID 和结果，不保存参数正文。
4. Review 与 Coach Harness 继续拥有状态机、预算、超时、重试和终态；治理引擎不直接运行工具，也不掌握数据库或 Provider。
5. 工具返回后由同一引擎核对 Manifest 声明的输出模型并运行 Pydantic 校验；领域范围和血缘检查仍由 Harness/Service 执行。
6. `adjust_running_plan` 被声明为 `prepare_change + state_proposal`，`can_persist=false`、`can_approve=false`。正式计划写入仍只经过用户确认、服务端重放、Hash 与 revision 校验，不注册虚构的“Agent 写入工具”。

## 原因

- 一份 Manifest 同时服务权限检查、Trace、Schema 导出和后续运行指标，减少规则漂移；
- Guardrail 返回结构化决策，而不是只抛字符串，便于故障注入和未来 Run/Span 聚合；
- 参数只比较规范化 SHA-256，可证明完整性又不把活动 ID、身体反馈或证据正文复制进 Trace；
- 保留 Harness 与领域服务边界，避免通用框架误替代训练计划的业务一致性规则。

## 后果

- 四个工具使用同一套前置与后置治理规则，原有失败码、确认中断和 Handoff 语义保持兼容；
- Review/Coach Trace 的事件类型不变，但权限和输出事件增加同构治理元数据；
- 当前 Trace 仍主要随单次结果或聊天证据快照存在，尚未形成持久化跨运行 Run/Span；
- 新增 Agent 工具必须先注册 Manifest，并为越权、篡改、超限与非法输出补测试；
- `services.runtime_governance` 在 Review Harness 中采用延迟导入，以避免现有 `services/__init__.py` 聚合入口反向加载 Harness 的循环依赖。

## 替代方案

### 继续在每个 Harness 内写独立权限判断

短期改动少，但第三、第四套 Harness 会继续复制安全规则，拒绝。

### 立即替换成完整第三方 Agent Runtime

会同时改变状态机、Trace、重试和业务确认边界，迁移风险大且当前没有证据证明必要，拒绝。

### 增加审核 Agent 判断能否调用工具

把确定性权限问题交给概率模型，无法提供更强保证，也增加成本和失败点，拒绝。

### 让通用治理层负责正式计划写入

无法表达服务端重放、revision 与训练领域不变量，拒绝；治理层只限制能力，正式写入继续属于业务 Service。
