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


class AssetSourceCacheService:
    """开发期资产源 raw cache 抓取操作。"""

    def __init__(self, *, fetch_source_cache: Callable[[str | Path], Any]) -> None:
        self._fetch_source_cache = fetch_source_cache

    def fetch_source_cache(self, output_dir: str | Path) -> Any:
        summary = self._fetch_source_cache(output_dir)
        logger.info("资产源 raw cache 已抓取", extra={"output_dir": str(output_dir)})
        return summary


class AssetManifestBuildService:
    """开发期资产 manifest 构建操作。"""

    def __init__(
        self,
        *,
        build_manifest: Callable[[str | Path, str | Path], Any],
    ) -> None:
        self._build_manifest = build_manifest

    def build_manifest(self, source_cache_dir: str | Path, output_path: str | Path) -> Any:
        summary = self._build_manifest(source_cache_dir, output_path)
        logger.info(
            "资产 manifest 已构建",
            extra={"source_cache_dir": str(source_cache_dir), "output_path": str(output_path)},
        )
        return summary


class AssetManifestAuditService:
    """开发期资产 manifest 验收操作。"""

    def __init__(self, *, audit_manifest: Callable[[str | Path], Any]) -> None:
        self._audit_manifest = audit_manifest

    def audit_manifest(self, manifest_path: str | Path) -> Any:
        report = self._audit_manifest(manifest_path)
        logger.info(
            "资产 manifest 验收完成",
            extra={"manifest_path": str(manifest_path), "issue_count": report.issue_count},
        )
        return report
