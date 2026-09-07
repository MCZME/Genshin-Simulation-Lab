from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from genshin_sim.assets import AssetValidationError, EffectPayload, WeaponAsset, WeaponLevelStats
from genshin_sim.infrastructure.assets_project_amber._common import (
    _BASE_ATTACK,
    _STAT_MAP,
    _WEAPON_LEVELS,
    _add_props,
    _affix_component_format,
    _affix_component_kind,
    _ascension_phases_for_level,
    _calculate_scaled_prop,
    _calculate_secondary_prop,
    _map_value,
    _parse_affix_value,
    _payload_data,
    _promote_max_levels,
    _prop_configs,
    _read_json,
    _require_mapping,
    _required_str,
    _weapon_secondary_prop,
)

_AFFIX_HIGHLIGHT_PATTERN = re.compile(r"<color=[^>]+>(?P<value>.*?)</color>")
_WEAPON_PASSIVE_HANDLER_KEY = "weapon.unimplemented_passive"


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
            "source_templates": {str(refinement): text for refinement, text in refinements},
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


def _weapon_levels(promote_max_levels: tuple[int, ...]) -> tuple[int, ...]:
    max_level = max(promote_max_levels, default=max(_WEAPON_LEVELS))
    return tuple(range(1, min(max_level, max(_WEAPON_LEVELS)) + 1))
