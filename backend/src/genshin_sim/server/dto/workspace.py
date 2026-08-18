"""工作区 HTTP DTO。"""

from __future__ import annotations

from pydantic import BaseModel

WORKSPACE_NAME = "Genshin Simulation Lab"


class WorkspaceResponse(BaseModel):
    """GET /api/v1/workspace 的响应模型。"""

    initialized: bool
    asset_db_version: str
    name: str
