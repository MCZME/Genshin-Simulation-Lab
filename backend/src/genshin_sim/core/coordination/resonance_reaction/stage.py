"""元素共鸣动态效果的事实响应阶段。

在 ``FACT_RESPONSE`` 阶段消费已提交的反应事实，为下一结算轮次产生
强类型意图：双雷掉落雷元素微粒、双草为全队施加精通 Buff。阶段自身只
提交共鸣领域状态（双雷冷却认领），不直接写入能量或 Buff 领域。
"""

from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.systems.buff.models import ApplyBuffRequest, BuffModifierValue
from genshin_sim.core.systems.resonance.errors import ResonanceValidationError
from genshin_sim.core.systems.resonance.ports import (
    CharacterShieldPresenceReadPort,
    LunarCagePresenceReadPort,
)
from genshin_sim.core.systems.resonance.runtime import ResonanceRuntime


def _require_trigger_keys(keys: Iterable[str], name: str) -> frozenset[str]:
    result = frozenset(keys)
    for key in result:
        if not isinstance(key, str) or not key.strip():
            raise ResonanceValidationError(f"{name} 必须是非空字符串集合")
    return result


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ResonanceValidationError(f"{name} 必须是非空字符串")


class ResonanceReactionStage:
    """消费反应事实并按激活共鸣生成下一轮意图。"""

    def __init__(
        self,
        *,
        resonance_runtime: ResonanceRuntime,
        intent_queue: IntentQueue,
        team_slots: Iterable[int],
        electro_particle_triggers: Iterable[str],
        dendro_em_30_triggers: Iterable[str],
        dendro_em_20_triggers: Iterable[str],
        dendro_em_30_definition_key: str,
        dendro_em_20_definition_key: str,
        geo_res_shred_definition_key: str,
        shield_presence_port: CharacterShieldPresenceReadPort,
        lunar_cage_presence_port: LunarCagePresenceReadPort,
        geo_res_shred_duration_frames: int = 900,
        geo_res_shred_value: float = -0.2,
    ) -> None:
        self._runtime = resonance_runtime
        self._queue = intent_queue
        self._team_slots = tuple(sorted(team_slots))
        if not self._team_slots or any(slot <= 0 for slot in self._team_slots):
            raise ResonanceValidationError("队伍槽位必须是非空正整数集合")
        self._electro_triggers = _require_trigger_keys(
            electro_particle_triggers, "双雷触发反应集合"
        )
        self._dendro_em_30_triggers = _require_trigger_keys(
            dendro_em_30_triggers, "双草 +30 触发反应集合"
        )
        self._dendro_em_20_triggers = _require_trigger_keys(
            dendro_em_20_triggers, "双草 +20 触发反应集合"
        )
        _require_text(dendro_em_30_definition_key, "双草 +30 Buff 定义 key")
        _require_text(dendro_em_20_definition_key, "双草 +20 Buff 定义 key")
        _require_text(geo_res_shred_definition_key, "双岩减抗 Buff 定义 key")
        self._dendro_em_30_definition_key = dendro_em_30_definition_key
        self._dendro_em_20_definition_key = dendro_em_20_definition_key
        self._geo_res_shred_definition_key = geo_res_shred_definition_key
        self._shield_presence_port = shield_presence_port
        self._lunar_cage_presence_port = lunar_cage_presence_port
        if (
            isinstance(geo_res_shred_duration_frames, bool)
            or not isinstance(geo_res_shred_duration_frames, int)
            or geo_res_shred_duration_frames <= 0
        ):
            raise ResonanceValidationError("双岩减抗持续时间必须是正整数")
        self._geo_res_shred_duration_frames = geo_res_shred_duration_frames
        self._geo_res_shred_value = float(geo_res_shred_value)
        self._processed_frame = -1
        self._processed_count = 0

    def update_frame(self, context, frame: int) -> None:
        if self._processed_frame != frame:
            self._processed_frame = frame
            self._processed_count = 0
        events = context.events.frame_events
        for event_index in range(self._processed_count, len(events)):
            self._processed_count += 1
            event = events[event_index]
            if event.event_type is EventType.REACTION_OCCURRED:
                occurrence = getattr(event.payload, "occurrence", None)
                if occurrence is not None:
                    self._handle_electro(context, occurrence, frame, event_index)
                    self._handle_dendro(context, occurrence, frame, event_index)
            elif event.event_type is EventType.DAMAGE_RESOLVED:
                result = getattr(event.payload, "result", None)
                if result is not None:
                    self._handle_geo_res_shred(context, result, frame, event_index)

    def is_idle(self) -> bool:
        return True

    def _handle_electro(self, context, occurrence, frame: int, event_index: int) -> None:
        if not self._runtime.has("resonance.electro"):
            return
        if occurrence.reaction_key not in self._electro_triggers:
            return
        if not self._runtime.try_claim_electro_particle(frame):
            return
        request = ImpactRequest(
            frame=frame,
            kind=ImpactKind.ENERGY,
            impact_key="resonance.electro.particle",
            owner_slot=_slot_from_source(occurrence.source_ref.source_key),
            request_id=f"resonance.electro:{occurrence.occurrence_ref}",
            params={
                "energy": {
                    "schema_version": 1,
                    "operation": "spawn_pickup",
                    "pickup_kind": "particle",
                    "element": "electro",
                    "count": 1,
                    "travel_frames": 0,
                }
            },
        )
        self._enqueue(
            context,
            intent_id=(f"resonance.electro:{occurrence.occurrence_ref}:{frame}:{event_index}"),
            source_ref="resonance.electro",
            payload=request,
        )

    def _handle_dendro(self, context, occurrence, frame: int, event_index: int) -> None:
        if not self._runtime.has("resonance.dendro"):
            return
        if occurrence.reaction_key in self._dendro_em_30_triggers:
            definition_key = self._dendro_em_30_definition_key
            value = 30.0
        elif occurrence.reaction_key in self._dendro_em_20_triggers:
            definition_key = self._dendro_em_20_definition_key
            value = 20.0
        else:
            return
        for slot in self._team_slots:
            request = ApplyBuffRequest(
                request_id=(f"resonance.dendro:{occurrence.occurrence_ref}:slot_{slot}"),
                frame=frame,
                order=slot,
                definition_key=definition_key,
                target_ref=AttributeSubjectRef.character(f"character:slot_{slot}"),
                source_context=RuntimeSourceRef(
                    RuntimeSourceKind.SYSTEM,
                    "resonance.dendro",
                    occurrence.occurrence_ref,
                ),
                duration_frames=360,
                modifier_values=(BuffModifierValue("elemental_mastery", value),),
            )
            self._enqueue(
                context,
                intent_id=(
                    f"resonance.dendro:{occurrence.occurrence_ref}:"
                    f"slot_{slot}:{frame}:{event_index}"
                ),
                source_ref="resonance.dendro",
                payload=request,
            )

    def _handle_geo_res_shred(
        self,
        context,
        result,
        frame: int,
        event_index: int,
    ) -> None:
        if not self._runtime.has("resonance.geo"):
            return
        target_ref = getattr(result, "target_ref", None)
        source_ref = getattr(result, "source_ref", None)
        if not isinstance(target_ref, AttributeSubjectRef) or not isinstance(
            source_ref,
            AttributeSubjectRef,
        ):
            return
        if target_ref.kind is not AttributeSubjectKind.TARGET:
            return
        shielded = self._shield_presence_port.has_active_shield(
            source_ref,
            frame,
        )
        if not shielded and not self._lunar_cage_presence_port.has_active_lunar_cage():
            return
        request = ApplyBuffRequest(
            request_id=(
                f"resonance.geo:{getattr(result, 'request_id', 'damage')}:{target_ref.entity_id}"
            ),
            frame=frame,
            order=0,
            definition_key=self._geo_res_shred_definition_key,
            target_ref=target_ref,
            source_context=RuntimeSourceRef(
                RuntimeSourceKind.SYSTEM,
                "resonance.geo",
                getattr(result, "request_id", None),
            ),
            duration_frames=self._geo_res_shred_duration_frames,
            modifier_values=(BuffModifierValue("resistance_geo", self._geo_res_shred_value),),
            applier_ref=source_ref,
        )
        self._enqueue(
            context,
            intent_id=(
                f"resonance.geo:{getattr(result, 'request_id', 'damage')}:"
                f"{target_ref.entity_id}:{frame}:{event_index}"
            ),
            source_ref="resonance.geo",
            payload=request,
        )

    def _enqueue(self, context, *, intent_id: str, source_ref: str, payload: object) -> None:
        self._queue.enqueue(
            IntentEnvelope(
                intent_id=intent_id,
                kind=IntentKind.BUFF
                if isinstance(payload, ApplyBuffRequest)
                else IntentKind.IMPACT,
                frame=context.current_frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=source_ref,
                payload=payload,
            )
        )


def _slot_from_source(source_key: str) -> int | None:
    prefix = "character:slot_"
    if not source_key.startswith(prefix):
        return None
    suffix = source_key.removeprefix(prefix)
    if not suffix.isdigit():
        return None
    return int(suffix)
