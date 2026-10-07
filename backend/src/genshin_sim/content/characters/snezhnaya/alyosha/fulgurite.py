"""轰霆猎场创建实体：单一实体、双攻击通道（轰霆猎场 AoE tick + 图加林撕咬）。

轰霆猎场是空间中的一个实体，其范围就是它的大小；该实体发起两个独立攻击——
轰霆猎场 AoE tick（范围内所有敌人）与图加林撕咬（单体）。
时序全部锚定施放帧：首拍/首咬偏移由创建请求 config 携带（绝对帧），此后固定
120 帧间隔推进；无敌人时图加林仍按期执行攻击动作（咬空气），调度无条件推进。

图加林索敌：范围内有弋猎印记的敌人则优先攻击（多个取其中
最近者），没有则直接取全范围最近者——印记前置筛选 + 组内就近；激活（清除）
印记并触发猎者之准由 REMOVE_STATUS 影响请求 + ``BUFF_REMOVED`` hook 编排。

P4/C4 与图加林攻击动作同步：每次撕咬 tick 固定产出（不要求命中，咬空气也
回血），P4 治疗当前场上角色、C4 治疗生命百分比最低角色（全员满血时按槽位
并列取 1 号位）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_BURST_FIELD_TICK_IMPACT_KEY,
    ALYOSHA_BURST_TUGARIN_BITE_IMPACT_KEY,
    ALYOSHA_FIELD_TICK_AOE_OFFSET,
    ALYOSHA_FIELD_TICK_AOE_RADIUS,
    ALYOSHA_FIELD_TICK_PERIOD_FRAMES,
    ALYOSHA_FIELD_TICK_SCHEDULE_KEY,
    ALYOSHA_FULGURITE_OBJECT_KEY,
    ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
    ALYOSHA_TUGARIN_BITE_PERIOD_FRAMES,
    ALYOSHA_TUGARIN_BITE_SCHEDULE_KEY,
    ALYOSHA_TUGARIN_SEARCH_RADIUS,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeSubjectRef,
)
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.space import SpatialEntity, SpatialEntityKind
from genshin_sim.core.space.created_objects import (
    CreatedObjectRuntimeState,
    CreatedObjectTickState,
)
from genshin_sim.core.space.geometry import ImpactAreaSpec
from genshin_sim.core.systems.buff import BuffRuntime
from genshin_sim.core.systems.health import HealthRuntime


@dataclass(frozen=True, slots=True)
class FulguriteHealChannel:
    """P4/C4 回血通道配置（开关与数值由角色工厂按解锁状态装配）。

    ``atk_ratio`` 为回复量占阿罗夏攻击力的比例（资产效果行 components 直出）。
    """

    impact_key: str
    component_key: str
    atk_ratio: float

    def __post_init__(self) -> None:
        if isinstance(self.atk_ratio, bool) or not isinstance(self.atk_ratio, int | float):
            raise ContentUnitValidationError("轰霆猎场回血通道比例必须是数字")
        if self.atk_ratio <= 0.0:
            raise ContentUnitValidationError("轰霆猎场回血通道比例必须为正数")


class AlyoshaFulguriteFieldType:
    """轰霆猎场创建实体类型：双 tick 调度、图加林索敌与周期回血。"""

    def __init__(
        self,
        *,
        slot: int,
        field_spec: DamageImpactSpec,
        bite_spec: DamageImpactSpec,
        c2_apply_mark: bool,
        mark_duration_frames: int,
        p4_heal: FulguriteHealChannel | None = None,
        c4_heal: FulguriteHealChannel | None = None,
    ) -> None:
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("轰霆猎场类型必须绑定正整数队伍槽位")
        self._slot = slot
        self._field_spec = field_spec
        self._bite_spec = bite_spec
        self._c2_apply_mark = bool(c2_apply_mark)
        self._mark_duration_frames = mark_duration_frames
        self._p4_heal = p4_heal
        self._c4_heal = c4_heal
        # 类属性形态的 type_key（与 CreatedEntityType 协议的可变属性兼容）。
        self.type_key = ALYOSHA_FULGURITE_OBJECT_KEY

    def build_state(
        self,
        config: Mapping[str, object],
        entity: SpatialEntity,
        frame: int,
        previous: CreatedObjectRuntimeState | None,
    ) -> CreatedObjectRuntimeState:
        del frame, previous
        field_first = _require_config_frame(config, "field_first_tick_frame")
        bite_first = _require_config_frame(config, "tugarin_first_bite_frame")
        return CreatedObjectRuntimeState(
            entity=entity,
            type_key=self.type_key,
            schedules=(
                CreatedObjectTickState(
                    schedule_key=ALYOSHA_FIELD_TICK_SCHEDULE_KEY,
                    next_tick_frame=field_first,
                ),
                CreatedObjectTickState(
                    schedule_key=ALYOSHA_TUGARIN_BITE_SCHEDULE_KEY,
                    next_tick_frame=bite_first,
                ),
            ),
        )

    def on_tick(
        self,
        state: CreatedObjectRuntimeState,
        schedule: CreatedObjectTickState,
        frame: int,
        context: SimulationContext,
    ) -> tuple[ImpactRequest, ...]:
        if schedule.schedule_key == ALYOSHA_FIELD_TICK_SCHEDULE_KEY:
            schedule.next_tick_frame = frame + ALYOSHA_FIELD_TICK_PERIOD_FRAMES
            return self._field_tick_requests(state, frame, context)
        if schedule.schedule_key == ALYOSHA_TUGARIN_BITE_SCHEDULE_KEY:
            schedule.next_tick_frame = frame + ALYOSHA_TUGARIN_BITE_PERIOD_FRAMES
            return self._tugarin_bite_requests(state, frame, context)
        raise ContentUnitValidationError(f"轰霆猎场未知 tick 调度：{schedule.schedule_key}")

    # ------------------------------------------------------------------
    # 轰霆猎场 AoE tick：范围内所有敌人。
    # ------------------------------------------------------------------
    def _field_tick_requests(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
        context: Any,
    ) -> tuple[ImpactRequest, ...]:
        request_id = f"tick:{state.entity.entity_id}:{frame}:{ALYOSHA_FIELD_TICK_SCHEDULE_KEY}"
        targets = self._targets_in_field_area(context, state)
        if not targets:
            return ()
        return (
            ImpactRequest(
                frame=frame,
                kind=ImpactKind.DAMAGE,
                impact_key=ALYOSHA_BURST_FIELD_TICK_IMPACT_KEY,
                owner_slot=self._slot,
                request_id=request_id,
                target_refs=targets,
                damage_spec=replace(self._field_spec, impact_ref=f"{request_id}:damage"),
            ),
        )

    def _targets_in_field_area(
        self,
        context: Any,
        state: CreatedObjectRuntimeState,
    ) -> tuple[str, ...]:
        space_runtime = _space_runtime(context)
        if space_runtime is None:
            return ()
        area = ImpactAreaSpec(
            shape="圆柱",
            radius=ALYOSHA_FIELD_TICK_AOE_RADIUS,
            local_offset_xz=ALYOSHA_FIELD_TICK_AOE_OFFSET,
        ).resolve(state.entity.position, state.entity.facing)
        entities = space_runtime.entities_in_area(area, kinds={SpatialEntityKind.TARGET})
        candidates = space_runtime.resolve_candidate_targets(
            tuple(entity.entity_id for entity in entities)
        )
        return tuple(candidate.target_id for candidate in candidates)

    # ------------------------------------------------------------------
    # 图加林撕咬：印记前置筛选 + 组内就近；激活印记并触发周期回血。
    # ------------------------------------------------------------------
    def _tugarin_bite_requests(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
        context: Any,
    ) -> tuple[ImpactRequest, ...]:
        bite = self._resolve_bite_target(context, state, frame)
        requests: list[ImpactRequest] = []
        if bite is not None:
            bite_entity_id = bite.entity_id
            if self._c2_apply_mark:
                requests.append(self._mark_apply_request(frame, bite_entity_id))
            request_id = (
                f"tick:{state.entity.entity_id}:{frame}:{ALYOSHA_TUGARIN_BITE_SCHEDULE_KEY}"
            )
            requests.append(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.DAMAGE,
                    impact_key=ALYOSHA_BURST_TUGARIN_BITE_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=request_id,
                    target_refs=(bite.target_id,),
                    damage_spec=replace(self._bite_spec, impact_ref=f"{request_id}:damage"),
                ),
            )
            # 攻击激活（清除）印记；CONSUMED 原因由 BUFF_REMOVED hook 转授
            # 猎者之准。C2 施加的印记随本次攻击一并激活（先施加 → 攻击激活）。
            requests.append(self._mark_consume_request(frame, bite_entity_id))
        # P4/C4 与攻击动作同步：无目标（咬空气）也固定产出。
        if self._p4_heal is not None:
            requests.append(self._heal_request(frame, self._p4_heal, ("player:active",)))
        if self._c4_heal is not None:
            c4_target = self._lowest_hp_character(context, frame)
            if c4_target is not None:
                requests.append(self._heal_request(frame, self._c4_heal, (c4_target,)))
        return tuple(requests)

    def _mark_apply_request(self, frame: int, entity_id: str) -> ImpactRequest:
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.APPLY_STATUS,
            impact_key="alyosha.c2_mark_apply",
            owner_slot=self._slot,
            request_id=f"tick:mark_apply:{frame}:{entity_id}",
            target_refs=(entity_id,),
            params={
                "buff": {
                    "definition_key": ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
                    "duration_frames": self._mark_duration_frames,
                }
            },
        )

    def _mark_consume_request(self, frame: int, entity_id: str) -> ImpactRequest:
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.REMOVE_STATUS,
            impact_key="alyosha.mark_consume",
            owner_slot=self._slot,
            request_id=f"tick:mark_consume:{frame}:{entity_id}",
            target_refs=(entity_id,),
            params={
                "buff_remove": {
                    "definition_key": ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
                    "reason": "consumed",
                }
            },
        )

    def _heal_request(
        self,
        frame: int,
        channel: FulguriteHealChannel,
        target_refs: tuple[str, ...],
    ) -> ImpactRequest:
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.HEAL,
            impact_key=channel.impact_key,
            owner_slot=self._slot,
            request_id=f"tick:heal:{frame}:{channel.component_key}",
            target_refs=target_refs,
            params={
                "heal": {
                    "healing_id": f"tick:{frame}:{channel.component_key}",
                    "scaling_terms": (
                        {
                            "component_key": channel.component_key,
                            "attribute_key": STAT_ATK_TOTAL.value,
                            "coefficient": channel.atk_ratio,
                        },
                    ),
                    "flat_healing": 0.0,
                    "tags": (),
                }
            },
        )

    def _resolve_bite_target(
        self,
        context: Any,
        state: CreatedObjectRuntimeState,
        frame: int,
    ) -> _BiteCandidate | None:
        """印记前置筛选 + 组内就近。"""

        space_runtime = _space_runtime(context)
        if space_runtime is None:
            return None
        entities = space_runtime.entities_in_radius(
            state.entity.position,
            ALYOSHA_TUGARIN_SEARCH_RADIUS,
            kinds={SpatialEntityKind.TARGET},
        )
        if not entities:
            return None
        buff_runtime = _buff_runtime(context)
        candidates = tuple(
            _BiteCandidate(
                entity_id=entity.entity_id,
                distance=entity.position.distance_xz_to(state.entity.position),
                marked=(
                    buff_runtime is not None
                    and bool(
                        buff_runtime.reader.active(
                            frame,
                            target_ref=AttributeSubjectRef.target(entity.entity_id),
                            definition_key=ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
                        )
                    )
                ),
            )
            for entity in entities
        )
        marked = [candidate for candidate in candidates if candidate.marked]
        pool = marked or list(candidates)
        return min(pool, key=lambda candidate: (candidate.distance, candidate.entity_id))

    def _lowest_hp_character(self, context: Any, frame: int) -> str | None:
        """C4 目标：生命百分比最低角色，并列（含全员满血）取最低槽位。"""

        simulation = _simulation(context)
        if simulation is None:
            return None
        space_runtime = getattr(simulation, "space_runtime", None)
        if space_runtime is None or space_runtime.team_state is None:
            return None
        health = simulation.get_system(HealthRuntime)
        if health is None:
            return None
        ratios: list[tuple[float, int, str]] = []
        for character in space_runtime.team_state.characters:
            subject = AttributeSubjectRef.character(character.combat_entity_id)
            ratios.append((health.get_hp_ratio(subject, frame), character.slot, subject.entity_id))
        if not ratios:
            return None
        return min(ratios)[2]


@dataclass(frozen=True, slots=True)
class _BiteCandidate:
    entity_id: str
    distance: float
    marked: bool

    @property
    def target_id(self) -> str:
        return self.entity_id


def _require_config_frame(config: Any, key: str) -> int:
    if not isinstance(config, dict):
        raise ContentUnitValidationError("轰霆猎场创建 config 必须是映射")
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContentUnitValidationError(f"轰霆猎场创建 config 缺少合法 {key}")
    return value


def _space_runtime(context: Any):
    # on_tick 的 context 是 SimulationContext 本体（space_runtime 直接挂载）；
    # 兼容包装形态（context.simulation）以覆盖测试注入。
    runtime = getattr(context, "space_runtime", None)
    if runtime is not None:
        return runtime
    simulation = getattr(context, "simulation", None)
    return getattr(simulation, "space_runtime", None)


def _simulation(context: Any):
    return context if hasattr(context, "get_system") else getattr(context, "simulation", None)


def _buff_runtime(context: Any) -> BuffRuntime | None:
    simulation = _simulation(context)
    if simulation is None:
        return None
    runtime = simulation.get_system(BuffRuntime)
    return runtime if isinstance(runtime, BuffRuntime) else None
