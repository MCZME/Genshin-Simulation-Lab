"""test_assembler_content.py 测试。"""

from __future__ import annotations

from genshin_sim.application.assembly import (
    SimulationAssembler,
)
from genshin_sim.assets.models import (
    CharacterAsset,
)
from genshin_sim.content.bootstrap_content_units import (
    create_default_content_unit_registry,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.core.actions import (
    TimedImpactAction,
)
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STAT_CRIT_RATE,
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
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffValueRefreshPolicy,
)
from tests.helpers.assembly import (
    ContributedActionInterpreter,
    TestAttributeModifier,
    TestCreatedObjectBehavior,
    TestImpactFactory,
    minimal_input,
    skill_input_trace,
)
from tests.helpers.asset_repository import FakeAssetRepository


def test_assembler_injects_character_runtime_contribution_and_actions():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__(
                characters=(
                    CharacterAsset(
                        asset_key="character:75",
                        source_id="75",
                        name="test",
                        element="hydro",
                        weapon_type="sword",
                        rarity=5,
                        burst_energy_cost=60.0,
                        handler_key="character.runtime",
                    ),
                ),
            )

    interpreter = ContributedActionInterpreter()
    impact_factory = TestImpactFactory()
    created_object_behavior = TestCreatedObjectBehavior()
    registry = create_default_content_unit_registry()
    registry.register_character_factory(
        "character.runtime",
        lambda request: ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key=request.character_key,
            handler_key=request.handler_key,
            version="dev-test",
            slot=request.slot,
            action_interpreter=interpreter,
            actions=(
                TimedImpactAction(
                    action_key="character.runtime.skill",
                    duration_frames=1,
                    impact_keys=("impact.character_runtime",),
                ),
            ),
            impact_factories={"impact.character_runtime": impact_factory},
            created_object_behaviors={"created_object.character_runtime": created_object_behavior},
        ),
    )

    assembled = SimulationAssembler(
        RuntimeRepository(),
        content_unit_registry=registry,
    ).assemble(minimal_input(input_trace=skill_input_trace()))
    result = assembled.simulator.run()

    assert result.end_frame == 3
    assert assembled.content_bundle.action_interpreters == {1: interpreter}
    assert "character.runtime.skill" in assembled.action_registry.action_keys
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
            super().__init__(
                characters=(
                    CharacterAsset(
                        asset_key="character:75",
                        source_id="75",
                        name="test",
                        element="hydro",
                        weapon_type="sword",
                        rarity=5,
                        burst_energy_cost=60.0,
                        handler_key="character.attribute_modifier",
                    ),
                ),
            )

    registry = create_default_content_unit_registry()
    registry.register_character_factory(
        "character.attribute_modifier",
        lambda request: ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key=request.character_key,
            handler_key=request.handler_key,
            version="dev-test",
            slot=request.slot,
            modifiers=(TestAttributeModifier(),),
        ),
    )

    assembled = SimulationAssembler(
        RuntimeRepository(),
        content_unit_registry=registry,
    ).assemble(minimal_input())
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
            super().__init__(
                characters=(
                    CharacterAsset(
                        asset_key="character:75",
                        source_id="75",
                        name="test",
                        element="hydro",
                        weapon_type="sword",
                        rarity=5,
                        burst_energy_cost=60.0,
                        handler_key="character.buff",
                    ),
                ),
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
    registry = create_default_content_unit_registry()
    registry.register_character_factory(
        "character.buff",
        lambda request: ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key=request.character_key,
            handler_key=request.handler_key,
            version="dev-test",
            slot=request.slot,
            buff_definitions=(definition,),
        ),
    )

    assembled = SimulationAssembler(
        RuntimeRepository(),
        content_unit_registry=registry,
    ).assemble(minimal_input())
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


def test_assembler_registers_content_private_attribute_and_native_provider():
    private_key = AttributeKey("character.attribute_modifier.private_bonus")
    subject_ref = AttributeSubjectRef.character("character:slot_1")

    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__(
                characters=(
                    CharacterAsset(
                        asset_key="character:75",
                        source_id="75",
                        name="test",
                        element="hydro",
                        weapon_type="sword",
                        rarity=5,
                        burst_energy_cost=60.0,
                        handler_key="character.attribute_modifier",
                    ),
                ),
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
    registry = create_default_content_unit_registry()
    registry.register_character_factory(
        "character.attribute_modifier",
        lambda request: ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key=request.character_key,
            handler_key=request.handler_key,
            version="dev-test",
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

    assembled = SimulationAssembler(
        RuntimeRepository(),
        content_unit_registry=registry,
    ).assemble(minimal_input())
    resolution = assembled.attribute_runtime.resolver.resolve(
        AttributeQuery(subject_ref, private_key, frame=0)
    )

    assert resolution.final_value == 0.25


def test_assembler_mounts_content_state_under_character_runtime_state():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__(
                characters=(
                    CharacterAsset(
                        asset_key="character:75",
                        source_id="75",
                        name="test",
                        element="hydro",
                        weapon_type="sword",
                        rarity=5,
                        burst_energy_cost=60.0,
                        handler_key="character.state_mount",
                    ),
                ),
            )

    registry = create_default_content_unit_registry()
    registry.register_character_factory(
        "character.state_mount",
        lambda request: ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key=request.character_key,
            handler_key=request.handler_key,
            version="dev-test",
            slot=request.slot,
            state_schema=StateSchema(
                owner_ref=f"character:slot_{request.slot}",
                fields=(
                    StateField(
                        name="stacks",
                        field_type=StateFieldType.INT,
                        default=0,
                    ),
                ),
            ),
        ),
    )

    assembled = SimulationAssembler(
        RuntimeRepository(),
        content_unit_registry=registry,
    ).assemble(minimal_input())
    character = assembled.space_runtime.team_state.current_character

    mount = character.content_states["character.state_mount"]
    assert mount.owner == "character:slot_1"
    assert mount.values == {"stacks": 0}
    assert assembled.content_bundle.content_state_mounts == (mount,)
