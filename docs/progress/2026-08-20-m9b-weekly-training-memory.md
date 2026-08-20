# M9-B：版本化周训练记忆

## 1. 本阶段目标

把正式周计划、用户确认的执行事实、规范化 Activity、Check-in 和已批准计划变更结算为可审计的 Weekly Training Memory，并让 Planning Agent 在下一周规划时优先消费这类记忆。

## 2. 用户可感知结果

- 网页训练闭环可以点击“结算上一训练周”，查看完成、跳过、未解决课次、确认训练时长与距离、身体反馈和缺失数据；
- API 可以生成和列出指定目标的周训练记忆；
- CLI 支持 `memory build-week`、`memory weekly` 和带显式确认的 `memory invalidate-week`，作为失效审计入口；
- 下一周计划会优先使用最近有效周记忆计算训练时长基线，并在 evidence 中说明使用了哪一版；
- 演示种子数据库包含一个已经结算的上一训练周，首次启动即可展示跨周记忆链路。

## 3. 主要新增与修改文件

- 领域与服务：`src/runcrew/domain/memory.py`、`src/runcrew/services/weekly_training_memory.py`；
- 存储：`src/runcrew/storage/models.py`、`src/runcrew/storage/repositories.py`；
- 规划消费：`src/runcrew/domain/training_planning.py`、`src/runcrew/services/training_planning.py`；
- 产品编排：`src/runcrew/domain/training_operations.py`、`src/runcrew/services/training_operations.py`；
- 入口：`src/runcrew/cli.py`、`src/runcrew/web/server.py`、`src/runcrew/web/static/chat.*`；
- 演示与契约：`src/runcrew/services/demo_seed.py`、`schemas/training-operations/weekly-memory-*.schema.json`；
- 测试：`tests/test_weekly_training_memory.py`、`tests/test_demo_seed.py`、`tests/test_training_operations.py`；
- 决策：`docs/adr/0022-versioned-weekly-training-memory.md`。

## 4. 关键技术决策

- 只在训练周结束后生成正式记忆，且严格执行 `as_of` 知识截止时间；
- 只有 `applied` 执行确认引用的 Activity 才计入完成量，避免把设备候选误当作训练事实；
- 使用稳定事实 Hash、UUIDv5、版本号与 `active / superseded / invalidated` 生命周期支持幂等、替代和撤销；`as_of` 只筛选可见事实，不因刷新时间变化制造空版本；
- 失效记录永不复活：同样事实重新生成也会创建更高版本；
- Planning 优先读取最近有效周记忆；至少 2 周且周均确认时长达到 45 分钟才采用该基线，否则回退到 Activity；
- LLM 不拥有正式记忆写权限，当前使用 SQLite 结构化检索，不提前引入向量库。

## 5. 验收命令与结果

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe demo-seed --reset --as-of 2026-08-20T08:00:00+08:00
.\.venv\Scripts\runcrew.exe memory weekly --goal-id <goal-id> --db data\private\demo\runcrew-demo.db
git diff --check
```

- 全量自动化测试：153 passed；
- Python 编译、Schema 导出一致性与 JavaScript 语法检查通过；
- 演示种子可重复生成上一训练周记忆；
- 未读取真实 COROS/FIT 数据、未调用 DeepSeek、未产生外部费用。

## 6. 实施中的问题与修复

- `PlanningEvidence` 扩展后只刷新单份 Schema，导致依赖它的 Coach 和训练运营 Schema 不一致；改为重新运行全部相关 exporter，并由回归测试校验。
- 最初确定性 ID 只包含事实 Hash，失效后用相同事实重建会覆盖并“复活”旧记录；改为把递增版本纳入 ID，并始终从最新历史版本继续编号。
- 阶段开始前发现偏好测试依赖“当天零点”，跨日后把刚确认偏好误判为未来数据；为训练运营 Service 注入时钟，保留历史回放边界并消除系统时间抖动。

## 7. 下一阶段唯一入口

M9-C：实现按 Execution、Recovery、Plan 职责构建的 Memory Context，记录每条记忆为什么被选中或排除，并设置明确的条数/字符预算。

## 8. 真实数据与外部额度

本阶段只使用合成 fixture、临时 SQLite 和隔离演示数据库；没有访问个人训练数据库、COROS 账户或付费模型。
