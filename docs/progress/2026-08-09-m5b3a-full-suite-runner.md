# M5-B3a 完整评测运行器与共享费用门

## 1. 本阶段目标

在不自动产生模型费用的前提下，为完整 `review-agent-eval/1.0` 套件提供真实 DeepSeek 运行入口，并避免把每个用例的费用上限误当成整套评测总上限。

## 2. 用户能感知到的结果

新增命令：

```powershell
.\.venv\Scripts\runcrew.exe eval deepseek-suite `
  --confirm-paid-api `
  --max-total-estimated-cost-usd 0.01 `
  --output data\private\evals\deepseek-suite.json
```

缺少明确付费确认、共享总费用上限或 API Key 时，命令会在联网前退出。报告只允许写入 `data/private/`。

## 3. 新增/修改的文件

- `src/runcrew/cli.py`：增加完整 Suite 命令；
- `src/runcrew/policies/deepseek.py`：增加可跨 Policy 实例共享的 `DeepSeekCostBudget`；
- `src/runcrew/policies/__init__.py`：导出共享费用对象；
- `tests/test_agent_evaluation.py`：验证 CLI 付费确认与总费用参数；
- `tests/test_deepseek_policy.py`：验证跨用例费用累计、越界遥测和后续请求前停止；
- 当前状态、路线图、模型方案和面试说明同步更新。

## 4. 关键技术决策

- 12 个场景仍复用同一版本化 Suite，不另造一套“模型专用题”；
- 每个默认 Policy 场景创建独立 Policy，避免对话状态串场；
- 所有 Policy 共享同一个费用对象，费用不会随新用例重置；
- 费用是根据 API 返回 usage 后验估算，越界响应仍会产生实际费用，但后续请求会被阻止；
- 脚本化故障和护栏场景继续由原有 Policy 注入，用来评估 Harness，不消耗模型费用。

## 5. 验收结果

```text
pytest：50 passed
deepseek-suite --help：成功
真实 DeepSeek API 调用：0
```

## 6. 已知问题

- 本地费用门不是供应商账单硬上限，无法阻止第一笔请求或越界的最后一笔响应；
- 完整 Suite 尚未真实运行，因此还没有 DeepSeek 与确定性 Policy 的质量对照结论；
- 当前 Suite 中部分护栏是脚本化故障注入，不能被误解为模型安全评分。

## 7. 下一阶段唯一入口

由用户在已设置 `DEEPSEEK_API_KEY` 的同一 PowerShell 中运行 `deepseek-suite`，随后解析私有报告，与确定性基线对照并决定是否需要调整 Prompt、上下文或模型。

## 8. 数据与额度

本阶段只运行 Mock 和本地测试，没有调用真实 API，也没有发送真实跑步数据。下一阶段命令只使用仓库内的合成评测数据，但会消耗少量 DeepSeek 额度。
