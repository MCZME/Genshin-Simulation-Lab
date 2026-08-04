from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from genshin_sim.application.assembly import (
    InvalidRuntimePayloadError,
    MissingRuntimeAssetError,
    MissingRuntimeHandlerError,
    SimulationAssembler,
)
from genshin_sim.application.assembly.attributes import build_attribute_runtime
from genshin_sim.application.config import SimulationConfig
from genshin_sim.assets import AssetDbInfo
from genshin_sim.assets.models import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    WeaponAsset,
    WeaponLevelStats,
)
from genshin_sim.content import ContentRuntimeContribution, create_default_registry
from genshin_sim.core.actions import (
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputSessionView,
    PreparedAction,
    TimedImpactAction,
)
from genshin_sim.core.attributes import (
    RESISTANCE_HYDRO,
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    STAT_CRIT_RATE,
    STAT_HP_MAX,
    AttributeDefinition,
    AttributeKey,
    AttributeQuery,
    AttributeSubjectKind,
    AttributeSubjectRef,
    AttributeVisibility,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    ProviderAttributeRead,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ActionImpactContext, ImpactKind, ImpactRequest
from genshin_sim.core.snapshots import export_snapshot
from genshin_sim.core.space import CreatedObjectRuntimeState, SpatialEntityKind
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.healing import HealingRequest, HealingRequestHandler
from genshin_sim.core.systems.health import (
    CharacterDamageApplication,
    HealthChangeKind,
    UnsupportedHealthSubjectError,
)


class BrokenRegistry:
    def create_character(self, request):
        del request
        raise LookupError("missing handler")

    def create_weapon(self, request):
        del request
        raise LookupError("missing handler")

    def create_artifact(self, request):
        del request
        raise LookupError("missing handler")

    def create_impact(self, request):
        del request
        raise LookupError("missing handler")


@dataclass(frozen=True, slots=True)
class CharacterContentState:
    charge: int


class ContributedActionInterpreter:
    supported_action_keys = ("character.runtime.skill",)

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key="character.runtime.skill",
                owner=ActionOwnerRef.character(session.owner.slot or 1),
                requested_start_frame=session.current_frame,
                source_session_id=session.session_id,
            )
        )


class MissingActionInterpreter:
    supported_action_keys = ("character.runtime.missing",)

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context, session
        return ActionInterpretationResult.wait()


class TestImpactFactory:
    def create_requests(self, context: ActionImpactContext):
        return (
            ImpactRequest(
                frame=context.frame,
                kind=ImpactKind.DAMAGE,
                impact_key=context.impact_key,
                owner_slot=context.owner.slot,
                action_key=context.action_key,
                source_impact_point_id=context.impact_point_id,
                params={"handled": True},
            ),
        )


class TestCreatedObjectBehavior:
    def create_tick_requests(self, state: CreatedObjectRuntimeState, frame: int):
        del state, frame
        return ()


class TestAttributeModifier:
    modifier_key = "modifier.test.crit_rate"
    owner_ref = "character:slot_1"
    targets = (str(STAT_CRIT_RATE),)
    scope = "attribute"
    priority = 0

    def evaluate(self, query, context):
        del query, context
        return (
            ModifierTerm(
                target_key=STAT_CRIT_RATE,
                stage=ModifierStage.FLAT_ADD,
                value=0.2,
                provider_key=self.modifier_key,
                source_ref=RuntimeSourceRef(RuntimeSourceKind.CONTENT, self.modifier_key),
            ),
        )


