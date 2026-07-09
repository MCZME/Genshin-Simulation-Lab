from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from genshin_sim.assets import ArtifactSetAsset, AssetValidationError, CharacterAsset, WeaponAsset
from genshin_sim.infrastructure.assets_project_amber._common import (
    _ELEMENT_MAP,
    _WEAPON_TYPE_MAP,
    _items_mapping,
    _map_value,
    _optional_str,
    _require_mapping,
    _required_int,
    _required_str,
)


def _build_characters(avatar_index_data: Mapping[str, Any]) -> tuple[CharacterAsset, ...]:
    items = _items_mapping(avatar_index_data, "avatar/index")
    characters: list[CharacterAsset] = []
    for source_id, raw in sorted(items.items()):
        item = _require_mapping(raw, f"avatar.items[{source_id}]")
        if not _has_supported_character_index_fields(item):
            continue
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
