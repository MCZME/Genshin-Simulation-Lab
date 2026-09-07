"""界面偏好与开发者设置 HTTP DTO。"""

from __future__ import annotations

from pydantic import BaseModel


class WorkspaceSettingsView(BaseModel):
    """配置面板展示的工作区信息；data_dir 为用户自配项，只读展示。"""

    data_dir: str


class DeveloperSettingsView(BaseModel):
    """开发者模式开关；修改写入 config.toml，重启服务后生效。"""

    enabled: bool


class UiSettingsResponse(BaseModel):
    """GET/PUT /api/v1/settings 的响应模型。"""

    run_animation: bool
    developer: DeveloperSettingsView
    workspace: WorkspaceSettingsView


class UiSettingsUpdateRequest(BaseModel):
    """PUT /api/v1/settings 的请求模型；工作区节不可经此修改。

    ``developer_enabled`` 可选：缺省时保持当前开发者模式不变，
    兼容只发送 ``run_animation`` 的既有前端。
    """

    run_animation: bool
    developer_enabled: bool | None = None