class FakeAssetRepository:
    def __init__(self) -> None:
        self.character = CharacterAsset(
            asset_key="character:75",
            source_id="75",
            name="test",
            element="hydro",
            weapon_type="sword",
            rarity=5,
            burst_energy_cost=60.0,
            handler_key="generic.test_character",
        )
        self.weapon = WeaponAsset(
            asset_key="weapon:11512",
            source_id="11512",
            name="test weapon",
            weapon_type="sword",
            rarity=5,
            handler_key="generic.test_weapon",
        )
        self.artifact_set = ArtifactSetAsset(
            asset_key="artifact_set:15032",
            source_id="15032",
            name="test set",
            handler_key="generic.test_artifact_set",
        )

    def get_meta(self) -> dict[str, str]:
        return {"schema_version": "2"}

    def get_info(self) -> AssetDbInfo:
        return AssetDbInfo(meta={"schema_version": "2"})

    def list_characters(self) -> tuple[CharacterAsset, ...]:
        return (self.character,)

    def get_character(self, character_key: str):
        assert character_key == self.character.asset_key
        return self.character

    def get_character_level_stats(
        self,
        character_key: str,
        level: int,
        *,
        ascended: bool = True,
    ):
        assert character_key == self.character.asset_key
        assert level == 90
        assert ascended
        return CharacterLevelStats(
            character_key=character_key,
            level=level,
            ascension_phase=6,
            base_hp=10000,
            base_atk=1000,
            base_def=700,
        )

    def list_weapons(self, weapon_type: str | None = None):
        del weapon_type
        return (self.weapon,)

    def get_weapon(self, weapon_key: str):
        assert weapon_key == self.weapon.asset_key
        return self.weapon

    def get_weapon_level_stats(
        self,
        weapon_key: str,
        level: int,
        *,
        ascended: bool = True,
    ):
        assert weapon_key == self.weapon.asset_key
        assert level == 90
        assert ascended
        return WeaponLevelStats(
            weapon_key=weapon_key,
            level=level,
            ascension_phase=6,
            base_atk=500,
        )

    def list_artifact_sets(self):
        return (self.artifact_set,)

    def get_artifact_set(self, artifact_set_key: str):
        assert artifact_set_key == self.artifact_set.asset_key
        return self.artifact_set

    def get_artifact_set_bonuses(self, artifact_set_key: str, piece_count: int | None = None):
        assert artifact_set_key == self.artifact_set.asset_key
        return (
            ArtifactSetBonus(
                artifact_set_key=artifact_set_key,
                piece_count=4,
                handler_key="generic.static_modifiers",
                params={"schema_version": 1},
            ),
        )

    def get_talent_scalings(self, character_key: str, talent_key: str):
        del character_key, talent_key
        return ()

    def get_effect_payloads(self, owner_key: str, effect_kind: str | None = None):
        del effect_kind
        if owner_key == self.character.asset_key:
            return (
                EffectPayload(
                    effect_key="effect:char",
                    owner_type="character",
                    owner_key=owner_key,
                    effect_kind="passive",
                    handler_key="generic.static_modifiers",
                    params={"schema_version": 1},
                ),
            )
        return ()


class SlotAwareAssetRepository(FakeAssetRepository):
    def __init__(self) -> None:
        super().__init__()
        self.characters = {
            "character:pyro": CharacterAsset(
                asset_key="character:pyro",
                source_id="pyro",
                name="Pyro",
                element="pyro",
                weapon_type="sword",
                rarity=4,
                burst_energy_cost=40.0,
                handler_key="generic.test_character",
            ),
            "character:electro": CharacterAsset(
                asset_key="character:electro",
                source_id="electro",
                name="Electro",
                element="electro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=80.0,
                handler_key="generic.test_character",
            ),
        }

    def list_characters(self) -> tuple[CharacterAsset, ...]:
        return tuple(self.characters.values())

    def get_character(self, character_key: str):
        return self.characters[character_key]

    def get_character_level_stats(
        self,
        character_key: str,
        level: int,
        *,
        ascended: bool = True,
    ):
        assert level == 90
        assert ascended
        return CharacterLevelStats(
            character_key=character_key,
            level=level,
            ascension_phase=6,
            base_hp=10000,
            base_atk=1000,
            base_def=700,
        )

    def get_effect_payloads(self, owner_key: str, effect_kind: str | None = None):
        del owner_key, effect_kind
        return ()


