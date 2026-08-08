# ADR-0001：使用 Provider 隔离外部数据源

- 状态：接受
- 日期：2026-08-08

## 背景

项目当前使用 COROS，未来可能增加 FIT、Keep 或其他平台。各来源字段、单位、授权和错误行为不同。

## 决策

所有外部活动来源实现统一 `ActivityProvider` 协议。业务层只使用 `ActivitySummary` 和 `ActivityDetail`，不直接依赖 COROS 文本或工具名称。

## 原因

- 避免 COROS 格式变化扩散到所有 Agent；
- 支持 fixture 离线测试；
- 便于增加 FIT 兜底；
- 让 Domain 和 Service 可以独立评测。

## 后果

需要额外维护 Parser 和字段映射，但系统边界更清晰，故障更容易定位。

## 替代方案

让 Agent 直接读取 MCP 文本。拒绝，因为格式不稳定、难以测试且容易污染 Prompt。

