# 当前状态

> 本文件是项目当前进度的唯一事实来源。任何 AI 开始工作时必须先读本文件。  
> 最后更新：2026-08-20

## 当前里程碑

**M7 训练产品闭环、M9 可审计 Memory Manager、M8 求职证据包与 M10 Agent Runtime Governance 均已完成。M10 已闭合四工具 Manifest/Guardrail、Review/Coach 统一 Run/Span、跨运行指标、5场景治理评测和只读工程观测台。全量202项测试通过；下一入口为 M8-A1.4 本机视觉与点击验收。真实 DeepSeek 聊天同题验收仍待补。**

M1-M4 数据、Skill 和单 Agent Harness 已完成；M5-A 当前可以完成：

```text
版本化合成评测套件
→ 运行正常任务、韧性、护栏和预算共 12 个场景
→ 复用真实 ReviewAgentHarness 和 Training Review Service
→ 注入瞬时错误、超时、非法输出和非法 Policy 动作
→ 校验终态、Schema、事实一致性和工具是否越权执行
→ 聚合完成率、护栏通过率、调用成本、延迟和退出原因
→ 生成 suite_hash 和可比较评测报告
```

## 已验证事实

- M8-A1.1 已把默认三栏收敛为训练记录＋连续对话两栏；M8-A1.3 进一步把普通后台结构改为训练索引、活动刊号、连续指标带和训练研究笔记；
- 首屏已删除技术流程图、巨型宣传标题、英文运行状态和演示标签，用户语言统一为当前活动、高频问题、增强回答与训练计划；
- M8-A1.2 已去除荧光黄绿和高饱和亮蓝，主按钮改为炭黑，森林绿只表达状态；正文、列表、输入框与抽屉字号已提高，并增加低幅交互反馈；
- 本地服务不再在启动时永久缓存静态文件，CSS/JS 使用版本化 URL；旧服务只需再重启一次，后续前端更新可直接刷新查看；
- 当前活动名称不再被会话标题覆盖；距离、用时、平均配速和平均心率由活动 DTO 动态填入连续数据带；
- 用户问题、RunCrew 回答、回答模式、evidence、置信度和缺失数据已改为正文＋脚注式表达；Agent 协作和上下文用量移入“回答依据”；
- 桌面根页面已固定为 `68px` 顶栏与剩余工作区两行网格，侧栏和聊天区允许在剩余行内收缩，静态资源版本为 `20260820-4`；
- M8-B 已将目标创建、周计划草案与重放确认、今日/下一节训练、活动候选人工匹配、跑后反馈、Coach 调整审核和本周总结接入同一网页流程；
- M9-A 已增加 `athlete_preferences` 类型化长期偏好：网页/API/CLI 必须显式确认；同 key 新值替代旧版本，停用不硬删除，到期不进入计划上下文；
- Planning Agent 会在目标允许日期内优先使用长跑日偏好，并在 `input_hash` 与 evidence 中记录偏好版本、来源和采用结果；偏好变化会使待激活旧草案变为 stale；
- M9-B 已增加 `weekly_training_memories`：完整训练周结束后，只从正式计划、已应用执行确认、对应规范化 Activity、Check-in 和已批准变更确定性结算；
- 周训练记忆具有输入 Hash、来源引用、版本及 `active / superseded / invalidated` 生命周期；未确认、未来或失效事实不会进入 Planning；
- Planning Agent 优先用最近有效周记忆计算确认训练时长基线，并将记忆 ID、版本和 Hash 写入 evidence 与计划输入 Hash；记忆不足时回退到规范化 Activity；
- M9-C 已增加统一 Memory Context Builder：Execution 为0条/0字符，Recovery 最多2条/1400字符，Plan 最多5条/1800字符；
- 每个候选都记录选中顺序或职责无权限、未来、过期、替代、归档、失效、窗口外和预算不足等排除原因；
- Plan 周摘要不包含恢复、疼痛和急性症状字段；Recovery 周摘要只作背景且不改变安全阈值；Context Hash 绑定实际选中内容，Audit Hash 绑定完整检索审计；
- Execution、Recovery、Planning 结果和网页周视图携带职责 Context，`runcrew memory context` 可独立检查；CLI Planning 已与网页统一消费周记忆；
- M9-D 已增加独立 `memory_candidates` 生命周期：聊天只从明确长期长跑日表达生成候选，临时、否定、多星期歧义和不支持内容不生成；
- 候选保存原消息 ID/文本 Hash、类型化值、规则版本、置信边界、Candidate Hash 与七天有效期，不复制消息正文，也不进入正式 Agent Context；
- 浏览器只提交决定和预期 Candidate Hash；确认时服务端重算候选 Hash、重读原始用户消息，并复用 M9-A 正式偏好服务，拒绝、替代、过期或来源变化均不会写入；
- M9-E 已建立 `memory-manager-eval/1.0`：candidate 6个、lifecycle 5个、integrity 2个、retrieval 3个，共16个无私人数据场景；
- Memory 基线16/16满足期望，候选正样本召回、负样本拒绝、生命周期、来源完整性、确认边界、职责隔离和无关注入抵抗均为100%，意外正式写入为0；Suite Hash 为 `78e9e4dc7c1e75cb94fbbbfbc60cb9b9b74874da7555757a58487567892d51ef`；
- 生命周期与篡改场景使用隔离 SQLite 运行真实 Repository/Service，职责召回运行正式 Context Builder；这些数字只覆盖2个合成正样本、4个合成负样本和列出的工程场景，不代表真实用户语言总体准确率；
- 无关、过期、归档、未来、失效或错误目标记忆不会改变实际 Context Hash，但会改变 Audit Hash并留下排除原因；当前没有评测证据支持引入向量数据库；
- M9-F 已增加按需加载的“记忆档案”：集中查看待确认 Candidate、正式偏好、周训练记忆、来源摘要、时效、生命周期和三职责选中/排除原因；
- M10-A 已注册 `review_running_training`、`compare_training_execution`、`assess_running_recovery`、`adjust_running_plan` 四个 Tool Manifest，明确责任角色、访问、副作用、风险、Schema、确认和运行上限；
- 统一 Runtime Guardrail 会在执行前检查注册、角色、访问级别、持久化/审批能力、确认、参数 Hash 和超时/重试上限，在执行后核对 Manifest 输出 Schema；
- Review/Coach Trace 保留原事件与失败码，并增加 Manifest Hash、参数一致性、规则 ID/结果等同构脱敏元数据；参数正文、身体反馈和 Token 不进入治理 Trace；
- M10-B 已增加 `agent_runtime_runs / agent_runtime_spans`，把 Review/Coach 映射为同一 `runtime-run/1.0 + runtime-span/1.0` 父子时间线；
- 聊天首轮 Review 与训练运营 Coach 使用独立短事务 best-effort 持久化；表缺失、锁冲突或序列化失败不会改变 Agent 终态，离线 Evaluation 不写产品 Runtime 表；
- Runtime 只保存白名单 Hash、规则、计数、错误类型、节点/工具和时间信息，业务关联只存不可逆 `scope_ref_hash`；默认保留30天；
- Runtime 指标支持1—30天窗口与最多500 Run，确定性计算成功率、Guardrail 拒绝率、工具成功率、重试率、预算耗尽率和 nearest-rank P50/P95，并按工作流、版本、工具、职责和退出原因分组；
- `runtime-governance-eval/1.0` 五个合成场景5/5符合期望，执行前阻断、非法输出阻断和观测故障隔离均为100%，禁止工具误执行与敏感错误泄漏均为0；该结果不代表真实 LLM 攻防效果；
- `GET /api/runtime/metrics`、`GET /api/runtime/runs`、单次父子时间线与治理评测 API 均为只读；`/engineering` 已消费这些接口形成 Runtime 观测台；
- Candidate 决定、偏好停用和周记忆失效继续复用既有服务与确认边界；控制面不拥有新写权限，不硬删除历史，也不向浏览器返回 Provider 外部 ID、原始载荷、坐标或 Token；
- 周计划与执行写入分别受 `input_hash` 重放和 `revision` 保护，候选活动只有在用户确认后才计入周完成率；
- Coach 运行开始和完成时，Execution、Recovery、Plan 三个职责节点会同步显示运行中、已完成、无需调用或生成草案状态；
- 新界面保持 `textContent` DOM 安全边界和响应式布局，JavaScript 语法、专项静态资源测试及 202 项全量测试通过；
- `runcrew demo-seed --reset` 可以在 `data/private/demo/` 创建与个人数据库隔离的完整合成训练状态；种子不调用 COROS/DeepSeek，也不预置对话或 Coach 结论；
- 求职演示包已包含系统架构图、训练闭环时序图、五分钟演示脚本和明确的可声明/不可声明证据边界；
- 求职材料包已区分202项回归、Runtime 治理5/5、真实 DeepSeek 单 Agent 12/12、确定性多 Agent 18/18和 Memory Manager 16/16，并为简历条目、核心难点和14个面试追问建立证据索引；
- 2026-08-20 应用内浏览器仍无可用实例，因此收敛版视觉和记忆档案点击验收仍需本机人工复核，没有冒充完成截图验收；

