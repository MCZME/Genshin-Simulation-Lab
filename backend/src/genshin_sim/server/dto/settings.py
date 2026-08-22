"""界面偏好设置 HTTP DTO。"""

from __future__ import annotations

from pydantic import BaseModel


class WorkspaceSettingsView(BaseModel):
    """配置面板展示的工作区信息；data_dir 为用户自配项，只读展示。"""

    data_dir: str


class UiSettingsResponse(BaseModel):
    """GET/PUT /api/v1/settings 的响应模型。"""

    run_animation: bool
    workspace: WorkspaceSettingsView


class UiSettingsUpdateRequest(BaseModel):
    """PUT /api/v1/settings 的请求模型；工作区节不可经此修改。"""

    run_animation: bool
