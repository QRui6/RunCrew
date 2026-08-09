# RunCrew 项目实施全景与面试说明

> 用途：帮助项目作者、后续开发者和 AI 清楚理解 RunCrew 为什么这样设计、各阶段已经做了什么、遇到过什么问题、下一步允许做什么。  
> 最后更新：2026-08-09  
> 当前事实来源仍以 `docs/CURRENT_STATE.md` 为准；本文负责解释完整过程和面试叙事。

说明：类名、字段名、命令和 Skill 唯一名称继续使用英文，保证代码、JSON 和工具兼容；所有面向人的解释、流程、提示和字段描述使用中文。

## 1. 项目当前处于什么程度

一句话结论：

> RunCrew 已经完成“真实跑步数据接入 → 统一数据模型 → 私有存储 → FIT 详情恢复 → 确定性复盘 → 可回放 Training Review Skill → 有界单 Agent Loop → 版本化评测基线 → DeepSeek Policy → v1.1 同 Hash 完整模型对照”。多 Agent 没有评测必要性，产品化界面尚未完成。

当前里程碑是 **M5 全部完成，下一阶段 M6-A 本地只读演示界面**。

| 能力 | 当前状态 | 说明 |
|---|---|---|
| COROS OAuth + MCP 接入 | 已完成 | 可以授权并查询真实活动列表 |
| 活动统一 Schema | 已完成 | COROS/fixture/FIT 转换为 `ActivitySummary` / `ActivityDetail` |
| SQLite 持久化 | 已完成 | 保存规范化活动、原始事件和同步记录 |
| 幂等同步 | 已完成 | 使用 `provider + external_id` 去重更新 |
| 详情失败隔离 | 已完成 | 详情失败不回滚活动摘要 |
| FIT 详情兜底 | 已完成 | 支持私有缓存、CRC 校验和 session/lap/record 解析 |
| 单次活动确定性复盘 | 已完成 | 输出配速稳定性及 evidence |
| Training Review Skill | 已完成 | 输出完成度、负荷变化、训练异常三类 finding |
| 可回放上下文 | 已完成 | 使用目标活动时间、`input_hash` 和规则版本 |
| LLM Policy / 自然语言总结 | 部分完成 | DeepSeek 适配器和 Mock 已完成，真实 API 与自然语言总结未完成 |
| Agent 状态机、Trace、预算和重试 | 已完成 | 支持权限、确认、重试、两级超时、故障注入和明确终态 |
| 单 Agent 离线评测 | 已完成并扩展 | 12 个场景达到确定性基线，Report 1.1 已支持模型调用、解析、Token 和耗时指标 |
| 多 Agent 编排 | 未实现 | 只有 M5 评测证明单 Agent 不够时才条件式增加 |
| Web 界面和简历演示 | 未实现 | 属于 M6 |
| 伤病、营养、睡眠完整 Agent | 不在当前范围 | 防止重新变成“大而全”项目 |

## 2. 当前完整技术链路

```text
COROS 官方服务
  → OAuth 2.0 Authorization Code + PKCE
  → MCP initialize / tools/call
  → CorosActivityProvider
      ├─ 活动详情
      ├─ 分圈数据
      └─ FIT URL / 私有 FIT 缓存
  → COROS Parser / Garmin FIT SDK
  → ActivitySummary / ActivityDetail
  → Sync Service
  → raw_provider_events + activities + sync_runs
  → Training Context Builder
  → Deterministic Training Review Service
  → review-running-training Skill
  → 通过 JSON Schema 校验的 TrainingReviewResult
  → DeterministicReviewPolicy / DeepSeekReviewPolicy
  → Review Agent Harness
  → Action / Observation Loop
  → 权限 + 确认 + 预算 + 重试 + 超时 + Trace
  → 通过 Agent Run Schema 校验的终态输出
  → 12 场景 Agent Evaluation Runner
  → Suite Hash + 任务/护栏/事实/成本/延迟指标
```

各层职责：

| 层 | 负责什么 | 明确不负责什么 |
|---|---|---|
| Provider | OAuth、MCP、厂商格式和 FIT 获取 | 不做训练判断 |
| Parser | 字段、单位、时间和二进制格式转换 | 不写数据库、不调用 LLM |
| Domain | 定义 RunCrew 统一业务对象 | 不知道 COROS、HTTP、SQLite |
| Storage | 表结构、查询、幂等保存 | 不解释训练意义 |
| Service | 确定性业务规则和流程组合 | 不解析厂商原始文本 |
| Skill | 指导 Agent 选择数据、调用 Service、验证证据 | 不重新计算指标 |
| Harness | 状态、权限、确认、预算、Trace、重试和验证 | 不替代领域规则、不直接读取 Provider 原始数据 |

