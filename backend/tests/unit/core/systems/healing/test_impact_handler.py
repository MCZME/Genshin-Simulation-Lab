from __future__ import annotations

from dataclasses import replace

from genshin_sim.core.attributes import (
    STAT_HP_BASE,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.entity_states import HealthState
from genshin_sim.core.events import EventEngine
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.impacts.runtime import ImpactRequestDispatcher
from genshin_sim.core.systems.healing import (
    HealingImpactRequestHandler,
    HealingRequestHandler,
    HealingResolver,
)
from genshin_sim.core.systems.health import (
    CharacterHealthStore,
    HealthRuntime,
)

SOURCE_REF = AttributeSubjectRef.character("character:slot_1")
OTHER_REF = AttributeSubjectRef.character("character:slot_2")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONTENT, "barbara.elemental_skill")


class _CharacterStub:
    def __init__(self, combat_entity_id: str) -> None:
        self.combat_entity_id = combat_entity_id


class _TeamStub:
    def __init__(self, active_entity_id: str) -> None:
        self.current_character = _CharacterStub(active_entity_id)


class _SpaceStub:
    def __init__(self, active_entity_id: str) -> None:
        self.team_state = _TeamStub(active_entity_id)


class _Context:
    def __init__(self, active_entity_id: str = "character:slot_1") -> None:
        self.space_runtime = _SpaceStub(active_entity_id)


def _attribute_resolver(*, hp: float = 1000.0) -> AttributeResolver:
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    SOURCE_REF,
                    BaseAttributeContribution(STAT_HP_BASE, hp, SOURCE_CONTEXT),
                ),
                (
                    OTHER_REF,
                    BaseAttributeContribution(STAT_HP_BASE, hp, SOURCE_CONTEXT),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _impact_handler(
    *,
    current_hp: float = 500.0,
) -> tuple[HealingImpactRequestHandler, HealthState]:
    health = HealthState(current_hp)
    events = EventEngine()
    resolver = _attribute_resolver()
    health_runtime = HealthRuntime(
        resolver,
        CharacterHealthStore(
            (
                (SOURCE_REF, health),
                (OTHER_REF, HealthState(current_hp)),
            )
        ),
        events,
    )
    handler = HealingRequestHandler(HealingResolver(resolver), health_runtime)
    return HealingImpactRequestHandler(handler), health


def _heal_request(
    *,
    anchor_entity_id: str = "player:active",
    target_refs: tuple[str, ...] = (),
    owner_slot: int = 1,
) -> ImpactRequest:
    return ImpactRequest(
        frame=6,
        kind=ImpactKind.HEAL,
        impact_key="barbara.elemental_skill.heal",
        owner_slot=owner_slot,
        request_id="impact:barbara:heal",
        anchor_entity_id=anchor_entity_id,
        target_refs=target_refs,
        params={
            "heal": {
                "healing_id": "barbara.elemental_skill.heal",
                "scaling_terms": (
                    {
                        "component_key": "持续治疗量:ratio",
                        "attribute_key": "stat.hp.max",
                        "coefficient": 0.1,
                    },
                ),
                "flat_healing": 5.0,
                "source_context": {
                    "kind": "content",
                    "source_key": "barbara.elemental_skill",
                },
                "tags": ("barbara.ring",),
            }
        },
    )


def test_healing_impact_handler_resolves_active_character_anchor():
    handler, health = _impact_handler()

    records = handler.handle_impact_request(_Context(), _heal_request())

    assert len(records) == 1
    assert records[0].result.final_healing == 105
    assert health.current_hp == 605
    assert handler.records[0].healing_requests[0].target_ref == SOURCE_REF


def test_healing_impact_handler_fans_out_explicit_target_refs():
    handler, health = _impact_handler()

    records = handler.handle_impact_request(
        _Context(),
        _heal_request(target_refs=("character:slot_1", "character:slot_2")),
    )

    assert len(records) == 2
    assert [record.result.target_ref for record in records] == [SOURCE_REF, OTHER_REF]
    assert health.current_hp == 605


def test_healing_impact_handler_rejects_missing_contract():
    handler, _ = _impact_handler()
    request = replace(_heal_request(), params={})

    assert not handler.has_heal_contract(request)


def test_dispatcher_routes_heal_request_to_impact_handler():
    handler, health = _impact_handler()
    dispatcher = ImpactRequestDispatcher(healing_handler=handler)

    dispatcher.dispatch_requests(_Context(), (_heal_request(),))

    assert health.current_hp == 605
    assert dispatcher.healing_records[0].healing_requests[0].target_ref == SOURCE_REF


def test_dispatcher_ignores_heal_without_handler():
    dispatcher = ImpactRequestDispatcher()

    dispatcher.dispatch_requests(_Context(), (_heal_request(),))

    assert dispatcher.ignored_requests[-1].reason == "治疗请求处理器尚未接入"
