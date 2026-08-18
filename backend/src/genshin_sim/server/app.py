"""FastAPI 应用工厂。

server 不创建全局应用实例，也不处理启动方式；调用方负责注入
application 公开出口，并在后续打包阶段决定如何运行服务。
"""

from __future__ import annotations

from fastapi import FastAPI

from genshin_sim.application import ApplicationFacade
from genshin_sim.server.errors import register_error_handlers
from genshin_sim.server.routers import assets, inputs, results, runs, workflows, workspace

APP_TITLE = "Genshin Simulation Lab"
APP_VERSION = "0.1.0"


def create_app(application: ApplicationFacade) -> FastAPI:
    """Create the HTTP app bound to one application instance."""
    app = FastAPI(title=APP_TITLE, version=APP_VERSION)
    app.state.application = application
    app.include_router(assets.router)
    app.include_router(inputs.router)
    app.include_router(results.router)
    app.include_router(runs.router)
    app.include_router(workflows.router)
    app.include_router(workspace.router)
    register_error_handlers(app)
    return app
