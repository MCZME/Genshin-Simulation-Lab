---
name: commit-workflow
description: 本仓库的提交、分支、Issue 和 PR 工作流。用于准备提交、拆分或修正最近提交、选择提交信息、检查分支名、创建或处理 Issue、判断一个问题该走 Issue 还是 PR、总结验证结果，或根据本 skill 撰写 PR/合并说明。
---

# 提交工作流

## 适用范围

本 skill 是本仓库 Git 与 GitHub 工作流的唯一正文来源。提交、分支、Issue、PR、合并与检查规则统一维护在这里，不在 `AGENTS.md` 或 `docs/` 中重复保存。

## 基本原则

- GitHub 作为代码审查、任务记录和进度管理入口。
- 个人开发者定位，流程保持轻量：不启用分支保护、不预建 Issue 模板与标签集合；纪律性要求由本 skill 约定承载，CI 是唯一强制兜底。
- 分支与 PR 的强制要求针对 AI 开发；维护者可自行决定是否使用分支，允许直推 `main`。
- 每个 Pull Request 或 Issue 只处理一个明确主题，避免混入无关改动。
- 涉及架构、契约、资产库、结果库或数值机制的变更，必须明确标注风险并同步相关文档。
- AI 参与的改动经过与人工改动一致的分支、提交、检查和记录流程。

## 分支

### 命名

分支名使用英文小写字母、数字和短横线：

```text
<type>/<short-english-topic>
ai/<short-english-topic>
```

AI 主导的工作使用 `ai/` 前缀。不要使用中文、空格或下划线。

示例：

```text
feat/config-validation
fix/core-event-order
docs/github-workflow
ai/project-initialization
```

### 使用规则

- AI 开发必须在单独分支进行，不直接修改 `main`。
- 维护者可直接在 `main` 提交，不受分支限制；是否使用分支由维护者自行决定。
- 不启用分支保护。
- 分支粒度按**可独立验收的功能**切分，不按"完成某个角色/某个大模块"切分。一个分支对应一个可以单独验收的能力，使其能与其他分支并行推进。
- 分支名不表达内容版本；内容当前状态由 content 的 `version` 参数独立表达。

## Issue 与 PR 的分工

**核心判据：有没有代码可提交。**

| 情况 | 载体 | 说明 |
| --- | --- | --- |
| 一个功能需要多个 PR | Issue | 先讨论清楚，再进入开发 |
| 单一或简单的功能 | PR | 直接开 PR，不建 Issue |
| 一个问题的修复要拆多个 PR | Issue 作为父任务 | PR 引用该 Issue，全部合并后才关闭 |
| 待办、需要后续完成的内容 | Issue | 没有代码可提交，PR 无法承载 |

### 创建权限

- 维护者与 AI 都可以创建 Issue。
- **AI 创建 Issue 前必须获得维护者同意**。AI 遇到应当创建 Issue 的情况时，先向维护者提出，不自行创建。
- Issue 的具体开法不做统一限制，由当时情况决定；基础要求是创建时打上标签（见下）。

## Issue 标签

标签用于在不打开 Issue 的情况下筛选和管理 Issue 列表，属于项目管理维度。

设计原则：

- 每个维度必须解决一个实际筛选问题，不为分类而分类。
- 标签数量保持最少，少到每次创建 Issue 时都能记得打完。
- 不预建整套标签；用到时再在 GitHub 上创建。

推荐维度：

**状态**（对应阻塞与在制情况）

```text
status:blocked       卡住：缺少可信来源、缺少前置设计等
status:ready         可以开始
status:in-progress   正在做
```

**优先级**

```text
priority:high
priority:medium
priority:low
```

一个 Issue 打一个状态标签加一个优先级标签。其他维度（模块、风险等）按需临时新增，不预建。

## 提交信息

使用 Conventional Commits：

```text
type(scope): 中文摘要
```

`type` 使用标准英文类型：

```text
feat fix docs refactor test chore build ci perf ai
```

AI 协作规范、skill、agent 配置等 AI 协作资产统一使用 `ai` 类型。

需要表达模块或主题时，使用简短英文 `scope`，例如 `core`、`content`、`assets`、`config`、`github`。

摘要使用中文，保持简短、明确，只表达一件事。

示例：

```text
feat(content): 接入芭芭拉元素战技
test(reactions): 补充超导反应 golden case
docs(contract): 补充护盾系统契约边界
ai(skill): 收敛提交工作流范围
```

如果存在破坏性变更，在正文或 footer 中写 `BREAKING CHANGE:`。

生成文件、锁文件和依赖变更应与需要它们的改动放在同一个提交中。

## 提交前检查

暂存前检查工作区：

```powershell
git status --short
git diff --stat
git diff --cached --stat
```

区分维护者已有改动和 AI 本次改动。不要回滚、覆盖或暂存无关的改动。

按一个可审查主题组织改动。如果工作区同时包含规划文档和代码实现，优先拆成不同提交；除非文档是该实现对应的直接契约更新。

