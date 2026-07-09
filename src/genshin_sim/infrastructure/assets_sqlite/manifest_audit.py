from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from genshin_sim.infrastructure.assets_sqlite.manifest import (
    AssetManifest,
    load_asset_manifest,
)

_CHARACTER_LEVELS = (*range(1, 91), 95, 100)
_WEAPON_LEVELS = tuple(range(1, 91))
_CHARACTER_PROMOTE_MAX_LEVELS = (20, 40, 50, 60, 70, 80, 100)
_LOW_RARITY_WEAPON_PROMOTE_MAX_LEVELS = (20, 40, 50, 60, 70)
_STANDARD_WEAPON_PROMOTE_MAX_LEVELS = (20, 40, 50, 60, 70, 80, 90)

_ALLOWED_ELEMENTS = frozenset({"anemo", "cryo", "dendro", "electro", "geo", "hydro", "pyro"})
_ALLOWED_WEAPON_TYPES = frozenset({"bow", "catalyst", "claymore", "polearm", "sword"})
_ALLOWED_CHARACTER_RARITIES = frozenset({4, 5})
_ALLOWED_WEAPON_RARITIES = frozenset({1, 2, 3, 4, 5})
_ALLOWED_STATS = frozenset(
    {
        "atk_percent",
        "crit_damage",
        "crit_rate",
        "cryo_damage_bonus",
        "def_percent",
        "dendro_damage_bonus",
        "electro_damage_bonus",
        "elemental_mastery",
        "energy_recharge",
        "geo_damage_bonus",
        "healing_bonus",
        "hp_percent",
        "hydro_damage_bonus",
        "physical_damage_bonus",
        "pyro_damage_bonus",
        "anemo_damage_bonus",
    }
)
_ALLOWED_TALENT_SCALING_MODES = frozenset({"constant", "level_table"})
_ALLOWED_TALENT_COMPONENT_KINDS = frozenset(
    {"flat", "plain_ratio", "plain_value", "stat_ratio"}
)
_ALLOWED_ARTIFACT_SET_BONUS_PIECES = frozenset({1, 2, 4})