def _minimal_config(*, input_trace: list[dict[str, object]] | None = None) -> SimulationConfig:
    return SimulationConfig.from_mapping(
        {
            "schema_version": 1,
            "kind": "simulation_config",
            "meta": {"name": "demo", "description": ""},
            "team": [
                {
                    "slot": 1,
                    "character": {
                        "asset_key": "character:75",
                        "level": 90,
                        "constellation": 2,
                        "talents": {"normal_attack": 1},
                    },
                    "weapon": {
                        "asset_key": "weapon:11512",
                        "level": 90,
                        "refinement": 1,
                    },
                    "artifacts": {
                        "sets": [
                            {"asset_key": "artifact_set:15032", "pieces": 4},
                        ],
                        "stats": {},
                    },
                }
            ],
            "scene": {
                "player": {
                    "position": {"x": 1, "y": 0, "z": 2},
                    "facing": {"x": 0, "y": 0, "z": 1},
                },
                "targets": [
                    {
                        "id": "target_1",
                        "level": 90,
                        "position": {"x": 0, "y": 0, "z": 0},
                        "resistance": {"hydro": 0.1},
                    }
                ],
            },
            "input_trace": [] if input_trace is None else input_trace,
            "rules": {"enabled": []},
            "run_options": {"max_frames": 10},
        }
    )


def _reordered_two_slot_config() -> SimulationConfig:
    payload = _minimal_config().to_dict()
    payload["team"] = [
        {
            "slot": 2,
            "character": {
                "asset_key": "character:electro",
                "level": 90,
                "constellation": 0,
                "talents": {"normal_attack": 1},
            },
        },
        {
            "slot": 1,
            "character": {
                "asset_key": "character:pyro",
                "level": 90,
                "constellation": 0,
                "talents": {"normal_attack": 1},
            },
        },
    ]
    return SimulationConfig.from_mapping(payload)


