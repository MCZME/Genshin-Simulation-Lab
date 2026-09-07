# Genshin Simulation Lab - backend

Python 后端：仿真运行时核心、应用服务、基础设施与 CLI / Web 服务入口。Python 3.14+，使用 [uv](https://docs.astral.sh/uv/) 管理依赖与虚拟环境。

仓库整体说明、Web 服务与前端见根目录 [README.md](../README.md)；开发规则与架构硬规则见 [AGENTS.md](../AGENTS.md)。

## 目录结构

```text
backend/
├── src/genshin_sim/
│   ├── core/             # 纯仿真运行时核心，不依赖数据库、UI、应用层或具体内容实现
│   │   ├── systems/      # 领域系统：元素附着(aura)、附着ICD、状态效果(buff)、冷却、伤害、
│   │   │                 #   元素能量、治疗、生命值、附魔(infusion)、月兆、移动、
│   │   │                 #   元素反应(reaction)、元素共鸣(resonance)、护盾
│   │   ├── coordination/ # 跨系统协调器：元素反应、共鸣反应、角色受伤、状态效果最大生命、角色能力条件
│   │   ├── simulation/   # 仿真主流程：时钟、上下文、意图队列、结算管线
│   │   ├── actions/      # 动作定义、解释器与机制请求管理
│   │   ├── attributes/   # 属性计算（基础值、modifier、provider）
│   │   ├── space/        # 战场空间：空间实体与范围形状
│   │   ├── entity_states/# 实体运行态：角色、目标、生命值、能量、内容状态与生命周期
│   │   ├── events/       # 事件模型、payload 与事件引擎（只发布已发生的事实）
│   │   ├── impacts/      # Impact 模型与分发运行时
│   │   ├── snapshots/    # 运行态快照
│   │   ├── elements/     # 元素类型与元素量基础模型
│   │   └── contracts/    # 仿真内部契约：意图、阶段、状态 schema、JSON 序列化
│   ├── content/          # 具体角色、武器、圣遗物与 handler 实现（characters/weapons/artifacts/
│   │                     #   team/generic/definitions；test/ 为测试用 content）
│   ├── assets/           # 资产数据对象、仓库协议与相关错误，不做 SQLite 访问
│   ├── infrastructure/   # 具体技术实现：assets_sqlite（资产库）、assets_project_amber（来源抓取）、
│   │                     #   results_sqlite（结果库与分析查询）、file_storage、logging、jobs
│   ├── application/      # 唯一公开能力出口：assembly（资产→runtime 装配链）、services（用例门面）、
│   │                     #   batch/execution/jobs（运行与批处理）、input、config
│   ├── cli/              # genshin-sim 命令行入口
│   └── server/           # genshin-sim-server 网页服务入口（FastAPI 路由 + DTO）
├── tests/
│   ├── unit/             # 单元测试，按 core/content/assets/infrastructure/application/cli/server 分层
│   ├── integration/      # 跨模块集成测试（content/infrastructure/reactions 等）
│   ├── golden/           # golden case，按业务领域组织（artifacts/damage/infusion/moonsign/reactions/resonance）
│   └── helpers/          # 测试辅助
├── data/                 # 本地工作区，由 project init 与各命令管理
└── pyproject.toml
```

## 依赖方向

- `core/` 是纯仿真核心：不 import `assets`、`infrastructure`、`application`、`ui`、`content`，不依赖数据库。
- `content/` 可以依赖 `core/` 与 `assets/` 的数据对象；具体机制数值必须来自真实资产与 handler，不由 `core/` 硬编码。
- `assets/` 只保存数据对象与仓库协议；SQLite 访问在 `infrastructure/`。
- `application/` 编排用例与组装，是唯一公开能力出口；`cli/` 与 `server/` 只通过它调用能力，不直接访问 SQLite 或组装仿真核心对象。
- 领域系统自治：一个系统不 import 另一个系统的 Runtime / Store；跨系统流程统一放 `core/coordination/`，每个协调器只处理一个明确的跨系统流程。

完整边界规则见 [模块边界设计](../docs/架构/模块边界设计.md) 与 [系统自治与跨系统协调规范](../docs/工程/系统自治与跨系统协调规范.md)。

## 装配链路

仿真运行对象按「资产 → `handler_key` → content contribution → runtime 注入」装配：资产数据库提供资产与 handler 绑定，`content/` 按 `handler_key` 提供行为，`application/assembly/` 在组装阶段完成校验与注入。缺资产、缺 handler、JSON 格式错误都在组装阶段报错，不延迟到仿真运行中。资产识别只用 `asset_key`，不使用显示名称。

## 开发与质量检查

所有命令在 `backend/` 目录下执行：

```powershell
uv sync          # 安装依赖
uv run pytest    # 测试
uv run ruff check
uv run ruff format
uv run pyright
```

测试用例较多，按改动范围选择更窄的路径即可，全量 `pytest` 仅在大改动或跨模块改动时运行：

```powershell
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/golden
uv run pytest --cov=genshin_sim
```

golden case 按业务领域组织在 `tests/golden/`；新机制数值接入前先确定可信来源，预期值记录出处与适用版本，测试规范见 [测试规范](../docs/工程/测试规范.md)。

## 数据工作区

`data/` 是本地工作区，默认路径可被 CLI 参数覆盖：

| 目录 | 内容 |
| --- | --- |
| `data/assets/` | 资产库（`assets.db`）、`manifests/` 资产清单、`sources/` 抓取来源 |
| `data/inputs/` | 模拟输入文件 |
| `data/results/` | 结果库（`results.db`）与导出 |
| `data/workflows/` | 画布工作流定义 |
| `data/logs/` | 运行日志 |
| `data/templates/`、`data/exports/` | 模板与导出目录 |

项目配置 `config.toml` 由 `uv run genshin-sim project init` 生成，`project show` 可查看全部工作区路径。

## CLI 与服务入口

| 入口 | 定义 | 说明 |
| --- | --- | --- |
| `genshin-sim` | `src/genshin_sim/cli/main.py` | 命令行：project / assets / input / run / results |
| `genshin-sim-server` | `src/genshin_sim/server/main.py` | FastAPI + Uvicorn 网页服务，托管前端构建产物与 `/api/v1` |

典型命令流程与子命令一览见根目录 [README.md](../README.md)。

## 延伸文档

- 文档总入口：[docs/文档入口.md](../docs/文档入口.md)
- 架构：[模块边界设计](../docs/架构/模块边界设计.md)
- 契约：[资产数据库契约](../docs/契约/资产数据库契约.md)、[模拟输入契约](../docs/契约/模拟输入契约.md)、[结果库契约](../docs/契约/结果库契约.md)
- 工程：[系统自治与跨系统协调规范](../docs/工程/系统自治与跨系统协调规范.md)、[测试规范](../docs/工程/测试规范.md)
