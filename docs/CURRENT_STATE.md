# 当前状态

> 本文件是项目当前进度的唯一事实来源。任何 AI 开始工作时必须先读本文件。  
> 最后更新：2026-08-09

## 当前里程碑

**M5-A、M5-B1 与 M5-B2 已完成；M5-B3 完整 12 场景真实模型对照待开始。**

M1-M4 数据、Skill 和单 Agent Harness 已完成；M5-A 当前可以完成：

```text
版本化合成评测套件
→ 运行正常任务、韧性、护栏和预算共 12 个场景
→ 复用真实 ReviewAgentHarness 和 Training Review Service
→ 注入瞬时错误、超时、非法输出和非法 Policy 动作
→ 校验终态、Schema、事实一致性和工具是否越权执行
→ 聚合完成率、护栏通过率、调用成本、延迟和退出原因
→ 生成 suite_hash 和可比较评测报告
```

## 已验证事实

- Python 3.13 本地环境可运行；
- 自动化测试：50 passed；
- fixture 首次同步插入 2 条；
- fixture 第二次同步插入 0 条、更新 2 条；
- 真实 COROS OAuth + PKCE 成功；
- 真实 `querySportRecords` 成功；
- 真实 COROS 活动已转换并写入本地数据库；
- `activities review --latest --provider coros` 可以输出复盘 JSON；
- Token 未落盘；
- 必要项目文档和 AI 入口已补齐。
- RunCrew 已初始化为独立 Git 仓库，默认分支为 `main`；首次提交为 `d157a78`。
- GitHub 私有仓库：`https://github.com/QRui6/RunCrew`；本地 `main` 跟踪 `origin/main`。
- 官方 `garmin-fit-sdk` 21.212.0 可在 Python 3.13 解码和编码 FIT；
- 合成 FIT 可稳定映射 1 个 session、4 个 lap 和 12 个 record；
- FIT HTTPS、50 MB 上限、过期 URL、CRC、私有缓存和失败降级均有自动化测试；
- `queryActivityFitFileDownloadUrls` 的实时 schema 已核对，单活动参数为 `labelId + sportType`。
- 一条由用户从 COROS App 手动导出的真实 FIT 已通过 CRC、session、lap 和 record 解析；
- 真实 FIT 经私有缓存进入完整同步链，验收结果为 `detailed=1, detail_errors=0`；
- 真实活动复盘已输出基于多分圈计算的 `pace_stability` evidence，数据质量为 high。
- M2 已通过 GitHub PR #1 合并到 `main`；
- M3 GitHub PR #2 与 M4 GitHub PR #3 已依次合并到 `main`；
- M5-A GitHub PR #4 已创建，base 为 `main`；
- `TrainingReviewRequest` / `TrainingReviewResult` Schema 已定义并导出；
- `review-running-training` Skill 已通过官方 `quick_validate.py`；
- 同一输入会生成相同 `input_hash` 和结果，回放测试已通过；
- 真实 COROS 本地活动已通过 Training Review CLI 回放，缺少计划和负荷历史时正确降级，分圈 evidence 仍然保留。
- 中文《项目实施全景与面试说明》已记录 M0-M5-A 的技术方案、错误复盘、面试表达和后续范围冻结；
- Training Review Skill、UI 元数据和导出 Schema 的说明已中文化。
- `ReviewAgentRunRequest` / `ReviewAgentRunResult`、Action、Context、Trace、Error 和 Budget Schema 已定义；
- 单 Agent 只允许调用 `review_running_training`，未知工具、参数篡改和未确认调用会被拒绝；
- 步骤、逻辑工具调用、重试、单次工具超时和整次 Run 超时均有明确预算；
- 瞬时错误、工具超时、非法输出、越权、缺少确认和预算耗尽均通过故障注入测试；
- `runcrew agent review` 可以返回经过校验的训练复盘、终态、退出原因、预算和 Trace；
- Agent Run 输入输出 JSON Schema 已导出，并由测试防止与 Pydantic 模型漂移。
- fixture 端到端 Agent Smoke Test 已通过：`succeeded / completed`，2 个策略步骤、1 次逻辑工具调用、1 次工具尝试。
- `review-agent-eval/1.0` 已包含 12 个无私人数据场景，覆盖任务、韧性、护栏和预算；
- 离线基线 12/12 通过，正常任务完成率、护栏通过率、Schema 通过率和事实一致率均为 100%；
- 被护栏拒绝后底层工具执行数为 0，平均逻辑工具调用 0.5833，平均工具尝试 0.75；
- 评测套件和报告 Schema 已导出，`suite_hash` 可标识同一批评测输入；
- `runcrew eval review-agent` 可运行评测，报告只允许写入 `data/private/`。
- M5-B 已核对 DeepSeek 官方模型、Tool Calls、思考模式和 Schema 约束；推荐 `deepseek-v4-flash` 非思考模式，选型与接入方案已形成中文文档。
- `DeepSeekReviewPolicy` 已实现受控 Context、非思考 Tool Calls、Action 解析和有限 API 重试；
- DeepSeek API Key 由环境变量和 `SecretStr` 管理，只允许发送到官方 HTTPS 主机；
- 模型 Tool Call 仍经过 Pydantic、白名单、确认、参数一致性和预算校验，Mock 参数篡改时底层工具执行数为 0；
- Policy Trace 只记录模型名、模式、尝试数、解析错误、耗时和 Token 等白名单元数据；
- Evaluation Report Schema 已升级至 1.1，可按用例和总报告统计模型调用、API 尝试、动作解析错误、缓存 Token、输入/输出/思考 Token 和模型耗时；
- `runcrew eval deepseek-smoke` 已实现，只运行 `complete_training_review` 合成用例，并在读取 Key 前强制要求 `--confirm-paid-api` 与 `--max-estimated-cost-usd`；
- 费用按 `deepseek-pricing/2026-08-09` 估算并写入 Trace/报告，超过 Policy 上限时停止后续动作；该上限是本地后验停止门，不是供应商账单硬上限；
- DeepSeek Policy 与 CLI 的零费用测试已覆盖 Mock 契约、安全门、单用例 Smoke 和完整 Suite 费用门；全量 50 项测试通过。
- 真实 `deepseek-v4-flash` 非思考请求已连通，首次 Tool Call 参数通过 Action Schema 和 Harness 校验；
- 第一次真实 Smoke 共 2 次模型请求、2369 Token、估算 0.00036106 美元，动作解析错误为 0；
- 第二轮模型重复请求工具，Harness 在执行前以工具预算拦截，底层工具实际只执行 1 次；
- 已把第二轮上下文修正为标准 `assistant(tool_calls) → tool(tool_call_id, result)` 消息链，Mock 回归通过。
- 修复后第二次真实 Smoke 达到 `succeeded / completed`，事实一致性为 True，业务工具只执行 1 次；
- 成功 Smoke 共 2 次模型请求、2549 Token、0 个动作解析错误，估算费用 0.00016426 美元，模型累计耗时 4663.993 ms；
- 成功尝试输入 Token 中 1664 个命中缓存、630 个未命中缓存；两次真实报告均保存在 `data/private/evals/`。
- `runcrew eval deepseek-suite` 已实现：复用同一 12 场景 Suite，并以跨用例共享费用对象限制整套评测总成本；尚未执行真实模型调用。

