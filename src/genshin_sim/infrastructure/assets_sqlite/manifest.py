from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
from genshin_sim.infrastructure.assets_sqlite.schema import (
    ASSET_SCHEMA_VERSION,
    validate_asset_database,
)
from genshin_sim.infrastructure.assets_sqlite.writer import SQLiteAssetDataWriter

ASSET_MANIFEST_KIND = "asset_manifest"
ASSET_MANIFEST_SCHEMA_VERSION = 1

_TOP_LEVEL_FIELDS = {
    "schema_version",
    "kind",
    "meta",
    "characters",
    "character_level_stats",
    "weapons",
    "weapon_level_stats",
    "artifact_sets",
    "artifact_set_bonuses",
    "talent_scalings",
    "effect_payloads",
}


@dataclass(frozen=True, slots=True)
class AssetManifest:
    meta: dict[str, str]
    characters: tuple[CharacterAsset, ...]
    character_level_stats: tuple[CharacterLevelStats, ...]
    weapons: tuple[WeaponAsset, ...]
    weapon_level_stats: tuple[WeaponLevelStats, ...]
    artifact_sets: tuple[ArtifactSetAsset, ...]
    artifact_set_bonuses: tuple[ArtifactSetBonus, ...]
    talent_scalings: tuple[TalentScalingEntry, ...]
    effect_payloads: tuple[EffectPayload, ...]


