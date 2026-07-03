---
name: commit-workflow
description: 本仓库的提交、分支和 PR 工作流。用于准备提交、拆分或修正最近提交、选择提交信息、检查分支名、总结验证结果，或根据本 skill 撰写 PR/合并说明。
---

# 提交工作流

## 适用范围

将此 skill 作为本仓库 Git 与 GitHub 工作流的唯一正文来源。提交、分支、Issue、PR、合并、检查和阶段管理规则统一维护在这里，不在 `AGENTS.md` 或 `docs/` 中重复保存。

## 基本原则

- GitHub 作为代码审查、任务记录和阶段管理入口。
- `main` 保持为稳定主线，不直接提交日常开发改动。
- 每个 Pull Request 只处理一个明确主题，避免混入无关重构。
- 涉及架构、契约、资产库、结果库、数值机制或迁移策略的变更，必须在 PR 中明确标注风险并同步相关文档。
- AI/Codex 参与的改动也必须经过同样的分支、提交、检查和审查流程。

## 提交前检查

暂存前检查工作区：

```powershell
git status --short
git diff --stat
git diff --cached --stat
```

区分用户已有改动和 Codex 本次改动。不要回滚、覆盖或暂存无关的用户改动。

按一个可审查主题组织改动。如果工作区同时包含规划文档和代码实现，优先拆成不同提交；除非文档是该实现对应的直接契约更新。

提交前运行适用检查：

```powershell
uv run pytest
uv run ruff check
uv run pyright
```

纯文档改动可以不运行代码检查，但需要在最终回复或 PR 说明中明确说明。

## 提交信息

使用 Conventional Commits：

```text
type(scope): 中文摘要
```

`type` 使用标准英文类型：

```text
feat fix docs refactor test chore build ci perf ai
```

AI/Codex 协作规范、skill、agent 配置等 AI 协作资产统一使用 `ai` 类型。

需要表达模块或主题时，使用简短英文 `scope`，例如 `core`、`assets`、`config`、`github`、`migration`。

摘要使用中文，保持简短、明确，只表达一件事。

示例：

```text
docs(github): 补充 PR 与分支管理规范
docs(migration): 记录迁移阶段安排与旧项目盘点
feat(core): 建立事件与上下文骨架
test(core): 补充事件队列最小用例
ai(skill): 提取提交工作流规范
```

如果存在破坏性变更，在正文或 footer 中写 `BREAKING CHANGE:`。

生成文件、锁文件和依赖变更应与需要它们的改动放在同一个提交中。

首次提交建议使用：

```text
chore: 初始化项目骨架、文档规范与测试基础
```

## 拆分提交

使用小而聚焦的主题提交：

- `docs(...)` 用于纯文档的策略、规划、规范和记录。
- `feat(...)` 或 `fix(...)` 用于行为变化和实现。
- `test(...)` 用于不随实现一起提交的纯测试补充。
- `chore(...)` 用于不改变产品行为的项目维护。

如果刚创建的本地提交混入多个主题，在最终交付前改写它：

```powershell
git reset --soft HEAD~1
git restore --staged .
git add <topic-files>
git commit -m "type(scope): 中文摘要"
```

对每个主题重复暂存和提交。若沙箱阻止写入 Git 元数据，请请求授权。

## 分支命名

分支名使用英文小写字母、数字和短横线：

```text
<type>/<short-english-topic>
codex/<short-english-topic>
```

Codex 主导的工作使用 `codex/` 前缀。不要使用中文、空格或下划线。

示例：

```text
docs/github-workflow
feat/config-validation
fix/core-event-order
codex/project-initialization
```

如果用户要求直接翻译现有中文分支名，保留前缀，并将主题翻译为简短的英文短横线命名。

## Issue 管理

Issue 用于记录待办、缺陷、迁移任务、设计讨论和验收目标。建议标签如下：

```text
type:feat
type:fix
type:docs
type:test
type:refactor
type:chore

area:core
area:content
area:assets
area:application
area:infrastructure
area:analysis
area:ui
area:cli
area:docs

risk:architecture
risk:contract
risk:numerical
risk:migration

status:needs-confirmation
status:blocked
status:ready
status:review
```

标签使用原则：

- `type:*` 表示任务性质。
- `area:*` 表示主要影响模块。
- `risk:*` 表示需要额外审查的风险类别。
- `status:*` 表示当前处理状态。

涉及以下内容的 Issue，应优先标记 `status:needs-confirmation`：

- 顶层模块职责或依赖方向变化。
- `SimulationConfig`、资产库 schema 或结果库核心结构变化。
- 原神角色、武器、圣遗物、反应、敌人等具体机制数值。
- 新增外部数据源、抓取流程、依赖库或服务。
- 删除旧项目逻辑、删除数据文件或重写大范围模块。

## PR 说明

PR 是本项目最小审查单位。撰写 PR 说明或 GitHub 工作交接时，包含：

- 目标
- 修改范围
- 风险类型，尤其是架构、契约、资产 schema、结果 schema、数值行为或迁移风险
- 验证命令和结果
- 文档同步情况
- AI/Codex 参与范围

清楚标注不确定或高风险事项，不要把它们描述成已经定论。

建议 PR 模板：

```markdown
## 目标

## 修改范围

## 是否涉及风险
- [ ] 架构边界
- [ ] 配置契约
- [ ] 资产库 schema
- [ ] 结果库结构
- [ ] 游戏机制/数值
- [ ] 旧项目迁移

## 验证
- [ ] uv run pytest
- [ ] uv run ruff check
- [ ] uv run pyright
- [ ] 未运行，原因：

## 文档同步
- [ ] 不需要
- [ ] 已同步 docs/

## AI 参与说明
```

## 合并策略

- 推荐使用 Squash merge 合并 PR，让主线历史保持按主题聚合。
- Squash 后的提交信息仍需符合 `type(scope): 中文摘要`。
- Draft PR 用于提前暴露方向、CI 结果和审查问题；未满足验收标准前不合并。
- 重要契约或架构 PR 合并前，应至少完成一次人工确认。

## 检查要求

代码 PR 至少运行与改动相关的检查：

```powershell
uv run pytest
uv run ruff check
uv run pyright
```

文档或 skill-only 改动可不运行代码检查，但应在最终回复或 PR 中说明。

如果工具不可用或检查失败，不得伪造结果，应写明原因和当前状态。

涉及复杂数值逻辑时，应优先补充 golden case 或最小可复现实例。

## 阶段管理

建议使用 GitHub Milestones 管理阶段目标：

```text
M0 项目骨架与规范
M1 资产库最小闭环
M2 SimulationConfig 与组装
M3 core 仿真最小闭环
M4 结果库与分析
M5 CLI / UI MVP
```

每个 Milestone 应包含：

- 目标范围
- 必要文档
- 主要 Issue 或 PR
- 阶段验收标准

## AI/Codex 协作补充

- Codex 主导的工作优先使用 `codex/` 分支。
- AI/Codex 协作规范、skill、agent 配置等 AI 协作资产统一使用 `ai` 类型。
- AI 生成或修改的代码仍需遵守模块边界、契约和测试要求。
- AI 不应仅凭记忆实现游戏机制数值。
- 涉及高风险内容时，AI 应在 Issue 或 PR 中标注不确定性，并请求人工确认。
- AI 完成任务时应说明修改文件、行为变化、文档同步、检查结果和未解决风险。
