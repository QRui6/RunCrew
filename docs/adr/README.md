# 架构决策索引

| ADR | 状态 | 决策 |
|---|---|---|
| [ADR-0001](0001-provider-boundary.md) | 接受 | 使用 Provider 隔离外部数据源 |
| [ADR-0002](0002-raw-and-canonical-data.md) | 接受 | 同时保存原始数据与统一 Schema |
| [ADR-0003](0003-partial-sync-success.md) | 接受 | 详情失败不回滚活动列表 |
| [ADR-0004](0004-ephemeral-oauth-token.md) | 接受，临时 | 当前不持久化 OAuth Token |
| [ADR-0005](0005-official-garmin-fit-sdk.md) | 接受 | 使用 Garmin 官方 Python FIT SDK |
| [ADR-0006](0006-deterministic-training-review-skill.md) | 接受 | Skill 只编排确定性训练复盘 |
| [ADR-0007](0007-bounded-review-agent-loop.md) | 接受 | 使用有界动作协议实现单 Agent Loop |
| [ADR-0008](0008-versioned-offline-agent-evaluation.md) | 接受 | 先建立版本化离线评测基线再接入真实 LLM |
| [ADR-0009](0009-deepseek-policy-adapter-boundary.md) | 接受 | DeepSeek 只替换 Policy，并继续由本地 Harness 掌握执行权 |
| [ADR-0010](0010-shared-evaluation-time-budget.md) | 接受 | 确定性 Policy 与网络 LLM 使用同一合理时间预算，且预算属于 Suite Hash |
| [ADR-0011](0011-grounded-chat-snapshot.md) | 接受 | 连续对话固定证据快照，并只传递有界最近历史 |
| [ADR-0012](0012-layered-flexible-chat-grounding.md) | 接受 | 个人事实强制 evidence，通用知识与建议保留表达自由 |
| [ADR-0013](0013-confirmed-plan-change-boundary.md) | 接受 | 激活计划只能通过带版本检查的提案和用户确认变更 |
| [ADR-0014](0014-deterministic-recovery-risk-boundary.md) | 接受 | 恢复 Agent 只能解释确定性风险结果，不能自行诊断或打分 |
| [ADR-0015](0015-deterministic-plan-draft-boundary.md) | 接受 | 计划 Skill 只生成可回放草案或待确认提案参数，不保存或批准 |
| [ADR-0016](0016-confirmed-training-execution-boundary.md) | 接受 | 训练执行先生成候选，只有用户确认后才写入并提升 revision |
| [ADR-0017](0017-coach-orchestrator-handoff-boundary.md) | 接受 | Coach 只做路由，职责节点使用最小类型化交接并在计划变更前暂停 |
| [ADR-0018](0018-replay-before-coach-approval.md) | 接受 | 浏览器只提交决定，批准前服务端重放 Coach 并拒绝过期草案 |
| [ADR-0019](0019-versioned-coach-agent-evaluation.md) | 接受 | 多 Agent 评测复用真实 Harness 与产品审核边界，并建立版本化合成基线 |
| [ADR-0020](0020-confirmed-typed-athlete-preference-memory.md) | 接受 | 长期训练偏好使用类型化、显式确认、版本替代和可追溯写入 |
| [ADR-0021](0021-isolated-synthetic-demo-database.md) | 接受 | 求职演示使用隔离、显式重置且不预置 Agent 结论的合成数据库 |

新 ADR 使用四位编号，必须记录背景、决策、原因、后果和替代方案。
