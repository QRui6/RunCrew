# Changelog

本项目使用阶段化变更记录。当前处于早期开发阶段，尚未发布稳定版本。

## 2026-08-16

### Fixed

- 将桌面页面固定为 `68px 顶栏 + 剩余工作区` 两行网格，锁定根级滚动并让顶栏锚定顶部，修复顶部品牌、导航和状态被向上裁切；
- 修正工作区内部网格的最小高度和溢出关系，保证底部输入框、发送按钮、免责声明和左侧隐私说明完整落入视口；
- 移动端继续使用文档级滚动，不受桌面视口锁定影响；
- 静态资源版本升级为 `20260816-6`，并增加顶栏与底部边界布局契约测试。

## 2026-08-15

### Changed

- 将通用 SaaS 工作区重构为“运动编辑部 × 数据实验室”视觉：训练索引、活动刊号、编辑式标题、连续指标带与证据脚注共同形成 RunCrew 品牌母题；
- 用户问题和 Agent 回答改为训练研究笔记排版，不再使用聊天气泡；“运行详情”改为按需“回答依据”；
- 当前活动名称保持为页面稳定锚点，会话标题只在对话索引中展示；训练运营和多 Agent 审核能力保持不变；
- 聊天静态资源版本升级为 `20260815-4`，并增加新产品结构的自动化契约断言；
- 将前端视觉系统从荧光黄绿＋亮蓝改为暖灰、炭黑和低饱和森林绿，主操作统一使用炭黑按钮；
- 提高活动、会话、正文、输入框和抽屉字号，增加克制的悬停、按压、内容进入和抽屉滑入反馈；
- 为聊天 CSS/JS 增加版本化 URL，降低浏览器复用旧资源的可能；
- 将默认三栏界面收敛为训练记录与对话两栏，活动快照、智能体协作、用量和安全策略改为按需“运行详情”抽屉；
- 删除首屏技术流程图、巨型宣传标题、英文运行状态和 Private Beta 等演示标签，统一中文业务语言；
- 当前活动名称成为对话主标题，副标题直接展示距离、时长、配速和来源，欢迎区只保留高频问题与证据说明；
- 训练闭环能力保持不变，普通产品面改用训练计划、联合评估、训练执行、恢复评估和计划调整等用户语言；

### Verified

- JavaScript 语法、两个产品入口专项测试和 130 项全量测试通过；本阶段没有调用 COROS 或 DeepSeek；

### Fixed

- 修复本地服务启动时把静态 HTML/CSS/JS 永久读入内存、导致代码更新后刷新浏览器仍看到旧页面的问题；

## 2026-08-13

### Added

- 将聊天首页重构为正式跑步训练智能工作台，增加产品导航、个人训练空间、实时上下文检查器和可观察的 Agent 协作状态；
- 将训练闭环重组为训练运营中心，按计划上下文、身体反馈、跨 Agent 联合评估和运行审计组织，并保留人工确认边界；
- 增加响应式布局、减少动态效果支持、`Ctrl+N` 新建对话和 `Esc` 关闭运营中心等产品级交互；

- 增加 `coach-agent-eval/1.0`：18个版本化无私人数据场景，覆盖任务、节点韧性、权限/交接护栏、预算和批准前 stale；
- 增加 Coach Evaluation Suite/Report Schema、稳定 `suite_hash`、CLI `eval coach-agent`、Schema 导出脚本和 ADR-0019；
- 增加事实一致率、Recovery→Plan 血缘一致率、用户确认边界率、审核防护率和错误节点执行数等多 Agent 指标；
- 增加5项 Coach 评测版本、回放、失败检测、Schema 与私有报告路径测试；
- 在聊天产品增加“训练闭环”抽屉，可选择目标/活动来源、查看激活计划、提交身体反馈、运行 Coach 并审核计划调整；
- 增加训练运营产品领域契约、Service 和五类本地 API；
- 增加本地 `coach_runs` 审计表，保存 Coach 请求、受校验结果、workflow/planning hash、审核状态和正式 proposal 关联；
- 增加批准前 Coach 服务端重放：只有新旧 Planning hash 与完整草案一致才创建并批准正式提案，否则标记 stale；
- 增加六份训练运营 API JSON Schema、导出脚本、8项服务/API/安全/静态资源测试和 ADR-0018；
- 增加 Coach Orchestrator 输入、动作、最小 Policy Context、节点权限、Handoff、Trace、Budget、Error 和输出 Schema；
- 增加 Execution、Recovery、Plan 三个隔离职责节点和确定性编排 Loop，支持有限重试、节点/整次超时、步骤与调用预算；
- 增加 `runcrew coach run`，串联“执行对照 → 恢复评估 → 必要时计划调整”，并在计划草案后暂停等待用户确认；
- 增加跨目标、跨计划和恢复证据血缘校验；Handoff Trace 只记录字段名和请求哈希；
- 增加 Coach 输入输出 JSON Schema、导出脚本和 ADR-0017；
- 增加10项编排、故障和真实 SQLite CLI 集成测试，全量测试增至117项；
- 增加 `compare-training-execution` 中文 Skill、四个输入输出 Schema、规则边界和官方 UI 元数据；
- 增加 `execution compare/decide`，支持只读候选匹配、用户确认、标记跳过和清除错误执行状态；
- 增加训练执行确认审计表，所有写入受 plan revision 保护并提升 revision；
- 增加12项执行对照、冲突降级、未来数据、stale、CLI 和 Schema 测试，全量测试增至107项；
- 增加 ADR-0016，固定候选匹配不能自动成为执行事实的边界。
- 增加 `draft-running-plan` 中文 Skill、周计划/调整输入 Schema、统一输出 Schema、规则边界资料和官方 UI 元数据；
- 增加确定性训练计划 Service，可根据目标、可训练星期与截止时点前历史活动生成可回放周草案；
- 增加 `runcrew planning draft` 与 `runcrew planning adjust`，后者串联 Recovery Skill 并生成带 revision 的待确认提案参数；
- 增加10项计划回放、未来数据隔离、运动类型过滤、保守模板、权限边界与 CLI 测试，全量测试增至95项；
- 增加 ADR-0015，固定计划 Skill 不保存、不批准、不覆盖正式计划的边界。
- 增加 `assess-running-recovery` 中文 Skill、输入输出 Schema、安全边界参考和官方 UI 元数据；
- 增加确定性恢复风险 Context 与 Service，输出五类 recommendation、evidence、缺失数据、置信度和计划动作；
- `DailyCheckIn` 增加结构化急性症状枚举，避免从自由文本猜测心肺红旗；
- 增加 `runcrew recovery assess` CLI 和带时区历史回放；
- 增加12项恢复规则、未来数据隔离、负荷代理、持久化、CLI 和 Schema 测试；
- 增加 ADR-0014，固定恢复风险规则与未来 Recovery Agent 的职责边界。

