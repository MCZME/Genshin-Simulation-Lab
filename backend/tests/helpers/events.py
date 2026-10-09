"""测试共享的事件构造器与简单运行上下文替身。"""

from __future__ import annotations

from types import SimpleNamespace

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import AuraKind, ElementalSourceRef
from genshin_sim.core.events import (
    ActionStartedPayload,
    EventType,
    GameEvent,
)


def make_event_context(
    frame: int,
    events: tuple = (),
    *,
    random_source: object | None = None,
) -> SimpleNamespace:
    """构造含帧事件列表的最小运行上下文替身。"""

    return SimpleNamespace(
        current_frame=frame,
        settlement_round=0,
        events=SimpleNamespace(frame_events=events),
        random_source=random_source,
    )


def make_reaction_occurrence_event(
    frame: int,
    reaction_key: str,
    occurrence_ref: str,
    *,
    source_key: str = "character:slot_1",
    aura_kind: AuraKind | None = None,
) -> SimpleNamespace:
    """构造反应发生事实替身。

    ``aura_kind`` 非空时补上 ``transition.aura_kind``：扩散类内容的「被扩散
    元素」判据只读该字段（反应事实本体由反应系统产出，此处仅补最小形状）。
    """

    transition = None if aura_kind is None else SimpleNamespace(aura_kind=aura_kind)
    return SimpleNamespace(
        frame=frame,
        event_type=EventType.REACTION_OCCURRED,
        payload=SimpleNamespace(
            occurrence=SimpleNamespace(
                reaction_key=reaction_key,
                occurrence_ref=occurrence_ref,
                source_ref=ElementalSourceRef(source_key),
                transition=transition,
            )
        ),
    )


def make_damage_resolved_event(
    frame: int,
    request_id: str,
    *,
    source_key: str = "character:slot_1",
    target_key: str = "target:1",
    main_attack_tag: str | None = None,
) -> SimpleNamespace:
    """构造伤害结算事实替身。"""

    return SimpleNamespace(
        frame=frame,
        event_type=EventType.DAMAGE_RESOLVED,
        payload=SimpleNamespace(
            result=SimpleNamespace(
                request_id=request_id,
                frame=frame,
                source_ref=AttributeSubjectRef.character(source_key),
                target_ref=AttributeSubjectRef.target(target_key),
                main_attack_tag=main_attack_tag,
            )
        ),
    )


def make_action_started_event(
    frame: int,
    slot: int,
    ability: str,
    *,
    instance_id: int = 1,
    action_key: str = "character.test.skill",
) -> GameEvent:
    """构造动作开始事实。"""

    return GameEvent(
        EventType.ACTION_STARTED,
        frame,
        ActionStartedPayload(
            instance_id=instance_id,
            frame=frame,
            action_key=action_key,
            owner_slot=slot,
            ability_key=ability,
        ),
    )
