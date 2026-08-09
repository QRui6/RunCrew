# Changelog

本项目使用阶段化变更记录。当前处于早期开发阶段，尚未发布稳定版本。

## 2026-08-09

### Added

- 增加 `DeepSeekReviewPolicy`、官方 HTTPS Chat Completions Transport、环境配置、非思考 Tool Calls 解析和有限 API 重试；
- 增加 Policy Trace 白名单，记录模型名、模式、API 尝试、动作解析错误、Token 和耗时，不记录 Prompt、响应正文、Key 或工具参数；
- Evaluation Report 升级至 1.1，增加按用例和聚合的模型调用与 Token 指标；
- 增加受显式付费确认与估算费用上限保护的单条合成 DeepSeek Smoke 命令；
- 增加带价格版本的费用估算和 Policy 费用停止门；
- 增加 9 项 DeepSeek Mock 契约、安全、脱敏、费用门和 Smoke CLI 测试；
- DeepSeek 第二轮改用标准 `assistant(tool_calls) → tool(tool_call_id, result)` 消息链，避免只传 Observation JSON 导致模型重复调用工具；
- 增加完整 12 场景 `deepseek-suite` 命令和跨 Policy 实例共享的总费用停止门；
- 修复完整 Suite 命令擅自把默认场景总超时从 1 秒改为 60 秒、导致 `suite_hash` 无法与确定性基线严格比较的问题；
- 增加回归测试，保证真实模型命令原样使用版本化 Suite；
- 将 Suite 升级为 `review-agent-eval/1.1`，为确定性 Policy 和网络 LLM 统一使用15秒总运行预算；
- Agent 总超时取消正在进行的 DeepSeek 请求时，现在记录已发起 API 尝试和失败遥测，但不会伪造未返回的 Token/费用；
- 增加 ADR-0010，明确时间预算继续属于 Suite Hash，不能按模型偷偷改题；
- 增加 M5-B DeepSeek 模型选型与接入方案，明确模型、模式、数据边界、Harness 校验、失败处理和验收标准；
- 增加 `review-agent-eval/1.0` 版本化离线评测套件，包含 12 个任务、韧性、护栏和预算场景；
- 增加 Evaluation Case、Suite、Metrics 和 Report Schema，以及 Schema 导出脚本；
- 增加 Agent 评测运行器、可替换 Policy 工厂、故障注入、事实一致性和工具执行判分；
- 增加 `runcrew eval review-agent` CLI，并限制报告只能写入 `data/private/`；
- 增加评测退化检测、Schema 漂移和 CLI 私有路径测试；
- 增加训练复盘单 Agent 的 Run、Context、Action、Trace、Error 和 Budget Schema；
- 增加只允许一个只读 Skill 的 Agent Harness 与 `call_tool → observation → finish` 有限循环；
- 增加工具白名单、确认门、步骤/调用预算、有限重试、两级超时和结构化退出原因；
- 增加 `runcrew agent review` CLI 和 Agent Run 输入输出 JSON Schema；
- 增加瞬时错误、超时、非法输出、越权、缺少确认和预算耗尽的故障注入测试；
- 增加 Training Review 输入、计划、窗口、finding 和结果 Schema；
- 增加以目标活动时间为锚点的 7/28 天 Context Builder 和稳定输入哈希；
- 增加训练完成度、七天负荷变化和训练异常三类 evidence-backed 规则；
- 增加 `review-running-training` Skill、JSON Schema 和 CLI；
- 增加缺失数据降级、回放、负荷异常、Schema 漂移和 CLI 测试。
- 中文化 Training Review Skill、UI 元数据和 JSON Schema 字段说明；
- 增加《RunCrew 项目实施全景与面试说明》，记录各阶段方案、亮点、错误、解决方案和范围冻结规则。

### Verified

