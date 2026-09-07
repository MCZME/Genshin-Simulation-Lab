from __future__ import annotations

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.entity_states import HealthState
from genshin_sim.core.systems.health import (
    CharacterHealthNotFoundError,
    CharacterHealthStore,
    HealthValidationError,
    UnsupportedHealthSubjectError,
)

CHARACTER_REF = AttributeSubjectRef.character("character:slot_1")
TARGET_REF = AttributeSubjectRef.target("target:target_1")


def test_character_health_store_indexes_health_by_character_ref():
    health = HealthState(1000)
    store = CharacterHealthStore(((CHARACTER_REF, health),))

    assert store.contains(CHARACTER_REF)
    assert store.get(CHARACTER_REF) is health
    assert store.require(CHARACTER_REF) is health


def test_character_health_store_returns_none_or_raises_for_missing_character():
    store = CharacterHealthStore()

    assert store.get(CHARACTER_REF) is None
    with pytest.raises(CharacterHealthNotFoundError):
        store.require(CHARACTER_REF)


def test_character_health_store_rejects_duplicate_character_refs():
    with pytest.raises(HealthValidationError, match="角色生命主体重复"):
        CharacterHealthStore(((CHARACTER_REF, HealthState(100)), (CHARACTER_REF, HealthState(50))))


def test_character_health_store_rejects_target_subjects():
    with pytest.raises(UnsupportedHealthSubjectError):
        CharacterHealthStore(((TARGET_REF, HealthState(100)),))

    store = CharacterHealthStore()
    with pytest.raises(UnsupportedHealthSubjectError):
        store.get(TARGET_REF)


def test_character_health_store_returns_original_health_state_reference():
    health = HealthState(1000)
    store = CharacterHealthStore(((CHARACTER_REF, health),))

    store.require(CHARACTER_REF).current_hp = 300

    assert health.current_hp == 300
