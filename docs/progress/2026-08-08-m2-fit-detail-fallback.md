# M2：FIT 详情兜底

## 目标

当 COROS 详情与分圈工具不可用时，通过单条原始 FIT 文件恢复真实 `ActivityDetail`，同时控制下载额度、保护私人数据并保持 summary 同步可用。

## 用户可感知结果

Provider 现在依次尝试 COROS 详情、COROS 分圈、私有 FIT 缓存和 FIT 下载。成功时可得到 session、lap、record；全部失败时仍保存活动摘要并明确记录 warning，不伪造详情。

## 主要文件

- `src/runcrew/providers/fit/download.py`：HTTPS 下载、大小上限、过期链接识别、原子缓存和缓存清理；
- `src/runcrew/providers/fit/parser.py`：FIT/CRC 校验及 Domain 映射；
- `src/runcrew/providers/coros/provider.py`：三级详情降级编排；
- `src/runcrew/providers/coros/parser.py`：FIT URL 提取和工具错误脱敏；
- `tests/conftest.py`：使用官方 Encoder 生成无坐标合成 FIT；
- `tests/test_fit_parser.py`、`tests/test_fit_download.py`、`tests/test_coros_fit_fallback.py`：契约和故障路径；
- `scripts/inspect_coros_tool.py`：只读查看单个 MCP 工具 schema；
- `docs/adr/0005-official-garmin-fit-sdk.md`：SDK 选型决策。

## 关键决策

使用 Garmin 官方 `garmin-fit-sdk`，不让 LLM 解释二进制数据。真实 FIT 只保存在 `data/private/fit/`，文件名不含 LabelId；先查缓存，再请求短期 URL。下载内容必须通过 FIT 识别和 CRC 校验，否则删除不可用缓存。

## 验收结果

```text
pytest / scripts/verify.py: 19 passed
合成 FIT: 1 session, 4 laps, 12 records
缓存回归: 两次详情请求仅下载一次
真实 COROS summary: 同步成功并在详情失败时保留
真实 FIT: 用户从 COROS App 手动导出并写入私有缓存
真实同步: detailed=1, detail_errors=0
真实复盘: 输出基于多分圈计算的 pace_stability evidence，confidence=high
```

真实调用前通过 `tools/list` 核对了输入 schema；`labelId + sportType` 参数正确。COROS 自动 URL 工具没有返回地址后，使用官方 App 手动导出同一条活动的 FIT；先独立验证解析，再放入私有缓存完成 Provider、Sync、Storage 和 Review 端到端验收。

## 已知问题

- COROS 自动 FIT URL 工具仍返回错误，当前真实文件由用户手动导出；
- COROS 工具首次只返回通用 `isError`，新代码已保留并脱敏服务端错误文本，方便下次定位。

## 下一阶段唯一入口

M3：定义 Training Review Skill 的输入/输出 Schema，把确定性复盘服务包装成可回放、带 evidence、缺失数据可降级的 Skill。M3 不需要再次下载真实 FIT。

## 私有数据与额度

本阶段真实同步只选择一条活动。真实数据库和任何未来下载的 FIT 均在 Git 忽略目录中；进展文档不记录活动数值、LabelId、位置、坐标或签名 URL。
