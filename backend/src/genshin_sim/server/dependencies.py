"""HTTP 路由共享依赖。"""

from __future__ import annotations

from typing import cast

from fastapi import Request

from genshin_sim.application import ApplicationError, ApplicationFacade


def require_initialized(request: Request) -> None:
    """除 workspace 外的 MVP 端点要求工作区已初始化。"""

    facade = cast(ApplicationFacade, request.app.state.application)
    if not facade.get_workspace().initialized:
        raise ApplicationError(
            "workspace_not_initialized",
            "工作区尚未初始化",
        )
