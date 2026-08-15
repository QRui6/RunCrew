# M8-A1.2 克制型视觉系统与静态资源刷新

## 1. 本阶段目标

在 M8-A1.1 两栏信息架构不变的基础上，解决高饱和蓝色、荧光黄绿色、多种状态色和过小字号造成的年轻化、概念化观感，形成更克制、耐看的正式产品视觉与交互反馈。

用户提供的截图仍包含 `PRIVATE BETA`、永久右侧栏、巨型标题和 Evidence 流程图，实际是 M8-A1 旧页面，而不是提交 `47b627e` 后的两栏版。排查发现 `DemoApplication` 在服务启动时一次性读取静态文件，因此旧进程即使返回 `Cache-Control: no-cache`，仍会从内存持续返回旧 HTML/CSS/JS。

## 2. 用户可感知的结果

- 去除荧光黄绿和高饱和亮蓝，改用暖灰背景、炭黑文字/主按钮和低饱和森林绿状态色；
- 品牌跑步符号改为炭黑与象牙白，头像改为中性灰；
- 选中活动使用浅灰绿色而不是亮蓝描边；
- 发送与联合评估统一使用炭黑主按钮，森林绿只表达成功、正常和上下文就绪；
- 正文、活动列表、历史对话、输入框和抽屉文字整体提高字号，减少“为了塞信息而缩小文字”的感觉；
- 增加克制的悬停上浮、按钮按压、欢迎内容进入、消息进入、遮罩淡入、抽屉滑入和 Toast 反馈；
- CSS/JS URL 增加资源版本号，浏览器不会继续复用旧资源；
- 服务改为每次静态资源请求读取当前文件，后续修改 CSS/JS 不再要求反复重启服务。

## 3. 修改文件

- `src/runcrew/web/static/chat.css`：重设颜色、字号、阴影与交互动效；
- `src/runcrew/web/static/chat.html`：为 CSS/JS 添加版本化查询参数；
- `src/runcrew/web/server.py`：静态资源由启动时读入内存改为请求时读取；
- `tests/test_training_operations.py`：增加版本化资源、无荧光色和新设计令牌断言；
- `docs/CURRENT_STATE.md`、`docs/PROGRESS.md`、`CHANGELOG.md`：同步阶段事实。

## 4. 设计策略

### 只保留一个品牌强调色

正式产品面不再同时使用亮蓝、黄绿和绿色。深森林绿只用于导航焦点、轻量链接和正常状态；关键提交按钮使用炭黑，避免整页呈现营销型 SaaS 的高饱和操作色。

### 高级感来自比例与克制

本阶段没有加入渐变、玻璃拟态、大面积阴影或装饰插图。重点是暖灰层次、1 像素边界、统一圆角、可读字号、少量留白和短时长反馈。

### 动效只解释状态变化

内容进入、消息出现和抽屉展开使用 160–320ms 的低幅位移动效；按钮按压只移动 1px。系统继续支持 `prefers-reduced-motion`，用户要求减少动态时会关闭这些效果。

## 5. 旧页面问题与解决方案

原实现把静态资源内容保存在 `DemoApplication._static` 中，服务进程启动后不再读取文件。浏览器即使重新请求，服务端仍返回旧字节。本阶段将 `_static` 改为保存资源对象，`handle()` 每次 GET 时调用 `read_bytes()`；同时 HTML 引用 `/assets/chat.css?v=20260815-3` 与 `/assets/chat.js?v=20260815-3`。

已有旧进程必须再重启一次才能加载这项服务端修复；从此次重启之后，前端静态文件更新可以直接刷新页面查看。

## 6. 验收

```powershell
node --check src\runcrew\web\static\chat.js
.\.venv\Scripts\python.exe -m pytest tests\test_training_operations.py::test_training_ui_assets_and_exported_schemas_are_current tests\test_demo_web.py::test_demo_application_serves_static_ui_and_read_only_json -q
.\.venv\Scripts\python.exe scripts\verify.py
```

结果：JavaScript 语法通过，两个静态资源专项测试通过，130 项全量测试通过。

## 7. 已知限制与下一步

- 应用内浏览器没有可用实例，未声称完成截图和像素级验收；
- 用户需要停止旧进程并重新启动一次，再提供最新两栏版截图；
- 下一步只根据最新截图调整字体、留白和色彩细节，不恢复永久三栏，也不向首页增加工程信息；
- 用户确认视觉基线后进入 M8-A2 求职演示包。

## 8. 数据与外部额度

本阶段没有调用 COROS、DeepSeek 或其他外部服务，没有读取私人活动明细；测试仅使用合成数据和临时 SQLite。
