from __future__ import annotations

import pytest

from genshin_sim.assets import (
    AssetDbInfo,
    AssetValidationError,
    CharacterAsset,
    EffectPayload,
    TalentScalingEntry,
    WeaponAsset,
    split_asset_key,
    validate_asset_key,
)


def test_split_asset_key_parses_identity():
    parts = split_asset_key("character:75", "character")

    assert parts.asset_type == "character"
    assert parts.source_id == "75"


def test_validate_asset_key_rejects_wrong_type():
    with pytest.raises(AssetValidationError, match="expected weapon asset_key"):
        validate_asset_key("character:75", "weapon")


def test_character_asset_validates_key_and_name():
    asset = CharacterAsset(
        asset_key="character:75",
        source_id="75",
        name="test",
        element="hydro",
        weapon_type="sword",
        rarity=5,
        handler_key="generic.test_character",
    )

    assert asset.asset_key == "character:75"


def test_weapon_asset_requires_valid_key():
    with pytest.raises(AssetValidationError):
        WeaponAsset(
            asset_key="weapon:11512",
            source_id="bad",
            name="test",
            weapon_type="sword",
            rarity=4,
        )


def test_asset_info_rejects_negative_counts():
    with pytest.raises(AssetValidationError):
        AssetDbInfo(meta={}, character_count=-1)


def test_talent_scaling_entry_keeps_tags_tuple():
    entry = TalentScalingEntry(
        character_key="character:75",
        talent_key="elemental_skill",
        entry_key="skill",
        label="skill",
        scaling={},
        tags=("a", "b"),
    )

    assert entry.tags == ("a", "b")


def test_effect_payload_validates_owner_key():
    payload = EffectPayload(
        effect_key="effect:1",
        owner_type="character",
        owner_key="character:75",
        effect_kind="test",
        handler_key="generic.static_modifiers",
        params={"schema_version": 1},
    )

    assert payload.owner_key == "character:75"
