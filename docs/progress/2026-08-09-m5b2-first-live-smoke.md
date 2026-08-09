# M5-B2：第一次 DeepSeek 真实合成 Smoke

- 日期：2026-08-09
- 状态：完成
- 模型：`deepseek-v4-flash`
- 模式：非思考
- 数据：`complete_training_review` 合成用例

## 1. 本阶段目标

使用一个无私人数据的合成用例验证真实 DeepSeek Chat Completions、Tool Calls、Observation 回传、Harness 护栏、Token/费用记录和最终终态。

## 2. 首次真实结果

```text
真实模型请求：2
API 尝试：2
动作解析错误：0
输入 Token：2159
输出 Token：210
思考 Token：0
总 Token：2369
估算费用：0.00036106 USD
模型累计耗时：4133.008 ms
业务工具执行：1
最终状态：budget_exhausted / step_budget_exhausted
```

这次不是网络、鉴权或 Schema 失败。第一次模型 Tool Call 参数合法，训练复盘工具成功执行；第二次模型没有结束，而是再次请求同一工具。Harness 在第二次底层执行前用工具预算将其拦截，因此没有重复执行业务工具，也没有产生不完整业务输出。

## 3. 根因

第一版适配器每一步都发送一个新的 `ReviewAgentContext` JSON。虽然第二步 Context 已包含 Observation，但消息列表没有按 Tool Calls 标准回传：

```text
assistant(tool_calls=[...])
→ tool(tool_call_id=..., content=...)
```

模型因而没有获得标准的“上一轮工具已经执行完成”对话语义，在 `tool_choice=auto` 时再次选择了工具。

## 4. 修复

- Policy 在单次 Run 内保留第一轮 assistant Tool Call；
- 第二轮按标准消息顺序发送 `system → user → assistant(tool_calls) → tool(result)`；
- `tool_call_id` 保持一致；
- Tool Result 只包含已校验 Observation 和剩余预算；
- Policy 新 Run 的 `step=0` 会清空旧对话和旧 Telemetry，防止跨 Run 污染；
- 若从一个已有 Observation、但缺少历史 Tool Call 的异常上下文启动，则使用 `tool_choice=none` 防止重复调用。

## 5. 自动化验证

Mock 完整 Loop 测试现在明确断言第二轮消息角色顺序、Tool Call ID、Tool Result Observation 和剩余工具预算。全量 48 项测试通过。

## 5.1 第二次真实复验

```text
真实模型请求：2
API 尝试：2
动作解析错误：0
输入 Token：2294
  - 缓存命中：1664
  - 缓存未命中：630
输出 Token：255
总 Token：2549
估算费用：0.00016426 USD
模型累计耗时：4663.993 ms
业务工具执行：1
事实一致性：True
最终状态：succeeded / completed
```

第二次真实结果证明标准 assistant/tool 消息链修复有效。Token 总数虽然略高于第一次，但大量输入命中缓存，因此估算费用从 0.00036106 美元下降到 0.00016426 美元。

## 6. 工程价值

- 真实服务暴露了 Mock 仅验证响应格式、没有验证模型对消息语义理解的问题；
- Harness 在模型行为错误时正确阻止了第二次工具执行，证明安全边界没有依赖模型自律；
- API 重试、动作解析错误和业务工具预算能够区分故障来源；
- 失败报告保留了足够的 Token、费用和终态证据，没有保存 Key 或模型正文。

## 7. 下一步唯一入口

M5-B3 使用完整 `review-agent-eval/1.0` 套件运行真实 DeepSeek 对照，统计正常任务、韧性、护栏、预算、Token、费用和延迟，并与确定性 Policy 基线比较。

## 8. 外部额度与私人数据

- 本次估算费用为 0.00036106 美元；
- 第二次成功复验估算费用为 0.00016426 美元；
- 两份报告位于 `data/private/evals/deepseek-smoke-attempt-1.json` 和 `deepseek-smoke-attempt-2-success.json`；
- API Key 未写入文件、Trace 或 Git；
- 输入为版本化合成数据，没有读取真实 COROS 数据库或 FIT。
