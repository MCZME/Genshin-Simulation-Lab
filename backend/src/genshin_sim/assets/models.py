from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from genshin_sim.assets.errors import AssetValidationError

_ASSET_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True, slots=True)
class AssetKeyParts:
    asset_type: str
    source_id: str


def split_asset_key(asset_key: str, expected_type: str | None = None) -> AssetKeyParts:
    if not isinstance(asset_key, str) or not asset_key:
        raise AssetValidationError(f"invalid asset_key: {asset_key!r}")
    if asset_key.count(":") != 1:
        raise AssetValidationError(f"invalid asset_key: {asset_key!r}")

    asset_type, source_id = asset_key.split(":")
    if not _ASSET_TYPE_PATTERN.fullmatch(asset_type):
        raise AssetValidationError(f"invalid asset_key type: {asset_key!r}")
    if not _SOURCE_ID_PATTERN.fullmatch(source_id):
        raise AssetValidationError(f"invalid asset_key source_id: {asset_key!r}")
    if expected_type is not None and asset_type != expected_type:
        raise AssetValidationError(f"expected {expected_type} asset_key, got {asset_key!r}")
    return AssetKeyParts(asset_type=asset_type, source_id=source_id)


def validate_asset_key(asset_key: str, expected_type: str | None = None) -> str:
    split_asset_key(asset_key, expected_type)
    return asset_key


