# M5-A：单 Agent 离线评测基线

- 日期：2026-08-09
- 状态：完成
- 分支：`feat/m5-agent-evaluation-baseline`
- 基线：M3 PR #2 与 M4 PR #3 已依次合并到 `main`
- Pull Request：GitHub PR #4，base 为 `main`

## 1. 本阶段目标

在接入真实 LLM 以前，为 M4 Agent Harness 建立可回放、可聚合、无私人数据的离线评测基线。M5-A 不增加业务 Agent、不调用 COROS，也不消耗模型费用。

## 2. 用户能感知到的结果

用户可以运行：

```powershell
runcrew eval review-agent `
  --output data/private/evals/m5-baseline.json
```

系统执行 12 个固定场景，输出逐用例结果、聚合指标、套件哈希和是否满足基线。报告只能保存到 `data/private/`，避免未来真实模型评测意外进入 Git。

## 3. 评测场景

| 类别 | 场景 |
|---|---|
| 正常任务 | 完整数据、缺数安全降级、瞬时错误后恢复 |
| 韧性 | 持续超时、非法工具输出、永久工具失败 |
| 护栏 | 未知工具、参数篡改、缺少确认、提前结束 |
| 预算 | 步骤预算耗尽、工具预算为零 |

## 4. 指标定义

- `expectation_pass_rate`：全部场景是否得到预期终态；
- `task_completion_rate`：正常任务是否成功产生合法输出；
- `guardrail_pass_rate`：越权或非法动作是否在工具执行前被拦截；
- `schema_valid_rate`：Run Result 是否可再次通过 Schema 校验；
- `fact_integrity_rate`：成功输出是否与确定性工具结果完全一致；
- `prohibited_tool_execution_count`：护栏拒绝后工具仍执行的次数；
- `average_tool_calls / attempts`：逻辑调用和重试成本；
- `p95_latency_ms`：本机离线耗时观察值；
- `termination_reason_counts`：退出原因分布。

当前硬门槛是不含延迟的所有正确性指标达到 100%，且越权后工具执行数为 0。

## 5. 主要文件

| 文件 | 作用 |
|---|---|
| `evals/review_agent/cases.json` | 12 个版本化评测场景 |
| `evals/review_agent/*.schema.json` | 套件和报告 JSON Schema |
| `src/runcrew/domain/evaluation.py` | Case、Suite、Metrics、Report 模型 |
| `src/runcrew/evaluation/review_agent.py` | 场景构建、故障注入、判分和聚合 |
| `scripts/export_evaluation_schemas.py` | 从 Pydantic 导出 Schema |
| `tests/test_agent_evaluation.py` | 套件、指标、退化检测、Schema 和 CLI 测试 |

## 6. 实施策略与亮点

- 把任务成功率和故障安全性分开统计，故障用例按预期失败不算系统退化；
- 用套件 SHA-256 标识评测输入，后续模型结果可以确认是否基于同一套问题；
- 成功输出与确定性 Skill 结果做对象级比较，防止 Policy 修改 finding、level 或 evidence；
- 记录护栏之后底层工具是否真的执行，而不只检查返回了什么错误；
- 评测 Policy 使用可替换工厂，M5-B 接入真实 LLM 时不需要重写评测器；
- 报告路径默认收紧到 `data/private/`。

## 7. 验收结果

```text
total_cases=12
passed_cases=12
failed_cases=0
meets_baseline=true
expectation_pass_rate=1.0
task_completion_rate=1.0
guardrail_pass_rate=1.0
schema_valid_rate=1.0
fact_integrity_rate=1.0
prohibited_tool_execution_count=0
average_tool_calls=0.5833
average_tool_attempts=0.75
```

自动化测试总数增至 39 项，其中 M5-A 专项测试 5 项。

## 8. 已知限制

- 当前仍是确定性 Policy 和脚本化故障，不代表真实模型能力；
- 还没有模型 ID、Token、费用和动作解析错误指标；
- P95 延迟受本机调度影响，当前不作为硬门槛；
- 评测场景是合成数据，尚未建立经过脱敏的历史真实回放集；
- 尚无多 Agent，且本阶段没有提供拆分证据。

## 9. 下一阶段唯一入口

M5-B 只接入一个真实 LLM Policy。模型必须读取同一 `ReviewAgentContext`、输出同一 `call_tool / finish` Action Schema，并在相同 12 个场景上与确定性基线比较。接入前需要确定模型供应商、模型名和费用上限。

## 10. 外部额度与私人数据

- 没有调用 COROS 或真实 FIT；
- 没有调用 LLM API；
- 套件只包含合成活动；
- 生成报告位于 Git 忽略的 `data/private/evals/`。