如果刚创建的本地提交混入多个主题，在交付前改写它：

```powershell
git reset --soft HEAD~1
git restore --staged .
git add <topic-files>
git commit -m "type(scope): 中文摘要"
```

对每个主题重复暂存和提交。若沙箱阻止写入 Git 元数据，请求授权。

## 验证要求

本地按改动范围运行窄路径，CI 全量兜底。

backend/ 下：

```powershell
uv run ruff check
uv run pyright
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/golden
```

frontend/ 下：

```powershell
pnpm lint
pnpm typecheck
pnpm test
```

纯文档或 skill 改动可以不运行代码检查，但需在交付说明或 PR 中明确说明。

小修改只运行与改动对应的窄测试路径；全量 `pytest` 仅在大改动或改动横跨多个模块时运行。

涉及复杂数值逻辑时，应优先补充 golden case 或最小可复现实例。

如果工具不可用或检查失败，不得伪造结果，应写明原因和当前状态。

## Issue 说明

Issue 用于记录需要讨论的功能规划、需要后续完成的待办，以及没有代码可提交的问题。

**Issue 的内容不做格式限制**，由创建者按当时情况自由书写。不要求固定的章节、字段或模板结构。

唯一的基础要求是：创建 Issue 时打上标签（状态与优先级，见上）。

## PR 说明

PR 是代码改动的最小审查与合入单位。一个 PR 只处理一个主题。撰写 PR 说明时包含：

- 目标
- 修改范围
- 关联 Issue（如适用）
- 风险类型，尤其是架构、契约、资产 schema、结果库 schema、数值行为风险
- 验证命令和结果
- 文档同步情况

清楚标注不确定或高风险事项，不要把它们描述成已经定论。

PR 模板已落地为 `.github/PULL_REQUEST_TEMPLATE.md`。

## Issue 与 PR 的评论

评论与直接编辑原文都可能用到，二者做的事不同。Issue 与 PR 共用本判据。

**核心判据：这次改动是否改变了原本在说的东西。**

| 情况 | 做法 | 说明 |
| --- | --- | --- |
| 同一件事的取值或表述变了 | **直接编辑原文** | 例如武器攻击力从 `100` 改为 `120`、修正措辞、补充范围说明。原文与评论表达的是同一命题，改掉更干净 |
| 新增了原本没有的内容 | **新增评论** | 例如原本只实现武器，后来在其中加入一个 Buff。原本没有这件事，写进原文会让后来读者以为一开始就是这么设计的 |
| 原结论被推翻或方向改变 | **新增评论** | 保留原结论与改变的原因，再按需同步正文 |

理由：GitHub 的编辑历史记录的是"改了哪些字"，评论记录的是"为什么后来加了这件事"。前者是文本 diff，后者是意图。新增内容若直接写进原文，丢失的是"这是后来才加的"这一事实。

补充规则：

- 直接编辑原文时，不需要在正文里保留变更历史；历史由 Git 编辑记录与评论承载。
- 评论内容不做格式限制。
- 本判据用于应对讨论完成后的临时变化。正常流程是创建 Issue 或 PR 之前先讨论清楚内容，不把它当作日常操作。
- 判断不清时，选择新增评论：多留一条过程记录，比丢失变更原因更容易接受。

## 合并策略

- 使用 Squash merge 合并 PR，让主线历史保持按主题聚合。
- Squash 后的提交信息仍需符合 `type(scope): 中文摘要`。
- Draft PR 用于提前暴露方向、CI 结果和待确认问题；未满足验收标准前不合并。
- 合并由维护者决定。维护者按 CI 结果判断，不要求逐行审查。

## 版本

- `git tag` 是项目唯一版本号；代码内不维护包版本常量（`pyproject.toml` 的 `version` 仅为打包样板，frontend 为私有应用不发布）。
- 只在 `main` 上、CI 通过后打 tag。
- Release notes 手动撰写，从该版本区间的 PR 列表与提交归纳，不引入自动生成工具。

## 检查要求

CI 在 PR 与 `main` push 时运行全量检查兜底（定义在 `.github/workflows/ci.yml`）：

- backend：`uv sync --frozen` 后运行 ruff check、pyright、pytest 全量。
- frontend：`pnpm install --frozen-lockfile` 后运行 lint、typecheck、test 全量。

本地求快（窄路径），CI 求全（全量）。

## AI 协作补充

- AI 主导的工作使用 `ai/` 分支，并在单独分支中开发，不直接修改 `main`。
- AI 协作规范、skill、agent 配置等 AI 协作资产统一使用 `ai` 类型提交。
- AI 生成或修改的代码仍需遵守模块边界、契约和测试要求。
- AI 不应仅凭记忆实现游戏机制数值；缺少可信来源时不得补齐，应作为阻塞项提出。
- AI 创建 Issue 前必须获得维护者同意。
- 涉及高风险内容时，AI 应在 Issue 或 PR 中标注不确定性，并请求维护者确认。
- AI 完成任务时应说明修改文件、行为变化、文档同步、检查结果和未解决风险。
