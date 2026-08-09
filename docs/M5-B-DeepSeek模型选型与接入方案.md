# M5-B：DeepSeek 模型选型与接入方案

> 状态：M5-B1 与 M5-B2 已完成；第一次完整运行 12/12 满足预期，但严格同 Hash 对照待修复后复跑。
> 最后核对官方文档：2026-08-09。模型能力、名称和价格可能变化，正式调用前必须再次核对。

## 1. 结论

DeepSeek **满足 RunCrew M5-B 的功能要求**。第一版推荐：

```text
模型：deepseek-v4-flash
模式：非思考模式
接口：Chat Completions + 原生 Tool Calls
输出约束：普通 Tool Calls + 本地 Pydantic 二次校验
运行边界：只替换 Policy，不接管 Harness、工具、规则计算和事实判断
数据边界：先只运行合成评测数据，不上传真实 COROS/FIT 数据
```

不建议第一版使用 `deepseek-v4-pro`、思考模式或 Beta Strict Mode。原因不是这些能力不可用，而是当前 Agent 只有 `call_tool` 和 `finish` 两种动作、一个只读工具；Flash 更便宜、更快，非思考模式也避免多轮工具调用时维护 `reasoning_content`。先用最小方案建立真实模型基线，若评测证明能力不足，再升级模型。

## 2. RunCrew 对 LLM 的真实要求

LLM 在本项目中不是跑步数据计算器，只负责从受控上下文中选择下一步动作：

```text
ReviewAgentContext
        ↓
DeepSeekReviewPolicy
        ↓
call_tool / finish
        ↓
现有 AGENT_ACTION_ADAPTER 校验
        ↓
现有 ReviewAgentHarness 执行权限、确认、预算、重试和超时
```

因此模型需要具备：

- 接收结构化上下文；
- 原生工具调用或稳定结构化输出；
- 返回工具名称和 JSON 参数；
- 多轮接收工具观察结果；
- 提供 Token 用量，便于统计费用；
- 能被超时、重试和预算机制包裹。

DeepSeek 当前公开能力可以覆盖以上要求。

## 3. 为什么选 deepseek-v4-flash

| 方案 | 是否首选 | 原因 |
|---|---:|---|
| `deepseek-v4-flash` 非思考模式 | 是 | 足够完成简单 Agent 动作选择，速度和费用更适合反复评测 |
| `deepseek-v4-flash` 思考模式 | 暂不使用 | 工具调用时需要在后续请求中正确回传 `reasoning_content`，增加上下文和状态管理复杂度 |
| `deepseek-v4-pro` | 暂不使用 | 当前任务复杂度不足以证明更高费用的必要性；若 Flash 评测不达标再对照 |
| JSON Output | 备用 | 可保证 JSON 形式，但原生 Tool Calls 更贴合当前动作协议；仍需处理空内容和截断 |
| Beta Strict Mode | 暂不使用 | 支持的 JSON Schema 是子集，例如对象字段要求全部 required，部分长度约束不支持；当前 Pydantic Schema 不能直接照搬 |

不要再使用旧名称 `deepseek-chat` 或 `deepseek-reasoner`。官方已在 2026-07-24 停止这两个模型入口，应显式配置 `deepseek-v4-flash` 或 `deepseek-v4-pro`。

## 4. DeepSeek 能做什么，不能替代什么

### 可以交给模型

- 根据上下文判断当前应调用训练复盘工具还是结束；
- 生成符合协议的工具调用意图；
- 在已有 Observation 后决定结束；
- 后续在已验证事实之上生成自然语言说明。

### 不能交给模型

- 解析 FIT 二进制、CRC 或 COROS 原始字段；
- 计算距离、配速、负荷、阈值和 confidence；
- 决定自己是否有工具权限；
- 绕过确认、预算、超时和参数一致性校验；
- 编造工具没有返回的跑步事实；
- 直接获得真实用户隐私数据作为第一轮测试输入。

DeepSeek 官方也明确提示：模型生成的工具参数可能无效或产生幻觉。因此所有参数都必须继续经过现有 Pydantic Schema 与 Harness 校验，绝不能收到 Tool Call 后直接执行。

## 5. 实施方案

### 5.1 配置

只通过环境变量读取配置，不把 Key 写入 `.env` 示例值、代码、文档、Trace 或 Git：

