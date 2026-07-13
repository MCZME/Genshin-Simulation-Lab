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
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
)
from genshin_sim.core.impacts import ActionImpactContext, ImpactKind, ImpactRequest
from genshin_sim.core.space import CreatedObjectRuntimeState, SpatialEntityKind
from genshin_sim.core.systems.health import UnsupportedHealthSubjectError


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
        assembled.action_manager,
        assembled.impact_runtime,
        assembled.space_runtime,
    )
    character_ref = AttributeSubjectRef.character("character:slot_1")
    target_ref = AttributeSubjectRef.target("target:target_1")
    assert assembled.health_runtime.get_current_hp(character_ref) == 10000
    assert assembled.health_runtime.get_max_hp(character_ref, frame=0) == 10000
    assert assembled.health_runtime.get_hp_ratio(character_ref, frame=0) == 1.0
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
