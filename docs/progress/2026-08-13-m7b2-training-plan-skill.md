# M7-B2 训练计划草案与调整 Skill

## 本阶段目标

建立第三个确定性领域 Skill：根据目标与历史生成周计划草案，并把 M7-B1 的恢复动作转换为带 revision 的待确认调整提案，为下一阶段跨职责 Harness 提供真实业务工具。

## 用户可感知结果

生成下一周草案：

```powershell
.\.venv\Scripts\runcrew.exe planning draft `
  --goal-id <目标ID> `
  --week-start 2026-08-17 `
  --provider coros
```

运行恢复评估并生成调整提案参数：

```powershell
.\.venv\Scripts\runcrew.exe planning adjust `
  --goal-id <目标ID> `
  --provider coros
```

两条命令都只返回 JSON 草案，不写入正式计划。`adjust` 已形成第一个确定性的跨 Skill 串联：Recovery 输出 `plan_action`，Plan 消费该动作并生成提案参数。

## 新增和修改文件

- `src/runcrew/domain/training_planning.py`：请求、证据、周计划草案、提案草案和输出 Schema；
- `src/runcrew/services/training_planning.py`：时间边界、历史基线、排课、降级和阻塞规则；
- `skills/draft-running-plan/`：中文 Skill、UI 元数据、规则边界和导出 Schema；
- `scripts/export_training_planning_schemas.py`：Schema 导出；
- `tests/test_training_planning.py`：回放、未来数据、保守模板、提案和 CLI 测试；
- `src/runcrew/cli.py`：`planning draft/adjust` 命令；
- ADR-0015：固定计划草案与用户确认边界。

## 技术策略与亮点

1. `as_of` 明确知识截止时间，历史活动不会穿越回放时点；
2. 同输入生成相同 `input_hash` 和 UUIDv5 计划课 ID；
3. 训练日只来自用户 availability，并用组合评分优先拉开间隔；
4. 历史不足时不按目标成绩硬算间歇课，改用低强度模板并降低置信表达；
5. 具体 5% 增量、60% 降级与时长配比明确归属 RunCrew 工程规则；
6. `keep` 不生成无意义提案；缺数据和专业升级信号安全阻塞；
7. 调整只消费 Recovery 动作，不在 Plan Skill 中重复计算健康风险；
8. 提案绑定 base revision，但不落库、不批准，测试证明 pending proposal 仍为空。

## 实施中的错误与解决方案

### 恢复建议与动作不是简单一一对应

`reduce/rest` 在缺少下一计划课时会由 Recovery Skill 降级为 `wait_for_more_data`。初版调整输入误写成严格一一对应，后改为允许这两个安全降级组合，同时仍拒绝矛盾动作。

### 测试活动跨过知识截止时间

最初的合成活动以待规划周为基准生成，导致部分数据晚于 `as_of` 并被正确过滤，测试却错误期待生成节奏课。修正 fixture 以 `as_of` 为锚点，同时保留单独的未来数据隔离测试。

### 训练日间隔的直觉预期错误

可用日为周一至周日的六天时，组合算法选出周一、周四、周日，最小间隔为3天；原测试期待周一、周三、周六。改为验证算法实际最优解，不修改正确的排课逻辑。

## 验收结果

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_training_planning.py -q
$env:PYTHONUTF8='1'; python <skill-creator>\quick_validate.py skills\draft-running-plan
.\.venv\Scripts\python.exe scripts\verify.py
```

- 10项计划专项测试通过；
- Skill 官方校验通过；
- 全项目95项测试通过；
- 没有读取真实私人活动、调用 COROS 或 DeepSeek，也没有产生费用。

## 已知限制

- v1 主要按训练时长规划，不提供精确配速区间；
- 不处理比赛周、天气、海拔、力量训练、跨项目负荷和专业教练个体化策略；
- 多 Provider 自动去重尚未实现，需显式选择 Provider；
- 当前只是 Recovery 与 Plan 的确定性 Skill 串联，尚无多 Agent Harness、独立权限和跨节点 Trace；
- 草案尚未接入聊天产品，也没有“一键保存为 draft plan”的受确认入口。

## 下一阶段唯一入口

M7-B3：实现训练执行对照 Skill，把计划课与实际 Activity 建立可审计匹配，区分完成、部分完成、跳过和无法匹配，为 Coach Orchestrator 提供训练执行反馈。

## 数据与外部额度

本阶段只使用合成数据和公开权威资料，没有读取 `data/private/`，没有调用外部账户或付费模型。
