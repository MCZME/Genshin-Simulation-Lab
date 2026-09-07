# Genshin Simulation Lab

Genshin Impact 战斗仿真与分析工具。项目以可验证为核心目标：仿真数值与机制行为必须可复现（相同配置、资产版本、输入、帧顺序与随机种子得到相同结果）；角色、武器、圣遗物与反应细节在接入前先确定可信来源，并以 golden case 锁定预期值。

> 本项目为非官方的粉丝研究与仿真工具，与 HoYoverse / miHoYo 无关，不用于数据抓取或商业用途。

## 仓库结构

- `backend/`：Python 后端。Python 顶层模块位于 `backend/src/genshin_sim/`，按职责分为：
  - `core/`：纯仿真运行时核心（领域系统、协调器、事件引擎），不依赖数据库、UI 或具体内容实现；
  - `content/`：具体角色、武器、圣遗物与 handler 实现；
  - `assets/`：资产数据对象与仓库协议；
  - `infrastructure/`：SQLite、文件存储、日志等具体技术实现；
  - `application/`：唯一公开能力出口，编排用例与组装；
  - `cli/` 与 `server/`：命令行与网页服务入口，只通过 `application/` 调用能力。
- `frontend/`：独立 Web 前端工程（React + TypeScript + Vite + React Flow），只通过 HTTP API 调用后端能力，详见 [frontend/README.md](frontend/README.md)。
- `docs/`：正式文档，按 `架构/`、`契约/`、`决策/`、`工程/` 分区，入口见 [docs/文档入口.md](docs/文档入口.md)。
- `AGENTS.md`：Codex/AI 协作规则与架构硬规则。

## 环境要求

- 后端：Python 3.14+ 与 [uv](https://docs.astral.sh/uv/)。
- 前端（仅开发或构建 Web 界面时需要）：Node.js 22.12+ 与 pnpm 11。

## 后端开发

所有 Python 命令在 `backend/` 目录下执行：

```powershell
uv sync          # 安装依赖
uv run pytest    # 测试
uv run ruff check
uv run pyright
```

### CLI 典型流程

CLI 入口为 `genshin-sim`，所有能力通过 `application/` 公开。典型流程：初始化项目配置 → 构建资产库 → 校验输入 → 运行模拟 → 读取结果：

```powershell
uv run genshin-sim project init
uv run genshin-sim assets build --manifest data/assets/manifests/project_amber_yatta_full.json
uv run genshin-sim input validate data/inputs/barbara_demo.json
uv run genshin-sim run data/inputs/barbara_demo.json
uv run genshin-sim results list
uv run genshin-sim results inspect <session_id>
uv run genshin-sim results events <session_id>
```

主要子命令一览：

| 子命令 | 说明 |
| --- | --- |
| `project init` / `project show` | 初始化与查看项目配置（`config.toml` 与工作区路径） |
| `assets init` / `build` / `validate` / `info` | 初始化、构建、校验资产库并打印信息 |
| `assets list` / `inspect` / `show-handlers` | 浏览资产与 handler_key 绑定 |
| `assets fetch-source` / `build-manifest` / `audit-manifest` | 资产来源抓取与 manifest 构建、审计 |
| `assets set-handler` / `reset-handler` / `sync-handlers` | 维护 handler_key 绑定并写回 manifest |
| `input validate` / `input list` | 校验与列出模拟输入文件 |
| `run <input>` | 通过应用服务运行一次模拟 |
| `results init` / `list` / `inspect` / `events` | 查询本地结果库中的运行与事件 |

`run` 与 `results` 支持 `--db` / `--results-db` / `--root` 覆盖默认路径；资产库默认位于 `<root>/data/assets/assets.db`。

## Web 服务与前端

后端 Web 服务（FastAPI + Uvicorn）托管 `frontend/dist` 构建产物与 `/api/v1`：

```powershell
uv run genshin-sim-server --root . --port 8000
```

使用 Web 界面前先构建前端产物：

```powershell
cd frontend
pnpm install
pnpm build
```

前端开发模式（Vite 默认端口 5173，`/api` 代理到 `127.0.0.1:8000`，需另起后端服务）：

```powershell
pnpm dev
```

## 文档

- 文档入口：[docs/文档入口.md](docs/文档入口.md)（当前生效架构、契约与工程规范索引）。
- 决策记录：`docs/决策/`，按「产品与技术选型 / 架构与运行时 / 契约与数值冻结 / UI与工作流 / 工程与流程」主题分区。
- 当前待办：[docs/工程/后续实现计划.md](docs/工程/后续实现计划.md)。
- 开发规则、架构硬规则与验证命令：[AGENTS.md](AGENTS.md)。
