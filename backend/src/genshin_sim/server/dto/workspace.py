"""工作区 HTTP DTO。"""

from __future__ import annotations

from pydantic import BaseModel


class WorkspaceResponse(BaseModel):
    """GET /api/v1/workspace 的响应模型。"""

    data_dir: str
    asset_db_version: str
    initialized: bool
