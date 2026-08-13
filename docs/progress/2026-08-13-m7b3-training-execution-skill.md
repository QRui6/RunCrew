# M7-B3 训练执行对照 Skill

## 本阶段目标

建立计划课与实际跑步活动之间可解释、可回放、可人工纠正的关联，补齐“计划之后发生了什么”的事实链。

## 用户可感知结果

```powershell
.\.venv\Scripts\runcrew.exe execution compare `
  --plan-id <计划ID> `
  --provider coros
```

系统返回 complete、partial、skipped、unmatched、upcoming 或 rest。清晰候选仍标记 suggested，不会自动写入。

用户确认时运行：

```powershell
.\.venv\Scripts\runcrew.exe execution decide `
  --plan-id <计划ID> `
  --base-revision <revision> `
  --session-id <计划课ID> `
  --decision confirm_match `
  --activity-id <RunCrew活动ID>
```

也可显式 `mark_skipped` 或 `clear_execution`。每次成功写入都会提升计划 revision 并保存审计记录。

## 新增和修改文件

- `domain/training_execution.py`：对照、候选、证据、确认与输出 Schema；
- `services/training_execution.py`：确定性候选、完成比例、冲突降级和确认状态机；
- `storage/models.py` / `repositories.py`：训练执行确认审计表和 Repository；
- `skills/compare-training-execution/`：中文 Skill、规则边界、UI 元数据和四个导出 Schema；
- `scripts/export_training_execution_schemas.py`：Schema 导出；
- `tests/test_training_execution.py`：匹配、回放、冲突、写入、stale、CLI 和 Schema 测试；
- `cli.py`：`execution compare/decide` 命令；
- ADR-0016：候选与用户确认边界。

## 技术策略与亮点

1. as_of 约束历史回放，不读取未来活动；
2. input hash 排除计划的 created/updated 时间噪声，同一业务输入稳定回放；
3. 日期和训练量只形成候选，系统不自动认领活动；
4. 多候选、共享候选、低分候选和缺训练量均安全降级；
5. unmatched 不等于 skipped，避免把同步失败误记为用户未训练；
6. 用户确认写入 linked_activity_id/status，并以 revision 防止并发旧操作；
7. 支持清除错误关联，确认历史独立审计；
8. 只使用内部 Activity ID，不向业务层暴露 Provider 外部 ID。

## 实施中的错误与解决方案

### 计划创建时间破坏回放稳定性

初版 Hash 直接包含完整 TrainingPlan，因此两份业务相同但创建时间不同的计划产生不同 Hash。改为只哈希计划 ID、目标、周、状态、revision 与 sessions。

### 未来课测试越过训练周边界

测试把未来课放到下一周，被 TrainingPlan Schema 正确拒绝。改为将 as_of 前移，在同一训练周内验证 upcoming。

### 只按日期的候选被误当成完整完成

初版缺少距离/时长时默认完成比例为1。改为 None，并输出 unmatched/缺少可比较训练量，不把日期相同等价为完成训练目标。

## 验收结果

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_training_execution.py -q
$env:PYTHONUTF8='1'; python <skill-creator>\quick_validate.py skills\compare-training-execution
.\.venv\Scripts\python.exe scripts\verify.py
```

- 12项执行对照专项测试通过；
- Skill 官方校验通过；
- 全项目107项测试通过；
- 只使用合成数据，没有调用 COROS、DeepSeek 或其他外部账户。

## 已知限制

- 不解析训练标题、配速区间、心率区间和间歇分段来识别课型；
- 不自动去重多设备/多 Provider 的同一次活动；
- 跨计划复用同一 Activity 的冲突尚未统一检查；
- 当前 CLI 会展示内部 Activity ID 供确认，聊天产品尚未提供更友好的候选卡片；
- 目前是确定性 Skill 与状态机，尚未接入多 Agent Harness 和跨节点 Trace。

## 下一阶段唯一入口

M7-C：实现 Coach Orchestrator Harness，把恢复评估、计划调整和执行对照作为三个受权限约束的工具节点，记录跨职责 Trace、预算、退出条件和用户确认暂停点。

## 数据与外部额度

本阶段只使用合成数据，没有读取 `data/private/`，没有调用外部账户或产生费用。
