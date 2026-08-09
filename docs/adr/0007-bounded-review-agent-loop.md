# ADR-0007：使用有界动作协议实现单 Agent Loop

- 状态：接受
- 日期：2026-08-09

## 背景

M3 已经提供确定性的 Training Review Skill，但它仍然由 CLI 直接调用，尚未体现 Agent 的上下文、动作选择、工具权限、预算、重试、Trace 和退出条件。如果直接引入某个 Agent 框架或让 LLM 自由调用工具，会在状态边界尚未稳定时同时引入框架行为和模型不确定性，难以定位错误来源。

## 决策

M4 使用项目内可测试的有限循环。策略层每一步只能返回两类结构化动作：

- `call_tool`：请求调用 `review_running_training`；
- `finish`：在已经获得并校验训练复盘结果后结束。

Harness 负责构建有界 `ReviewAgentContext`，并统一执行：

- 只读工具白名单和确认门；
- 步骤、逻辑工具调用和重试预算；
- 单次工具超时和整次 Run 超时；
- 瞬时错误有限重试；
- `TrainingReviewResult` 输出校验；
- 连续编号、相对时间且经过脱敏的 Trace；
- 成功、失败、超时和预算耗尽四类终态。

默认使用 `DeterministicReviewPolicy` 完成离线回归。未来 LLM 策略必须实现相同的 `next_action(context)` 接口并返回相同动作 Schema，不能绕过 Harness，也不能直接计算训练指标。

## 原因

- 把 Agent 编排问题与模型生成质量分开验证；
- 即使没有 API Key，也能离线测试全部循环和失败语义；
- 模型、框架或供应商以后可以替换，权限和预算边界保持不变；
- 单一 Skill 足以暴露最小 Loop 的真实工程问题，不需要提前拆分多 Agent；
- Trace 不记录原始活动和异常正文，降低私人数据泄漏风险。

## 后果

- 当前 Agent 能完成结构化复盘编排，但还不能声称已经由真实 LLM 自主决策；
- Trace 当前随 CLI JSON 返回，尚未持久化；
- 工具超时可以停止等待，但线程中已经开始的同步只读数据库操作不能被强制终止；
- 接入 LLM 时必须增加模型动作解析、Token/费用预算和真实模型 Smoke Test，但无需重写 Harness。

## 替代方案

- 立即使用 LangGraph/LangChain：暂不采用，因为当前只有两个动作和一个工具，框架会掩盖状态机本身；
- 让 LLM 直接读取数据库或 COROS MCP：拒绝，因为会绕过 Domain、Skill 和隐私边界；
- 直接把 M3 CLI 称为 Agent：拒绝，因为它没有动作循环、权限、预算和 Trace；
- 立即拆成训练、恢复和风险多个 Agent：拒绝，尚无单 Agent 失败证据。
