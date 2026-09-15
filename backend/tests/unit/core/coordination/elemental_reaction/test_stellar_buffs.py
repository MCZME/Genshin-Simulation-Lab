# 单一关注点：辉映·星烁 Buff 定义、请求计划与领域来源物理减抗的冲突槽语义。
from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    BONUS_DAMAGE_CRYO,
    STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.coordination.elemental_reaction.status import (
    SUPERCONDUCT_BUFF_DEFINITION_KEY,
    SUPERCONDUCT_BUFF_TERM_KEY,
    SUPERCONDUCT_STATUS_PROFILE_KEY,
    superconduct_buff_definition,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
    STELLAR_FIELD_RESIST_SOURCE_KEY,
    STELLAR_RADIANCE_BUFF_DEFINITION_KEY,
    STELLAR_RADIANCE_CRYO_BONUS_TERM_KEY,
    STELLAR_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY,
    STELLAR_RADIANCE_ELECTRO_BONUS_TERM_KEY,
    STELLAR_RADIANCE_PERSISTENCE_FRAMES,
    plan_radiance_buff_requests,
    stellar_radiance_buff_definition,
)
from genshin_sim.core.events import EventEngine
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationOutcome,
    BuffAttributeModifierProvider,
    BuffDefinitionRegistry,
    BuffModifierValue,
    BuffResolver,
    BuffRuntime,
    BuffStore,
)
from genshin_sim.core.systems.reaction.states import STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES

CHARACTER = AttributeSubjectRef.character("character:test")
OTHER_CHARACTER = AttributeSubjectRef.character("character:other")
ENEMY = AttributeSubjectRef.target("target:star")
FIELD_OCCURRENCE = "interaction:1:occurrence:0"


def _radiance_request(
    request_id: str,
    target_ref: AttributeSubjectRef,
    *,
    order: int,
    frame: int = 0,
    settled_stacks: int = 0,
) -> ApplyBuffRequest:
    return plan_radiance_buff_requests(
        frame=frame,
        occurrence_ref=FIELD_OCCURRENCE,
        character_refs=(target_ref,),
        settled_stacks=settled_stacks,
        field_expires_at_frame=frame + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
        order_start=order,
    )[0]


def test_radiance_buff_definition_targets_character_bonus_and_multiplier_terms() -> None:
    definition = stellar_radiance_buff_definition()

    assert definition.definition_key == STELLAR_RADIANCE_BUFF_DEFINITION_KEY
    assert definition.max_stacks == 1
    term_targets = {
        template.term_key: template.target_key for template in definition.attribute_modifiers
    }
    assert term_targets[STELLAR_RADIANCE_CRYO_BONUS_TERM_KEY] is BONUS_DAMAGE_CRYO
    assert (
        term_targets[STELLAR_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY]
        is STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER
    )


@pytest.mark.parametrize(
    ("settled_stacks", "expected_bonus", "expected_multiplier"),
    [(0, 0.20, 1.0), (1, 0.29, 1.45), (12, 0.40, 2.0), (13, 0.40, 2.0)],
)
def test_radiance_requests_project_stack_coefficients(
    settled_stacks: int,
    expected_bonus: float,
    expected_multiplier: float,
) -> None:
    requests = plan_radiance_buff_requests(
        frame=0,
        occurrence_ref=FIELD_OCCURRENCE,
        character_refs=(CHARACTER, OTHER_CHARACTER),
        settled_stacks=settled_stacks,
        field_expires_at_frame=STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
    )

    assert len(requests) == 2
    values = {value.term_key: value.value for value in requests[0].modifier_values}
    assert values[STELLAR_RADIANCE_CRYO_BONUS_TERM_KEY] == pytest.approx(expected_bonus)
    assert values[STELLAR_RADIANCE_ELECTRO_BONUS_TERM_KEY] == pytest.approx(expected_bonus)
    assert values[STELLAR_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY] == pytest.approx(expected_multiplier)
    assert requests[0].duration_frames == (
        STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES + STELLAR_RADIANCE_PERSISTENCE_FRAMES
    )


def test_field_resistance_replaces_superconduct_source_in_same_conflict_slot() -> None:
    runtime = BuffRuntime(
        definition_registry=BuffDefinitionRegistry((superconduct_buff_definition(),)),
        resolver=BuffResolver(),
        buff_store=BuffStore(),
        event_engine=EventEngine(),
    )

    def _request(request_id: str, source_key: str, duration: int) -> ApplyBuffRequest:
        return ApplyBuffRequest(
            request_id=request_id,
            frame=0,
            order=0,
            definition_key=SUPERCONDUCT_BUFF_DEFINITION_KEY,
            target_ref=ENEMY,
            source_context=RuntimeSourceRef(RuntimeSourceKind.MECHANIC, source_key, "cause"),
            duration_frames=duration,
            modifier_values=(BuffModifierValue(SUPERCONDUCT_BUFF_TERM_KEY, -0.40),),
        )

    field_result = runtime.apply(
        _request(
            "resist:field:1",
            STELLAR_FIELD_RESIST_SOURCE_KEY,
            STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
        )
    )
    normal_result = runtime.apply(_request("resist:normal:1", SUPERCONDUCT_STATUS_PROFILE_KEY, 720))

    assert field_result.outcome is BuffApplicationOutcome.CREATED
    assert normal_result.outcome is BuffApplicationOutcome.REPLACED
    assert normal_result.replaced_instance_refs == (field_result.instance_ref,)
    active = runtime.reader.active(0, definition_key=SUPERCONDUCT_BUFF_DEFINITION_KEY)
    assert len(active) == 1
    assert active[0].state.source_context.source_key == SUPERCONDUCT_STATUS_PROFILE_KEY

    field_refresh = runtime.apply(
        _request(
            "resist:field:2",
            STELLAR_FIELD_RESIST_SOURCE_KEY,
            STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
        )
    )
    assert field_refresh.outcome is BuffApplicationOutcome.REPLACED
    assert len(runtime.reader.active(0, definition_key=SUPERCONDUCT_BUFF_DEFINITION_KEY)) == 1


def test_radiance_buff_contributes_element_bonus_through_attribute_system() -> None:
    """辉映 Buff 的冰/雷增伤与直伤系数词条必须经属性系统可读。"""

    registry = create_public_attribute_registry()
    buff_store = BuffStore()
    buff_runtime = BuffRuntime(
        definition_registry=BuffDefinitionRegistry(
            (superconduct_buff_definition(), stellar_radiance_buff_definition())
        ),
        resolver=BuffResolver(),
        buff_store=buff_store,
        event_engine=EventEngine(),
    )
    buff_runtime.commit_prevalidated(
        buff_runtime.prepare_apply(
            plan_radiance_buff_requests(
                frame=0,
                occurrence_ref=FIELD_OCCURRENCE,
                character_refs=(CHARACTER,),
                settled_stacks=3,
                field_expires_at_frame=STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
            )
        )
    )
    attribute_resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(()),
        modifier_index=ModifierProviderIndex(
            (
                BuffAttributeModifierProvider(
                    stellar_radiance_buff_definition(), buff_runtime.reader
                ),
            ),
            registry=registry,
        ),
    )

    cryo = attribute_resolver.resolve(
        AttributeQuery(
            subject_ref=CHARACTER,
            attribute_key=BONUS_DAMAGE_CRYO,
            frame=10,
        )
    )
    multiplier = attribute_resolver.resolve(
        AttributeQuery(
            subject_ref=CHARACTER,
            attribute_key=STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER,
            frame=10,
        )
    )
    assert cryo.final_value == pytest.approx(0.31)
    assert multiplier.final_value == pytest.approx(1.55)
