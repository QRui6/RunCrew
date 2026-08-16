# M8-A1.3b 底部工作区边界修复

## 1. 问题现象

顶部导航修复后，用户的第二张本机截图显示底部输入框、发送按钮和左侧隐私说明没有完整落入视口，最后一部分被工作区底边裁掉。截图同时证明新版顶栏已经完整显示，因此这是独立的内部布局收缩问题。

## 2. 原因判断

根页面已经固定为“顶栏＋工作区”两行，但工作区内部的左右两个网格子项仍保留默认 `min-height: auto`。这会让侧栏内容和聊天区内容以自身固有高度参与网格计算，而不是在剩余行内收缩。左侧 footer 还允许 Flex 默认收缩，主区则使用 `height: 100%`，两者共同导致底部内容超出实际可用高度后被裁切。

## 3. 修复策略

- `workspace` 明确隐藏外层溢出，内部滚动由具体列表与消息区负责；
- `rail` 和 `chat-stage` 增加 `min-height: 0`，允许它们在根网格剩余行内正确收缩；
- `chat-stage` 去除 `height: 100%`，直接使用父网格分配的高度；
- 顶栏、开始新对话按钮和隐私 footer 禁止 Flex 收缩，把有限高度让给活动和对话列表；
- 输入区成为聊天网格明确的最后一行，并为系统安全区保留底部 padding；
- 资源版本升级到 `20260816-6`，防止修复前 CSS 继续命中缓存。

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

专项测试通过，并增加工作区溢出、聊天四行网格、安全区 padding 和资源版本断言。全量结果以本阶段最终统一验证为准。

## 6. 已知限制与下一步

当前没有可连接的应用内浏览器实例，因此最终像素确认仍由用户在本机完成。用户需要 `Ctrl+F5` 后确认输入框完整边框、发送按钮、底部免责声明和左侧隐私说明全部可见。

## 7. 数据与外部额度

本次只修改静态布局与契约测试，没有读取私人活动明细，没有调用 COROS、DeepSeek 或其他外部服务。
