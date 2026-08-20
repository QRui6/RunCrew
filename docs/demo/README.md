# RunCrew 求职演示包

这套演示只使用程序生成的合成活动、目标、计划、身体反馈和长期偏好，不读取 `data/runcrew.db`、真实 COROS/FIT 或 DeepSeek Key。

## 一键准备

```powershell
cd D:\AgentProjets\RunCrew
.\.venv\Scripts\runcrew.exe demo-seed --reset
.\.venv\Scripts\runcrew.exe demo --db data\private\demo\runcrew-demo.db
```

浏览器打开 `http://127.0.0.1:8766`。演示数据库位于 Git 忽略的 `data/private/demo/`，与个人真实数据库隔离。

## 材料导航

| 材料 | 用途 |
|---|---|
| [系统架构图](system-architecture.md) | 解释 Provider、Domain、Skill、Harness、Memory、Trace 和 Evaluation 如何分层 |
| [训练闭环时序图](training-loop-sequence.md) | 解释用户确认、Agent 协作和计划重放发生在什么位置 |
| [5分钟演示脚本](five-minute-demo-script.md) | 按固定顺序完成可重复现场演示 |

## 演示数据包含什么

- 8条无坐标、无真实账号标识的合成跑步活动；
- 1个十公里训练目标；
- 1份当前周激活计划和1条已确认活动匹配；
- 1份上一周正式计划及其版本化周训练记忆；
- 1条无急性红旗、但恢复状态偏低的合成 Check-in；
- 1条明确确认的“周日长跑”长期偏好；
- 0个预置对话和0个预置 Coach 结论，关键 Agent 结果在现场真实运行。

每次演示前重新执行 `demo-seed --reset`，可以消除上一次对话、审核和计划修改造成的状态漂移。

## 证据边界

演示时可以声明：

- 数据、计划、Memory、Agent Harness 和网页闭环均在本地真实运行；
- 训练判断来自确定性 Service/Skill，回答可追溯到 evidence；
- Execution、Recovery、Plan 三个职责由 Harness 按权限编排；
- 计划和长期偏好写入需要用户确认；
- 当前全量153项自动化测试通过；周训练记忆专项测试覆盖知识截止、确认边界、版本替代、失效与 Planning 消费。

演示时不能声明：

- 合成数据证明了真实用户效果；
- 当前 Coach 已完成真实 LLM 多 Agent 稳定性验证；
- 恢复风险是医学诊断；
- 本地费用门能够替代模型供应商账户额度；
- 系统已经过生产级并发或大规模用户验证。
