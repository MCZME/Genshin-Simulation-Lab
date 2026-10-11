"""FastAPI 应用工厂。

server 不创建全局应用实例，也不处理启动方式；调用方负责注入
application 公开出口，并在后续打包阶段决定如何运行服务。
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from genshin_sim.application import ApplicationFacade
from genshin_sim.server.errors import register_error_handlers
from genshin_sim.server.request_logging import RequestLoggingMiddleware
from genshin_sim.server.routers import (
    analysis,
    assets,
    inputs,
    results,
    runs,
    settings,
    workflows,
    workspace,
)

APP_TITLE = "Genshin Simulation Lab"
APP_VERSION = "0.1.0"

_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
_ENTRY_CACHE_CONTROL = "no-cache"


class _FrontendStaticFiles(StaticFiles):
    """带缓存策略的前端静态托管。

    Vite 产物中 assets/ 下文件名带内容 hash，可永久缓存；入口页
    index.html 不带 hash，必须 no-cache 强制重验证，否则重建后浏览器
    会按启发式缓存继续使用旧入口页。
    """

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        if scope.get("path", "").startswith("/assets/"):
            response.headers["Cache-Control"] = _ASSET_CACHE_CONTROL
        else:
            response.headers["Cache-Control"] = _ENTRY_CACHE_CONTROL
        return response


def create_app(
    application: ApplicationFacade,
    *,
    static_dir: str | Path | None = None,
) -> FastAPI:
    """Create the HTTP app bound to one application instance.

    static_dir 指向前端构建产物目录（需含 index.html）；提供时挂载同源
    静态托管，未提供则只提供 HTTP API。
    """

    app = FastAPI(title=APP_TITLE, version=APP_VERSION)
    app.state.application = application
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(analysis.router)
    app.include_router(assets.router)
    app.include_router(inputs.router)
    app.include_router(results.router)
    app.include_router(runs.router)
    app.include_router(workflows.router)
    app.include_router(settings.router)
    app.include_router(workspace.router)
    register_error_handlers(app)
    if static_dir is not None:
        _mount_frontend(app, Path(static_dir))
    return app


def _mount_frontend(app: FastAPI, static_dir: Path) -> None:
    """挂载前端构建产物；目录无效在组装阶段报错，不延迟到请求。"""

    if not static_dir.is_dir() or not (static_dir / "index.html").is_file():
        raise RuntimeError(
            f"前端静态目录无效，需为包含 index.html 的构建产物目录：{static_dir}"
        )
    # 必须在所有路由之后挂载：/api/v1 与 /docs、/openapi.json 先命中，
    # 其余路径（含 /）才落到静态文件，未知名由 StaticFiles 返回 404。
    app.mount("/", _FrontendStaticFiles(directory=static_dir, html=True), name="frontend")
