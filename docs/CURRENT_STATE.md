# 当前状态

> 本文件是项目当前进度的唯一事实来源。任何 AI 开始工作时必须先读本文件。  
> 最后更新：2026-08-08

## 当前里程碑

**M2：FIT 详情兜底——已完成。**

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
- 一条由用户从 COROS App 手动导出的真实 FIT 已通过 CRC、session、lap 和 record 解析；
- 真实 FIT 经私有缓存进入完整同步链，验收结果为 `detailed=1, detail_errors=0`；
- 真实活动复盘已输出基于多分圈计算的 `pace_stability` evidence，数据质量为 high。

## 当前已知问题

真实账户测试中，COROS 的自动详情来源仍存在外部限制：

- `getActivityDetail` 异常；
- `queryActivityLapData` 返回相同异常。
- `queryActivityFitFileDownloadUrls` 在参数符合实时 schema 的情况下返回 `isError=true`，没有下发下载 URL；
- 自动 FIT URL 未能验证，但用户手动导出的真实 FIT 已通过私有缓存完成端到端验收。

当前降级行为：

- 活动列表仍然保存；
- 若私有缓存存在，解析真实 FIT 并生成 `ActivityDetail`；
- 若没有缓存且 COROS FIT URL 工具失败，保留 summary 并记录 warning；
- 不伪造分圈和时间序列。

## 下一项唯一任务

**M3：实现 Training Review Skill 的最小可回放竖切。**

具体起点：定义 Skill 的输入/输出 Schema，把现有确定性复盘服务包装成可复用能力；先完成无 LLM 的回放与 evidence 契约，再接入模型。

## 外部额度约束

未来重试 COROS 自动 FIT URL 获取仍会消耗每日下载额度，执行前必须向用户说明并确认只下载一条活动。M3 开发不需要再次下载真实 FIT。

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
