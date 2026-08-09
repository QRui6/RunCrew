# ADR-0009：DeepSeek 只替换 Policy，并继续由本地 Harness 掌握执行权

- 状态：接受
- 日期：2026-08-09

## 背景

M4 已用确定性 Policy 验证 `call_tool → observation → finish` Loop，M5-A 已建立离线评测基线。M5-B 需要接入真实 LLM，但不能同时改写动作协议、工具执行、安全护栏和业务规则，否则模型错误与运行时回归无法区分。

DeepSeek 原生 Tool Calls 的参数仍可能不是合法 JSON，或包含 Schema 未声明的参数；其 Beta Strict Mode 只支持 JSON Schema 子集，当前 `TrainingReviewRequest` 不能未经转换直接依赖 Strict Mode。

## 决策

- 第一版模型固定为 `deepseek-v4-flash` 非思考模式；
- 使用官方 Chat Completions + 普通 Tool Calls；
- 复用现有 `httpx`，不引入额外模型 SDK；
- `DeepSeekReviewPolicy` 只把受控 `ReviewAgentContext` 转为模型请求，并把响应转为现有 `ToolCallAction / FinishAction`；
- Tool Call 必须再次通过 Pydantic、白名单、确认门、参数一致性和预算校验；
- API Key 使用 `SecretStr` 和环境变量，只允许发送到 DeepSeek 官方 HTTPS 主机；
- Policy 自己处理有限 API 重试，Harness 继续处理工具重试，两种重试分别统计；
- Trace 只接收模型名、模式、尝试数、耗时、Token 和解析结果等白名单元数据，不保存 Prompt、响应正文或工具参数；
- 评测报告 1.1 增加模型调用、API 尝试、动作解析错误、Token、带版本费用估算和模型耗时字段；
- 真实 Smoke 入口只运行一个合成用例，且必须显式提供付费确认和本地估算费用上限。

## 原因

- 保持唯一变量是动作选择层，能够与确定性基线公平比较；
- 本地校验不依赖模型自律或供应商 Strict Mode；
- 非思考模式不需要保存和回传 `reasoning_content`，降低多轮工具调用复杂度；
- 直接使用 `httpx` 可以完整测试请求地址、授权头、错误分类和脱敏；
- Policy API 重试与业务工具重试分离后，费用和故障来源更容易解释。

## 后果

- 当前代码已经可以构造和解析 DeepSeek 请求，但 Mock 通过不代表真实服务已经验收；
- 首次真实请求必须使用合成用例，并由用户配置 Key、确认外部调用和费用上限；
- 当前费用按 `deepseek-pricing/2026-08-09` 估算；真实调用前仍需重新核对官方单价；
- 本地费用门收到 usage 后才能判断，只能阻止后续动作，不能阻止第一笔请求或替代账户侧余额限制；
- 普通 Tool Calls 可能产生非法参数，但 Harness 会在工具执行前拒绝；
- 若后续使用思考模式，必须新增 `reasoning_content` 的多轮回传设计和专项测试。

## 替代方案

- 使用 DeepSeek Beta Strict Mode：暂缓，因为当前 Schema 需要转换，且仍不能替代本地权限校验；
- 使用 OpenAI 兼容 SDK：暂缓，当前只有一个接口，额外依赖不能带来明显收益；
- 把模型直接放进 Service：拒绝，因为会破坏确定性业务规则和可回放性；
- 让模型直接执行 MCP：拒绝，因为会绕过现有 Skill、权限和数据边界；
- 立即使用 Pro 或思考模式：暂缓，先由 Flash 的同套评测结果证明升级必要性。
