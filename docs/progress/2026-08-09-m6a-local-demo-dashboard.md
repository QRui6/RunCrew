# M6-A 本地只读演示 Dashboard

## 1. 本阶段目标

把已经完成的真实活动数据、Training Review Skill、Agent Harness/Loop/Trace 和 Same-Hash 模型评测集中展示，使项目可以在面试中直观看懂，同时冻结营养、伤病诊断、自动计划和多 Agent 范围。

## 2. 用户能感知到的结果

运行：

```powershell
.\.venv\Scripts\runcrew.exe demo
```

浏览器打开 `http://127.0.0.1:8766`。页面支持：

- 查看最新规范化活动与最近活动规模；
- 切换 COROS、fixture 或 Keep Provider；
- 输入可选计划距离/时长并只读回放 Agent；
- 查看三类 finding、结构化 evidence、数据质量和输入 Hash；
- 查看 Agent 终态、步骤/工具预算和完整脱敏 Trace；
- 对照确定性 Policy 与 DeepSeek 的相同 Suite Hash、12/12、延迟、Token 和费用。

## 3. 新增与修改文件

- `src/runcrew/web/dashboard.py`：只读展示数据契约、Agent 回放和评测报告聚合；
- `src/runcrew/web/server.py`：回环地址 HTTP 服务、固定路由和安全响应头；
- `src/runcrew/web/static/`：响应式单页 Dashboard；
- `src/runcrew/cli.py`：增加 `runcrew demo`；
- `tests/test_demo_web.py`：数据、隐私、API 与 CLI 测试；
- `pyproject.toml`：显式把静态资源包含进 Wheel；
- README、架构、安全、路线图和项目全景文档同步更新。

## 4. 关键技术决策

- 使用现有 Python 架构和标准库 HTTP Server，不另建 React/Node 项目；
- 只绑定 `127.0.0.1`，不提供 `0.0.0.0` 或公网部署参数；
- API 只接受 GET，不提供同步、删除、写计划或真实 LLM 调用；
- 页面通过现有 Service 和 Harness 产生结果，不复制 Training Review 规则；
- 浏览器 DTO 不包含外部活动 ID、raw payload、坐标、Token 或完整内部对象；
- 最终评测报告仍保存在 `data/private/`，页面只读取聚合指标。

## 5. 验收结果

```text
专项 Web 测试：4 passed
全量验证：56 passed
真实本地规范化数据：activity_available=True
Agent：succeeded
finding：3
Trace：9 events
Evaluation：same_suite=True
回环 HTTP：首页200、API 200、CSP存在、API no-store
JavaScript 语法检查：通过
真实外部 API 调用：0
```

本地虚拟环境没有安装构建后端 `hatchling`，因此没有执行离线 Wheel 构建；静态资源已经在 Hatch 配置中显式声明，常规隔离构建会根据 `build-system` 安装后端。

## 6. 已知限制

- 当前页面没有登录系统，只能在本机使用；
- 页面不持久化用户输入的训练目标；
- 当前 Agent 回放使用确定性 Policy，不会从页面触发收费模型；
- 没有进行公网部署，也没有必要在 M6-A 部署；
- 浏览器视觉验收由用户启动本地页面完成，自动化测试覆盖结构和数据契约。

## 7. 下一阶段唯一入口

M6-B 基于现有页面制作5分钟演示脚本、系统架构图、失败复盘图、简历描述和高频面试问答，不扩展业务功能。

## 8. 数据与额度

开发和自动化测试没有调用 COROS 或 DeepSeek。只读验收使用本机已有规范化 COROS 数据，仅输出“是否可用、状态和数量”等安全统计；没有复制真实指标到文档或 Git。
