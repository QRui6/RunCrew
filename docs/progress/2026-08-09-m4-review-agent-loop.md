# M4：训练复盘单 Agent Loop

- 日期：2026-08-09
- 状态：完成
- 分支：`feat/m4-review-agent-loop`
- 基线：M3 PR #2 最新提交 `b5c43f6`
- Pull Request：GitHub PR #3，基线为 M3 分支，必须在 PR #2 之后合并

## 1. 本阶段目标

在不扩展新业务 Agent 的前提下，把 M3 Training Review Skill 放入一个可测试、可追踪、不会无限运行的单 Agent Harness，完成 Context + Harness + Loop 最小竖切。

## 2. 用户能感知到的结果

用户可以运行：

```powershell
runcrew agent review --latest --provider fixture
runcrew agent review --latest --provider coros
```

输出除了原有训练复盘，还包含：

- 本次 `run_id`；
- 成功、失败、超时或预算耗尽状态；
- 明确退出原因；
- 步骤、工具调用和重试消耗；
- 从开始、动作选择、权限检查、工具调用、输出验证到结束的完整 Trace。

## 3. 主要新增与修改文件

| 文件 | 作用 |
|---|---|
| `src/runcrew/domain/agent.py` | Run、Context、Action、Trace、Error 和 Budget Schema |
| `src/runcrew/harness/review_agent.py` | 单 Agent 状态循环和统一执行边界 |
| `src/runcrew/services/training_review.py` | 增加从规范化活动 Store 执行 Skill 的统一入口 |
| `src/runcrew/storage/repositories.py` | 增加按 RunCrew 内部活动 ID 查询 |
| `src/runcrew/cli.py` | 增加 `agent review` 命令 |
| `tests/test_review_agent.py` | 成功路径和故障注入测试 |
| `skills/review-running-training/references/agent-run-*.schema.json` | Agent Run 输入输出 JSON Schema |
| `docs/adr/0007-bounded-review-agent-loop.md` | 状态机与框架选择决策 |

## 4. Context Engineering

策略层只能看到 `ReviewAgentContext`：

```text
固定目标和指令版本
+ 用户 TrainingReviewRequest
+ 工具白名单与确认要求
+ 已校验的上一轮观察
+ 剩余步骤和工具预算
```

它看不到 COROS 原始文本、完整 SQLite、外部活动 ID、GPS 和 Token。这样既压缩上下文，也阻断策略层绕过业务边界。

## 5. Harness Engineering

Harness 统一负责：

- 仅允许 `review_running_training`；
- 当前工具只读，默认无需确认；确认门本身有测试；
- 默认 4 步、1 次逻辑工具调用、1 次重试；
- 每次工具尝试 5 秒、整次 Run 15 秒；
- 只重试 `RetryableToolError` 和超时；
- 永久错误、越权、参数篡改和非法输出立即停止；
- Trace 不保存异常正文和私人载荷。

## 6. Loop Engineering

默认循环为：

```text
created
→ planning
→ call_tool
→ permission check
→ calling_tool
→ observation / retry / failure
→ planning
→ finish
→ validating
→ completed
```

退出条件共有：

- `completed`；
- 策略动作非法；
- 工具越权或缺少确认；
- 工具永久失败或重试耗尽；
- 工具或整次 Run 超时；
- 工具输出 Schema 无效；
- 在获得观察前提前结束；
- 步骤或工具预算耗尽。

## 7. 故障注入与错误解决

通过注入异步 Tool 和 Policy 测试替身覆盖：

| 故障 | 预期行为 |
|---|---|
| 首次瞬时失败 | 记录重试事件，第二次成功；异常正文不进入 Trace |
| 工具持续超时 | 按配置重试后以 `tool_timeout` 停止 |
| Policy 持续无响应 | 整次 Run 超时后以 `run_timeout` 停止 |
| 返回不完整字典 | `TrainingReviewResult` 校验失败，拒绝输出 |
| 请求未知工具 | 权限检查失败，工具不会执行 |
| 修改用户目标活动参数 | 参数完整性检查失败，工具不会执行 |
| 工具要求确认但未确认 | 以 `confirmation_required` 停止 |
| 只给 1 步或 0 次工具预算 | 在对应边界以预算耗尽停止 |

实施中首次 CLI 测试返回 `tool_failure / NameError`。原因是把 Repository 执行入口加入 `training_review.py` 后漏导入 `build_training_context`。补齐显式导入后，单文件 10 项测试和全部 34 项测试通过。这个错误说明 Trace 中保留异常类型而不暴露异常正文，既能定位代码类别，也不会把潜在私人信息写入输出。

## 8. 关键策略与亮点

- 没有把普通函数调用包装后冒充 Agent，而是实现了动作协议、循环、状态和终止条件；
- 默认确定性 Policy 与未来 LLM Policy 共用接口，模型不是 Harness 的硬依赖；
- 业务规则仍在 M3 Service，Agent 不能修改 finding、level 和 evidence；
- 逻辑调用预算与重试预算分开统计，避免把一次瞬时重试误当成第二次业务决策；
- Trace 使用相对时间和稳定错误代码，方便回放、测试和后续指标统计；
- Schema、CLI、测试和 Skill 文档同步更新，防止接口漂移。

## 9. 验收结果

```powershell
\.venv\Scripts\python.exe -m pytest tests\test_review_agent.py
# 10 passed

\.venv\Scripts\python.exe scripts\verify.py
# 34 passed

\.venv\Scripts\runcrew.exe sync --provider fixture --days 30 --detail-limit 1 --db data\private\m4-smoke.db
\.venv\Scripts\runcrew.exe agent review --latest --provider fixture --db data\private\m4-smoke.db
# status=succeeded, termination_reason=completed, steps=2, tool_calls=1, attempts=1
```

Skill 已通过官方 `quick_validate.py`；Agent Run Schema 与 Pydantic 模型的一致性由自动化测试验证。

## 10. 已知限制

- 默认 Policy 是确定性的，真实 LLM 策略尚未接入；
- 尚未统计 Token 和模型费用；
- Trace 只随命令输出，尚未进入数据库；
- Python 线程中已经开始的同步只读查询不能被强制中止，但 Harness 会停止等待并返回超时；
- 仍然只有一个业务 Skill，没有多 Agent。

## 11. 下一阶段唯一入口

先建立小型历史回放评测集和指标，接入一个实现相同 Action Schema 的真实 LLM Policy，并与确定性 Policy 比较成功率、非法动作率、工具调用数、延迟和费用。没有评测证据前不拆分 Agent。

## 12. 外部额度与私人数据

- 本阶段不需要重新调用 COROS，也不消耗 FIT 下载额度；
- 自动化测试只使用合成 fixture；
- 没有读取或提交 `data/private/` 和真实 SQLite 内容。
