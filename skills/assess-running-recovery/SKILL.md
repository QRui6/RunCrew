---
name: assess-running-recovery
description: 基于 RunCrew 规范化训练记录、最近主观身体反馈和下一次计划课，执行可回放的恢复与训练风险分层。用于判断今天应照常训练、降低训练、休息、补充数据或停止训练建议并寻求专业帮助，以及为计划调整 Agent 提供带 evidence 的结构化依据。不得用于伤病确诊、疾病诊断或替代医生。
---

# 跑步恢复风险评估

把规范化活动、身体反馈和当前课表交给确定性 Service，返回带证据的训练决策边界。不要由 LLM 自行计算风险等级。

## 执行流程

1. 确认目标是 RunCrew 内部训练目标，不接受 Provider 外部 ID。
2. 使用带时区的评估时间构建上下文；历史回放时不得读取该时间之后的活动或反馈。
3. 多个 Provider 可能记录同一活动时显式指定 Provider，避免重复计算训练量。
4. 执行：

```powershell
runcrew recovery assess `
  --goal-id <RunCrew目标ID> `
  --provider coros
```

回放历史评估时显式提供时间：

```powershell
runcrew recovery assess `
  --goal-id <RunCrew目标ID> `
  --assessed-at 2026-08-13T08:00:00+08:00 `
  --provider coros
```

5. 使用 [输入 Schema](references/input.schema.json) 和 [输出 Schema](references/output.schema.json) 校验结果。
6. 只解释已经校验的 recommendation、evidence、missing_data 和 confidence；不要重新打分或提升置信度。
7. 需要修改计划时，把 `plan_action` 交给计划 Agent 形成 `PlanChangeProposal`；本 Skill 不直接写入激活计划。

## 结果语义

- `proceed`：当前已知信息未触发规则阈值，不表示保证安全；
- `reduce`：请求计划 Agent 生成降级提案；
- `rest`：请求计划 Agent 生成休息提案；
- `seek_professional_help`：停止自动训练处方，提示寻求合适的专业帮助；
- `insufficient_data`：先补充近期身体反馈或课表，不能默认正常训练。

风险优先级固定为：急性红旗或极严重疼痛 > 休息阈值 > 降级阈值 > 正常。训练负荷不得覆盖急性症状。

## 证据与规则边界

- 急性症状来自用户显式枚举，不从自由文本猜测；
- 胸部不适、晕厥/明显头晕、异常或严重呼吸困难、新发心律异常属于停止训练建议的红旗；
- 疲劳、睡眠、酸痛、准备度和负荷变化采用版本化的 RunCrew 保守工程阈值，不得描述成医学标准；
- 训练负荷字段覆盖不足时可使用训练时长变化作为代理，必须在 evidence 中标明 `duration_seconds_proxy`；
- 缺少足够新的身体反馈时返回 `insufficient_data`，但历史反馈中的严重红旗仍需升级；
- 每个结论使用 `input_hash + ruleset_version` 支持回放。

权威红旗资料和本项目规则归属见 [安全边界](references/safety-boundary.md)。

## 医疗与权限护栏

- 不输出确诊、病名判断、治疗方案或“保证不会受伤”；
- 不把训练量相关性解释成伤病因果关系；
- 出现红旗时不要继续生成替代训练课；
- `reduce` 和 `rest` 只产生建议，激活计划仍需用户批准；
- 不读取或输出原始 Provider payload、坐标、Token、完整 FIT 或私人数据库内容；
- 不把 `proceed` 表述为医学许可。

## 失败处理

- 目标不存在：停止并返回明确错误；
- 近期反馈缺失或过旧：返回 `insufficient_data`；
- 下一次计划课缺失：保留风险结论，但 `plan_action` 改为等待补充课表；
- 训练量不可比较：保留 `comparable_training_volume` 缺失项，不伪造变化趋势；
- Schema 校验失败：拒绝输出不完整自然语言结论。
