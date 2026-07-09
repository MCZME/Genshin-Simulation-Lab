from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from genshin_sim.assets import AssetValidationError

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
_AFFIX_NUMBER_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?%?$")
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_TEXT_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?%?")


@dataclass(frozen=True, slots=True)
class _PropConfig:
    init_value: float
    curve_type: str


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


def _optional_non_empty_str(payload: Mapping[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise AssetValidationError(f"{field_name} 必须是字符串")
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


def _text_number_components(text: str) -> list[dict[str, Any]]:
    return [
        _single_text_number_component(position, raw_value)
        for position, raw_value in enumerate(_text_number_values(text))
    ]


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
