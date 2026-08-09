# ADR-0006：Skill 只编排确定性训练复盘

- 状态：接受
- 日期：2026-08-09

## 背景

Training Review 需要计算训练完成度、负荷变化和训练异常。若把这些计算直接放入 Prompt，同一输入可能产生不同结论，阈值难以测试，缺失数据也容易被自然语言掩盖。

## 决策

以 Pydantic Domain 模型作为输入/输出唯一事实来源，由确定性 Service 构建上下文和 findings，再把 JSON Schema 导出到 `skills/review-running-training/references/`。Skill 负责选择数据、调用 Service、验证契约和解释 evidence；LLM 未来只能改写已经验证的结果，不能计算指标、修改 level 或补齐缺失事实。

回放身份由 `input_hash + ruleset_version` 组成，时间窗口锚定目标活动时间而不是当前系统时间。

## 原因

- 相同输入可以回放并比较；
- 每条结论强制携带 evidence；
- 规则阈值可以单元测试和版本化；
- 数据不足时稳定输出 `unknown + requires`；
- 后续更换模型不会改变基础业务判断。

## 后果

- Schema 和规则升级必须显式修改版本并更新回放测试；
- LLM 生成的表达能力暂时受限，但其错误不会污染指标计算；
- JSON Schema 是 Domain 模型的生成物，测试必须防止两者漂移。

## 替代方案

- 让 LLM 直接读取活动 JSON 并完成全部分析：拒绝，因为不可稳定回放；
- 只输出确定性文本、不创建 Skill：拒绝，因为无法形成可复用 Agent 能力和清晰契约；
- 立即拆分多个训练 Agent：推迟到单 Skill 的评测证明存在职责冲突之后。
