# M0：COROS MCP 接入 Spike

## 目标

在正式开发前验证 COROS 官方 MCP 是否真正可用，避免围绕不存在或不稳定的数据接口设计整个项目。

## 完成结果

- 官方入口返回标准 Bearer 授权挑战；
- 确认中国区实际资源地址；
- 动态 OAuth 客户端注册成功；
- Authorization Code + PKCE 成功；
- MCP `initialize` 成功；
- 发现 22 个 COROS 工具；
- 跑步记录、健康摘要、体能评估、恢复状态调用成功；
- 确认工具主要以 `content[].text` 返回，而不是 `structuredContent`；
- 确认设备码授权不适合作为当前默认流程。

## 产物

Spike 位于父工作区，而不是 RunCrew 包内：

- `D:\AgentProjets\scripts\coros_mcp_spike.mjs`
- `D:\AgentProjets\docs\COROS-MCP-接入Spike测试报告.md`

## 决策

采用 COROS MCP 主路径、FIT 兜底、手工 Check-in 补充；Keep 不阻塞 MVP。

## 下一入口

创建独立 Python 项目并完成真实数据竖切。