## 3. 用户目前可以使用哪些功能

### 3.1 同步活动

```powershell
runcrew sync --provider coros --days 30 --detail-limit 1
```

功能：

- 打开 COROS 官方授权页；
- 获取最近跑步活动；
- 转换并写入 SQLite；
- 重复同步时更新原记录；
- 尝试补齐一条详情；
- 详情失败时保留摘要并记录 warning。

### 3.2 查看活动

```powershell
runcrew activities list
runcrew activities review --latest --provider coros
```

功能：

- 查看已经规范化的活动；
- 查看单次活动摘要；
- 在有三个以上有效分圈时计算配速变异系数；
- 返回 `message + evidence + confidence`。

### 3.3 运行 Training Review Skill

```powershell
runcrew training review --latest --provider coros
```

已知训练计划时：

```powershell
runcrew training review --latest --provider coros `
  --planned-distance-km 8 --planned-duration-minutes 45
```

固定返回：

1. `training_completion`：实际训练与用户提供计划的完成比例；
2. `load_change`：最近七天与此前七天的训练负荷变化；
3. `training_anomaly`：分圈波动或同类型历史配速偏差。

如果缺少计划、训练负荷或历史活动，系统返回 `unknown + requires`，而不是猜测。

### 3.4 运行训练复盘 Agent

```powershell
runcrew agent review --latest --provider coros
```

在原有 Training Review 结果之外，固定返回：

- `run_id`、`status` 和 `termination_reason`；
- 步骤、逻辑工具调用和工具尝试数量；
- 从开始、策略动作、权限检查、工具尝试、输出验证到退出的 Trace；
- 失败时稳定错误代码和是否值得重试，不输出潜在敏感的异常正文。

当前默认 Policy 是确定性的。它用于证明 Harness 和 Loop 的工程边界，不等于已经调用真实大模型。

### 3.5 运行单 Agent 离线评测

```powershell
runcrew eval review-agent `
  --output data/private/evals/m5-baseline.json
```

评测不读取真实跑步数据库，也不调用 COROS 或 LLM。它执行 12 个版本化场景，输出正常任务完成率、护栏通过率、Schema 通过率、事实一致率、工具调用/尝试、P95 延迟和退出原因分布。报告只能写入 Git 忽略的 `data/private/`。

## 4. 各阶段实施过程

### M0：COROS MCP 接入 Spike

#### 目标

先证明数据源真实可用，再决定是否围绕它建设项目。

#### 技术实现

- Bearer 授权挑战与 OAuth 元数据发现；
- 动态 OAuth 客户端注册；
- Authorization Code + PKCE；
- MCP `initialize`；
- MCP `tools/list` 和只读工具调用；
- 确认中国区服务地址和返回格式。

#### 实施策略

- 先写一次性 Spike，不急着搭完整工程；
- 验证活动、健康、体能和恢复等代表性工具；
- 确认数据格式后再决定 Python 项目结构。

#### 关键发现

- COROS MCP 可以连接；
- 工具主要返回 `content[].text`，不能假设一定有 `structuredContent`；
- 返回内容可能是格式化文本或多层 JSON 字符串；
- 设备码授权不适合作为当前默认登录流程。

#### 阶段亮点

避免在接口可用性未知时先做复杂 Agent，降低方向错误成本。

#### 面试表达

> 我没有一开始就搭多 Agent，而是先做数据接入 Spike，验证 OAuth、MCP 协议、工具清单和真实返回格式，以此决定后续架构。

### M1：真实数据竖切

#### 目标

把“能调用 COROS”变成“真实数据可以稳定保存、重复同步和确定性使用”。

#### 技术实现

- Pydantic 领域模型：`ActivitySummary`、`ActivityDetail`、`Lap`、`MetricPoint`；
- `ActivityProvider` 统一接口；
- COROS OAuth 客户端和 MCP 客户端；
- 确定性 COROS Parser；
- SQLAlchemy + SQLite；
- `activities`、`raw_provider_events`、`sync_runs` 三张表；
- 基于 `provider + external_id` 的幂等 upsert；
- Typer CLI；
- fixture 离线回归测试；
- 单次活动确定性复盘。

#### 关键策略

##### Provider 隔离

业务层只看 RunCrew Domain，不知道 COROS 字段和 MCP 工具名。未来增加其他来源时不重写复盘逻辑。

##### 原始数据与规范化数据分层

