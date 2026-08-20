# M10-A Agent Runtime Tool Governance 阶段记录

## 1. 本阶段目标

把 Review Agent 与 Coach Orchestrator 中分散的工具能力、权限、确认、参数完整性、运行上限和输出 Schema 统一为一套版本化 Runtime 治理契约，同时保持原有 Harness 状态机、失败码与业务写入边界不变。

## 2. 用户与开发者可感知结果

- 当前四个真实 Agent 工具都有可导出的 Tool Manifest；
- 未注册工具、错误角色、访问越权、持久化/审批越权、参数篡改、缺少确认和运行预算超限会在执行前被拒绝；
- 工具输出必须同时匹配 Manifest 声明和 Pydantic Schema；
- Review/Coach Trace 可以回答本次调用经过哪些治理规则、Manifest 是否一致和参数 Hash 是否匹配；
- Trace 不包含真实参数、身体反馈正文、Provider 原始载荷或 Token。

## 3. 新增与修改文件

新增：

- `src/runcrew/domain/runtime_governance.py`
- `src/runcrew/services/runtime_governance.py`
- `scripts/export_runtime_governance_schemas.py`
- `schemas/runtime-governance/` 四份契约/快照
- `tests/test_runtime_governance.py`
- `docs/plans/2026-08-20-m10-agent-runtime-governance.md`
- `docs/adr/0027-versioned-tool-runtime-governance.md`

修改：

- `src/runcrew/harness/review_agent.py`
- `src/runcrew/harness/coach.py`
- Review/Coach 既有测试、架构、状态、路线图、进展、变更日志与求职材料。

## 4. 关键技术策略

1. **Manifest 是静态能力上限**：声明角色、访问、副作用、风险、确认、Schema 和运行上限，不保存运行时凭据或业务数据。
2. **Guardrail 是纯决策**：输入实际/可信参数后比较规范化 Hash，输出规则级 allow/deny/require_confirmation；不直接访问数据库或执行工具。
3. **Harness 仍是执行者**：原状态机、预算、重试、超时和终态不迁移，降低改造风险。
4. **业务不变量不下沉**：目标/计划范围、Recovery→Plan 血缘、计划重放、revision 和正式写入继续由 Harness/Service 校验。
5. **Trace 最小披露**：记录 Manifest Hash、参数是否一致、规则 ID/结果和运行上限数值，不记录参数正文。

## 5. 实施错误与解决方案

### 错误一：模块级导入触发循环依赖

第一版让 `review_agent.py` 在模块加载时导入 `services.runtime_governance`。Python 会先执行 `services/__init__.py`，其中 `ChatService` 又导入 `runcrew.harness`，导致尚未完成初始化的 `ReviewAgentHarness` 被反向读取，测试收集失败。

解决：Review Harness 使用类型检查导入加构造时延迟导入，依赖在模块初始化完成后才解析；Coach 的既有加载顺序保持不变。后续若重构包结构，可把 Runtime 迁入独立顶层包，但 M10-A 不为目录美观扩大改动面。

### 错误二：输出 Guardrail 结果作用域错误

第一版 `_call_node` 内部完成输出校验，但外层 `_run_loop` 直接引用内部局部变量，正常 Coach 场景出现 `NameError`。

解决：让 `_call_node` 明确返回 `(typed_output, ToolOutputGuardrailResult)`，外层在领域范围校验完成后把同一决策写入 `node_output_validated`。专项回归随后全部通过。

## 6. 验收结果

执行：

```powershell
.\.venv\Scripts\python.exe scripts\export_runtime_governance_schemas.py
.\.venv\Scripts\python.exe -m pytest tests\test_runtime_governance.py tests\test_review_agent.py tests\test_coach_harness.py tests\test_deepseek_policy.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

- Runtime Governance 与两套 Harness 联合专项 38 项通过；
- 全量 189 项测试通过；
- 新增8项治理专项测试；
- 既有 Review、Coach 与 DeepSeek Policy 行为保持兼容；
- 本阶段没有读取私人数据库、调用 COROS 或 DeepSeek，也没有产生外部费用。

## 7. 已知边界

- 当前 Manifest 只覆盖四个真实 Agent 工具，不把普通 Service/API 操作冒充为 Agent Tool；
- Trace 尚未统一持久化为跨运行 Run/Span；
- 尚未提供跨运行成功率、拒绝率、重试率和 P95 聚合；
- 当前 Guardrail 安全场景是确定性故障注入，只证明 Runtime 会拒绝，不代表真实 LLM 不会尝试越权。

## 8. 下一阶段唯一入口

M10-B：定义并持久化统一 `RuntimeRun / RuntimeSpan`，先让 Review 与 Coach 的现有 Trace 映射到同一时间线，再增加查询 API。不得先做大盘，也不得让观测写入失败改变业务终态。
