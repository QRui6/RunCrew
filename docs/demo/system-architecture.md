# RunCrew 系统架构图

```mermaid
flowchart TB
    U[跑步用户]

    subgraph Product[本地产品层 · 127.0.0.1]
        Chat[连续对话工作区]
        Ops[训练闭环]
        Eng[工程观测台]
    end

    subgraph Application[应用与上下文层]
        ChatService[Chat Service<br/>Evidence Snapshot + 最近8条消息]
        TrainingOps[Training Operations Service<br/>目标 / 计划 / 执行 / Check-in / 审核]
        Memory[Memory Manager<br/>偏好确认 / 周结算 / 版本 / 失效]
        Context[Role-scoped Context Builder<br/>字段投影 / 固定预算 / 双 Hash 审计]
    end

    subgraph Agent[Agent 工程层]
        ReviewHarness[Review Agent Harness<br/>Action-Observation Loop]
        CoachHarness[Coach Orchestrator Harness<br/>Execution → Recovery → Plan]
        Guard[权限 / 预算 / 重试 / 超时<br/>确认 / Trace / Schema]
    end

    subgraph Skills[确定性 Skill 与领域服务]
        Review[Training Review]
        Execution[Execution Compare]
        Recovery[Recovery Assessment]
        Planning[Plan Draft / Adjustment]
    end

    subgraph Data[本地事实与审计]
        SQLite[(SQLite<br/>Activity / Conversation / Cycle / Memory / Run)]
        Eval[版本化 Evaluation<br/>Suite Hash + 故障注入]
    end

    subgraph Provider[外部数据边界]
        Adapter[ActivityProvider]
        Coros[COROS OAuth + MCP]
        Fit[FIT Parser + 私有缓存]
        Fixture[合成 Fixture]
    end

    U --> Chat
    U --> Ops
    Chat --> ChatService
    Ops --> TrainingOps
    Eng --> SQLite
    Eng --> Eval

    ChatService --> Context
    TrainingOps --> Context
    TrainingOps --> Memory
    Memory --> SQLite
    Memory --> Context
    Context --> ReviewHarness
    Context --> CoachHarness
    ReviewHarness --> Guard
    CoachHarness --> Guard
    Guard --> Review
    Guard --> Execution
    Guard --> Recovery
    Guard --> Planning

    Review --> SQLite
    Execution --> SQLite
    Recovery --> SQLite
    Planning --> SQLite
    Eval -.同题回放.-> ReviewHarness
    Eval -.故障注入.-> CoachHarness

    SQLite --> Adapter
    Adapter --> Coros
    Adapter --> Fit
    Adapter --> Fixture
```

## 面试讲解顺序

1. 最下面是数据可信边界：外部格式先经过 Provider 和 Parser 变成统一 Activity；
2. 中间是确定性 Skill：计算、阈值、缺失数据和 evidence 不交给 LLM；
3. Harness 掌握工具白名单、确认、预算、超时、Trace 和终态，Policy 只有建议权；
4. 应用层按职责裁剪 Context：Execution 不读记忆，Recovery 只读周聚合，Plan 读取偏好和训练基线；`context_hash` 约束业务输入，`audit_hash` 记录完整选择过程；
5. 产品层只展示可操作流程，工程观测台单独展示 Trace 与评测证据；
6. Evaluation 复用真实 Harness，而不是为测试重写一套模拟流程。
