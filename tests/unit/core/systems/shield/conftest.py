from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from genshin_sim.core.attributes import (
    BONUS_SHIELD_STRENGTH,
    STAT_DEF_BASE,
    STAT_HP_BASE,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
    create_public_attribute_registry,
)
from genshin_sim.core.entity_states import CharacterRuntimeState, HealthState
from genshin_sim.core.events import EventEngine
from genshin_sim.core.mechanics import MechanicRuntime
from genshin_sim.core.simulation import TeamRuntimeState
from genshin_sim.core.systems.health import CharacterHealthStore, HealthRuntime
from genshin_sim.core.systems.shield import (
    ShieldCapacityFormula,
    ShieldComponentStore,
    ShieldElement,
    ShieldGrantPolicy,
    ShieldGrantRequest,
    ShieldProtectionRef,
    ShieldResolver,
    ShieldRuntime,
)

CHARACTER_A = AttributeSubjectRef.character("character:slot_1")
CHARACTER_B = AttributeSubjectRef.character("character:slot_2")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONTENT, "test.shield")
PROTECTION_REF = ShieldProtectionRef.active_team()


@dataclass(slots=True)
class ShieldTestRig:
    runtime: ShieldRuntime
    mechanic_runtime: MechanicRuntime
    component_store: ShieldComponentStore
    health_runtime: HealthRuntime
    event_engine: EventEngine
    team_state: TeamRuntimeState
    character_a: CharacterRuntimeState
    character_b: CharacterRuntimeState


def build_rig(
    *,
    shield_strength_a: float = 0.0,
    shield_strength_b: float = 0.0,
    hp: float = 10_000.0,
) -> ShieldTestRig:
    registry = create_public_attribute_registry()
    source = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.base")
    base = BaseAttributeSet(
        (
            (CHARACTER_A, BaseAttributeContribution(STAT_HP_BASE, hp, source)),
            (CHARACTER_A, BaseAttributeContribution(STAT_DEF_BASE, 1_000.0, source)),
            (CHARACTER_B, BaseAttributeContribution(STAT_HP_BASE, hp, source)),
            (CHARACTER_B, BaseAttributeContribution(STAT_DEF_BASE, 1_500.0, source)),
        )
    )
    providers = tuple(
        _strength_provider(ref, value, slot)
        for ref, value, slot in (
            (CHARACTER_A, shield_strength_a, 1),
            (CHARACTER_B, shield_strength_b, 2),
        )
        if value != 0
    )
    attribute_resolver = AttributeResolver(
        definitions=registry,
        base_attributes=base,
        modifier_index=ModifierProviderIndex(providers, registry=registry),
    )
    character_a = CharacterRuntimeState(
        slot=1,
        character_key="character:test_a",
        level=90,
        health=HealthState(hp),
    )
    character_b = CharacterRuntimeState(
        slot=2,
        character_key="character:test_b",
        level=90,
        health=HealthState(hp),
    )
    team_state = TeamRuntimeState((character_a, character_b))
    health_store = CharacterHealthStore(
        (
            (CHARACTER_A, character_a.health),
            (CHARACTER_B, character_b.health),
        )
    )
    events = EventEngine()
    health_runtime = HealthRuntime(attribute_resolver, health_store, events)
    mechanic_runtime = MechanicRuntime()
    component_store = ShieldComponentStore()
    resolver = ShieldResolver(attribute_resolver)
    runtime = ShieldRuntime(
        resolver=resolver,
        mechanic_runtime=mechanic_runtime,
        component_store=component_store,
        attribute_resolver=attribute_resolver,
        health_runtime=health_runtime,
        event_engine=events,
        team_state=team_state,
    )
    return ShieldTestRig(
        runtime=runtime,
        mechanic_runtime=mechanic_runtime,
        component_store=component_store,
        health_runtime=health_runtime,
        event_engine=events,
        team_state=team_state,
        character_a=character_a,
        character_b=character_b,
    )


def grant_request(
    *,
    grant_id: str = "grant:1",
    frame: int = 1,
    mechanic_key: str = "test.shield",
    handler_key: str = "test.shield.handler",
    creator_ref: AttributeSubjectRef = CHARACTER_A,
    element: ShieldElement = ShieldElement.NONE,
    duration_frames: int = 60,
    flat_absorption: float = 1_000.0,
    grant_policy: ShieldGrantPolicy = ShieldGrantPolicy.REPLACE,
    conflict_key: str = "test.shield.conflict",
    capacity_limit: float | None = None,
) -> ShieldGrantRequest:
    return ShieldGrantRequest(
        grant_id=grant_id,
        frame=frame,
        mechanic_key=mechanic_key,
        handler_key=handler_key,
        protection_ref=PROTECTION_REF,
        creator_ref=creator_ref,
        source_context=SOURCE_CONTEXT,
        element=element,
        duration_frames=duration_frames,
        grant_formula=ShieldCapacityFormula(flat_absorption=flat_absorption),
        capacity_limit_formula=(
            None
            if capacity_limit is None
            else ShieldCapacityFormula(flat_absorption=capacity_limit)
        ),
        grant_policy=grant_policy,
        conflict_key=conflict_key,
    )


def _strength_provider(
    ref: AttributeSubjectRef,
    value: float,
    slot: int,
) -> StaticModifierProvider:
    provider_key = f"test.shield_strength.{slot}"
    term = ModifierTerm(
        target_key=BONUS_SHIELD_STRENGTH,
        stage=ModifierStage.FLAT_ADD,
        value=value,
        provider_key=provider_key,
        source_ref=SOURCE_CONTEXT,
    )
    return StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({BONUS_SHIELD_STRENGTH}),
            owner_ref=ref,
        ),
        (term,),
        subject_ref=ref,
    )


@pytest.fixture
def shield_rig() -> ShieldTestRig:
    return build_rig()


@pytest.fixture
def rig_factory() -> Callable[..., ShieldTestRig]:
    return build_rig


@pytest.fixture
def make_grant() -> Callable[..., ShieldGrantRequest]:
    return grant_request
