# Codex 项目协作规则

本文档是仓库级 Codex/AI 协作入口。处理本项目任务时，先阅读本文件，再按任务范围阅读 `docs/` 中的正式文档。详细设计、契约、迁移清单和 Git 工作流不在本文件展开。

## 仓库结构

- `backend/`：Python 后端。包含 `src/genshin_sim/` 包、`tests/`、`pyproject.toml`、`uv.lock`、`.python-version`、配置模板与本地数据目录。
- `frontend/`：Web 前端工程（计划中）。只通过 HTTP API 调用后端能力，不 import 任何 Python 代码；具体规范见 `docs/工程/前端工程规范.md`。
- `docs/`：正式文档，按 `架构/`、`契约/`、`决策/`、`工程/` 分区。
- `prototypes/`：本地 UI 原型，不提交，计划删除。

## 项目定位

- 本项目是旧项目的移植与重建，不是简单复制旧代码。
- 顶层模块边界、资产/配置契约和核心运行时骨架已经建立；当前重点是按小切片迁移可验证的机制与内容能力。
- 仿真数值和机制行为必须可验证；不要仅凭记忆、旧代码或外部资料单独实现角色、武器、圣遗物或反应细节。
- 旧项目位置：`E:\project\Genshin Damage calculation`。旧代码和旧测试只作行为线索与覆盖参考，不能直接成为新架构契约。

## 必读文档

开始较大改动前，至少阅读：

- [文档入口](docs/文档入口.md)
- [项目决策记录](docs/决策/项目决策记录.md)
- [模块边界设计](docs/架构/模块边界设计.md)
- [系统自治与跨系统协调](docs/决策/系统自治与跨系统协调.md)
- [测试规范](docs/工程/测试规范.md)

涉及数据、配置或组装时，还要阅读：

- [资产数据库设计](docs/契约/资产数据库设计.md)
- [仿真配置契约与最小闭环](docs/契约/仿真配置契约与最小闭环.md)

涉及迁移时，还要阅读：

- [迁移阶段安排](docs/工程/迁移阶段安排.md)

涉及原神机制、数值或元素反应时，还要阅读：

- [原神游戏机制实现规范](docs/工程/原神游戏机制实现规范.md)
- [元素附着、ICD 与反应设计规范](docs/工程/元素附着、ICD与反应设计规范.md)
- 对应系统的架构/契约文档；元素反应统一从[架构索引](docs/架构/系统/元素反应/文档索引.md)和[契约索引](docs/契约/元素反应/文档索引.md)进入

Git、分支、Issue、PR 与合并规则统一使用仓库 skill：`.codex/skills/commit-workflow/SKILL.md`。

## 架构硬规则

- Python 顶层模块（位于 `backend/src/genshin_sim/`）：`core/`、`content/`、`assets/`、`infrastructure/`、`application/`、`analysis/`、`cli/`、`server/`。
- `frontend/` 是独立的前端工程，不属于 Python 顶层模块，不参与 Python 模块依赖规则。
- `core/` 是纯仿真运行时核心，不依赖数据库、UI、应用层或具体内容实现。
- `core/` 不能 import `assets`、`infrastructure`、`application`、`ui`、`content`。
- `assets/` 保存资产数据对象、仓库协议与相关错误；不实现 SQLite 访问。
- `content/` 保存具体角色、武器、圣遗物和 handler 实现，可以依赖 `core/` 与 `assets/` 数据对象。
- `application/` 是 Python 后端唯一公开能力出口，负责编排用例与组装，不直接编写具体 SQLite 查询；`cli/` 与 `server/` 只能通过其公开接口调用能力。
- `infrastructure/` 保存 SQLite、文件存储、日志、任务执行等具体技术实现。
- `analysis/` 只做结果加工、聚合、对比和报告模型，不写库、不画 UI。
- `cli/` 通过 `application/` 调用能力，不直接访问 SQLite 或组装仿真核心对象。
- `server/` 是与 `cli/` 同级的网页服务入口，通过 `application/` 调用能力；不直接访问 SQLite 或组装仿真核心对象。
- `frontend/` 只通过 `server/` 暴露的 HTTP API 调用应用能力，不直接访问 SQLite，不组装仿真核心对象。
- 旧 Flet 壳已移除（2026-08-17）。
- `core/systems/<domain>/` 实行系统自治：每个系统只拥有本领域的状态、公式、计划、写入口和领域事实。
- 一个领域系统不能 import 另一个领域系统的具体 Runtime 或 Store，也不能直接修改另一个系统的状态；只读依赖必须通过中立共享模型或窄协议表达。
- 跨系统仿真流程统一放在 `core/coordination/`；写协调器负责编排准备、校验、无回调提交和事实顺序，只读条件协调器只组合领域条件证据且不得推进时间、修改状态、发布事实或提供预留。
- `core/coordination/` 不拥有长期领域状态，不实现领域公式，不提供全局万能调度器；每个 coordinator 只处理一个明确跨系统流程。
- `EventEngine` 只发布和记录已经发生的事实，不作为跨系统写入或当前结算递归调用入口。
- 有身份和生命周期的运行态由对应领域系统直接拥有；不得为了复用而把不同机制塞进通用 Store。

