# M8-B 网页训练产品闭环

## 1. 本阶段目标

把 M7 已经存在于 CLI、Skill 和 Service 层的训练能力接入普通用户可操作的网页流程，解决“技术模块已经完成，但用户仍需进入终端、不同步骤彼此割裂”的问题。

本阶段没有增加营养、伤病诊断等新角色，而是闭合以下主链路：

```text
创建目标 → 预览周计划 → 用户确认激活 → 查看今日训练
→ 候选活动匹配 → 用户确认执行事实 → 跑后复盘/身体反馈
→ Execution / Recovery / Plan 协作 → 用户审核调整 → 本周总结
```

## 2. 借鉴的产品经验

- TrainingPeaks 把设备同步、计划课、完成活动和合规度放在同一条训练工作流中。RunCrew 因此不再把“目标创建”和“计划执行”分成终端与网页两套入口；
- TrainingPeaks 对错误或缺失的计划课匹配保留人工配对/解除能力。RunCrew 延续 M7-B3 的原则：算法只能提供候选，用户确认后才形成执行事实；
- TrainingPeaks Athlete Home 同时突出今日安排和目标，周视图提供总结。RunCrew 新增“今日/下一节训练”和“本周总结”，避免用户只能看到技术节点；
- Intervals.icu 用外部 ID、计划训练、活动和 webhook 支持连续数据流。RunCrew 当前不引入新的云依赖，但继续保留统一 Activity ID、Provider 过滤和后续事件触发扩展点；
- FitTrackee 强调自托管、活动文件和隐私。RunCrew 继续只绑定本机，目标、计划、反馈和审核记录写入本地 SQLite，不把私人原始载荷发给模型。

参考：

- <https://www.trainingpeaks.com/learn/>
- <https://help.trainingpeaks.com/hc/en-us/articles/115002250311-How-can-I-pair-and-unpair-my-planned-and-completed-workouts>
- <https://www.trainingpeaks.com/learn/trainingpeaks-athlete-user-guide/>
- <https://www.intervals.icu/features/open-api/>
- <https://github.com/samr1/fittrackee>

## 3. 用户现在可以完成什么

1. 在“训练闭环”抽屉新建训练目标，选择项目、目标日期、目标成绩和可训练星期；
2. 为下一周生成确定性保守计划草案，先查看每节训练、总时长、规则解释和数据不足警告；
3. 明确确认后激活计划；确认时服务端会重新生成草案并比对 `input_hash`，旧草案不会被静默写入；
4. 查看今日训练或下一节训练、到期课表、待核对候选、已确认数量、反馈天数和周完成率；
5. 对建议匹配或多个候选逐项确认，也可标记跳过、解除错误关联；每次写入都受计划 `revision` 保护；
6. 对已确认活动直接进入连续对话复盘，系统自动准备“复盘并讨论下一次训练”的问题；
7. 保存疲劳、酸痛、睡眠、准备度、疼痛和急性症状等结构化跑后反馈；
8. 运行 Execution、Recovery、Plan 三职责协作，并批准或拒绝计划调整；
9. 查看本周计划时长、到期训练确认率、跳过数和最近 Coach 运行记录。

## 4. 核心实现与策略

### 4.1 复用既有能力，不在前端重写规则

- 周计划仍由 `execute_weekly_plan_draft` 生成；
- 活动候选仍由 `execute_training_comparison` 计算；
- 执行确认仍由 `confirm_training_execution` 写入；
- 恢复与计划调整仍通过 `CoachOrchestratorHarness` 编排；
- 网页新增的 `TrainingOperationsService` 方法只负责产品编排、作用域校验、事务和 DTO 转换。

这样可以保证 CLI、Skill、Agent 和网页使用同一套确定性事实层。

### 4.2 草案确认采用“重放后写入”

第一次请求只返回 `TrainingPlanningResult`，不写数据库。用户确认时提交最初的请求和 `expected_input_hash`，服务端重新运行 Planning Skill。只有新旧 hash 一致且结果仍为 `ready`，才创建、填充并激活计划。

这个策略与 Coach 调整批准前的重放一致，可防止历史活动、目标或已有计划变化后仍应用过期草案。

