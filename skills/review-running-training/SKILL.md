---
name: review-running-training
description: 基于一条 RunCrew 规范化活动、近期训练历史和可选训练计划生成训练复盘。用于回答训练完成度、七天负荷变化、配速异常、分圈稳定性、证据缺失以及历史复盘回放等问题。必须返回通过 TrainingReviewResult Schema 校验的结果，禁止推断医疗诊断。
---

# 跑步训练复盘

从 RunCrew Domain 数据生成可回放、带证据的训练复盘。指标计算必须由确定性 Service 完成；LLM 只能解释已经通过校验的结论。

## 执行流程

1. 从 RunCrew Repository 选择一条规范化目标活动。除非用户明确要求排查问题，否则不要读取 COROS 原始文本或 `data/private/`。
2. 按目标活动的时间而不是当前系统时间，收集回看窗口内相同 Provider 的活动。
3. 只有用户明确提供计划距离或计划时长时，才加入训练计划；不得猜测计划。
4. 运行确定性训练复盘：

```powershell
runcrew training review --latest --provider coros
```

已知训练计划时显式传入目标：

```powershell
runcrew training review --latest --provider coros `
  --planned-distance-km 8 --planned-duration-minutes 45
```

5. 使用 [输入 Schema](references/input.schema.json) 校验请求，使用 [输出 Schema](references/output.schema.json) 校验结果。
6. 固定返回 `training_completion`、`load_change` 和 `training_anomaly` 三类结论。数据不足时保留 `unknown` 及其 `requires` 证据，不得删除。
7. 用户需要自然语言说明时，只改写已经验证的 message，并引用 evidence 中的数值；不得重新计算指标、改变 level 或隐藏缺失数据。

## 证据规则

- 使用 `input_hash + ruleset_version` 标识一次可回放结果。
- 每条 finding 必须包含非空 evidence。
- 缺少计划、负荷窗口不完整、分圈或历史配速不足，都属于数据限制，不代表用户训练表现差。
- 不得把训练负荷变化或配速异常解释为伤病、疾病或医疗结论。
- 输出说明中不得暴露 Provider 外部 ID、GPS 坐标、Access Token 或签名 URL。

## 失败处理

- 找不到目标活动时，明确返回查询错误并停止。
- 历史数据不足时，仍然返回符合 Schema 的降级结果并降低 confidence。
- Schema 校验失败时返回校验错误，不得使用不完整的自然语言结果替代结构化输出。
