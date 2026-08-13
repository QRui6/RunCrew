# ADR-0019：多 Agent 评测复用真实 Harness 与产品审核边界

状态：接受

日期：2026-08-13

## 背景

M7-C 已有 Execution、Recovery、Plan 三个职责节点和 Coach Orchestrator，M7-D 已将草案审核接入本地产品。单元测试能证明单个分支，但不能回答整套跨节点流程在正常、故障、越权、血缘篡改和计划状态变化下是否稳定，也不能生成可比较的版本化指标。

## 决策

1. `coach-agent-eval/1.0` 直接运行真实 `CoachOrchestratorHarness`，不复制一套评测专用状态机；
2. Harness 场景只替换无私人数据的类型化节点结果，或注入瞬时失败、超时、非法 Schema、越权输出与 Policy 动作；
3. 批准前状态漂移场景使用临时 SQLite 和真实 `TrainingOperationsService`，验证重放、revision 与 stale 边界；
4. Suite 固定版本与 `suite_hash`，报告聚合任务、韧性、护栏、审核、Schema、事实、血缘、确认边界、节点调用和延迟；
5. 护栏场景额外检查应在执行前拒绝时底层节点是否仍被调用；
6. 评测用例可进入 Git，报告仍只允许写入 `data/private/`；
7. v1.0 只建立确定性 Policy 基线，不调用真实 LLM，也不把结果夸大为模型对抗安全或生产稳定性。

## 原因

- 复用真实 Harness 能避免“测试通过但产品走另一条链”的假阳性；
- 合成节点事实可作为稳定 ground truth，覆盖真实私人历史暂时没有的极端分支；
- stale 属于编排后的写入安全，必须在真实 Service/SQLite 边界验证；
- 分开统计任务、韧性、护栏和审核，避免把安全退出错误地算成任务失败；
- Suite Hash 使未来 LLM Coach Policy 能在相同题集上比较。

## 后果

- v1.0 的主要结论是 Harness、确定性路由和产品审核边界满足18个合成场景，不能代表真实模型能稳定选择多 Agent 动作；
- P95 会被 SQLite stale 集成场景主导，适合作为本机回归观察，不作为跨机器硬门槛；
- 若接入 LLM Coach Policy，需要增加模型调用、动作解析、Token、费用和提示注入场景，但不能修改现有场景来迁就模型；
- 临时 SQLite Engine 必须显式释放，否则 Windows 无法清理评测目录。

## 替代方案

- 只保留 M7-C/M7-D 单元测试：拒绝，因为缺少版本化聚合结果和同题对照入口；
- 为评测重写一个简化 Coach：拒绝，因为会形成与产品不同的旁路；
- 使用真实跑步数据库跑全套：拒绝，因为隐私、覆盖不足和不可重复；
- 直接接入 DeepSeek 再评测：拒绝，因为没有多 Agent 确定性基线，无法区分模型与 Harness 回归。