- 原始数据用于审计、重解析和排查格式变化；
- 规范化数据用于业务规则和 Skill；
- 两者通过来源 ID 和 hash 建立证据链。

##### 部分成功

活动列表先提交，详情逐条补全。详情失败时：

- 保留 summary；
- 记录 `detail_errors`；
- 标记 `completed_with_warnings`；
- 不把 summary 伪装成 detail。

#### 遇到的问题

| 问题 | 处理方式 |
|---|---|
| COROS 返回格式化文本 | 编写确定性文本 Parser，不让 LLM 临时解释 |
| 响应可能被 JSON 编码多次 | 增加最多四层的 JSON 解包 |
| 详情和分圈工具返回服务异常 | 采用部分成功语义，先保存摘要 |
| 保存 Refresh Token 会扩大风险 | M1 不持久化 Token，每次重新授权 |

#### 阶段亮点

- 真实数据而不是纯 Mock；
- 失败隔离而不是“全成功或全失败”；
- 原始数据和规范化数据可审计；
- 规则先于 LLM，便于测试。

#### 面试表达

> M1 的重点不是页面，而是建立可靠数据边界。我用 Provider 隔离厂商格式，用原始事件和规范化活动双层存储支持审计，用部分成功事务避免详情故障导致整批数据丢失。

### M2：FIT 详情兜底

#### 目标

当 COROS 详情和分圈工具不可用时，通过真实 FIT 恢复分圈和秒级记录。

#### 技术实现

- Garmin 官方 `garmin-fit-sdk`；
- FIT 文件识别与 CRC 完整性校验；
- session、lap、record 到 Domain 的确定性映射；
- HTTPS 强制、60 秒超时、50 MB 大小上限；
- 过期 URL 和 HTTP 错误分类；
- `data/private/fit/` 私有缓存；
- 使用外部活动 ID 的 SHA-256 前缀作为缓存文件名；
- 无效缓存删除；
- Garmin Encoder 生成无坐标合成 FIT fixture；
- COROS 详情 → 分圈 → FIT → summary warning 的降级链。

#### 关键策略

- 先查缓存再申请 FIT URL，减少每日额度消耗；
- 不把真实 FIT 放进测试目录或 Git；
- 二进制解析完全交给确定性 SDK，不让 LLM 处理；
- 下载成功但 CRC/Schema 失败时不保留污染缓存。

#### 遇到的问题

| 问题 | 原因判断 | 解决方案 |
|---|---|---|
| COROS `getActivityDetail` 失败 | 外部服务异常 | 继续尝试分圈和 FIT |
| `queryActivityLapData` 同样失败 | 外部服务异常 | 进入 FIT 降级 |
| FIT URL 工具返回 `isError=true` | 参数已核对，推断为服务端或权限问题 | 保留摘要；支持用户手动导出 FIT |
| 第一次错误只有通用 `isError` | 本地错误可观测性不足 | 保留并脱敏服务端错误文本 |
| 手动 FIT 如何关联活动 | 缓存需要对应 external ID | 使用哈希缓存路径关联最新活动 |

#### 真实验收

- 用户从 COROS App 手动导出一条真实 FIT；
- FIT 通过 CRC、session、lap、record 解析；
- 私有缓存进入完整同步链；
- 同步得到 `detailed=1, detail_errors=0`；
- 复盘成功产生真实多分圈 evidence。

具体私人指标不写入项目文档。

#### 阶段亮点

- 不依赖单一脆弱详情接口；
- 有缓存、配额、安全和失败语义；
- 合成 fixture 与真实 Smoke Test 结合；
- 外部服务失败时仍可演示完整系统。

#### 面试表达

> COROS 的详情工具真实环境不稳定，我没有伪造详情，而是设计了三级降级链。FIT 使用官方 SDK 做 CRC 和消息解析，真实文件进入 Git 忽略的私有缓存，测试则由 Encoder 生成无坐标合成文件。

### M3：Training Review Skill

#### 目标

把活动复盘从普通 Service 变成 Agent 可以稳定复用、验证和回放的 Skill。

#### 技术实现

- `TrainingReviewRequest` 输入 Schema；
- `TrainingReviewResult` 输出 Schema；
- JSON Schema 自动导出；
- 以目标活动时间为锚点的 Context Builder；
- 最近七天与此前七天窗口聚合；
- `input_hash + ruleset_version` 回放身份；
- 三类固定 finding；
- 每条 finding 强制非空 evidence；
- `unknown + requires` 缺失数据契约；
- `skills/review-running-training/SKILL.md`；
- `agents/openai.yaml` Skill UI 元数据；
- CLI 与 fixture/真实本地回放测试。

