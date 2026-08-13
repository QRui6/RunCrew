# M7-C Coach Orchestrator Harness

日期：2026-08-13
状态：完成

## 1. 本阶段目标

把训练执行对照、恢复风险评估和计划调整从三个孤立 Skill 连接为可验证的跨职责工作流，同时保留工具隔离、最小上下文、预算、重试、超时、Trace 和用户确认边界。

## 2. 用户能感知到的结果

用户现在可以运行：

```powershell
.\.venv\Scripts\runcrew.exe coach run `
  --goal-id <目标ID> `
  --plan-id <激活计划ID> `
  --provider coros
```

系统会：

1. 由 Execution Agent 对照本周计划与已同步跑步；
2. 由 Recovery Agent 读取近期训练和当天/前一天身体反馈；
3. 恢复状态正常时直接结束；
4. 需要减量或休息时，把已校验恢复动作交给 Plan Agent；
5. Plan Agent 只生成草案，工作流停在 `awaiting_user_confirmation`；
6. 缺少新鲜反馈或出现红旗时安全阻断，不继续生成训练调整。

输出包括三个节点结果、跨节点 handoff、预算、退出原因和脱敏 Trace。该命令不会保存计划变更，也不会提升计划 revision。

## 3. 新增/修改的文件

- `src/runcrew/domain/coach.py`：运行请求、动作、最小 Policy Context、权限、Handoff、Trace、Budget、Error 和结果 Schema；
- `src/runcrew/harness/coach.py`：确定性 Orchestrator Policy、三个职责节点、有限 Loop 和故障边界；
- `src/runcrew/cli.py`：新增 `coach run`；
- `src/runcrew/domain/training_execution.py`：执行结果补充 `goal_id`，用于阻断跨目标输出；
- `src/runcrew/services/training_execution.py`：从计划写入执行结果的目标血缘；
- `schemas/coach-orchestrator/`：输入输出 JSON Schema；
- `scripts/export_coach_orchestrator_schemas.py`：Schema 导出；
- `tests/test_coach_harness.py`：正常、阻断、越权、篡改、重试、超时、Schema 和真实数据库 CLI 测试；
- `docs/adr/0017-coach-orchestrator-handoff-boundary.md`：编排边界决策。

## 4. 关键技术决策

### Orchestrator 不是超级 Agent

Policy 只看到完成状态、恢复路由、剩余预算和下一节点的类型化请求，不看到活动详情、身体量表、evidence 正文或数据库对象。它只输出 `delegate_execution / delegate_recovery / delegate_plan / finish`。

### 三个职责节点拥有不同权限

- Execution Agent：只读 `compare_training_execution`；
- Recovery Agent：只读 `assess_running_recovery`；
- Plan Agent：仅 `prepare_change`，不能 persist 或 approve。

Harness 同时校验节点、工具和权限级别。参数不是由 Harness 生成的预期请求时，在底层工具执行前拒绝。

### 类型化交接与证据血缘

Execution 输出必须同时匹配运行的 `goal_id` 和 `plan_id`；Plan 输出必须引用同一个 Recovery `input_hash`、recommendation 和 `plan_action`。Handoff 只记录传递字段名与请求哈希，既可审计又不把私有数据复制到 Trace。

### Human-in-the-loop 是终态

减量/休息草案产生后不是 `succeeded`，而是 `awaiting_user_confirmation`。Trace 明确记录 `persisted=false`、`approved=false`。缺反馈和红旗分别返回 `provide_fresh_check_in` 与 `seek_professional_review`。

## 5. 验收命令与结果

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
```

结果：`117 passed`，项目统一验证通过。

10 项新增测试覆盖：

- 正常恢复只走 Execution → Recovery；
- 中等风险走 Execution → Recovery → Plan，并等待用户确认；
- 数据不足和专业升级安全阻断；
- Policy 只接收最小上下文；
- 参数篡改在工具调用前拒绝；
- 权限错误和跨目标输出 fail closed；
- 瞬时失败有限重试、节点调用预算和超时；
- 非法节点输出 Schema 拒绝；
- 相同运行输入生成相同 workflow hash；
- CLI 使用真实 SQLite Service，运行后数据库没有 pending proposal，plan revision 保持不变。

## 6. 实施中的错误与解决方案

1. 给 `TrainingExecutionResult` 增加 `goal_id` 后，旧导出 Schema 漂移测试失败。原因是代码契约更新但版本库中的 JSON Schema 未同步；运行导出脚本并保留漂移测试后解决。
2. 新测试最初使用字母 `r` 模拟 SHA-256。Schema 正确拒绝，因为哈希只允许十六进制字符；测试改用合法字符。这证明 Schema 没有为测试夹具放宽。
3. CLI 集成夹具的 `raw_payload_hash` 过短，被 Domain 最小长度约束拒绝；修复夹具而不是绕过领域校验。

## 7. 已知问题

- 默认路由 Policy 是确定性的，还没有接入 DeepSeek 进行多工具决策；
- Coach 结果尚未进入聊天产品；
- 计划草案只返回，尚未提供从 Coach 输出一键创建 pending proposal 的交互；
- 跨节点 Trace 随 CLI JSON 返回，尚未持久化；
- 当前只有测试级故障覆盖，尚未形成版本化多 Agent Evaluation Suite。

## 8. 下一阶段唯一入口

**M7-D：把目标、身体反馈、计划状态和 Coach 运行接入连续对话产品，并让用户能够在界面中审核而非自动应用计划调整。**

## 9. 数据与外部额度

本阶段实现和测试只使用本地合成数据，没有读取用户真实活动，没有调用 COROS 或 DeepSeek，也没有产生外部费用。
