"""界面偏好设置 HTTP 路由；持久化到项目配置（config.toml）的 ui 节。"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request

from genshin_sim.application import ApplicationFacade
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.settings import (
    UiSettingsResponse,
    UiSettingsUpdateRequest,
    WorkspaceSettingsView,
)

router = APIRouter(
    prefix="/api/v1/settings",
    tags=["settings"],
    dependencies=[Depends(require_initialized)],
)


@router.get("", response_model=UiSettingsResponse)
def get_ui_settings(request: Request) -> UiSettingsResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    settings = facade.get_ui_settings()
    workspace = facade.get_workspace()
    return UiSettingsResponse(
        run_animation=settings.run_animation,
        workspace=WorkspaceSettingsView(data_dir=workspace.data_dir),
    )


@router.put("", response_model=UiSettingsResponse)
def save_ui_settings(
    payload: UiSettingsUpdateRequest,
    request: Request,
) -> UiSettingsResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    settings = facade.save_ui_settings(run_animation=payload.run_animation)
    workspace = facade.get_workspace()
    return UiSettingsResponse(
        run_animation=settings.run_animation,
        workspace=WorkspaceSettingsView(data_dir=workspace.data_dir),
    )
