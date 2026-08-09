# ADR-0005：使用 Garmin 官方 Python FIT SDK

- 状态：接受
- 日期：2026-08-08

## 背景

COROS 的活动详情和分圈 MCP 工具在真实测试中返回服务端异常。项目需要通过原始 FIT 文件确定性恢复 session、lap 和 record 数据，并需要不含真实用户数据的合成测试文件。

## 决策

使用 Garmin 官方 `garmin-fit-sdk` 21.x（本阶段验证版本为 21.212.0）作为 FIT 解码和测试文件编码依赖。

## 原因

- Garmin 是 FIT 协议维护者；
- SDK 支持 Python 3.13；
- 支持 FIT 文件识别、CRC 完整性检查和消息解码；
- 当前版本同时提供 Encoder，可以生成合成 FIT fixture；
- 解码时自动处理 scale、offset、时间戳和已知类型；
- 避免把真实运动文件复制到测试目录。

## 后果

- RunCrew 的 FIT Parser 仍需负责把 SDK 字典映射为 Domain Schema；
- SDK 解码错误必须转换为不包含私人 payload 的明确异常；
- 真实 FIT 只保存在 `data/private/fit/`；
- 未来升级 SDK 时必须运行合成 fixture 和一条显式授权的真实 Smoke Test。

## 替代方案

- `fitdecode`：Python 3.13 可用，但属于第三方实现；
- 自行实现 FIT 二进制协议：维护成本和错误风险过高；
- 让 LLM 解释 FIT：二进制不可行，也无法提供确定性和完整性校验。