### Changed

- 修正全景说明中“多 Agent、训练计划数据库、结构化 Check-in 尚未实现”等过期表述，并区分历史范围冻结和当前事实；
- 浏览器审核请求只允许 `decision + comment`，不能提交计划 patch、reason 或 revision；拒绝不会创建正式提案；
- Coach 运行可跨页面刷新恢复，最近运行列表展示待确认、批准、拒绝与 stale 状态；
- 训练执行对照输出增加 `goal_id`，供跨节点 Harness 校验目标范围；
- 计划调整节点保持 `prepare_change` 权限，不能保存或批准提案；缺反馈或红旗时 Coach 不调用 Plan 节点；
- `unmatched` 与 `skipped` 分离；缺少活动不再被解释为用户跳过训练，只有显式确认才更新计划课状态；
- 同一计划内重复活动关联、未来确认和超过三天的跨日确认被拒绝。
- 计划历史不足时使用低强度模板，不按目标成绩推导高强度处方；具体增量、时长分配与降级比例显式归属 RunCrew 工程规则；
- Recovery 的 `plan_action` 成为 Plan Skill 的结构化输入；`keep` 不生成提案，数据不足与专业升级信号安全阻塞。
- 训练负荷覆盖不足80%时改用七天训练时长变化代理，并在 evidence 中公开方法；
- 下一计划课可跨当前周读取到下一训练周；
- 恢复风险建议仍通过 M7-A 提案与用户确认边界修改计划，Skill 不直接写入。

### Verified

- Coach 确定性多 Agent 基线18/18通过，Suite Hash 为 `f1bc86ec92be4aa317b033dd469b6c48d6f0f7c959ce106bc750072d731b8451`；任务、韧性、护栏、审核、Schema、事实、血缘与确认边界指标均为100%，错误节点执行数为0；
- M7-E 全量自动化测试增至130项，项目统一验证通过；只使用合成数据和临时 SQLite，没有调用 COROS 或 DeepSeek；
- M7-D 全量自动化测试增至125项，训练运营 API、重放批准、stale、前端资源和 Schema 漂移均通过；
- `chat.js` 与工程观测台 `app.js` 均通过 JavaScript 语法检查；本阶段没有调用 COROS 或 DeepSeek；
- 应用内浏览器本次无可用实例，未声称完成视觉点击验收，保留本机人工复核项；
- Coach CLI 真实 SQLite 集成测试证明生成草案后 pending proposal 仍为空、plan revision 不变；
- 117项全量测试和项目统一验证通过；M7-C 没有调用 COROS 或 DeepSeek；
- `assess-running-recovery` 通过官方 `quick_validate.py`；
- 12项专项测试和85项全量测试通过；
- 本阶段没有调用 COROS 或 DeepSeek，没有产生外部费用。

## 2026-08-12

### Added

- 增加训练目标、周计划、计划课、每日身体反馈、计划变更提案和用户确认领域模型；
- 增加五张 SQLite 业务表及 Repository，不破坏已有活动和聊天数据；
- 增加训练闭环 Service，落实草稿编辑、计划激活、变更提案、批准/拒绝和版本冲突状态机；
- 增加 `runcrew cycle` 命令组，用于建立目标—计划—反馈—调整的本地工作流；
- 增加 ADR-0013，明确专业 Agent 只有建议权，激活计划的修改必须经过用户确认；
- 增加训练闭环领域、持久化、越权写入、过期提案、矛盾休息课和 CLI 日期测试。

### Changed

- 将简历材料后移到 M8，M7 优先完成可验证的多智能体训练运营闭环；
- M6-A3b 真实聊天模型评测保留为待补验收，但不再阻塞确定性业务能力建设。

### Fixed

- CLI 日期参数改为显式 ISO 日期解析，兼容当前 Typer 版本；
- 为计划变更增加显式字段清除语义，避免休息课残留距离、时长或强度；
- 过期提案以可提交的 `stale` 结果返回，避免错误回滚丢失审计状态。

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
