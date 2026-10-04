"""独舞倒影舞步：创建物自身 tick 调度驱动的拂羽/旋翼轮换攻击。

独舞倒影是带双 tick 调度的空间创建物（持续 20s，重召唤由 ``create_or_refresh``
原生承载）：拂羽/旋翼各一条独立调度，周期均为 234f（拂羽→旋翼 109f + 旋翼→
拂羽 125f），首拍错开 109f，展开后即交替轮换。调度状态（下次攻击帧）由创建
物运行态持有——E/Q 施放经 CREATE_ENTITY 的 ``tick_schedules`` 参数锚定节奏
（E 重召唤重置为拂羽首拍、Q 重召唤保留既有顺序，见 ``impacts.py``），特殊战
技施放经 ``ALIGN_CREATED_ENTITY_TICKS`` 请求把调度重锚到施放 +114f（相位保持）。
到期帧由本模块注册的 tick 行为读召唤物实体位置、按命中数据表索敌（圆柱 15
就近→「分数」策略）与 AOE（圆柱 4.0）解析命中集合后产出伤害请求。

辉映状态下舞步为**双命中**（冰命中 + 额外的星变体命中，星超导/星扩散按
辉映证据分派，见 ``stellar.py``）；无辉映时只有冰命中。

tick 到期早于召唤物过期帧才触发（创建物运行时原生承载，过期即停）；找不到
可命中目标时不产出伤害请求，节奏照常推进，与游戏内「间歇性攻击」语义一致。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_DANCE_PLUME_HIT,
    ODETTE_DANCE_PLUME_IMPACT_KEY,
    ODETTE_DANCE_SEARCH_RADIUS,
    ODETTE_DANCE_STEP_PLUME,
    ODETTE_DANCE_STEP_WING,
    ODETTE_DANCE_WING_HIT,
    ODETTE_DANCE_WING_IMPACT_KEY,
)
from genshin_sim.content.characters.snezhnaya.odette.stellar import (
    OdetteStellarChannel,
    resolve_stellar_variant_spec,
)
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.space import (
    CreatedObjectRuntimeState,
    ImpactAreaSpec,
    SpatialEntityKind,
)

if TYPE_CHECKING:
    from genshin_sim.core.simulation.context import SimulationContext
    from genshin_sim.core.space import Vector3


class OdetteDanceError(RuntimeError):
    """独舞倒影舞步行为运行期错误（接线缺失或契约不完整）。"""


_STEP_HIT_DATA = {
    ODETTE_DANCE_STEP_PLUME: ODETTE_DANCE_PLUME_HIT,
    ODETTE_DANCE_STEP_WING: ODETTE_DANCE_WING_HIT,
}
_STEP_IMPACT_KEYS = {
    ODETTE_DANCE_STEP_PLUME: ODETTE_DANCE_PLUME_IMPACT_KEY,
    ODETTE_DANCE_STEP_WING: ODETTE_DANCE_WING_IMPACT_KEY,
}


class OdetteDanceStepBehavior:
    """单条舞步的 tick 行为：就近索敌 + AOE 圈定命中集合，产出冰+星双命中。

    每条舞步调度各持一个行为实例（behavior_key = ``odette.dance_reflection.
    plume`` / ``.wing``），到期帧由创建物运行时回调；行为本身无帧状态，轮换
    节奏完全由调度状态承载。
    """

    def __init__(
        self,
        *,
        step: str,
        slot: int,
        cryo_spec: DamageImpactSpec,
        stellar_channel: OdetteStellarChannel,
    ) -> None:
        if step not in _STEP_IMPACT_KEYS:
            raise OdetteDanceError(f"未知独舞倒影舞步：{step}")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise OdetteDanceError("独舞倒影舞步行为必须绑定正整数队伍槽位")
        self._step = step
        self._slot = slot
        self._cryo_spec = cryo_spec
        self._stellar_channel = stellar_channel

    @property
    def step(self) -> str:
        return self._step

    def create_tick_requests(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
        context: SimulationContext,
    ) -> Sequence[ImpactRequest]:
        target_refs = self._resolve_hit_targets(
            context,
            state.entity.position,
            state.entity.facing,
        )
        if not target_refs:
            return ()
        requests = [self._cryo_request(state, frame, target_refs)]
        stellar_spec = resolve_stellar_variant_spec(
            self._stellar_channel,
            simulation=context,
            owner_ref=f"character:slot_{self._slot}",
            frame=frame,
        )
        if stellar_spec is not None:
            requests.append(self._stellar_request(state, frame, stellar_spec, target_refs))
        return tuple(requests)

    def _cryo_request(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
        target_refs: tuple[str, ...],
    ) -> ImpactRequest:
        impact_key = _STEP_IMPACT_KEYS[self._step]
        request_id = f"tick:{state.entity.entity_id}:{frame}:{self._step}"
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.DAMAGE,
            impact_key=impact_key,
            owner_slot=self._slot,
            request_id=request_id,
            target_refs=target_refs,
            damage_spec=replace(
                self._cryo_spec,
                impact_ref=f"{request_id}:damage",
            ),
        )

    def _stellar_request(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
        spec: DamageImpactSpec,
        target_refs: tuple[str, ...],
    ) -> ImpactRequest:
        impact_key = self._stellar_channel.impact_key
        request_id = f"tick:{state.entity.entity_id}:{frame}:{self._step}:stellar"
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

    def _resolve_hit_targets(
        self,
        simulation: SimulationContext,
        summon_position: Vector3,
        summon_facing: Vector3,
    ) -> tuple[str, ...]:
        """索敌 + AOE：圆柱 15 就近选锚，锚点处圆柱 4.0 圈定命中集合。

        「就近」由「分数」策略承载（X/Z 就近、并列取稳定实体 id 较小者，
        sandrone 棱晶弹先例）；AOE 展开语义与动作影响点一致（以选中目标为
        锚点、随召唤物朝向旋转本地偏移）。
        """

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
        hit_data = _STEP_HIT_DATA[self._step]
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
