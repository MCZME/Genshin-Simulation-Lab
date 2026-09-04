from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from genshin_sim.assets import ArtifactSetAsset, AssetValidationError, CharacterAsset, WeaponAsset
from genshin_sim.infrastructure.assets_project_amber._common import (
    _ELEMENT_MAP,
    _WEAPON_TYPE_MAP,
    _items_mapping,
    _map_value,
    _optional_str,
    _payload_data,
    _read_json,
    _require_mapping,
    _required_int,
    _required_str,
)


def _build_characters(
    cache_dir: Path,
    avatar_index_data: Mapping[str, Any],
) -> tuple[CharacterAsset, ...]:
    items = _items_mapping(avatar_index_data, "avatar/index")
    characters: list[CharacterAsset] = []
    for source_id, raw in sorted(items.items()):
        item = _require_mapping(raw, f"avatar.items[{source_id}]")
        if not _has_supported_character_index_fields(item):
            continue
        detail_path = cache_dir / "avatar" / f"{source_id}.json"
        detail = _payload_data(_read_json(detail_path), f"avatar/{source_id}")
        talents = _require_mapping(detail.get("talent"), f"avatar/{source_id}.talent")
        costs = []
        for talent_key, raw_talent in talents.items():
            talent = _require_mapping(raw_talent, f"avatar/{source_id}.talent[{talent_key}]")
            if talent.get("type") != 1:
                continue
            cost = talent.get("cost")
            if isinstance(cost, bool) or not isinstance(cost, int | float):
                raise AssetValidationError(
                    f"avatar/{source_id}.talent[{talent_key}].cost 必须是数值"
                )
            costs.append(float(cost))
        if len(costs) != 1:
            raise AssetValidationError(
                f"avatar/{source_id} 必须恰好有一个 type == 1 的元素爆发天赋"
            )
        characters.append(
            CharacterAsset(
                asset_key=f"character:{source_id}",
                source_id=source_id,
                name=_required_str(item, "name", f"avatar.items[{source_id}]"),
                element=_map_value(
                    _ELEMENT_MAP,
                    _required_str(item, "element", f"avatar.items[{source_id}]"),
                    f"avatar.items[{source_id}].element",
                ),
                weapon_type=_map_value(
                    _WEAPON_TYPE_MAP,
                    _required_str(item, "weaponType", f"avatar.items[{source_id}]"),
                    f"avatar.items[{source_id}].weaponType",
                ),
                rarity=_required_int(item, "rank", f"avatar.items[{source_id}]"),
                burst_energy_cost=costs[0],
            )
        )
    return tuple(characters)


def _has_supported_character_index_fields(item: Mapping[str, Any]) -> bool:
    name = item.get("name")
    element = item.get("element")
    weapon_type = item.get("weaponType")
    rank = item.get("rank")
    return (
        isinstance(name, str)
        and bool(name)
        and isinstance(element, str)
        and element in _ELEMENT_MAP
        and isinstance(weapon_type, str)
        and weapon_type in _WEAPON_TYPE_MAP
        and isinstance(rank, int)
        and not isinstance(rank, bool)
    )


def _build_weapons(weapon_index_data: Mapping[str, Any]) -> tuple[WeaponAsset, ...]:
    items = _items_mapping(weapon_index_data, "weapon/index")
    weapons: list[WeaponAsset] = []
    for source_id, raw in sorted(items.items()):
        item = _require_mapping(raw, f"weapon.items[{source_id}]")
        item_path = f"weapon.items[{source_id}]"
        if item.get("isWeaponSkin") is True:
            continue
        weapon_type = _optional_str(item, "type") or _optional_str(item, "weaponType")
        if weapon_type is None:
            raise AssetValidationError(f"{item_path}.type 是必填字段")
        weapons.append(
            WeaponAsset(
                asset_key=f"weapon:{source_id}",
                source_id=source_id,
                name=_required_str(item, "name", item_path),
                weapon_type=_map_value(_WEAPON_TYPE_MAP, weapon_type, f"{item_path}.type"),
                rarity=_required_int(item, "rank", item_path),
            )
        )
    return tuple(weapons)


def _build_artifact_sets(reliquary_index_data: Mapping[str, Any]) -> tuple[ArtifactSetAsset, ...]:
    items = _items_mapping(reliquary_index_data, "reliquary/index")
    artifact_sets: list[ArtifactSetAsset] = []
    for source_id, raw in sorted(items.items()):
        item = _require_mapping(raw, f"reliquary.items[{source_id}]")
        artifact_sets.append(
            ArtifactSetAsset(
                asset_key=f"artifact_set:{source_id}",
                source_id=source_id,
                name=_required_str(item, "name", f"reliquary.items[{source_id}]"),
            )
        )
    return tuple(artifact_sets)
