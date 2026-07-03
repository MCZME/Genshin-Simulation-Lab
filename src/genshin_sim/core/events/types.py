from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Protocol, runtime_checkable


class EventType(Enum):
    """核心事件类型。

    第一版保留旧项目事件名称，方便后续游戏逻辑直迁。
    """

    FRAME_END = auto()
    INPUT_KEY_EVENT = auto()
    ACTION_DECISION = auto()

    BEFORE_DAMAGE = auto()
    AFTER_DAMAGE = auto()
    BEFORE_CALCULATE = auto()
    AFTER_CALCULATE = auto()

    AFTER_ELEMENTAL_REACTION = auto()
    ELECTRO_CHARGED_TICK = auto()
    BURNING_TICK = auto()

    AFTER_LUNAR_BLOOM = auto()
    AFTER_LUNAR_CHARGED = auto()
    AFTER_LUNAR_CRYSTALLIZE = auto()
    LUNAR_CHARGED_TICK = auto()
    LUNAR_CRYSTALLIZE_ATTACK = auto()
    GRASS_DEW_GAIN = auto()
    GRASS_DEW_CONSUME = auto()
    GRAVITY_INTERFERENCE = auto()

    AFTER_HEALTH_CHANGE = auto()
    BEFORE_HEAL = auto()
    AFTER_HEAL = auto()
    BEFORE_HURT = auto()
    AFTER_HURT = auto()

    ON_MODIFIER_ADDED = auto()
    ON_MODIFIER_REMOVED = auto()
    ON_EFFECT_ADDED = auto()
    ON_EFFECT_REMOVED = auto()
    ON_SHIELD_CHANGE = auto()

    BEFORE_NORMAL_ATTACK = auto()
    BEFORE_CHARGED_ATTACK = auto()
    BEFORE_PLUNGING_ATTACK = auto()
    BEFORE_SKILL = auto()
    AFTER_SKILL = auto()
    BEFORE_BURST = auto()
    AFTER_BURST = auto()
    BEFORE_DASH = auto()
    BEFORE_JUMP = auto()
    BEFORE_FALLING = auto()

    BEFORE_ENERGY_CHANGE = auto()
    AFTER_ENERGY_CHANGE = auto()
    AFTER_CHARACTER_SWITCH = auto()
    NIGHTSOUL_BURST = auto()

    SCENE_ENTITY_ENTER = auto()
    SCENE_ENTITY_EXIT = auto()
    SCENE_ENTITY_TICK = auto()


@dataclass(slots=True)
class GameEvent:
    """一次仿真事件。

    ``record`` 只表达事件是否进入帧事件缓冲；具体如何持久化由 core 外部决定。
    """

    event_type: EventType
    frame: int
    source: Any = None
    data: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False
    record: bool = True

    def cancel(self) -> None:
        self.cancelled = True


@runtime_checkable
class EventHandler(Protocol):
    """对象式事件处理器协议。"""

    def handle_event(self, event: GameEvent) -> None:
        """处理事件。"""
