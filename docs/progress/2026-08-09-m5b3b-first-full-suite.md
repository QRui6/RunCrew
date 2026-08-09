# M5-B3b 两次完整运行与公平预算修复

## 1. 本阶段目标

运行完整 DeepSeek 合成评测，与确定性 Policy 在相同版本化 Suite 上比较任务完成、护栏、事实、费用和延迟。

## 2. 第一次运行结果

```text
场景：12/12 满足预期
正常任务完成率：1.0
护栏通过率：1.0
Schema 通过率：1.0
事实一致率：1.0
越权工具执行：0
模型 API 请求：12
动作解析错误：0
总 Token：12897
估算费用：0.00061916 美元
Policy 累计耗时：23581.19 ms
P95 单场景耗时：4422.692 ms
```

9 个场景实际使用 DeepSeek Policy；`unknown_tool_blocked`、`tampered_arguments_blocked` 和 `premature_finish_blocked` 使用脚本化 Policy 注入非法动作，只验证 Harness 最后防线。

## 3. 发现的问题

确定性基线的 Suite Hash 为：

```text
f3dc7dd964da5773c3a3fda5a717e41c4b8c02b06131959b3a708e88a74dd4f8
```

第一次真实报告的 Hash 为：

```text
783517e25bcfa77b2cbddee9249c8481d9deeecc2a02944382468a88c3f63636
```

原因是 `deepseek-suite` 命令把 v1.0 默认的 `run_timeout_seconds` 从1秒改成了60秒。虽然所有真实场景实际都在约4.5秒内完成，但输入已经不是完全相同的 Suite，所以本次报告不能冒充严格同题对照。

## 4. 修复策略

- 保留第一次报告为 `data/private/evals/deepseek-suite-attempt-1-timeout-adjusted.json`；
- 删除 CLI 对场景超时的隐式改写，原样传入加载的版本化 Suite；
- 增加 CLI 回归测试，断言交给评测器的 Suite 与源文件完全一致；
- 增加 CLI Suite 不变性测试。

## 4.1 第二次严格复跑

第二次报告与 v1.0 确定性基线 Hash 完全相同，但结果为3/12：3个脚本化 Policy 场景通过，9个真实 DeepSeek 场景全部在约1秒时返回 `run_timeout`。报告没有收到任何 API usage，因此本地 Token 和估算费用均为0；这不能证明供应商账户一定没有计费。

该结果证明失败来自 Suite v1.0 为离线快速回归设置的1秒总预算，而不是9次独立的模型动作错误。报告保存为 `data/private/evals/deepseek-suite-attempt-2-one-second-timeout.json`。

## 4.2 最终修复

- Suite 升级到 `review-agent-eval/1.1`；
- 确定性 Policy 与 DeepSeek 统一使用15秒总运行预算；
- 时间预算继续进入 Suite Hash，不为模型创建隐藏特例；
- v1.1 确定性基线 12/12 通过，Hash 为 `2b89473f6f9e02f06960965bfafdac74aacff1b28ead42eeade0e7a5afd199e9`；
- 总超时取消模型请求时记录已发起 API 尝试和失败遥测，未知 usage 不伪造为已知成本；
- 全量验证增至52 passed。

## 5. 本阶段文件

- `src/runcrew/cli.py`：删除 60 秒超时改写；
- `src/runcrew/domain/evaluation.py`：Suite 升级至 v1.1，并把统一总预算设为15秒；
- `src/runcrew/harness/review_agent.py`：总超时结果接收被取消 Policy 的白名单遥测；
- `src/runcrew/policies/deepseek.py`：取消请求时记录 API 尝试，不伪造 usage；
- `evals/review_agent/cases.json` 与两个导出 Schema：同步 v1.1；
- `tests/test_agent_evaluation.py`：增加 Suite 不变性测试；
- `tests/test_deepseek_policy.py`：增加被总超时取消的模型请求遥测测试；
- `docs/adr/0010-shared-evaluation-time-budget.md`：记录统一时间预算决策；
- `docs/CURRENT_STATE.md`、`docs/ROADMAP.md`、`CHANGELOG.md`：记录第一次结果、缺陷和修复；
- 本文件：保留评测审计过程。

## 6. 下一阶段唯一入口

再次运行 v1.1 `deepseek-suite` 命令，并确认新报告 Hash 为 `2b89473f...`。随后才能形成正式的确定性 Policy / DeepSeek 对照结论。

## 7. 数据与额度

第一次运行只发送合成数据，估算费用 0.00061916 美元。第二次报告因请求在 usage 返回前被取消而显示0美元，真实账户是否计费仍以供应商账单为准。最终复跑预计产生与第一次相近的费用，并继续受0.01美元共享上限保护。