```text
DEEPSEEK_API_KEY=<仅保存在本机环境中>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

第一版直接复用项目现有 `httpx`，不必为了单一请求额外引入 SDK。

### 5.2 Policy 适配器

新增 `DeepSeekReviewPolicy`，实现已经存在的 `ReviewAgentPolicy` 协议：

1. 只从 `ReviewAgentContext` 选择允许暴露的字段；
2. 构造固定 System Instruction 和一个 `review_running_training` 工具定义；
3. 禁用思考模式；
4. 将返回的 Tool Call 转成 `ToolCallAction`；
5. 已有合法 Observation 且模型不再调用工具时，转成 `FinishAction`；
6. 交给 `AGENT_ACTION_ADAPTER` 和 Harness 再次校验；
7. 把模型名、请求时延、Token 和解析结果写入脱敏 Trace/评测指标。

Policy 不直接执行工具，也不复制 Harness 的权限逻辑。

### 5.3 失败处理

可以重试：

- 网络超时；
- HTTP 429；
- HTTP 5xx；
- 服务端资源不足；
- 空响应或一次性不可解析输出。

不能通过重试绕过：

- 未知工具；
- 参数篡改；
- 缺少用户确认；
- 步骤或 Token/费用预算耗尽。

### 5.4 评测顺序

1. [已完成] 增加完全 Mock 的适配器契约测试，不产生费用；
2. [已完成] 用一条最小合成上下文做一次真实 API Smoke Test；
3. [第一次运行通过，待同 Hash 复跑] 在现有 12 个合成场景上运行真实模型；
4. 记录完成率、动作解析错误、Token、费用、延迟和退出原因；
5. 与确定性 Policy 基线比较；
6. 只有 Flash 未达到验收线时，再用 Pro 跑同一 Suite；
7. 只有单 Agent 的职责或上下文问题有评测证据时，再考虑多 Agent。

## 6. M5-B 验收标准

- `DeepSeekReviewPolicy` 不修改现有 Harness 和工具安全边界；
- API Key 不进入 Git、日志、错误信息和评测报告；
- Tool Call 必须通过本地 Schema、白名单、确认门和参数一致性校验；
- 合成评测报告记录模型全名、模式、Token、估算费用、API 延迟和动作解析错误；
- 真实 LLM 结果与同一 `suite_hash` 的确定性基线可以比较；
- 非法模型动作不会触发底层工具；
- 没有真实跑步数据发送给模型；
- 成本上限和最大输出 Token 有显式配置；
- 若真实服务不可用，离线 51 项测试仍可独立通过。

## 6.1 M5-B1 已实现结果

- `DeepSeekReviewPolicy` 与 `HttpxDeepSeekTransport`；
- 环境变量配置、`SecretStr` 和官方 HTTPS 主机限制；
- 非思考模式、普通 Tool Calls 和本地 Action 校验；
- 网络、429/5xx、非法 JSON、输出截断和资源不足的有限重试；
- 模型元数据进入白名单 Trace；
- Evaluation Report 1.1 的模型调用、API 尝试、动作解析错误、Token 和模型耗时指标；
- 带 `deepseek-pricing/2026-08-09` 版本的费用估算和本地停止门；
- 只运行一个合成场景、且要求显式付费确认和费用上限的 `runcrew eval deepseek-smoke`；
- 单用例 Smoke 与完整 Suite 都要求显式付费确认；完整 Suite 使用跨 Policy 实例共享的总费用门；
- 全量 51 项零费用测试通过。

## 6.2 M5-B3 第一次完整运行

第一次完整运行得到 12/12 满足预期，3 个正常任务均成功，事实一致性、Schema 和护栏指标均为 100%。9 个场景使用真实 DeepSeek Policy，另外 3 个场景继续使用脚本化非法动作来验证 Harness。模型共请求 12 次，使用 12897 Token，估算费用 0.00061916 美元，动作解析错误为 0。

复核时发现完整命令为了容纳外部延迟，把默认场景的总超时从题集中的 15 秒改成了 60 秒。这使真实报告的 `suite_hash` 与确定性基线不同，无法满足“相同输入严格比较”的验收要求。该报告保留为功能证据；代码已改为原样传入版本化 Suite，并用测试防止再次发生隐式改题。正式结论必须以修复后的同 Hash 复跑为准。

这些结果与成功单用例 Smoke 共同证明接入链路可用，但不能替代完整 Suite 的模型质量评测。

本地费用上限根据 API 返回的 usage 后验计算：它可以阻止同一 Policy 的后续动作，但第一笔请求已经发生，因此不能当作供应商账单硬上限。正式调用仍应使用低余额账户并先核对官方价格。

## 7. 当前评测基线的一个限制

现有 12 个场景中，越权、参数篡改和提前结束等场景由脚本化 Policy 主动注入，用来证明 Harness 安全，而不是证明 LLM 一定不会产生这些动作。M5-B 接入后仍需增加少量“真实模型动作选择”用例，例如提示注入、缺失 Observation、用户文本诱导调用未知工具，才能单独衡量模型层行为。无论模型表现如何，Harness 护栏都必须是最后防线。

## 8. 官方依据

- [DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion)
- [DeepSeek 思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)
- [DeepSeek API 更新记录](https://api-docs.deepseek.com/updates/)
- [DeepSeek-V4 发布说明](https://api-docs.deepseek.com/news/news260424/)
