# M7-E Coach 多 Agent 版本化评测

日期：2026-08-13

状态：完成

## 1. 本阶段目标

为已实现的 Coach 多职责编排建立可回放、可比较的版本化离线评测，量化正常业务、故障恢复、权限/交接护栏、预算与批准前 stale 防护，而不是只依赖分散的单元测试或演示成功。

## 2. 用户与面试可感知的结果

现在可以运行：

```powershell
.\.venv\Scripts\runcrew.exe eval coach-agent `
  --output data\private\evals\coach-agent-v1.0.json
```

命令使用18个无私人数据场景运行真实 Coach Harness，并生成带固定 Suite Hash 的报告。确定性基线结果为18/18：任务、韧性、护栏、批准防护、Schema、事实、血缘和用户确认边界均为100%，被护栏拒绝后错误执行节点数为0。

## 3. 新增/修改文件

- `src/runcrew/domain/coach_evaluation.py`：Suite、Case、Report 与聚合指标 Schema；
- `src/runcrew/evaluation/coach_agent.py`：真实 Harness 运行、合成节点、故障注入、判断与聚合；
- `evals/coach_agent/cases.json`：18个版本化场景；
- `evals/coach_agent/cases.schema.json`、`report.schema.json`：防漂移 JSON Schema；
- `scripts/export_coach_evaluation_schemas.py`：Schema 导出；
- `src/runcrew/cli.py`：新增 `eval coach-agent`；
- `tests/test_coach_evaluation.py`：版本、基线、失败检测、Schema 和私有报告路径测试；
- `docs/adr/0019-versioned-coach-agent-evaluation.md`：评测复用真实 Harness 与产品边界的决策。

同时修正《项目实施全景与面试说明》中把多 Agent、训练计划数据库和 Check-in 误写为尚未实现的旧表述。

## 4. 场景与指标

18个场景分为：

- 任务3项：低风险完成、中风险减量、高风险休息；
- 韧性4项：瞬时重试、节点超时、非法节点 Schema、永久失败；
- 护栏8项：缺反馈、红旗升级、Handoff 篡改、错误权限、跨目标输出、Recovery 血缘篡改、非法 Policy 动作、提前结束；
- 预算2项：节点调用预算和步骤预算；
- 审核1项：真实 SQLite 中计划先变化，批准旧草案被重放标记 stale。

报告指标包括预期通过率、任务完成率、韧性/护栏/审核通过率、Schema/事实/血缘一致率、确认边界率、错误节点执行数、平均节点调用/尝试、P95 和退出原因分布。

## 5. 技术策略与亮点

### 不创建评测旁路

正常和故障场景直接调用 `CoachOrchestratorHarness`，只注入确定性的节点输入输出。评测器不自行模拟路由、权限、预算或 Trace，因此测到的是实际产品编排内核。

### 把跨 Agent 事实分成三层验证

- `fact_integrity`：最终采用的 Execution/Recovery/Plan 内容没有偏离合成节点事实；
- `lineage_integrity`：Handoff 连续且 Recovery `input_hash/recommendation/plan_action` 未在 Plan 节点被改写；
- `confirmation_boundary`：减量/休息必须产生草案并停在 `persisted=false, approved=false`。

### 把写入安全纳入 Suite

`stale_approval_replay_blocked` 不使用 Mock，而是在临时 SQLite 中运行真实 `TrainingOperationsService`：Coach 先生成草案，用户先修改计划并提升 revision，再批准旧草案；系统必须保留用户的新状态、不创建旧提案并返回 stale。

## 6. 验收结果

```text
suite_version: coach-agent-eval/1.0
suite_hash: f1bc86ec92be4aa317b033dd469b6c48d6f0f7c959ce106bc750072d731b8451
passed: 18/18
average_node_calls: 1.2778
average_node_attempts: 1.3889
prohibited_node_execution_count: 0
```

专项测试：`5 passed`。

全量测试：`130 passed`。

完整项目验证：`scripts/verify.py` 通过。

## 7. 实施中的错误与解决方案

首轮专项测试在 Windows 清理 `approval_stale` 临时目录时失败，报错为 SQLite 文件仍被占用。原因不是业务断言失败，而是评测同时创建了种子 `Database` 和产品 Service 的两个 Engine，离开临时目录前没有释放连接池。修复为在 `finally` 中显式 `dispose()` 两个 Engine，随后复跑通过。没有使用 `ignore_errors` 掩盖资源泄漏。

## 8. 已知限制

- 当前评测对象是确定性 Coach Policy，不是 DeepSeek Coach Policy；
- Policy/越权场景是脚本化故障注入，证明 Harness 能拦截，不等于真实模型提示注入安全；
- 节点业务事实来自合成结果，真实跨周数据量仍有限；
- P95 受真实 SQLite stale 场景和本机性能影响，只用于回归观察；
- 还没有人工偏好、自然语言协作质量或线上并发评测。

## 9. 下一阶段唯一入口

**M8-A：把已经完成的技术链路整理为可复现的求职演示包，先产出架构图、训练闭环时序图和一条不依赖私人数据的演示脚本。**

M6-A3b 真实 DeepSeek 8轮聊天仍是待补模型验收，不阻塞 M8-A。

## 10. 数据与外部额度

本阶段只使用合成数据和临时 SQLite，没有读取用户真实活动，没有调用 COROS 或 DeepSeek，没有产生外部费用。评测报告写入 `data/private/`，未提交 Git。
