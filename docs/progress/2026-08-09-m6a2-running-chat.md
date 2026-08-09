# M6-A2 跑步数据连续对话 MVP

## 1. 本阶段目标

把产品主入口从只读展示页改成用户可以真实选择跑步、发送消息和持续追问的 Agent 聊天工作区；原 Dashboard 保留为工程观测台。

## 2. 用户能感知到的结果

运行 `runcrew demo` 后，用户可以选择一场规范化活动、创建会话、询问完成度/负荷/异常/证据/缺失数据，并在刷新后继续查看本机历史。没有 Key 时使用离线 evidence 回答；本机存在 Key 且用户显式勾选时才调用 DeepSeek。

## 3. 新增与修改文件

- `domain/chat.py`：Conversation、Message、Answer、Usage 和 Turn Result 契约；
- `storage/models.py` / `repositories.py`：两张聊天表和持久化 Repository；
- `policies/chat.py`：离线回答与 DeepSeek JSON 回答 Policy；
- `services/chat.py`：首轮 Review Agent、证据快照、有界历史和回答编排；
- `web/server.py`：聊天 GET/POST API、64 KB 请求上限和 `/engineering` 路由；
- `web/static/chat.*`：三栏跑步对话工作区；
- `tests/test_chat.py`：持久化、连续追问、API、脱敏、模型契约和上下文裁剪测试；
- ADR-0011 与项目状态、架构、安全、路线图、README 同步更新。

## 4. 关键技术决策

- Conversation 固定绑定一个内部 Activity，首次 Agent 结果作为 immutable evidence snapshot；
- 后续轮次只传最近8条消息，单条最多1200字符；
- 模型不读取数据库和 Provider，只接收由 Service 构造的脱敏 JSON；
- 回答必须引用已有 finding 类型，并通过医疗边界校验；
- 默认离线，付费模型必须在页面显式开启；
- 原 Dashboard 不删除，改为 `/engineering` 工程观测入口。

## 5. 验收结果

```text
全量测试：59 passed
JavaScript 语法：chat.js / app.js 均通过
git diff --check：通过
真实外部 API 调用：0
```

## 6. 已知限制

- 尚未做真实 DeepSeek 多轮聊天验收；
- 一个会话不能切换或比较多个 Activity；
- 聊天尚不能补充训练计划；
- 没有对话删除、导出和数据保留期限；
- 没有流式响应，模型回答完成后一次性显示。

## 7. 下一阶段唯一入口

M6-A3 建立无私人数据的多轮聊天评测集，覆盖证据引用、缺数诚实性、历史裁剪、医疗边界、提示注入、费用和失败恢复，然后显式确认一次真实 DeepSeek 合成多轮验收。

## 8. 数据与额度

本阶段自动化测试只使用合成 fixture 和 Mock DeepSeek；没有读取文档外的真实活动值，也没有发起 COROS 或 DeepSeek 请求。会话数据保存在 Git 忽略的本地 SQLite。
