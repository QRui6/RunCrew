# Changelog

本项目使用阶段化变更记录。当前处于早期开发阶段，尚未发布稳定版本。

## 2026-08-09

### Added

- 增加训练复盘单 Agent 的 Run、Context、Action、Trace、Error 和 Budget Schema；
- 增加只允许一个只读 Skill 的 Agent Harness 与 `call_tool → observation → finish` 有限循环；
- 增加工具白名单、确认门、步骤/调用预算、有限重试、两级超时和结构化退出原因；
- 增加 `runcrew agent review` CLI 和 Agent Run 输入输出 JSON Schema；
- 增加瞬时错误、超时、非法输出、越权、缺少确认和预算耗尽的故障注入测试；
- 增加 Training Review 输入、计划、窗口、finding 和结果 Schema；
- 增加以目标活动时间为锚点的 7/28 天 Context Builder 和稳定输入哈希；
- 增加训练完成度、七天负荷变化和训练异常三类 evidence-backed 规则；
- 增加 `review-running-training` Skill、JSON Schema 和 CLI；
- 增加缺失数据降级、回放、负荷异常、Schema 漂移和 CLI 测试。
- 中文化 Training Review Skill、UI 元数据和 JSON Schema 字段说明；
- 增加《RunCrew 项目实施全景与面试说明》，记录各阶段方案、亮点、错误、解决方案和范围冻结规则。

### Verified

- M4 单 Agent 成功路径和故障路径通过 10 项专项测试；
- 全部自动化测试增至 34 项；
- fixture 端到端 Agent CLI 验收成功，Trace 完整记录 2 步策略决策和 1 次工具调用；
- M2 通过 PR #1 合并到 `main`；
- 24 项自动化测试通过；
- Skill 官方校验器通过；
- 一条真实 COROS 本地活动成功回放，缺失计划/负荷历史时没有编造结论。

### Known Issues

- 当前使用确定性 Policy，真实 LLM Policy、Token/费用预算和模型评测尚未实现；
- Agent Trace 尚未持久化；
- COROS 训练负荷尚未进入规范化活动；
- 训练计划尚未持久化；

## 2026-08-08

### Added

- 创建 RunCrew Python 项目和本地 `.venv`；
- 增加 Activity、Health、Recovery 和 Review 领域模型；
- 增加 ActivityProvider 协议与 fixture Provider；
- 增加 COROS OAuth + PKCE、MCP 客户端和格式化文本解析；
- 增加 SQLite activities、raw events、sync runs；
- 增加幂等同步与详情错误隔离；
- 增加确定性活动复盘；
- 增加 CLI：`init-db`、`status`、`sync`、`activities list/review`；
- 增加 9 项自动化测试；
- 增加 AI 项目入口、当前状态、路线图、架构、ADR、进展索引和安全文档；
- 增加统一自检脚本 `scripts/verify.py`。
- 初始化独立 Git 仓库，默认分支为 `main`。
- 创建首次提交并推送至 GitHub 私有仓库 `QRui6/RunCrew`。
- 增加 Garmin 官方 FIT SDK、确定性 session/lap/record 映射和 CRC 校验；
- 增加 COROS“详情 → 分圈 → FIT → summary warning”降级链；
- 增加 HTTPS、大小、超时、过期 URL、私有缓存和无效缓存清理；
- 增加不含位置的合成 FIT fixture 与相关契约测试，总测试数增至 19；
- 增加 COROS MCP 工具 schema 只读诊断脚本。

### Verified

- fixture 重复同步不会生成重复活动；
- 真实 COROS 活动列表可以授权、解析、入库和复盘；
- Token 未持久化；
- COROS 详情服务异常时列表数据不会回滚。
- FIT 解析、缓存复用、错误脱敏和三级降级链通过离线自动化验收；
- 真实 FIT 工具参数已根据 COROS 实时 `tools/list` schema 核对。
- 用户手动导出的单条真实 FIT 已通过私有缓存完成同步、入库和分圈复盘，结果为 `detailed=1, detail_errors=0`；

### Known Issues

- COROS `getActivityDetail` 和 `queryActivityLapData` 当前返回服务端异常；
- COROS FIT URL 工具当前返回 `isError=true`，自动下载仍未验收；手动 FIT 已完成真实分圈复盘验收；
- 尚未实现 Token 加密缓存和数据库迁移。
