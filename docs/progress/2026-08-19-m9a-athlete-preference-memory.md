# M9-A 类型化运动员偏好记忆

## 1. 本阶段目标

在现有对话、证据快照和训练业务状态之上，增加第一条可被 Planning Agent 真正消费的长期记忆链路，同时保持显式确认、来源追踪、有效期、冲突替代和可回放边界。

## 2. 用户能感知到的结果

- 在“训练闭环 → 长期训练偏好”中确认偏好的长跑星期；
- 可设置可选失效日期、查看当前/被替代/过期/已停用状态，并停用当前偏好；
- 新周计划会在目标允许的训练日范围内优先把长距离课安排到偏好日；
- 如果偏好与当前目标可训练日冲突，目标设置优先，Planning evidence 明确记录“未采用”；
- 偏好改变后，已经预览但尚未激活的旧草案会在服务端重放时被拒绝。

## 3. 新增与修改的主要文件

- `src/runcrew/domain/memory.py`：偏好、写入确认和停用输入契约；
- `src/runcrew/services/athlete_memory.py`：幂等确认、版本替代、归档和到期展示；
- `src/runcrew/storage/models.py` / `repositories.py`：`athlete_preferences` 与结构化检索；
- `src/runcrew/services/training_planning.py`：偏好上下文、计划 Hash、evidence 和长跑日安排；
- `src/runcrew/services/training_operations.py` / `web/server.py`：本地产品 API；
- `src/runcrew/web/static/chat.*`：偏好确认、状态列表和停用交互；
- `src/runcrew/cli.py`：`memory remember-long-run-day/list/archive`；
- `tests/test_athlete_memory.py`：M9-A 专项回归；
- `schemas/training-operations/`：写入和停用 JSON Schema；
- `docs/adr/0020-confirmed-typed-athlete-preference-memory.md`：写入边界决策。

## 4. 关键技术决策

1. v1 只实现 `preferred_long_run_weekday`，不创建万能键值表；
2. API/CLI 都要求显式 `confirmed=true` 或 `--confirm`；
3. 相同值重复提交返回同一版本，新值通过 `supersedes_id` 替代旧版本；
4. 停用使用 `archived`，不硬删除；到期检索自动排除；
5. `TrainingGoal.available_weekdays` 的当前目标约束优先于长期偏好；
6. 偏好进入周计划 `input_hash` 与 evidence，确保个性化仍可回放；
7. 不接入 LLM 自动抽取、向量库或未经确认的健康记忆。

## 5. 验收

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_athlete_memory.py -q
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe memory --help
```

专项 9 个场景通过；全量结果以 `docs/CURRENT_STATE.md` 最新记录为准。测试只使用临时 SQLite 和合成数据，没有读取真实跑步活动或调用外部服务。

应用内浏览器在本次会话中没有可用实例，因此没有把视觉点击验收标成完成；HTTP、DOM、JavaScript 语法和端到端 API 行为已由自动化测试覆盖，页面仍需用户本机刷新后主观复核。

## 6. 已知限制

- 当前只记忆长跑星期，不保存训练时间、回答风格或伤痛标签；
- 普通聊天不会自动提取偏好候选；
- 尚无 Weekly Training Memory 和跨周期 Memory Context Builder；
- 到期状态在读取时投影为 `expired`，底层历史记录保持原始审计 JSON；
- 仍是单用户本地产品，不包含账户系统。

## 7. 下一阶段唯一入口

回到 M8-A2：基于现有闭环与 M9-A 记忆链路制作无私人数据的求职演示包。M9-B 周训练记忆在演示包完成后再启动，避免继续扩大范围。

## 8. 外部数据与费用

没有读取真实 COROS/FIT 私人数据，没有调用 DeepSeek，也没有产生外部费用。
