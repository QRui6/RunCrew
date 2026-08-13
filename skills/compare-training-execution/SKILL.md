---
name: compare-training-execution
description: 将 RunCrew 中指定训练计划的计划课与规范化实际跑步活动进行可回放对照，输出已完成、部分完成、已跳过、待执行、休息或无法匹配，并通过用户确认建立或清除关联。用于用户询问本周训练执行情况、某次跑步对应哪节计划课、是否完成训练量、确认匹配、标记跳过或纠正错误关联时。不得自动认领相似活动、自动判定跳过、关联非跑步活动或绕过 plan revision。
---

# 训练执行对照

先生成只读候选，再由用户显式确认写入。不要让 LLM 自行修改 `status` 或 `linked_activity_id`。

## 生成执行对照

1. 使用 RunCrew 内部 `plan_id`，不要使用 Provider 外部 ID。
2. 显式设置 `as_of` 进行历史回放；不得读取该时点之后的活动。
3. 多个 Provider 可能重复记录活动时显式指定 Provider。
4. 执行：

```powershell
runcrew execution compare `
  --plan-id <RunCrew计划ID> `
  --provider coros
```

历史回放时增加：

```powershell
  --as-of 2026-08-16T20:00:00+08:00
```

5. 使用 [对照输入 Schema](references/compare-input.schema.json) 和 [对照输出 Schema](references/output.schema.json) 校验结果。
6. `suggested` 只是候选，必须等待用户确认；`unmatched` 不等于用户跳过训练。

## 解释结果

- `complete`：已确认或候选活动达到至少 90% 的可比较训练量；候选仍不等于写入；
- `partial`：已确认或候选活动低于 90%；不评价训练质量或伤病因果；
- `skipped`：只能来自用户明确标记；
- `unmatched`：没有候选、候选冲突、训练量不可比或已有关联失效；
- `upcoming`：知识截止时间时尚未到计划日期；
- `rest`：休息课不匹配活动。

匹配状态：

- `confirmed`：用户确认的持久化关联或跳过状态；
- `suggested`：只有一个清晰候选，仍需确认；
- `ambiguous`：多个候选得分接近，或同一活动竞争多节课；
- `broken_link`：计划记录了活动 ID，但当前上下文找不到对应活动；
- `none`：没有匹配。

## 用户确认与纠正

确认建议活动：

```powershell
runcrew execution decide `
  --plan-id <计划ID> `
  --base-revision <对照结果中的revision> `
  --session-id <计划课ID> `
  --decision confirm_match `
  --activity-id <RunCrew活动ID>
```

用户明确没有完成某课时使用 `--decision mark_skipped`。纠正错误关联或跳过状态时，使用最新 revision 和 `--decision clear_execution`。

使用 [确认输入 Schema](references/decision-input.schema.json) 与 [确认输出 Schema](references/decision-output.schema.json) 校验结果。

## 匹配与完成度边界

- 候选只包含跑步、室内跑、越野跑和场地跑；
- 默认只比较计划日前后一天，可由调用方设为 0 至 3 天；
- 日期接近度占候选分数 55%，距离/时长相似度占 45%；缺少训练量时不输出完成结论；
- 距离和时长都存在时，完成比例取两者较低值；
- 最佳得分低于 0.65、前两名差值小于 0.15，或同一活动竞争多节课时返回 ambiguous；
- 这些阈值是 `training-execution-rules/1.0` 工程规则，不是运动科学标准。

详细规则见 [执行对照边界](references/execution-boundary.md)。

## 权限护栏

- `compare` 只读，不修改计划；
- `decide` 必须由用户显式触发，并使用 `base_revision`；
- revision 已变化时记录 stale，不执行写入；
- 同一活动不能关联同一计划中的两节课；
- 不能确认未来活动，也不能提前标记未来计划课为完成或跳过；
- 活动日期与计划课相差超过三天时拒绝确认；
- 不读取或输出 Provider 原始载荷、外部 ID、坐标、Token 或完整 FIT。

## 失败处理

- 计划或计划课不存在：返回明确错误；
- 没有活动候选：保留 unmatched，等待用户补同步、选择活动或标记跳过；
- 候选冲突：展示脱敏候选，不擅自选择；
- 已确认关联失效：返回 broken_link，提示检查 Provider 过滤或清除关联；
- 过期 revision：记录 stale，重新 compare 后再确认；
- Schema 校验失败：拒绝把自然语言推断写入计划。
