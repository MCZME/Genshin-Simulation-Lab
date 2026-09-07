from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from genshin_sim.assets import (
    AssetValidationError,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
)
from genshin_sim.infrastructure.assets_project_amber._common import (
    _BASE_ATTACK,
    _BASE_DEFENSE,
    _BASE_HP,
    _CHARACTER_LEVELS,
    _STAT_MAP,
    _add_props,
    _ascension_phases_for_level,
    _calculate_scaled_prop,
    _extend_last_promote_max_level,
    _map_value,
    _number_value,
    _numeric_sort_key,
    _optional_non_empty_str,
    _optional_str,
    _payload_data,
    _promote_max_levels,
    _prop_configs,
    _read_json,
    _require_mapping,
    _required_str,
    _round_number,
    _text_number_components,
)

_TALENT_LEVELS = tuple(range(1, 16))
_TALENT_PARAM_PATTERN = re.compile(r"\{param(?P<index>\d+):(?P<format>[^}]+)\}")
_CHARACTER_PASSIVE_HANDLER_KEY = "character.unimplemented_passive"
_CHARACTER_CONSTELLATION_HANDLER_KEY = "character.unimplemented_constellation"
_CHARACTER_SPECIAL_TALENT_HANDLER_KEY = "character.unimplemented_special_talent"


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
        rows.extend(_build_character_special_talent_payloads(character, detail))
        rows.extend(_build_character_passive_payloads(character, detail))
        rows.extend(_build_character_constellation_payloads(character, detail))
    return tuple(rows)


def _build_character_special_talent_payloads(
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
        if "promote" not in talent or _map_core_talent_key(str(source_talent_key), talent):
            continue
        if _is_empty_placeholder_talent(talent):
            continue
        effect_kind = _special_talent_effect_kind(talent)
        rows.append(
            EffectPayload(
                effect_key=f"{character.asset_key}:{effect_kind}:{source_talent_key}",
                owner_type="character",
                owner_key=character.asset_key,
                effect_kind=effect_kind,
                unlock_key=f"talent:{source_talent_key}",
                handler_key=_CHARACTER_SPECIAL_TALENT_HANDLER_KEY,
                params=_character_special_talent_effect_params(
                    source_talent_key=str(source_talent_key),
                    talent=talent,
                    effect_kind=effect_kind,
                    item_path=f"avatar/{character.source_id}.talent[{source_talent_key}]",
                ),
            )
        )
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
                        f"avatar/{character.source_id}.constellation[{source_constellation_key}]"
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


def _character_special_talent_effect_params(
    *,
    source_talent_key: str,
    talent: Mapping[str, Any],
    effect_kind: str,
    item_path: str,
) -> dict[str, Any]:
    description = _optional_non_empty_str(talent, "description")
    return {
        "schema_version": 1,
        "source": "project-amber-yatta",
        "source_talent_key": source_talent_key,
        "source_skill_id": talent.get("skillId"),
        "name": _required_str(talent, "name", item_path),
        "effect_kind": effect_kind,
        "source_template": description or "",
        "components": _text_number_components(description or ""),
        "promote_entries": _special_talent_promote_entries(
            talent,
            item_path=f"{item_path}.promote",
        ),
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


def _special_talent_effect_kind(talent: Mapping[str, Any]) -> str:
    text = _talent_search_text(talent)
    if "替代冲刺" in text:
        return "alternate_sprint"
    if "跳" in text or "燃素" in text:
        return "special_movement"
    return "special_talent"


def _special_talent_promote_entries(
    talent: Mapping[str, Any],
    *,
    item_path: str,
) -> list[dict[str, Any]]:
    raw_promote = talent.get("promote")
    if raw_promote is None:
        return []
    promote = _require_mapping(raw_promote, item_path)
    raw_level = promote.get("1")
    if raw_level is None:
        return []
    level = _require_mapping(raw_level, f"{item_path}[1]")
    raw_description = level.get("description")
    if not isinstance(raw_description, list):
        return []
    entries: list[dict[str, Any]] = []
    for line_index, raw_line in enumerate(raw_description, start=1):
        if raw_line == "":
            continue
        line = _required_description_line(raw_line, f"{item_path}[1].description[{line_index}]")
        param_refs = _talent_param_refs(line)
        label, expression = _split_talent_description_line(line)
        entries.append(
            {
                "source_line_index": line_index,
                "label": label,
                "expression": expression,
                "source_template": line,
                "components": [
                    {
                        "kind": _talent_component_kind(param_format),
                        "source_param": f"param{param_index}",
                        "format": param_format,
                        "values": [
                            _special_talent_promote_param_value(
                                level,
                                param_index,
                                item_path=f"{item_path}[1].params",
                            )
                        ],
                    }
                    for param_index, param_format in param_refs
                ],
            }
        )
    return entries


def _special_talent_promote_param_value(
    promote_level: Mapping[str, Any],
    param_index: int,
    *,
    item_path: str,
) -> float:
    params = promote_level.get("params")
    if not isinstance(params, list):
        raise AssetValidationError(f"{item_path} 必须是 JSON 数组")
    value_index = param_index - 1
    if value_index >= len(params):
        raise AssetValidationError(f"{item_path} 缺少 param{param_index}")
    return _round_number(_number_value(params[value_index], f"{item_path}[{value_index}]"))


def _talent_search_text(talent: Mapping[str, Any]) -> str:
    return " ".join(
        part for part in (talent.get("name"), talent.get("description")) if isinstance(part, str)
    )