### 4.3 候选不是事实

周视图可以返回 `suggested`、`ambiguous`、`none` 或 `confirmed`。前端只把候选展示为按钮，不会自动完成计划课。确认、跳过和解除都会携带 `base_revision`；如果另一个操作已经修改计划，旧操作返回 `stale`。

### 4.4 周进度只统计已确认事实

算法预测“可能完成”不会进入已确认数量。周完成率只用 `match_state=confirmed` 且结果为完成/部分完成的到期训练计算，因此演示指标可以追溯到用户确认和真实 Activity。

### 4.5 安全与隐私边界

- 所有新增端点继续只由回环地址上的本地服务提供；
- API DTO 使用 `extra=forbid`，前端不能注入计划内容或越权修改；
- Provider 原始 ID、原始载荷和坐标不进入新增周视图；
- 急性症状继续触发恢复安全边界，系统不做医疗诊断；
- 本阶段未调用 COROS、DeepSeek 或其他付费服务。

## 5. 新增或修改的主要文件

- `src/runcrew/domain/training_operations.py`：目标、草案、激活、周视图、进度和执行确认 DTO；
- `src/runcrew/services/training_operations.py`：产品闭环编排、重放校验、周计划选择、进度聚合；
- `src/runcrew/web/server.py`：新增目标、计划草案/激活、周视图和执行确认 API；
- `src/runcrew/web/static/chat.html`：训练闭环表单、今日训练、执行核对和周总结结构；
- `src/runcrew/web/static/chat.js`：网页状态、API 调用、候选确认和复盘跳转；
- `src/runcrew/web/static/chat.css`：新增闭环组件及响应式样式；
- `schemas/training-operations/`：新增六份网页训练运营 Schema；
- `scripts/export_training_operations_schemas.py`：同步导出新增 Schema；
- `tests/test_training_operations.py`：新增目标—计划—周视图以及候选—确认—总结端到端测试。

## 6. 实施中出现的问题与处理

### 6.1 基线命令误用了系统 Python

现象：`python scripts/verify.py` 报告找不到 pytest。

原因：系统 Python 没有安装项目开发依赖，项目依赖位于 `.venv`。

处理：改用 `.\.venv\Scripts\python.exe scripts\verify.py`，基线 130 项测试通过。该问题不是业务代码失败。

### 6.2 旧静态资源契约测试失败

现象：界面文案从“记录今日状态”改为“跑后反馈”后，旧断言失败。

处理：同步更新产品契约和静态资源版本，不保留误导性的旧文案；新增对目标创建、计划预览和今日执行入口的断言。

### 6.3 当前周与下一周计划的选择语义

风险：一个目标可以同时存在当前周和未来周的激活计划，简单使用“最近更新计划”可能把未来计划当成当前计划。

处理：优先选择当前自然周的激活计划；没有当前周计划时再选择最近的未来计划，最后才使用旧的兜底查询。

## 7. 自动化验收

```powershell
node --check src\runcrew\web\static\chat.js
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\verify.py
```

结果：132 项测试通过；项目验证脚本通过。新增测试覆盖：

- 网页创建目标；
- 计划草案保持只读；
- 错误 hash 被拒绝；
- 正确重放后激活计划；
- 周视图生成进度；
- 活动候选等待人工确认；
- 确认后计划 revision 增加并进入周完成率。

## 8. 已知限制

- Planning v1 只自动生成未来训练周，不生成进行中的当前周，也不处理比赛周；
- 周计划主要按时长和训练历史生成，尚不处理天气、海拔、力量训练与精确配速区间；
- “活动同步完成后自动弹出候选”目前表现为用户打开训练闭环时刷新，不是后台 push；
- 周总结是确定性结构化摘要，尚没有跨多周趋势图；
- 页面已通过 DOM、HTTP、JavaScript 和端到端测试，但仍需用户在本机做最终视觉和点击体验复核。

## 9. 下一阶段唯一入口

执行 M8-A2：基于已经闭合的真实产品链路，补充不含私人数据的演示种子、架构图、训练闭环时序图和 5 分钟可重复演示脚本，而不是继续扩展新的 Agent 角色。