#### 为什么不直接接 LLM

如果让 LLM 同时负责计算和表达，会出现：

- 同一输入的结论不稳定；
- 阈值无法单元测试；
- 缺失数据容易被语言掩盖；
- 更换模型会改变业务判断。

因此当前职责是：

```text
确定性 Service：计算指标、选择 level、产生 evidence
Skill：选择数据、调用 Service、验证 Schema
未来 LLM：只改写已验证结论，不新增事实
```

#### 三类 finding

| finding | 输入 | 数据不足时 |
|---|---|---|
| training_completion | 实际距离/时长 + 用户提供计划 | `unknown`，要求 planned session |
| load_change | 连续两个七天窗口的训练负荷 | `unknown`，要求两个窗口都有 load |
| training_anomaly | 三个以上分圈或三个历史同类活动 | `unknown`，要求分圈或历史基线 |

#### 遇到的问题

| 问题 | 解决方案 | 工程启示 |
|---|---|---|
| pytest 无法访问 Windows 用户 Temp | 将 `--basetemp` 固定到 Git 忽略的 `data/private/pytest` | 验证环境也要可复现 |
| PowerShell 展开 `$review-running-training` | 使用单引号并通过官方生成器重新生成 | Shell 转义是 Harness 风险 |
| Skill 校验器在 venv 缺少 PyYAML | 使用已有依赖的系统 Python 执行官方校验器 | 区分项目依赖与开发工具依赖 |
| 中文 SKILL.md 被生成器按 GBK 读取失败 | 使用 `python -X utf8` 运行生成器 | 中文 Windows 必须显式处理编码 |
| 真实 COROS 没有训练负荷历史 | 输出 `unknown + requires`，不伪造趋势 | 缺数据策略属于产品能力 |

#### 阶段亮点

- Skill 不是一段大 Prompt，而是稳定能力契约；
- 同一输入可回放；
- 数据质量和业务结论分离；
- 规则与 LLM 职责清晰；
- Skill 和 Schema 已中文化，便于项目作者理解。

#### 面试表达

> 我把 Skill 设计成确定性 Service 的编排层，而不是让大模型自由分析。输入、输出、缺失数据和 evidence 都有 Schema，回放使用输入哈希和规则版本，因此模型升级不会破坏基础判断。

### M4：训练复盘单 Agent Loop

#### 目标

把 M3 的直接 Skill 调用放入一个真正有动作选择、观察反馈、权限、预算、Trace 和退出条件的有限循环，同时保持只有一个 Agent 和一个业务 Skill。

#### 技术实现

- `ReviewAgentRunRequest` / `ReviewAgentRunResult`；
- `ReviewAgentContext` 分层上下文；
- `call_tool` / `finish` 可判别联合 Action Schema；
- `ToolPermission` 只读白名单和确认门；
- `AgentTraceEvent`、`AgentRunError`、`AgentBudgetUsage`；
- `ReviewAgentHarness` 有限状态循环；
- 默认 `DeterministicReviewPolicy`；
- 瞬时错误和超时有限重试；
- 单次工具超时与整次 Run 超时；
- 工具输出 Schema 和目标活动一致性校验；
- `runcrew agent review` CLI；
- Agent Run 输入输出 JSON Schema。

#### 分层上下文策略

Policy 只接收：固定目标、指令版本、用户结构化请求、允许工具、已经校验的 Observation 和剩余预算。它看不到 COROS 原始文本、完整数据库、外部活动 ID、GPS 或 Token。

```text
固定指令层
+ 用户请求层
+ 工具权限层
+ 已校验观察层
+ 运行预算层
```

#### Loop 与退出条件

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

策略非法、越权、缺少确认、参数篡改、工具失败、超时、非法输出、提前结束和预算耗尽都会进入明确终态，不会无限循环。

#### 遇到的问题

| 问题 | 解决方案 | 工程启示 |
|---|---|---|
| Repository 执行入口首次运行出现 `NameError` | 补齐 `build_training_context` 显式导入 | Trace 需要保留可定位的异常类型 |
| 异常正文可能包含私人数据 | Trace 只记录稳定错误代码和异常类名 | 可观测性不等于保存全部异常文本 |
| 重试是否消耗第二次业务调用额度 | 分开统计逻辑工具调用和工具尝试 | 预算语义必须明确，否则指标无法解释 |
| 同步数据库查询无法被线程强制终止 | Harness 停止等待并返回超时，只允许只读工具 | 超时边界与底层取消能力要分别说明 |

