"""资产查询 HTTP 路由。"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Query, Request

from genshin_sim.application import ApplicationFacade, AssetListItem
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.assets import AssetListResponse, AssetResponse

router = APIRouter(
    prefix="/api/v1/assets",
    tags=["assets"],
    dependencies=[Depends(require_initialized)],
)


@router.get("/{asset_type}", response_model=AssetListResponse)
def list_assets(
    asset_type: str,
    request: Request,
    q: str | None = Query(default=None),
    element: str | None = Query(default=None),
    weapon_type: str | None = Query(default=None),
    rarity: int | None = Query(default=None, ge=1, le=5),
    usable: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=0, le=200),
    offset: int = Query(default=0, ge=0),
) -> AssetListResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    items = facade.list_assets(
        asset_type,
        q=q,
        element=element,
        weapon_type=weapon_type,
        rarity=rarity,
        usable=usable,
        limit=limit,
        offset=offset,
    )
    return AssetListResponse(items=[_asset_to_dto(item) for item in items])


@router.get("/{asset_type}/{source_id}", response_model=AssetResponse)
def get_asset(
    asset_type: str,
    source_id: str,
    request: Request,
) -> AssetResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return _asset_to_dto(facade.get_asset(asset_type, source_id))


def _asset_to_dto(item: AssetListItem) -> AssetResponse:
    return AssetResponse(
        asset_key=item.asset_key,
        source_id=item.source_id,
        name=item.name,
        usable=item.usable,
        status=item.status,
        rarity=item.rarity,
        element=item.element,
        weapon_type=item.weapon_type,
    )
