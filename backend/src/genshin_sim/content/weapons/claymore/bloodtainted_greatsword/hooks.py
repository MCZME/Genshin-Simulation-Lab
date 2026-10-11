"""以理服人被动的事件钩子：战技开启窗口，窗口内普攻/重击命中小范围追加伤害。

单个钩子双订阅：``ACTION_STARTED``（装备者施放元素战技 → 记录窗口截止帧，
钩子实例字段，与西风系列一致）与 ``DAMAGE_RESOLVED``（窗口内普攻/重击命中
敌人 → 按间隔对命中点小范围内敌人产出追加伤害 ``ImpactRequest``）。

AOE 目标经空间运行时按命中敌人位置展开（角色内容侧同款查询），只读取空间
状态，不写任何领域状态。
"""

from __future__ import annotations

from dataclasses import replace

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.claymore.bloodtainted_greatsword.data import (
    BLOODTAINTED_PROC_IMPACT_KEY,
    PROC_AOE_RADIUS,
    TRIGGER_ABILITY_KEY,
    TRIGGER_ATTACK_TAGS,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.space import SpatialEntityKind
from genshin_sim.core.space.geometry import ImpactAreaSpec
from genshin_sim.core.space.runtime import SpaceRuntime

# 敌方目标判据按 entity_id 前缀区分，与西风系列一致。
_ENEMY_TARGET_PREFIX = "target:"


class StraightTalkWindowHook:
    """「有话直说」：战技开启窗口，窗口内普攻/重击命中小范围追加伤害。"""

    def __init__(
        self,
        *,
        handler_key: str,
        impact_key: str,
        owner_ref: str,
        slot: int,
        damage_spec: DamageImpactSpec,
        window_frames: int,
        interval_frames: int,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("有话直说 handler_key 必须是非空字符串")
        if not isinstance(impact_key, str) or not impact_key.strip():
            raise ContentUnitValidationError("有话直说 impact_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("有话直说 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("有话直说必须绑定正整数队伍槽位")
        if not isinstance(damage_spec, DamageImpactSpec):
            raise ContentUnitValidationError("有话直说 damage_spec 必须是 DamageImpactSpec")
        if window_frames <= 0:
            raise ContentUnitValidationError("有话直说窗口帧数必须为正")
        if interval_frames <= 0:
            raise ContentUnitValidationError("有话直说触发间隔必须为正帧数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._damage_spec = damage_spec
        self._window_frames = window_frames
        self._interval_frames = interval_frames
        self._trigger_tags = frozenset(TRIGGER_ATTACK_TAGS)
        self._window_until_frame: int | None = None
        self._last_proc_frame: int | None = None
        self.hook_key = f"{impact_key}:{owner_ref}"
        self.state_key = handler_key
        self.subscriptions = ("ACTION_STARTED", "DAMAGE_RESOLVED")
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def window_until_frame(self) -> int | None:
        """当前窗口截止帧；仅供测试与结果投影读取。"""

        return self._window_until_frame

    @property
    def last_proc_frame(self) -> int | None:
        """最近一次成功追加伤害的帧；仅供测试与结果投影读取。"""

        return self._last_proc_frame

    def handle(self, event: object, context: object) -> HookResult:
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        if getattr(event, "event_type", None) is EventType.ACTION_STARTED:
            return self._handle_cast(event, frame)
        return self._handle_hit(event, context, frame)

    def _handle_cast(self, event: object, frame: int) -> HookResult:
        payload = getattr(event, "payload", None)
        if payload is None:
            return HookResult()
        if getattr(payload, "owner_slot", None) != self._slot:
            return HookResult()
        if getattr(payload, "ability_key", None) != TRIGGER_ABILITY_KEY:
            return HookResult()
        self._window_until_frame = frame + self._window_frames
        return HookResult()

    def _handle_hit(self, event: object, context: object, frame: int) -> HookResult:
        if self._window_until_frame is None or frame >= self._window_until_frame:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        source_ref = getattr(result, "source_ref", None)
        if getattr(source_ref, "entity_id", None) != self._owner_ref:
            return HookResult()
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        if not isinstance(target_id, str) or not target_id.startswith(_ENEMY_TARGET_PREFIX):
            return HookResult()
        if getattr(result, "main_attack_tag", None) not in self._trigger_tags:
            return HookResult()
        if not self._dealt_damage(result):
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            self._interval_frames
        ):
            return HookResult()
        target_ids = self._targets_in_area(context, target_id)
        if not target_ids:
            return HookResult()
        request_id = f"hook:{self.hook_key}:{frame}"
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.DAMAGE,
                    impact_key=BLOODTAINTED_PROC_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=request_id,
                    target_refs=target_ids,
                    damage_spec=replace(
                        self._damage_spec,
                        impact_ref=f"{request_id}:damage",
                    ),
                ),
            )
        )

    def _targets_in_area(self, context: object, center_target_id: str) -> tuple[str, ...]:
        """以命中敌人位置为锚展开「小范围」目标；空间不可用时退化为单体。"""

        space_runtime = _space_runtime(context)
        if space_runtime is None:
            return (center_target_id,)
        center = space_runtime.get_entity(center_target_id)
        if center is None:
            return (center_target_id,)
        area = ImpactAreaSpec(shape="圆柱", radius=PROC_AOE_RADIUS).resolve(
            center.position,
            center.facing,
        )
        entities = space_runtime.entities_in_area(
            area,
            kinds=frozenset({SpatialEntityKind.TARGET}),
        )
        candidates = space_runtime.resolve_candidate_targets(
            tuple(entity.entity_id for entity in entities)
        )
        return tuple(candidate.target_id for candidate in candidates)

    @staticmethod
    def _dealt_damage(result: object) -> bool:
        damage = getattr(result, "final_damage", None)
        if isinstance(damage, bool) or not isinstance(damage, int | float):
            return False
        return damage > 0


def _space_runtime(context: object) -> SpaceRuntime | None:
    simulation = context if hasattr(context, "get_system") else getattr(context, "simulation", None)
    if simulation is None:
        return None
    space_runtime = getattr(simulation, "space_runtime", None)
    return space_runtime if isinstance(space_runtime, SpaceRuntime) else None
