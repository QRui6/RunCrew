# 开发路线图

## 状态说明

- `完成`：代码、测试、验收和文档均完成；
- `进行中`：已经开始实现；
- `待开始`：尚未开始；
- `受阻`：存在明确外部阻塞。

## M0：COROS 接入 Spike

状态：**完成**

验收：

- 官方 MCP 连通；
- OAuth 元数据发现；
- PKCE 授权成功；
- MCP initialize 成功；
- 22 个工具发现；
- 四项真实只读工具调用成功。

## M1：真实数据竖切

状态：**完成**

验收：

- 独立 Python 项目；
- Domain Schema；
- Provider 协议；
- SQLite 三张核心表；
- fixture 幂等同步；
- COROS 活动列表真实同步；
- 确定性 summary 复盘；
- 详情失败不回滚列表；
- 9 项测试通过；
- AI 项目记忆文件齐全。

## M2：FIT 详情兜底

状态：**完成**

验收：

- [x] 只使用一条真实 FIT 验收：COROS URL 工具失败后，由用户从 App 手动导出并放入私有缓存；
- [x] 确定性解析 session/lap/record；
- [x] 生成 `ActivityDetail`；
- [x] 能生成带分圈证据的真实活动复盘；
- [x] 有不含位置的合成 FIT fixture；
- [x] 处理下载额度、缓存、超时和过期 URL；
- [x] FIT 失败仍保留 summary。

## M3：Training Review Skill

状态：**完成**

目标：把单次活动和最近训练历史转为可复用 Skill，而不是直接写入 Prompt。

验收：

- [x] 明确输入/输出 Schema；
- [x] 训练完成度、负荷变化、异常点均带 evidence；
- [x] 缺失数据有降级策略；
- [x] 同一输入可回放；
- [x] 规则与 LLM 职责分离。

## M4：Context + Harness + Loop

状态：**完成**

验收：

- [x] 分层上下文；
- [x] 工具权限与确认；
- [x] 状态机；
- [x] 重试、超时、预算和退出条件；
- [x] Trace；
- [x] 故障注入；
- [x] Agent 输出可验证。

默认业务 CLI 仍使用确定性 Policy；DeepSeek 已完成 v1.1 同 Hash 的12场景对照。当前结论限于一个工具、两种动作的单 Agent 协议，不能扩展成复杂规划或生产稳定性声明。

## M5：单 Agent 评测与真实 LLM Policy

状态：**完成**

验收：

- [x] 12 个不含私人数据的离线回放场景；
- [x] 完成率、护栏、Schema、事实一致性、工具调用、重试和延迟指标；
- [x] 版本化 Suite/Report Schema、`suite_hash` 和私有报告；
- [x] 核对 DeepSeek 官方能力并形成 `deepseek-v4-flash` 非思考模式接入方案；
- [x] 一个实现 M4 Action Schema 的 `DeepSeekReviewPolicy` 适配器；
- [x] Mock 适配器契约、安全和评测聚合测试；
- [x] Token、模型调用、API 尝试、动作解析错误和模型耗时指标结构；
- [x] 受显式确认与费用上限保护的单次合成数据 Smoke 命令；
- [x] 带价格版本的本地费用估算和后验停止门；
- [x] 使用真实 DeepSeek API 完成一次成功的合成数据 Smoke；
- [x] 验证真实 API 鉴权、非思考模型、首轮 Tool Call、Token 和费用返回；
- [x] 第一次真实失败时由 Harness 阻止重复工具执行；
- [x] 使用标准 assistant/tool 消息链复验并得到 `succeeded / completed`；
- [x] 增加完整 Suite 命令和跨用例共享的总费用停止门；
- [x] 第一次运行完整 12 场景 DeepSeek Suite，12/12 满足预期；
- [x] 发现并修复 CLI 改写用例超时导致 Suite Hash 漂移的问题；
- [x] 使用原始 v1.0 Suite 复跑并取得相同 Hash，确认1秒总预算导致9个网络模型场景超时；
- [x] 升级 `review-agent-eval/1.1`，为全部 Policy 统一设置15秒总预算并建立12/12确定性基线；
- [x] 被总超时取消的模型请求记录已发起尝试，未知 usage 不伪造 Token 或费用；
- [x] 使用 v1.1 Suite 复跑 DeepSeek 并取得相同 `suite_hash`；
- [x] 与确定性 Policy 基线对照：双方12/12，模型额外产生Token、费用和网络延迟；
- [x] 多 Agent 决策记录：当前无评测证据支持拆分，继续保持单 Agent。