#### 故障注入

自动化测试覆盖首次瞬时失败后恢复、连续超时、非法输出、未知工具、缺少确认和步骤预算耗尽。所有失败路径都返回结构化错误，不使用不完整自然语言结果兜底。

#### 阶段亮点

- 不把一次函数调用包装后冒充 Agent，而是实现动作—观察循环；
- Policy 与 Harness 解耦，未来真实 LLM 复用同一动作协议；
- 工具只能通过白名单进入，Agent 不能直接访问 COROS；
- Trace、错误、预算和终态均有 Schema；
- 52 项测试可以离线验证成功、故障路径、模型适配器契约和评测退化，不依赖 API Key。

#### 面试表达

> M4 我没有立即依赖 Agent 框架，而是先把最小状态机写清楚。Policy 只能输出 call_tool 或 finish，Harness 负责权限、确认、预算、重试、超时和输出校验；工具结果作为 Observation 回到下一轮，所有路径都有脱敏 Trace 和明确终态。默认确定性 Policy 用于建立离线基线，未来 LLM 只替换动作选择层。

### M5-A：单 Agent 离线评测基线

#### 目标

在接入真实 LLM 前回答三个问题：Harness 是否稳定、故障时是否安全、未来模型结果是否可以与统一基线比较。

#### 技术实现

- `review-agent-eval/1.1` 版本化 Suite；
- 12 个任务、韧性、护栏和预算场景；
- Case、Metrics、Report Pydantic Schema；
- Suite/Report JSON Schema 导出与漂移测试；
- 合成完整活动和缺数活动；
- 可替换 `default_policy_factory`；
- Tool 与 Policy 故障注入；
- 确定性事实对象级对比；
- 工具是否在护栏后真实执行的旁路检查；
- `suite_hash` 和私有 JSON 报告。

#### 为什么故障用例不算“任务失败”

超时、非法输出和越权用例的目标本来就是验证系统能否安全退出。因此报告分开统计：正常任务看 `task_completion_rate`，护栏看 `guardrail_pass_rate`，所有场景再看 `expectation_pass_rate`。这样不会为了追求表面上的 100% 成功率而吞掉错误。

#### 当前基线

```text
12/12 场景满足预期
task_completion_rate=1.0
guardrail_pass_rate=1.0
schema_valid_rate=1.0
fact_integrity_rate=1.0
prohibited_tool_execution_count=0
```

#### 阶段亮点

- 不是只测试最终文本，而是测试终态、事实、预算和底层工具副作用；
- 题集用哈希标识，未来不同模型必须在相同输入上比较；
- 评测器已经预留真实 LLM Policy 注入口，但当前不产生 API 费用；
- 报告默认私有，避免未来真实评测数据误提交。

#### 面试表达

> 接 LLM 前我先建立了 12 场景离线评测基线，把正常任务完成和异常安全退出分开计分。除了 Schema 和最终状态，我还比较 Agent 输出是否修改确定性工具事实，并检测越权被拒绝后底层工具是否仍执行。评测套件有稳定 hash，后续 LLM 或多 Agent 必须在同一题集上对照。

### M5-B1：DeepSeek Policy 适配器与 Mock 契约

#### 目标

只改变动作选择层，在零费用、无真实数据外发的条件下先证明 DeepSeek 请求、响应、重试、脱敏和评测指标能够进入现有 Harness。

#### 技术实现

- `DeepSeekReviewPolicy` 实现现有 `ReviewAgentPolicy` 协议；
- `HttpxDeepSeekTransport` 调用官方 `/chat/completions`；
- 固定 `deepseek-v4-flash`、非思考模式和普通 Tool Calls；
- 环境变量、`SecretStr` 和官方 HTTPS 主机限制；
- Tool Call 参数 JSON 解码与现有 Action Schema 校验；
- 网络、429/5xx、资源不足、截断和非法 JSON 的有限 API 重试；
- 模型元数据通过固定白名单进入 Trace；
- Evaluation Report 1.1 聚合模型调用、API 尝试、解析错误、Token 和模型耗时；
- 使用带版本的 DeepSeek 单价估算费用，并在超过本地上限时停止后续动作；
- 9 项 Mock 契约、安全、费用门与 Smoke CLI 测试；
- 只运行一个合成用例、要求显式付费确认和费用上限的 Smoke 命令。

#### 为什么模型重试不放进工具重试

模型 API 失败发生在动作生成阶段，业务工具重试发生在动作已经通过权限检查之后。两者的费用、故障源和安全含义不同，因此分别实现、分别统计，避免把“两次模型请求”误说成“两次训练复盘工具调用”。

