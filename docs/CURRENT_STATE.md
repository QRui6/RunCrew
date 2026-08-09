# 当前状态

> 本文件是项目当前进度的唯一事实来源。任何 AI 开始工作时必须先读本文件。  
> 最后更新：2026-08-09

## 当前里程碑

**M3：Training Review Skill——已完成。**

M1/M2 数据链路已完成；M3 当前可以完成：

```text
目标 Activity + 同来源历史活动 + 可选训练计划
→ 以目标活动时间构建 7/28 天上下文
→ 生成稳定 input_hash
→ 确定性计算训练完成度、负荷变化和训练异常
→ 每条 finding 强制携带 evidence
→ 缺失数据输出 unknown + requires
→ 通过 Skill 和 JSON Schema 暴露给未来 Agent
```

## 已验证事实

- Python 3.13 本地环境可运行；
- 自动化测试：24 passed；
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
- `TrainingReviewRequest` / `TrainingReviewResult` Schema 已定义并导出；
- `review-running-training` Skill 已通过官方 `quick_validate.py`；
- 同一输入会生成相同 `input_hash` 和结果，回放测试已通过；
- 真实 COROS 本地活动已通过 Training Review CLI 回放，缺少计划和负荷历史时正确降级，分圈 evidence 仍然保留。
- 已新增中文《项目实施全景与面试说明》，记录 M0-M3 的技术方案、错误复盘、面试表达和 M4-M6 范围冻结；
- Training Review Skill、UI 元数据和导出 Schema 的说明已中文化。

## 当前已知限制

- `getActivityDetail` 异常；
- `queryActivityLapData` 返回相同异常；
- `queryActivityFitFileDownloadUrls` 在参数符合实时 schema 的情况下返回 `isError=true`，没有下发下载 URL；
- 自动 FIT URL 未能验证，但用户手动导出的真实 FIT 已通过私有缓存完成端到端验收；
- 当前 COROS 规范化活动没有训练负荷字段，因此真实 `load_change` 暂时可能为 `unknown`；
- 训练计划尚未持久化，只能通过 CLI 显式传入距离/时长目标；
- Skill 尚未接入 LLM；当前只输出经过验证的结构化结果，这是 M3 的刻意边界；
- 真实数据库历史活动数量仍少，跨周负荷回放主要由合成 fixture 验证。

当前降级行为：

- 活动列表仍然保存；
- 若私有缓存存在，解析真实 FIT 并生成 `ActivityDetail`；
- 若没有缓存且 COROS FIT URL 工具失败，保留 summary 并记录 warning；
- 不伪造分圈和时间序列。

## 下一项唯一任务

**M4：实现单 Agent 的 Context + Harness + Loop 最小竖切。**

具体起点：定义一次 review run 的状态机和 Trace Schema，让 Agent 只能通过 Training Review Skill 获取结论；加入工具预算、超时、重试、退出条件、故障注入和输出验证。

## 外部额度约束

未来重试 COROS 自动 FIT URL 获取仍会消耗每日下载额度，执行前必须向用户说明并确认只下载一条活动。M3 开发不需要再次下载真实 FIT。

## 验收命令

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe status
.\.venv\Scripts\runcrew.exe activities review --latest --provider coros
.\.venv\Scripts\runcrew.exe training review --latest --provider coros
```

## 私有本地状态

- 真实数据库：`data/runcrew.db`，已 Git 忽略；
- 私有调试载荷：`data/private/`，已 Git 忽略；
- 虚拟环境：`.venv/`，已 Git 忽略。

不要在普通文档或 Git 中复制其中的真实活动数值、LabelId、位置和坐标。
