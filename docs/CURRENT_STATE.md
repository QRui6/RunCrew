# 当前状态

> 本文件是项目当前进度的唯一事实来源。任何 AI 开始工作时必须先读本文件。  
> 最后更新：2026-08-13

## 当前里程碑

**M5 与 M6-A1/A2/A3a 已完成；真实 DeepSeek 聊天同题验收仍待新 Key。M7-A 训练闭环基础与 M7-B1/B2 恢复风险、训练计划 Skill 已完成，下一步是 M7-B3 训练执行对照 Skill。**

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

- Python 3.13 本地环境可运行；
- 自动化测试：95 passed；
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
- `/engineering` 工程观测台可以筛选 Provider、设置可选训练目标并回放确定性 Agent，展示 activity、evidence、预算、Trace 和 Same-Hash 评测对照；
- 工程观测 API 只接受 GET；聊天 API 提供受限 POST 并写入本地会话，两者均不返回外部活动 ID、raw payload、坐标或 Token；
- 本机真实 COROS 规范化数据只读验收通过：活动可用、Agent succeeded、3条 finding、9个 Trace 事件、Same-Hash 成立；
- M6-A1 自动化测试曾增至56项，覆盖 Dashboard 数据脱敏、Agent 回放、静态资源、API 参数、只读方法、缺失数据库不落盘和 CLI 入口。
- 产品根页面已经改为跑步数据连续对话工作区，原 Dashboard 保留为 `/engineering` 工程观测台；
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

## 当前已知限制

- `getActivityDetail` 异常；
- `queryActivityLapData` 返回相同异常；
- `queryActivityFitFileDownloadUrls` 在参数符合实时 schema 的情况下返回 `isError=true`，没有下发下载 URL；
- 自动 FIT URL 未能验证，但用户手动导出的真实 FIT 已通过私有缓存完成端到端验收；
- 当前 COROS 规范化活动没有训练负荷字段，因此真实 `load_change` 暂时可能为 `unknown`；
- 训练目标、周计划和主观反馈已经持久化，计划草案可由 CLI 生成，但尚未接入聊天界面，也不会自动匹配实际 Activity；
- 恢复风险阈值是 RunCrew 保守工程规则，不是临床决策；无训练负荷时的时长代理不能表示强度差异；
- Recovery 与 Plan Skill 已能确定性串联，但 Recovery Agent、Plan Agent 和 Coach Orchestrator Harness 尚未实现，不能声称已有多 Agent 协作；
- 计划 v1 主要按时长规划，不处理比赛周、天气、海拔、力量训练或精确配速区间；5%增量和60%降级是保守工程规则；
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

**M7-B3：实现训练执行对照 Skill。**

该 Skill 把计划课与实际 Activity 建立可审计匹配，输出完成、部分完成、跳过或无法匹配，并保留用户人工纠正入口。完成后再用 Harness 连接 Recovery Agent、Plan Agent 与执行对照，形成第一个可评测的训练运营闭环。M6-A3b 真实 DeepSeek 8轮评测仍待新 Key，不阻塞本地确定性业务建设。

完整模型结论见 [M5-B3 DeepSeek 最终评测报告](M5-B3-DeepSeek最终评测报告.md)。

## 外部额度约束

未来重试 COROS 自动 FIT URL 获取仍会消耗每日下载额度，执行前必须向用户说明并确认只下载一条活动。聊天默认使用离线模式；界面勾选 DeepSeek 后会把规范化活动摘要、确定性复盘和最近对话发送到官方 API并产生费用，不发送 Provider 原始载荷、外部 ID、坐标或 FIT。M7-B2 只运行本地合成测试并查阅公开资料，没有调用外部账户或付费模型。

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
.\.venv\Scripts\runcrew.exe cycle --help
.\.venv\Scripts\runcrew.exe recovery assess --help
.\.venv\Scripts\runcrew.exe demo --no-open-browser
```

## 私有本地状态

- 真实数据库：`data/runcrew.db`，已 Git 忽略；
- 私有调试载荷：`data/private/`，已 Git 忽略；
- 虚拟环境：`.venv/`，已 Git 忽略。

不要在普通文档或 Git 中复制其中的真实活动数值、LabelId、位置和坐标。
