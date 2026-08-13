# M8-A1 正式产品界面重构

## 1. 本阶段目标

解决原聊天首页更像视觉 Demo、没有正式产品信息架构的问题。在不改动业务 API、数据契约和安全边界的前提下，把已实现的连续对话、证据上下文、多 Agent Coach、人工审核与工程观测组织为一个统一的跑步训练智能工作台。

参考对象不是某一套配色，而是 Waku Agent 等 Agent 工作台将聊天、运行过程、工具/数据和观测能力放进同一产品壳层的组织方式；同时参考正式企业 Agent 产品对“主工作区、上下文面板、运行状态、人工控制”的分层。没有复制第三方代码或品牌资产。

## 2. 用户可以感知到的结果

- 顶部从宣传式 Header 改为正式产品导航，明确区分智能对话、训练运营和工程观测；
- 左侧成为个人训练空间，统一承载跑步记录、最近对话和本地数据边界；
- 中间保持连续对话为第一主任务，欢迎页解释 Evidence → Review → Response 的处理链；
- 右侧把原先的静态说明改为实时运行检查器，展示活动快照、Agent 协作状态与安全策略；
- 训练运营改为独立运营中心，按计划上下文、身体反馈、联合评估、运行审计四步组织；
- Coach 运行时，主界面同步呈现 Execution、Recovery、Plan 的运行中、完成或跳过状态；
- 桌面、窄屏和移动端具有独立布局规则，并支持减少动态效果偏好；
- 支持 `Ctrl+N` 新建对话、`Esc` 关闭训练运营中心。

## 3. 修改文件

- `src/runcrew/web/static/chat.html`：重建产品导航、三栏工作台、Agent 检查器和训练运营中心语义结构；
- `src/runcrew/web/static/chat.css`：重写设计令牌、组件、消息、抽屉和响应式规则；
- `src/runcrew/web/static/chat.js`：适配新欢迎页并增加 Agent 协作状态、键盘操作与可访问状态；
- `tests/test_training_operations.py`：增加正式工作台、Agent 协作区和运行状态函数的静态回归断言；
- `docs/CURRENT_STATE.md`、`docs/PROGRESS.md`、`CHANGELOG.md`：更新当前事实、阶段索引和变更记录。

## 4. 关键技术与产品决策

### 保留能力，重组信息架构

本次没有做“只展示不存在能力”的界面。所有核心入口继续复用已有 API：活动/会话、聊天消息、训练 bootstrap、check-in、Coach run、查询与 decision。右侧协作状态由真实 Coach 运行结果驱动，不模拟工具调用详情。

### 视觉语言

采用深海军蓝、白、低饱和灰与克制的蓝色操作色，荧光绿只保留为运动品牌识别和健康状态点。弱化夸张阴影、巨大装饰图形与全大写海报感，强调 8/12/16 像素级间距、细边框、状态标签和数据对齐。

### Agent 可观察性分层

用户主界面只展示职责、状态和安全策略；详细 Trace、预算和评测仍进入 `/engineering`。这样既能说明编排发生了什么，又避免普通用户被工程日志淹没。

### 安全与可访问性

继续使用 `textContent` 和 DOM 节点创建，不引入 `innerHTML`。训练运营抽屉增加 `aria-controls` / `aria-expanded`，保留键盘关闭能力；支持 `prefers-reduced-motion`。

## 5. 验收

```powershell
node --check src\runcrew\web\static\chat.js
.\.venv\Scripts\python.exe -m pytest tests\test_training_operations.py::test_training_ui_assets_and_exported_schemas_are_current -q
.\.venv\Scripts\python.exe scripts\verify.py
```

结果：JavaScript 语法通过，专项测试通过，全量 130 项测试通过。另以临时端口启动真实本地服务，首页、CSS 和 chat bootstrap 均返回 HTTP 200，页面包含正式产品标题与 Agent 协作检查器，随后已终止临时进程。

## 6. 已知问题

- 本次会话的应用内浏览器没有可用实例，因此没有声称完成浏览器截图与逐像素验收；需要用户在本机启动后做最终视觉复核；
- 右侧检查器当前呈现 Agent 节点状态，但还没有逐步流式推送 Trace；页面只会在运行开始和响应完成时更新；
- 移动端优先保留活动选择、聊天和训练运营，实时上下文检查器在 1050px 以下隐藏；
- 这仍是只绑定回环地址的本地产品，不等同于已经具备账号、云端部署、监控告警和多租户隔离的公开 SaaS。

## 7. 下一阶段唯一入口

M8-A2：基于已经完成的正式产品面，制作可复现求职演示包，包括系统架构图、训练闭环时序图和无私人数据演示脚本。正式录制或截图前，先完成一次本机视觉复核。

## 8. 数据与外部额度

本阶段没有调用 COROS、DeepSeek 或其他付费 API，没有写入用户活动和训练计划数据；自动化测试只使用合成数据和临时 SQLite。