## 文档规则

- `docs/` 下文件夹和文件名使用中文。
- 文档正文使用中文。
- 文档路径引用使用相对链接。
- 改动架构边界、配置契约、资产库 schema、结果数据模型或迁移策略时，必须同步更新对应文档。
- 正式文档按唯一职责落位：`架构/`、`契约/`、`决策/`、`工程/`；草案、待确认和临时资料必须显式标注状态。
- 文档与代码冲突时，根据已确认资料、正式契约和 golden case 判断真值，再修正错误一侧。

## 开发规则

- 优先保持改动范围小，避免顺手重构无关模块。
- 迁移旧项目能力时，先确定行为目标、可信来源和验收方式，再写实现。
- 复杂数值逻辑优先补 golden case 或最小可复现实例；`tests/golden/` 按业务领域组织，不按交付版本号分类。
- 不把显示名称作为仿真识别依据；资产引用统一使用 `asset_key`。
- `handler_key` 是代码实现绑定入口，不要用显示名称或 `asset_key` 直接绑定行为。
- 装配链路是 `资产 -> handler_key -> content contribution -> runtime 注入`；缺资产、缺 handler、JSON 格式错误应在组装阶段报错，不延迟到仿真运行中。
- 纯公式解析、状态提交和外层编排必须分离；状态先计划并原子提交，事实后发布。
- 相同配置、资产版本、输入、帧顺序和随机种子必须得到相同结果。

## AI 工作流程

1. 先读本文件、任务相关正式文档和现有代码。
2. 判断是否涉及架构、契约、数值、元素机制或迁移风险。
3. 小步实现，优先沿用现有目录、命名、注册表和组装入口。
4. 同步必要文档；Git/PR 工作流遵循 `commit-workflow` skill。
5. 运行可用检查，并在最终回复中说明修改范围、文档同步、检查结果和未解决风险。

遇到以下情况应请求人工确认：

- 改变顶层模块职责或依赖方向。
- 改变 `SimulationConfig`、资产库 schema 或结果库核心结构。
- 引入新的外部依赖、数据源、网络抓取流程或大型工具链。
- 实现尚无可信来源或 golden case 支撑的游戏机制数值。
- 删除或覆盖用户已有改动。
- 大幅改写 UI 产品形态或核心交互模式。

## 验证命令

当前项目使用 `pytest`、`ruff`、`pyright` 作为第一批质量工具。

常用命令（在 `backend/` 目录下执行）：

```powershell
uv run pytest
uv run pytest --cov=genshin_sim
uv run ruff check
uv run ruff format
uv run pyright
```

前端质量工具进入实现阶段后启用（在 `frontend/` 目录下执行）：

```powershell
pnpm lint
pnpm typecheck
pnpm test
```

按改动范围选择更窄的测试路径，例如：

```powershell
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/golden
```

如果命令不可用，不要伪造结果；在最终回复中说明未运行或失败原因。