只有评测证明职责冲突、上下文负担或权限边界无法由单 Agent 稳定处理时，才增加训练分析、恢复分析或风险审查 Agent；否则继续保持单 Agent。

## M6：连续对话界面

状态：**进行中（M6-A1、M6-A2 已完成）**

验收：

- [x] M6-A1：本地工程观测台集中展示 Activity、Skill evidence、Agent Trace 和模型评测对照；
- [x] M6-A1：只绑定回环地址、观测 API 只读且浏览器字段脱敏；
- [x] M6-A2：选择活动、创建会话、发送消息和连续追问的产品聊天界面；
- [x] M6-A2：会话/消息/证据快照 SQLite 持久化和最近 8 条消息上下文窗口；
- [x] M6-A2：离线证据回答和显式 DeepSeek JSON 回答契约；
- [x] M6-A3a：分层自由回答契约、7场景8轮聊天 Suite 与8/8离线基线；
- [ ] M6-A3b：一次显式付费的完整合成 DeepSeek 8轮同题验收（等待新 Key 可被当前进程读取）；
- [ ] M6-A3b：真实 DeepSeek 同题评测保留为待补模型验收，不再阻塞训练闭环建设；

## M7：多智能体训练运营闭环

状态：**完成**

目标不是堆叠角色，而是让不同职责的 Agent 围绕同一个训练状态协作，并由 Harness 管理权限、冲突、确认、失败和回放。

- [x] M7-A：训练目标、周计划、主观反馈、变更提案和用户确认的领域模型；
- [x] M7-A：激活计划不可直接修改，提案使用 `base_revision` 防止旧建议覆盖；
- [x] M7-A：五张 SQLite 表、Repository、Service 状态机和 `runcrew cycle` CLI；
- [x] M7-B1：确定性的恢复与风险评估 Skill；
- [x] M7-B2：确定性的训练计划草案与调整 Skill；
- [x] M7-B3：训练执行对照 Skill，连接计划课与实际 Activity；
- [x] M7-C：Coach Orchestrator 编排训练执行、恢复和计划职责，提供最小交接、权限、预算、Trace 与确认中断；
- [x] M7-D：把目标、每日反馈、Coach 运行与重放审核接入聊天产品；
- [x] M7-E：18场景版本化多 Agent 任务、冲突、越权、故障恢复、事实/血缘、确认和 stale 评测。

## M8：演示与求职材料

状态：**进行中**

- [x] M8-A1：正式产品界面重构与首屏信息架构收敛；
- [x] M8-A1.3：以训练索引、活动刊号、连续指标带、训练笔记和证据脚注建立 RunCrew 独有的编辑式产品视觉；
- [x] M8-A1.3a：桌面根容器固定为顶栏＋工作区两行布局，修复浏览器恢复滚动位置时顶部导航被裁切；
- [x] M8-A1.3b：允许侧栏和聊天区在剩余视口内正确收缩，保证输入区与隐私 footer 完整落入底部边界；
- [x] M8-B：闭合网页自助训练链路，支持目标创建、计划草案重放确认、今日训练、活动匹配确认、跑后反馈、Agent 调整审核和周总结；
- [ ] M8-A1.4：在本机完成桌面首屏、长回答、回答依据和训练闭环抽屉的主观视觉验收（不阻塞 M8-A2）；
- [x] M8-A2：架构图、训练闭环时序图与无私人数据演示脚本；
- [x] 可重复演示脚本；
- [x] M8-A3：简历描述、项目难点、量化结果、面试追问清单与仓库证据映射。

## M9：可审计 Agent Memory Manager

状态：**进行中（M9-A、M9-B、M9-C 已完成；下一步进入 M9-D）**

- [x] M9-A：类型化 `preferred_long_run_weekday` 长期偏好；
- [x] M9-A：显式确认、重复提交幂等、`superseded / expired / archived` 生命周期和来源追踪；
- [x] M9-A：Planning Agent 消费偏好，目标设置优先，偏好进入 `input_hash + evidence`；
- [x] M9-A：网页和 CLI 管理入口、JSON Schema 与专项测试；
- [x] M9-B：从计划、执行确认和 Check-in 确定性生成版本化 Weekly Training Memory；
- [x] M9-C：按职责构建 Memory Context，记录选中/排除记忆和上下文预算；
- [ ] M9-D：聊天只生成待确认 Memory Candidate，不允许 LLM 直接写入；
- [ ] M9-E：版本化 Memory Evaluation，覆盖召回、冲突、过期、来源和无关记忆注入；
- [ ] 只有评测证明结构化检索不足时，才评估向量数据库。
