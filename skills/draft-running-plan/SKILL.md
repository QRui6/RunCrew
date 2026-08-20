---
name: draft-running-plan
description: 根据 RunCrew 中已保存的训练目标、可训练星期、已确认长期偏好、规范化历史活动和恢复评估动作，生成可回放的周训练计划草案或待用户确认的计划调整提案参数。用于用户要求安排下一训练周、根据疲劳或疼痛反馈降低下一课、把下一课改为休息，或检查计划 Agent 是否越权时。不得用于自动批准、直接覆盖激活计划、比赛周处方、伤病诊断或治疗建议。
---

# 跑步训练计划草案

使用确定性 Service 生成结构化计划，不让 LLM 自行计算周跑量、调整幅度或批准变更。

## 选择操作

- 安排尚无计划的训练周：执行“生成周计划草案”；
- 已有激活计划，需要依据最新恢复评估调整下一课：执行“恢复评估转调整提案”；
- 用户只是讨论训练思路：先解释，不要擅自生成或保存计划；
- 比赛周、目标已过期或存在专业评估升级信号：停止自动规划并说明阻塞原因。

## 生成周计划草案

1. 确认训练目标是有效的 RunCrew 内部目标。
2. `--week-start` 必须是周一；`--as-of` 是知识截止时间，历史回放不得读取之后的数据。
3. 多个 Provider 可能记录同一活动时显式指定 Provider。
4. 执行：

```powershell
runcrew planning draft `
  --goal-id <RunCrew目标ID> `
  --week-start 2026-08-17 `
  --provider coros
```

历史回放时增加：

```powershell
  --as-of 2026-08-13T08:00:00+08:00
```

5. 使用 [周计划输入 Schema](references/draft-input.schema.json) 和 [输出 Schema](references/output.schema.json) 校验结果。
6. `status=ready` 只表示草案完整；仍须用户确认，且命令不会写入数据库。

## 恢复评估转调整提案

该操作按固定顺序运行 Recovery Skill，再把其 `plan_action` 交给 Plan Skill：

```powershell
runcrew planning adjust `
  --goal-id <RunCrew目标ID> `
  --provider coros
```

回放指定时点时增加 `--assessed-at <带时区ISO时间>`。直接调用 Service 时使用 [调整输入 Schema](references/adjust-input.schema.json)。

动作语义固定：

- `keep`：返回 `no_change`，不制造无意义提案；
- `ask_plan_agent_to_reduce`：生成降低负荷的 `PlanSessionPatch`；
- `ask_plan_agent_to_replace_with_rest`：生成清除距离、时长和强度并改为休息的 Patch；
- `wait_for_more_data`：返回 `blocked`，先补充数据；
- `hold_until_professional_review`：返回 `blocked`，不生成替代训练。

## 规则与证据边界

- 只在用户声明的可训练星期中选课，并优先拉开训练日间隔；
- 如果存在经过用户确认且仍有效的长跑星期偏好，只在该日期属于当前目标可训练日时采用；目标级设置始终优先；
- 历史足够时，以知识截止日前的规范化活动计算历史周均时长；v1 最多增加 5%；
- 历史不足时只使用低强度入门模板，不根据目标成绩编造间歇配速；
- 只有至少 8 条近期活动、每周至少 3 个训练日且距离比赛至少 4 周时，v1 才允许生成一次受控节奏课；
- 休息日间隔、循序渐进属于安全原则；5% 上限、时长分配和质量课门槛是 RunCrew 自身的版本化保守工程规则，不得说成医学标准；
- 每个结果携带 `input_hash + ruleset_version`；草案课 ID 由输入确定，可用于同输入回放。
- 实际读取的偏好版本必须进入 `input_hash` 和 evidence；偏好变化后旧草案不得继续激活。

规则来源与已知限制见 [规划规则边界](references/planning-boundary.md)。

## 权限护栏

- 不覆盖已经存在的周计划；
- 不保存 `PlanChangeProposalDraft`，更不能批准自己的提案；
- 调整提案必须绑定 `plan_id + base_revision`，避免旧提案覆盖新计划；
- 不把 `target_time_seconds` 直接换算为高强度训练处方；
- 不读取或输出 Provider 原始载荷、坐标、Token、完整 FIT 或私人数据库内容；
- 不输出确诊、治疗方案或保证不受伤的说法。

## 失败处理

- 目标不存在或未激活：返回明确错误；
- 该周已有计划、目标已过期或属于比赛周：返回 `blocked`；
- 本周已没有可训练日期：返回 `blocked`；
- 恢复动作引用的课不在激活计划：返回 `blocked`；
- 目标课已完成或跳过：拒绝生成调整提案；
- Schema 校验失败：拒绝把自然语言建议当作计划结果。