def _skill_input_trace() -> list[dict[str, object]]:
    return [
        {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
        {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
    ]


def test_assembler_builds_minimal_runtime_graph():
    assembler = SimulationAssembler(FakeAssetRepository(), create_default_registry())
    assembled = assembler.assemble(_minimal_config())

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
        assembled.shield_runtime,
        assembled.elemental_settlement_coordinator,
        assembled.action_manager,
        assembled.impact_runtime,
        assembled.energy_runtime,
        assembled.space_runtime,
    )


def test_assembler_matches_energy_profiles_by_slot_not_team_input_order():
    assembled = SimulationAssembler(SlotAwareAssetRepository(), create_default_registry()).assemble(
        _reordered_two_slot_config()
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


def test_assembler_rejects_character_asset_without_burst_energy_cost():
    repository = FakeAssetRepository()
    repository.character = CharacterAsset(
        asset_key="character:75",
        source_id="75",
        name="test",
        element="hydro",
        weapon_type="sword",
        rarity=5,
        handler_key="generic.test_character",
    )

    with pytest.raises(InvalidRuntimePayloadError, match="缺少 burst_energy_cost"):
        SimulationAssembler(repository, create_default_registry()).assemble(_minimal_config())


def test_assembler_routes_structured_energy_impact_and_settles_pickup():
    assembler = SimulationAssembler(FakeAssetRepository(), create_default_registry())
    assembled = assembler.assemble(_minimal_config())

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
    assembled = SimulationAssembler(FakeAssetRepository(), create_default_registry()).assemble(
        _minimal_config()
    )
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


def test_assembler_injects_character_runtime_contribution_and_actions():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__()
            self.character = CharacterAsset(
                asset_key="character:75",
                source_id="75",
                name="test",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key="character.runtime",
            )

    interpreter = ContributedActionInterpreter()
    impact_factory = TestImpactFactory()
    created_object_behavior = TestCreatedObjectBehavior()
    registry = create_default_registry()
    registry.register_character_factory(
        "character.runtime",
        lambda request: ContentRuntimeContribution(
            owner_type="character",
            owner_key=request.character_key,
            handler_key=request.handler_key,
            slot=request.slot,
            action_interpreter=interpreter,
            actions=(
                TimedImpactAction(
                    action_key="character.runtime.skill",
                    duration_frames=1,
                    impact_keys=("impact.character_runtime",),
                ),
            ),
            state_extension=CharacterContentState(charge=2),
            impact_factories={"impact.character_runtime": impact_factory},
            created_object_behaviors={"created_object.character_runtime": created_object_behavior},
        ),
    )

    assembled = SimulationAssembler(RuntimeRepository(), registry).assemble(
        _minimal_config(input_trace=_skill_input_trace())
    )
    result = assembled.simulator.run()

    assert result.end_frame == 3
    assert assembled.content_bundle.action_interpreters == {1: interpreter}
    assert "character.runtime.skill" in assembled.action_registry.action_keys
    assert assembled.content_bundle.content_state_store.get_character_state(
        slot=1,
        handler_key="character.runtime",
        expected_type=CharacterContentState,
    ) == CharacterContentState(charge=2)
    assert assembled.impact_dispatcher.factory_keys == ("impact.character_runtime",)
    assert assembled.space_runtime.created_object_runtime.behavior_keys == (
        "created_object.character_runtime",
    )
    assert assembled.action_manager.decisions[0].action_key == "character.runtime.skill"
    assert assembled.action_manager.instances[0].impact_points[0].impact_key == (
        "impact.character_runtime"
    )


def test_assembler_injects_content_attribute_modifier_as_core_term():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__()
            self.character = CharacterAsset(
                asset_key="character:75",
                source_id="75",
                name="test",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key="character.attribute_modifier",
            )

    registry = create_default_registry()
    registry.register_character_factory(
        "character.attribute_modifier",
        lambda request: ContentRuntimeContribution(
            owner_type="character",
            owner_key=request.character_key,
            handler_key=request.handler_key,
            slot=request.slot,
            modifiers=(TestAttributeModifier(),),
        ),
    )

    assembled = SimulationAssembler(RuntimeRepository(), registry).assemble(_minimal_config())
    character_ref = AttributeSubjectRef.character("character:slot_1")
    resolution = assembled.attribute_runtime.resolver.resolve(
        AttributeQuery(character_ref, STAT_CRIT_RATE, frame=0)
    )

    assert resolution.final_value == 0.2
    assert resolution.applied_terms[0].provider_key == "modifier.test.crit_rate"
    target_resolution = assembled.attribute_runtime.resolver.resolve(
        AttributeQuery(
            AttributeSubjectRef.target("target:target_1"),
            STAT_CRIT_RATE,
            frame=0,
        )
    )
    assert target_resolution.final_value == 0.0


def test_assembler_injects_content_buff_definition_and_attribute_provider():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__()
            self.character = CharacterAsset(
                asset_key="character:75",
                source_id="75",
                name="test",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key="character.buff",
            )

    definition = BuffDefinition(
        definition_key="buff.assembler.atk",
        mechanic_key="mechanic.assembler.atk",
        handler_key="character.buff",
        conflict_key="buff.assembler.atk",
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key="assembler.atk.flat",
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({"assembler"}),
    )
    registry = create_default_registry()
    registry.register_character_factory(
        "character.buff",
        lambda request: ContentRuntimeContribution(
            owner_type="character",
            owner_key=request.character_key,
            handler_key=request.handler_key,
            slot=request.slot,
            buff_definitions=(definition,),
        ),
    )

    assembled = SimulationAssembler(RuntimeRepository(), registry).assemble(_minimal_config())
    character_ref = AttributeSubjectRef.character("character:slot_1")

    assert assembled.buff_definitions == (definition,)
    assert (
        assembled.attribute_runtime.resolver.resolve(
            AttributeQuery(character_ref, STAT_ATK_TOTAL, frame=1)
        ).final_value
        == 1500
    )

    assembled.impact_request_dispatcher.dispatch_requests(
        assembled.context,
        (
            ImpactRequest(
                frame=1,
                kind=ImpactKind.APPLY_STATUS,
                impact_key="impact.assembler.buff",
                owner_slot=1,
                request_id="impact:assembler:buff:1",
                target_refs=("character:slot_1",),
                params={
                    "buff": {
                        "definition_key": definition.definition_key,
                        "duration_frames": 10,
                        "modifier_values": ({"term_key": "assembler.atk.flat", "value": 200},),
                    }
                },
            ),
        ),
    )

    resolution = assembled.attribute_runtime.resolver.resolve(
        AttributeQuery(character_ref, STAT_ATK_TOTAL, frame=1)
    )
    assert resolution.final_value == 1700
    assert assembled.impact_request_dispatcher.buff_records[0].results[0].definition_key == (
        definition.definition_key
    )
    assert assembled.context.events.frame_events[-1].event_type is EventType.BUFF_APPLIED


def test_assembler_rejects_buff_definition_with_dynamic_hp_dependency_via_provider_reads():
    private_key = AttributeKey("character.buff.private_hp_seed")
    subject_ref = AttributeSubjectRef.character("character:slot_1")

    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__()
            self.character = CharacterAsset(
                asset_key="character:75",
                source_id="75",
                name="test",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key="character.buff",
            )

    provider_key = "character.buff.max_hp_from_private"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            reads=(ProviderAttributeRead(private_key),),
            writes=frozenset({STAT_HP_MAX}),
            private_namespace="character.buff",
            owner_ref=subject_ref,
        ),
        (
            ModifierTerm(
                target_key=STAT_HP_MAX,
                stage=ModifierStage.FLAT_ADD,
                value=0.0,
                provider_key=provider_key,
                source_ref=RuntimeSourceRef(RuntimeSourceKind.CONTENT, provider_key),
            ),
        ),
        subject_ref=subject_ref,
    )
    definition = BuffDefinition(
        definition_key="buff.assembler.private_hp",
        mechanic_key="mechanic.assembler.private_hp",
        handler_key="character.buff",
        conflict_key="buff.assembler.private_hp",
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key="assembler.private_hp.flat",
                target_key=private_key,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({"assembler"}),
    )
    registry = create_default_registry()
    registry.register_character_factory(
        "character.buff",
        lambda request: ContentRuntimeContribution(
            owner_type="character",
            owner_key=request.character_key,
            handler_key=request.handler_key,
            slot=request.slot,
            attribute_definitions=(
                AttributeDefinition(
                    key=private_key,
                    owner_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
                    policy_key="additive",
                    visibility=AttributeVisibility.CONTENT_PRIVATE,
                    namespace_owner="character.buff",
                ),
            ),
            attribute_providers=(provider,),
            buff_definitions=(definition,),
        ),
    )

    assembler = SimulationAssembler(RuntimeRepository(), registry)

    with pytest.raises(
        InvalidRuntimePayloadError,
        match="第一版不能动态影响 stat.hp.max",
    ):
        assembler.assemble(_minimal_config())