#### 当前验证结果

```text
DeepSeek Mock 完整 Loop：call_tool → observation → finish
模型参数篡改：permission_denied，底层工具执行数 0
Policy Token/解析/耗时：进入 Trace 和 Evaluation Report 1.1
全量测试：48 passed
真实 API 请求：0
```

#### 面试表达

> M5-B1 我让 DeepSeek 只替换 Policy，没有改 Harness。模型用普通 Tool Calls 表达动作，参数仍由 Pydantic、白名单、确认门和一致性校验兜底；API 重试与业务工具重试分开统计。为了保护隐私，Trace 只接收 Token、耗时和解析状态等白名单元数据。当前先用官方格式 Mock 验证了完整 Loop，下一步才做单条合成数据的真实调用。

### M5-B2：第一次真实合成 Smoke 与兼容修复

第一次真实请求成功完成鉴权、非思考模型调用和首轮 Tool Call，动作参数没有解析错误。工具返回 Observation 后，第二轮模型再次请求相同工具，最终被 Harness 的工具预算拦截：

```text
policy_calls=2
api_attempts=2
action_parse_errors=0
total_tokens=2369
estimated_cost_usd=0.00036106
tool_attempts_used=1
terminal=budget_exhausted / step_budget_exhausted
```

根因不是 DeepSeek 接口失败，而是第一版把 Observation 放进一个新的 Context JSON，却没有按标准 Tool Calls 对话回传上一轮 assistant Tool Call 和对应 Tool Result。模型没有获得明确的工具完成语义。

修复后第二轮消息改为：

```text
system
→ user(initial bounded context)
→ assistant(tool_calls=[...])
→ tool(tool_call_id=..., validated observation)
```

Mock 回归会检查消息角色顺序、`tool_call_id`、Observation 和剩余预算。第二次真实同用例复验已经达到：

```text
terminal=succeeded / completed
fact_integrity=True
tool_attempts_used=1
policy_calls=2
action_parse_errors=0
total_tokens=2549
estimated_cost_usd=0.00016426
```

成功尝试有 1664 个输入 Token 命中缓存、630 个未命中缓存，所以虽然总 Token 略高，估算费用仍低于第一次失败尝试。当前可以声称单用例真实 LLM Loop 已通过，但还不能把它扩展为完整模型稳定性结论。

#### 这次失败的工程价值

- 证明格式正确的 Mock 不等于真实模型理解了多轮语义；
- Harness 在模型重复动作时将第二次工具执行数保持为 0；
- Token、费用、动作解析和工具执行指标能够区分模型行为问题与接口问题；
- 失败没有被吞掉或伪装成成功结果。

## 5. Agent 工程技术目前做到哪里

| Agent 工程概念 | 当前实现 | 当前结论 |
|---|---|---|
| MCP | RunCrew 作为客户端连接 COROS MCP | 已实践真实协议、OAuth 和工具调用 |
| Skill | `review-running-training` | 已完成第一个可复用 Skill |
| Context Engineering | 领域上下文 + 有界 Agent Context，只暴露请求、权限、合法观察和剩余预算 | 已有分层和裁剪，尚无 Token 级压缩 |
| Harness Engineering | 统一 Run、权限、确认、预算、重试、两级超时、验证和 Trace | M4 最小竖切已完成 |
| Loop Engineering | `call_tool → observation → finish` 有限状态循环和明确退出条件 | M4 最小竖切已完成 |
| LLM | `deepseek-v4-flash` v1.1 同 Hash 对照12/12通过 | 当前动作协议不需要升级 Pro |
| Multi-Agent | 尚未实现 | 必须由评测证明必要性 |
| Evaluation | 12场景 v1.1 Suite、52项测试、Suite Hash、任务/护栏/事实/Token/费用/延迟指标 | 确定性与 DeepSeek 均12/12，M5-B3完成 |

## 6. 贯穿项目的核心设计原则

### 6.1 先确定性，后生成式

字段解析、单位转换、CRC、统计指标、阈值和 confidence 都由代码负责。LLM 不弥补本应由 Schema 和规则解决的问题。

### 6.2 每个判断都要有 evidence

不能只输出“最近训练不太稳定”，还要说明使用了多少分圈、变异系数是多少、比较窗口是什么。

### 6.3 缺失数据是一等状态

`unknown` 不是失败，而是明确告诉用户当前不能判断，以及还需要什么数据。

### 6.4 外部失败不能污染内部状态