- Python 3.13 本地环境可运行；
- 自动化测试：202 passed；
- fixture 首次同步插入 2 条；
- fixture 第二次同步插入 0 条、更新 2 条；
- 真实 COROS OAuth + PKCE 成功；
- 真实 `querySportRecords` 成功；
- 真实 COROS 活动已转换并写入本地数据库；
- `activities review --latest --provider coros` 可以输出复盘 JSON；
- Token 未落盘；
- 必要项目文档和 AI 入口已补齐。
- RunCrew 已初始化为独立 Git 仓库，默认分支为 `main`；首次提交为 `d157a78`。
- GitHub 私有仓库：`https://github.com/QRui6/RunCrew`；本地 `main` 跟踪 `origin/main`。
- 官方 `garmin-fit-sdk` 21.212.0 可在 Python 3.13 解码和编码 FIT；
- 合成 FIT 可稳定映射 1 个 session、4 个 lap 和 12 个 record；
- FIT HTTPS、50 MB 上限、过期 URL、CRC、私有缓存和失败降级均有自动化测试；
- `queryActivityFitFileDownloadUrls` 的实时 schema 已核对，单活动参数为 `labelId + sportType`。
- 一条由用户从 COROS App 手动导出的真实 FIT 已通过 CRC、session、lap 和 record 解析；
- 真实 FIT 经私有缓存进入完整同步链，验收结果为 `detailed=1, detail_errors=0`；
- 真实活动复盘已输出基于多分圈计算的 `pace_stability` evidence，数据质量为 high。
- M2 已通过 GitHub PR #1 合并到 `main`；
- M3 GitHub PR #2 与 M4 GitHub PR #3 已依次合并到 `main`；
- M5-A GitHub PR #4 已创建，base 为 `main`；
- `TrainingReviewRequest` / `TrainingReviewResult` Schema 已定义并导出；
- `review-running-training` Skill 已通过官方 `quick_validate.py`；
- 同一输入会生成相同 `input_hash` 和结果，回放测试已通过；
- 真实 COROS 本地活动已通过 Training Review CLI 回放，缺少计划和负荷历史时正确降级，分圈 evidence 仍然保留。
- 中文《项目实施全景与面试说明》已记录 M0-M5-A 的技术方案、错误复盘、面试表达和后续范围冻结；
- Training Review Skill、UI 元数据和导出 Schema 的说明已中文化。
- `ReviewAgentRunRequest` / `ReviewAgentRunResult`、Action、Context、Trace、Error 和 Budget Schema 已定义；
- 单 Agent 只允许调用 `review_running_training`，未知工具、参数篡改和未确认调用会被拒绝；
- 步骤、逻辑工具调用、重试、单次工具超时和整次 Run 超时均有明确预算；
- 瞬时错误、工具超时、非法输出、越权、缺少确认和预算耗尽均通过故障注入测试；
- `runcrew agent review` 可以返回经过校验的训练复盘、终态、退出原因、预算和 Trace；
- Agent Run 输入输出 JSON Schema 已导出，并由测试防止与 Pydantic 模型漂移。
- fixture 端到端 Agent Smoke Test 已通过：`succeeded / completed`，2 个策略步骤、1 次逻辑工具调用、1 次工具尝试。
- `review-agent-eval/1.1` 已包含 12 个无私人数据场景，覆盖任务、韧性、护栏和预算；
- 离线基线 12/12 通过，正常任务完成率、护栏通过率、Schema 通过率和事实一致率均为 100%；
- 被护栏拒绝后底层工具执行数为 0，平均逻辑工具调用 0.5833，平均工具尝试 0.75；
- 评测套件和报告 Schema 已导出，`suite_hash` 可标识同一批评测输入；
- `runcrew eval review-agent` 可运行评测，报告只允许写入 `data/private/`。
- M5-B 已核对 DeepSeek 官方模型、Tool Calls、思考模式和 Schema 约束；推荐 `deepseek-v4-flash` 非思考模式，选型与接入方案已形成中文文档。
- `DeepSeekReviewPolicy` 已实现受控 Context、非思考 Tool Calls、Action 解析和有限 API 重试；
- DeepSeek API Key 由环境变量和 `SecretStr` 管理，只允许发送到官方 HTTPS 主机；
- 模型 Tool Call 仍经过 Pydantic、白名单、确认、参数一致性和预算校验，Mock 参数篡改时底层工具执行数为 0；
- Policy Trace 只记录模型名、模式、尝试数、解析错误、耗时和 Token 等白名单元数据；
- Evaluation Report Schema 已升级至 1.1，可按用例和总报告统计模型调用、API 尝试、动作解析错误、缓存 Token、输入/输出/思考 Token 和模型耗时；
- `runcrew eval deepseek-smoke` 已实现，只运行 `complete_training_review` 合成用例，并在读取 Key 前强制要求 `--confirm-paid-api` 与 `--max-estimated-cost-usd`；
- 费用按 `deepseek-pricing/2026-08-09` 估算并写入 Trace/报告，超过 Policy 上限时停止后续动作；该上限是本地后验停止门，不是供应商账单硬上限；
- DeepSeek Policy 与 CLI 的零费用测试已覆盖 Mock 契约、安全门、单用例 Smoke、完整 Suite 费用门、Suite 不变性和请求取消遥测；M6-A1 Dashboard 完成时全量56项通过。
- 真实 `deepseek-v4-flash` 非思考请求已连通，首次 Tool Call 参数通过 Action Schema 和 Harness 校验；
- 第一次真实 Smoke 共 2 次模型请求、2369 Token、估算 0.00036106 美元，动作解析错误为 0；
- 第二轮模型重复请求工具，Harness 在执行前以工具预算拦截，底层工具实际只执行 1 次；
- 已把第二轮上下文修正为标准 `assistant(tool_calls) → tool(tool_call_id, result)` 消息链，Mock 回归通过。
- 修复后第二次真实 Smoke 达到 `succeeded / completed`，事实一致性为 True，业务工具只执行 1 次；
- 成功 Smoke 共 2 次模型请求、2549 Token、0 个动作解析错误，估算费用 0.00016426 美元，模型累计耗时 4663.993 ms；
- 成功尝试输入 Token 中 1664 个命中缓存、630 个未命中缓存；两次真实报告均保存在 `data/private/evals/`。
- `runcrew eval deepseek-suite` 已实现：复用同一 12 场景 Suite，并以跨用例共享费用对象限制整套评测总成本。
- 第一次完整 DeepSeek 运行 12/12 满足预期：任务完成率、护栏通过率、Schema 通过率和事实一致率均为 100%，越权工具执行数与动作解析错误均为 0；
- 第一次完整运行共 12 次 API 请求、12897 Token、估算费用 0.00061916 美元，Policy 累计耗时 23581.19 ms，P95 单场景耗时 4422.692 ms；
- 9 个场景使用真实 DeepSeek Policy，3 个越权/参数篡改/提前结束场景继续使用脚本化故障注入；
- 审核报告时发现 CLI 曾把默认场景 `run_timeout_seconds` 从 1 改为 60，使报告 Hash `783517...` 与 v1.0 基线 Hash `f3dc7d...` 不同；该报告已另存为 `deepseek-suite-attempt-1-timeout-adjusted.json`；
- 第二次运行原样使用 v1.0，Hash 与基线一致，但9个真实模型场景全部在1秒内 `run_timeout`，只有3个脚本化护栏场景通过；报告保存为 `deepseek-suite-attempt-2-one-second-timeout.json`；
- v1.0 的1秒预算原本只适合确定性离线回归，不适合需要网络往返的 LLM；这不是模型动作质量失败，而是评测预算设计不公平；
- Suite 已升级到 `review-agent-eval/1.1`，两种 Policy 统一使用15秒总预算，超时仍进入 Hash；新的确定性基线 12/12 通过，Hash 为 `2b89473f6f9e02f06960965bfafdac74aacff1b28ead42eeade0e7a5afd199e9`；
- 被总超时取消的模型请求现在会记录 API 尝试和失败遥测；由于供应商没有返回 usage，本地 Token/费用保持0，但不能据此断言账户一定未计费。
- v1.1 最终 DeepSeek 报告与确定性基线 Suite Hash 完全一致，均为 `2b89473f6f9e02f06960965bfafdac74aacff1b28ead42eeade0e7a5afd199e9`；
- 两种 Policy 均为12/12满足预期，终态分布、平均工具调用0.5833和平均工具尝试0.75一致；
- DeepSeek 正常任务完成率、护栏通过率、Schema 通过率和事实一致率均为100%，越权工具执行数与动作解析错误均为0；
- DeepSeek 共12次 API 请求、13175 Token，估算费用0.00076208美元；Policy 累计耗时24667.601ms，平均单次 API 约2055.633ms，P95单场景4862.875ms；
- 输入 Token 缓存命中率约81.49%；最终报告保存在 `data/private/evals/deepseek-suite-v1.1-final.json`；
- 当前简单动作协议没有证据需要升级 `deepseek-v4-pro`，也没有职责冲突或上下文负担证据支持拆分多 Agent。
- `runcrew demo` 已提供只绑定 `127.0.0.1:8766` 的本地产品服务；
- `/engineering` 工程观测台可以筛选7/30天 Runtime 窗口，展示跨运行指标、5场景治理基线、最近 Run 和单次脱敏父子时间线；
- Runtime 工程观测 API 只接受 GET；聊天 API 提供受限 POST 并写入本地会话，两者均不返回外部活动 ID、raw payload、坐标或 Token；
- 本机真实 COROS 规范化数据只读验收通过：活动可用、Agent succeeded、3条 finding、9个 Trace 事件、Same-Hash 成立；
- M6-A1 自动化测试曾增至56项，覆盖 Dashboard 数据脱敏、Agent 回放、静态资源、API 参数、只读方法、缺失数据库不落盘和 CLI 入口。
- 产品根页面是跑步数据连续对话工作区，`/engineering` 是独立的只读 Runtime 工程观测台；
- 用户可以选择具体 Activity、创建本地会话、发送消息、加载历史并围绕同一证据快照连续追问；
- 首次提问通过真实 `ReviewAgentHarness → review_running_training` 生成 `TrainingReviewResult + Trace`，后续追问复用快照；
- `chat_conversations` / `chat_messages` 持久化会话、消息、evidence 引用、置信度、缺失数据、模型和用量；
- 聊天上下文最多携带最近8条历史消息，单条最多1200字符；不向回答 Policy 暴露 Provider 原始载荷、外部 ID 或坐标；
- 默认离线 evidence 回答不产生外部请求；只有界面显式开启且本机存在 Key 时才调用 `DeepSeekGroundedChatPolicy`；
- DeepSeek 回答必须通过 JSON Schema、evidence 类型白名单和越界医疗措辞检查；Mock 已验证 JSON 模式、130 Token 用量与8条上下文裁剪；
- 自动化测试增至59项，两个 JavaScript 文件均通过语法检查。
- `ChatAnswer` 已升级为“自由正文 + 分层论断”：五种回答模式和四类论断，只有个人数据事实/推断强制 evidence；
- 通用跑步知识与训练建议无需机械引用个人 evidence，但不能伪装成用户已经发生的事实；
- UI 可以展示回答模式、数据事实/推断/通用知识/建议标签，并把后续问题作为可点击追问；
- M6-A2 旧消息不需要数据库迁移：Repository 从原有 JSON 元数据兼容恢复，新消息持久化完整回答结构；
- `running-chat-eval/1.0` 包含7个合成场景、8个连续轮次，覆盖 grounding、openness、safety 和长 context；
- 离线自由对话基线8/8通过，四项指标均为100%，Suite Hash 为 `ab097079836d0fa2c1227da0e84dfa32be5bd40538d15e52c47d2580d265fe94`；
- 评测会拒绝把通用知识错误包装成个人数据结论；DeepSeek 无效回答也会保留已返回 Token 和估算费用；
- `runcrew eval deepseek-chat-suite` 已实现完整 Suite、显式付费确认、共享费用门和私有报告路径限制；
- 自动化测试增至66项；M6-A3 尚未调用真实 DeepSeek，因为当前进程、Windows User 和 Machine 环境均没有可读取的新 Key。
- M7-A 已增加训练目标、周计划、计划课、每日身体反馈、变更提案和用户确认领域契约；
- 新增 `training_goals`、`training_plans`、`daily_check_ins`、`plan_change_proposals`、`user_confirmations` 五张本地表；
- `runcrew cycle` 可以创建/列出目标、创建周计划、添加训练课、激活计划、记录反馈、提出变更、确认变更和查看快照；
- 激活计划禁止直接写入，Agent 只能基于当前 revision 提案；用户批准后才生效，旧版本提案标记为 stale；
- 休息课不能残留距离或时长，Patch 通过显式 clear 字段区分“不修改”和“清除”；
- M7-A 全量自动化测试增至73项；只使用合成数据，没有访问外部服务或产生费用。
- M7-B3 新增第六张训练闭环业务表 `training_execution_confirmations`，用于保存执行确认审计记录；
- `assess-running-recovery` Skill 已提供中文流程、输入输出 Schema、运动安全红旗资料和 UI 元数据，并通过官方校验；
- `RecoveryAssessmentRequest/Result` 使用显式评估时间、Provider 过滤、`input_hash` 和 `recovery-risk-rules/1.0` 支持回放；
- 恢复风险输出固定为 `proceed / reduce / rest / seek_professional_help / insufficient_data`，recommendation 与 risk level 由 Schema 约束一致；
- 心肺红旗优先于训练负荷；缺少新鲜身体反馈时不会默认正常训练，过期红旗仍会升级；
- 训练负荷覆盖不足80%时以七天训练时长变化作为公开代理，而不是伪造 load；
- `plan_action` 只请求计划 Agent 产生变更提案，Recovery Skill 不直接修改正式计划；
- 历史回放排除评估时间之后的活动和反馈，下一计划课可从当前周或下一周读取；
- M7-B1 增加12项专项测试，全量自动化测试增至85项；没有调用外部账户或付费模型。
- `draft-running-plan` Skill 已提供中文流程、两类输入 Schema、统一输出 Schema、规则边界和 UI 元数据，并通过官方校验；
- `planning draft` 根据目标、可训练星期、截止时间前历史活动生成待确认周计划草案，不覆盖已有周计划；
- 草案使用 `training-plan-rules/1.0 + input_hash + UUIDv5 session id` 支持同输入稳定回放；
- 历史不足时只安排低强度入门模板；目标成绩不会被直接换算为高强度处方；
- `planning adjust` 已串联 Recovery Skill 与 Plan Skill：消费 `plan_action` 后返回带 `base_revision` 的 `PlanChangeProposal` 参数；
- `keep` 不生成提案；缺数据与专业评估升级信号返回 blocked；reduce/rest 仍需用户确认；
- Plan Skill 不保存、不批准提案，专项测试证明命令执行后 pending proposal 为空；
- M7-B2 增加10项专项测试，全量自动化测试增至95项；没有读取私人活动或调用外部账户。
- `compare-training-execution` 中文 Skill 已提供对照/确认 Schema、规则边界和 UI 元数据，并通过官方校验；
- `execution compare` 对计划课和实际跑步进行只读候选匹配，输出 complete/partial/skipped/unmatched/upcoming/rest；
- 清晰候选仍标记 suggested；多候选、同一活动竞争多课、低分和缺少可比较训练量均不会自动关联；
- unmatched 不自动等同 skipped，跳过只能由用户通过 `execution decide` 明确确认；
- 确认匹配、标记跳过和清除状态均使用 base revision，成功后提升 plan revision 并保存独立审计记录；
- 未来活动、未来计划课、相差超过三天的活动和同计划重复关联被拒绝；
- M7-B3 增加12项专项测试，全量自动化测试增至107项；没有读取私人活动或调用外部账户。
- `CoachAgentRunRequest/Result`、四类动作、最小 Policy Context、节点权限、Handoff、Trace、Budget 和 Error Schema 已定义并导出；
- `DeterministicCoachPolicy` 只负责 Execution → Recovery → 必要时 Plan 的路由，不能读取原始活动、身体反馈明细或数据库；
- Execution、Recovery、Plan 三个职责节点各自只绑定单一工具，Plan 只有 `prepare_change` 权限，不能保存或批准；
- Harness 校验交接参数、工具白名单、目标/计划范围和 Recovery `input_hash` 血缘，并统一处理步骤/调用预算、重试、节点/整次超时和非法输出；
- 减量/休息只生成草案并以 `awaiting_user_confirmation` 暂停；缺反馈与安全红旗直接阻断而不调用 Plan；
- `runcrew coach run` 已接入真实 SQLite Service；集成测试证明运行后 pending proposal 为空、plan revision 不变；
- M7-C 增加10项专项测试，全量自动化测试增至117项；没有读取私人活动或调用外部账户。
- 聊天产品顶部新增训练闭环入口，可选择激活目标、活动来源、查看计划、提交结构化身体反馈并运行 Coach；
- `coach_runs` 保存运行请求、完整受校验结果、workflow/planning hash、审核状态、proposal ID 与决定时间，刷新后可以恢复待审核运行；
- 浏览器 decision 只允许 `approve/reject + comment`，额外的 changes/reason/revision 会被 Schema 拒绝；
- 用户拒绝只关闭 Coach 运行，不创建正式提案；用户批准前服务端重放原请求，结果或草案变化则标记 stale；
- 重放一致时由服务端从 Coach 草案创建正式提案，再经 `TrainingCycleService` revision 校验应用；
- 六份训练运营 API Schema 已导出，新增8项产品服务、API、安全和静态资源测试；
- `coach-agent-eval/1.0` 已建立18个版本化无私人数据场景，覆盖正常路由、恢复/休息、缺反馈、红旗、重试、超时、非法输出、权限、Handoff、血缘、预算和 stale；
- Coach 评测直接复用真实 Harness，批准前状态漂移场景运行真实 `TrainingOperationsService + 临时 SQLite`；
- 确定性多 Agent 基线18/18通过，Suite Hash 为 `f1bc86ec92be4aa317b033dd469b6c48d6f0f7c959ce106bc750072d731b8451`；
- 任务、韧性、护栏、审核、Schema、事实、血缘和用户确认边界通过率均为100%，错误节点执行数为0，平均节点调用1.2778、平均尝试1.3889；

