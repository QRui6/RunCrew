# M9-D：聊天待确认 Memory Candidate

## 1. 本阶段目标

让自然语言聊天能够提出受支持的类型化记忆候选，但不能直接写入正式长期偏好；用户必须在原消息下明确确认或拒绝。

## 2. 用户可感知结果

- 输入“以后长跑优先安排在周日”等稳定偏好表达后，原消息下出现候选卡片；
- 卡片明确显示“尚未写入长期记忆”、候选星期和置信边界；
- 点击“确认记住”并再次确认后，候选才转换为正式长期偏好；
- 点击“忽略”、等待七天过期或用新候选替代，都不会写入正式 Memory；
- 临时安排、否定、多星期歧义和不支持的内容不会出现候选；
- 刷新页面后候选状态、原消息引用和正式偏好来源链仍然存在。

## 3. 主要新增与修改文件

- 领域契约：`src/runcrew/domain/memory.py`、`src/runcrew/domain/chat.py`；
- 提取与确认服务：`src/runcrew/services/memory_candidates.py`、`src/runcrew/services/chat.py`；
- 存储：`memory_candidates` 表、`MemoryCandidateRepository`；
- API 与产品：`src/runcrew/web/server.py`、`src/runcrew/web/static/chat.*`；
- Schema：`scripts/export_memory_candidate_schemas.py`、`schemas/memory-candidate/`；
- 测试：`tests/test_memory_candidates.py`；
- 决策：`docs/adr/0024-confirmed-chat-memory-candidate.md`。

## 4. 关键技术决策

- v1 只支持 `preferred_long_run_weekday`，不建立通用文本 Memory；
- 使用高精度确定性规则，临时、否定、歧义表达宁可漏召回也不产生错误候选；
- 候选保存消息 ID 和文本 Hash，不在候选表重复保存用户原文；
- Candidate Hash 固定候选值、来源、规则、置信边界和有效期；浏览器只提交决定与预期 Hash；
- 确认时服务端重算候选 Hash、重读原消息并复用正式偏好确认服务；
- 新候选替代旧 pending 候选，七天未处理自动过期，已结束状态不可反向修改；
- 提取流程不依赖 DeepSeek，LLM 没有候选或正式 Memory 写工具。

## 5. 验收命令与结果

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\python.exe -m pytest tests\test_memory_candidates.py -q
node --check src\runcrew\web\static\chat.js
git diff --check
```

- Memory Candidate 专项：15 passed；
- 全量自动化测试：173 passed；
- Python 编译、5份 Candidate/Chat Schema、JavaScript 语法与差异检查通过；
- 没有读取真实训练数据库、COROS/FIT、Token 或模型密钥，没有调用 DeepSeek。

## 6. 实施中的问题与修复

- 仅比较浏览器传回的 Hash 仍不能防止数据库候选正文被意外改写；确认流程增加服务端 Candidate Hash 重算，并重新读取原始用户消息核对文本 Hash。
- 最初考虑相同值存在 pending 时静默复用旧候选，但新对话中将看不到确认卡；改为每条新的明确表达都生成新候选，并替代旧 pending，保证确认行为始终绑定当前原消息。
- 过期扫描与确认流程最初分别读取一次系统时间，候选在极窄的过期边界上可能得到不同判断；现在一次确认只生成一个时间快照，并同时用于过期结算与正式写入。
- Chat Bootstrap 原本会为会话列表加载全部候选，产生不必要的 N+1 查询和元数据返回；列表 DTO 保持候选为空，只在打开具体会话时加载。
- Plan 页面旧文案写着“普通聊天不会自动写入”，容易被理解为聊天完全没有 Memory 能力；改为“聊天可以提出待确认候选，但不会自动写入”。

## 7. 下一阶段唯一入口

M9-E：建立版本化 Memory Evaluation Suite，固定候选提取、临时/否定拒绝、冲突替代、过期、来源篡改、确认写入和职责召回的可比较指标与 Suite Hash。

## 8. 真实数据与外部额度

本阶段只使用合成活动、临时 SQLite 和离线回答策略；没有访问个人训练数据或任何外部付费服务。
