# M5-B3b 第一次完整运行与 Hash 漂移修复

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

原因是 `deepseek-suite` 命令把默认场景的 `run_timeout_seconds` 从 15 秒改成了 60 秒。虽然所有真实场景实际都在约 4.5 秒内完成，但输入已经不是完全相同的 Suite，所以本次报告不能冒充严格同题对照。

## 4. 修复策略

- 保留第一次报告为 `data/private/evals/deepseek-suite-attempt-1-timeout-adjusted.json`；
- 删除 CLI 对场景超时的隐式改写，原样传入加载的版本化 Suite；
- 增加 CLI 回归测试，断言交给评测器的 Suite 与源文件完全一致；
- 全量验证增至 51 passed。

## 5. 本阶段文件

- `src/runcrew/cli.py`：删除 60 秒超时改写；
- `tests/test_agent_evaluation.py`：增加 Suite 不变性测试；
- `docs/CURRENT_STATE.md`、`docs/ROADMAP.md`、`CHANGELOG.md`：记录第一次结果、缺陷和修复；
- 本文件：保留评测审计过程。

## 6. 下一阶段唯一入口

再次运行相同 `deepseek-suite` 命令，并确认新报告 Hash 与确定性基线相同。随后才能形成正式的确定性 Policy / DeepSeek 对照结论。

## 7. 数据与额度

第一次运行只发送合成数据，估算费用 0.00061916 美元。修复过程没有调用 API；复跑预计产生相近费用，并继续受 0.01 美元共享上限保护。