@dataclass(frozen=True, slots=True)
class AssetManifestAuditIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class AssetManifestAuditReport:
    manifest_path: Path
    data_version: str
    character_count: int
    character_level_stat_count: int
    character_level_complete_count: int
    weapon_count: int
    weapon_level_stat_count: int
    weapon_level_complete_count: int
    artifact_set_count: int
    artifact_set_bonus_count: int
    talent_scaling_count: int
    effect_payload_count: int
    issues: tuple[AssetManifestAuditIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def issue_count(self) -> int:
        return len(self.issues)


def audit_asset_manifest(manifest_path: str | Path) -> AssetManifestAuditReport:
    path = Path(manifest_path)
    manifest = load_asset_manifest(path)
    return audit_loaded_asset_manifest(manifest, manifest_path=path)


def audit_loaded_asset_manifest(
    manifest: AssetManifest,
    *,
    manifest_path: str | Path,
) -> AssetManifestAuditReport:
    issues: list[AssetManifestAuditIssue] = []

    _audit_asset_keys(manifest, issues)
    _audit_basic_enums(manifest, issues)

    character_level_complete_count = _audit_character_level_stats(manifest, issues)
    weapon_level_complete_count = _audit_weapon_level_stats(manifest, issues)

    _audit_artifact_set_bonuses(manifest, issues)
    _audit_talent_scalings(manifest, issues)
    _audit_effect_payloads(manifest, issues)

    return AssetManifestAuditReport(
        manifest_path=Path(manifest_path),
        data_version=manifest.meta.get("data_version", ""),
        character_count=len(manifest.characters),
        character_level_stat_count=len(manifest.character_level_stats),
        character_level_complete_count=character_level_complete_count,
        weapon_count=len(manifest.weapons),
        weapon_level_stat_count=len(manifest.weapon_level_stats),
        weapon_level_complete_count=weapon_level_complete_count,
        artifact_set_count=len(manifest.artifact_sets),
        artifact_set_bonus_count=len(manifest.artifact_set_bonuses),
        talent_scaling_count=len(manifest.talent_scalings),
        effect_payload_count=len(manifest.effect_payloads),
        issues=tuple(issues),
    )


def _audit_asset_keys(
    manifest: AssetManifest,
    issues: list[AssetManifestAuditIssue],
) -> None:
    _append_duplicate_issue(
        issues,
        code="duplicate_character_asset_key",
        label="角色 asset_key",
        values=(item.asset_key for item in manifest.characters),
    )
    _append_duplicate_issue(
        issues,
        code="duplicate_character_source_id",
        label="角色 source_id",
        values=(item.source_id for item in manifest.characters),
    )
    _append_duplicate_issue(
        issues,
        code="duplicate_weapon_asset_key",
        label="武器 asset_key",
        values=(item.asset_key for item in manifest.weapons),
    )
    _append_duplicate_issue(
        issues,
        code="duplicate_weapon_source_id",
        label="武器 source_id",
        values=(item.source_id for item in manifest.weapons),
    )
    _append_duplicate_issue(
        issues,
        code="duplicate_artifact_set_asset_key",
        label="圣遗物套装 asset_key",
        values=(item.asset_key for item in manifest.artifact_sets),
    )
    _append_duplicate_issue(
        issues,
        code="duplicate_artifact_set_source_id",
        label="圣遗物套装 source_id",
        values=(item.source_id for item in manifest.artifact_sets),
    )


def _audit_basic_enums(
    manifest: AssetManifest,
    issues: list[AssetManifestAuditIssue],
) -> None:
    invalid_character_elements = sorted(
        item.asset_key for item in manifest.characters if item.element not in _ALLOWED_ELEMENTS
    )
    if invalid_character_elements:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_character_element",
                message=(
                    "角色 element 存在不支持的取值，示例："
                    f"{_format_examples(invalid_character_elements)}"
                ),
            )
        )

    invalid_character_weapon_types = sorted(
        item.asset_key
        for item in manifest.characters
        if item.weapon_type not in _ALLOWED_WEAPON_TYPES
    )
    if invalid_character_weapon_types:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_character_weapon_type",
                message=(
                    "角色 weapon_type 存在不支持的取值，示例："
                    f"{_format_examples(invalid_character_weapon_types)}"
                ),
            )
        )

    invalid_character_rarities = sorted(
        item.asset_key
        for item in manifest.characters
        if item.rarity not in _ALLOWED_CHARACTER_RARITIES
    )
    if invalid_character_rarities:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_character_rarity",
                message=(
                    "角色 rarity 必须是 4 或 5，示例："
                    f"{_format_examples(invalid_character_rarities)}"
                ),
            )
        )

    invalid_weapon_types = sorted(
        item.asset_key for item in manifest.weapons if item.weapon_type not in _ALLOWED_WEAPON_TYPES
    )
    if invalid_weapon_types:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_weapon_type",
                message=(
                    "武器 weapon_type 存在不支持的取值，示例："
                    f"{_format_examples(invalid_weapon_types)}"
                ),
            )
        )

    invalid_weapon_rarities = sorted(
        item.asset_key for item in manifest.weapons if item.rarity not in _ALLOWED_WEAPON_RARITIES
    )
    if invalid_weapon_rarities:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_weapon_rarity",
                message=(
                    "武器 rarity 必须在 1-5 之间，示例："
                    f"{_format_examples(invalid_weapon_rarities)}"
                ),
            )
        )


def _audit_character_level_stats(
    manifest: AssetManifest,
    issues: list[AssetManifestAuditIssue],
) -> int:
    character_keys = {item.asset_key for item in manifest.characters}
    expected_pairs = set(
        _expected_level_phase_pairs(_CHARACTER_LEVELS, _CHARACTER_PROMOTE_MAX_LEVELS)
    )
    expected_by_character = {character_key: expected_pairs for character_key in character_keys}
    actual_by_character: dict[str, set[tuple[int, int]]] = {
        character_key: set() for character_key in character_keys
    }

    _append_duplicate_issue(
        issues,
        code="duplicate_character_level_stats",
        label="角色等级属性",
        values=(
            f"{item.character_key}@{item.level}/{item.ascension_phase}"
            for item in manifest.character_level_stats
        ),
    )

    unknown_character_keys = sorted(
        {
            item.character_key
            for item in manifest.character_level_stats
            if item.character_key not in character_keys
        }
    )
    if unknown_character_keys:
        issues.append(
            AssetManifestAuditIssue(
                code="orphan_character_level_stats",
                message=(
                    "角色等级属性引用了不存在的角色，示例："
                    f"{_format_examples(unknown_character_keys)}"
                ),
            )
        )

    invalid_stat_rows = sorted(
        f"{item.character_key}@{item.level}/{item.ascension_phase}"
        for item in manifest.character_level_stats
        if item.ascension_stat is not None and item.ascension_stat not in _ALLOWED_STATS
    )
    if invalid_stat_rows:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_character_ascension_stat",
                message=(
                    "角色突破属性存在不支持的 stat，示例："
                    f"{_format_examples(invalid_stat_rows)}"
                ),
            )
        )

    invalid_stat_pairs = sorted(
        f"{item.character_key}@{item.level}/{item.ascension_phase}"
        for item in manifest.character_level_stats
        if (item.ascension_stat is None) != (item.ascension_value is None)
    )
    if invalid_stat_pairs:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_character_ascension_pair",
                message=(
                    "角色 ascension_stat 与 ascension_value 必须同时为空或同时存在，示例："
                    f"{_format_examples(invalid_stat_pairs)}"
                ),
            )
        )

    for item in manifest.character_level_stats:
        if item.character_key in actual_by_character:
            actual_by_character[item.character_key].add((item.level, item.ascension_phase))

    _append_level_coverage_issues(
        issues,
        code_prefix="character",
        label="角色",
        actual_by_asset=actual_by_character,
        expected_by_asset=expected_by_character,
    )
    return sum(
        1
        for character_key, pairs in actual_by_character.items()
        if pairs == expected_by_character[character_key]
    )