def test_assembler_rejects_buff_definition_with_unknown_attribute_target():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__()
            self.character = CharacterAsset(
                asset_key="character:75",
                source_id="75",
                name="test",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key="character.buff",
            )

    unknown_key = AttributeKey("character.buff.unknown")
    definition = BuffDefinition(
        definition_key="buff.assembler.unknown",
        mechanic_key="mechanic.assembler.unknown",
        handler_key="character.buff",
        conflict_key="buff.assembler.unknown",
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key="assembler.unknown.flat",
                target_key=unknown_key,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({"assembler"}),
    )
    registry = create_default_registry()
    registry.register_character_factory(
        "character.buff",
        lambda request: ContentRuntimeContribution(
            owner_type="character",
            owner_key=request.character_key,
            handler_key=request.handler_key,
            slot=request.slot,
            buff_definitions=(definition,),
        ),
    )

    assembler = SimulationAssembler(RuntimeRepository(), registry)

    with pytest.raises(InvalidRuntimePayloadError, match="写入未知属性"):
        assembler.assemble(_minimal_config())


def test_assembler_converts_buff_validation_error_raised_inside_content_factory():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__()
            self.character = CharacterAsset(
                asset_key="character:75",
                source_id="75",
                name="test",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key="character.buff",
            )

    def create_invalid_contribution(request) -> ContentRuntimeContribution:
        definition = BuffDefinition(
            definition_key="buff.assembler.invalid",
            mechanic_key="mechanic.assembler.invalid",
            handler_key=request.handler_key,
            conflict_key="buff.assembler.invalid",
            target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
            application_policy=BuffApplicationPolicy.REFRESH,
            value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
            max_stacks=0,
            marker_only=True,
        )
        return ContentRuntimeContribution(
            owner_type="character",
            owner_key=request.character_key,
            handler_key=request.handler_key,
            slot=request.slot,
            buff_definitions=(definition,),
        )

    registry = create_default_registry()
    registry.register_character_factory("character.buff", create_invalid_contribution)

    with pytest.raises(InvalidRuntimePayloadError, match="max_stacks"):
        SimulationAssembler(RuntimeRepository(), registry).assemble(_minimal_config())


