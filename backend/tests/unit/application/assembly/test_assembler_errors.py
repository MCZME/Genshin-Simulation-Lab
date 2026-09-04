"""test_assembler_errors.py 测试。"""

from __future__ import annotations

import pytest

from genshin_sim.application.assembly import (
    InvalidRuntimePayloadError,
    MissingRuntimeAssetError,
    MissingRuntimeHandlerError,
    SimulationAssembler,
)
from genshin_sim.assets.models import (
    CharacterAsset,
    WeaponAsset,
)
from genshin_sim.content.bootstrap_content_units import (
    create_default_content_unit_registry,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import (
    ContentUnitRegistry,
)
from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeDefinition,
    AttributeKey,
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
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffValueRefreshPolicy,
)
from tests.helpers.assembly import (
    ContributedActionInterpreter,
    MissingActionInterpreter,
    TestCreatedObjectBehavior,
    minimal_input,
    skill_input_trace,
)
from tests.helpers.asset_repository import FakeAssetRepository


def test_assembler_rejects_character_asset_without_burst_energy_cost():
    repository = FakeAssetRepository(
        characters=(
            CharacterAsset(
                asset_key="character:75",
                source_id="75",
                name="test",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                handler_key="generic.test_character",
            ),
        )
    )

    with pytest.raises(InvalidRuntimePayloadError, match="缺少 burst_energy_cost"):
        SimulationAssembler(repository).assemble(minimal_input())


def test_assembler_rejects_buff_definition_with_dynamic_hp_dependency_via_provider_reads():
    private_key = AttributeKey("character.buff.private_hp_seed")
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
                        handler_key="character.buff",
                    ),
                ),
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
    registry = create_default_content_unit_registry()
    registry.register_character_factory(
        "character.buff",
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
                    namespace_owner="character.buff",
                ),
            ),
            attribute_providers=(provider,),
            buff_definitions=(definition,),
        ),
    )

    assembler = SimulationAssembler(
        RuntimeRepository(),
        content_unit_registry=registry,
    )

    with pytest.raises(
        InvalidRuntimePayloadError,
        match="第一版不能动态影响 stat.hp.max",
    ):
        assembler.assemble(minimal_input())


def test_assembler_rejects_buff_definition_with_unknown_attribute_target():
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

    assembler = SimulationAssembler(
        RuntimeRepository(),
        content_unit_registry=registry,
    )

    with pytest.raises(InvalidRuntimePayloadError, match="写入未知属性"):
        assembler.assemble(minimal_input())


def test_assembler_converts_buff_validation_error_raised_inside_content_factory():
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

    def create_invalid_contribution(request) -> ContentUnit:
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
        return ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key=request.character_key,
            handler_key=request.handler_key,
            version="dev-test",
            slot=request.slot,
            buff_definitions=(definition,),
        )

    registry = create_default_content_unit_registry()
    registry.register_character_factory("character.buff", create_invalid_contribution)

    with pytest.raises(InvalidRuntimePayloadError, match="max_stacks"):
        SimulationAssembler(
            RuntimeRepository(),
            content_unit_registry=registry,
        ).assemble(minimal_input())


def test_assembler_rejects_action_interpreter_from_weapon():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__(
                weapons=(
                    WeaponAsset(
                        asset_key="weapon:11512",
                        source_id="11512",
                        name="test weapon",
                        weapon_type="sword",
                        rarity=5,
                        handler_key="weapon.bad_action_interpreter",
                    ),
                ),
            )

    registry = create_default_content_unit_registry()
    registry.register_weapon_factory(
        "weapon.bad_action_interpreter",
        lambda request: ContentUnit(
            owner_type=ContentUnitOwnerType.WEAPON,
            owner_key=request.weapon_key,
            handler_key=request.handler_key,
            version="dev-test",
            slot=request.slot,
            action_interpreter=ContributedActionInterpreter(),
        ),
    )

    assembler = SimulationAssembler(
        RuntimeRepository(),
        content_unit_registry=registry,
    )

    with pytest.raises(
        InvalidRuntimePayloadError,
        match="只有角色内容单元可以贡献动作解释器",
    ):
        assembler.assemble(minimal_input())


def test_assembler_rejects_missing_character_interpreter_when_action_input_exists():
    assembler = SimulationAssembler(FakeAssetRepository())

    with pytest.raises(InvalidRuntimePayloadError, match="动作输入需要队伍槽位提供动作解释器"):
        assembler.assemble(minimal_input(input_trace=skill_input_trace()))


def test_assembler_rejects_interpreter_declared_action_without_registered_action():
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

    registry = create_default_content_unit_registry()
    registry.register_character_factory(
        "character.runtime",
        lambda request: ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key=request.character_key,
            handler_key=request.handler_key,
            version="dev-test",
            slot=request.slot,
            action_interpreter=MissingActionInterpreter(),
        ),
    )

    assembler = SimulationAssembler(
        RuntimeRepository(),
        content_unit_registry=registry,
    )

    with pytest.raises(InvalidRuntimePayloadError, match="声明了未注册 action"):
        assembler.assemble(minimal_input(input_trace=skill_input_trace()))


def test_assembler_rejects_created_object_behavior_from_weapon():
    class RuntimeRepository(FakeAssetRepository):
        def __init__(self) -> None:
            super().__init__(
                weapons=(
                    WeaponAsset(
                        asset_key="weapon:11512",
                        source_id="11512",
                        name="test weapon",
                        weapon_type="sword",
                        rarity=5,
                        handler_key="weapon.bad_created_object",
                    ),
                ),
            )

    registry = create_default_content_unit_registry()
    registry.register_weapon_factory(
        "weapon.bad_created_object",
        lambda request: ContentUnit(
            owner_type=ContentUnitOwnerType.WEAPON,
            owner_key=request.weapon_key,
            handler_key=request.handler_key,
            version="dev-test",
            slot=request.slot,
            created_object_behaviors={"created_object.bad": TestCreatedObjectBehavior()},
        ),
    )

    assembler = SimulationAssembler(
        RuntimeRepository(),
        content_unit_registry=registry,
    )

    with pytest.raises(
        InvalidRuntimePayloadError,
        match="只有角色内容单元可以贡献内容创建对象行为",
    ):
        assembler.assemble(minimal_input())


def test_assembler_raises_for_missing_asset():
    class BrokenRepository(FakeAssetRepository):
        def get_character(self, character_key: str):
            raise LookupError(character_key)

    assembler = SimulationAssembler(BrokenRepository())

    with pytest.raises(MissingRuntimeAssetError):
        assembler.assemble(minimal_input())


def test_assembler_raises_for_missing_handler():
    assembler = SimulationAssembler(
        FakeAssetRepository(),
        content_unit_registry=ContentUnitRegistry(),
    )

    with pytest.raises(MissingRuntimeHandlerError):
        assembler.assemble(minimal_input())
