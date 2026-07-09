from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from genshin_sim.assets import (
    AssetValidationError,
    CharacterAsset,
    CharacterLevelStats,
    WeaponAsset,
    WeaponLevelStats,
)
from genshin_sim.infrastructure.assets_project_amber.fetcher import (
    PROJECT_AMBER_LANGUAGE,
    PROJECT_AMBER_SOURCE_NAME,
    PROJECT_AMBER_SOURCE_VERSION,
)
from genshin_sim.infrastructure.assets_sqlite.schema import ASSET_SCHEMA_VERSION

PROJECT_AMBER_MANIFEST_IMPORTER_VERSION = "project-amber-yatta-manifest-converter-1"

_CHARACTER_LEVELS = (*range(1, 91), 95, 100)
_WEAPON_LEVELS = tuple(range(1, 91))

_ELEMENT_MAP = {
    "Ice": "cryo",
    "Fire": "pyro",
    "Water": "hydro",
    "Wind": "anemo",
    "Electric": "electro",
    "Rock": "geo",
    "Grass": "dendro",
}

_WEAPON_TYPE_MAP = {
    "WEAPON_SWORD_ONE_HAND": "sword",
    "WEAPON_CLAYMORE": "claymore",
    "WEAPON_POLE": "polearm",
    "WEAPON_BOW": "bow",
    "WEAPON_CATALYST": "catalyst",
}

_STAT_MAP = {
    "FIGHT_PROP_CRITICAL": "crit_rate",
    "FIGHT_PROP_CRITICAL_HURT": "crit_damage",
    "FIGHT_PROP_CHARGE_EFFICIENCY": "energy_recharge",
    "FIGHT_PROP_ELEMENT_MASTERY": "elemental_mastery",
    "FIGHT_PROP_HEAL_ADD": "healing_bonus",
    "FIGHT_PROP_ATTACK_PERCENT": "atk_percent",
    "FIGHT_PROP_HP_PERCENT": "hp_percent",
    "FIGHT_PROP_DEFENSE_PERCENT": "def_percent",
    "FIGHT_PROP_WATER_ADD_HURT": "hydro_damage_bonus",
    "FIGHT_PROP_FIRE_ADD_HURT": "pyro_damage_bonus",
    "FIGHT_PROP_ICE_ADD_HURT": "cryo_damage_bonus",
    "FIGHT_PROP_ELEC_ADD_HURT": "electro_damage_bonus",
    "FIGHT_PROP_WIND_ADD_HURT": "anemo_damage_bonus",
    "FIGHT_PROP_ROCK_ADD_HURT": "geo_damage_bonus",
    "FIGHT_PROP_GRASS_ADD_HURT": "dendro_damage_bonus",
    "FIGHT_PROP_PHYSICAL_ADD_HURT": "physical_damage_bonus",
}

_BASE_HP = "FIGHT_PROP_BASE_HP"
_BASE_ATTACK = "FIGHT_PROP_BASE_ATTACK"
_BASE_DEFENSE = "FIGHT_PROP_BASE_DEFENSE"
_BASE_PROPS = frozenset({_BASE_HP, _BASE_ATTACK, _BASE_DEFENSE})


@dataclass(frozen=True, slots=True)
class ProjectAmberManifestBuildSummary:
    output_path: Path
    source_cache_dir: Path
    character_count: int
    character_level_stat_count: int
    weapon_count: int
    weapon_level_stat_count: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class _PropConfig:
    init_value: float
    curve_type: str


def build_asset_manifest_from_project_amber_cache(
    source_cache_dir: str | Path,
    output_path: str | Path,
) -> ProjectAmberManifestBuildSummary:
    cache_dir = Path(source_cache_dir)
    target_path = Path(output_path)

    cache_meta = _load_cache_meta(cache_dir)
    avatar_index = _payload_data(_read_json(cache_dir / "avatar" / "index.json"), "avatar/index")
    weapon_index = _payload_data(_read_json(cache_dir / "weapon" / "index.json"), "weapon/index")
    avatar_curve = _payload_data(
        _read_json(cache_dir / "static" / "avatarCurve.json"),
        "static/avatarCurve",
    )
    weapon_curve = _payload_data(
        _read_json(cache_dir / "static" / "weaponCurve.json"),
        "static/weaponCurve",
    )

    characters = _build_characters(avatar_index)
    character_level_stats = _build_character_level_stats(cache_dir, characters, avatar_curve)
    weapons = _build_weapons(weapon_index)
    weapon_level_stats = _build_weapon_level_stats(cache_dir, weapons, weapon_curve)
    content_hash = str(cache_meta.get("content_hash") or _hash_cache_inputs(cache_dir))

    manifest = {
        "schema_version": 1,
        "kind": "asset_manifest",
        "meta": _build_asset_meta(cache_meta, content_hash),
        "characters": [asdict(item) for item in characters],
        "character_level_stats": [asdict(item) for item in character_level_stats],
        "weapons": [asdict(item) for item in weapons],
        "weapon_level_stats": [asdict(item) for item in weapon_level_stats],
        "artifact_sets": [],
        "artifact_set_bonuses": [],
        "talent_scalings": [],
        "effect_payloads": [],
    }

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return ProjectAmberManifestBuildSummary(
        output_path=target_path,
        source_cache_dir=cache_dir,
        character_count=len(characters),
        character_level_stat_count=len(character_level_stats),
        weapon_count=len(weapons),
        weapon_level_stat_count=len(weapon_level_stats),
        content_hash=content_hash,
    )


