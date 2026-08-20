# M8-A2 求职演示包

- 日期：2026-08-19
- 状态：完成

## 1. 本阶段目标

把已经可运行的 RunCrew 产品闭环整理为一套不依赖个人数据、能够重复准备、能够在五分钟内解释清楚的求职演示材料。

## 2. 用户可以感知的结果

- 一条命令重置 8 条合成跑步活动、当前训练目标、激活计划、执行确认、身体反馈和周日长跑偏好；
- 启动产品后可以现场运行活动复盘、Execution / Recovery / Plan 三职责 Agent 协作、计划变更审核和连续追问；
- 架构图、训练闭环时序图和五分钟演示脚本可以直接用于面试讲解；
- 演示不会读取真实 COROS/FIT、个人数据库或 DeepSeek Key。

## 3. 新增或修改的主要文件

- `src/runcrew/domain/demo.py`：演示种子输出契约；
- `src/runcrew/services/demo_seed.py`：隔离数据库和合成训练状态生成器；
- `src/runcrew/cli.py`：`runcrew demo-seed` 命令；
- `schemas/demo/seed-output.schema.json`：对外输出 JSON Schema；
- `docs/demo/README.md`：演示材料入口与证据边界；
- `docs/demo/system-architecture.md`：系统架构图；
- `docs/demo/training-loop-sequence.md`：训练闭环时序图；
- `docs/demo/five-minute-demo-script.md`：现场演示脚本；
- `tests/test_demo_seed.py`：演示数据、重置、产品服务、Coach 和 CLI 边界测试。

## 4. 关键技术决策

- 演示数据库与个人数据库物理隔离，CLI 进一步限制输出目录；
- 默认拒绝覆盖，显式 `--reset` 才允许重置；
- 稳定 ID 与动态周内排期结合：同一锚点可回放，同时保证任意星期启动都有可演示的后续训练；
- 只预置业务事实，不预置 Agent 结论，让现场 Trace 具有证明力；
- 架构决策详见 [ADR-0021](../adr/0021-isolated-synthetic-demo-database.md)。

## 5. 验收命令与结果

```powershell
.\.venv\Scripts\python.exe scripts\export_demo_schemas.py
.\.venv\Scripts\python.exe -m pytest tests\test_demo_seed.py -q
.\.venv\Scripts\python.exe scripts\verify.py
```

- Demo Seed 专项测试：5 passed；
- 全量测试：146 passed；
- 文档、Schema、Python 编译和全量测试统一验证通过。

## 6. 实施中出现的错误与解决方案

第一次专项测试在 Windows 上执行第二次 `--reset` 时出现 `PermissionError`。原因不是业务文件越界，而是前一次 SQLite Engine 的连接池仍持有文件句柄。修复方式是在种子写入结束后显式执行 `database.engine.dispose()`，再由测试验证连续重置可成功。

另一个风险是固定把后续训练放在周四：如果面试发生在周五至周日，Coach 会找不到合理的下一节训练。最终改为基于启动日安排已完成和待执行训练，并始终保留本周长跑节点。

## 7. 下一阶段唯一入口

M8-A3：形成简历描述、项目难点、量化结果和面试追问清单，并把每一项表述映射到仓库中的可验证证据。

## 8. 真实数据与外部额度

本阶段只使用程序生成的合成数据；没有读取个人活动、没有调用 COROS、没有调用 DeepSeek，也没有产生外部费用。

