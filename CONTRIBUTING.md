# RunCrew 开发约定

## 环境

- Python 3.11+，当前验证环境为 Python 3.13；
- 项目虚拟环境位于 `.venv`；
- 依赖由 `pyproject.toml` 管理；
- Windows PowerShell 可能禁止运行 `Activate.ps1`，因此文档统一使用 `.venv\Scripts\python.exe` 和 `.venv\Scripts\runcrew.exe`。

## 修改代码前

1. 阅读根目录 `AGENTS.md`；
2. 阅读 `docs/CURRENT_STATE.md`；
3. 确认当前任务属于哪个 Roadmap 里程碑；
4. 运行：

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
```

## 代码约定

- 使用类型注解；
- 外部输入必须经 Pydantic 或等价 Schema 校验；
- 时间必须带时区；
- 单位在领域层统一为米、秒、bpm 等明确单位；
- Provider 错误必须带明确上下文，但错误消息不能包含 Token 和完整私人载荷；
- 规则输出必须附带 `evidence`；
- 新的 Provider 必须实现 `ActivityProvider` 协议；
- Bug 修复必须先增加可以重现问题的测试。

## 测试层级

1. Domain 单元测试；
2. Parser 契约测试；
3. Provider 使用 Fake MCP/HTTP 的测试；
4. SQLite 幂等和容错测试；
5. 显式授权后的真实账户 Smoke Test。

真实账户测试不能成为普通 pytest 的必需条件。

## 文档更新规则

| 变化 | 必须更新 |
|---|---|
| 当前状态或下一步变化 | `docs/CURRENT_STATE.md` |
| 里程碑状态变化 | `docs/ROADMAP.md` |
| 用户可见功能或重要修复 | `CHANGELOG.md` |
| 阶段完成 | `docs/progress/` 对应文件和 `docs/PROGRESS.md` |
| 架构选择或取舍 | `docs/adr/` |
| 模块边界变化 | `docs/ARCHITECTURE.md` |
| 数据安全策略变化 | `SECURITY.md` |

