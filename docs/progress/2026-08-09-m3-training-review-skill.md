# M3：Training Review Skill

## 目标

把单次活动复盘和最近训练历史封装为输入输出明确、结论可回放、缺数据可降级的 Skill，为后续 Context、Harness 和 Agent Loop 提供稳定能力边界。

## 用户可感知结果

用户现在可以运行：

```powershell
runcrew training review --latest --provider coros
```

系统固定返回训练完成度、七天负荷变化和训练异常三类 finding。每条 finding 都包含 evidence；没有计划或历史负荷时返回 `unknown + requires`，不会补写不存在的数据。

## 主要文件

- `src/runcrew/domain/training_review.py`：请求、计划、窗口、finding 和结果 Schema；
- `src/runcrew/services/training_context.py`：目标时间锚定、窗口聚合和输入哈希；
- `src/runcrew/services/training_review.py`：三类确定性规则；
- `skills/review-running-training/SKILL.md`：Agent 使用流程与边界；
- `skills/review-running-training/references/*.schema.json`：机器可读契约；
- `scripts/export_training_review_schemas.py`：从 Domain 模型导出 JSON Schema；
- `tests/test_training_review.py`：回放、降级、异常、Schema 和 CLI 测试；
- `docs/adr/0006-deterministic-training-review-skill.md`：规则与 LLM 分工决策。

## 关键决策

- 时间窗口锚定目标活动时间，不依赖运行当天时间；
- `input_hash + ruleset_version` 作为回放身份；
- Pydantic Domain 模型是契约唯一事实来源，Skill 引用导出的 JSON Schema；
- LLM 不计算指标、不修改 level、不隐藏 missing data；
- 没有持久化训练计划前，计划目标只能由用户显式提供。

## 验收

```text
pytest / scripts/verify.py: 24 passed
skill-creator quick_validate.py: Skill is valid
fixture CLI: 三类 finding 均满足 Schema
真实 COROS 本地回放: 成功；缺失计划/负荷历史时降级，真实分圈 evidence 保留
```

具体活动 ID、时间、距离、心率和分圈数值不写入阶段文档。

## 已知限制

- COROS 当前没有映射训练负荷，真实负荷趋势需要后续补充数据源或字段；
- 训练计划没有持久化模型；
- 当前没有 LLM narrative、Trace、工具预算和状态机；
- 真实跨周历史仍少，负荷规则主要由人工 fixture 验证。

## 下一阶段唯一入口

M4：定义 Review Agent 的状态机与 Trace Schema，使用本 Skill 作为唯一训练分析工具，增加重试、超时、预算、故障注入、退出条件和输出 Schema 验证。

## 私有数据

M3 只读取本地规范化活动，不读取或提交 `data/private/`、原始 FIT、真实 LabelId 和 Token。真实验收结果仅记录状态，不记录个人运动指标。