列表成功、详情失败时保留列表；FIT 无效时不写 detail；单条失败不回滚整批。

### 6.5 隐私默认收紧

- Token 不落盘；
- 真实数据库、FIT 和调试 payload 不进 Git；
- 文档不记录真实活动 ID、坐标和个人指标；
- 错误信息脱敏 URL 和长 ID。

### 6.6 不为展示名词而增加 Agent

只有当单 Agent 评测暴露职责冲突、上下文超限或不同权限边界时，才拆分多 Agent。

## 7. 当前没有实现的功能

以下内容不能在面试中说成已经完成：

- DeepSeek Policy 只有 Mock 验证，没有真实 API 结果、LLM 生成说明、费用预算和模型行为对照；
- Trace 尚未持久化或做成可视化看板；
- 没有伤病诊断、营养处方和医疗建议；
- 没有睡眠、HRV、疼痛 Check-in 的完整数据闭环；
- 没有训练计划数据库；
- 没有 Keep Provider；
- 没有 Web/移动端界面；
- 没有多 Agent；
- 没有线上部署；
- COROS 自动 FIT URL 仍未真实验证成功；
- 没有 Token 加密缓存和数据库迁移工具。

## 8. 后续范围冻结规则

为了防止项目再次扩大，后续必须遵守：

### M4 已按冻结范围完成一个 Review Agent Loop

已经实现：

- 单 Agent；
- 只使用 `review-running-training` 一个业务 Skill；
- Run State Schema；
- Trace/Event Schema；
- 工具调用预算；
- 超时与有限重试；
- 故障注入；
- 输出 Schema 验证；
- 明确退出条件；

真实 LLM narrative 没有实现，因为它是可选项，不影响 Harness 和 Loop 的 M4 验收。

M4 禁止顺手增加：

- Keep、Strava 等新 Provider；
- 伤病、营养和睡眠 Agent；
- 多 Agent；
- Web UI；
- 自动修改 COROS 训练计划；
- 向量数据库或复杂 RAG；
- 云部署。

### M5 先做单 Agent 评测和真实 LLM Policy

M5 只允许增加：

- [x] 不含私人数据的离线回放评测集；
- [x] 完成率、护栏、工具调用数、重试数和延迟指标；
- [x] 一个实现相同 Action Schema 的 DeepSeek Policy 适配器；
- [x] Token、模型调用、API 尝试、动作解析错误和耗时指标结构；
- [x] 受显式确认和费用门保护的单条合成 Smoke 命令；
- [x] 带价格版本的 Token 费用估算结构；
- [ ] 实际执行单条合成上下文的真实 DeepSeek Smoke；
- [ ] LLM 与确定性 Policy 的对照结果；
- [ ] 是否需要多 Agent 的书面决策门。

### 只有满足条件才做多 Agent

必须先有评测证据证明至少一项成立：

- 单 Agent 上下文超限；
- 训练分析与风险审查需要不同工具权限；
- 单 Agent 在职责冲突测试中稳定失败；
- 拆分后关键指标明显改善。

否则继续保持单 Agent。

### M6 才做演示与简历包装

- Trace 展示；
- 关键成功率和稳定性指标；
- 最小演示界面；
- 架构图；
- 简历描述和面试问答。

## 9. 面试讲解模板

### 30 秒版本

> RunCrew 是我基于真实跑步数据做的 Agent 工程项目。当前完成了 COROS MCP 接入、统一活动 Schema、FIT 详情降级、可回放 Training Review Skill、带权限和预算的单 Agent Loop，以及 12 场景离线评测基线。训练指标由确定性 Service 计算，Agent 只通过白名单 Skill 获取结论；评测同时检查事实一致性和越权后工具是否执行。

### 2 分钟版本

> 我是跑步用户，所以选择了一个能长期产生真实反馈的场景。项目先通过 Spike 验证 COROS OAuth 和 MCP，再建立 Provider、Domain、Storage、Service 分层。真实环境中 COROS 详情接口不稳定，我设计了详情、分圈、FIT、summary warning 的降级链，并用 Garmin 官方 SDK 做 CRC 和消息解析。之后我把训练完成度、负荷变化和异常判断做成确定性 Service，再通过 Skill 和 JSON Schema 暴露。M4 增加单 Agent Loop：Policy 只能输出 call_tool 或 finish，Harness 统一做白名单、确认、预算、重试、超时、校验和 Trace。M5-A 又建立 12 个版本化场景，把正常任务和异常安全退出分开计分，并检查模型层是否修改工具事实、护栏后底层工具是否仍执行。真实 LLM 后续只替换 Policy 层，并在同一题集上与确定性基线比较。

