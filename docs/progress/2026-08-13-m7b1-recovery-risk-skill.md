# M7-B1 恢复与训练风险评估 Skill

## 本阶段目标

建立第二个可复用、确定性、可回放的领域 Skill，为未来 Recovery Agent 提供受控工具，同时把运动安全红旗与项目自定义训练阈值明确分开。

## 用户可感知结果

用户可以运行：

```powershell
.\.venv\Scripts\runcrew.exe recovery assess `
  --goal-id <目标ID> `
  --provider coros
```

系统综合最近活动、最近身体反馈和下一次计划课，输出：

- `proceed`：未触发当前规则；
- `reduce`：建议请求计划 Agent 降级；
- `rest`：建议请求计划 Agent 改为休息；
- `seek_professional_help`：停止自动训练处方并提示专业帮助；
- `insufficient_data`：补充近期反馈或课表后再判断。

每个结果包含 evidence、缺失数据、置信度、两个七天窗口、规则版本、输入 Hash 和计划动作，但不会直接修改正式计划。

## 新增和修改文件

- `src/runcrew/domain/recovery_assessment.py`：请求、窗口、证据、计划动作和结果 Schema；
- `src/runcrew/services/recovery_context.py`：有时间边界的回放 Context 与 Hash；
- `src/runcrew/services/recovery_assessment.py`：确定性风险规则；
- `skills/assess-running-recovery/`：中文 Skill、UI 元数据、安全边界和导出 Schema；
- `scripts/export_recovery_assessment_schemas.py`：Schema 导出；
- `tests/test_recovery_assessment.py`：规则、回放、持久化、CLI 与 Schema 测试；
- `DailyCheckIn.acute_symptoms`：结构化运动安全症状。

## 技术策略与亮点

1. `assessed_at` 明确锚定上下文，不读取未来活动或反馈；
2. 活动按内部 ID 去重，并支持 Provider 过滤；
3. 急性心肺红旗覆盖普通负荷判断；
4. 过期红旗仍升级，过期的一般疼痛只触发补充新反馈；
5. 训练负荷覆盖不足80%时，使用七天训练时长作为代理并公开 method；
6. `proceed` 不等于安全保证，缺近期反馈绝不默认正常；
7. 输出只给计划动作，正式课表仍走提案、revision 和用户确认；
8. `input_hash + ruleset_version` 支持稳定回放。

## 实施中的错误与解决方案

### Skill 初始化短描述不满足长度

官方初始化器要求 `short_description` 为25到64字符，第一次23字符被拒绝。补充描述后重新生成。

### 官方生成器缺少 PyYAML

项目虚拟环境没有生成器自身使用的 PyYAML。没有把它加入运行依赖；改用已经具备该依赖的系统 Python。

### Windows GBK 无法读取中文 SKILL.md

系统 Python 默认编码为 GBK，读取 UTF-8 Skill 失败。设置 `PYTHONUTF8=1` 后使用同一官方生成器成功生成 `agents/openai.yaml`。

### 历史评估可能读取未来反馈

初版 Service 直接读取数据库最近若干条反馈。改为按评估日期窗口查询，并用测试证明未来活动和反馈不会进入 Context 或 Hash。

### 单周查询看不到下周课表

周日评估可能需要处理下周一的课。Repository 改为读取当前周及下一训练周的激活计划，再选择日期最近的待执行课。

## 验收结果

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_recovery_assessment.py -q
$env:PYTHONUTF8='1'; python <skill-creator>\quick_validate.py skills\assess-running-recovery
.\.venv\Scripts\python.exe scripts\verify.py
```

- 12项恢复风险专项测试通过；
- 官方 Skill 校验通过；
- 全项目85项测试通过；
- 没有调用 COROS 或 DeepSeek，没有产生费用。

## 已知限制

- 当前阈值是保守工程规则，不是临床决策工具；
- 只有每日单条主观反馈，没有症状持续时间和趋势模型；
- 无训练负荷时使用训练时长代理，无法表示强度差异；
- 当前 Skill 只通过 CLI 使用，尚未接入聊天界面；
- Recovery Agent、Plan Agent 和协调 Harness 尚未实现；
- 真实用户使用前仍需人工确认输入量表是否容易理解。

## 下一阶段唯一入口

M7-B2：实现训练计划草案与调整 Skill。它根据目标、可训练日期、当前周计划和 Recovery Skill 的 `plan_action` 生成结构化草案或 `PlanChangeProposal` 参数，但不自行批准提案。

## 数据与外部额度

本阶段仅使用合成数据和公开安全资料，没有读取 `data/private/`，没有调用外部账户或付费模型。
