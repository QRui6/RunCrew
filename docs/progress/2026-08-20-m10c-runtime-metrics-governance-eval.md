# M10-C 阶段记录：跨运行指标、治理评测与只读观测台

> 日期：2026-08-20  
> 结果：已完成

## 本阶段解决的问题

M10-A 解决“工具能否被调用”，M10-B 解决“单次运行发生了什么”。M10-C 把正式 Run/Span 变成可以跨运行比较的指标，并用独立合成套件验证治理失败路径，最后在产品内提供只读工程观测页面。

## 已完成实现

### 1. 可重算指标

- 新增 `runtime-metrics/1.0`；
- 支持1—30天窗口、最多500 Run 和显式截断标记；
- 计算 Run 成功率、Guardrail 拒绝率、工具成功率、重试率、预算耗尽率、Run P50/P95/最大耗时；
- 支持 workflow、workflow version、tool、role、termination reason 分组；
- 空样本比例和延迟返回 `null`，不伪造0值；
- `GET /api/runtime/metrics` 只读返回，POST 等写方法返回405。

### 2. 版本化治理评测

- 新增 `runtime-governance-eval/1.0` 五场景套件；
- 覆盖未注册工具、参数篡改、确认绕过、非法输出、Runtime 写入失败；
- CLI：`runcrew eval runtime-governance`；
- Suite Hash：`4ca00de0bab7be9b1cd96b27a081481214b2beceb2327264da6ae9ab6ed2234e`；
- 结果：5/5符合期望，执行前阻断、非法输出阻断、观测故障隔离均为100%，禁止工具误执行0，敏感错误泄漏0；
- 证据范围固定为 `deterministic_synthetic_governance`，不能解释为真实 LLM 攻防效果。

### 3. 工程观测页

- `/engineering` 已改为正式 Runtime Control Room；
- 提供7/30天筛选、四项核心指标、工作流健康度、退出原因、工具/职责聚合、5场景治理基线；
- 最近运行表可打开单次脱敏父子时间线抽屉；
- 页面只使用 `textContent` 创建动态内容，API 与页面均没有删除、重放或审批能力。

## 指标口径

| 指标 | 分子 / 分母 |
|---|---|
| Run 成功率 | `succeeded Run / 全部 Run` |
| Guardrail 拒绝率 | `blocked Guardrail Span / 全部 Guardrail Span` |
| 工具成功率 | `成功终态 Span / 调用开始 Span` |
| 重试率 | `Retry Span / 调用开始 Span` |
| 预算耗尽率 | `budget_exhausted Run / 全部 Run` |
| P50/P95 | Run 总耗时 nearest-rank |

## 实施判断与问题复盘

最大的设计陷阱是“观测写入失败率”无法从成功写入的 Runtime 表中可靠计算：失败时恰好没有记录。如果把缺失记录估算成0，指标会产生虚假确定性。本阶段没有增加伪指标，而是在产品指标中固定展示覆盖说明，并由独立故障注入套件验证 best-effort 隔离。

另一个边界是离线评测不能进入产品 Runtime 表，否则5个故障场景会直接拉低真实产品成功率。因此评测报告与产品 Run/Span 保持两条证据链，只在工程观测页并列展示。

## 验证

```powershell
.\.venv\Scripts\runcrew.exe eval runtime-governance
.\.venv\Scripts\python.exe -m pytest
```

- Runtime 治理套件：5/5；
- 全量自动化回归：202项；
- JavaScript 语法、DOM 安全、只读 API、Schema 漂移、空样本与 nearest-rank 均有自动化测试。

## 已知限制

- 当前是本地、30天、最多500 Run 的读取时聚合，不是生产 OLAP 或分布式链路系统；
- 只有聊天首轮 Review 和训练运营 Coach 两条产品路径写入 Runtime；
- 写入失败不会出现在产品指标样本中；
- 指标只证明工程运行事实，不证明训练建议有效或用户效果；
- 页面仍需要用户在本机完成一次真实点击与视觉复核。

## 下一入口

M10 Runtime Governance 主线已收尾。下一项不再扩展 Agent 层，而是完成两项独立验收：本机 `/engineering` 视觉与点击复核，以及使用新 Key 运行真实 DeepSeek 连续聊天同题评测。
