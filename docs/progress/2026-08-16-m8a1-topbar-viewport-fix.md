# M8-A1.3a 顶部导航视口稳定性修复

## 1. 问题现象

用户在本机截图中发现顶部全局导航整体向上裁切：品牌主标题、产品导航和右侧状态只显示下半部分。主内容、活动索引和输入区仍能显示，说明问题位于页面根容器与顶栏的视口定位关系，而不是业务数据或组件内容。

## 2. 原因判断

桌面页面原来通过 `topbar: 68px` 与 `workspace: calc(100vh - 68px)` 分别计算高度，但 `body` 本身仍是普通文档流，`html` 也没有锁定根级滚动。浏览器保留非零页面滚动位置时，普通定位的顶栏会随根页面一起离开视口，形成截图中的顶部裁切。

## 3. 修复策略

- 桌面端把 `body` 改成两行网格：固定 `68px` 顶栏与占满剩余空间的工作区；
- `html/body` 在桌面端共同禁止根级滚动，滚动只发生在活动列表、消息区和抽屉内部；
- 顶栏增加 `position: sticky; top: 0`，即使浏览器恢复了旧滚动位置也保持锚定；
- `workspace` 改用网格剩余行，不再独立计算 `100vh - 68px`；
- 720px 以下恢复文档级滚动与块布局，避免移动端被桌面视口锁定；
- CSS/JS 资源版本升级为 `20260816-5`，确保浏览器不会继续使用修复前样式。

## 4. 修改文件

- `src/runcrew/web/static/chat.css`
- `src/runcrew/web/static/chat.html`
- `tests/test_training_operations.py`
- `docs/CURRENT_STATE.md`
- `docs/ROADMAP.md`
- `docs/PROGRESS.md`
- `CHANGELOG.md`

## 5. 验收

```powershell
node --check src\runcrew\web\static\chat.js
.\.venv\Scripts\python.exe -m pytest tests\test_training_operations.py::test_training_ui_assets_and_exported_schemas_are_current tests\test_chat.py::test_chat_api_creates_conversation_and_executes_paid_mode_only_when_requested -q
.\.venv\Scripts\python.exe scripts\verify.py
```

专项测试已通过；全量结果以本阶段最终统一验证为准。测试增加桌面根网格、sticky 顶栏和资源版本断言，防止同类问题回归。

## 6. 已知限制与下一步

当前会话没有可连接的应用内浏览器实例，无法替代用户完成真实窗口的像素级确认。下一步由用户停止旧服务、重新启动并 `Ctrl+F5`，确认顶栏完整显示；通过后继续检查长回答和两个抽屉。

## 7. 数据与外部额度

本次修复只涉及静态布局和测试，没有读取私人活动明细，没有调用 COROS 或 DeepSeek，也没有产生外部费用。
