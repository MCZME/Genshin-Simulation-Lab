"""月兆运行时：等级只读查询、非月兆月曜增伤应用与到期清理。"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STAT_DEF_TOTAL,
    STAT_ELEMENTAL_MASTERY,
    STAT_HP_MAX,
    AttributeQuery,
    AttributeResolveOptions,
    AttributeSubjectRef,
    AttributeSystemError,
    TraceLevel,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.events import (
    ActionStartedPayload,
    EventEngine,
    EventType,
    GameEvent,
    MoonsignBonusAppliedPayload,
    MoonsignBonusExpiredPayload,
    MoonsignLevelSetPayload,
)
from genshin_sim.core.systems.moonsign.errors import MoonsignError, MoonsignValidationError
from genshin_sim.core.systems.moonsign.models import (
    MoonsignBonusRecord,
    MoonsignLevel,
    MoonsignScaling,
    MoonsignStatSnapshot,
)
from genshin_sim.core.systems.moonsign.resolver import resolve_non_moonsign_bonus
from genshin_sim.core.systems.moonsign.snapshots import MoonsignSnapshot
from genshin_sim.core.systems.moonsign.store import MoonsignStore


class MoonsignRuntime:
    """月兆领域运行入口。

    等级在组装期确定；运行时在 ``FACT_RESPONSE`` 消费 ``ACTION_STARTED``，
    满辉时对非月兆角色的元素战技/爆发应用覆盖式月曜增伤，并在到期帧清理。
    """

    def __init__(
        self,
        store: MoonsignStore,
        event_engine: EventEngine,
        attribute_resolver,
        scaling_by_element: Mapping[Element, MoonsignScaling],
        *,
        cap: float = 0.36,
        duration_frames: int = 1200,
        element_by_slot: Mapping[int, Element] | None = None,
    ) -> None:
        self.store = store
        self.event_engine = event_engine
        self.attribute_resolver = attribute_resolver
        self.scaling_by_element = dict(scaling_by_element)
        self.cap = cap
        self.duration_frames = duration_frames
        self.element_by_slot = dict(element_by_slot or {})
        self._processed_frame = -1
        self._processed_count = 0
        self._level_published = False

    @property
    def level(self) -> MoonsignLevel:
        return self.store.level

    @property
    def has_nascent(self) -> bool:
        return self.store.level.rank >= 1

    @property
    def has_ascendant(self) -> bool:
        return self.store.level.rank >= 2

    def update_frame(self, context, frame: int) -> None:
        if not self._level_published:
            self._level_published = True
            self.event_engine.publish(
                GameEvent(
                    EventType.MOONSIGN_LEVEL_SET,
                    frame,
                    MoonsignLevelSetPayload(
                        level=self.store.level.value,
                        moonsign_character_refs=tuple(
                            ref.entity_id for ref in self.store.moonsign_character_refs
                        ),
                        established_frame=0,
                    ),
                    self,
                )
            )
        expired = self.store.clear_expired(frame)
        if expired is not None:
            self.event_engine.publish(
                GameEvent(
                    EventType.MOONSIGN_BONUS_EXPIRED,
                    frame,
                    MoonsignBonusExpiredPayload(
                        frame=frame,
                        source_ref=expired.source_ref.entity_id,
                        value=expired.value,
                    ),
                    self,
                )
            )
        if self._processed_frame != frame:
            self._processed_frame = frame
            self._processed_count = 0
        events = context.events.frame_events
        for event_index in range(self._processed_count, len(events)):
            self._processed_count += 1
            event = events[event_index]
            if event.event_type is not EventType.ACTION_STARTED:
                continue
            payload = event.payload
            if not isinstance(payload, ActionStartedPayload):
                continue
            self._handle_action_started(payload, frame)

    def is_idle(self) -> bool:
        return True

    def lunar_reaction_bonus(self, frame: int) -> float:
        return self.store.current_bonus_value(frame)

    def snapshot(self, frame: int) -> MoonsignSnapshot:
        bonus = self.store.bonus
        return MoonsignSnapshot(
            frame=frame,
            level=self.store.level.value,
            moonsign_character_refs=tuple(
                ref.entity_id for ref in self.store.moonsign_character_refs
            ),
            bonus=None
            if bonus is None
            else {
                "source_ref": bonus.source_ref.entity_id,
                "value": bonus.value,
                "applied_frame": bonus.applied_frame,
                "expires_at_frame": bonus.expires_at_frame,
            },
        )

    def _handle_action_started(
        self,
        payload: ActionStartedPayload,
        frame: int,
    ) -> None:
        if self.store.level is not MoonsignLevel.ASCENDANT:
            return
        if payload.ability_key not in {"elemental_skill", "elemental_burst"}:
            return
        if payload.owner_slot is None:
            return
        character_ref = AttributeSubjectRef.character(f"character:slot_{payload.owner_slot}")
        if character_ref in self.store.moonsign_character_refs:
            return
        element = self.element_by_slot.get(payload.owner_slot)
        if element is None:
            return
        stats = self._resolve_stats(character_ref, frame)
        value = resolve_non_moonsign_bonus(
            element,
            stats,
            self.scaling_by_element,
            self.cap,
        )
        record = MoonsignBonusRecord(
            source_ref=character_ref,
            value=value,
            applied_frame=frame,
            expires_at_frame=frame + self.duration_frames,
        )
        self.store.apply_bonus(record)
        self.event_engine.publish(
            GameEvent(
                EventType.MOONSIGN_BONUS_APPLIED,
                frame,
                MoonsignBonusAppliedPayload(
                    frame=frame,
                    source_ref=character_ref.entity_id,
                    value=value,
                    expires_at_frame=record.expires_at_frame,
                ),
                self,
            )
        )

    def _resolve_stats(
        self,
        character_ref: AttributeSubjectRef,
        frame: int,
    ) -> MoonsignStatSnapshot:
        try:
            atk = self._resolve(character_ref, STAT_ATK_TOTAL, frame)
            hp_max = self._resolve(character_ref, STAT_HP_MAX, frame)
            def_total = self._resolve(character_ref, STAT_DEF_TOTAL, frame)
            em = self._resolve(character_ref, STAT_ELEMENTAL_MASTERY, frame)
        except AttributeSystemError as exc:
            raise MoonsignError(f"月曜增伤属性解析失败：{exc}") from exc
        return MoonsignStatSnapshot(
            atk=atk,
            hp_max=hp_max,
            def_total=def_total,
            elemental_mastery=em,
        )

    def _resolve(self, character_ref: AttributeSubjectRef, key, frame: int) -> float:
        resolution = self.attribute_resolver.resolve(
            AttributeQuery(character_ref, key, frame),
            options=AttributeResolveOptions(trace_level=TraceLevel.NONE),
        )
        value = resolution.final_value
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise MoonsignValidationError(f"{key} 解析结果不是数字")
        return float(value)
