"""芭芭拉内容事件钩子：环、被动与命座的运行时行为。

事件钩子统一收敛在本文件：环命中治疗（普攻/重击）、安可延长、C1 周期回能、
C4 重击命中回能。效果工厂与效果声明见 ``effects.py``；属性修饰见
``modifiers.py``；创建物 tick 行为见 ``ring.py``。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_CHARGED_ATTACK_ACTION_KEY,
    BARBARA_CONSTELLATION_C1_ENERGY_IMPACT_KEY,
    BARBARA_CONSTELLATION_C4_ENERGY_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_ON_HIT_HEAL_IMPACT_KEY,
    BARBARA_ENCORE_EXTEND_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_ACTION_KEYS,
    BARBARA_RING_OBJECT_KEY,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.systems.damage import DamageRequestHandler

C4_BUCKET_PRUNE_AFTER_FRAMES = 600


class BarbaraRingOnHitHealHook:
    """环存在期间，芭芭拉普攻/重击命中时治疗全队（每次动作影响只触发一次）。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        heal_payload: Mapping[str, object],
    ) -> None:
        self._owner_ref = owner_ref
        self._slot = slot
        self._heal_payload = dict(heal_payload)
        self._seen_frame: int | None = None
        self._seen_impact_point_ids: set[str] = set()
        self.hook_key = f"barbara.ring.on_hit_heal:{owner_ref}"
        self.state_key = BARBARA_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        payload = getattr(event, "payload", None)
        result = getattr(payload, "result", None)
        if result is None or getattr(result, "source_ref", None) is None:
            return HookResult()
        if result.source_ref.entity_id != self._owner_ref:
            return HookResult()
        if not self._ring_active(context):
            return HookResult()
        hit = self._hit_record(context, result.request_id)
        if hit is None:
            return HookResult()
        multiplier, impact_point_id = hit
        frame = getattr(event, "frame", 0)
        if not self._observe_hit(frame, impact_point_id):
            return HookResult()
        team_state = getattr(
            getattr(context, "simulation", None),
            "space_runtime",
            None,
        )
        team_state = getattr(team_state, "team_state", None)
        if team_state is None:
            return HookResult()
        request = ImpactRequest(
            frame=frame,
            kind=ImpactKind.HEAL,
            impact_key=BARBARA_ELEMENTAL_SKILL_ON_HIT_HEAL_IMPACT_KEY,
            owner_slot=self._slot,
            request_id=f"hook:{self.hook_key}:{result.request_id}",
            target_refs=tuple(character.combat_entity_id for character in team_state.characters),
            params={
                "heal": self._scaled_payload(
                    multiplier,
                    result.request_id,
                )
            },
        )
        return HookResult(impact_requests=(request,))

    def _ring_active(self, context: object) -> bool:
        simulation = getattr(context, "simulation", None)
        space_runtime = getattr(simulation, "space_runtime", None)
        created_object_runtime = getattr(
            space_runtime,
            "created_object_runtime",
            None,
        )
        if created_object_runtime is None:
            return False
        return any(
            obj.object_key == BARBARA_RING_OBJECT_KEY
            and obj.is_active_at(getattr(simulation, "current_frame", 0))
            for obj in created_object_runtime.objects
        )

    def _hit_record(
        self,
        context: object,
        request_id: str,
    ) -> tuple[float, str] | None:
        simulation = getattr(context, "simulation", None)
        handler = None if simulation is None else simulation.get_system(DamageRequestHandler)
        if not isinstance(handler, DamageRequestHandler):
            return None
        for record in handler.records:
            if record.result.request_id != request_id:
                continue
            action_key = record.impact_request.action_key
            if action_key in BARBARA_NORMAL_ATTACK_ACTION_KEYS:
                multiplier = 1.0
            elif action_key == BARBARA_CHARGED_ATTACK_ACTION_KEY:
                multiplier = 4.0
            else:
                return None
            impact_point_id = record.impact_request.source_impact_point_id
            if impact_point_id is None:
                impact_point_id = record.impact_request.request_id
            if impact_point_id is None:
                return None
            return multiplier, impact_point_id
        return None

    def _observe_hit(self, frame: int, impact_point_id: str) -> bool:
        if self._seen_frame != frame:
            self._seen_frame = frame
            self._seen_impact_point_ids.clear()
        if impact_point_id in self._seen_impact_point_ids:
            return False
        self._seen_impact_point_ids.add(impact_point_id)
        return True

    def _scaled_payload(self, multiplier: float, request_id: str) -> dict[str, object]:
        raw_terms = cast(
            tuple[Mapping[str, object], ...],
            self._heal_payload["scaling_terms"],
        )
        scaling_terms = tuple(
            {
                **term,
                "coefficient": cast(float, term["coefficient"]) * multiplier,
            }
            for term in raw_terms
        )
        payload = dict(self._heal_payload)
        payload["scaling_terms"] = scaling_terms
        payload["flat_healing"] = cast(float, payload["flat_healing"]) * multiplier
        payload["healing_id"] = f"{BARBARA_ELEMENTAL_SKILL_ON_HIT_HEAL_IMPACT_KEY}:{request_id}"
        return payload


