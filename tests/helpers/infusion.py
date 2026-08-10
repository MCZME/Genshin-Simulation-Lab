"""元素附魔测试共用的定义、请求与记录工厂。"""

from __future__ import annotations

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.systems.infusion import (
    ApplyInfusionRequest,
    InfusionDefinition,
    InfusionLifecycleState,
    InfusionMode,
    InfusionRecord,
    RefreshPolicy,
)

CHARACTER = AttributeSubjectRef.character("character:slot_1")
CHARACTER_2 = AttributeSubjectRef.character("character:slot_2")
SOURCE = RuntimeSourceRef(RuntimeSourceKind.MECHANIC, "mechanic.test_infusion", "slot:1")
SOURCE_2 = RuntimeSourceRef(RuntimeSourceKind.MECHANIC, "mechanic.test_infusion", "slot:2")

DEFAULT_ATTACK_TAGS = frozenset({"普通攻击", "重击", "下落攻击"})


def make_definition(
    *,
    definition_key: str = "infusion.test",
    mechanic_key: str = "mechanic.test_infusion",
    handler_key: str = "test.infusion",
    mode: InfusionMode = InfusionMode.INFUSION,
    element: Element = Element.PYRO,
    refresh_policy: RefreshPolicy = RefreshPolicy.ONCE,
    duration_frames: int = 10,
    period_frames: int | None = None,
    weapon_gauge: AuraAmount | None = None,
    applicable_attack_tags: frozenset[str] = DEFAULT_ATTACK_TAGS,
    target_kinds: frozenset[AttributeSubjectKind] | None = None,
) -> InfusionDefinition:
    return InfusionDefinition(
        definition_key=definition_key,
        mechanic_key=mechanic_key,
        handler_key=handler_key,
        mode=mode,
        element=element,
        applicable_attack_tags=applicable_attack_tags,
        refresh_policy=refresh_policy,
        duration_frames=duration_frames,
        weapon_gauge=weapon_gauge if weapon_gauge is not None else AuraAmount.one(),
        period_frames=period_frames,
        target_kinds=target_kinds or frozenset({AttributeSubjectKind.CHARACTER}),
    )


def make_request(
    request_id: str,
    definition: InfusionDefinition,
    *,
    frame: int = 0,
    order: int = 0,
    character_ref: AttributeSubjectRef = CHARACTER,
    source_context: RuntimeSourceRef = SOURCE,
    applier_ref: AttributeSubjectRef | None = None,
) -> ApplyInfusionRequest:
    return ApplyInfusionRequest(
        request_id=request_id,
        frame=frame,
        order=order,
        definition_key=definition.definition_key,
        character_ref=character_ref,
        source_context=source_context,
        applier_ref=applier_ref,
    )


def make_record(
    instance_ref,
    definition: InfusionDefinition,
    *,
    character_ref: AttributeSubjectRef = CHARACTER,
    applier_ref: AttributeSubjectRef | None = None,
    source_context: RuntimeSourceRef = SOURCE,
    created_frame: int = 0,
    last_applied_frame: int = 0,
    expires_at_frame: int = 10,
    next_refresh_frame: int | None = None,
    lifecycle_state: InfusionLifecycleState = InfusionLifecycleState.ACTIVE,
    removed_frame: int | None = None,
    removal_reason=None,
    remaining_gauge: AuraAmount | None = None,
) -> InfusionRecord:
    return InfusionRecord(
        instance_ref=instance_ref,
        definition=definition,
        character_ref=character_ref,
        applier_ref=applier_ref,
        source_context=source_context,
        mode=definition.mode,
        element=definition.element,
        refresh_policy=definition.refresh_policy,
        created_frame=created_frame,
        last_applied_frame=last_applied_frame,
        expires_at_frame=expires_at_frame,
        next_refresh_frame=next_refresh_frame,
        lifecycle_state=lifecycle_state,
        removed_frame=removed_frame,
        removal_reason=removal_reason,
        remaining_gauge=(definition.weapon_gauge if remaining_gauge is None else remaining_gauge),
    )