def build_asset_database_from_manifest(
    db_path: str | Path,
    manifest_path: str | Path,
) -> Path:
    manifest = load_asset_manifest(manifest_path)
    target_path = Path(db_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    if temp_path.exists():
        temp_path.unlink()

    try:
        SQLiteAssetDataWriter(temp_path).replace_all(
            meta=manifest.meta,
            characters=manifest.characters,
            character_level_stats=manifest.character_level_stats,
            weapons=manifest.weapons,
            weapon_level_stats=manifest.weapon_level_stats,
            artifact_sets=manifest.artifact_sets,
            artifact_set_bonuses=manifest.artifact_set_bonuses,
            talent_scalings=manifest.talent_scalings,
            effect_payloads=manifest.effect_payloads,
        )
        validate_asset_database(temp_path)
        temp_path.replace(target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return target_path


def load_asset_manifest(manifest_path: str | Path) -> AssetManifest:
    path = Path(manifest_path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AssetValidationError(f"无法读取资产 manifest：{path}") from exc

    try:
        raw_payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AssetValidationError(f"资产 manifest 必须是合法 JSON：{path}") from exc

    payload = _require_mapping(raw_payload, "manifest")
    _reject_unknown_keys(payload, _TOP_LEVEL_FIELDS, "manifest")
    _validate_manifest_header(payload)

    return AssetManifest(
        meta=_load_meta(payload, path, raw_text),
        characters=tuple(
            _load_character(item, f"characters[{index}]")
            for index, item in enumerate(_optional_sequence(payload, "characters"))
        ),
        character_level_stats=tuple(
            _load_character_level_stats(item, f"character_level_stats[{index}]")
            for index, item in enumerate(_optional_sequence(payload, "character_level_stats"))
        ),
        weapons=tuple(
            _load_weapon(item, f"weapons[{index}]")
            for index, item in enumerate(_optional_sequence(payload, "weapons"))
        ),
        weapon_level_stats=tuple(
            _load_weapon_level_stats(item, f"weapon_level_stats[{index}]")
            for index, item in enumerate(_optional_sequence(payload, "weapon_level_stats"))
        ),
        artifact_sets=tuple(
            _load_artifact_set(item, f"artifact_sets[{index}]")
            for index, item in enumerate(_optional_sequence(payload, "artifact_sets"))
        ),
        artifact_set_bonuses=tuple(
            _load_artifact_set_bonus(item, f"artifact_set_bonuses[{index}]")
            for index, item in enumerate(_optional_sequence(payload, "artifact_set_bonuses"))
        ),
        talent_scalings=tuple(
            _load_talent_scaling(item, f"talent_scalings[{index}]")
            for index, item in enumerate(_optional_sequence(payload, "talent_scalings"))
        ),
        effect_payloads=tuple(
            _load_effect_payload(item, f"effect_payloads[{index}]")
            for index, item in enumerate(_optional_sequence(payload, "effect_payloads"))
        ),
    )


def _validate_manifest_header(payload: Mapping[str, Any]) -> None:
    schema_version = _require_field(payload, "schema_version", "manifest")
    if schema_version != ASSET_MANIFEST_SCHEMA_VERSION:
        raise AssetValidationError(f"不支持的资产 manifest schema_version：{schema_version!r}")

    kind = _require_field(payload, "kind", "manifest")
    if kind != ASSET_MANIFEST_KIND:
        raise AssetValidationError(f"资产 manifest kind 必须是 {ASSET_MANIFEST_KIND!r}")


def _load_meta(payload: Mapping[str, Any], path: Path, raw_text: str) -> dict[str, str]:
    meta = _optional_mapping(payload, "meta")
    rows = {str(key): str(value) for key, value in meta.items()}
    rows.setdefault("schema_version", ASSET_SCHEMA_VERSION)
    if rows["schema_version"] != ASSET_SCHEMA_VERSION:
        raise AssetValidationError(f"资产数据库 schema_version 必须是 {ASSET_SCHEMA_VERSION!r}")
    rows.setdefault("source_name", "asset-manifest")
    rows.setdefault("source_version", path.name)
    rows.setdefault("data_version", rows["source_version"])
    rows.setdefault("importer_version", "asset-manifest-1")
    rows.setdefault("content_hash", hashlib.sha256(raw_text.encode("utf-8")).hexdigest())
    return rows


def _load_character(raw: Any, path: str) -> CharacterAsset:
    item = _require_mapping(raw, path)
    _reject_unknown_keys(
        item,
        {
            "asset_key",
            "source_id",
            "name",
            "element",
            "weapon_type",
            "rarity",
            "burst_energy_cost",
            "handler_key",
        },
        path,
    )
    return CharacterAsset(
        asset_key=_required_str(item, "asset_key", path),
        source_id=_required_str(item, "source_id", path),
        name=_required_str(item, "name", path),
        element=_required_str(item, "element", path),
        weapon_type=_required_str(item, "weapon_type", path),
        rarity=_required_int(item, "rarity", path),
        burst_energy_cost=_required_float(item, "burst_energy_cost", path),
        handler_key=_optional_str(item, "handler_key", path),
    )


def _load_character_level_stats(raw: Any, path: str) -> CharacterLevelStats:
    item = _require_mapping(raw, path)
    _reject_unknown_keys(
        item,
        {
            "character_key",
            "level",
            "ascension_phase",
            "base_hp",
            "base_atk",
            "base_def",
            "ascension_stat",
            "ascension_value",
        },
        path,
    )
    return CharacterLevelStats(
        character_key=_required_str(item, "character_key", path),
        level=_required_int(item, "level", path),
        ascension_phase=_required_int(item, "ascension_phase", path),
        base_hp=_required_float(item, "base_hp", path),
        base_atk=_required_float(item, "base_atk", path),
        base_def=_required_float(item, "base_def", path),
        ascension_stat=_optional_str(item, "ascension_stat", path),
        ascension_value=_optional_float(item, "ascension_value", path),
    )


def _load_weapon(raw: Any, path: str) -> WeaponAsset:
    item = _require_mapping(raw, path)
    _reject_unknown_keys(
        item,
        {"asset_key", "source_id", "name", "weapon_type", "rarity", "handler_key"},
        path,
    )
    return WeaponAsset(
        asset_key=_required_str(item, "asset_key", path),
        source_id=_required_str(item, "source_id", path),
        name=_required_str(item, "name", path),
        weapon_type=_required_str(item, "weapon_type", path),
        rarity=_required_int(item, "rarity", path),
        handler_key=_optional_str(item, "handler_key", path),
    )


def _load_weapon_level_stats(raw: Any, path: str) -> WeaponLevelStats:
    item = _require_mapping(raw, path)
    _reject_unknown_keys(
        item,
        {
            "weapon_key",
            "level",
            "ascension_phase",
            "base_atk",
            "secondary_stat",
            "secondary_value",
        },
        path,
    )
    return WeaponLevelStats(
        weapon_key=_required_str(item, "weapon_key", path),
        level=_required_int(item, "level", path),
        ascension_phase=_required_int(item, "ascension_phase", path),
        base_atk=_required_float(item, "base_atk", path),
        secondary_stat=_optional_str(item, "secondary_stat", path),
        secondary_value=_optional_float(item, "secondary_value", path),
    )


def _load_artifact_set(raw: Any, path: str) -> ArtifactSetAsset:
    item = _require_mapping(raw, path)
    _reject_unknown_keys(item, {"asset_key", "source_id", "name", "handler_key"}, path)
    return ArtifactSetAsset(
        asset_key=_required_str(item, "asset_key", path),
        source_id=_required_str(item, "source_id", path),
        name=_required_str(item, "name", path),
        handler_key=_optional_str(item, "handler_key", path),
    )


def _load_artifact_set_bonus(raw: Any, path: str) -> ArtifactSetBonus:
    item = _require_mapping(raw, path)
    _reject_unknown_keys(
        item,
        {"artifact_set_key", "piece_count", "handler_key", "params"},
        path,
    )
    return ArtifactSetBonus(
        artifact_set_key=_required_str(item, "artifact_set_key", path),
        piece_count=_required_int(item, "piece_count", path),
        handler_key=_required_str(item, "handler_key", path),
        params=dict(_required_mapping(item, "params", path)),
    )


def _load_talent_scaling(raw: Any, path: str) -> TalentScalingEntry:
    item = _require_mapping(raw, path)
    _reject_unknown_keys(
        item,
        {"character_key", "talent_key", "entry_key", "label", "scaling", "tags"},
        path,
    )
    return TalentScalingEntry(
        character_key=_required_str(item, "character_key", path),
        talent_key=_required_str(item, "talent_key", path),
        entry_key=_required_str(item, "entry_key", path),
        label=_required_str(item, "label", path),
        scaling=dict(_required_mapping(item, "scaling", path)),
        tags=_optional_string_tuple(item, "tags", path),
    )


def _load_effect_payload(raw: Any, path: str) -> EffectPayload:
    item = _require_mapping(raw, path)
    _reject_unknown_keys(
        item,
        {
            "effect_key",
            "owner_type",
            "owner_key",
            "effect_kind",
            "unlock_key",
            "handler_key",
            "params",
        },
        path,
    )
    return EffectPayload(
        effect_key=_required_str(item, "effect_key", path),
        owner_type=_required_str(item, "owner_type", path),
        owner_key=_required_str(item, "owner_key", path),
        effect_kind=_required_str(item, "effect_kind", path),
        unlock_key=_optional_str(item, "unlock_key", path),
        handler_key=_required_str(item, "handler_key", path),
        params=dict(_required_mapping(item, "params", path)),
    )


def _optional_sequence(payload: Mapping[str, Any], field_name: str) -> Sequence[Any]:
    value = payload.get(field_name, ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AssetValidationError(f"{field_name} 必须是 JSON 数组")
    return value


def _optional_mapping(payload: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    value = payload.get(field_name, {})
    return _require_mapping(value, field_name)


def _required_mapping(
    payload: Mapping[str, Any],
    field_name: str,
    item_path: str,
) -> Mapping[str, Any]:
    value = _require_field(payload, field_name, item_path)
    return _require_mapping(value, f"{item_path}.{field_name}")


def _require_mapping(value: Any, item_path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssetValidationError(f"{item_path} 必须是 JSON 对象")
    return value


def _reject_unknown_keys(
    payload: Mapping[str, Any],
    allowed_fields: set[str],
    item_path: str,
) -> None:
    unknown = sorted(str(key) for key in payload if str(key) not in allowed_fields)
    if unknown:
        raise AssetValidationError(f"{item_path} 包含未知字段：{', '.join(unknown)}")


def _require_field(payload: Mapping[str, Any], field_name: str, item_path: str) -> Any:
    if field_name not in payload:
        raise AssetValidationError(f"{item_path}.{field_name} 是必填字段")
    return payload[field_name]


def _required_str(payload: Mapping[str, Any], field_name: str, item_path: str) -> str:
    value = _require_field(payload, field_name, item_path)
    if not isinstance(value, str):
        raise AssetValidationError(f"{item_path}.{field_name} 必须是字符串")
    return value


def _optional_str(payload: Mapping[str, Any], field_name: str, item_path: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise AssetValidationError(f"{item_path}.{field_name} 必须是字符串")
    return value


def _required_int(payload: Mapping[str, Any], field_name: str, item_path: str) -> int:
    value = _require_field(payload, field_name, item_path)
    if not isinstance(value, int) or isinstance(value, bool):
        raise AssetValidationError(f"{item_path}.{field_name} 必须是整数")
    return value


def _required_float(payload: Mapping[str, Any], field_name: str, item_path: str) -> float:
    value = _require_field(payload, field_name, item_path)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise AssetValidationError(f"{item_path}.{field_name} 必须是数字")
    return float(value)


def _optional_float(payload: Mapping[str, Any], field_name: str, item_path: str) -> float | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise AssetValidationError(f"{item_path}.{field_name} 必须是数字")
    return float(value)


def _optional_string_tuple(
    payload: Mapping[str, Any],
    field_name: str,
    item_path: str,
) -> tuple[str, ...]:
    value = payload.get(field_name, ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AssetValidationError(f"{item_path}.{field_name} 必须是 JSON 数组")
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise AssetValidationError(f"{item_path}.{field_name}[{index}] 必须是字符串")
    return tuple(value)