def _audit_weapon_level_stats(
    manifest: AssetManifest,
    issues: list[AssetManifestAuditIssue],
) -> int:
    weapon_keys = {item.asset_key for item in manifest.weapons}
    expected_by_weapon = {
        item.asset_key: set(
            _expected_level_phase_pairs(
                _weapon_levels_for_rarity(item.rarity),
                _weapon_promote_max_levels_for_rarity(item.rarity),
            )
        )
        for item in manifest.weapons
    }
    actual_by_weapon: dict[str, set[tuple[int, int]]] = {
        weapon_key: set() for weapon_key in weapon_keys
    }

    _append_duplicate_issue(
        issues,
        code="duplicate_weapon_level_stats",
        label="武器等级属性",
        values=(
            f"{item.weapon_key}@{item.level}/{item.ascension_phase}"
            for item in manifest.weapon_level_stats
        ),
    )

    unknown_weapon_keys = sorted(
        {
            item.weapon_key
            for item in manifest.weapon_level_stats
            if item.weapon_key not in weapon_keys
        }
    )
    if unknown_weapon_keys:
        issues.append(
            AssetManifestAuditIssue(
                code="orphan_weapon_level_stats",
                message=f"武器等级属性引用了不存在的武器，示例：{_format_examples(unknown_weapon_keys)}",
            )
        )

    invalid_stat_rows = sorted(
        f"{item.weapon_key}@{item.level}/{item.ascension_phase}"
        for item in manifest.weapon_level_stats
        if item.secondary_stat is not None and item.secondary_stat not in _ALLOWED_STATS
    )
    if invalid_stat_rows:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_weapon_secondary_stat",
                message=f"武器副属性存在不支持的 stat，示例：{_format_examples(invalid_stat_rows)}",
            )
        )

    invalid_stat_pairs = sorted(
        f"{item.weapon_key}@{item.level}/{item.ascension_phase}"
        for item in manifest.weapon_level_stats
        if (item.secondary_stat is None) != (item.secondary_value is None)
    )
    if invalid_stat_pairs:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_weapon_secondary_pair",
                message=(
                    "武器 secondary_stat 与 secondary_value 必须同时为空或同时存在，示例："
                    f"{_format_examples(invalid_stat_pairs)}"
                ),
            )
        )

    for item in manifest.weapon_level_stats:
        if item.weapon_key in actual_by_weapon:
            actual_by_weapon[item.weapon_key].add((item.level, item.ascension_phase))

    _append_level_coverage_issues(
        issues,
        code_prefix="weapon",
        label="武器",
        actual_by_asset=actual_by_weapon,
        expected_by_asset=expected_by_weapon,
    )
    return sum(
        1
        for weapon_key, pairs in actual_by_weapon.items()
        if pairs == expected_by_weapon[weapon_key]
    )


