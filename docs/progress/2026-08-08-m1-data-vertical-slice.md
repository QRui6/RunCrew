# M1：真实数据竖切

## 目标

把“能调用 COROS”变成“可以稳定保存和使用跑步数据”，暂不依赖 LLM。

## 普通用户视角的结果

系统现在能够：

1. 打开 COROS 官方登录授权页；
2. 获取最近的跑步记录；
3. 把厂商文本转换成 RunCrew 自己的数据格式；
4. 保存到本地数据库；
5. 重复同步时更新旧记录而不是产生重复数据；
6. 生成一份有数据证据的基础复盘；
7. 详情服务异常时保留已经成功获得的活动，不整批失败。

## 新增的主要文件

### 项目与环境

- `pyproject.toml`
- `.gitignore`
- `.env.example`
- `README.md`

### 领域模型

- `src/runcrew/domain/activity.py`
- `src/runcrew/domain/health.py`
- `src/runcrew/domain/recovery.py`
- `src/runcrew/domain/review.py`

### Provider

- `src/runcrew/providers/base.py`
- `src/runcrew/providers/fixture.py`
- `src/runcrew/providers/coros/oauth.py`
- `src/runcrew/providers/coros/mcp.py`
- `src/runcrew/providers/coros/parser.py`
- `src/runcrew/providers/coros/provider.py`

### 存储与服务

- `src/runcrew/storage/models.py`
- `src/runcrew/storage/database.py`
- `src/runcrew/storage/repositories.py`
- `src/runcrew/services/sync.py`
- `src/runcrew/services/activity_review.py`
- `src/runcrew/cli.py`

### 测试

- `tests/fixtures/coros_activities.json`
- `tests/test_domain.py`
- `tests/test_coros_parser.py`
- `tests/test_coros_provider.py`
- `tests/test_review.py`
- `tests/test_sync.py`
- `tests/test_sync_resilience.py`

## 验收

```text
pytest: 9 passed
fixture 首次同步: inserted=2
fixture 第二次同步: inserted=0, updated=2
真实 COROS 同步: fetched=1, inserted=1
详情服务异常: detail_errors=1，状态 completed_with_warnings
```

具体真实活动指标不写入阶段文档。

## 已知问题

COROS 的 `getActivityDetail` 和 `queryActivityLapData` 在真实测试时返回相同服务端异常提示，因此当前只有真实 summary，尚无真实 lap/time series。

## 下一入口

M2：用一条 FIT 文件补齐真实 `ActivityDetail`。真实下载会消耗每日额度，执行前需要用户确认。

