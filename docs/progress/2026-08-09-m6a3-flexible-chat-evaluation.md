# M6-A3 自由对话契约与多轮评测

## 1. 本阶段目标

解决 M6-A2“所有回答都围绕三类 finding，过于死板”的问题：个人数据事实继续严格引用 evidence，同时允许自然解释、假设讨论、通用跑步知识、训练思路和澄清问题。

## 2. 用户能感知到的结果

聊天回答现在会标识“个人数据分析、数据＋训练思路、通用跑步知识、需要补充信息、安全边界”。正文可以自然展开；界面额外显示数据事实、数据推断、通用知识和可选建议标签，并把模型给出的后续问题变成可点击按钮。

## 3. 新增与修改文件

- `domain/chat.py`：五种回答模式、四类论断与分层 evidence 校验；
- `policies/chat.py`：自由但有依据的 Prompt、扩展离线策略、失败用量记录；
- `storage/repositories.py`：在既有 JSON 元数据中兼容持久化新回答结构；
- `evaluation/chat.py` 与 `domain/chat_evaluation.py`：多轮评测执行器、指标和报告；
- `evals/running_chat/`：7场景8轮 v1.0 Suite 和 JSON Schema；
- `cli.py`：`running-chat` 离线基线与受费用门保护的 `deepseek-chat-suite`；
- `web/static/chat.*`：回答模式、论断标签和可点击追问；
- `tests/test_chat_evaluation.py`：套件、回放、过度 grounding 退化、CLI 安全门和 Suite 不变性测试。

## 4. 关键技术决策

- 正文自由，关键个人事实/推断严格；
- 通用知识和训练建议不强制引用个人数据；
- 数据分析与混合建议必须至少包含一条合法个人 evidence 论断；
- 同一套题分别统计 grounding、openness、safety、schema；
- DeepSeek 无效回答即使最终被拒绝，已返回的 Token 和估算费用仍计入失败遥测；
- 旧聊天消息无需数据库迁移，可从原 evidence 元数据兼容恢复。

## 5. 当前验收结果

```text
自动化测试：66 passed
running-chat-eval/1.0：7 cases / 8 turns
离线基线：8/8，grounding/openness/safety/schema 均为100%
Suite Hash：ab097079836d0fa2c1227da0e84dfa32be5bd40538d15e52c47d2580d265fe94
真实 DeepSeek 调用：0（当前进程和用户/机器环境均未读取到新 Key）
```

## 6. 已知限制

- 真实 DeepSeek 8轮同题评测尚未执行，本阶段仍处于进行中；
- 当前“回答自然度”只用最低长度、模式和论断多样性做结构化代理指标，尚无人工偏好评分；
- 提示注入用例检查输出模式与事实契约，不等价于全面红队测试；
- 通用跑步知识的事实正确性尚未接入独立知识评测集。

## 7. 下一阶段唯一入口

在新的 `DEEPSEEK_API_KEY` 可被当前开发进程读取后，运行完整合成聊天 Suite，报告写入 `data/private/evals/running-chat-deepseek-v1.0.json`；审核8轮通过率、模式分布、Token、费用和失败原因，再决定是否完成 M6-A3。

## 8. 数据与额度

离线评测只使用固定合成十公里活动，不含用户真实活动、位置、外部 ID 或 FIT。本次尚未产生外部模型费用。