## 当前已知限制

- `getActivityDetail` 异常；
- `queryActivityLapData` 返回相同异常；
- `queryActivityFitFileDownloadUrls` 在参数符合实时 schema 的情况下返回 `isError=true`，没有下发下载 URL；
- 自动 FIT URL 未能验证，但用户手动导出的真实 FIT 已通过私有缓存完成端到端验收；
- 当前 COROS 规范化活动没有训练负荷字段，因此真实 `load_change` 暂时可能为 `unknown`；
- 训练计划尚未持久化，只能通过 CLI 显式传入距离/时长目标；
- 当前正式基线仍使用确定性 Policy 和脚本化故障；DeepSeek 只有单用例真实结果，尚无完整模型质量结论；
- DeepSeek 已有单用例成功报告，但尚无完整 Suite 的真实模型基线；
- 评测已经支持 Token、动作解析、带版本单价的费用估算和共享费用门，但完整 12 场景模型对照尚未运行；
- 本地费用门只能在收到真实 usage 后停止后续动作，不能阻止第一笔请求，也不能替代 DeepSeek 账户侧余额控制；
- 单用例真实 DeepSeek Loop 已验收，但还不能把一个成功用例描述成完整模型稳定性结论；
- Trace 当前随 CLI JSON 返回，尚未持久化；
- 工具超时会停止 Harness 等待，但已经在线程中开始的同步只读查询不能被强制终止；
- 真实数据库历史活动数量仍少，跨周负荷回放主要由合成 fixture 验证。

当前降级行为：

- 活动列表仍然保存；
- 若私有缓存存在，解析真实 FIT 并生成 `ActivityDetail`；
- 若没有缓存且 COROS FIT URL 工具失败，保留 summary 并记录 warning；
- 不伪造分圈和时间序列。

## 下一项唯一任务

**M5-B3：运行完整真实 LLM Suite，并与当前离线基线比较。**

运行已经实现的 `runcrew eval deepseek-suite`，在同一 `review-agent-eval/1.0` 套件上记录所有默认 Policy 场景的完成率、终态、Token、费用和延迟；脚本化护栏场景继续验证 Harness。没有完整对照结果前不拆分多 Agent。

详细边界见 [M5-B：DeepSeek 模型选型与接入方案](M5-B-DeepSeek模型选型与接入方案.md)。

## 外部额度约束

未来重试 COROS 自动 FIT URL 获取仍会消耗每日下载额度，执行前必须向用户说明并确认只下载一条活动。调用 DeepSeek 会产生外部请求和费用；Smoke 和完整 Suite 都要求命令行显式确认费用上限。M5-B3 只发送合成评测数据，不发送真实 COROS/FIT 内容。

## 验收命令

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe status
.\.venv\Scripts\runcrew.exe activities review --latest --provider coros
.\.venv\Scripts\runcrew.exe training review --latest --provider coros
.\.venv\Scripts\runcrew.exe agent review --latest --provider coros
.\.venv\Scripts\runcrew.exe eval review-agent --output data\private\evals\m5-baseline.json
.\.venv\Scripts\runcrew.exe eval deepseek-suite --help
```

## 私有本地状态

- 真实数据库：`data/runcrew.db`，已 Git 忽略；
- 私有调试载荷：`data/private/`，已 Git 忽略；
- 虚拟环境：`.venv/`，已 Git 忽略。

不要在普通文档或 Git 中复制其中的真实活动数值、LabelId、位置和坐标。
