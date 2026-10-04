"""独舞倒影实体类型：创建物自身 tick 调度驱动的拂羽/旋翼轮换攻击。

独舞倒影注册为类型化创建实体（``type_key = odette.dance_reflection``）：
拂羽/旋翼各一条独立 tick 调度，周期均为 234f（拂羽→旋翼 109f + 旋翼→拂羽
125f），首拍错开 109f，展开后即交替轮换。调度存储由创建物运行时基座持有，
到期驱动与过期门控亦然；本类型负责"是什么与怎么再来"——

- ``build_state``：解析创建配置（``entry``：elemental_skill/elemental_burst；
  ``preserve_order``：Q 重召唤保留既有顺序），声明初始调度。E 重召唤忽略
  旧态、从拂羽重开；Q 重召唤经 ``previous`` 读旧调度相位、从当前下一拍继续；
- ``on_tick``：到期帧先把调度推进到原定帧 + 234f（无论是否命中目标，
  节奏照常交替），再读召唤物实体位置、按命中数据表索敌（圆柱 15 就近→
  「分数」策略）与 AOE（圆柱 4.0）解析命中集合后产出伤害请求。

辉映状态下舞步为**双命中**（冰命中 + 额外的星变体命中，星超导/星扩散按
辉映证据分派，见 ``stellar.py``）；无辉映时只有冰命中。

tick 到期早于召唤物过期帧才触发（创建物运行时原生承载，过期即停）；找不到
可命中目标时不产出伤害请求，节奏照常推进，与游戏内「间歇性攻击」语义一致。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_DANCE_FIRST_ATTACK_AFTER_BURST_FRAMES,
    ODETTE_DANCE_FIRST_ATTACK_AFTER_E_HIT_FRAMES,
    ODETTE_DANCE_OBJECT_KEY,
    ODETTE_DANCE_PLUME_HIT,
    ODETTE_DANCE_PLUME_IMPACT_KEY,
    ODETTE_DANCE_PLUME_SCHEDULE_KEY,
    ODETTE_DANCE_PLUME_TO_WING_FRAMES,
    ODETTE_DANCE_SEARCH_RADIUS,
    ODETTE_DANCE_STEP_PERIOD_FRAMES,
    ODETTE_DANCE_STEP_PLUME,
    ODETTE_DANCE_STEP_WING,
    ODETTE_DANCE_WING_HIT,
    ODETTE_DANCE_WING_IMPACT_KEY,
    ODETTE_DANCE_WING_SCHEDULE_KEY,
    ODETTE_DANCE_WING_TO_PLUME_FRAMES,
    ODETTE_ELEMENTAL_BURST_ACTION_KEY,
    ODETTE_ELEMENTAL_BURST_SUMMON_FRAME,
    ODETTE_ELEMENTAL_SKILL_ACTION_KEY,
)
from genshin_sim.content.characters.snezhnaya.odette.stellar import (
    OdetteStellarChannel,
    resolve_stellar_variant_spec,
)
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.space import (
    CreatedObjectRuntimeState,
    CreatedObjectTickState,
    ImpactAreaSpec,
    SpatialEntityKind,
)

if TYPE_CHECKING:
    from genshin_sim.core.simulation.context import SimulationContext
    from genshin_sim.core.space import SpatialEntity, Vector3


class OdetteDanceError(RuntimeError):
    """独舞倒影实体类型运行期错误（接线缺失或契约不完整）。"""


_STEP_HIT_DATA = {
    ODETTE_DANCE_STEP_PLUME: ODETTE_DANCE_PLUME_HIT,
    ODETTE_DANCE_STEP_WING: ODETTE_DANCE_WING_HIT,
}
_STEP_IMPACT_KEYS = {
    ODETTE_DANCE_STEP_PLUME: ODETTE_DANCE_PLUME_IMPACT_KEY,
    ODETTE_DANCE_STEP_WING: ODETTE_DANCE_WING_IMPACT_KEY,
}


class OdetteDanceReflectionType:
    """独舞倒影创建实体类型：双舞步调度声明 + 冰/星双命中产出。

    实例在内容编译期构造并持有编译期依赖（队伍槽位、舞步伤害契约与星烁
    通道）；实例级配置（施放入口、是否保留顺序）经创建请求的 ``config``
    在 ``build_state`` 解析。
    """

    type_key = ODETTE_DANCE_OBJECT_KEY

    def __init__(
        self,
        *,
        slot: int,
        cryo_specs: Mapping[str, DamageImpactSpec],
        stellar_channels: Mapping[str, OdetteStellarChannel],
    ) -> None:
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise OdetteDanceError("独舞倒影实体类型必须绑定正整数队伍槽位")
        missing = [
            step
            for step in (ODETTE_DANCE_STEP_PLUME, ODETTE_DANCE_STEP_WING)
            if step not in cryo_specs or step not in stellar_channels
        ]
        if missing:
            raise OdetteDanceError(f"独舞倒影舞步契约缺失：{missing}")
        self._slot = slot
        self._cryo_specs = dict(cryo_specs)
        self._stellar_channels = dict(stellar_channels)

    def build_state(
        self,
        config: Mapping[str, object],
        entity: SpatialEntity,
        frame: int,
        previous: CreatedObjectRuntimeState | None,
    ) -> CreatedObjectRuntimeState:
        entry = config.get("entry")
        if entry not in (ODETTE_ELEMENTAL_SKILL_ACTION_KEY, ODETTE_ELEMENTAL_BURST_ACTION_KEY):
            raise OdetteDanceError(f"独舞倒影创建配置 entry 非法：{entry!r}")
        raw_preserve = config.get("preserve_order", False)
        if not isinstance(raw_preserve, bool):
            raise OdetteDanceError("独舞倒影创建配置 preserve_order 必须是布尔值")
        schedules = self._initial_schedules(
            entry=entry,
            preserve_order=raw_preserve,
            previous=previous,
            frame=frame,
        )
        return CreatedObjectRuntimeState(
            entity=entity,
            type_key=self.type_key,
            schedules=schedules,
        )

    def on_tick(
        self,
        state: CreatedObjectRuntimeState,
        schedule: CreatedObjectTickState,
        frame: int,
        context: SimulationContext,
    ) -> Sequence[ImpactRequest]:
        if schedule.schedule_key not in _STEP_HIT_DATA:
            raise OdetteDanceError(f"独舞倒影未知舞步调度：{schedule.schedule_key}")
        step = schedule.schedule_key
        # 推进基于原定 tick 帧：无论是否命中目标都照常交替（间歇性攻击语义），
        # 追赶补发时按原定节奏落帧。
        schedule.next_tick_frame = frame + ODETTE_DANCE_STEP_PERIOD_FRAMES
        target_refs = self._resolve_hit_targets(
            context,
            state.entity.position,
            state.entity.facing,
            step,
        )
        if not target_refs:
            return ()
        requests = [self._cryo_request(state, frame, step, target_refs)]
        stellar_spec = resolve_stellar_variant_spec(
            self._stellar_channels[step],
            simulation=context,
            owner_ref=f"character:slot_{self._slot}",
            frame=frame,
        )
        if stellar_spec is not None:
            requests.append(self._stellar_request(state, frame, step, stellar_spec, target_refs))
        return tuple(requests)

    def _initial_schedules(
        self,
        *,
        entry: str,
        preserve_order: bool,
        previous: CreatedObjectRuntimeState | None,
        frame: int,
    ) -> tuple[CreatedObjectTickState, ...]:
        """按施放入口构建拂羽/旋翼两条调度（next 为绝对帧）。

        E（重新召唤）：命中帧 +134f 拂羽首拍、+109f 后旋翼接拍；Q：施放
        +252f 首击（创建帧为施放第 1 帧，故首拍偏移 251），``preserve_order``
        且旧态存在时保留拂羽/旋翼顺序（从旧调度最早一拍的舞步继续），否则
        从拂羽起拍。
        """

        if entry == ODETTE_ELEMENTAL_SKILL_ACTION_KEY:
            plume_offset = ODETTE_DANCE_FIRST_ATTACK_AFTER_E_HIT_FRAMES
            wing_offset = plume_offset + ODETTE_DANCE_PLUME_TO_WING_FRAMES
        else:
            first_offset = (
                ODETTE_DANCE_FIRST_ATTACK_AFTER_BURST_FRAMES - ODETTE_ELEMENTAL_BURST_SUMMON_FRAME
            )
            next_step = self._preserved_next_step(previous) if preserve_order else None
            if next_step == ODETTE_DANCE_STEP_WING:
                plume_offset = first_offset + ODETTE_DANCE_WING_TO_PLUME_FRAMES
                wing_offset = first_offset
            else:
                plume_offset = first_offset
                wing_offset = first_offset + ODETTE_DANCE_PLUME_TO_WING_FRAMES
        return (
            CreatedObjectTickState(
                schedule_key=ODETTE_DANCE_PLUME_SCHEDULE_KEY,
                next_tick_frame=frame + plume_offset,
            ),
            CreatedObjectTickState(
                schedule_key=ODETTE_DANCE_WING_SCHEDULE_KEY,
                next_tick_frame=frame + wing_offset,
            ),
        )

    @staticmethod
    def _preserved_next_step(previous: CreatedObjectRuntimeState | None) -> str | None:
        """读旧运行态调度中最早一拍的舞步（无可用调度时返回 ``None``）。"""

        if previous is None:
            return None
        due = [
            (schedule.next_tick_frame, schedule.schedule_key)
            for schedule in previous.schedules
            if schedule.next_tick_frame is not None
        ]
        if not due:
            return None
        return min(due)[1]

    def _cryo_request(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
        step: str,
        target_refs: tuple[str, ...],
    ) -> ImpactRequest:
        impact_key = _STEP_IMPACT_KEYS[step]
        request_id = f"tick:{state.entity.entity_id}:{frame}:{step}"
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.DAMAGE,
            impact_key=impact_key,
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
        state: CreatedObjectRuntimeState,
        frame: int,
        step: str,
        spec: DamageImpactSpec,
        target_refs: tuple[str, ...],
    ) -> ImpactRequest:
        impact_key = self._stellar_channels[step].impact_key
        request_id = f"tick:{state.entity.entity_id}:{frame}:{step}:stellar"
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
        step: str,
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
