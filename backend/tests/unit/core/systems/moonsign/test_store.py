"""月兆 Store 测试。"""

from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.moonsign import (
    MoonsignBonusRecord,
    MoonsignLevel,
    MoonsignStateConflictError,
    MoonsignStore,
)


def test_store_sets_level_once_and_guards_second_write():
    store = MoonsignStore()
    ref = AttributeSubjectRef.character("character:slot_1")
    store.set_level(MoonsignLevel.NASCENT, (ref,))
    assert store.level is MoonsignLevel.NASCENT
    assert store.moonsign_character_refs == (ref,)
    with pytest.raises(MoonsignStateConflictError, match="只能"):
        store.set_level(MoonsignLevel.ASCENDANT, (ref,))


def test_store_set_level_rejects_non_subject_refs_before_sorting():
    store = MoonsignStore()
    with pytest.raises(MoonsignStateConflictError, match="月兆角色引用"):
        store.set_level(MoonsignLevel.ASCENDANT, cast(Any, ("character:slot_1",)))


def test_store_bonus_override_and_expiry():
    store = MoonsignStore()
    ref = AttributeSubjectRef.character("character:slot_1")
    first = MoonsignBonusRecord(ref, 0.1, 100, 1300)
    store.apply_bonus(first)
    assert store.current_bonus_value(200) == 0.1

    second = MoonsignBonusRecord(ref, 0.2, 300, 1500)
    store.apply_bonus(second)
    assert store.current_bonus_value(400) == 0.2

    expired = store.clear_expired(1500)
    assert expired is second
    assert store.bonus is None
    assert store.current_bonus_value(1501) == 0.0
    assert store.clear_expired(1600) is None
