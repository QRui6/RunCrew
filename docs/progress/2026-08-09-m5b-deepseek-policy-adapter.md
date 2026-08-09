# M5-B1：DeepSeek Policy 适配器与 Mock 契约

- 日期：2026-08-09
- 状态：完成
- 分支：`feat/m5-agent-evaluation-baseline`
- Pull Request：GitHub PR #4，base 为 `main`
- 外部调用：无

## 1. 本阶段目标

在不配置 API Key、不产生费用、不上传真实跑步数据的前提下，实现 DeepSeek Policy 的代码边界，并用 Mock 响应验证请求契约、动作解析、Harness 护栏、脱敏和评测指标。

## 2. 用户能感知到的结果

项目现在已有真实 LLM 的可替换适配器代码，而不再只是一个接口设想。适配器能够：

- 将 `ReviewAgentContext` 转成 DeepSeek Chat Completions 请求；
- 固定使用非思考模式和一个 `review_running_training` Tool；
- 把 Tool Call 转成现有 `ToolCallAction`；
- 把无 Tool Call 的正常结束转成 `FinishAction`；
- 对网络错误、429/5xx、非法 JSON、截断和资源不足做有限重试；
- 把模型名、Token、耗时、尝试数和解析错误写入脱敏 Trace/评测指标；
- 按固定价格版本估算费用，并在超过本地 Policy 上限时停止后续动作；
- 提供只运行一个合成用例且要求显式付费确认的 Smoke 命令；
- 继续由 Harness 拦截未知工具、参数篡改、缺少确认和预算越界。

## 3. 主要文件

| 文件 | 作用 |
|---|---|
| `src/runcrew/policies/deepseek.py` | 配置、HTTP Transport、请求构造、响应解析、有限重试和调用元数据 |
| `src/runcrew/policies/__init__.py` | Policy 公共导出 |
| `src/runcrew/harness/review_agent.py` | 只把白名单 Policy 元数据接入现有 Trace |
| `src/runcrew/domain/evaluation.py` | 通用 Policy Token/解析/耗时指标，报告版本升级为 1.1 |
| `src/runcrew/evaluation/review_agent.py` | 从可观测 Policy 聚合模型调用指标 |
| `tests/test_deepseek_policy.py` | 零费用 Mock 契约、安全和评测聚合测试 |
| `evals/review_agent/report.schema.json` | 更新后的 1.1 评测报告 Schema |

## 4. 关键技术决策

- Policy 只做动作选择，不执行工具；
- 只允许 DeepSeek 官方 HTTPS 主机，降低 Key 被错误 Base URL 带走的风险；
- `SecretStr` 避免配置对象打印出 Key；
- 普通 Tool Calls 之后仍进行本地 Pydantic 校验；
- 模型 API 重试和业务工具重试分别计数；
- Mock Transport 复现官方响应结构，不引入真实网络；
- Trace 采用固定白名单，不接收 Prompt、模型正文或工具参数；
- 确定性 Policy 在新增模型指标中保持全部为零，不破坏 M5-A 基线。

## 5. 验收结果

```text
专项测试：22 passed
全量测试：48 passed
统一自检：Project verification passed
真实 DeepSeek 请求：0
真实 COROS/FIT 读取：0
```

新增 9 项 DeepSeek 相关测试，覆盖完整两步 Agent Loop、请求字段、非法 JSON 后重试、参数篡改拦截、失败脱敏、官方 HTTPS Transport、环境配置失败关闭、评测 Token/费用聚合、费用停止门和 Smoke CLI 前置条件。

## 6. 已知限制

- 尚未使用真实 `deepseek-v4-flash` 响应验证兼容性；
- 尚未把 DeepSeek 接入普通 `agent review` CLI；
- 尚无真实 Token、延迟和费用数据；
- 费用按 2026-08-09 官方单价估算，尚无真实 usage 可以验证；
- 本地费用门是收到 usage 后的后验停止门，不能阻止第一笔请求；
- 12 场景真实模型对照尚未运行；
- Mock 只能证明本地适配器行为，不能证明模型质量或服务稳定性。

## 7. 下一阶段唯一入口

M5-B2 由用户在本机设置 `DEEPSEEK_API_KEY`，确认付费外部调用和费用上限后执行已经实现的单用例 Smoke 命令。单次 Smoke 成功后，才允许运行完整 12 场景模型评测。

## 8. 外部额度与私人数据

- 本阶段没有调用 DeepSeek、COROS 或 FIT；
- API Key 当前不存在于项目环境，也没有写入任何文件；
- Mock 上下文只包含合成活动；
- Git 变更不含真实活动、外部 ID、坐标或模型响应正文。
