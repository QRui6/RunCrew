# RunCrew 实施状态

> 这是 M0-M3 的详细实施快照。最新进度以 [CURRENT_STATE.md](CURRENT_STATE.md) 为准，阶段历史以 [PROGRESS.md](PROGRESS.md) 为准。

> 更新时间：2026-08-09

## 当前里程碑：Training Review Skill

状态：**已完成并通过 fixture 与真实 COROS 本地回放验收。**

已经形成以下闭环：

```text
规范化目标活动 + 最近历史 + 可选计划
  → Training Context Builder
  → input_hash + 7/28 天窗口
  → completion / load change / anomaly
  → TrainingReviewResult Schema
  → review-running-training Skill
```

## 已实现模块

| 模块 | 位置 | 作用 |
|---|---|---|
| 领域模型 | `src/runcrew/domain` | Activity、Lap、Health、Recovery、Review Schema |
| Provider 协议 | `src/runcrew/providers/base.py` | 隔离 COROS、FIT、Keep 等数据来源 |
| COROS OAuth | `src/runcrew/providers/coros/oauth.py` | 动态注册、PKCE、本地回调，不记录密码 |
| MCP 客户端 | `src/runcrew/providers/coros/mcp.py` | initialize、tools/call、SSE/JSON 响应 |
| COROS 解析器 | `src/runcrew/providers/coros/parser.py` | 嵌套 JSON 与官方格式化文本的确定性解析 |
| COROS Provider | `src/runcrew/providers/coros/provider.py` | 活动列表、详情/分圈降级链 |
| FIT 下载与解析 | `src/runcrew/providers/fit` | 私有缓存、下载边界、CRC、session/lap/record 映射 |
| SQLite 存储 | `src/runcrew/storage` | activities、raw events、sync runs |
| 同步服务 | `src/runcrew/services/sync.py` | 幂等、部分成功、warning 隔离 |
| 活动复盘 | `src/runcrew/services/activity_review.py` | 无 LLM、证据驱动的确定性分析 |
| Training Context | `src/runcrew/services/training_context.py` | 历史窗口、聚合和回放哈希 |
| Training Review | `src/runcrew/services/training_review.py` | 完成度、负荷变化和异常 finding |
| Training Skill | `skills/review-running-training` | Agent 工作流、Schema 和证据边界 |
| CLI | `src/runcrew/cli.py` | init-db、status、sync、activity review、training review |

## 实际验收结果

### 自动化测试

```text
24 passed
```

覆盖：

- 时区强校验；
- 缺省配速派生；
- 双层 JSON 与 COROS 文本协议解析；
- COROS Provider 列表/详情管道；
- 确定性复盘；
- SQLite 幂等同步；
- 详情端点失败不回滚活动列表。
- 合成 FIT 编解码、CRC 和 Domain 映射；
- FIT 下载缓存、大小限制和过期链接；
- COROS 详情/分圈失败后的 FIT 降级编排。
- Training Review 输入输出 Schema 与 JSON Schema 漂移检查；
- 时间锚定回放、缺失数据降级、负荷变化和异常规则；
- Training Review CLI。

### CLI 离线验收

```text
首次 fixture 同步：inserted=2
第二次 fixture 同步：inserted=0, updated=2
```

证明 `provider + external_id` 去重规则有效。

### 真实 COROS 验收

```text
fetched=1, inserted=0, updated=1, detailed=1, detail_errors=0
```

真实活动已通过手动 FIT 私有缓存生成 detail，并成功通过 Training Review Skill 本地回放。具体活动数值只保存在本地数据库，不写入此文档。

## 当前已知限制

### 1. COROS 详情类工具当前异常

真实测试中：

- `querySportRecords` 正常；
- `getActivityDetail` 返回 COROS 服务端异常提示；
- 降级调用 `queryActivityLapData` 返回相同异常提示。
- `queryActivityFitFileDownloadUrls` 参数符合实时 schema，但工具返回 `isError=true`。

没有私有 FIT 缓存时的 RunCrew 行为：

1. 活动列表先独立提交；
2. 详情错误计入 `detail_errors`；
3. 同步状态为 `completed_with_warnings`；
4. 不伪造分圈和时间序列；
5. 复盘明确返回“数据不足”。

### 2. Token 暂不持久化

每次 COROS 同步都需要重新授权。下一阶段若增加刷新令牌缓存，必须使用系统凭据存储或等价的加密方案，不允许明文写入 `.env`、SQLite 或日志。

### 3. 数据库尚未引入迁移工具

当前通过 SQLAlchemy `create_all` 创建结构。Schema 稳定后应加入 Alembic 迁移，避免手工修改本地数据库。

## 当前里程碑：FIT 详情兜底

状态：**已完成离线与真实 FIT 端到端验收。**

已经实现：

1. 调用 `queryActivityFitFileDownloadUrls` 获取指定活动的短期下载地址；
2. 下载 FIT 到 Git 忽略的私有目录；
3. 解析 session、lap、record 数据；
4. 映射为 `ActivityDetail`、`Lap`、`MetricPoint`；
5. 让 Provider 降级链变为：

```text
getActivityDetail
  → queryActivityLapData
  → FIT download + deterministic parser
  → summary-only warning
```

6. 用官方 Encoder 生成无坐标合成 FIT 建立回归测试；
7. 增加下载额度、缓存、超时、链接过期和失败清理策略。

COROS 自动 URL 工具未返回下载地址，因此用户从官方 App 手动导出同一条活动的 FIT 并放入私有缓存。真实同步得到 `detailed=1, detail_errors=0`，复盘成功产生基于多分圈的 evidence。自动 URL 获取保留为外部服务已知限制。

## 已完成里程碑：Training Review Skill

已经实现：

1. `TrainingReviewRequest` 和 `TrainingReviewResult` Pydantic Schema；
2. 以目标活动时间为锚点的历史上下文；
3. `input_hash + ruleset_version` 回放身份；
4. 训练完成度、七天负荷变化和训练异常三类 finding；
5. 每条 finding 的强制 evidence；
6. 缺少计划、负荷或配速基线时的 `unknown + requires`；
7. 项目 Skill、JSON Schema、CLI 和 5 项专项测试；
8. 规则计算与未来 LLM narrative 的职责隔离。

## 常用命令

```powershell
# 运行全部测试
.\.venv\Scripts\python.exe -m pytest

# 查看数据库状态
.\.venv\Scripts\runcrew.exe status

# 离线同步
.\.venv\Scripts\runcrew.exe sync --provider fixture --days 30 --detail-limit 1

# 真实 COROS 同步
.\.venv\Scripts\runcrew.exe sync --provider coros --days 30 --detail-limit 1

# 查看 COROS 最新活动的确定性复盘
.\.venv\Scripts\runcrew.exe activities review --latest --provider coros

# 运行 Training Review Skill
.\.venv\Scripts\runcrew.exe training review --latest --provider coros
```

## 安全约束

- `.env`、SQLite 数据库、`data/private` 均已加入 `.gitignore`；
- OAuth state 和 PKCE verifier 仅存在于进程内；
- Access Token/Refresh Token 不写入日志和测试结果；
- 私有失败载荷只有显式传入 `--debug-payload` 时才保存；
- 原始运动数据不得提交到公开仓库。