class BarbaraRingEncoreHook:
    """安可：环存在期间，当前场角色拾取元素微粒/晶球时延长环持续时间。

    每个微粒/晶球按 ``extend_frames`` 延长；单个环实例累计延长不超过
    ``max_extra_frames``。能量已满（CAPPED）的拾取同样触发。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        object_key: str,
        extend_frames: int,
        max_extra_frames: int,
    ) -> None:
        self._owner_ref = owner_ref
        self._slot = slot
        self._object_key = object_key
        self._extend_frames = extend_frames
        self._max_extra_frames = max_extra_frames
        self.hook_key = f"barbara.encore:{owner_ref}"
        self.state_key = BARBARA_CHARACTER_HANDLER_KEY
        self.subscriptions = ("ENERGY_PICKUP_SETTLED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        payload = getattr(event, "payload", None)
        result = getattr(payload, "result", None)
        pickup = getattr(result, "pickup", None)
        if pickup is None:
            return HookResult()
        if not self._ring_active(context):
            return HookResult()
        count = getattr(pickup, "count", None)
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            return HookResult()
        frame = getattr(event, "frame", 0)
        request = ImpactRequest(
            frame=frame,
            kind=ImpactKind.EXTEND_CREATED_ENTITY,
            impact_key=BARBARA_ENCORE_EXTEND_IMPACT_KEY,
            owner_slot=self._slot,
            request_id=f"hook:{self.hook_key}:{pickup.pickup_id}",
            params={
                "object_key": self._object_key,
                "owner_key": f"slot:{self._slot}",
                "frames": self._extend_frames * count,
                "max_extra_frames": self._max_extra_frames,
            },
        )
        return HookResult(impact_requests=(request,))

    def _ring_active(self, context: object) -> bool:
        simulation = getattr(context, "simulation", None)
        space_runtime = getattr(simulation, "space_runtime", None)
        created_object_runtime = getattr(
            space_runtime,
            "created_object_runtime",
            None,
        )
        if created_object_runtime is None:
            return False
        return any(
            obj.object_key == self._object_key
            and obj.entity.owner_key == f"slot:{self._slot}"
            and obj.is_active_at(getattr(simulation, "current_frame", 0))
            for obj in created_object_runtime.objects
        )


class BarbaraConstellationC1EnergyHook:
    """C1：订阅 FRAME_STARTED，每 ``interval_frames`` 帧恢复一次能量。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        interval_frames: int,
        amount: float,
    ) -> None:
        if interval_frames <= 0:
            raise ContentUnitValidationError("C1 恢复间隔必须为正帧数")
        if amount <= 0:
            raise ContentUnitValidationError("C1 恢复量必须为正数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._interval_frames = interval_frames
        self._amount = amount
        self.hook_key = f"barbara.constellation.c1:{owner_ref}"
        self.state_key = BARBARA_CHARACTER_HANDLER_KEY
        self.subscriptions = ("FRAME_STARTED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if frame <= 0 or frame % self._interval_frames != 0:
            return HookResult()
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=BARBARA_CONSTELLATION_C1_ENERGY_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    target_refs=(self._owner_ref,),
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "restore",
                            "amount": self._amount,
                            "tags": [],
                        }
                    },
                ),
            )
        )


