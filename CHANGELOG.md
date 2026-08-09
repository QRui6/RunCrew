# Changelog

本项目使用阶段化变更记录。当前处于早期开发阶段，尚未发布稳定版本。

## 2026-08-09

### Added

- 将聊天回答升级为五种 response mode 与四类分层论断，个人事实/推断强制 evidence，通用知识/建议保留表达自由；
- 增加 `running-chat-eval/1.0`：7个合成场景、8个连续轮次，覆盖 grounding、openness、safety 和长历史；
- 增加聊天评测 Suite/Report Schema、离线运行器、聚合指标和 Schema 导出脚本；
- 增加 `eval running-chat` 与受显式付费确认、共享费用门保护的 `eval deepseek-chat-suite`；
- 聊天界面新增回答模式、论断类型和可点击后续问题；
- DeepSeek 聊天无效回答现在仍记录已返回 Token 和估算费用；
- 增加7项聊天评测、自由度退化、CLI安全门、上下文和失败用量测试；
- 将产品主入口从只读 Dashboard 改为围绕个人跑步数据连续追问的本地聊天工作区，原页面保留为 `/engineering` 工程观测台；
- 增加 Activity 选择、会话创建、消息 POST、历史加载和 SQLite 持久化；
- 首次提问复用 `ReviewAgentHarness → review_running_training` 生成并保存 evidence/Trace 快照，后续追问不重复计算；
- 增加最近8条消息/单条1200字符的上下文窗口、离线证据回答和 DeepSeek JSON 回答策略；
- 增加回答 evidence 引用白名单、置信度/缺失数据契约、医疗诊断措辞校验、Token/费用展示和64 KB请求上限；
- 增加3项聊天持久化、真实 HTTP 契约、DeepSeek Mock 与上下文裁剪测试；
- 增加 `runcrew demo` 本地只读 Dashboard，集中展示 Activity、Training Review evidence、Agent 预算/Trace 和 Same-Hash 模型对照；
- 增加无第三方 Web 依赖的回环 HTTP 服务、展示 DTO、响应式单页和静态资源 Wheel 配置；
- 演示 API 只接受 GET，浏览器 DTO 排除 Provider 外部 ID、raw payload、坐标和 Token；
- 增加4项 Dashboard 数据、隐私、静态路由、参数、只读方法、缺失数据库不落盘和 CLI 测试；
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

- `running-chat-eval/1.0` 离线基线7场景8轮全部通过，grounding、openness、safety、schema均为100%；
- 聊天 Suite Hash 为 `ab097079836d0fa2c1227da0e84dfa32be5bd40538d15e52c47d2580d265fe94`；
- 全量自动化测试增至66项；M6-A3a没有调用真实 DeepSeek；
- 跑步聊天首问和追问持久化、同一 evidence 快照复用、脱敏 DTO 与 DeepSeek JSON 契约通过自动化测试；
- 全量自动化测试增至59项，两个前端脚本均通过 JavaScript 语法检查；
- 本机已有 COROS 规范化数据通过只读 Dashboard 验收：Agent succeeded、3条 finding、9个 Trace 事件、Same-Hash 成立；
- 全量自动化测试增至56项；
- v1.1 最终 DeepSeek 与确定性基线使用相同 Suite Hash `2b89473f...`，双方均为 12/12 满足预期；
- DeepSeek 最终任务、护栏、Schema 和事实一致率均为 100%，越权工具执行和动作解析错误均为0；
- 最终模型评测使用12次 API 请求、13175 Token，估算费用0.00076208美元，Policy 累计耗时24667.601ms，P95单场景耗时4862.875ms；
- 两种 Policy 的终态分布、平均工具调用数0.5833和平均工具尝试数0.75完全一致；
- 修复后第二次真实 DeepSeek 合成 Smoke 达到 `succeeded / completed`，事实一致性为 True，工具只执行 1 次；
- 成功 Smoke 使用 2 次模型请求、2549 Token，估算费用 0.00016426 美元，动作解析错误为 0；
- 第二次输入有 1664 个缓存命中 Token、630 个未命中 Token，费用低于第一次失败尝试；
- 第一次完整 DeepSeek Suite 运行 12/12 满足预期，任务/护栏/Schema/事实一致率均为 100%，动作解析错误和越权工具执行均为 0；
- 第一次完整运行使用 12 次模型请求、12897 Token、估算 0.00061916 美元；发现其 Suite Hash 因 CLI 超时改写与基线不同，已保留为尝试报告而不冒充正式同题对照；
- 第二次完整运行与 v1.0 确定性基线 Hash 相同，但9个真实模型场景全部在1秒总预算内超时，只有3个脚本化护栏场景通过；
- 新的 v1.1 确定性基线 12/12 通过，随后 DeepSeek 使用相同15秒预算和 Hash 也达到12/12；
- 第一次真实 DeepSeek 合成 Smoke 成功完成鉴权和首轮 Tool Call；第二轮重复调用被 Harness 在执行前拦截，实际工具执行数为 1；
- 首次真实 Smoke 记录 2 次模型请求、2369 Token、0 个动作解析错误和 0.00036106 美元估算费用；
- M3 PR #2 与 M4 PR #3 已依次合并到 `main`；
- M5-A 离线基线 12/12 场景通过，正确性指标均为 100%，越权后工具执行数为 0；
- M5-B3 完成时全部自动化测试为52项；
- M4 单 Agent 成功路径和故障路径通过 10 项专项测试；
- fixture 端到端 Agent CLI 验收成功，Trace 完整记录 2 步策略决策和 1 次工具调用；
- M2 通过 PR #1 合并到 `main`；
- 24 项自动化测试通过；
- Skill 官方校验器通过；
- 一条真实 COROS 本地活动成功回放，缺失计划/负荷历史时没有编造结论。

### Known Issues

- 三个非法动作护栏场景仍由脚本化 Policy 注入，当前结论主要证明 Harness 防线，不等于真实模型对抗安全得分；
- DeepSeek 已通过当前简单动作协议，尚未评估包含提示注入或复杂多工具选择的模型行为；
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
