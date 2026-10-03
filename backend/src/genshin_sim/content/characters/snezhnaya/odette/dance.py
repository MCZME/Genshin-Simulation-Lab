"""独舞倒影轮换：FRAME_STARTED 周期 hook 驱动的舞步攻击。

独舞倒影是**无 tick 行为的空间创建物**（位置固定于召唤点、持续时间 20s，
重召唤由 ``create_or_refresh`` 原生承载），轮换节奏由本 hook 驱动：下次
攻击帧与当前舞步（拂羽/旋翼）记在宿主角色内容状态，解释器在 E/Q/特殊战技
施放帧写入锚点（E 命中 +134f、Q 施放 +252f 且保留既有顺序、特殊战技施放
+114f 恢复），hook 到期帧读召唤物实体位置、按命中数据表索敌（圆柱 15
就近→「分数」策略）与 AOE（圆柱 4.0）解析命中集合后产出伤害请求，并推进
舞步交替（拂羽→旋翼 109f、旋翼→拂羽 125f）。

辉映状态下舞步为**双命中**（冰命中 + 额外的星变体命中，星超导/星扩散按
辉映证据分派，见 ``stellar.py``）；无辉映时只有冰命中。

到期帧找不到活动召唤物时解除轮换（写回 0），等待下一次 E/Q 重新锚定；
找不到可命中目标时舞步照常推进（只是不产出伤害请求），与游戏内「间歇性
攻击」语义一致。
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_DANCE_OBJECT_KEY,
    ODETTE_DANCE_PLUME_HIT,
    ODETTE_DANCE_PLUME_IMPACT_KEY,
    ODETTE_DANCE_PLUME_TO_WING_FRAMES,
    ODETTE_DANCE_SEARCH_RADIUS,
    ODETTE_DANCE_STEP_PLUME,
    ODETTE_DANCE_STEP_WING,
    ODETTE_DANCE_WING_HIT,
    ODETTE_DANCE_WING_IMPACT_KEY,
    ODETTE_DANCE_WING_TO_PLUME_FRAMES,
    ODETTE_STATE_SUMMON_NEXT_ATTACK_FRAME,
    ODETTE_STATE_SUMMON_NEXT_STEP,
)
from genshin_sim.content.characters.snezhnaya.odette.stellar import (
    OdetteStellarChannel,
    resolve_stellar_variant_spec,
)
from genshin_sim.content.hooks import HookContext
from genshin_sim.content.models import HookResult
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.space import (
    CreatedObjectRuntimeState,
    ImpactAreaSpec,
    SpatialEntityKind,
    Vector3,
)


class OdetteDanceError(RuntimeError):
    """独舞倒影轮换 hook 运行期错误（接线缺失或契约不完整）。"""


_STEP_HIT_DATA = {
    ODETTE_DANCE_STEP_PLUME: ODETTE_DANCE_PLUME_HIT,
    ODETTE_DANCE_STEP_WING: ODETTE_DANCE_WING_HIT,
}
_STEP_IMPACT_KEYS = {
    ODETTE_DANCE_STEP_PLUME: ODETTE_DANCE_PLUME_IMPACT_KEY,
    ODETTE_DANCE_STEP_WING: ODETTE_DANCE_WING_IMPACT_KEY,
}
_NEXT_STEP = {
    ODETTE_DANCE_STEP_PLUME: ODETTE_DANCE_STEP_WING,
    ODETTE_DANCE_STEP_WING: ODETTE_DANCE_STEP_PLUME,
}
_STEP_INTERVALS = {
    ODETTE_DANCE_STEP_PLUME: ODETTE_DANCE_PLUME_TO_WING_FRAMES,
    ODETTE_DANCE_STEP_WING: ODETTE_DANCE_WING_TO_PLUME_FRAMES,
}


class OdetteDanceHook:
    """按轮换状态在到期帧产出拂羽/旋翼舞步伤害请求。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        cryo_specs: dict[str, DamageImpactSpec],
        stellar_channels: dict[str, OdetteStellarChannel],
    ) -> None:
        if not owner_ref.strip():
            raise OdetteDanceError("独舞倒影轮换 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise OdetteDanceError("独舞倒影轮换 hook 必须绑定正整数队伍槽位")
        missing = [
            step
            for step in (ODETTE_DANCE_STEP_PLUME, ODETTE_DANCE_STEP_WING)
            if step not in cryo_specs or step not in stellar_channels
        ]
        if missing:
            raise OdetteDanceError(f"独舞倒影舞步契约缺失：{missing}")
        self._owner_ref = owner_ref
        self._slot = slot
        self._cryo_specs = dict(cryo_specs)
        self._stellar_channels = dict(stellar_channels)
        self.hook_key = f"odette.dance:{owner_ref}"
        self.state_key = ODETTE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("FRAME_STARTED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        if getattr(event, "event_type", None) is not EventType.FRAME_STARTED:
            return HookResult()
        frame = getattr(event, "frame", 0)
        if frame <= 0:
            return HookResult()

        hook_context = cast(HookContext, context)
        state = hook_context.state(self._owner_ref)
        next_attack = _as_frame(state.get(ODETTE_STATE_SUMMON_NEXT_ATTACK_FRAME))
        if next_attack <= 0 or frame < next_attack:
            return HookResult()
        raw_step = state.get(ODETTE_STATE_SUMMON_NEXT_STEP)
        step = raw_step if raw_step in _STEP_HIT_DATA else ODETTE_DANCE_STEP_PLUME

        summon = self._active_summon(hook_context, frame)
        disarm_patch = StatePatchRequest(
            owner_ref=self._owner_ref,
            state_key=self.state_key,
            fields={ODETTE_STATE_SUMMON_NEXT_ATTACK_FRAME: 0},
        )
        if summon is None:
            # 召唤物已过期/不存在：解除轮换，等待下一次 E/Q 重新锚定。
            return HookResult(state_patches=(disarm_patch,))

        advance_patch = StatePatchRequest(
            owner_ref=self._owner_ref,
            state_key=self.state_key,
            fields={
                ODETTE_STATE_SUMMON_NEXT_ATTACK_FRAME: frame + _STEP_INTERVALS[step],
                ODETTE_STATE_SUMMON_NEXT_STEP: _NEXT_STEP[step],
            },
        )
        target_refs = self._resolve_hit_targets(
            hook_context,
            step,
            summon.entity.position,
            summon.entity.facing,
        )
        if not target_refs:
            return HookResult(state_patches=(advance_patch,))
        requests = [self._cryo_request(step, frame, target_refs)]
        stellar_spec = resolve_stellar_variant_spec(
            self._stellar_channels[step],
            simulation=hook_context.simulation,
            owner_ref=self._owner_ref,
            frame=frame,
        )
        if stellar_spec is not None:
            requests.append(
                self._stellar_request(
                    self._stellar_channels[step].impact_key, frame, step, stellar_spec, target_refs
                )
            )
        return HookResult(
            impact_requests=tuple(requests),
            state_patches=(advance_patch,),
        )

    def _cryo_request(
        self,
        step: str,
        frame: int,
        target_refs: tuple[str, ...],
    ) -> ImpactRequest:
        request_id = f"hook:{self.hook_key}:{frame}:{step}"
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.DAMAGE,
            impact_key=_STEP_IMPACT_KEYS[step],
            owner_slot=self._slot,
            request_id=request_id,
            target_refs=target_refs,
            damage_spec=replace(
                self._cryo_specs[step],
                impact_ref=f"{request_id}:damage",
            ),
        )

    def _stellar_request(
        self,
        impact_key: str,
        frame: int,
        step: str,
        spec: DamageImpactSpec,
        target_refs: tuple[str, ...],
    ) -> ImpactRequest:
        request_id = f"hook:{self.hook_key}:{frame}:{step}:stellar"
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.DAMAGE,
            impact_key=impact_key,
            owner_slot=self._slot,
            request_id=request_id,
            target_refs=target_refs,
            damage_spec=replace(
                spec,
                impact_ref=f"{request_id}:damage",
            ),
        )

    def _active_summon(
        self, hook_context: HookContext, frame: int
    ) -> CreatedObjectRuntimeState | None:
        simulation = hook_context.simulation
        if simulation is None:
            return None
        space_runtime = simulation.space_runtime
        if space_runtime is None:
            return None
        owner_key = f"character:slot_{self._slot}"
        for obj in space_runtime.created_object_runtime.active_objects:
            if obj.object_key == ODETTE_DANCE_OBJECT_KEY and obj.entity.owner_key == owner_key:
                return obj
        return None

    def _resolve_hit_targets(
        self,
        hook_context: HookContext,
        step: str,
        summon_position: Vector3,
        summon_facing: Vector3,
    ) -> tuple[str, ...]:
        """索敌 + AOE：圆柱 15 就近选锚，锚点处圆柱 4.0 圈定命中集合。

        「就近」由「分数」策略承载（X/Z 就近、并列取稳定实体 id 较小者，
        sandrone 棱晶弹先例）；AOE 展开语义与动作影响点一致（以选中目标为
        锚点、随召唤物朝向旋转本地偏移）。
        """

        simulation = hook_context.simulation
        if simulation is None:
            return ()
        space_runtime = simulation.space_runtime
        if space_runtime is None:
            return ()
        candidates = space_runtime.entities_in_radius(
            summon_position,
            ODETTE_DANCE_SEARCH_RADIUS,
            kinds={SpatialEntityKind.TARGET},
        )
        if not candidates:
            return ()
        anchor = min(
            candidates,
            key=lambda entity: (entity.position.distance_xz_to(summon_position), entity.entity_id),
        )
        hit_data = _STEP_HIT_DATA[step]
        area = ImpactAreaSpec(
            shape=hit_data.aoe_shape,
            radius=hit_data.aoe_radius,
            local_offset_xz=hit_data.aoe_offset,
        ).resolve(anchor.position, summon_facing)
        entities = space_runtime.entities_in_area(area, kinds={SpatialEntityKind.TARGET})
        resolved = space_runtime.resolve_candidate_targets(
            tuple(entity.entity_id for entity in entities)
        )
        return tuple(candidate.target_id for candidate in resolved)


def _as_frame(raw: object) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        return 0
    return raw