class BarbaraConstellationC4EnergyHook:
    """C4：一次重击动作内按不同敌人去重恢复能量，单次至多 5 点。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        amount: float,
        max_per_action: int,
        prune_after_frames: int = C4_BUCKET_PRUNE_AFTER_FRAMES,
    ) -> None:
        if amount <= 0:
            raise ContentUnitValidationError("C4 恢复量必须为正数")
        if max_per_action <= 0:
            raise ContentUnitValidationError("C4 单次上限必须为正整数")
        if (
            isinstance(prune_after_frames, bool)
            or not isinstance(prune_after_frames, int)
            or prune_after_frames <= 0
        ):
            raise ContentUnitValidationError("C4 剪枝间隔必须为正整数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._amount = amount
        self._max_per_action = max_per_action
        self._prune_after_frames = prune_after_frames
        self._seen_targets: dict[str, tuple[int, set[str]]] = {}
        self.hook_key = f"barbara.constellation.c4:{owner_ref}"
        self.state_key = BARBARA_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def bucket_count(self) -> int:
        return len(self._seen_targets)

    def handle(self, event: object, context: object) -> HookResult:
        frame = getattr(event, "frame", 0)
        self._prune(frame)
        payload = getattr(event, "payload", None)
        result = getattr(payload, "result", None)
        if result is None or getattr(result, "source_ref", None) is None:
            return HookResult()
        if result.source_ref.entity_id != self._owner_ref:
            return HookResult()
        target_ref = getattr(result, "target_ref", None)
        target_id = getattr(target_ref, "entity_id", None)
        if not isinstance(target_id, str) or not target_id.startswith("target:"):
            return HookResult()
        action_key, bucket_id = self._hit_bucket(context, result.request_id)
        if action_key != BARBARA_CHARGED_ATTACK_ACTION_KEY or bucket_id is None:
            return HookResult()
        _, seen = self._seen_targets.get(bucket_id, (frame, set()))
        if target_id in seen or len(seen) >= self._max_per_action:
            return HookResult()
        seen.add(target_id)
        self._seen_targets[bucket_id] = (frame, seen)
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=BARBARA_CONSTELLATION_C4_ENERGY_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{bucket_id}:{target_id}",
                    target_refs=(self._owner_ref,),
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "restore",
                            "amount": self._amount,
                            "tags": [],
                        }
                    },
                ),
            )
        )

    def _hit_bucket(
        self,
        context: object,
        request_id: str,
    ) -> tuple[str | None, str | None]:
        simulation = getattr(context, "simulation", None)
        handler = None if simulation is None else simulation.get_system(DamageRequestHandler)
        if not isinstance(handler, DamageRequestHandler):
            return None, None
        for record in handler.records:
            if record.result.request_id != request_id:
                continue
            impact_request = record.impact_request
            action_key = impact_request.action_key
            if action_key != BARBARA_CHARGED_ATTACK_ACTION_KEY:
                return action_key, None
            bucket_id = impact_request.source_impact_point_id
            if bucket_id is None:
                bucket_id = impact_request.request_id
            if bucket_id is None:
                bucket_id = request_id
            return action_key, bucket_id
        return None, None

    def _prune(self, frame: int) -> None:
        """惰性清理超过剪枝间隔没有新命中的重击桶。"""

        if not self._seen_targets:
            return
        cutoff = frame - self._prune_after_frames
        stale = [
            bucket_id
            for bucket_id, (last_seen, _) in self._seen_targets.items()
            if last_seen < cutoff
        ]
        for bucket_id in stale:
            del self._seen_targets[bucket_id]