def _audit_artifact_set_bonuses(
    manifest: AssetManifest,
    issues: list[AssetManifestAuditIssue],
) -> None:
    artifact_set_keys = {item.asset_key for item in manifest.artifact_sets}
    _append_duplicate_issue(
        issues,
        code="duplicate_artifact_set_bonus",
        label="圣遗物套装效果",
        values=(
            f"{item.artifact_set_key}@{item.piece_count}/{item.handler_key}"
            for item in manifest.artifact_set_bonuses
        ),
    )

    unknown_artifact_set_keys = sorted(
        {
            item.artifact_set_key
            for item in manifest.artifact_set_bonuses
            if item.artifact_set_key not in artifact_set_keys
        }
    )
    if unknown_artifact_set_keys:
        issues.append(
            AssetManifestAuditIssue(
                code="orphan_artifact_set_bonus",
                message=(
                    "圣遗物套装效果引用了不存在的套装，示例："
                    f"{_format_examples(unknown_artifact_set_keys)}"
                ),
            )
        )

    invalid_piece_counts = sorted(
        f"{item.artifact_set_key}@{item.piece_count}"
        for item in manifest.artifact_set_bonuses
        if item.piece_count not in _ALLOWED_ARTIFACT_SET_BONUS_PIECES
    )
    if invalid_piece_counts:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_artifact_set_bonus_piece_count",
                message=(
                    "圣遗物套装效果 piece_count 必须是 1、2 或 4，示例："
                    f"{_format_examples(invalid_piece_counts)}"
                ),
            )
        )

    invalid_params = sorted(
        f"{item.artifact_set_key}@{item.piece_count}"
        for item in manifest.artifact_set_bonuses
        if not _valid_artifact_set_bonus_params(item.params)
    )
    if invalid_params:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_artifact_set_bonus_params",
                message=(
                    "圣遗物套装效果 params 不合法，示例："
                    f"{_format_examples(invalid_params)}"
                ),
            )
        )


def _audit_talent_scalings(
    manifest: AssetManifest,
    issues: list[AssetManifestAuditIssue],
) -> None:
    character_keys = {item.asset_key for item in manifest.characters}
    _append_duplicate_issue(
        issues,
        code="duplicate_talent_scaling",
        label="技能倍率条目",
        values=(
            f"{item.character_key}@{item.talent_key}/{item.entry_key}"
            for item in manifest.talent_scalings
        ),
    )

    unknown_character_keys = sorted(
        {
            item.character_key
            for item in manifest.talent_scalings
            if item.character_key not in character_keys
        }
    )
    if unknown_character_keys:
        issues.append(
            AssetManifestAuditIssue(
                code="orphan_talent_scaling",
                message=f"技能倍率引用了不存在的角色，示例：{_format_examples(unknown_character_keys)}",
            )
        )

    invalid_headers: list[str] = []
    invalid_components: list[str] = []
    invalid_values: list[str] = []
    for item in manifest.talent_scalings:
        item_ref = f"{item.character_key}@{item.talent_key}/{item.entry_key}"
        _audit_talent_scaling_payload(
            item.scaling,
            item_ref=item_ref,
            invalid_headers=invalid_headers,
            invalid_components=invalid_components,
            invalid_values=invalid_values,
        )

    if invalid_headers:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_talent_scaling_header",
                message=f"技能倍率 scaling 表头不合法，示例：{_format_examples(invalid_headers)}",
            )
        )
    if invalid_components:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_talent_scaling_components",
                message=f"技能倍率 components 不合法，示例：{_format_examples(invalid_components)}",
            )
        )
    if invalid_values:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_talent_scaling_values",
                message=f"技能倍率 values 不合法，示例：{_format_examples(invalid_values)}",
            )
        )


def _audit_talent_scaling_payload(
    scaling: Mapping[str, Any],
    *,
    item_ref: str,
    invalid_headers: list[str],
    invalid_components: list[str],
    invalid_values: list[str],
) -> None:
    schema_version = scaling.get("schema_version")
    mode = scaling.get("mode")
    if schema_version != 1 or mode not in _ALLOWED_TALENT_SCALING_MODES:
        invalid_headers.append(item_ref)
        return

    level_count = _talent_scaling_level_count(scaling, str(mode), item_ref, invalid_headers)
    if level_count is None:
        return

    components = scaling.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or not components
    ):
        invalid_components.append(item_ref)
        return

    for index, raw_component in enumerate(components):
        component_ref = f"{item_ref}.components[{index}]"
        if not isinstance(raw_component, Mapping):
            invalid_components.append(component_ref)
            continue
        kind = raw_component.get("kind")
        if kind not in _ALLOWED_TALENT_COMPONENT_KINDS:
            invalid_components.append(component_ref)
            continue
        values = raw_component.get("values")
        if not _is_numeric_sequence(values, expected_length=level_count):
            invalid_values.append(component_ref)


