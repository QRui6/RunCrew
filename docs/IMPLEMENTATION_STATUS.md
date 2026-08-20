# RunCrew 实施状态导航

> 本文件不再维护重复的阶段快照，避免多份“当前状态”相互冲突。最后调整：2026-08-20。

请按以下顺序阅读：

1. [CURRENT_STATE.md](CURRENT_STATE.md)：唯一当前事实来源，回答“现在做到哪里、限制和下一步是什么”；
2. [RunCrew-项目实施全景与面试说明.md](RunCrew-项目实施全景与面试说明.md)：完整记录阶段实现方案、技术策略、亮点、错误和面试表达；
3. [PROGRESS.md](PROGRESS.md)：各阶段不可变的历史交接索引；
4. [ROADMAP.md](ROADMAP.md)：后续阶段和验收条件；
5. [adr/README.md](adr/README.md)：关键架构选择及其原因。

当前一句话状态：M7 训练闭环、M9 Memory Manager、M8 求职证据包和 M10 Runtime Governance 已完成；跨运行指标、5场景治理评测与只读工程观测台已落地，全量202项测试通过。下一步是本机视觉/点击验收；真实 DeepSeek 聊天评测仍是独立付费收尾项。

常用验收命令：

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\runcrew.exe training review --latest --provider fixture
.\.venv\Scripts\runcrew.exe agent review --latest --provider fixture
.\.venv\Scripts\runcrew.exe eval review-agent --output data\private\evals\m5-baseline.json
.\.venv\Scripts\runcrew.exe eval deepseek-suite --help
.\.venv\Scripts\runcrew.exe eval coach-agent --output data\private\evals\coach-agent-v1.0.json
.\.venv\Scripts\runcrew.exe demo --no-open-browser
.\.venv\Scripts\runcrew.exe cycle --help
.\.venv\Scripts\runcrew.exe recovery assess --help
.\.venv\Scripts\runcrew.exe planning --help
.\.venv\Scripts\runcrew.exe execution --help
.\.venv\Scripts\runcrew.exe coach --help
.\.venv\Scripts\runcrew.exe memory --help
```
