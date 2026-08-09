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

当前使用确定性 Policy 验证 Harness 和 Loop；真实 LLM Policy、Token/费用预算和模型评测尚未实现，不能在面试中声称已经完成模型自主决策。

## M5：单 Agent 评测与真实 LLM Policy

状态：**进行中（M5-A 已完成；M5-B 选型方案已完成）**

验收：

- [x] 12 个不含私人数据的离线回放场景；
- [x] 完成率、护栏、Schema、事实一致性、工具调用、重试和延迟指标；
- [x] 版本化 Suite/Report Schema、`suite_hash` 和私有报告；
- [x] 核对 DeepSeek 官方能力并形成 `deepseek-v4-flash` 非思考模式接入方案；
- [ ] 一个实现 M4 Action Schema 的真实 LLM Policy；
- [ ] Mock 适配器契约测试和单次合成数据 API Smoke Test；
- [ ] Token、费用和动作解析错误指标；
- [ ] 与确定性 Policy 基线对照；
- [ ] 多 Agent 决策记录。

只有评测证明职责冲突、上下文负担或权限边界无法由单 Agent 稳定处理时，才增加训练分析、恢复分析或风险审查 Agent；否则继续保持单 Agent。

## M6：界面与简历材料

状态：**待开始**

验收：

- 可演示界面；
- 架构图与 Trace；
- 简历描述、项目难点和量化结果。