def _load_cache_meta(cache_dir: Path) -> Mapping[str, Any]:
    manifest_path = cache_dir / "fetch_manifest.json"
    if not manifest_path.exists():
        return {}
    payload = _read_json(manifest_path)
    if payload.get("kind") != "project_amber_source_cache":
        raise AssetValidationError("fetch_manifest.json 不是 Project Amber raw cache manifest")
    return payload


def _build_asset_meta(cache_meta: Mapping[str, Any], content_hash: str) -> dict[str, str]:
    source_name = str(cache_meta.get("source_name") or PROJECT_AMBER_SOURCE_NAME)
    source_version = str(cache_meta.get("source_version") or PROJECT_AMBER_SOURCE_VERSION)
    language = str(cache_meta.get("language") or PROJECT_AMBER_LANGUAGE)
    fetched_at = cache_meta.get("fetched_at")
    data_version = f"{source_name}:{source_version}:{content_hash[:12]}"

    rows = {
        "schema_version": ASSET_SCHEMA_VERSION,
        "data_version": data_version,
        "importer_version": PROJECT_AMBER_MANIFEST_IMPORTER_VERSION,
        "source_name": source_name,
        "source_version": source_version,
        "source_language": language,
        "content_hash": content_hash,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if fetched_at is not None:
        rows["source_fetched_at"] = str(fetched_at)
    return rows


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


def _build_character_level_stats(
    cache_dir: Path,
    characters: tuple[CharacterAsset, ...],
    avatar_curve_data: Mapping[str, Any],
) -> tuple[CharacterLevelStats, ...]:
    rows: list[CharacterLevelStats] = []
    for character in characters:
        detail_path = cache_dir / "avatar" / f"{character.source_id}.json"
        if not detail_path.exists():
            continue
        detail = _payload_data(_read_json(detail_path), f"avatar/{character.source_id}")
        upgrade = _require_mapping(detail.get("upgrade"), f"avatar/{character.source_id}.upgrade")
        prop_configs = _prop_configs(upgrade, f"avatar/{character.source_id}.upgrade")
        promote_max_levels = _promote_max_levels(
            upgrade,
            f"avatar/{character.source_id}.upgrade",
        )
        promote_max_levels = _extend_last_promote_max_level(
            promote_max_levels,
            max(_CHARACTER_LEVELS),
        )
        special_prop = _optional_str(detail, "specialProp")
        ascension_stat = (
            _map_value(_STAT_MAP, special_prop, f"avatar/{character.source_id}.specialProp")
            if special_prop
            else None
        )

        for level in _CHARACTER_LEVELS:
            for phase in _ascension_phases_for_level(level, promote_max_levels):
                add_props = _add_props(upgrade, phase, f"avatar/{character.source_id}")
                rows.append(
                    CharacterLevelStats(
                        character_key=character.asset_key,
                        level=level,
                        ascension_phase=phase,
                        base_hp=_calculate_scaled_prop(
                            prop_configs,
                            avatar_curve_data,
                            _BASE_HP,
                            level,
                            add_props,
                            f"avatar/{character.source_id}",
                        ),
                        base_atk=_calculate_scaled_prop(
                            prop_configs,
                            avatar_curve_data,
                            _BASE_ATTACK,
                            level,
                            add_props,
                            f"avatar/{character.source_id}",
                        ),
                        base_def=_calculate_scaled_prop(
                            prop_configs,
                            avatar_curve_data,
                            _BASE_DEFENSE,
                            level,
                            add_props,
                            f"avatar/{character.source_id}",
                        ),
                        ascension_stat=ascension_stat,
                        ascension_value=_round_number(add_props.get(special_prop, 0.0))
                        if special_prop
                        else None,
                    )
                )
    return tuple(rows)


def _build_weapon_level_stats(
    cache_dir: Path,
    weapons: tuple[WeaponAsset, ...],
    weapon_curve_data: Mapping[str, Any],
) -> tuple[WeaponLevelStats, ...]:
    rows: list[WeaponLevelStats] = []
    for weapon in weapons:
        detail_path = cache_dir / "weapon" / f"{weapon.source_id}.json"
        if not detail_path.exists():
            continue
        detail = _payload_data(_read_json(detail_path), f"weapon/{weapon.source_id}")
        upgrade = _require_mapping(detail.get("upgrade"), f"weapon/{weapon.source_id}.upgrade")
        prop_configs = _prop_configs(upgrade, f"weapon/{weapon.source_id}.upgrade")
        promote_max_levels = _promote_max_levels(upgrade, f"weapon/{weapon.source_id}.upgrade")
        secondary_prop = _weapon_secondary_prop(prop_configs)
        secondary_stat = (
            _map_value(_STAT_MAP, secondary_prop, f"weapon/{weapon.source_id}.secondary")
            if secondary_prop
            else None
        )

        for level in _weapon_levels(promote_max_levels):
            for phase in _ascension_phases_for_level(level, promote_max_levels):
                add_props = _add_props(upgrade, phase, f"weapon/{weapon.source_id}")
                rows.append(
                    WeaponLevelStats(
                        weapon_key=weapon.asset_key,
                        level=level,
                        ascension_phase=phase,
                        base_atk=_calculate_scaled_prop(
                            prop_configs,
                            weapon_curve_data,
                            _BASE_ATTACK,
                            level,
                            add_props,
                            f"weapon/{weapon.source_id}",
                        ),
                        secondary_stat=secondary_stat,
                        secondary_value=_calculate_secondary_prop(
                            prop_configs,
                            weapon_curve_data,
                            secondary_prop,
                            level,
                            f"weapon/{weapon.source_id}",
                        )
                        if secondary_prop
                        else None,
                    )
                )
    return tuple(rows)


def _weapon_levels(promote_max_levels: tuple[int, ...]) -> tuple[int, ...]:
    max_level = max(promote_max_levels, default=max(_WEAPON_LEVELS))
    return tuple(range(1, min(max_level, max(_WEAPON_LEVELS)) + 1))


def _promote_max_levels(upgrade: Mapping[str, Any], item_path: str) -> tuple[int, ...]:
    promotes = _promotes(upgrade, item_path)
    max_levels: list[int] = []
    for index, promote in enumerate(promotes):
        max_levels.append(_required_int(promote, "unlockMaxLevel", f"{item_path}.promote[{index}]"))
    return tuple(max_levels)


def _extend_last_promote_max_level(
    promote_max_levels: tuple[int, ...],
    max_level: int,
) -> tuple[int, ...]:
    if not promote_max_levels or promote_max_levels[-1] >= max_level:
        return promote_max_levels
    return (*promote_max_levels[:-1], max_level)


def _ascension_phases_for_level(
    level: int,
    promote_max_levels: tuple[int, ...],
) -> tuple[int, ...]:
    phases = tuple(
        phase
        for phase, max_level in enumerate(promote_max_levels)
        if level <= max_level and (phase == 0 or level >= promote_max_levels[phase - 1])
    )
    if not phases:
        raise AssetValidationError(f"等级 {level} 没有对应的突破阶段")
    return phases


def _prop_configs(upgrade: Mapping[str, Any], item_path: str) -> dict[str, _PropConfig]:
    props = upgrade.get("prop")
    if not isinstance(props, list):
        raise AssetValidationError(f"{item_path}.prop 必须是 JSON 数组")
    configs: dict[str, _PropConfig] = {}
    for index, raw in enumerate(props):
        prop = _require_mapping(raw, f"{item_path}.prop[{index}]")
        prop_type = _required_str(prop, "propType", f"{item_path}.prop[{index}]")
        configs[prop_type] = _PropConfig(
            init_value=_required_number(prop, "initValue", f"{item_path}.prop[{index}]"),
            curve_type=_required_str(prop, "type", f"{item_path}.prop[{index}]"),
        )
    return configs


def _weapon_secondary_prop(prop_configs: Mapping[str, _PropConfig]) -> str | None:
    for prop_type in prop_configs:
        if prop_type not in _BASE_PROPS:
            return prop_type
    return None


def _calculate_scaled_prop(
    prop_configs: Mapping[str, _PropConfig],
    curve_data: Mapping[str, Any],
    prop_type: str,
    level: int,
    add_props: Mapping[str, float],
    item_path: str,
) -> float:
    config = prop_configs.get(prop_type)
    if config is None:
        raise AssetValidationError(f"{item_path} 缺少属性配置：{prop_type}")
    coeff = _curve_coeff(curve_data, level, config.curve_type, item_path)
    return _round_number(config.init_value * coeff + float(add_props.get(prop_type, 0.0)))


def _calculate_secondary_prop(
    prop_configs: Mapping[str, _PropConfig],
    curve_data: Mapping[str, Any],
    prop_type: str,
    level: int,
    item_path: str,
) -> float:
    config = prop_configs.get(prop_type)
    if config is None:
        raise AssetValidationError(f"{item_path} 缺少副属性配置：{prop_type}")
    coeff = _curve_coeff(curve_data, level, config.curve_type, item_path)
    return _round_number(config.init_value * coeff)


def _curve_coeff(
    curve_data: Mapping[str, Any],
    level: int,
    curve_type: str,
    item_path: str,
) -> float:
    level_curve = _require_mapping(curve_data.get(str(level)), f"{item_path}.curve[{level}]")
    curve_infos = _require_mapping(level_curve.get("curveInfos"), f"{item_path}.curve[{level}]")
    if curve_type not in curve_infos:
        raise AssetValidationError(f"{item_path}.curve[{level}] 缺少曲线：{curve_type}")
    value = curve_infos[curve_type]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise AssetValidationError(f"{item_path}.curve[{level}].{curve_type} 必须是数字")
    return float(value)


def _add_props(upgrade: Mapping[str, Any], phase: int, item_path: str) -> Mapping[str, float]:
    promotes = _promotes(upgrade, f"{item_path}.upgrade")
    if phase >= len(promotes):
        raise AssetValidationError(f"{item_path}.upgrade.promote 缺少突破阶段：{phase}")
    promote = _require_mapping(promotes[phase], f"{item_path}.upgrade.promote[{phase}]")
    raw_add_props = promote.get("addProps", {})
    add_props = _require_mapping(raw_add_props, f"{item_path}.upgrade.promote[{phase}].addProps")
    return {
        str(key): _number_value(value, f"{item_path}.upgrade.promote[{phase}].addProps.{key}")
        for key, value in add_props.items()
    }


def _promotes(upgrade: Mapping[str, Any], item_path: str) -> list[Any]:
    promotes = upgrade.get("promote")
    if not isinstance(promotes, list):
        raise AssetValidationError(f"{item_path}.promote 必须是 JSON 数组")
    return promotes


def _payload_data(payload: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    response = payload.get("response")
    if response is not None and response != 200:
        raise AssetValidationError(f"{label} 的 response 不是 200：{response!r}")
    data = payload.get("data")
    return _require_mapping(data, f"{label}.data")


def _items_mapping(payload_data: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    return _require_mapping(payload_data.get("items"), f"{label}.items")


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AssetValidationError(f"无法读取 Project Amber cache 文件：{path}") from exc
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AssetValidationError(f"Project Amber cache 文件必须是合法 JSON：{path}") from exc
    return _require_mapping(payload, str(path))


def _require_mapping(value: Any, item_path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssetValidationError(f"{item_path} 必须是 JSON 对象")
    return value


def _required_str(payload: Mapping[str, Any], field_name: str, item_path: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise AssetValidationError(f"{item_path}.{field_name} 必须是非空字符串")
    return value


def _optional_str(payload: Mapping[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise AssetValidationError(f"{field_name} 必须是非空字符串")
    return value


def _required_int(payload: Mapping[str, Any], field_name: str, item_path: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise AssetValidationError(f"{item_path}.{field_name} 必须是整数")
    return value


def _required_number(payload: Mapping[str, Any], field_name: str, item_path: str) -> float:
    return _number_value(payload.get(field_name), f"{item_path}.{field_name}")


def _number_value(value: Any, item_path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise AssetValidationError(f"{item_path} 必须是数字")
    return float(value)


def _map_value(mapping: Mapping[str, str], value: str, item_path: str) -> str:
    mapped = mapping.get(value)
    if mapped is None:
        raise AssetValidationError(f"{item_path} 不支持的取值：{value!r}")
    return mapped


def _round_number(value: float) -> float:
    return round(float(value), 6)


def _hash_cache_inputs(cache_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(cache_dir.rglob("*.json")):
        if path.name == "fetch_manifest.json":
            continue
        digest.update(path.relative_to(cache_dir).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()
