# 当前状态

> 本文件是项目当前进度的唯一事实来源。任何 AI 开始工作时必须先读本文件。  
> 最后更新：2026-08-09

## 当前里程碑

**M5-A：单 Agent 离线评测基线——已完成；M5-B 模型选型方案已完成、代码待开始。**

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
- 自动化测试：39 passed；
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

## 当前已知限制

- `getActivityDetail` 异常；
- `queryActivityLapData` 返回相同异常；
- `queryActivityFitFileDownloadUrls` 在参数符合实时 schema 的情况下返回 `isError=true`，没有下发下载 URL；
- 自动 FIT URL 未能验证，但用户手动导出的真实 FIT 已通过私有缓存完成端到端验收；
- 当前 COROS 规范化活动没有训练负荷字段，因此真实 `load_change` 暂时可能为 `unknown`；
- 训练计划尚未持久化，只能通过 CLI 显式传入距离/时长目标；
- 当前评测仍使用确定性 Policy 和脚本化故障；真实 LLM Policy、Token/费用指标和模型调用评测尚未实现；
- DeepSeek 只完成技术选型，尚未配置 API Key、发起付费请求或产生真实模型结果；
- Trace 当前随 CLI JSON 返回，尚未持久化；
- 工具超时会停止 Harness 等待，但已经在线程中开始的同步只读查询不能被强制终止；
- 真实数据库历史活动数量仍少，跨周负荷回放主要由合成 fixture 验证。

当前降级行为：

- 活动列表仍然保存；
- 若私有缓存存在，解析真实 FIT 并生成 `ActivityDetail`；
- 若没有缓存且 COROS FIT URL 工具失败，保留 summary 并记录 warning；
- 不伪造分圈和时间序列。

## 下一项唯一任务

**M5-B：接入一个真实 LLM Policy，并与当前离线基线比较。**

模型候选已经明确为 `deepseek-v4-flash` 非思考模式。具体起点：实现 `DeepSeekReviewPolicy` 的 Mock 契约测试，由用户在本机配置 API Key 和费用上限后只用合成数据做一次真实 Smoke Test；随后在相同 12 个场景上记录动作解析、完成率、Token、费用和延迟。没有对照结果前不拆分多 Agent。

详细边界见 [M5-B：DeepSeek 模型选型与接入方案](M5-B-DeepSeek模型选型与接入方案.md)。

## 外部额度约束

未来重试 COROS 自动 FIT URL 获取仍会消耗每日下载额度，执行前必须向用户说明并确认只下载一条活动。调用 DeepSeek 会产生外部请求和费用，首次真实调用前也必须确认费用上限；M5-A 与本次模型调研均没有调用 COROS、真实 FIT 或 LLM API。

## 验收命令

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe status
.\.venv\Scripts\runcrew.exe activities review --latest --provider coros
.\.venv\Scripts\runcrew.exe training review --latest --provider coros
.\.venv\Scripts\runcrew.exe agent review --latest --provider coros
.\.venv\Scripts\runcrew.exe eval review-agent --output data\private\evals\m5-baseline.json
```

## 私有本地状态

- 真实数据库：`data/runcrew.db`，已 Git 忽略；
- 私有调试载荷：`data/private/`，已 Git 忽略；
- 虚拟环境：`.venv/`，已 Git 忽略。

不要在普通文档或 Git 中复制其中的真实活动数值、LabelId、位置和坐标。
