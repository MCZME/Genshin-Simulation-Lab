"""资产查询 HTTP DTO。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AssetResponse(BaseModel):
    """资产列表项/详情；不返回 handler_key 或内部 payload。"""

    asset_key: str
    source_id: str
    name: str
    usable: bool
    status: str | None = None
    rarity: int | None = None
    element: str | None = None
    weapon_type: str | None = None


class AssetListResponse(BaseModel):
    """按类型搜索/列表响应。"""

    items: list[AssetResponse] = Field(default_factory=list)