def test_attribute_runtime_isolates_static_asset_modifiers_by_character_slot():
    @dataclass(frozen=True, slots=True)
    class AttributeAssetBundle:
        slot: int
        character_level_stats: CharacterLevelStats
        weapon_level_stats: WeaponLevelStats | None = None

    runtime = build_attribute_runtime(
        config=_minimal_config(),
        assets=(
            AttributeAssetBundle(
                slot=1,
                character_level_stats=CharacterLevelStats(
                    character_key="character:slot_1",
                    level=90,
                    ascension_phase=6,
                    base_hp=1000,
                    base_atk=100,
                    base_def=100,
                    ascension_stat="hp_percent",
                    ascension_value=0.2,
                ),
            ),
            AttributeAssetBundle(
                slot=2,
                character_level_stats=CharacterLevelStats(
                    character_key="character:slot_2",
                    level=90,
                    ascension_phase=6,
                    base_hp=2000,
                    base_atk=200,
                    base_def=200,
                    ascension_stat="hp_percent",
                    ascension_value=0.5,
                ),
            ),
        ),
        contributions=(),
    )

    slot_1 = runtime.resolver.resolve(
        AttributeQuery(AttributeSubjectRef.character("character:slot_1"), STAT_HP_MAX, frame=0)
    )
    slot_2 = runtime.resolver.resolve(
        AttributeQuery(AttributeSubjectRef.character("character:slot_2"), STAT_HP_MAX, frame=0)
    )

    assert slot_1.final_value == 1200
    assert slot_2.final_value == 3000


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

    assembled = SimulationAssembler(RuntimeRepository(), create_default_registry()).assemble(
        _minimal_config()
    )
    character_ref = AttributeSubjectRef.character("character:slot_1")

    assert assembled.health_runtime.get_current_hp(character_ref) == 12000
    assert assembled.space_runtime.team_state.current_character.health.current_hp == 12000
    assert assembled.context.get_system("HealthRuntime") is assembled.health_runtime


def test_assembler_registers_content_private_attribute_and_native_provider():
    private_key = AttributeKey("character.attribute_modifier.private_bonus")
    subject_ref = AttributeSubjectRef.character("character:slot_1")

    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__()
            self.character = CharacterAsset(
                asset_key="character:75",
                source_id="75",
                name="test",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key="character.attribute_modifier",
            )

    provider_key = "character.attribute_modifier.private_provider"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({private_key}),
            private_namespace="character.attribute_modifier",
            owner_ref=subject_ref,
        ),
        (
            ModifierTerm(
                target_key=private_key,
                stage=ModifierStage.FLAT_ADD,
                value=0.25,
                provider_key=provider_key,
                source_ref=RuntimeSourceRef(
                    RuntimeSourceKind.CONTENT,
                    "character.attribute_modifier",
                ),
            ),
        ),
        subject_ref=subject_ref,
    )
    registry = create_default_registry()
    registry.register_character_factory(
        "character.attribute_modifier",
        lambda request: ContentRuntimeContribution(
            owner_type="character",
            owner_key=request.character_key,
            handler_key=request.handler_key,
            slot=request.slot,
            attribute_definitions=(
                AttributeDefinition(
                    key=private_key,
                    owner_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
                    policy_key="additive",
                    visibility=AttributeVisibility.CONTENT_PRIVATE,
                    namespace_owner="character.attribute_modifier",
                ),
            ),
            attribute_providers=(provider,),
        ),
    )

    assembled = SimulationAssembler(RuntimeRepository(), registry).assemble(_minimal_config())
    resolution = assembled.attribute_runtime.resolver.resolve(
        AttributeQuery(subject_ref, private_key, frame=0)
    )

    assert resolution.final_value == 0.25


