# 当前状态

> 本文件是项目当前进度的唯一事实来源。任何 AI 开始工作时必须先读本文件。  
> 最后更新：2026-08-08

## 当前里程碑

**M1：真实 COROS 数据竖切——已完成。**

已经可以完成：

```text
COROS 官方授权
→ MCP 握手
→ 获取最近活动列表
→ 解析 COROS 格式化文本
→ 转换为 ActivitySummary
→ 保存原始事件和规范化活动
→ SQLite 幂等更新
→ 输出确定性 summary 复盘
```

## 已验证事实

- Python 3.13 本地环境可运行；
- 自动化测试：9 passed；
- fixture 首次同步插入 2 条；
- fixture 第二次同步插入 0 条、更新 2 条；
- 真实 COROS OAuth + PKCE 成功；
- 真实 `querySportRecords` 成功；
- 真实 COROS 活动已转换并写入本地数据库；
- `activities review --latest --provider coros` 可以输出复盘 JSON；
- Token 未落盘；
- 必要项目文档和 AI 入口已补齐。
- RunCrew 已初始化为独立 Git 仓库，默认分支为 `main`；当前文件尚未创建首次提交。

## 当前已知问题

真实账户测试中，COROS 当前详情类工具返回服务端异常文本：

- `getActivityDetail` 异常；
- `queryActivityLapData` 返回相同异常。

当前系统行为正确：

- 活动列表仍然保存；
- 同步状态记为 `completed_with_warnings`；
- `detail_errors=1`；
- 不伪造分圈和时间序列；
- 复盘明确提示详情数据不足。

## 下一项唯一任务

**M2：实现单条活动的 FIT 详情兜底。**

具体起点：

1. 为 COROS Provider 增加 `queryActivityFitFileDownloadUrls` 调用；
2. 只选择一条活动，避免浪费每日 FIT 下载额度；
3. 将 FIT 保存到 `data/private/fit/`；
4. 选择确定性 FIT 解析库；
5. 映射 session、lap、record 到 `ActivityDetail`；
6. 添加脱敏 fixture 和契约测试；
7. 降级失败时继续保持 summary-only warning。

## 开始下一任务前需要用户确认

FIT URL/文件获取会消耗 COROS 的每日下载额度。在进行真实下载前应向用户说明并确认只下载一条活动。

## 验收命令

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe status
.\.venv\Scripts\runcrew.exe activities review --latest --provider coros
```

## 私有本地状态

- 真实数据库：`data/runcrew.db`，已 Git 忽略；
- 私有调试载荷：`data/private/`，已 Git 忽略；
- 虚拟环境：`.venv/`，已 Git 忽略。

不要在普通文档或 Git 中复制其中的真实活动数值、LabelId、位置和坐标。