## 当前已知限制

- M9-A/M9-D 当前只支持 `preferred_long_run_weekday`，复杂隐含或跨消息偏好会保守漏召回；M9-E 的100%召回/拒绝只来自2个合成正样本与4个合成负样本，不能声称真实用户准确率；
- 演示种子是合成业务场景，只能证明当前工程链路可运行，不能证明真实用户训练效果或生产级稳定性；
- 到期偏好会在读取时排除并投影为 `expired`，当前不运行后台任务改写其历史审计 JSON；
- `getActivityDetail` 异常；
- `queryActivityLapData` 返回相同异常；
- `queryActivityFitFileDownloadUrls` 在参数符合实时 schema 的情况下返回 `isError=true`，没有下发下载 URL；
- 自动 FIT URL 未能验证，但用户手动导出的真实 FIT 已通过私有缓存完成端到端验收；
- 当前 COROS 规范化活动没有训练负荷字段，因此真实 `load_change` 暂时可能为 `unknown`；
- 训练目标、计划草案/激活、今日训练、活动匹配确认、反馈、Coach 运行/审核和周总结均已接入网页；CLI 保留为工程与回放入口；
- 恢复风险阈值是 RunCrew 保守工程规则，不是临床决策；无训练负荷时的时长代理不能表示强度差异；
- Coach 多职责 Harness 已通过版本化确定性 Suite，但尚未接入或评测真实 LLM Coach Policy；脚本化越权注入只能证明 Harness 防线；
- 普通自然语言聊天不会隐式触发训练写入；结构化训练闭环抽屉才拥有显式审核入口；
- 本阶段没有进行真实浏览器逐像素验收，桌面首屏、长回答和两个抽屉仍需本机主观复核；HTTP/DOM/JS 自动化已通过；
- 计划 v1 主要按时长规划，不处理比赛周、天气、海拔、力量训练或精确配速区间；5%增量和60%降级是保守工程规则；
- 执行对照 v1 不理解训练标题、配速/心率区间和间歇分段；多设备重复活动及跨计划重复关联尚未自动解决；
- 当前12场景中，3个非法动作场景使用脚本化 Policy 注入，只能证明 Harness 能拦截，不能声称真实 DeepSeek 在提示注入或恶意诱导下同样安全；
- 当前模型任务只有一个工具和两种动作，12/12通过不代表复杂规划、多工具协作或生产稳定性已经验收；
- 本地费用门只能在收到真实 usage 后停止后续动作，不能阻止第一笔请求，也不能替代 DeepSeek 账户侧余额控制；
- 单用例真实 DeepSeek Loop 已验收，但还不能把一个成功用例描述成完整模型稳定性结论；
- Review Agent Trace 已随聊天 evidence 快照持久化；CLI Trace 仍只随单次 JSON 返回；
- 聊天 DeepSeek 路径已通过 Mock 契约和离线8轮评测，但尚未完成真实模型同题运行，不能声称多轮模型稳定性或提示注入安全已验收；
- 当前自然度只通过回答模式、论断类型和最低信息量做代理测量，尚无人工偏好评分；
- 当前一个 Conversation 固定绑定一个目标活动；还不能在同一会话中切换活动或比较任意两场跑步；
- 聊天记录尚无删除、导出和保留期限功能；
- 工具超时会停止 Harness 等待，但已经在线程中开始的同步只读查询不能被强制终止；
- 真实数据库历史活动数量仍少，跨周负荷回放主要由合成 fixture 验证。

