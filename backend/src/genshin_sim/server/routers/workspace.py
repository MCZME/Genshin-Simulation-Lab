"""工作区 HTTP 路由。"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request

from genshin_sim.application import ApplicationFacade
from genshin_sim.server.dto.workspace import WorkspaceResponse

router = APIRouter(prefix="/api/v1", tags=["workspace"])


@router.get("/workspace", response_model=WorkspaceResponse)
def get_workspace(request: Request) -> WorkspaceResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    info = facade.get_workspace()
    return WorkspaceResponse(
        data_dir=info.data_dir,
        asset_db_version=info.asset_db_version,
        initialized=info.initialized,
    )
