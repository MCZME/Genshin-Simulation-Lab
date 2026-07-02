# GitHub 管理规范

本文档定义本项目在 GitHub 上的分支、Issue、Pull Request、提交与检查规则。目标是让重建过程中的架构、契约、数值和迁移改动可追踪、可审查、可回退。

## 1. 基本原则

- GitHub 作为代码审查、任务记录和阶段管理入口。
- `main` 保持为稳定主线，不直接提交日常开发改动。
- 每个 Pull Request 只处理一个明确主题，避免混入无关重构。
- 涉及架构、契约、资产库、结果库、数值机制或迁移策略的变更，必须在 PR 中明确标注风险并同步相关文档。
- AI/Codex 参与的改动也必须经过同样的分支、提交、检查和审查流程。

## 2. 分支规范

分支名统一使用英文，格式如下：

```text
<type>/<short-english-topic>
codex/<short-english-topic>
```

规则：

- 只使用小写英文字母、数字和短横线 `-`。
- 不使用中文、空格或下划线。
- `type` 优先使用 `feat`、`fix`、`docs`、`test`、`refactor`、`chore`、`build`、`ci`、`perf`。
- Codex 或 AI 主导完成的分支使用 `codex/` 前缀。
- 分支主题应短而明确，表达任务范围，不表达实现细节。

示例：

```text
docs/github-workflow
feat/config-validation
feat/assets-sqlite-schema
fix/core-event-order
test/golden-cases
codex/simulation-config-contract
```

## 3. 提交规范

提交信息沿用项目既有 Conventional Commits 规则：

```text
type(scope): 中文摘要
```

示例：

```text
docs(github): 补充 PR 与分支管理规范
feat(config): 增加仿真配置基础校验
test(core): 补充事件队列最小用例
```

规则：

- `type` 使用标准英文类型。
- `scope` 可选，建议使用模块名或主题名。
- 摘要使用中文，简短、明确，只表达一件事。
- 一次提交只做一类事情，不混入无关改动。
- 破坏性变更在正文或 footer 中写 `BREAKING CHANGE:`。

## 4. Issue 管理

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

## 5. Pull Request 规范

PR 是本项目最小审查单位。每个 PR 应说明：

- 目标：解决什么问题。
- 修改范围：改了哪些模块或文档。
- 风险类型：是否涉及架构、契约、数值、迁移等高风险内容。
- 验证方式：运行了哪些检查，或说明未运行原因。
- 文档同步：是否需要更新 `docs/`，以及更新位置。
- AI 参与说明：如果 AI/Codex 参与了实现，应说明参与范围。

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

## 6. 合并策略

- 推荐使用 Squash merge 合并 PR，让主线历史保持按主题聚合。
- Squash 后的提交信息仍需符合 `type(scope): 中文摘要`。
- Draft PR 用于提前暴露方向、CI 结果和审查问题；未满足验收标准前不合并。
- 重要契约或架构 PR 合并前，应至少完成一次人工确认。

## 7. 检查要求

当前项目第一批质量工具为：

```powershell
uv run pytest
uv run ruff check
uv run pyright
```

检查规则：

- 代码 PR 至少运行与改动相关的检查。
- 文档 PR 可不运行代码检查，但应在 PR 中说明。
- 如果工具不可用或检查失败，不得伪造结果，应在 PR 中写明原因和当前状态。
- 涉及复杂数值逻辑时，应优先补充 golden case 或最小可复现实例。

## 8. 阶段管理

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

- 目标范围。
- 必要文档。
- 主要 Issue 或 PR。
- 阶段验收标准。

## 9. AI/Codex 协作补充

- Codex 主导的工作优先使用 `codex/` 分支。
- AI 生成或修改的代码仍需遵守模块边界、契约和测试要求。
- AI 不应仅凭记忆实现游戏机制数值。
- 涉及高风险内容时，AI 应在 Issue 或 PR 中标注不确定性，并请求人工确认。
- AI 完成任务时应说明修改文件、行为变化、文档同步、检查结果和未解决风险。
