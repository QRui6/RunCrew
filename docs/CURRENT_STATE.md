# 当前状态

> 本文件是项目当前进度的唯一事实来源。任何 AI 开始工作时必须先读本文件。  
> 最后更新：2026-08-08

## 当前里程碑

**M2：FIT 详情兜底——进行中。**

M1 数据竖切已完成；M2 当前可以完成：

```text
COROS 详情
→ 失败时尝试分圈
→ 再失败时优先读取私有 FIT 缓存
→ 无缓存时请求单条 FIT URL
→ HTTPS 限制、大小上限和超时控制
→ CRC 校验并解析 session/lap/record
→ 转换为 ActivityDetail
→ 全部失败则保留 ActivitySummary + warning
```

## 已验证事实

- Python 3.13 本地环境可运行；
- 自动化测试：19 passed；
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

## 当前已知问题

真实账户测试中，COROS 当前三个详情来源均未成功：

- `getActivityDetail` 异常；
- `queryActivityLapData` 返回相同异常。
- `queryActivityFitFileDownloadUrls` 在参数符合实时 schema 的情况下返回 `isError=true`，没有下发下载 URL；
- 因没有获得真实 FIT，真实分圈复盘尚未验收，不能把 M2 标为完成。

当前系统行为正确：

- 活动列表仍然保存；
- 同步状态记为 `completed_with_warnings`；
- `detail_errors=1`；
- 不伪造分圈和时间序列；
- 复盘明确提示详情数据不足。

## 下一项唯一任务

**完成 M2 的唯一剩余验收：在 COROS FIT 工具恢复后，用一条真实 FIT 做 smoke test。**

验收成功标准：`detailed=1, detail_errors=0`，随后 `activities review` 输出至少 3 个带配速证据的真实 lap。若 COROS 仍返回工具错误，不重复消耗当天额度，只记录服务端原因并等待下次验证。

## 再次真实验收前需要用户确认

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
