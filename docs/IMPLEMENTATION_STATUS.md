# RunCrew 实施状态

> 这是 2026-08-08 数据竖切阶段的详细快照。最新进度以 [CURRENT_STATE.md](CURRENT_STATE.md) 为准，阶段历史以 [PROGRESS.md](PROGRESS.md) 为准。

> 更新时间：2026-08-08

## 当前里程碑：真实数据竖切

状态：**已完成并通过真实 COROS 账户验收。**

已经形成以下闭环：

```text
COROS OAuth + PKCE
  → MCP initialize
  → querySportRecords
  → 官方格式化文本解析
  → ActivitySummary Schema 校验
  → 原始事件 + 规范化活动分层保存
  → SQLite 幂等 upsert
  → 确定性活动复盘 JSON
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
| SQLite 存储 | `src/runcrew/storage` | activities、raw events、sync runs |
| 同步服务 | `src/runcrew/services/sync.py` | 幂等、部分成功、warning 隔离 |
| 活动复盘 | `src/runcrew/services/activity_review.py` | 无 LLM、证据驱动的确定性分析 |
| CLI | `src/runcrew/cli.py` | init-db、status、sync、list、review |

## 实际验收结果

### 自动化测试

```text
9 passed
```

覆盖：

- 时区强校验；
- 缺省配速派生；
- 双层 JSON 与 COROS 文本协议解析；
- COROS Provider 列表/详情管道；
- 确定性复盘；
- SQLite 幂等同步；
- 详情端点失败不回滚活动列表。

### CLI 离线验收

```text
首次 fixture 同步：inserted=2
第二次 fixture 同步：inserted=0, updated=2
```

证明 `provider + external_id` 去重规则有效。

### 真实 COROS 验收

```text
fetched=1, inserted=1, detailed=0, detail_errors=1
status=completed_with_warnings
```

真实活动已进入数据库，并成功生成 summary 级确定性复盘。具体活动数值只保存在本地数据库，不写入此文档。

## 当前已知限制

### 1. COROS 详情类工具当前异常

真实测试中：

- `querySportRecords` 正常；
- `getActivityDetail` 返回 COROS 服务端异常提示；
- 降级调用 `queryActivityLapData` 返回相同异常提示。

RunCrew 当前行为：

1. 活动列表先独立提交；
2. 详情错误计入 `detail_errors`；
3. 同步状态为 `completed_with_warnings`；
4. 不伪造分圈和时间序列；
5. 复盘明确返回“数据不足”。

### 2. Token 暂不持久化

每次 COROS 同步都需要重新授权。下一阶段若增加刷新令牌缓存，必须使用系统凭据存储或等价的加密方案，不允许明文写入 `.env`、SQLite 或日志。

### 3. 数据库尚未引入迁移工具

当前通过 SQLAlchemy `create_all` 创建结构。Schema 稳定后应加入 Alembic 迁移，避免手工修改本地数据库。

## 下一里程碑：FIT 详情兜底

目标：在不依赖 COROS 详情文本工具的情况下生成 `ActivityDetail`。

实施顺序：

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

6. 用一份脱敏后的最小 FIT fixture 建立回归测试；
7. 增加下载额度、超时、链接过期和重试策略。

FIT 下载会消耗 COROS 的每日额度，因此开发时只选择一条活动验证，不做批量下载。

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
```

## 安全约束

- `.env`、SQLite 数据库、`data/private` 均已加入 `.gitignore`；
- OAuth state 和 PKCE verifier 仅存在于进程内；
- Access Token/Refresh Token 不写入日志和测试结果；
- 私有失败载荷只有显式传入 `--debug-payload` 时才保存；
- 原始运动数据不得提交到公开仓库。
