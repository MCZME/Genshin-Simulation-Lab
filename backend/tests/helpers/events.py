"""测试共享的事件构造器与简单运行上下文替身。"""

from __future__ import annotations

from types import SimpleNamespace

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import ElementalSourceRef
from genshin_sim.core.events import (
    ActionStartedPayload,
    EventType,
    GameEvent,
)


def make_event_context(frame: int, events: tuple = ()) -> SimpleNamespace:
    """构造含帧事件列表的最小运行上下文替身。"""

    return SimpleNamespace(
        current_frame=frame,
        settlement_round=0,
        events=SimpleNamespace(frame_events=events),
    )


def make_reaction_occurrence_event(
    frame: int,
    reaction_key: str,
    occurrence_ref: str,
    *,
    source_key: str = "character:slot_1",
) -> SimpleNamespace:
    """构造反应发生事实替身。"""

    del frame
    return SimpleNamespace(
        event_type=EventType.REACTION_OCCURRED,
        payload=SimpleNamespace(
            occurrence=SimpleNamespace(
                reaction_key=reaction_key,
                occurrence_ref=occurrence_ref,
                source_ref=ElementalSourceRef(source_key),
            )
        ),
    )


def make_damage_resolved_event(
    frame: int,
    request_id: str,
    *,
    source_key: str = "character:slot_1",
    target_key: str = "target:1",
) -> SimpleNamespace:
    """构造伤害结算事实替身。"""

    return SimpleNamespace(
        event_type=EventType.DAMAGE_RESOLVED,
        payload=SimpleNamespace(
            result=SimpleNamespace(
                request_id=request_id,
                frame=frame,
                source_ref=AttributeSubjectRef.character(source_key),
                target_ref=AttributeSubjectRef.target(target_key),
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
