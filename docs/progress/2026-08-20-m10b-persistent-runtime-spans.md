# M10-B 持久化 Runtime Run/Span 阶段记录

## 1. 本阶段目标

把 Review Agent 与 Coach Orchestrator 的结果级 Trace 映射为同一套可持久化、可查询、带父子关系的 Runtime Run/Span，同时确保观测失败不改变业务终态。

## 2. 用户与开发者可感知结果

- 聊天首轮 Review 和训练运营 Coach 运行会留下统一 Runtime Run；
- 可以通过只读 API 查看最近运行或某次运行的完整父子时间线；
- 时间线区分 Policy、Guardrail、Handoff、Tool、Retry、Validation 和 Approval；
- 记录30天后过期并在后续写入时清理；
- Runtime 数据库写入失败时，聊天或 Coach 结果仍按原逻辑返回。

## 3. 新增与修改文件

新增：

- `src/runcrew/domain/runtime_observability.py`
- `src/runcrew/services/runtime_observability.py`
- `scripts/export_runtime_observability_schemas.py`
- `schemas/runtime-observability/` 四份 Schema
- `tests/test_runtime_observability.py`
- `docs/adr/0028-best-effort-persistent-runtime-spans.md`

修改：

- `src/runcrew/storage/models.py`
- `src/runcrew/storage/repositories.py`
- `src/runcrew/services/chat.py`
- `src/runcrew/services/training_operations.py`
- `src/runcrew/web/server.py`
- 相关产品测试、状态、架构、路线图、README、变更日志与求职证据。

## 4. 关键实现策略

1. **统一而不改写原 Trace**：Mapper 消费既有 Pydantic Trace，生成根 Span 与事件 Span；原结果契约继续保持兼容。
2. **白名单属性**：只保留规则 ID、Hash、计数、错误类型、Schema、运行上限和节点/工具名称；未知 details 默认丢弃。
3. **不可逆业务关联**：conversation 或 goal/plan 组合只形成 SHA-256 `scope_ref_hash`，不保存原 ID。
4. **best-effort 短事务**：Mapper 与 Runtime Repository 失败只生成 `RuntimePersistenceOutcome(error_type)`，不返回数据库异常正文。
5. **写入幂等与防覆盖**：同 Run/同 Trace 返回 `created=false`；同 Run/不同 Trace 拒绝覆盖旧证据。
6. **产品与评测隔离**：只在 ChatService/TrainingOperationsService 的 Harness 返回后写入；离线 Evaluation 不接入。

## 5. 实施错误与解决方案

### SQLite 时区列读回为 naive datetime

第一版 Repository 直接用 `AgentRuntimeRunRecord.expires_at <= aware_now` 判断单条记录是否过期。SQLite 读回的时间没有 tzinfo，专项 API 测试触发 `TypeError` 并返回500。

解决：Run 的规范 JSON 始终保存时区，Repository 先通过 `RuntimeRun.model_validate_json` 恢复 aware datetime，再执行单条过期判断；数据库 `expires_at` 列继续用于索引与批量删除。修复后专项24项通过。

## 6. 验收结果

```powershell
.\.venv\Scripts\python.exe scripts\export_runtime_observability_schemas.py
.\.venv\Scripts\python.exe -m pytest tests\test_runtime_observability.py tests\test_chat.py tests\test_training_operations.py tests\test_demo_web.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

- Runtime/产品联合专项24项通过；
- 新增6项 Runtime Observability 测试；
- 全量195项测试通过；
- 本阶段没有读取私人数据库、调用 COROS/DeepSeek 或产生费用。

## 7. 已知边界

- CLI、Evaluation 与独立 Harness 调用默认不持久化；
- 当前只有查询 API，没有 Runtime 时间线 UI；
- 没有跨运行聚合、P50/P95、拒绝率、重试率和告警；
- 没有分布式 Trace 上下文传播或外部 exporter；
- best-effort 写入失败当前不会主动通知用户。

## 8. 下一阶段唯一入口

M10-C：基于正式 Runtime 表计算跨运行成功率、拒绝率、重试率与P50/P95，增加版本化治理故障场景和只读工程观测视图。指标必须注明样本范围，不能把产品本地运行外推为生产效果。