当前降级行为：

- 活动列表仍然保存；
- 若私有缓存存在，解析真实 FIT 并生成 `ActivityDetail`；
- 若没有缓存且 COROS FIT URL 工具失败，保留 summary 并记录 warning；
- 不伪造分圈和时间序列。

## 下一项唯一任务

**M8-A1.4：本机视觉与点击验收。**

使用合成演示数据库启动产品，依次复核桌面首屏、训练运营抽屉、记忆档案、`/engineering` 7/30天筛选和单次 Trace 抽屉。2026-08-20 自动化 HTTP/DOM/JS 验证已通过，但应用内浏览器没有可用实例，因此没有冒充完成目视验收。M6-A3b 真实 DeepSeek 连续聊天同题评测仍是需要用户提供有效 Key 后执行的独立付费收尾项。

完整模型结论见 [M5-B3 DeepSeek 最终评测报告](M5-B3-DeepSeek最终评测报告.md)。

## 外部额度约束

未来重试 COROS 自动 FIT URL 获取仍会消耗每日下载额度，执行前必须向用户说明并确认只下载一条活动。聊天默认使用离线模式；界面勾选 DeepSeek 后会把规范化活动摘要、确定性复盘和最近对话发送到官方 API并产生费用，不发送 Provider 原始载荷、外部 ID、坐标或 FIT。M7-D/M7-E 只运行本地合成测试，没有调用外部账户或付费模型。