def _talent_scaling_level_count(
    scaling: Mapping[str, Any],
    mode: str,
    item_ref: str,
    invalid_headers: list[str],
) -> int | None:
    if mode == "constant":
        return 1

    level_min = scaling.get("level_min")
    level_max = scaling.get("level_max")
    if (
        not isinstance(level_min, int)
        or isinstance(level_min, bool)
        or not isinstance(level_max, int)
        or isinstance(level_max, bool)
        or level_min <= 0
        or level_max < level_min
    ):
        invalid_headers.append(item_ref)
        return None
    return level_max - level_min + 1


def _is_numeric_sequence(value: Any, *, expected_length: int) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False
    if len(value) != expected_length:
        return False
    return all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)


def _audit_effect_payloads(
    manifest: AssetManifest,
    issues: list[AssetManifestAuditIssue],
) -> None:
    known_owner_keys = {
        "artifact_set": {item.asset_key for item in manifest.artifact_sets},
        "character": {item.asset_key for item in manifest.characters},
        "weapon": {item.asset_key for item in manifest.weapons},
    }

    _append_duplicate_issue(
        issues,
        code="duplicate_effect_payload",
        label="效果参数 effect_key",
        values=(item.effect_key for item in manifest.effect_payloads),
    )

    unknown_owner_refs = sorted(
        f"{item.effect_key}->{item.owner_type}:{item.owner_key}"
        for item in manifest.effect_payloads
        if item.owner_type in known_owner_keys
        and item.owner_key not in known_owner_keys[item.owner_type]
    )
    if unknown_owner_refs:
        issues.append(
            AssetManifestAuditIssue(
                code="orphan_effect_payload",
                message=(
                    "效果参数引用了不存在的 owner，示例："
                    f"{_format_examples(unknown_owner_refs)}"
                ),
            )
        )

    invalid_effect_payloads = sorted(
        item.effect_key
        for item in manifest.effect_payloads
        if not _valid_effect_payload_params(item.params)
    )
    if invalid_effect_payloads:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_effect_payload_params",
                message=(
                    "效果参数 params 不合法，示例："
                    f"{_format_examples(invalid_effect_payloads)}"
                ),
            )
        )

    invalid_unlock_keys = sorted(
        item.effect_key
        for item in manifest.effect_payloads
        if not _valid_effect_payload_unlock_key(
            item.owner_type,
            item.effect_kind,
            item.unlock_key,
        )
    )
    if invalid_unlock_keys:
        issues.append(
            AssetManifestAuditIssue(
                code="invalid_effect_payload_unlock_key",
                message=(
                    "效果参数 unlock_key 不合法，示例："
                    f"{_format_examples(invalid_unlock_keys)}"
                ),
            )
        )


def _valid_effect_payload_params(params: Mapping[str, Any]) -> bool:
    if params.get("schema_version") != 1:
        return False
    components = params.get("components")
    if components is None:
        return True
    if not isinstance(components, Sequence) or isinstance(components, (str, bytes, bytearray)):
        return False

    refinement_min = params.get("refinement_min")
    refinement_max = params.get("refinement_max")
    if refinement_min is not None or refinement_max is not None:
        if (
            not isinstance(refinement_min, int)
            or isinstance(refinement_min, bool)
            or not isinstance(refinement_max, int)
            or isinstance(refinement_max, bool)
            or refinement_min <= 0
            or refinement_max < refinement_min
        ):
            return False
        expected_length = refinement_max - refinement_min + 1
    else:
        expected_length = None

    for component in components:
        if not isinstance(component, Mapping):
            return False
        values = component.get("values")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
            return False
        if expected_length is not None and len(values) != expected_length:
            return False
    return True


def _valid_effect_payload_unlock_key(
    owner_type: str,
    effect_kind: str,
    unlock_key: str | None,
) -> bool:
    if owner_type != "character":
        return True
    if effect_kind == "constellation":
        return unlock_key in {"c1", "c2", "c3", "c4", "c5", "c6"}
    if effect_kind in {"passive", "passive_exploration"}:
        return (
            isinstance(unlock_key, str)
            and unlock_key.startswith("passive:")
            and len(unlock_key) > len("passive:")
        )
    return True


def _valid_artifact_set_bonus_params(params: Mapping[str, Any]) -> bool:
    if params.get("schema_version") != 1:
        return False
    components = params.get("components")
    if components is None:
        return True
    if not isinstance(components, Sequence) or isinstance(components, (str, bytes, bytearray)):
        return False
    for component in components:
        if not isinstance(component, Mapping):
            return False
        values = component.get("values")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
            return False
    return True


