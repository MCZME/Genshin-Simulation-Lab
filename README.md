# Genshin Simulation Lab

Genshin Impact combat simulation and analysis toolkit.

## 仓库结构

- `backend/`：Python 后端（仿真引擎、应用服务、基础设施与测试）。所有 Python 命令在 `backend/` 目录下执行。
- `frontend/`：Web 前端工程（计划中），通过 HTTP API 调用后端能力。
- `docs/`：正式架构、契约、决策与工程文档，入口见 `docs/文档入口.md`。

## 开发运行

```powershell
cd backend
uv run pytest
uv run ruff check
uv run pyright
```

CLI 命令示例：

```powershell
uv run genshin-sim project init
uv run genshin-sim assets build --manifest data/assets/manifests/project_amber_yatta.json
uv run genshin-sim run data/inputs/barbara_demo.json
```

Web 服务启动（进入 Web 实现阶段后）：`uv run genshin-sim-server --root . --port 8000`，由 server 托管 `frontend/dist` 构建产物与 `/api/v1`。
前端开发模式：`cd frontend; pnpm dev`，Vite 将 `/api` 代理到本地后端。
