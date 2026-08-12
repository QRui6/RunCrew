# RunCrew 安全与隐私

RunCrew 处理运动、睡眠、心率、HRV、恢复、位置等私人数据。这些数据默认按敏感数据处理。

## 禁止提交的内容

- OAuth Access Token、Refresh Token；
- COROS/Keep 账号密码；
- PKCE verifier、未过期授权码；
- 真实 SQLite 数据库；
- 未脱敏 FIT/TCX；
- `data/private/` 下的调试载荷；
- 包含真实 LabelId、坐标、位置和健康指标的日志。

## 当前保护措施

- `.env`、`data/*.db`、`data/private/` 已加入 `.gitignore`；
- COROS Token 只保存在当前进程内；
- OAuth 使用 Authorization Code + PKCE；
- 私有 payload 只有显式传入 `--debug-payload` 才会保存；
- FIT 只写入 `data/private/fit/`，缓存文件名是 LabelId 的单向摘要；
- 下载错误不会输出签名 URL，工具错误会脱敏 URL 和长数字 ID；
- 测试 FIT 由 Garmin Encoder 人工生成，不含坐标或真实用户指标。
- 本地产品服务强制绑定 `127.0.0.1`，不提供公网监听参数；
- 工程观测 API 只接受 GET；聊天 POST API 限制 JSON 正文为 64 KB；
- 浏览器 DTO 不返回 Provider 外部 ID、原始 payload、坐标或 Token；
- DeepSeek 只有用户在界面显式开启后才调用，只发送规范化活动、确定性 evidence、最近 8 条消息和当前问题；
- DeepSeek 回答必须通过 `ChatAnswer` Schema、evidence 引用白名单和医疗诊断措辞校验；
- 个人数据事实和数据推断必须引用已有 evidence；通用知识和建议可以不引用个人数据，但会用独立论断类型标记；
- 无效模型回答仍统计供应商已返回的 Token 与估算费用，不把被拒绝的请求当作零成本；
- 会话历史只保存在本机 SQLite，响应设置 CSP、禁止 MIME 嗅探且 API 不缓存。
- 训练目标、计划和身体反馈只保存在本机 SQLite；专业 Agent 不能直接修改激活计划；
- 激活计划的调整必须形成带基础修订号的提案，并由用户批准，旧提案不能覆盖新版本；
- 疼痛和疲劳是用户主观输入，只能用于风险分层，不得被模型包装成诊断。

## 尚未实现

- 系统凭据存储中的 Refresh Token 加密缓存；
- 用户数据删除和导出命令；
- 数据保留期限；
- 数据库静态加密；
- 自动化密钥扫描。
- 对话导出、删除和保留期限；
- 更完整的真实模型提示注入红队；当前只有合成8轮 Suite，真实同题运行待新 Key。
- 训练闭环数据删除、导出、保留期限和数据库静态加密；
- 多 Agent 工具白名单与冲突评测尚未实现，当前只有领域 Service 权限边界。

在实现 Token 持久化前必须先创建 ADR 和威胁模型，不能把 Refresh Token 直接写入 `.env` 或 SQLite。

## 医疗边界

RunCrew 可以做训练风险提示和建议用户寻求专业帮助，但不能：

- 诊断伤病或疾病；
- 承诺预防伤病；
- 替代医生、康复师或营养师；
- 在数据不足时给出高置信度健康结论。
