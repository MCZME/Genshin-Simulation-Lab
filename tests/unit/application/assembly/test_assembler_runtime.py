"""test_assembler_runtime.py 测试。"""

from __future__ import annotations

import pytest

from genshin_sim.application.assembly import (
    SimulationAssembler,
)
from genshin_sim.assets.models import (
    CharacterAsset,
    CharacterLevelStats,
)
from genshin_sim.core.attributes import (
    RESISTANCE_HYDRO,
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    AttributeQuery,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.snapshots import export_snapshot
from genshin_sim.core.space import SpatialEntityKind
from genshin_sim.core.systems.healing import HealingRequest, HealingRequestHandler
from genshin_sim.core.systems.health import (
    CharacterDamageApplication,
    HealthChangeKind,
    UnsupportedHealthSubjectError,
)
from tests.helpers.assembly import (
    minimal_config,
    reordered_two_slot_config,
)
from tests.helpers.asset_repository import FakeAssetRepository


class SlotAwareAssetRepository(FakeAssetRepository):
    def __init__(self) -> None:
        super().__init__(
            characters=(
                CharacterAsset(
                    asset_key="character:pyro",
                    source_id="pyro",
                    name="Pyro",
                    element="pyro",
                    weapon_type="sword",
                    rarity=4,
                    burst_energy_cost=40.0,
                    handler_key="generic.test_character",
                ),
                CharacterAsset(
                    asset_key="character:electro",
                    source_id="electro",
                    name="Electro",
                    element="electro",
                    weapon_type="sword",
                    rarity=5,
                    burst_energy_cost=80.0,
                    handler_key="generic.test_character",
                ),
            ),
            effect_payloads=(),
        )


def test_assembler_builds_minimal_runtime_graph():
    assembler = SimulationAssembler(FakeAssetRepository())
    assembled = assembler.assemble(minimal_config())

    assert assembled.context.space_runtime is assembled.space_runtime
    player = assembled.space_runtime.get_entity("player:active")
    target = assembled.space_runtime.get_entity("target:target_1")
    assert player is not None
    assert player.kind is SpatialEntityKind.ACTIVE_CHARACTER
    assert player.position.x == 1
    assert player.active_slot == 1
    assert target is not None
    assert target.kind is SpatialEntityKind.TARGET
    runtime_target = assembled.space_runtime.targets.get("target_1")
    assert runtime_target is not None
    assert runtime_target.level == 90
    assert runtime_target.resistance == {"hydro": 0.1}
    assert not hasattr(runtime_target, "health")
    assert assembled.space_runtime.team_state.current_character.character_key == "character:75"
    assert assembled.space_runtime.team_state.current_character.health.current_hp == 10000
    assert assembled.simulator.max_frames == 10
    assert assembled.action_manager.is_idle()
    assert assembled.action_registry.action_keys == ("team.switch",)
    assert assembled.impact_dispatcher.factory_keys == ()
    assert assembled.space_runtime.created_object_runtime.behavior_keys == ()
    assert assembled.runtime_world.updatables == (
        assembled.buff_runtime,
        assembled.infusion_runtime,
        assembled.shield_runtime,
        assembled.elemental_settlement_coordinator,
        assembled.cooldown_frame_adapter,
        assembled.movement_runtime,
        assembled.resonance_runtime,
        assembled.action_manager,
        assembled.impact_runtime,
        assembled.energy_runtime,
        assembled.space_runtime,
        assembled.moonsign_runtime,
        assembled.resonance_reaction_stage,
        assembled.hook_dispatcher,
    )
    assert assembled.resonance_store.active_keys == ()
    assert assembled.resonance_runtime.store is assembled.resonance_store
    assert assembled.moonsign_runtime.store is assembled.moonsign_store
    assert assembled.moonsign_runtime.level.value == "none"


def test_assembler_matches_energy_profiles_by_slot_not_team_input_order():
    assembled = SimulationAssembler(SlotAwareAssetRepository()).assemble(
        reordered_two_slot_config()
    )

    slot_one = assembled.energy_store.require_profile(
        AttributeSubjectRef.character("character:slot_1")
    )
    slot_two = assembled.energy_store.require_profile(
        AttributeSubjectRef.character("character:slot_2")
    )

    assert [bundle.slot for bundle in assembled.assets] == [2, 1]
    assert (slot_one.character_key, slot_one.element.value, slot_one.capacity) == (
        "character:pyro",
        "pyro",
        40.0,
    )
    assert (slot_two.character_key, slot_two.element.value, slot_two.capacity) == (
        "character:electro",
        "electro",
        80.0,
    )


def test_assembler_routes_structured_energy_impact_and_settles_pickup():
    assembler = SimulationAssembler(FakeAssetRepository())
    assembled = assembler.assemble(minimal_config())

    request = ImpactRequest(
        frame=3,
        kind=ImpactKind.ENERGY,
        impact_key="test.energy.pickup",
        owner_slot=1,
        request_id="energy:pickup:1",
        params={
            "energy": {
                "schema_version": 1,
                "operation": "spawn_pickup",
                "pickup_kind": "particle",
                "element": "hydro",
                "count": 1,
                "travel_frames": 0,
            }
        },
    )

    assembled.impact_request_dispatcher.dispatch_requests(assembled.context, (request,))
    assembled.energy_runtime.update_frame(assembled.context, 3)

    restore_request = ImpactRequest(
        frame=4,
        kind=ImpactKind.ENERGY,
        impact_key="test.energy.restore",
        request_id="energy:restore:1",
        target_refs=("character:slot_1",),
        params={
            "energy": {
                "schema_version": 1,
                "operation": "restore",
                "amount": 4.0,
            }
        },
    )
    assembled.impact_request_dispatcher.dispatch_requests(assembled.context, (restore_request,))

    ref = AttributeSubjectRef.character("character:slot_1")
    assert assembled.energy_runtime.get_current_energy(ref) == 7.0
    assert assembled.energy_transit_queue.is_empty()
    assert export_snapshot(assembled.context).to_dict()["energy"] == {
        "frame": 0,
        "characters": (
            {
                "character_ref": {"kind": "character", "entity_id": "character:slot_1"},
                "character_key": "character:75",
                "element": "hydro",
                "current_energy": 7.0,
                "capacity": 60.0,
                "burst_ready": False,
            },
        ),
        "pending_pickups": (),
    }
    assert [event.event_type for event in assembled.context.events.frame_events] == [
        EventType.ENERGY_PICKUP_SPAWNED,
        EventType.ENERGY_PICKUP_SETTLED,
        EventType.CHARACTER_ENERGY_CHANGED,
        EventType.DIRECT_ENERGY_CHANGE_RESOLVED,
        EventType.CHARACTER_ENERGY_CHANGED,
    ]
    assert assembled.buff_definitions == ()
    assert assembled.buff_runtime.buff_store is assembled.buff_store
    assert assembled.buff_handler.runtime is assembled.buff_runtime
    assert assembled.impact_request_dispatcher.buff_handler is assembled.buff_handler
    assert assembled.shield_runtime.shield_store is assembled.shield_store
    assert assembled.shield_handler.runtime is assembled.shield_runtime
    assert assembled.character_damage_taken_coordinator.shield_port is assembled.shield_runtime
    character_ref = AttributeSubjectRef.character("character:slot_1")
    target_ref = AttributeSubjectRef.target("target:target_1")
    assert assembled.health_runtime.get_current_hp(character_ref) == 10000
    assert assembled.health_runtime.get_max_hp(character_ref, frame=0) == 10000
    assert assembled.health_runtime.get_hp_ratio(character_ref, frame=0) == 1.0
    assert isinstance(assembled.healing_handler, HealingRequestHandler)
    assert assembled.healing_handler.health_runtime is assembled.health_runtime
    assert assembled.healing_handler.event_engine is assembled.context.events
    assert assembled.context.get_system("HealingRequestHandler") is assembled.healing_handler
    assert assembled.context.get_system("BuffRuntime") is assembled.buff_runtime
    assert assembled.context.get_system("BuffImpactRequestHandler") is assembled.buff_handler
    with pytest.raises(UnsupportedHealthSubjectError):
        assembled.health_runtime.get_current_hp(target_ref)
    assert (
        assembled.attribute_runtime.resolver.resolve(
            AttributeQuery(character_ref, STAT_ATK_BASE, frame=0)
        ).final_value
        == 1500
    )
    assert (
        assembled.attribute_runtime.resolver.resolve(
            AttributeQuery(character_ref, STAT_ATK_TOTAL, frame=0)
        ).final_value
        == 1500
    )
    assert (
        assembled.attribute_runtime.resolver.resolve(
            AttributeQuery(target_ref, RESISTANCE_HYDRO, frame=0)
        ).final_value
        == 0.1
    )
    assert assembled.context.get_system("AttributeResolver") is assembled.attribute_runtime.resolver


def test_assembler_healing_handler_runs_real_single_target_loop():
    assembled = SimulationAssembler(FakeAssetRepository()).assemble(minimal_config())
    character_ref = AttributeSubjectRef.character("character:slot_1")
    source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, "assembler.healing")

    assembled.health_runtime.apply_damage(
        CharacterDamageApplication(
            change_id="damage:setup",
            frame=0,
            target_ref=character_ref,
            amount=500,
            source_ref=character_ref,
            source_context=source_context,
        )
    )
    assembled.context.events.clear_frame_events()

    record = assembled.healing_handler.handle(
        HealingRequest(
            healing_id="healing:assembled:1",
            frame=1,
            source_ref=character_ref,
            target_ref=character_ref,
            flat_healing=250,
            source_context=source_context,
            tags=frozenset({"assembler"}),
        )
    )

    assert record.result.final_healing == 250
    assert record.health_result.change_kind is HealthChangeKind.HEALING
    assert record.health_result.effective_amount == 250
    assert assembled.health_runtime.get_current_hp(character_ref) == 9750
    assert assembled.space_runtime.team_state.current_character.health.current_hp == 9750
    assert [event.event_type for event in assembled.context.events.frame_events] == [
        EventType.HEALING_RESOLVED,
        EventType.CHARACTER_HEALTH_CHANGED,
    ]
    assert assembled.healing_handler.records == (record,)


def test_assembler_initializes_character_health_from_final_max_hp():
    class RuntimeRepository(FakeAssetRepository):
        def get_character_level_stats(
            self,
            character_key: str,
            level: int,
            *,
            ascended: bool = True,
        ):
            stats = super().get_character_level_stats(
                character_key,
                level,
                ascended=ascended,
            )
            return CharacterLevelStats(
                character_key=stats.character_key,
                level=stats.level,
                ascension_phase=stats.ascension_phase,
                base_hp=10000,
                base_atk=stats.base_atk,
                base_def=stats.base_def,
                ascension_stat="hp_percent",
                ascension_value=0.2,
            )

    assembled = SimulationAssembler(RuntimeRepository()).assemble(minimal_config())
    character_ref = AttributeSubjectRef.character("character:slot_1")

    assert assembled.health_runtime.get_current_hp(character_ref) == 12000
    assert assembled.space_runtime.team_state.current_character.health.current_hp == 12000
    assert assembled.context.get_system("HealthRuntime") is assembled.health_runtime
