# 简历结论与仓库证据映射

提交简历、更新 README 或准备面试前，用本表逐项核对。证据优先级为：可重复命令/测试 > 版本化评测结果 > ADR/阶段记录 > 口头说明。

| 可使用的结论 | 主要证据 | 可重复验证 | 不应外推为 |
|---|---|---|---|
| 全量189项自动化测试通过 | `scripts/verify.py`、`tests/` | `.venv\Scripts\python.exe scripts\verify.py` | 189个真实用户场景或模型准确率 |
| 真实 COROS OAuth + PKCE/MCP 接入成功 | `docs/progress/2026-08-08-m0-coros-mcp-spike.md`、Provider 代码 | 需要个人授权，不作为公开演示步骤 | 所有 COROS 详情/FIT 接口稳定可用 |
| FIT 可解析 session/lap/record | `src/runcrew/providers/fit.py`、FIT 测试与 M2 记录 | 运行相关 pytest；真实文件不提交 | 自动 FIT URL 已验证 |
| 单 Agent 确定性与真实 DeepSeek 同 Hash 均12/12 | `docs/M5-B3-DeepSeek最终评测报告.md`、`docs/progress/2026-08-09-m5b3b-first-full-suite.md` | 公开套件可跑确定性基线；真实复跑会产生费用 | 复杂多工具 Agent 或生产稳定性100% |
| 多 Agent 确定性 Harness 18/18 | `evals/coach_agent/cases.json`、`docs/progress/2026-08-13-m7e-coach-agent-evaluation.md` | `runcrew eval coach-agent --output data/private/evals/coach-agent.json` | 真实 DeepSeek 多 Agent 18/18 |
| 计划变更需要确认、重放与 revision 校验 | ADR-0013、ADR-0018、训练运营 Service 与测试 | `tests/test_training_operations.py` | Agent 可以自动落地任意计划 |
| 多职责节点权限与 Handoff 可审计 | ADR-0017、Coach Harness、18场景评测 | Coach 专项测试和评测命令 | 节点是独立部署的微服务 |
| 四个 Agent 工具由统一 Manifest/Guardrail 治理 | ADR-0027、`tests/test_runtime_governance.py`、M10-A 阶段记录 | 运行 Runtime Governance 与两套 Harness 专项测试 | 已有持久化跨运行 Trace、生产级安全网关或真实 LLM 攻防结论 |
| 长期偏好显式确认且影响计划 | ADR-0020、`tests/test_athlete_memory.py` | 记忆专项测试、`runcrew memory --help` | 通用向量记忆或聊天自动学习 |
| Memory 按职责裁剪并记录预算与排除原因 | ADR-0023、`tests/test_memory_context.py`、`runcrew memory context` | 运行 Memory Context 专项测试或 CLI | 所有 Agent 共享全部历史、RAG 或自动记忆写入 |
| 聊天偏好候选需确认、来源与 Hash 重放后才写入 | ADR-0024、`tests/test_memory_candidates.py` | 运行 Candidate 专项测试或在合成演示对话中确认 | LLM 自动学习、真实用户抽取准确率或通用 Memory |
| Memory Manager 版本化基线16/16、意外正式写入0 | `evals/memory/`、ADR-0025、M9-E 阶段记录 | `runcrew eval memory --output data/private/evals/memory.json` | 16个真实用户、真实语言准确率或向量检索优越性 |
| 无私人数据演示可重复准备 | ADR-0021、`tests/test_demo_seed.py`、`docs/demo/` | `runcrew demo-seed --reset` | 合成数据证明用户训练效果 |

## 三组数字如何准确表达

### 189 passed

它代表当前仓库全量 pytest 回归，包括领域模型、存储、Provider、Skill、Harness、Runtime Governance、Evaluation、Web/API、Memory 控制面和 Demo Seed。它不是189个评测问题，也不是准确率。

### 12 / 12

它属于 `review-agent-eval/1.1` 单 Agent 动作协议。确定性 Policy 与真实 `deepseek-v4-flash` 使用相同 Suite Hash 和15秒总预算，均满足12个场景的预期终态。9个场景实际调用模型，3个非法动作场景由脚本注入验证 Harness。

### 18 / 18

它属于 `coach-agent-eval/1.0` 多职责编排基线，运行真实 Coach Harness、确定性路由 Policy 和合成节点/临时 SQLite。覆盖任务、韧性、护栏、Schema、事实、血缘、确认和 stale，但没有调用真实 LLM。

## 演示前最小复核

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe demo-seed --reset
.\.venv\Scripts\runcrew.exe demo --db data\private\demo\runcrew-demo.db
```

看到全量测试通过、演示种子输出 `synthetic_data: true`，再按五分钟脚本演示。不要在公开屏幕展示 `data/private/evals/`、环境变量或真实活动详情。
