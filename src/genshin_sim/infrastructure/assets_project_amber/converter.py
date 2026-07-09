from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from genshin_sim.assets import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    AssetValidationError,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
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
_TALENT_LEVELS = tuple(range(1, 16))
_TALENT_PARAM_PATTERN = re.compile(r"\{param(?P<index>\d+):(?P<format>[^}]+)\}")
_AFFIX_HIGHLIGHT_PATTERN = re.compile(r"<color=[^>]+>(?P<value>.*?)</color>")
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_AFFIX_NUMBER_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?%?$")
_TEXT_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?%?")
_WEAPON_PASSIVE_HANDLER_KEY = "weapon.unimplemented_passive"
_ARTIFACT_SET_BONUS_HANDLER_KEY = "artifact.unimplemented_set_bonus"
_CHARACTER_PASSIVE_HANDLER_KEY = "character.unimplemented_passive"
_CHARACTER_CONSTELLATION_HANDLER_KEY = "character.unimplemented_constellation"


@dataclass(frozen=True, slots=True)
class ProjectAmberManifestBuildSummary:
    output_path: Path
    source_cache_dir: Path
    character_count: int
    character_level_stat_count: int
    weapon_count: int
    weapon_level_stat_count: int
    artifact_set_count: int
    artifact_set_bonus_count: int
    talent_scaling_count: int
    effect_payload_count: int
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
    reliquary_index = _payload_data(
        _read_json(cache_dir / "reliquary" / "index.json"),
        "reliquary/index",
    )
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
    talent_scalings = _build_talent_scalings(cache_dir, characters)
    weapons = _build_weapons(weapon_index)
    weapon_level_stats = _build_weapon_level_stats(cache_dir, weapons, weapon_curve)
    effect_payloads = (
        *_build_character_effect_payloads(cache_dir, characters),
        *_build_weapon_effect_payloads(cache_dir, weapons),
    )
    artifact_sets = _build_artifact_sets(reliquary_index)
    artifact_set_bonuses = _build_artifact_set_bonuses(reliquary_index, artifact_sets)
    content_hash = str(cache_meta.get("content_hash") or _hash_cache_inputs(cache_dir))

    manifest = {
        "schema_version": 1,
        "kind": "asset_manifest",
        "meta": _build_asset_meta(cache_meta, content_hash),
        "characters": [asdict(item) for item in characters],
        "character_level_stats": [asdict(item) for item in character_level_stats],
        "weapons": [asdict(item) for item in weapons],
        "weapon_level_stats": [asdict(item) for item in weapon_level_stats],
        "artifact_sets": [asdict(item) for item in artifact_sets],
        "artifact_set_bonuses": [asdict(item) for item in artifact_set_bonuses],
        "talent_scalings": [_talent_scaling_to_manifest(item) for item in talent_scalings],
        "effect_payloads": [asdict(item) for item in effect_payloads],
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
        artifact_set_count=len(artifact_sets),
        artifact_set_bonus_count=len(artifact_set_bonuses),
        talent_scaling_count=len(talent_scalings),
        effect_payload_count=len(effect_payloads),
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


def _build_artifact_set_bonuses(
    reliquary_index_data: Mapping[str, Any],
    artifact_sets: tuple[ArtifactSetAsset, ...],
) -> tuple[ArtifactSetBonus, ...]:
    items = _items_mapping(reliquary_index_data, "reliquary/index")
    rows: list[ArtifactSetBonus] = []
    for artifact_set in artifact_sets:
        item = _require_mapping(
            items.get(artifact_set.source_id),
            f"reliquary.items[{artifact_set.source_id}]",
        )
        affixes = _require_mapping(
            item.get("affixList"),
            f"reliquary.items[{artifact_set.source_id}].affixList",
        )
        ordered_affixes = tuple(
            sorted(
                ((str(affix_id), raw_text) for affix_id, raw_text in affixes.items()),
                key=lambda affix: _numeric_sort_key(affix[0]),
            )
        )
        for index, (affix_id, raw_text) in enumerate(ordered_affixes):
            if not isinstance(raw_text, str) or not raw_text:
                raise AssetValidationError(
                    "reliquary.items"
                    f"[{artifact_set.source_id}].affixList[{affix_id}] 必须是非空字符串"
                )
            piece_count = _artifact_piece_count(index, len(ordered_affixes))
            rows.append(
                ArtifactSetBonus(
                    artifact_set_key=artifact_set.asset_key,
                    piece_count=piece_count,
                    handler_key=_ARTIFACT_SET_BONUS_HANDLER_KEY,
                    params=_artifact_set_bonus_params(
                        affix_id=affix_id,
                        piece_count=piece_count,
                        description=raw_text,
                    ),
                )
            )
    return tuple(rows)


def _artifact_piece_count(index: int, affix_count: int) -> int:
    if affix_count == 1:
        return 1
    if index == 0:
        return 2
    if index == 1:
        return 4
    raise AssetValidationError("圣遗物套装效果数量超过当前转换器支持范围")


def _artifact_set_bonus_params(
    *,
    affix_id: str,
    piece_count: int,
    description: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "project-amber-yatta",
        "source_affix_id": affix_id,
        "piece_count": piece_count,
        "source_template": description,
        "components": _text_number_components(description),
    }


def _single_text_number_component(position: int, raw_value: str) -> dict[str, Any]:
    value = _parse_affix_value(raw_value)
    return {
        "kind": _affix_component_kind([value]),
        "source_value": f"number_{position + 1}",
        "format": _affix_component_format([raw_value]),
        "raw_values": [raw_value],
        "values": [value],
    }


def _text_number_values(text: str) -> tuple[str, ...]:
    plain_text = _HTML_TAG_PATTERN.sub("", text)
    return tuple(match.group(0) for match in _TEXT_NUMBER_PATTERN.finditer(plain_text))


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


def _build_talent_scalings(
    cache_dir: Path,
    characters: tuple[CharacterAsset, ...],
) -> tuple[TalentScalingEntry, ...]:
    rows: list[TalentScalingEntry] = []
    for character in characters:
        detail_path = cache_dir / "avatar" / f"{character.source_id}.json"
        if not detail_path.exists():
            continue
        detail = _payload_data(_read_json(detail_path), f"avatar/{character.source_id}")
        talents = _require_mapping(detail.get("talent"), f"avatar/{character.source_id}.talent")
        for source_talent_key, raw_talent in sorted(
            talents.items(),
            key=lambda item: _talent_sort_key(str(item[0])),
        ):
            talent = _require_mapping(
                raw_talent,
                f"avatar/{character.source_id}.talent[{source_talent_key}]",
            )
            talent_key = _map_core_talent_key(str(source_talent_key), talent)
            if talent_key is None:
                continue
            rows.extend(
                _build_talent_scaling_entries(
                    character=character,
                    talent_key=talent_key,
                    source_talent_key=str(source_talent_key),
                    talent=talent,
                    item_path=f"avatar/{character.source_id}.talent[{source_talent_key}]",
                )
            )
    return tuple(rows)


def _talent_scaling_to_manifest(item: TalentScalingEntry) -> dict[str, Any]:
    row = asdict(item)
    row.pop("entry_id", None)
    return row


def _map_core_talent_key(source_talent_key: str, talent: Mapping[str, Any]) -> str | None:
    if source_talent_key == "0":
        return "normal_attack"
    if source_talent_key == "1":
        return "elemental_skill"
    if talent.get("type") == 1 and "promote" in talent:
        return "elemental_burst"
    return None


def _build_talent_scaling_entries(
    *,
    character: CharacterAsset,
    talent_key: str,
    source_talent_key: str,
    talent: Mapping[str, Any],
    item_path: str,
) -> tuple[TalentScalingEntry, ...]:
    promote_by_level = _talent_promote_by_level(talent, item_path)
    level_1 = promote_by_level[1]
    description = level_1.get("description")
    if not isinstance(description, list):
        raise AssetValidationError(f"{item_path}.promote[1].description 必须是 JSON 数组")

    entries: list[TalentScalingEntry] = []
    for line_index, raw_line in enumerate(description, start=1):
        if raw_line == "":
            continue
        line = _required_description_line(raw_line, f"{item_path}.description[{line_index}]")
        param_refs = _talent_param_refs(line)
        if not param_refs:
            continue
        label, expression = _split_talent_description_line(line)
        entries.append(
            TalentScalingEntry(
                character_key=character.asset_key,
                talent_key=talent_key,
                entry_key=_talent_entry_key(line_index, param_refs),
                label=label,
                scaling={
                    "schema_version": 1,
                    "mode": "level_table",
                    "level_min": min(_TALENT_LEVELS),
                    "level_max": max(_TALENT_LEVELS),
                    "source": "project-amber-yatta",
                    "source_talent_key": source_talent_key,
                    "source_skill_id": talent.get("skillId"),
                    "source_line_index": line_index,
                    "source_template": line,
                    "expression": expression,
                    "components": [
                        {
                            "kind": _talent_component_kind(param_format),
                            "source_param": f"param{param_index}",
                            "format": param_format,
                            "values": _talent_param_values(
                                promote_by_level,
                                param_index,
                                item_path,
                            ),
                        }
                        for param_index, param_format in param_refs
                    ],
                },
                tags=_talent_tags(talent_key, param_refs),
            )
        )
    return tuple(entries)


def _talent_promote_by_level(
    talent: Mapping[str, Any],
    item_path: str,
) -> dict[int, Mapping[str, Any]]:
    promote = _require_mapping(talent.get("promote"), f"{item_path}.promote")
    rows: dict[int, Mapping[str, Any]] = {}
    for level in _TALENT_LEVELS:
        raw_level = promote.get(str(level))
        rows[level] = _require_mapping(raw_level, f"{item_path}.promote[{level}]")
    return rows


def _required_description_line(value: Any, item_path: str) -> str:
    if not isinstance(value, str):
        raise AssetValidationError(f"{item_path} 必须是字符串")
    return value


def _talent_param_refs(line: str) -> tuple[tuple[int, str], ...]:
    return tuple(
        (int(match.group("index")), match.group("format"))
        for match in _TALENT_PARAM_PATTERN.finditer(line)
    )


def _split_talent_description_line(line: str) -> tuple[str, str]:
    label, separator, expression = line.partition("|")
    if not separator:
        return line, ""
    return label, expression


def _talent_entry_key(line_index: int, param_refs: tuple[tuple[int, str], ...]) -> str:
    params = "_".join(f"param_{param_index}" for param_index, _format in param_refs)
    return f"line_{line_index:02d}_{params}"


def _talent_component_kind(param_format: str) -> str:
    if param_format.endswith("P"):
        return "plain_ratio"
    return "plain_value"


def _talent_param_values(
    promote_by_level: Mapping[int, Mapping[str, Any]],
    param_index: int,
    item_path: str,
) -> list[float]:
    values: list[float] = []
    for level in _TALENT_LEVELS:
        promote = promote_by_level[level]
        params = promote.get("params")
        if not isinstance(params, list):
            raise AssetValidationError(f"{item_path}.promote[{level}].params 必须是 JSON 数组")
        value_index = param_index - 1
        if value_index >= len(params):
            raise AssetValidationError(
                f"{item_path}.promote[{level}].params 缺少 param{param_index}"
            )
        values.append(
            _round_number(_number_value(params[value_index], f"{item_path}.param{param_index}"))
        )
    return values


def _talent_tags(
    talent_key: str,
    param_refs: tuple[tuple[int, str], ...],
) -> tuple[str, ...]:
    tags = [talent_key]
    if any(param_format.endswith("P") for _param_index, param_format in param_refs):
        tags.append("ratio")
    else:
        tags.append("value")
    return tuple(tags)


def _talent_sort_key(source_talent_key: str) -> tuple[int, str]:
    try:
        return int(source_talent_key), source_talent_key
    except ValueError:
        return 9999, source_talent_key


def _build_character_effect_payloads(
    cache_dir: Path,
    characters: tuple[CharacterAsset, ...],
) -> tuple[EffectPayload, ...]:
    rows: list[EffectPayload] = []
    for character in characters:
        detail_path = cache_dir / "avatar" / f"{character.source_id}.json"
        if not detail_path.exists():
            continue
        detail = _payload_data(_read_json(detail_path), f"avatar/{character.source_id}")
        rows.extend(_build_character_passive_payloads(character, detail))
        rows.extend(_build_character_constellation_payloads(character, detail))
    return tuple(rows)


def _build_character_passive_payloads(
    character: CharacterAsset,
    detail: Mapping[str, Any],
) -> tuple[EffectPayload, ...]:
    raw_talents = detail.get("talent")
    if raw_talents is None:
        return ()
    talents = _require_mapping(raw_talents, f"avatar/{character.source_id}.talent")
    rows: list[EffectPayload] = []
    for source_talent_key, raw_talent in sorted(
        talents.items(),
        key=lambda item: _talent_sort_key(str(item[0])),
    ):
        talent = _require_mapping(
            raw_talent,
            f"avatar/{character.source_id}.talent[{source_talent_key}]",
        )
        if talent.get("type") != 2 or "promote" in talent:
            continue
        if _is_empty_placeholder_talent(talent):
            continue
        passive_kind = (
            "passive_exploration"
            if _is_exploration_passive(str(source_talent_key), talent)
            else "passive"
        )
        rows.append(
            EffectPayload(
                effect_key=f"{character.asset_key}:{passive_kind}:{source_talent_key}",
                owner_type="character",
                owner_key=character.asset_key,
                effect_kind=passive_kind,
                unlock_key=f"passive:{source_talent_key}",
                handler_key=_CHARACTER_PASSIVE_HANDLER_KEY,
                params=_character_talent_effect_params(
                    source_talent_key=str(source_talent_key),
                    talent=talent,
                    effect_kind=passive_kind,
                    item_path=f"avatar/{character.source_id}.talent[{source_talent_key}]",
                ),
            )
        )
    return tuple(rows)


def _build_character_constellation_payloads(
    character: CharacterAsset,
    detail: Mapping[str, Any],
) -> tuple[EffectPayload, ...]:
    raw_constellations = detail.get("constellation")
    if raw_constellations is None:
        return ()
    constellations = _require_mapping(
        raw_constellations,
        f"avatar/{character.source_id}.constellation",
    )
    rows: list[EffectPayload] = []
    for source_constellation_key, raw_constellation in sorted(
        constellations.items(),
        key=lambda item: _numeric_sort_key(str(item[0])),
    ):
        constellation = _require_mapping(
            raw_constellation,
            f"avatar/{character.source_id}.constellation[{source_constellation_key}]",
        )
        unlock_key = _constellation_unlock_key(str(source_constellation_key))
        rows.append(
            EffectPayload(
                effect_key=f"{character.asset_key}:constellation:{unlock_key}",
                owner_type="character",
                owner_key=character.asset_key,
                effect_kind="constellation",
                unlock_key=unlock_key,
                handler_key=_CHARACTER_CONSTELLATION_HANDLER_KEY,
                params=_character_constellation_effect_params(
                    source_constellation_key=str(source_constellation_key),
                    constellation=constellation,
                    unlock_key=unlock_key,
                    item_path=(
                        f"avatar/{character.source_id}"
                        f".constellation[{source_constellation_key}]"
                    ),
                ),
            )
        )
    return tuple(rows)


def _character_talent_effect_params(
    *,
    source_talent_key: str,
    talent: Mapping[str, Any],
    effect_kind: str,
    item_path: str,
) -> dict[str, Any]:
    description = _required_str(talent, "description", item_path)
    return {
        "schema_version": 1,
        "source": "project-amber-yatta",
        "source_talent_key": source_talent_key,
        "source_skill_id": talent.get("skillId"),
        "name": _required_str(talent, "name", item_path),
        "effect_kind": effect_kind,
        "source_template": description,
        "components": _text_number_components(description),
    }


def _character_constellation_effect_params(
    *,
    source_constellation_key: str,
    constellation: Mapping[str, Any],
    unlock_key: str,
    item_path: str,
) -> dict[str, Any]:
    description = _required_str(constellation, "description", item_path)
    return {
        "schema_version": 1,
        "source": "project-amber-yatta",
        "source_constellation_key": source_constellation_key,
        "source_talent_id": constellation.get("talentId"),
        "unlock_key": unlock_key,
        "name": _required_str(constellation, "name", item_path),
        "source_template": description,
        "components": _text_number_components(description),
    }


def _text_number_components(text: str) -> list[dict[str, Any]]:
    return [
        _single_text_number_component(position, raw_value)
        for position, raw_value in enumerate(_text_number_values(text))
    ]


def _constellation_unlock_key(source_constellation_key: str) -> str:
    try:
        level = int(source_constellation_key) + 1
    except ValueError as exc:
        raise AssetValidationError(f"命座键必须是整数：{source_constellation_key!r}") from exc
    if level < 1:
        raise AssetValidationError(f"命座键不能小于 0：{source_constellation_key!r}")
    return f"c{level}"


def _is_exploration_passive(source_talent_key: str, talent: Mapping[str, Any]) -> bool:
    if source_talent_key == "9":
        return True
    name = talent.get("name")
    description = talent.get("description")
    text = " ".join(part for part in (name, description) if isinstance(part, str))
    exploration_markers = (
        "小地图",
        "探索派遣",
        "合成",
        "锻造",
        "烹饪",
        "游泳",
        "滑翔",
        "冲刺",
        "采集",
        "异色原海异种",
    )
    return any(marker in text for marker in exploration_markers)


def _is_empty_placeholder_talent(talent: Mapping[str, Any]) -> bool:
    return not talent.get("name") and not talent.get("description")


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


def _build_weapon_effect_payloads(
    cache_dir: Path,
    weapons: tuple[WeaponAsset, ...],
) -> tuple[EffectPayload, ...]:
    rows: list[EffectPayload] = []
    for weapon in weapons:
        detail_path = cache_dir / "weapon" / f"{weapon.source_id}.json"
        if not detail_path.exists():
            continue
        detail = _payload_data(_read_json(detail_path), f"weapon/{weapon.source_id}")
        raw_affixes = detail.get("affix")
        if raw_affixes is None:
            continue
        affixes = _require_mapping(raw_affixes, f"weapon/{weapon.source_id}.affix")
        for affix_id, raw_affix in sorted(affixes.items()):
            affix = _require_mapping(raw_affix, f"weapon/{weapon.source_id}.affix[{affix_id}]")
            rows.append(
                _build_weapon_effect_payload(
                    weapon=weapon,
                    affix_id=str(affix_id),
                    affix=affix,
                    item_path=f"weapon/{weapon.source_id}.affix[{affix_id}]",
                )
            )
    return tuple(rows)


def _build_weapon_effect_payload(
    *,
    weapon: WeaponAsset,
    affix_id: str,
    affix: Mapping[str, Any],
    item_path: str,
) -> EffectPayload:
    affix_name = _required_str(affix, "name", item_path)
    upgrade = _require_mapping(affix.get("upgrade"), f"{item_path}.upgrade")
    refinements = _weapon_affix_refinements(upgrade, item_path)
    highlighted_values = [_affix_highlight_values(text) for _refinement, text in refinements]
    highlight_count = len(highlighted_values[0]) if highlighted_values else 0
    if any(len(values) != highlight_count for values in highlighted_values):
        raise AssetValidationError(f"{item_path}.upgrade 高亮参数数量必须在所有精炼等级中一致")

    return EffectPayload(
        effect_key=f"{weapon.asset_key}:passive:{affix_id}",
        owner_type="weapon",
        owner_key=weapon.asset_key,
        effect_kind="passive",
        handler_key=_WEAPON_PASSIVE_HANDLER_KEY,
        params={
            "schema_version": 1,
            "source": "project-amber-yatta",
            "source_affix_id": affix_id,
            "name": affix_name,
            "refinement_min": refinements[0][0],
            "refinement_max": refinements[-1][0],
            "source_templates": {
                str(refinement): text for refinement, text in refinements
            },
            "components": [
                _weapon_affix_component(position, highlighted_values)
                for position in range(highlight_count)
            ],
        },
    )


def _weapon_affix_refinements(
    upgrade: Mapping[str, Any],
    item_path: str,
) -> tuple[tuple[int, str], ...]:
    raw_levels: list[tuple[int, str]] = []
    for raw_refinement, raw_text in upgrade.items():
        try:
            refinement = int(str(raw_refinement)) + 1
        except ValueError as exc:
            raise AssetValidationError(
                f"{item_path}.upgrade 精炼等级必须是整数键：{raw_refinement!r}"
            ) from exc
        if not isinstance(raw_text, str) or not raw_text:
            raise AssetValidationError(f"{item_path}.upgrade[{raw_refinement}] 必须是非空字符串")
        raw_levels.append((refinement, raw_text))

    refinements = tuple(sorted(raw_levels))
    if not refinements:
        raise AssetValidationError(f"{item_path}.upgrade 至少需要一个精炼等级")
    expected = tuple(range(refinements[0][0], refinements[-1][0] + 1))
    actual = tuple(refinement for refinement, _text in refinements)
    if actual != expected:
        raise AssetValidationError(f"{item_path}.upgrade 精炼等级必须连续")
    return refinements


def _affix_highlight_values(text: str) -> tuple[str, ...]:
    return tuple(match.group("value") for match in _AFFIX_HIGHLIGHT_PATTERN.finditer(text))


def _weapon_affix_component(
    position: int,
    highlighted_values: list[tuple[str, ...]],
) -> dict[str, object]:
    raw_values = [values[position] for values in highlighted_values]
    values = [_parse_affix_value(value) for value in raw_values]
    return {
        "kind": _affix_component_kind(values),
        "source_value": f"highlight_{position + 1}",
        "format": _affix_component_format(raw_values),
        "raw_values": raw_values,
        "values": values,
    }


def _parse_affix_value(value: str) -> float | list[float] | str:
    if "/" in value:
        parts = value.split("/")
        parsed = [_parse_affix_scalar(part, percent_hint="%" in value) for part in parts]
        if all(isinstance(item, float) for item in parsed):
            return [float(item) for item in parsed]
        return value
    parsed = _parse_affix_scalar(value, percent_hint=False)
    if isinstance(parsed, float):
        return parsed
    return value


def _parse_affix_scalar(value: str, *, percent_hint: bool) -> float | str:
    stripped = value.strip()
    if not _AFFIX_NUMBER_PATTERN.fullmatch(stripped):
        return value
    is_percent = percent_hint or stripped.endswith("%")
    number_text = stripped[:-1] if stripped.endswith("%") else stripped
    number = float(number_text)
    return _round_number(number / 100.0 if is_percent else number)


def _affix_component_kind(values: list[float | list[float] | str]) -> str:
    if all(isinstance(value, float) for value in values):
        return "numeric"
    if all(isinstance(value, list) for value in values):
        return "numeric_list"
    if all(isinstance(value, str) for value in values):
        return "text"
    return "mixed"


def _affix_component_format(values: list[str]) -> str:
    if all("/" in value and "%" in value for value in values):
        return "percent_list"
    if all("/" in value for value in values):
        return "number_list"
    if all("%" in value for value in values):
        return "percent"
    if all(_AFFIX_NUMBER_PATTERN.fullmatch(value.strip()) for value in values):
        return "number"
    return "text"


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


def _numeric_sort_key(value: str) -> tuple[int, str]:
    try:
        return int(value), value
    except ValueError:
        return 9999, value


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
