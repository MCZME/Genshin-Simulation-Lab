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
    ActionInterpretation,
    ActionInterpretationTrigger,
    ActionTimelineSpec,
    SpatialQuery,
)
from genshin_sim.core.impacts import ImpactRequest
from genshin_sim.core.simulation import InputState, KeyEvent, KeyEventDispatch, KeyPhase
from genshin_sim.core.space import CreatedObjectRuntimeState, SpatialEntityKind, Vector3


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
    def interpret(self, context, session, trigger):
        del context
        if trigger is ActionInterpretationTrigger.PRESS:
            return ActionInterpretation.defer()
        if session.release_frame is None:
            return ActionInterpretation.reject("missing release frame")
        return ActionInterpretation.schedule(
            ActionTimelineSpec(
                action_key="character.runtime.skill",
                source_key=session.key,
                owner_slot=session.owner_slot_at_press,
                start_frame=session.release_frame,
                duration_frames=2,
                impact_keys=("impact.character_runtime",),
            )
        )


class TestImpactFactory:
    def create_impact_requests(self, request: ImpactRequest):
        return (request,)


class TestCreatedObjectBehavior:
    def create_tick_requests(self, state: CreatedObjectRuntimeState, frame: int):
        del state, frame
        return ()


class FakeAssetRepository:
    def __init__(self) -> None:
        self.character = CharacterAsset(
            asset_key="character:75",
            source_id="75",
            name="test",
            element="hydro",
            weapon_type="sword",
            rarity=5,
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
        return {"schema_version": "1"}

    def get_info(self) -> AssetDbInfo:
        return AssetDbInfo(meta={"schema_version": "1"})

    def list_characters(self):
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
        return ()

    def get_effect_payloads(self, owner_key: str, effect_kind: str | None = None):
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


def _minimal_config() -> SimulationConfig:
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
            "input_trace": [
                {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
                {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
            ],
            "rules": {"enabled": []},
            "run_options": {"max_frames": 10},
        }
    )


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
    assert (
        assembled.space_runtime.targets.get_by_spatial_entity_id("target:target_1")
        is runtime_target
    )
    assert assembled.space_runtime.team_state.current_character.character_key == "character:75"
    assert assembled.space_runtime.team_state.current_character.level == 90
    assert assembled.space_runtime.team_state.current_character.constellation == 2
    assert assembled.space_runtime.team_state.current_character.talent_levels == {
        "normal_attack": 1
    }
    assert assembled.simulator.max_frames == 10
    assert assembled.action_manager.is_idle()
    assert assembled.content_bundle.contributions == ()
    assert assembled.impact_dispatcher.factory_keys == ()
    assert assembled.space_runtime.created_object_runtime.behavior_keys == ()
    assert assembled.space_runtime.consumer_keys == (("player:active", "team.switch"),)
    assert assembled.team_switch_consumer.results == ()
    assert assembled.runtime_world.updatables[-1] is assembled.impact_runtime
    assert assembled.runtime_world.updatables[-2] is assembled.space_runtime


def test_assembler_injects_character_runtime_contribution():
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
            state_extension=CharacterContentState(charge=2),
            impact_factories={"impact.character_runtime": impact_factory},
            created_object_behaviors={"created_object.character_runtime": created_object_behavior},
        ),
    )

    assembled = SimulationAssembler(RuntimeRepository(), registry).assemble(_minimal_config())
    result = assembled.simulator.run()

    assert result.end_frame == 4
    assert assembled.content_bundle.action_interpreters == {1: interpreter}
    assert assembled.content_bundle.content_state_store.get_character_state(
        slot=1,
        handler_key="character.runtime",
        expected_type=CharacterContentState,
    ) == CharacterContentState(charge=2)
    assert assembled.impact_dispatcher.factory_keys == ("impact.character_runtime",)
    assert assembled.space_runtime.created_object_runtime.behavior_keys == (
        "created_object.character_runtime",
    )
    assert assembled.action_manager.decisions[0].timeline.action_key == "character.runtime.skill"
    assert assembled.action_manager.instances[0].impact_points[0].impact_key == (
        "impact.character_runtime"
    )


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


def test_assembled_action_manager_resolves_candidate_target_refs():
    assembler = SimulationAssembler(FakeAssetRepository(), create_default_registry())
    assembled = assembler.assemble(_minimal_config())

    decision = assembled.action_manager.schedule_timeline(
        assembled.context,
        ActionTimelineSpec(
            action_key="keyboard.e",
            owner_slot=1,
            start_frame=1,
            spatial_query=SpatialQuery(origin=Vector3(), radius=1),
        ),
    )

    assert decision.instance is not None
    assert decision.instance.candidate_entity_ids == ("target:target_1",)
    assert [
        (target.spatial_entity_id, target.target_id)
        for target in decision.instance.candidate_targets
    ] == [("target:target_1", "target_1")]
    assert len(decision.instance.impact_points) == 1
    impact_point = decision.instance.impact_points[0]
    assert impact_point.frame == 1
    assert impact_point.impact_key == "keyboard.e"
    assert impact_point.candidate_entity_ids == ("target:target_1",)
    assert [
        (target.spatial_entity_id, target.target_id) for target in impact_point.candidate_targets
    ] == [("target:target_1", "target_1")]


def test_assembled_action_manager_keeps_team_and_space_active_slot_in_sync():
    config = SimulationConfig.from_mapping(
        {
            **_minimal_config().to_dict(),
            "team": [
                _minimal_config().to_dict()["team"][0],
                {
                    "slot": 2,
                    "character": {
                        "asset_key": "character:75",
                        "level": 90,
                        "constellation": 0,
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
                },
            ],
        }
    )
    assembler = SimulationAssembler(FakeAssetRepository(), create_default_registry())
    assembled = assembler.assemble(config)

    assembled.team_action_controller.handle_key_event(
        assembled.context,
        KeyEventDispatch(
            frame=1,
            event=KeyEvent("keyboard.2", KeyPhase.PRESS),
        ),
        InputState(),
    )
    assert assembled.space_runtime.team_state.active_slot == 1

    assembled.space_runtime.update_frame(assembled.context, frame=1)

    player = assembled.space_runtime.get_entity("player:active")
    assert assembled.space_runtime.team_state.active_slot == 2
    assert assembled.space_runtime.team_state.current_character.slot == 2
    assert player is not None
    assert player.active_slot == 2
    assert assembled.team_switch_consumer.results[0].accepted
    assert assembled.action_manager.consumption_records[0].status == "switched"


def test_assembler_raises_for_missing_asset():
    class BrokenRepository(FakeAssetRepository):
        def get_character(self, character_key: str):
            raise LookupError(character_key)

    assembler = SimulationAssembler(BrokenRepository(), create_default_registry())

    with pytest.raises(MissingRuntimeAssetError):
        assembler.assemble(_minimal_config())


def test_assembler_raises_for_missing_handler():
    assembler = SimulationAssembler(
        FakeAssetRepository(),
        cast(Any, BrokenRegistry()),
    )

    with pytest.raises(MissingRuntimeHandlerError):
        assembler.assemble(_minimal_config())
