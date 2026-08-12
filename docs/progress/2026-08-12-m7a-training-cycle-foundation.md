# M7-A 训练闭环数据与权限基础

## 本阶段目标

在创建多个专业 Agent 前，先建立它们共同操作的真实业务对象和写入边界，使训练计划、恢复建议和用户决定可以持久化、回放和验证。

## 用户可感知结果

- 创建5公里、10公里、半马、全马或日常健身目标；
- 记录目标日期、目标成绩和每周可训练日期；
- 创建周训练计划，在草稿期增加具体训练课并激活；
- 记录疲劳、酸痛、睡眠质量、准备度、疼痛部位和备注；
- 为激活计划提交结构化变更提案；
- 用户批准或拒绝提案；
- 查看目标、当前计划、最近反馈和待确认提案组成的快照。

## 新增和修改文件

- `src/runcrew/domain/training_cycle.py`：目标、计划、反馈、提案、确认和快照 Schema；
- `src/runcrew/services/training_cycle.py`：训练闭环状态机与业务校验；
- `src/runcrew/storage/models.py`：五张本地表；
- `src/runcrew/storage/repositories.py`：对应 Repository；
- `src/runcrew/cli.py`：`runcrew cycle` 九个本地命令；
- `tests/test_training_cycle.py`：领域、持久化、权限、版本冲突和 CLI 测试；
- `docs/adr/0013-confirmed-plan-change-boundary.md`：计划写入权限决策。

## 关键技术策略

1. Domain 不依赖 SQLAlchemy、LLM 或 Provider；
2. 新表通过现有 `create_schema()` 增量创建，不修改已有 Activity 与 Chat 表；
3. 草稿与激活计划使用不同写入规则；
4. Agent 只有提案权，用户持有激活计划的最终修改权；
5. `base_revision` 防止旧提案覆盖新版本；
6. 结构化清除字段避免把课表改为休息后仍残留距离或强度；
7. 疼痛数据属于主观反馈，不能被解释为医疗诊断。

## 实施中出现的问题与解决方案

### Typer 不能直接解析 `datetime.date`

首次运行 `runcrew cycle --help` 时，当前 Typer 版本报告 `Type not yet supported: datetime.date`。改为 CLI 接收字符串，再通过共享的 `parse_iso_date()` 严格校验 `YYYY-MM-DD`，并增加非法日期回归测试。

### 计划课改为休息后可能残留训练量

普通的 Pydantic Patch 使用 `None` 表示“未修改”，无法同时表达“主动清除”。新增 `clear_distance`、`clear_duration` 和 `clear_intensity`，并在最终 Plan Schema 中拒绝带距离或时长的休息课。

### 过期提案的事务语义

若抛出异常后调用方回滚，`stale` 状态也可能丢失。Service 现在返回已标记失效的提案和确认记录，同时保持计划不变，让调用层正常提交审计结果。

## 验收

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_training_cycle.py -q
.\.venv\Scripts\runcrew.exe cycle --help
.\.venv\Scripts\python.exe scripts\verify.py
```

结果：7项专项测试和73项全量测试通过；完整 CLI 闭环从创建目标、计划、反馈和提案运行到用户批准及快照读取。

## 已知限制

- 目前只有 CLI，没有把目标、反馈和提案接入聊天界面；
- 还没有自动生成计划，也没有恢复风险判断 Skill；
- 计划课尚未自动匹配实际 Activity；
- 当前按本地单用户设计，没有登录和多租户；
- 使用增量建表而非正式迁移框架，后续字段变更前需要引入迁移策略。

## 下一阶段唯一入口

M7-B1：实现确定性的恢复与风险评估 Skill。它读取规范化的最近训练、最近主观反馈和下一次计划课，输出带 evidence 的 `proceed / reduce / rest / seek_professional_help` 建议，为 Recovery Agent 提供受控工具。

## 数据与外部额度

本阶段测试仅使用合成数据，没有读取 `data/private/`，没有调用 COROS 或 DeepSeek，也没有产生外部费用。
