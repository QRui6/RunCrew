# M9-C：按职责裁剪的记忆上下文

## 1. 本阶段目标

为 Execution、Recovery、Plan 建立同一套确定性 Memory Context Builder，固定可见字段、候选顺序和条数/字符预算，并记录每条记忆为什么被选中或排除。

## 2. 用户可感知结果

- 网页训练闭环显示执行核对、恢复评估和计划调整各自选中记忆数、字符用量和排除数；
- `runcrew memory context` 可以按职责查看完整选中/排除审计、Context Hash 与 Audit Hash；
- Execution 明确显示 0 条长期记忆权限，不会因为历史偏好改变活动匹配；
- Recovery 最多读取 2 份近期有效周摘要，并明确说明不会改变安全红旗阈值；
- Plan 读取有效偏好和历史周摘要，但不会获得疼痛、急性症状等不必要字段；
- CLI 与网页 Planning 现在统一使用同一周记忆 Context，消除了入口差异。

## 3. 主要新增与修改文件

- 领域契约：`src/runcrew/domain/memory.py`；
- Context Builder：`src/runcrew/services/memory_context.py`；
- 三职责接入：`src/runcrew/services/training_execution.py`、`recovery_context.py`、`recovery_assessment.py`、`training_planning.py`；
- 产品与入口：`src/runcrew/services/training_operations.py`、`src/runcrew/cli.py`、`src/runcrew/web/static/chat.*`；
- Schema：`scripts/export_memory_context_schemas.py`、`schemas/memory-context/` 及受影响的 Skill/Coach/Training Operations Schema；
- 测试：`tests/test_memory_context.py`、`tests/test_demo_seed.py`、`tests/test_training_operations.py`；
- 决策：`docs/adr/0023-role-scoped-memory-context.md`。

## 4. 关键技术决策

- Execution 为 0 条/0 字符；Recovery 为 2 条/1400 字符；Plan 为 5 条/1800 字符；
- 先按职责、目标、状态和时点过滤，再按偏好优先、周记忆从新到旧的确定顺序装入预算；
- 使用职责专属投影，Plan 周摘要主动删除恢复与疼痛字段；
- `context_hash` 只绑定实际选中内容，`audit_hash` 绑定完整检索决定，避免无关失效记录让业务结果变 stale；
- Context Hash 进入 Execution、Recovery 和 Planning 的业务输入 Hash，选中记忆变化可以被重放识别；
- Recovery 周摘要是背景证据，`affects_safety_thresholds=false`，不会覆盖当前 Check-in 或红旗规则。

## 5. 验收命令与结果

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe demo-seed --reset --as-of 2026-08-20T08:00:00+08:00
.\.venv\Scripts\runcrew.exe memory context --role plan --goal-id <goal-id> --as-of 2026-08-20T08:00:00+08:00 --target-week-start 2026-08-24 --db data\private\demo\runcrew-demo.db
git diff --check
```

- 全量自动化测试：158 passed；
- 新增5项 Memory Context 专项测试，覆盖职责隔离、字段投影、生命周期排除、双 Hash、预算、Planning、CLI 和 Schema；
- Python 编译、全部依赖 Schema 导出和 JavaScript 语法检查通过；
- 未读取真实训练数据库、未访问 COROS、未调用 DeepSeek、未产生外部费用。

## 6. 实施中的问题与修复

- 核对入口时发现 M9-B 的网页 Planning 已传入周记忆 Repository，但 `planning draft` CLI 没有传入，导致同一业务不同入口的 Context 不一致；M9-C 改为所有生产入口统一调用 Context Builder。
- 如果把全部排除决定写进业务 Hash，新增无关归档/失效记录也会让计划变 stale；拆分 `context_hash` 与 `audit_hash`，并用测试固定两者语义。
- 首次验收时 Plan 的恢复敏感字段虽然全部是 `null`，字段名仍出现在 JSON 和 Schema 中，不符合严格的字段最小化；将周记忆投影拆成以 `role` 为判别字段的 Recovery/Plan 联合类型，使 Plan 契约中根本不存在这些字段。
- 三个业务输出新增 Context 后，Planning、Recovery、Execution、Coach 和 Training Operations 的嵌套 Schema 同时变化；重新运行全部依赖 exporter，避免只更新局部 Schema。

## 7. 下一阶段唯一入口

M9-D：让自然语言聊天只能产生待用户确认的类型化 Memory Candidate；候选不能直接写入长期偏好或正式周记忆，并复用现有确认、来源和权限边界。

## 8. 真实数据与外部额度

本阶段只使用合成模型、临时 SQLite 和隔离演示库；没有读取 `data/runcrew.db`、真实 FIT、Token 或模型密钥。
