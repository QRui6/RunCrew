# M8-A3 求职叙事与证据映射

- 日期：2026-08-19
- 状态：完成

## 1. 本阶段目标

把 RunCrew 的工程实现压缩成准确、可面试、可追问的简历材料，并保证每个数字和技术结论都能定位到仓库证据。

## 2. 用户可以感知的结果

- 获得推荐三行版、紧凑两行版和按岗位调整的简历条目；
- 获得五个核心难点的“问题—约束—方案—验证—边界”讲述框架；
- 获得14个常见面试追问与基于实际代码的回答；
- 能通过证据表准确区分146项测试、单 Agent 12/12真实模型对照和多 Agent 18/18确定性基线。

## 3. 新增或修改的文件

- `docs/job/README.md`：求职材料导航和统一定位；
- `docs/job/resume-entry.md`：简历条目与禁用表述；
- `docs/job/core-challenges.md`：核心难点讲述框架；
- `docs/job/evidence-map.md`：结论、证据、命令和不可外推边界；
- `docs/job/interview-questions.md`：面试追问清单；
- README、CURRENT_STATE、ROADMAP、PROGRESS、CHANGELOG 与实施全景同步更新。

## 4. 关键技术决策

- 简历主线只保留“数据可靠性—Agent 编排—版本化验证”，不罗列所有模块；
- 真实 DeepSeek 12/12与确定性 Coach 18/18分开表达，禁止合并为“多 Agent 大模型准确率”；
- 用可重复命令、测试、评测、ADR 和阶段记录构成证据层级；
- 对未完成的真实多轮聊天、真实 LLM Coach、生产并发和用户效果主动标注边界。

## 5. 验收命令与结果

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
```

- 全量测试：146 passed；
- 必需文档、Python 编译和 Schema 契约验证通过；
- 求职材料中所有量化结论均可映射到现有仓库证据。

## 6. 已知问题

- 简历最终篇幅仍需结合用户整份简历版式压缩；
- 仓库是否公开、投递岗位侧重点和个人实习经历会影响最终取舍；
- M8-A1.4 本机主观视觉验收仍需用户实际点击确认。

## 7. 下一阶段唯一入口

M9-B：从正式计划、执行确认和 Check-in 确定性生成版本化 Weekly Training Memory，为跨周训练复盘和下一周 Planning Context 提供可追溯摘要。

## 8. 真实数据与外部额度

本阶段只整理仓库已有事实，没有读取个人活动、没有调用 COROS/DeepSeek，也没有产生外部费用。

