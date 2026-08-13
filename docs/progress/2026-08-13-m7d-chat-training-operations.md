# M7-D 聊天产品训练闭环

日期：2026-08-13
状态：完成

## 1. 本阶段目标

把训练目标、激活计划、每日身体反馈、Coach 跨职责运行和用户审核接入现有连续对话产品，使用户无需在多个 CLI 之间手动搬运 JSON，同时不削弱 M7-A/M7-C 的权限与确认边界。

## 2. 用户能感知到的结果

启动：

```powershell
.\.venv\Scripts\runcrew.exe demo
```

在聊天页面点击“训练闭环”后可以：

1. 选择激活训练目标和活动来源；
2. 查看激活计划、revision 和本周计划课；
3. 填写疲劳、酸痛、睡眠、疼痛部位、急性症状和备注；
4. 运行 Execution → Recovery → 必要时 Plan 的 Coach 工作流；
5. 查看每个职责节点的结果和待审核计划草案；
6. 明确批准或拒绝；
7. 页面刷新后从最近运行中恢复待审核状态；
8. 数据或计划变化时看到 `stale`，而不是让旧建议覆盖新计划。

## 3. 新增/修改文件

- `src/runcrew/domain/training_operations.py`：产品 DTO、提交契约、Coach Run Audit 与审核结果；
- `src/runcrew/services/training_operations.py`：训练运营产品服务、Coach 执行和重放批准；
- `src/runcrew/storage/models.py`：新增 `coach_runs` 审计表；
- `src/runcrew/storage/repositories.py`：Coach Run 保存、查询和最近运行；
- `src/runcrew/web/server.py`：训练 bootstrap、check-in、Coach run、查询和 decision API；
- `src/runcrew/web/static/chat.html/css/js`：训练闭环抽屉和交互；
- `schemas/training-operations/` 与导出脚本：六个产品 API Schema；
- `tests/test_training_operations.py`：服务、存储、API、安全和静态资源集成测试；
- `docs/adr/0018-replay-before-coach-approval.md`：批准前重放决策。

## 4. 核心策略与亮点

### 一个产品，两类交互

跑步活动聊天仍负责自由提问；训练闭环抽屉负责结构化的目标、反馈、Coach 和审核。没有把敏感写入动作伪装成普通自然语言，也没有另造一个只供演示的 Dashboard。

### 浏览器零 patch 权限

Decision Schema 使用 `extra=forbid`，只接受 `approve/reject + comment`。浏览器无法提交距离、时长、课型或 revision。服务端从已验证 Coach 结果取得草案。

### 批准前重放

批准不是直接套用历史输出。系统用原始请求重跑 Coach，对比新的 Planning input hash 和完整草案；活动、反馈或计划任何变化都会产生 `stale`。通过后仍由 `TrainingCycleService` 创建提案、校验 revision 并应用。

### 可恢复审计

`coach_runs` 保存请求、结果、workflow hash、planning hash、状态、proposal ID 和决定时间。刷新页面不会丢失待确认节点，最近运行可重新打开。

## 5. 验收与测试

新增8项测试覆盖：

- bootstrap 只返回规范化训练状态，不泄露 Provider 外部 ID 或 raw hash；
- 身体反馈按激活目标保存；
- Coach 运行持久化但不创建提案、不修改 revision；
- 批准前重放后应用并提升 revision；
- 拒绝不创建或应用提案；
- 计划变化使历史草案 stale；
- API 端到端和客户端 patch 注入拒绝；
- 页面入口、审核动作、DOM 安全与六份导出 Schema 防漂移。

JavaScript 通过：

```powershell
node --check src\runcrew\web\static\chat.js
```

项目统一验收结果记录在 `CURRENT_STATE.md`。

## 6. 实施中的问题

应用内浏览器插件在本次会话中没有可用实例，按 Browser 技能故障流程检查后列表为空。因此没有声称完成视觉点击验收；本阶段使用 HTTP API 集成、静态 HTML/JS 断言、DOM 安全检查、响应式 CSS 审阅和 JavaScript 语法检查。后续可由用户启动 `runcrew demo` 做本机视觉复核。

## 7. 已知限制

- 目标和训练计划的首次创建仍通过 CLI；页面只管理既有激活目标；
- 暂不在普通聊天文本中自动识别“帮我降级课表”并触发写入，避免隐式副作用；
- Coach Run Trace 已持久化在结果 JSON 中，但页面目前只展示三个节点摘要；
- 页面没有 Coach Run 删除、导出或保留期限功能；
- 未完成应用内浏览器视觉点击验收；
- 多 Agent 的版本化冲突与故障评测仍待 M7-E。

## 8. 下一阶段唯一入口

**M7-E：建立版本化 Coach Evaluation Suite，量化跨节点任务完成、权限、交接一致性、stale、故障恢复和确定性回放。**

## 9. 数据与外部额度

实现和自动化测试只使用本地合成数据，没有读取用户真实活动，没有调用 COROS 或 DeepSeek，也没有产生外部费用。
