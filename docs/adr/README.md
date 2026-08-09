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

新 ADR 使用四位编号，必须记录背景、决策、原因、后果和替代方案。