- 修复后第二次真实 DeepSeek 合成 Smoke 达到 `succeeded / completed`，事实一致性为 True，工具只执行 1 次；
- 成功 Smoke 使用 2 次模型请求、2549 Token，估算费用 0.00016426 美元，动作解析错误为 0；
- 第二次输入有 1664 个缓存命中 Token、630 个未命中 Token，费用低于第一次失败尝试；
- 第一次完整 DeepSeek Suite 运行 12/12 满足预期，任务/护栏/Schema/事实一致率均为 100%，动作解析错误和越权工具执行均为 0；
- 第一次完整运行使用 12 次模型请求、12897 Token、估算 0.00061916 美元；发现其 Suite Hash 因 CLI 超时改写与基线不同，已保留为尝试报告而不冒充正式同题对照；
- 第二次完整运行与 v1.0 确定性基线 Hash 相同，但9个真实模型场景全部在1秒总预算内超时，只有3个脚本化护栏场景通过；
- 新的 v1.1 确定性基线 12/12 通过，Hash 为 `2b89473f...`，等待 DeepSeek 使用相同15秒预算复跑；
- 第一次真实 DeepSeek 合成 Smoke 成功完成鉴权和首轮 Tool Call；第二轮重复调用被 Harness 在执行前拦截，实际工具执行数为 1；
- 首次真实 Smoke 记录 2 次模型请求、2369 Token、0 个动作解析错误和 0.00036106 美元估算费用；
- M3 PR #2 与 M4 PR #3 已依次合并到 `main`；
- M5-A 离线基线 12/12 场景通过，正确性指标均为 100%，越权后工具执行数为 0；
- 全部自动化测试增至 52 项；
- M4 单 Agent 成功路径和故障路径通过 10 项专项测试；
- fixture 端到端 Agent CLI 验收成功，Trace 完整记录 2 步策略决策和 1 次工具调用；
- M2 通过 PR #1 合并到 `main`；
- 24 项自动化测试通过；
- Skill 官方校验器通过；
- 一条真实 COROS 本地活动成功回放，缺失计划/负荷历史时没有编造结论。

### Known Issues

- DeepSeek v1.0 严格复跑受不现实的1秒总预算限制；v1.1 公平时间预算已建立，真实模型尚待最终复跑；
- 当前正式基线为确定性 Policy v1.1；严格同题真实模型对照尚未完成；
- Agent Trace 尚未持久化；
- COROS 训练负荷尚未进入规范化活动；
- 训练计划尚未持久化；

## 2026-08-08

### Added

- 创建 RunCrew Python 项目和本地 `.venv`；
- 增加 Activity、Health、Recovery 和 Review 领域模型；
- 增加 ActivityProvider 协议与 fixture Provider；
- 增加 COROS OAuth + PKCE、MCP 客户端和格式化文本解析；
- 增加 SQLite activities、raw events、sync runs；
- 增加幂等同步与详情错误隔离；
- 增加确定性活动复盘；
- 增加 CLI：`init-db`、`status`、`sync`、`activities list/review`；
- 增加 9 项自动化测试；
- 增加 AI 项目入口、当前状态、路线图、架构、ADR、进展索引和安全文档；
- 增加统一自检脚本 `scripts/verify.py`。
- 初始化独立 Git 仓库，默认分支为 `main`。
- 创建首次提交并推送至 GitHub 私有仓库 `QRui6/RunCrew`。
- 增加 Garmin 官方 FIT SDK、确定性 session/lap/record 映射和 CRC 校验；
- 增加 COROS“详情 → 分圈 → FIT → summary warning”降级链；
- 增加 HTTPS、大小、超时、过期 URL、私有缓存和无效缓存清理；
- 增加不含位置的合成 FIT fixture 与相关契约测试，总测试数增至 19；
- 增加 COROS MCP 工具 schema 只读诊断脚本。

### Verified

- fixture 重复同步不会生成重复活动；
- 真实 COROS 活动列表可以授权、解析、入库和复盘；
- Token 未持久化；
- COROS 详情服务异常时列表数据不会回滚。
- FIT 解析、缓存复用、错误脱敏和三级降级链通过离线自动化验收；
- 真实 FIT 工具参数已根据 COROS 实时 `tools/list` schema 核对。
- 用户手动导出的单条真实 FIT 已通过私有缓存完成同步、入库和分圈复盘，结果为 `detailed=1, detail_errors=0`；

### Known Issues

- COROS `getActivityDetail` 和 `queryActivityLapData` 当前返回服务端异常；
- COROS FIT URL 工具当前返回 `isError=true`，自动下载仍未验收；手动 FIT 已完成真实分圈复盘验收；
- 尚未实现 Token 加密缓存和数据库迁移。
