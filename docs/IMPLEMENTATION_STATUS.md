# RunCrew 实施状态导航

> 本文件不再维护重复的阶段快照，避免多份“当前状态”相互冲突。最后调整：2026-08-13。

请按以下顺序阅读：

1. [CURRENT_STATE.md](CURRENT_STATE.md)：唯一当前事实来源，回答“现在做到哪里、限制和下一步是什么”；
2. [RunCrew-项目实施全景与面试说明.md](RunCrew-项目实施全景与面试说明.md)：完整记录阶段实现方案、技术策略、亮点、错误和面试表达；
3. [PROGRESS.md](PROGRESS.md)：各阶段不可变的历史交接索引；
4. [ROADMAP.md](ROADMAP.md)：后续阶段和验收条件；
5. [adr/README.md](adr/README.md)：关键架构选择及其原因。

当前一句话状态：107项自动化测试通过；M7-B1/B2/B3 已完成恢复风险、计划草案和执行对照 Skill，且保留 revision 与用户确认边界；下一步实现 Coach Orchestrator Harness，真实 DeepSeek 聊天评测仍待新 Key。

常用验收命令：

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe training review --latest --provider fixture
.\.venv\Scripts\runcrew.exe agent review --latest --provider fixture
.\.venv\Scripts\runcrew.exe eval review-agent --output data\private\evals\m5-baseline.json
.\.venv\Scripts\runcrew.exe eval deepseek-suite --help
.\.venv\Scripts\runcrew.exe demo --no-open-browser
.\.venv\Scripts\runcrew.exe cycle --help
.\.venv\Scripts\runcrew.exe recovery assess --help
.\.venv\Scripts\runcrew.exe planning --help
.\.venv\Scripts\runcrew.exe execution --help
```
