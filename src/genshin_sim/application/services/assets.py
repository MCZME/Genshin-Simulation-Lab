from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from genshin_sim.assets import (
    ArtifactSetAsset,
    AssetRepository,
    CharacterAsset,
    WeaponAsset,
)

logger = logging.getLogger(__name__)


class AssetListKind(StrEnum):
    """应用服务对外暴露的资产类别。"""

    CHARACTERS = "characters"
    WEAPONS = "weapons"
    ARTIFACT_SETS = "artifact-sets"


@dataclass(frozen=True, slots=True)
class AssetListItem:
    asset_key: str
    name: str


class AssetsService:
    """通过应用层读取资产数据。"""

    def __init__(self, repository: AssetRepository) -> None:
        self.repository = repository

    def get_info(self):
        logger.debug("读取资产数据库信息")
        return self.repository.get_info()

    def list_assets(self, kind: AssetListKind | str) -> tuple[AssetListItem, ...]:
        resolved_kind = AssetListKind(kind)
        logger.debug("列出资产", extra={"asset_kind": resolved_kind.value})
        if resolved_kind is AssetListKind.CHARACTERS:
            items = self.repository.list_characters()
        elif resolved_kind is AssetListKind.WEAPONS:
            items = self.repository.list_weapons()
        else:
            items = self.repository.list_artifact_sets()
        return tuple(AssetListItem(asset_key=item.asset_key, name=item.name) for item in items)

    def inspect_asset(self, asset_key: str) -> CharacterAsset | WeaponAsset | ArtifactSetAsset:
        logger.debug("查看资产", extra={"asset_key": asset_key})
        if asset_key.startswith("character:"):
            return self.repository.get_character(asset_key)
        if asset_key.startswith("weapon:"):
            return self.repository.get_weapon(asset_key)
        if asset_key.startswith("artifact_set:"):
            return self.repository.get_artifact_set(asset_key)
        raise ValueError(f"不支持的 asset_key 类型：{asset_key}")

    def inspect_asset_dict(self, asset_key: str) -> dict[str, Any]:
        item = self.inspect_asset(asset_key)
        return {field: getattr(item, field) for field in item.__dataclass_fields__}


class AssetDatabaseService:
    """资产数据库维护操作的应用层封装。"""

    def __init__(
        self,
        *,
        init_database: Callable[[str | Path], Path],
        build_database: Callable[[str | Path], Path],
        validate_database: Callable[[str | Path], None],
    ) -> None:
        self._init_database = init_database
        self._build_database = build_database
        self._validate_database = validate_database

    def init_database(self, db_path: str | Path) -> Path:
        path = self._init_database(db_path)
        logger.info("资产数据库已初始化", extra={"asset_db": str(path)})
        return path

    def build_database(self, db_path: str | Path) -> Path:
        path = self._build_database(db_path)
        logger.info("资产数据库已构建", extra={"asset_db": str(path)})
        return path

    def validate_database(self, db_path: str | Path) -> None:
        self._validate_database(db_path)
        logger.info("资产数据库校验通过", extra={"asset_db": str(db_path)})
