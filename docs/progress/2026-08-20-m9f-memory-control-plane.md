# M9-F：用户可审计的 Memory 控制面

## 1. 本阶段目标

把已经存在的分层 Memory 从工程能力收束为用户可操作的产品闭环：集中查看系统记住了什么、来源与有效期、当前生命周期、不同 Agent 的读取结果，以及安全地确认、拒绝、停用或标记失效。

## 2. 用户可感知结果

- 顶部新增“记忆档案”，打开时才读取统一总览；
- 总览显示待确认候选、生效偏好、有效周记忆三项统计；
- 候选显示原对话、原话摘要、置信边界和截止时间，可确认或忽略；
- 正式偏好显示来源、生效时间和有效期，可显式停用；
- 周训练记忆显示目标、周次、版本、摘要、确认完成量、来源数量和证据 Hash，可显式标记失效；
- Execution、Recovery、Plan 分别显示选中条数、字符预算、是否注入，以及每条记忆被选中或排除的原因；
- 停用与失效不硬删除，原记录继续用于审计。

## 3. 主要文件

- 领域契约：`src/runcrew/domain/memory_control.py`；
- 聚合服务：`src/runcrew/services/memory_control.py`；
- HTTP 入口：`src/runcrew/web/server.py`；
- 产品界面：`src/runcrew/web/static/chat.html`、`chat.css`、`chat.js`；
- Schema：`scripts/export_memory_control_schemas.py`、`schemas/memory-control/`；
- 测试：`tests/test_memory_control.py`；
- 架构决策：`docs/adr/0026-lazy-memory-control-plane.md`。

## 4. 关键策略与亮点

1. **一个写入事实来源**：控制面只聚合；Candidate 决定、偏好停用和周记忆失效全部复用原服务。
2. **按需读取**：打开抽屉才构建跨目标总览和三个职责 Context，避免拖慢普通聊天。
3. **来源最小化**：候选表不复制正文，DTO 只返回原消息最多240字符摘要，不暴露 Provider 外部 ID 或原始载荷。
4. **可撤销但不抹除**：使用 archived / invalidated 生命周期，而不是硬删除历史依据。
5. **展示真实选择器**：职责可见性直接来自正式 Memory Context Builder，包括预算、Context Hash 所依据的选中结果和 Audit 排除原因。
6. **前端安全**：动态内容全部使用 `textContent` / DOM 节点创建，不使用 `innerHTML`。

## 5. API 与确认边界

```text
GET  /api/memory/overview
POST /api/memory/candidates/{id}/decision
POST /api/memory/preferences/{id}/archive
POST /api/memory/weekly-memories/{id}/invalidate
```

- Candidate 请求只能提交决定与预期 Hash，不能提交候选值；
- Preference archive 与 Weekly invalidation 都要求 `confirmed: true`；
- 浏览器还会在提交前二次确认；
- 原有 `/api/chat` 与 `/api/training` 路径继续兼容。

## 6. 验收结果

```powershell
node --check src\runcrew\web\static\chat.js
.\.venv\Scripts\python.exe -m pytest tests\test_memory_control.py tests\test_training_operations.py -q
.\.venv\Scripts\python.exe scripts\verify.py
```

- 新增3项 Memory 控制面专项测试；
- Memory 控制面与训练运营联合专项13项通过；
- 全量181项测试通过；
- Python 编译、Schema 一致性和 JavaScript 语法检查通过；
- 合成验收数据中 Provider 外部 ID 与 raw payload hash 未进入控制面响应。

## 7. 实施中的问题与处理

- 当前会话的应用内浏览器列表为空，无法完成截图级目视验收；已完成真实本地服务启动、DOM/API/JS 自动化验收，没有把浏览器验收冒充为完成。
- 为浏览器验收创建了隔离合成演示数据库，不读取个人数据库、聊天记录或真实活动；没有调用 COROS、DeepSeek 或产生外部费用。

## 8. 阶段结论与后续唯一入口

M9-A 至 M9-F 已闭合，Memory Manager 阶段完成。后续不再扩展 Memory 类型、向量库或 Agent 角色。

剩余收尾项只有：

1. M8-A1.4 在用户本机完成桌面与移动端目视验收；
2. M6-A3b 在确有需要时，用合成数据完成真实 DeepSeek 连续聊天同题验收。

两项都不阻塞当前项目作为可运行、可演示、可解释的简历项目使用。
