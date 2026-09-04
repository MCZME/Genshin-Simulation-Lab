"""界面偏好与开发者设置 HTTP 路由；持久化到项目配置（config.toml）。

开发者模式开关修改 config.toml 的 developer 节，需要重启服务
（重建内容注册表与资产仓库组合）后生效。
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request

from genshin_sim.application import ApplicationFacade
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.settings import (
    DeveloperSettingsView,
    UiSettingsResponse,
    UiSettingsUpdateRequest,
    WorkspaceSettingsView,
)

router = APIRouter(
    prefix="/api/v1/settings",
    tags=["settings"],
    dependencies=[Depends(require_initialized)],
)


def _settings_response(facade: ApplicationFacade) -> UiSettingsResponse:
    settings = facade.get_ui_settings()
    developer = facade.get_developer_settings()
    workspace = facade.get_workspace()
    return UiSettingsResponse(
        run_animation=settings.run_animation,
        developer=DeveloperSettingsView(enabled=developer.enabled),
        workspace=WorkspaceSettingsView(data_dir=workspace.data_dir),
    )


@router.get("", response_model=UiSettingsResponse)
def get_ui_settings(request: Request) -> UiSettingsResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return _settings_response(facade)


@router.put("", response_model=UiSettingsResponse)
def save_ui_settings(
    payload: UiSettingsUpdateRequest,
    request: Request,
) -> UiSettingsResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    facade.save_ui_settings(run_animation=payload.run_animation)
    if payload.developer_enabled is not None:
        facade.save_developer_settings(enabled=payload.developer_enabled)
    return _settings_response(facade)
