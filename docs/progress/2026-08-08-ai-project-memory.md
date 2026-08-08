# AI 项目记忆与交接体系

## 目标

解决“代码已经存在，但下一个 AI 不知道为什么这样做、做到哪里、下一步是什么”的问题。

## 新增文件

- `AGENTS.md`：AI 必读入口、规则、完成定义；
- `CONTRIBUTING.md`：开发与文档工作流；
- `SECURITY.md`：真实运动数据和 Token 安全边界；
- `CHANGELOG.md`：用户可见和架构级变更；
- `docs/PROJECT_CONTEXT.md`：项目目的和范围；
- `docs/CURRENT_STATE.md`：当前唯一状态源；
- `docs/ARCHITECTURE.md`：模块和数据流；
- `docs/ROADMAP.md`：阶段与验收标准；
- `docs/PROGRESS.md`：阶段记录索引；
- `docs/progress/`：不可覆盖的历史交接记录；
- `docs/adr/`：架构决策记录；
- `docs/GLOSSARY.md`：术语解释；
- `scripts/verify.py`：统一项目自检入口。
- 初始化独立 Git 仓库并将默认分支设为 `main`；
- 创建首次提交 `d157a78 chore: bootstrap RunCrew data vertical slice`；
- 创建并推送 GitHub 私有仓库 `QRui6/RunCrew`。

## 以后每阶段写在哪里

- 当前做到哪里：`docs/CURRENT_STATE.md`；
- 阶段是否完成：`docs/ROADMAP.md`；
- 本阶段具体做了什么：`docs/progress/YYYY-MM-DD-阶段名.md`；
- 阶段列表：`docs/PROGRESS.md`；
- 功能变化：`CHANGELOG.md`；
- 为什么选择某个方案：`docs/adr/`；
- 模块边界变化：`docs/ARCHITECTURE.md`。

## 验收

使用 `scripts/verify.py` 检查必需文档、Python 编译和全部测试。