def _require_non_empty_string(value: str | None, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise AssetValidationError(f"{field_name} must be a non-empty string")


def _require_optional_non_empty_string(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_non_empty_string(value, field_name)


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssetValidationError(f"{field_name} must be a positive integer")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AssetValidationError(f"{field_name} must be a non-negative integer")


def _require_non_negative_number(value: float, field_name: str) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise AssetValidationError(f"{field_name} must be a non-negative number")


def _require_mapping(value: Mapping[str, Any], field_name: str) -> None:
    if not isinstance(value, Mapping):
        raise AssetValidationError(f"{field_name} must be an object")


def _validate_asset_identity(asset_key: str, source_id: str, expected_type: str) -> None:
    parts = split_asset_key(asset_key, expected_type)
    _require_non_empty_string(source_id, "source_id")
    if parts.source_id != source_id:
        raise AssetValidationError(
            f"asset_key source_id {parts.source_id!r} does not match source_id {source_id!r}"
        )


@dataclass(frozen=True, slots=True)
class AssetDbInfo:
    meta: dict[str, str]
    character_count: int = 0
    weapon_count: int = 0
    artifact_set_count: int = 0

    def __post_init__(self) -> None:
        _require_mapping(self.meta, "meta")
        _require_non_negative_int(self.character_count, "character_count")
        _require_non_negative_int(self.weapon_count, "weapon_count")
        _require_non_negative_int(self.artifact_set_count, "artifact_set_count")


@dataclass(frozen=True, slots=True)
class CharacterAsset:
    asset_key: str
    source_id: str
    name: str
    element: str
    weapon_type: str
    rarity: int
    burst_energy_cost: float | None = None
    handler_key: str | None = None

    def __post_init__(self) -> None:
        _validate_asset_identity(self.asset_key, self.source_id, "character")
        _require_non_empty_string(self.name, "name")
        _require_non_empty_string(self.element, "element")
        _require_non_empty_string(self.weapon_type, "weapon_type")
        _require_positive_int(self.rarity, "rarity")
        if self.burst_energy_cost is not None:
            _require_non_negative_number(self.burst_energy_cost, "burst_energy_cost")
        _require_optional_non_empty_string(self.handler_key, "handler_key")


@dataclass(frozen=True, slots=True)
class CharacterLevelStats:
    character_key: str
    level: int
    ascension_phase: int
    base_hp: float
    base_atk: float
    base_def: float
    ascension_stat: str | None = None
    ascension_value: float | None = None

    def __post_init__(self) -> None:
        validate_asset_key(self.character_key, "character")
        _require_positive_int(self.level, "level")
        _require_non_negative_int(self.ascension_phase, "ascension_phase")
        _require_non_negative_number(self.base_hp, "base_hp")
        _require_non_negative_number(self.base_atk, "base_atk")
        _require_non_negative_number(self.base_def, "base_def")
        _require_optional_non_empty_string(self.ascension_stat, "ascension_stat")
        if self.ascension_value is not None:
            _require_non_negative_number(self.ascension_value, "ascension_value")


@dataclass(frozen=True, slots=True)
class WeaponAsset:
    asset_key: str
    source_id: str
    name: str
    weapon_type: str
    rarity: int
    handler_key: str | None = None

    def __post_init__(self) -> None:
        _validate_asset_identity(self.asset_key, self.source_id, "weapon")
        _require_non_empty_string(self.name, "name")
        _require_non_empty_string(self.weapon_type, "weapon_type")
        _require_positive_int(self.rarity, "rarity")
        _require_optional_non_empty_string(self.handler_key, "handler_key")


@dataclass(frozen=True, slots=True)
class WeaponLevelStats:
    weapon_key: str
    level: int
    ascension_phase: int
    base_atk: float
    secondary_stat: str | None = None
    secondary_value: float | None = None

    def __post_init__(self) -> None:
        validate_asset_key(self.weapon_key, "weapon")
        _require_positive_int(self.level, "level")
        _require_non_negative_int(self.ascension_phase, "ascension_phase")
        _require_non_negative_number(self.base_atk, "base_atk")
        _require_optional_non_empty_string(self.secondary_stat, "secondary_stat")
        if self.secondary_value is not None:
            _require_non_negative_number(self.secondary_value, "secondary_value")


@dataclass(frozen=True, slots=True)
class ArtifactSetAsset:
    asset_key: str
    source_id: str
    name: str
    handler_key: str | None = None

    def __post_init__(self) -> None:
        _validate_asset_identity(self.asset_key, self.source_id, "artifact_set")
        _require_non_empty_string(self.name, "name")
        _require_optional_non_empty_string(self.handler_key, "handler_key")


@dataclass(frozen=True, slots=True)
class ArtifactSetBonus:
    artifact_set_key: str
    piece_count: int
    handler_key: str
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_asset_key(self.artifact_set_key, "artifact_set")
        _require_positive_int(self.piece_count, "piece_count")
        _require_non_empty_string(self.handler_key, "handler_key")
        _require_mapping(self.params, "params")


@dataclass(frozen=True, slots=True)
class TalentScalingEntry:
    character_key: str
    talent_key: str
    entry_key: str
    label: str
    scaling: dict[str, Any]
    tags: tuple[str, ...] = ()
    entry_id: int | None = None

    def __post_init__(self) -> None:
        validate_asset_key(self.character_key, "character")
        _require_non_empty_string(self.talent_key, "talent_key")
        _require_non_empty_string(self.entry_key, "entry_key")
        _require_non_empty_string(self.label, "label")
        _require_mapping(self.scaling, "scaling")
        if not isinstance(self.tags, Sequence) or isinstance(self.tags, (str, bytes, bytearray)):
            raise AssetValidationError("tags must be a sequence of strings")
        for index, tag in enumerate(self.tags):
            _require_non_empty_string(tag, f"tags[{index}]")
        object.__setattr__(self, "tags", tuple(self.tags))
        if self.entry_id is not None:
            _require_positive_int(self.entry_id, "entry_id")


@dataclass(frozen=True, slots=True)
class EffectPayload:
    effect_key: str
    owner_type: str
    owner_key: str
    effect_kind: str
    handler_key: str
    params: dict[str, Any]
    unlock_key: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.effect_key, "effect_key")
        _require_non_empty_string(self.owner_type, "owner_type")
        _require_non_empty_string(self.owner_key, "owner_key")
        if self.owner_type in {"character", "weapon", "artifact_set"}:
            validate_asset_key(self.owner_key, self.owner_type)
        _require_non_empty_string(self.effect_kind, "effect_kind")
        _require_non_empty_string(self.handler_key, "handler_key")
        _require_mapping(self.params, "params")
        _require_optional_non_empty_string(self.unlock_key, "unlock_key")
