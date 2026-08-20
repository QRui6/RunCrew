# RunCrew 简历条目

## 推荐三行版

**RunCrew：基于真实跑步数据的可审计多智能体训练运营系统**｜个人项目｜2026.08—至今  
*Python · Pydantic · SQLAlchemy · SQLite · MCP · DeepSeek Tool Calls · JavaScript*

- 接入 COROS OAuth 2.0 + PKCE/MCP 与 Garmin FIT SDK，以 Provider 隔离厂商协议并统一 Activity Schema；设计“详情—分圈—FIT—摘要”分级降级和幂等同步，保证外部详情失败时仍保留可用活动事实。
- 围绕“计划—执行—反馈—调整”构建 Execution / Recovery / Plan 三职责 Agent 与 Coach Harness，通过最小类型化 Handoff、工具白名单、预算/超时/重试、Trace 和人工确认约束协作；计划批准前由服务端重放并校验 `input_hash + revision`，阻止过期草案覆盖新状态。
- 建立版本化评测与回归体系：单 Agent 确定性 Policy 和真实 DeepSeek 在同一 Suite Hash 下均为12/12，多 Agent 确定性 Harness 基线18/18，覆盖权限、故障恢复、Schema、事实血缘和 stale 审核，项目全量153项自动化测试通过。

## 更紧凑的两行版

**RunCrew｜可审计多智能体训练运营系统**：基于 COROS MCP/FIT 真实跑步数据构建计划—执行—恢复—调整闭环，以 Execution / Recovery / Plan 职责隔离、类型化 Handoff、工具权限、Trace、预算和人工确认约束 Agent；计划写入前执行服务端重放及 Hash/revision 校验。  
构建版本化合成评测，单 Agent 确定性 Policy 与真实 DeepSeek 同 Hash 均12/12，多 Agent 确定性 Harness 18/18，全量153项自动化测试通过。

## 面向不同岗位的微调

### Agent / 应用算法岗位

优先保留第二、第三条；技术栈突出 `DeepSeek Tool Calls、Context Engineering、Harness、Evaluation`。

### Python 后端岗位

优先保留第一、第二条；技术栈突出 `Python、Pydantic、SQLAlchemy、SQLite、OAuth 2.0、MCP`，面试补充状态机、幂等和重放。

### AI 全栈岗位

保留三条，在第二条末尾补充“提供本地连续对话与训练审核网页”，但不要把原生 JavaScript 页面写成 Vue/React，也不要写 FastAPI——当前项目没有使用这些框架。

## 不建议写进简历的表述

- “准确率100%”：不同评测指标不能被合并成通用准确率；
- “真实多智能体大模型评测18/18”：18/18评测的是确定性 Coach Policy；
- “生产级”“高并发”“服务大量用户”：没有相应部署和压测证据；
- “AI 自动修改训练计划”：正式写入需要用户批准，且服务端会先重放；
- “伤病诊断 Agent”：Recovery 只是保守的训练风险规则，不是医疗诊断；
- “RAG/向量记忆”：当前长期偏好使用类型化 SQLite 记忆，并未引入向量检索。
