from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from genshin_sim.application.models import AssetListItem, AssetListKind
from genshin_sim.application.services.errors import ApplicationServiceError
from genshin_sim.assets import (
    ArtifactSetAsset,
    AssetHandlerBindingRepository,
    AssetRepository,
    CharacterAsset,
    HandlerBinding,
    WeaponAsset,
)
from genshin_sim.content.registries import ContentUnitRegistry, HandlerImplementationStatus

logger = logging.getLogger(__name__)


class HandlerBindingKind(StrEnum):
    """资产 handler_key 绑定类别。"""

    CHARACTER = "character"
    WEAPON = "weapon"
    ARTIFACT_SET = "artifact-set"
    ARTIFACT_BONUS = "artifact-bonus"
    EFFECT = "effect"


class AssetsService:
    """通过应用层读取资产数据。"""

    def __init__(
        self,
        repository: AssetRepository,
        *,
        content_unit_registry: ContentUnitRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.content_unit_registry = content_unit_registry

    def get_info(self):
        logger.debug("读取资产数据库信息")
        return self.repository.get_info()

    def list_assets(
        self,
        kind: AssetListKind | str,
        *,
        q: str | None = None,
        element: str | None = None,
        weapon_type: str | None = None,
        rarity: int | None = None,
        usable: bool | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[AssetListItem, ...]:
        resolved_kind = AssetListKind(kind)
        logger.debug("列出资产", extra={"asset_kind": resolved_kind.value})
        if resolved_kind is AssetListKind.CHARACTERS:
            items = self.repository.list_characters()
        elif resolved_kind is AssetListKind.WEAPONS:
            items = self.repository.list_weapons()
        else:
            items = self.repository.list_artifact_sets()
        query = (q or "").strip().casefold()
        if query:
            items = tuple(
                item
                for item in items
                if query in item.name.casefold() or query in item.source_id.casefold()
            )
        listed = tuple(self._to_list_item(item, resolved_kind) for item in items)
        if element is not None:
            listed = tuple(item for item in listed if item.element == element)
        if weapon_type is not None:
            listed = tuple(item for item in listed if item.weapon_type == weapon_type)
        if rarity is not None:
            listed = tuple(item for item in listed if item.rarity == rarity)
        if usable is not None:
            listed = tuple(item for item in listed if item.usable == usable)
        if offset or limit is not None:
            if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                raise ValueError("offset 必须是非负整数")
            if limit is not None and (
                isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
            ):
                raise ValueError("limit 必须是非负整数")
            start = offset
            end = None if limit is None else start + limit
            listed = listed[start:end]
        return listed

    def get_asset(self, kind: AssetListKind | str, source_id: str) -> AssetListItem:
        """按资产类型与 source_id 返回单个展示项。"""

        resolved_kind = AssetListKind(kind)
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("source_id 不能为空")
        prefix = {
            AssetListKind.CHARACTERS: "character",
            AssetListKind.WEAPONS: "weapon",
            AssetListKind.ARTIFACT_SETS: "artifact_set",
        }[resolved_kind]
        asset = self._get_asset(resolved_kind, f"{prefix}:{source_id}")
        return self._to_list_item(asset, resolved_kind)

    def resolve_assets(self, keys: Sequence[str]) -> tuple[AssetListItem, ...]:
        """按完整 asset_key 批量解析展示项；未知或缺失的键静默跳过。"""

        items: list[AssetListItem] = []
        for key in dict.fromkeys(keys):
            try:
                asset = self.inspect_asset(key)
            except (KeyError, LookupError, ValueError):
                continue
            items.append(self._to_list_item(asset, _asset_list_kind(key)))
        return tuple(items)

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

    def _get_asset(
        self,
        kind: AssetListKind,
        asset_key: str,
    ) -> CharacterAsset | WeaponAsset | ArtifactSetAsset:
        if kind is AssetListKind.CHARACTERS:
            return self.repository.get_character(asset_key)
        if kind is AssetListKind.WEAPONS:
            return self.repository.get_weapon(asset_key)
        return self.repository.get_artifact_set(asset_key)

    def _to_list_item(
        self,
        asset: CharacterAsset | WeaponAsset | ArtifactSetAsset,
        kind: AssetListKind,
    ) -> AssetListItem:
        usable, status = self._availability(asset, kind)
        if isinstance(asset, CharacterAsset):
            rarity: int | None = asset.rarity
            element: str | None = asset.element
            weapon_type: str | None = asset.weapon_type
        elif isinstance(asset, WeaponAsset):
            rarity = asset.rarity
            element = None
            weapon_type = asset.weapon_type
        else:
            rarity = None
            element = None
            weapon_type = None
        return AssetListItem(
            asset_key=asset.asset_key,
            source_id=asset.source_id,
            name=asset.name,
            usable=usable,
            status=status,
            rarity=rarity,
            element=element,
            weapon_type=weapon_type,
        )

    def _availability(
        self,
        asset: CharacterAsset | WeaponAsset | ArtifactSetAsset,
        kind: AssetListKind,
    ) -> tuple[bool, str | None]:
        registry = self.content_unit_registry

        if kind is AssetListKind.CHARACTERS:
            if asset.handler_key is None:
                return False, "角色实现未接入"
            if registry is None:
                return False, "缺少内容注册表，无法确认可运行性"
            if not registry.has_character_handler(asset.handler_key):
                return False, "角色实现不可用"
        elif kind is AssetListKind.WEAPONS:
            if asset.handler_key is None:
                return False, "武器实现未接入"
            if registry is None:
                return False, "缺少内容注册表，无法确认可运行性"
            if not registry.has_weapon_handler(asset.handler_key):
                return False, "武器实现不可用"
        else:
            if registry is None:
                return False, "缺少内容注册表，无法确认可运行性"
            if asset.handler_key is not None and not registry.has_artifact_handler(
                asset.handler_key
            ):
                return False, "套装实现不可用"

        if not self._effects_available(asset.asset_key, registry):
            return False, "效果实现不可用"
        if kind is AssetListKind.ARTIFACT_SETS:
            try:
                bonuses = self.repository.get_artifact_set_bonuses(asset.asset_key)
            except Exception:
                return False, "套装效果数据不可用"
            if not all(
                registry.handler_status(bonus.handler_key)
                is HandlerImplementationStatus.IMPLEMENTED
                for bonus in bonuses
            ):
                return False, "套装效果实现不可用"
        return True, None

    def _effects_available(self, owner_key: str, registry: ContentUnitRegistry) -> bool:
        try:
            effects = self.repository.get_effect_payloads(owner_key)
        except Exception:
            return False
        return all(registry.has_effect_handler(effect.handler_key) for effect in effects)


def _asset_list_kind(key: str) -> AssetListKind:
    """按 asset_key 前缀映射资产列表类别。"""

    if key.startswith("character:"):
        return AssetListKind.CHARACTERS
    if key.startswith("weapon:"):
        return AssetListKind.WEAPONS
    if key.startswith("artifact_set:"):
        return AssetListKind.ARTIFACT_SETS
    raise ValueError(f"不支持的 asset_key 类型：{key}")


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


_EFFECT_PLACEHOLDER_BY_EFFECT_KIND: dict[str, str] = {
    "passive": "character.unimplemented_passive",
    "passive_exploration": "character.unimplemented_passive",
    "constellation": "character.unimplemented_constellation",
    "alternate_sprint": "character.unimplemented_special_talent",
    "special_movement": "character.unimplemented_special_talent",
    "special_talent": "character.unimplemented_special_talent",
}

ManifestHandlerValidator = Callable[[str | Path, HandlerBinding], None]
ManifestHandlerUpdater = Callable[[str | Path, HandlerBinding], Path]
ManifestHandlerSyncer = Callable[[str | Path, Sequence[HandlerBinding]], Path]


class AssetHandlerBindingService:
    """维护资产 handler_key 绑定（设置、重置、查看）。"""

    def __init__(
        self,
        *,
        repository: AssetHandlerBindingRepository,
        content_unit_registry: ContentUnitRegistry,
        manifest_validator: ManifestHandlerValidator | None = None,
        manifest_updater: ManifestHandlerUpdater | None = None,
        manifest_syncer: ManifestHandlerSyncer | None = None,
    ) -> None:
        self.repository = repository
        self.content_unit_registry = content_unit_registry
        self.manifest_validator = manifest_validator
        self.manifest_updater = manifest_updater
        self.manifest_syncer = manifest_syncer

    def set_handler(
        self,
        kind: HandlerBindingKind | str,
        key: str,
        handler_key: str,
        pieces: int | None = None,
        *,
        manifest_paths: Sequence[str | Path] = (),
    ) -> HandlerBinding:
        resolved_kind = HandlerBindingKind(kind)
        normalized = handler_key.strip()
        if not normalized:
            raise ApplicationServiceError("handler_key 不能为空")
        binding = self.repository.get_handler_binding(resolved_kind.value, key, pieces)
        self._require_registered(resolved_kind, normalized)
        final_binding = replace(binding, handler_key=normalized)
        self._validate_manifest_bindings(manifest_paths, final_binding)
        if binding.handler_key != normalized:
            self.repository.set_handler_binding(
                resolved_kind.value,
                key,
                normalized,
                pieces,
            )
        self._apply_manifest_bindings(manifest_paths, final_binding)
        return final_binding

    def reset_handler(
        self,
        kind: HandlerBindingKind | str,
        key: str,
        pieces: int | None = None,
        *,
        manifest_paths: Sequence[str | Path] = (),
    ) -> HandlerBinding:
        resolved_kind = HandlerBindingKind(kind)
        binding = self.repository.get_handler_binding(resolved_kind.value, key, pieces)
        target = self._reset_target(resolved_kind, binding)
        final_binding = replace(binding, handler_key=target)
        self._validate_manifest_bindings(manifest_paths, final_binding)
        self.repository.set_handler_binding(resolved_kind.value, key, target, pieces)
        self._apply_manifest_bindings(manifest_paths, final_binding)
        return final_binding

    def show_handlers(
        self,
        kind: HandlerBindingKind | str,
        owner_key: str | None = None,
    ) -> tuple[HandlerBinding, ...]:
        resolved_kind = HandlerBindingKind(kind)
        return self.repository.list_handler_bindings(resolved_kind.value, owner_key)

    def sync_handlers_to_manifests(
        self,
        manifest_paths: Sequence[str | Path],
        kind: HandlerBindingKind | str | None = None,
    ) -> dict[str, int]:
        if self.manifest_syncer is None:
            raise ApplicationServiceError("未配置 manifest 同步器")
        kinds = (HandlerBindingKind(kind),) if kind is not None else tuple(HandlerBindingKind)
        bindings = tuple(
            binding
            for resolved_kind in kinds
            for binding in self.repository.list_handler_bindings(resolved_kind.value)
        )
        result: dict[str, int] = {}
        for manifest_path in manifest_paths:
            self.manifest_syncer(manifest_path, bindings)
            result[str(manifest_path)] = len(bindings)
        return result

    def _require_registered(self, kind: HandlerBindingKind, handler_key: str) -> None:
        if kind is HandlerBindingKind.CHARACTER:
            registered = self.content_unit_registry.has_character_handler(handler_key)
        elif kind is HandlerBindingKind.WEAPON:
            registered = self.content_unit_registry.has_weapon_handler(handler_key)
        elif kind in (HandlerBindingKind.ARTIFACT_SET, HandlerBindingKind.ARTIFACT_BONUS):
            registered = self.content_unit_registry.has_artifact_handler(handler_key)
        else:
            registered = self.content_unit_registry.has_effect_handler(handler_key)
        if not registered:
            raise ApplicationServiceError(f"handler 未注册：{handler_key}")

    @staticmethod
    def _reset_target(
        kind: HandlerBindingKind,
        binding: HandlerBinding,
    ) -> str | None:
        if kind in (
            HandlerBindingKind.CHARACTER,
            HandlerBindingKind.WEAPON,
            HandlerBindingKind.ARTIFACT_SET,
        ):
            return None
        if kind is HandlerBindingKind.ARTIFACT_BONUS:
            return "artifact.unimplemented_set_bonus"
        placeholder = _EFFECT_PLACEHOLDER_BY_EFFECT_KIND.get(binding.effect_kind or "")
        if placeholder is None:
            raise ApplicationServiceError(f"不支持重置效果种类：{binding.effect_kind}")
        return placeholder

    def _validate_manifest_bindings(
        self,
        manifest_paths: Sequence[str | Path],
        binding: HandlerBinding,
    ) -> None:
        if not manifest_paths:
            return
        if self.manifest_validator is None or self.manifest_updater is None:
            raise ApplicationServiceError("未配置 manifest 写回器")
        for manifest_path in manifest_paths:
            self.manifest_validator(manifest_path, binding)

    def _apply_manifest_bindings(
        self,
        manifest_paths: Sequence[str | Path],
        binding: HandlerBinding,
    ) -> None:
        if not manifest_paths:
            return
        if self.manifest_updater is None:
            raise ApplicationServiceError("未配置 manifest 写回器")
        for manifest_path in manifest_paths:
            self.manifest_updater(manifest_path, binding)


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
