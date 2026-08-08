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
- 测试 fixture 为人工构造的脱敏数据。

## 尚未实现

- 系统凭据存储中的 Refresh Token 加密缓存；
- 用户数据删除和导出命令；
- 数据保留期限；
- 数据库静态加密；
- 自动化密钥扫描。

在实现 Token 持久化前必须先创建 ADR 和威胁模型，不能把 Refresh Token 直接写入 `.env` 或 SQLite。

## 医疗边界

RunCrew 可以做训练风险提示和建议用户寻求专业帮助，但不能：

- 诊断伤病或疾病；
- 承诺预防伤病；
- 替代医生、康复师或营养师；
- 在数据不足时给出高置信度健康结论。

