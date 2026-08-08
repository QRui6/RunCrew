# RunCrew AI 开发入口

本文件是任何 AI、自动化 Agent 或新开发者进入 RunCrew 项目时的第一入口。开始工作前必须完整阅读，并按下列顺序加载项目上下文。

## 必读顺序

1. `README.md`：项目是什么、如何运行；
2. `docs/PROJECT_CONTEXT.md`：业务目标、用户价值、范围与非目标；
3. `docs/CURRENT_STATE.md`：当前唯一有效的进度状态、已知问题、下一步；
4. `docs/ARCHITECTURE.md`：模块边界、数据流和失败语义；
5. `docs/ROADMAP.md`：阶段划分和验收标准；
6. 与当前任务有关的 `docs/adr/` 和 `docs/progress/` 文件。

发生冲突时，优先级为：

```text
用户当前明确要求
  > AGENTS.md
  > docs/CURRENT_STATE.md
  > ADR
  > ARCHITECTURE / ROADMAP
  > 历史 progress 文档
```

## 当前项目原则

1. 先把确定性数据链路做稳定，再引入 LLM 和多 Agent；
2. Provider 原始数据不能直接进入业务 Agent，必须转换为 RunCrew 统一 Schema；
3. 原始数据与规范化数据分层保存，以便回放、重解析和审计；
4. 任何训练判断必须携带 evidence，不能只输出自然语言结论；
5. 单条详情失败不能回滚已经成功获得的活动列表；
6. 不把 summary 伪装成 detail，不在缺少数据时编造分圈、心率或恢复结论；
7. 健康和运动数据属于私有数据，不得提交到公开仓库或写入普通日志；
8. Access Token、Refresh Token、PKCE verifier、密码不得明文落盘；
9. 当前系统不是医疗诊断工具，不输出确诊或替代医生的建议。

## 代码边界

```text
providers/   外部数据接入、授权、协议与解析
domain/      与厂商无关的统一领域模型
storage/     数据库模型与 Repository
services/    同步、复盘等确定性业务流程
cli.py       人机入口，只做参数编排
```

禁止：

- 在 `services/` 中直接解析 COROS 文本；
- 在 `domain/` 中出现 HTTP、OAuth、MCP 或 SQLAlchemy 依赖；
- 在 Agent Prompt 中弥补本应由解析器和 Schema 完成的数据校验；
- 为通过演示而吞掉错误或伪造缺失数据；
- 未经明确需求读取或输出 `data/private/` 和真实 SQLite 内容。

## 开发工作流

开始任务：

1. 阅读 `docs/CURRENT_STATE.md`；
2. 运行 `git status --short`，保护用户已有修改；
3. 运行 `\.venv\Scripts\python.exe scripts\verify.py` 建立基线；
4. 只修改当前里程碑所需模块。

结束任务：

1. 运行全部测试；
2. 更新 `docs/CURRENT_STATE.md`；
3. 更新 `docs/ROADMAP.md` 对应状态；
4. 在 `CHANGELOG.md` 记录对用户可见或架构级变化；
5. 在 `docs/progress/` 新建或更新本阶段记录，并更新 `docs/PROGRESS.md` 索引；
6. 如果做了难以逆转的技术选择，在 `docs/adr/` 新建 ADR；
7. 确认没有 Token、真实原始数据或私有调试载荷被 Git 跟踪。

## 完成定义

一个阶段只有同时满足以下条件才可标记完成：

- 代码已实现；
- 自动化测试通过；
- 至少一条可重复的验收命令通过；
- 已知限制被明确记录；
- `CURRENT_STATE`、`ROADMAP`、`CHANGELOG`、`PROGRESS` 已同步；
- 下一步是一个具体、可执行的任务，而不是“继续优化”。

## 常用命令

```powershell
\.venv\Scripts\python.exe scripts\verify.py
\.venv\Scripts\python.exe -m pytest
\.venv\Scripts\runcrew.exe status
\.venv\Scripts\runcrew.exe sync --provider fixture --days 30 --detail-limit 1
\.venv\Scripts\runcrew.exe activities review --latest --provider coros
```