### 最值得讲的三个难点

1. **外部服务不稳定**：设计部分成功和多级降级，而不是吞错或伪造详情；
2. **Agent 输出可信度**：把计算放在确定性 Service，Skill 只编排和验证；
3. **可验证 Agent 评测**：用版本化场景、Suite Hash、事实一致性和工具副作用检查衡量编排质量。

### 面试官可能追问

#### 为什么不用 LangChain/LangGraph？

当前只有一个 Agent、一个工具和两类动作，显式 Python 状态机更容易看清权限、预算和终止语义，也更适合故障注入。若后续评测出现持久化状态、并行分支或人工审批图明显复杂化，再用数据决定是否引入 LangGraph。

#### 为什么现在还没有 LLM？

因为如果基础指标都交给 LLM，无法判断模型错误还是数据错误。当前先建立确定性 ground truth，后续 LLM 只负责解释，这也为评测提供标准答案。

#### 确定性 Policy 还能算 Agent 吗？

当前已经有有界上下文、动作选择、工具观察、再次决策、输出验证和终止条件，因此是一个最小 Agent Loop；但 Policy 不是大模型，不能声称“LLM 已经自主规划”。它的价值是先把 Harness 建成可测试基线，之后接入 LLM 时能够区分模型问题和运行时问题。

#### 为什么不用多个 Agent？

多 Agent 会增加上下文传递、延迟、成本和失败面。项目要求先证明单 Agent 存在职责冲突，再拆分。

#### COROS 接口失败是否说明项目不可用？

不会。活动摘要可以部分成功保存，详情有 FIT 私有缓存和手动导出兜底；外部错误会记录 warning，不会污染已有数据。

#### 项目目前最大的不足是什么？

真实历史数据仍少、COROS 训练负荷未映射、训练计划未持久化；3个非法动作护栏场景也是脚本化注入，不是模型对抗安全评分。现在可以描述为“单 Agent、Harness、Loop 和真实模型同题评测已经完成”，但不能描述为生产上线、多 Agent 系统、医疗诊断或复杂自主规划平台。

## 10. 代码与文档导航

| 想了解什么 | 位置 |
|---|---|
| 项目目标和范围 | `docs/PROJECT_CONTEXT.md` |
| 当前唯一进度 | `docs/CURRENT_STATE.md` |
| 完整实施过程和面试说明 | 本文 |
| 系统分层和数据流 | `docs/ARCHITECTURE.md` |
| 阶段验收 | `docs/ROADMAP.md` |
| 历史阶段记录 | `docs/progress/` |
| 技术决策原因 | `docs/adr/` |
| AI 开发入口 | `AGENTS.md` |
| Training Review Skill | `skills/review-running-training/SKILL.md` |
| Activity Domain | `src/runcrew/domain/activity.py` |
| Training Review Domain | `src/runcrew/domain/training_review.py` |
| Agent Run Domain | `src/runcrew/domain/agent.py` |
| Context Builder | `src/runcrew/services/training_context.py` |
| 训练复盘规则 | `src/runcrew/services/training_review.py` |
| 单 Agent Harness 与 Loop | `src/runcrew/harness/review_agent.py` |
| DeepSeek Policy 适配器 | `src/runcrew/policies/deepseek.py` |
| 评测 Suite 与 Schema | `evals/review_agent/` |
| Agent Evaluation Domain | `src/runcrew/domain/evaluation.py` |
| 离线评测运行器 | `src/runcrew/evaluation/review_agent.py` |
| 统一验证入口 | `scripts/verify.py` |

## 11. 当前下一步

M5-B3 已完成，下一任务是 M6-A 本地只读演示界面：

```text
[已完成] 增加受确认和共享总费用门保护的完整 Suite 命令
→ [已完成] 第一次完整运行 12/12 满足预期，但发现 Suite Hash 漂移
→ [已完成] v1.0 同 Hash 复跑，发现1秒预算导致网络模型统一超时
→ [已完成] 升级 v1.1，为全部 Policy 固定15秒预算并建立新基线
→ [已完成] DeepSeek v1.1 同 Hash 复跑12/12
→ [下一步] 展示 Activity → Skill → Agent Loop → Trace → Evaluation 对照
→ 脚本化异常/护栏场景继续复用真实 Harness
→ 记录完成率、终态、Token、费用、延迟和事实一致性
→ 与确定性 Policy 基线比较
→ 用评测证据决定是否需要多 Agent
```

在评测证明单 Agent 存在职责冲突以前，不扩展新业务 Agent。