## 验收命令

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe status
.\.venv\Scripts\runcrew.exe activities review --latest --provider coros
.\.venv\Scripts\runcrew.exe training review --latest --provider coros
.\.venv\Scripts\runcrew.exe agent review --latest --provider coros
.\.venv\Scripts\runcrew.exe eval review-agent --output data\private\evals\m5-baseline.json
.\.venv\Scripts\runcrew.exe eval deepseek-suite --help
.\.venv\Scripts\runcrew.exe eval running-chat --output data\private\evals\running-chat-offline-v1.0.json
.\.venv\Scripts\runcrew.exe eval deepseek-chat-suite --help
.\.venv\Scripts\runcrew.exe eval coach-agent --output data\private\evals\coach-agent-v1.0.json
.\.venv\Scripts\runcrew.exe eval memory --output data\private\evals\memory-manager-v1.0.json
.\.venv\Scripts\runcrew.exe cycle --help
.\.venv\Scripts\runcrew.exe recovery assess --help
.\.venv\Scripts\runcrew.exe demo --no-open-browser
```

## 私有本地状态

- 真实数据库：`data/runcrew.db`，已 Git 忽略；
- 私有调试载荷：`data/private/`，已 Git 忽略；
- 虚拟环境：`.venv/`，已 Git 忽略。

不要在普通文档或 Git 中复制其中的真实活动数值、LabelId、位置和坐标。