def test_assembler_rejects_action_interpreter_from_weapon():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__()
            self.weapon = WeaponAsset(
                asset_key="weapon:11512",
                source_id="11512",
                name="test weapon",
                weapon_type="sword",
                rarity=5,
                handler_key="weapon.bad_action_interpreter",
            )

    registry = create_default_registry()
    registry.register_weapon_factory(
        "weapon.bad_action_interpreter",
        lambda request: ContentRuntimeContribution(
            owner_type="weapon",
            owner_key=request.weapon_key,
            handler_key=request.handler_key,
            slot=request.slot,
            action_interpreter=ContributedActionInterpreter(),
        ),
    )

    assembler = SimulationAssembler(RuntimeRepository(), registry)

    with pytest.raises(InvalidRuntimePayloadError, match="只有角色内容可以贡献动作解释器"):
        assembler.assemble(_minimal_config())


def test_assembler_rejects_missing_character_interpreter_when_action_input_exists():
    assembler = SimulationAssembler(FakeAssetRepository(), create_default_registry())

    with pytest.raises(InvalidRuntimePayloadError, match="动作输入需要队伍槽位提供动作解释器"):
        assembler.assemble(_minimal_config(input_trace=_skill_input_trace()))


def test_assembler_rejects_interpreter_declared_action_without_registered_action():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__()
            self.character = CharacterAsset(
                asset_key="character:75",
                source_id="75",
                name="test",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key="character.runtime",
            )

    registry = create_default_registry()
    registry.register_character_factory(
        "character.runtime",
        lambda request: ContentRuntimeContribution(
            owner_type="character",
            owner_key=request.character_key,
            handler_key=request.handler_key,
            slot=request.slot,
            action_interpreter=MissingActionInterpreter(),
        ),
    )

    assembler = SimulationAssembler(RuntimeRepository(), registry)

    with pytest.raises(InvalidRuntimePayloadError, match="声明了未注册 action"):
        assembler.assemble(_minimal_config(input_trace=_skill_input_trace()))


def test_assembler_rejects_created_object_behavior_from_weapon():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__()
            self.weapon = WeaponAsset(
                asset_key="weapon:11512",
                source_id="11512",
                name="test weapon",
                weapon_type="sword",
                rarity=5,
                handler_key="weapon.bad_created_object",
            )

    registry = create_default_registry()
    registry.register_weapon_factory(
        "weapon.bad_created_object",
        lambda request: ContentRuntimeContribution(
            owner_type="weapon",
            owner_key=request.weapon_key,
            handler_key=request.handler_key,
            slot=request.slot,
            created_object_behaviors={"created_object.bad": TestCreatedObjectBehavior()},
        ),
    )

    assembler = SimulationAssembler(RuntimeRepository(), registry)

    with pytest.raises(
        InvalidRuntimePayloadError,
        match="只有角色内容可以贡献内容创建对象行为",
    ):
        assembler.assemble(_minimal_config())


def test_assembler_raises_for_missing_asset():
    class BrokenRepository(FakeAssetRepository):
        def get_character(self, character_key: str):
            raise LookupError(character_key)

    assembler = SimulationAssembler(BrokenRepository(), create_default_registry())

    with pytest.raises(MissingRuntimeAssetError):
        assembler.assemble(_minimal_config())


def test_assembler_raises_for_missing_handler():
    assembler = SimulationAssembler(FakeAssetRepository(), cast(Any, BrokenRegistry()))

    with pytest.raises(MissingRuntimeHandlerError):
        assembler.assemble(_minimal_config())
