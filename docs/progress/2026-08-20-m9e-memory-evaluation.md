# M9-E：版本化 Memory Manager Evaluation

## 1. 本阶段目标

把 M9-A 至 M9-D 的分层 Memory 从“分别有测试”提升为“同一套公开输入、固定期望和 Suite Hash 下可重复比较”，并把意外正式写入作为高风险副作用单独统计。

## 2. 已实现结果

- 新增 `memory-manager-eval/1.0`，共16个无私人数据场景；
- 场景分为 candidate 6个、lifecycle 5个、integrity 2个、retrieval 3个；
- 生命周期与篡改场景运行正式 SQLite Repository、Candidate、Preference 和来源重放服务；
- 召回场景运行正式 Memory Context Builder，并检查职责字段白名单与排除审计；
- 无关记忆注入要求 Context Hash 不变、Audit Hash 改变，证明不可用候选只进入审计而不污染实际上下文；
- CLI `runcrew eval memory` 支持标准输出和 `data/private/` 私有报告；
- Suite/Report JSON Schema 已导出并由测试防漂移。

## 3. 当前基线

| 指标 | 结果 |
|---|---:|
| 场景满足期望 | 16 / 16 |
| Candidate 正样本召回 | 100%（2个合成正样本） |
| 负样本拒绝 | 100%（4个合成负样本） |
| 生命周期完整性 | 100% |
| 来源完整性 | 100% |
| 人工确认边界 | 100% |
| 职责隔离 | 100% |
| 无关记忆注入抵抗 | 100% |
| 意外正式 Memory 写入 | 0 |

Suite Hash：`78e9e4dc7c1e75cb94fbbbfbc60cb9b9b74874da7555757a58487567892d51ef`。

这些数字是版本化合成场景的工程回归结果，不是16个真实用户，也不是自然语言总体准确率。

## 4. 主要文件

- 领域契约：`src/runcrew/domain/memory_evaluation.py`；
- 运行器：`src/runcrew/evaluation/memory.py`；
- 用例与 Schema：`evals/memory/`；
- CLI：`src/runcrew/cli.py` 的 `eval memory`；
- 导出脚本：`scripts/export_memory_evaluation_schemas.py`；
- 测试：`tests/test_memory_evaluation.py`；
- 架构决策：`docs/adr/0025-versioned-memory-manager-evaluation.md`。

## 5. 验收命令

```powershell
.\.venv\Scripts\runcrew.exe eval memory
.\.venv\Scripts\runcrew.exe eval memory --output data\private\evals\memory-manager-v1.0.json
.\.venv\Scripts\python.exe -m pytest tests\test_memory_evaluation.py -q
.\.venv\Scripts\python.exe scripts\verify.py
```

## 6. 实施中的问题与修复

- 第一版每个持久化场景创建临时磁盘 SQLite；Windows 在 `TemporaryDirectory` 清理时发现 SQLAlchemy Engine 仍持有文件句柄，7个场景被清理异常覆盖。评测改用每场景独立的内存 SQLite，并在结束时显式 `engine.dispose()`，既保留真实事务/Repository 行为，也消除文件锁和磁盘残留。
- 初版只比较浏览器预期 Hash，不能体现数据库候选和原消息双重完整性；Suite 将两种篡改拆成独立场景，分别要求确认被阻断且正式写入为0。
- “100%召回”容易被误解为真实准确率；报告和文档明确给出分母，当前只有2个合成正样本与4个合成负样本。

## 7. 当前边界与下一步

- 复杂隐含表达、跨消息偏好和真实用户语言分布仍未覆盖；
- 当前没有 LLM Candidate Extractor，因此不存在“确定性规则 vs 模型”的同题结果；
- 结构化职责检索在当前 Suite 中16/16通过，没有证据引入向量数据库。

下一步进入 M9-F：建立用户可管理的 Memory 控制面，集中查看正式偏好、周记忆、待确认候选、来源、状态与停用操作；不增加新的自主写入权限。

## 8. 真实数据与外部费用

本阶段只使用公开合成文本、合成 Memory 和隔离 SQLite；没有读取真实跑步数据库、聊天记录、COROS/FIT、Token 或 DeepSeek Key，也没有产生外部费用。
