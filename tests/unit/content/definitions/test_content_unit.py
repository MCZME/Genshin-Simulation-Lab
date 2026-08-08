from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.content.definitions.components import GenericComponent
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.definitions.effects import (
    EffectKind,
    EffectSpec,
    UnlockKind,
    UnlockSpec,
)
from genshin_sim.core.contracts.phases import FramePhase, MountPoint
from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.systems.aura_icd import IcdDefinition


def _effect(effect_key: str) -> EffectSpec:
    return EffectSpec(
        effect_key=effect_key,
        kind=EffectKind.PASSIVE,
        unlock=UnlockSpec(kind=UnlockKind.ALWAYS, threshold=0),
    )


def _slice() -> Any:
    """返回可塞入任意切片占位参数的值。"""

    return object()


def test_character_unit_requires_slot():
    with pytest.raises(ContentUnitValidationError, match="slot"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key="character:1",
            handler_key="character.barbara",
            version="dev-m0",
        )


def test_weapon_unit_without_slot_is_allowed():
    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key="weapon:1",
        handler_key="weapon.test",
        version="dev-m0",
    )

    assert unit.slot is None


def test_reaction_capabilities_require_character_and_slot():
    with pytest.raises(ContentUnitValidationError, match="角色"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.WEAPON,
            owner_key="weapon:1",
            handler_key="weapon.test",
            version="dev-m0",
            slot=1,
            reaction_capabilities=("capability.test",),
        )

    with pytest.raises(ContentUnitValidationError, match="slot"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key="character:1",
            handler_key="character.test",
            version="dev-m0",
            slot=None,
            reaction_capabilities=("capability.test",),
        )

    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:1",
        handler_key="character.test",
        version="dev-m0",
        slot=1,
        reaction_capabilities=("capability.test",),
    )
    assert unit.reaction_capabilities == ("capability.test",)


def test_effect_keys_must_be_unique():
    with pytest.raises(ContentUnitValidationError, match="effect_key"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key="character:1",
            handler_key="character.test",
            version="dev-m0",
            slot=1,
            effects=(_effect("effect.dup"), _effect("effect.dup")),
        )


def test_aura_icd_definitions_must_be_icd_definition():
    with pytest.raises(ContentUnitValidationError, match="aura_icd_definitions"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key="character:1",
            handler_key="character.test",
            version="dev-m0",
            slot=1,
            aura_icd_definitions=(_slice(),),
        )

    definition = IcdDefinition("icd.test.ring", 90, (AuraAmount.one(),))
    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:1",
        handler_key="character.test",
        version="dev-m0",
        slot=1,
        aura_icd_definitions=(definition,),
    )

    assert unit.aura_icd_definitions == (definition,)


def test_mount_points_must_be_unique():
    mount = MountPoint(phase=FramePhase.INPUT_INTERPRET, key="na.1", kind="interpreter")

    with pytest.raises(ContentUnitValidationError, match="mount_points"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key="character:1",
            handler_key="character.test",
            version="dev-m0",
            slot=1,
            mount_points=(mount, mount),
        )


def test_compiled_params_must_be_json_compatible():
    bad_params: Any = {"bad": (1, 2)}

    with pytest.raises(TypeError, match="compiled_params"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key="character:1",
            handler_key="character.test",
            version="dev-m0",
            slot=1,
            compiled_params=bad_params,
        )


def test_unit_freezes_sequences():
    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:1",
        handler_key="character.test",
        version="dev-m0",
        slot=1,
        actions=[_slice()],
        effects=[_effect("effect.test")],
        mount_points=[MountPoint(phase=FramePhase.INPUT_INTERPRET, key="na.1", kind="interpreter")],
    )

    assert len(unit.actions) == 1
    assert len(unit.effects) == 1
    assert len(unit.mount_points) == 1


def test_unit_can_wrap_generic_component_in_effect():
    component = GenericComponent(
        kind="talent_level_boost",
        params={"skill": "elemental_skill", "amount": 3},
    )
    effect = EffectSpec(
        effect_key="character.barbara.c3",
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=3),
        component=component,
    )

    assert effect.component is component


def test_character_unit_accepts_runtime_slices():
    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:1",
        handler_key="character.test",
        version="dev-m3",
        slot=1,
        action_interpreter=_slice(),
        impact_factories={"impact.test": _slice()},
        created_object_behaviors={"created.test": _slice()},
        event_hooks=[_slice()],
        attribute_definitions=[_slice()],
        damage_modifier_providers=[_slice()],
    )

    assert len(unit.impact_factories) == 1
    assert len(unit.event_hooks) == 1
    assert len(unit.attribute_definitions) == 1


def test_action_interpreter_requires_character_and_slot():
    with pytest.raises(ContentUnitValidationError, match="角色"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.WEAPON,
            owner_key="weapon:1",
            handler_key="weapon.test",
            version="dev-m3",
            slot=1,
            action_interpreter=_slice(),
        )
    with pytest.raises(ContentUnitValidationError, match="slot"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key="character:1",
            handler_key="character.test",
            version="dev-m3",
            slot=None,
            action_interpreter=_slice(),
        )


def test_created_object_behaviors_require_character():
    with pytest.raises(ContentUnitValidationError, match="角色"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.ARTIFACT,
            owner_key="artifact_set:1",
            handler_key="artifact.test",
            version="dev-m3",
            slot=1,
            created_object_behaviors={"created.test": _slice()},
        )


def test_impact_factory_keys_must_be_non_empty():
    with pytest.raises(ContentUnitValidationError, match="impact_factories"):
        ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key="character:1",
            handler_key="character.test",
            version="dev-m3",
            slot=1,
            impact_factories={"": _slice()},
        )
