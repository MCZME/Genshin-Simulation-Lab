# 单一关注点：Buff 计划投影视图与动态最大生命投影解析。
from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.attributes import (
    STAT_HP_BASE,
    STAT_HP_MAX,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectKind,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.coordination.buff_max_hp_change import (
    BuffProjectionMode,
    ProjectedBuffMaxHpResolver,
    ProjectedBuffReader,
)
from genshin_sim.core.events import EventEngine
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffAttributeModifierProvider,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffDefinitionRegistry,
    BuffModifierValue,
    BuffMutationPlan,
    BuffRemovalReason,
    BuffResolver,
    BuffRuntime,
    BuffStore,
    BuffStoreReader,
    BuffValueRefreshPolicy,
    RemoveBuffRequest,
)
from genshin_sim.core.systems.buff.enums import BuffApplicationPolicy

CHARACTER = AttributeSubjectRef.character("character:slot_1")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.MECHANIC, "mechanic.test_max_hp", "slot:1")


def _definition() -> BuffDefinition:
    return BuffDefinition(
        definition_key="buff.test.max_hp",
        mechanic_key="mechanic.test_max_hp",
        handler_key="test.buff",
        conflict_key="buff.test.max_hp",
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REPLACE,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key="max_hp_flat",
                target_key=STAT_HP_MAX,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({"test_max_hp"}),
    )


def _apply(request_id: str, definition: BuffDefinition, frame: int, value: float = 500.0):
    return ApplyBuffRequest(
        request_id=request_id,
        frame=frame,
        order=0,
        definition_key=definition.definition_key,
        target_ref=CHARACTER,
        source_context=SOURCE_CONTEXT,
        duration_frames=5,
        stack_delta=1,
        modifier_values=(BuffModifierValue("max_hp_flat", value),),
        applier_ref=None,
    )


def _empty_plan(frame: int = 3) -> BuffMutationPlan:
    return BuffMutationPlan(
        operation_id=f"buff-empty:{frame}",
        frame=frame,
        expected_store_version=0,
        request_ids=(),
        expected_records=(),
        replacement_records=(),
        application_results=(),
        removal_results=(),
    )


@dataclass
class _Fixture:
    runtime: BuffRuntime
    store: BuffStore
    resolver: AttributeResolver
    definition: BuffDefinition


def _fixture() -> _Fixture:
    definition = _definition()
    registry = create_public_attribute_registry()
    store = BuffStore()
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    CHARACTER,
                    BaseAttributeContribution(STAT_HP_BASE, 1000.0, SOURCE_CONTEXT),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex(
            (BuffAttributeModifierProvider(definition, BuffStoreReader(store)),),
            registry=registry,
        ),
    )
    return _Fixture(
        runtime=BuffRuntime(
            definition_registry=BuffDefinitionRegistry((definition,)),
            resolver=BuffResolver(),
            buff_store=store,
            event_engine=EventEngine(),
        ),
        store=store,
        resolver=resolver,
        definition=definition,
    )


def test_after_view_overlays_replacements_before_commit():
    fixture = _fixture()
    plan = fixture.runtime.prepare_apply([_apply("req:1", fixture.definition, 10)])

    after = ProjectedBuffReader(fixture.store, plan, BuffProjectionMode.AFTER)
    before = ProjectedBuffReader(fixture.store, plan, BuffProjectionMode.BEFORE)

    assert len(after.active(10)) == 1
    assert before.active(10) == ()
    assert fixture.store.active(10) == ()


def test_before_view_keeps_due_records_active_at_boundary_frame():
    fixture = _fixture()
    fixture.runtime.apply(_apply("req:1", fixture.definition, 10))
    plan = fixture.runtime.prepare_expiry(15)
    assert plan is not None

    before = ProjectedBuffReader(fixture.store, plan, BuffProjectionMode.BEFORE)
    after = ProjectedBuffReader(fixture.store, plan, BuffProjectionMode.AFTER)

    assert len(before.active(15)) == 1
    assert after.active(15) == ()
    assert fixture.store.active(15) == ()


def test_remove_plan_before_view_matches_natural_activity():
    fixture = _fixture()
    result = fixture.runtime.apply(_apply("req:1", fixture.definition, 10))
    plan = fixture.runtime.prepare_remove(
        RemoveBuffRequest(
            request_id="rm:1",
            frame=12,
            instance_ref=result.instance_ref,
            reason=BuffRemovalReason.EXPLICIT,
        )
    )

    before = ProjectedBuffReader(fixture.store, plan, BuffProjectionMode.BEFORE)
    after = ProjectedBuffReader(fixture.store, plan, BuffProjectionMode.AFTER)

    assert len(before.active(12)) == 1
    assert after.active(12) == ()


def test_projection_resolver_resolves_old_and_new_max_hp_without_commit():
    fixture = _fixture()
    plan = fixture.runtime.prepare_apply([_apply("req:1", fixture.definition, 10)])
    projection = ProjectedBuffMaxHpResolver(fixture.resolver, fixture.store)

    old_max_hp, new_max_hp = projection.resolve_max_hp_pair(CHARACTER, 10, plan)

    assert old_max_hp == 1000.0
    assert new_max_hp == 1500.0
    # 真实解析器在提交前保持旧值，不受投影影响。
    assert (
        fixture.resolver.resolve(AttributeQuery(CHARACTER, STAT_HP_MAX, frame=10)).final_value
        == 1000.0
    )


def test_projection_resolver_reports_no_change_for_irrelevant_plan():
    fixture = _fixture()
    projection = ProjectedBuffMaxHpResolver(fixture.resolver, fixture.store)

    old_max_hp, new_max_hp = projection.resolve_max_hp_pair(CHARACTER, 3, _empty_plan())

    assert old_max_hp == new_max_hp == 1000.0