def _append_level_coverage_issues(
    issues: list[AssetManifestAuditIssue],
    *,
    code_prefix: str,
    label: str,
    actual_by_asset: dict[str, set[tuple[int, int]]],
    expected_by_asset: dict[str, set[tuple[int, int]]],
) -> None:
    missing_by_asset: dict[str, tuple[tuple[int, int], ...]] = {}
    unexpected_by_asset: dict[str, tuple[tuple[int, int], ...]] = {}
    for asset_key, actual_pairs in sorted(actual_by_asset.items()):
        expected_pairs = expected_by_asset[asset_key]
        missing = tuple(sorted(expected_pairs - actual_pairs))
        unexpected = tuple(sorted(actual_pairs - expected_pairs))
        if missing:
            missing_by_asset[asset_key] = missing
        if unexpected:
            unexpected_by_asset[asset_key] = unexpected

    if missing_by_asset:
        total_missing = sum(len(missing) for missing in missing_by_asset.values())
        issues.append(
            AssetManifestAuditIssue(
                code=f"incomplete_{code_prefix}_level_stats",
                message=(
                    f"{len(missing_by_asset)} 个{label}缺少完整等级属性，共缺 {total_missing} 条；"
                    f"示例：{_format_level_coverage_examples(missing_by_asset, verb='缺')}"
                ),
            )
        )

    if unexpected_by_asset:
        total_unexpected = sum(len(unexpected) for unexpected in unexpected_by_asset.values())
        issues.append(
            AssetManifestAuditIssue(
                code=f"unexpected_{code_prefix}_level_stats",
                message=(
                    f"{len(unexpected_by_asset)} 个{label}存在非预期等级属性，"
                    f"共 {total_unexpected} 条；"
                    f"示例：{_format_level_coverage_examples(unexpected_by_asset, verb='多')}"
                ),
            )
        )


def _append_duplicate_issue(
    issues: list[AssetManifestAuditIssue],
    *,
    code: str,
    label: str,
    values: Iterable[str],
) -> None:
    duplicates = _duplicates(values)
    if duplicates:
        issues.append(
            AssetManifestAuditIssue(
                code=code,
                message=f"{label} 存在重复值，示例：{_format_examples(duplicates)}",
            )
        )


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    counter = Counter(values)
    return tuple(sorted(value for value, count in counter.items() if count > 1))


def _expected_level_phase_pairs(
    levels: tuple[int, ...],
    promote_max_levels: tuple[int, ...],
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (level, phase)
        for level in levels
        for phase in _phases_for_level(level, promote_max_levels)
    )


def _weapon_levels_for_rarity(rarity: int) -> tuple[int, ...]:
    max_level = 70 if rarity <= 2 else 90
    return tuple(level for level in _WEAPON_LEVELS if level <= max_level)


def _weapon_promote_max_levels_for_rarity(rarity: int) -> tuple[int, ...]:
    if rarity <= 2:
        return _LOW_RARITY_WEAPON_PROMOTE_MAX_LEVELS
    return _STANDARD_WEAPON_PROMOTE_MAX_LEVELS


def _phases_for_level(level: int, promote_max_levels: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(
        phase
        for phase, max_level in enumerate(promote_max_levels)
        if level <= max_level and (phase == 0 or level >= promote_max_levels[phase - 1])
    )


def _format_level_coverage_examples(
    rows_by_asset: dict[str, tuple[tuple[int, int], ...]],
    *,
    verb: str,
    limit: int = 5,
) -> str:
    examples = []
    for asset_key, pairs in list(sorted(rows_by_asset.items()))[:limit]:
        examples.append(
            f"{asset_key} {verb} {len(pairs)} 条（如 {_format_level_phase_examples(pairs)}）"
        )
    omitted = len(rows_by_asset) - len(examples)
    if omitted > 0:
        examples.append(f"另有 {omitted} 项")
    return "；".join(examples)


def _format_level_phase_examples(pairs: tuple[tuple[int, int], ...], *, limit: int = 3) -> str:
    return _format_examples((f"{level}/{phase}" for level, phase in pairs), limit=limit)


def _format_examples(values: Iterable[str], *, limit: int = 5) -> str:
    examples = tuple(values)
    shown = examples[:limit]
    suffix = "" if len(examples) <= limit else f"，另有 {len(examples) - limit} 项"
    return "、".join(shown) + suffix
