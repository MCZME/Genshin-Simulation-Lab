"""砂糖大型风灵（元素爆发创建物）实体类型：按拍风伤 + 染色探测。

大型风灵注册为类型化创建实体（``type_key = sucrose.large_wind_spirit``），
承载元素爆发的持续输出与染色机制（实施规划 §11.3）。两条 tick 调度各司其职：

- ``attack``（周期 120f）：创建帧 +120 起拍、共 3 拍（137 / 257 / 377，相对
  施放帧）。到期先按索敌圆柱 15 +「分数」就近取锚点，再以锚点展开爆发圆柱
  AOE（r=8、偏移 (0, -2.5, 0)）解析命中集合后产出风伤请求；若染色已固定，
  同帧追加一段染色伤害请求并**复用同一目标集合**（染色行不单独索敌）；
- ``probe``（周期 18f）：创建帧 +18 起探，对判定区（攻击盒：前后 2.5 × 左右
  2.5，上下分量按项目 X/Z 模型忽略）内的敌人读元素附着，按 火 > 水 > 雷 > 冰
  取最高优先级附着元素并固定（第 4 档兼容 CRYO 与 FROZEN，均对应冰元素伤害）；
  命中即把本调度置 ``None`` 停机（首次探到即固定），始终未探到则保持纯风伤。

调度存储由创建物运行时基座持有，到期驱动、过期门控与追赶补发亦然；本类型
只负责「是什么与怎么再来」——配置解析、初始调度声明、请求产出与下一拍推进。
风灵与角色解耦：创建位置取自施放瞬间的当前场上角色，此后不跟随角色（切人 /
离场后继续按拍输出）。刷新（冷却结束后再次施放元素爆发）按新建语义重置节奏
与染色，不继承旧态。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ELEMENTAL_BURST_ACTION_KEY,
    SUCROSE_SPIRIT_ABSORPTION_PRIORITY,
    SUCROSE_SPIRIT_ANEMO_TICK_IMPACT_KEY,
    SUCROSE_SPIRIT_ATTACK_SCHEDULE_KEY,
    SUCROSE_SPIRIT_DURATION_FRAMES,
    SUCROSE_SPIRIT_OBJECT_KEY,
    SUCROSE_SPIRIT_PROBE_BOX_DEPTH,
    SUCROSE_SPIRIT_PROBE_BOX_LATERAL,
    SUCROSE_SPIRIT_PROBE_BOX_RADIUS,
    SUCROSE_SPIRIT_PROBE_BOX_SHAPE,
    SUCROSE_SPIRIT_PROBE_INTERVAL_FRAMES,
    SUCROSE_SPIRIT_PROBE_SCHEDULE_KEY,
    SUCROSE_SPIRIT_TICK_COUNT,
    SUCROSE_SPIRIT_TICK_PERIOD_FRAMES,
    SUCROSE_SPIRIT_WINDOW_FRAMES,
    SUCROSE_TALENT_FRAMES_PER_SECOND,
    SUCROSE_TARGETING,
)
from genshin_sim.content.characters.mondstadt.sucrose.impacts import (
    SucroseAbsorbedDamageChannel,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.elements import AuraKind, Element, ElementalSubjectRef
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.space import (
    CreatedObjectRuntimeState,
    CreatedObjectTickState,
    ImpactAreaSpec,
    SpatialEntityKind,
)
from genshin_sim.core.systems.aura import AuraRuntime

if TYPE_CHECKING:
    from genshin_sim.core.simulation.context import SimulationContext
    from genshin_sim.core.space import SpatialEntity


class SucroseSpiritError(RuntimeError):
    """大型风灵实体类型运行期错误（接线缺失或状态不一致）。"""


class SucroseSpiritRuntimeState(CreatedObjectRuntimeState):
    """大型风灵运行态：在基座上补充归属槽位与已固定的染色元素。"""

    def __init__(
        self,
        *,
        entity: SpatialEntity,
        type_key: str,
        schedules: Sequence[CreatedObjectTickState],
        owner_slot: int,
    ) -> None:
        super().__init__(
            entity=entity,
            type_key=type_key,
            schedules=schedules,
        )
        self.owner_slot = owner_slot
        # 染色判定结果：``None`` 表示尚未探到（保持纯风伤）；一旦固定不再变更。
        self.absorbed_element: Element | None = None


def resolve_spirit_timing(extra_seconds: int = 0) -> tuple[int, int, int]:
    """按「窗口延长秒数」解出 ``(窗口帧数, 生命周期帧数, 拍数)``。

    C2 把爆发窗口延长 2 秒（6s → 8s），拍数随之由 3 拍变 4 拍（137 / 257 /
    377 / 497）；窗口、生命周期与拍数三者必须同源，否则会出现「窗口 8s 却只
    打 3 拍」或「打出第 5 拍」这类漂移，故统一由本函数派生：

    - 窗口帧数 = 基础窗口 + 延长秒数 × 60；
    - 拍数 = 窗口帧数 ÷ 拍周期（整除，基础 360 / 120 = 3、延长后 480 / 120 = 4）；
    - 生命周期 = 窗口 + 1（末拍正好落在窗口端点，过期判据不含端点帧）。

    ``SucroseSpiritType`` 构造时还会按这三者再校验一次（``_validate_tick_budget``）。
    """

    if isinstance(extra_seconds, bool) or not isinstance(extra_seconds, int) or extra_seconds < 0:
        raise ContentUnitValidationError("大型风灵窗口延长秒数必须为非负整数")
    window_frames = SUCROSE_SPIRIT_WINDOW_FRAMES + extra_seconds * SUCROSE_TALENT_FRAMES_PER_SECOND
    tick_count = window_frames // SUCROSE_SPIRIT_TICK_PERIOD_FRAMES
    if tick_count <= 0:
        raise ContentUnitValidationError("大型风灵窗口过短：不足一拍")
    return window_frames, window_frames + 1, tick_count


class SucroseSpiritType:
    """大型风灵创建实体类型：双调度（按拍风伤 / 染色探测）。

    实例在内容编译期构造并持有编译期依赖（队伍槽位、风伤契约、染色通道）；
    实例级配置（施放入口）经创建请求的 ``config`` 在 ``build_state`` 解析。
    """

    type_key = SUCROSE_SPIRIT_OBJECT_KEY

    def __init__(
        self,
        *,
        slot: int,
        anemo_spec: DamageImpactSpec,
        absorbed_channel: SucroseAbsorbedDamageChannel,
        duration_frames: int = SUCROSE_SPIRIT_DURATION_FRAMES,
        tick_count: int = SUCROSE_SPIRIT_TICK_COUNT,
    ) -> None:
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("大型风灵实体类型必须绑定正整数队伍槽位")
        if not isinstance(anemo_spec, DamageImpactSpec):
            raise ContentUnitValidationError("大型风灵风伤契约必须是 DamageImpactSpec")
        if anemo_spec.area is None:
            raise ContentUnitValidationError("大型风灵风伤契约缺少 AOE 区域")
        if not isinstance(absorbed_channel, SucroseAbsorbedDamageChannel):
            raise ContentUnitValidationError("大型风灵染色通道必须是 SucroseAbsorbedDamageChannel")
        search_area = SUCROSE_TARGETING.search_area
        if search_area is None:
            raise ContentUnitValidationError("砂糖索敌规格缺少搜索区域")
        self._validate_tick_budget(duration_frames, tick_count)
        self._slot = slot
        self._duration_frames = duration_frames
        self._tick_count = tick_count
        self._anemo_spec = anemo_spec
        self._anemo_area = anemo_spec.area
        self._absorbed_channel = absorbed_channel
        self._search_radius = float(search_area.radius)
        # 判定区以风灵自身为原点（本地偏移为零），随创建物朝向旋转。
        self._probe_area = ImpactAreaSpec(
            shape=SUCROSE_SPIRIT_PROBE_BOX_SHAPE,
            radius=SUCROSE_SPIRIT_PROBE_BOX_RADIUS,
            length=SUCROSE_SPIRIT_PROBE_BOX_DEPTH,
            width=SUCROSE_SPIRIT_PROBE_BOX_LATERAL,
        )

    @staticmethod
    def _validate_tick_budget(duration_frames: int, tick_count: int) -> None:
        """校验「按拍数 × 周期 × 生命周期」三者自洽（声明即约束）。

        第 k 拍落在创建帧 + k × 周期：末拍须早于过期帧（``frame < 创建帧 +
        生命周期``，否则被过期门控丢弃），且再下一拍须不早于过期帧（否则会多
        出一拍）。三者任一处漂移都会在这里确定性失败，避免静默变成 2 拍 / 4 拍。

        C2 把窗口延长 2 秒后这组数值整体变化（480 / 481 / 4 拍），故三者都按
        实例取值校验，不再读模块常量。
        """

        if isinstance(duration_frames, bool) or not isinstance(duration_frames, int):
            raise ContentUnitValidationError("大型风灵生命周期必须是整数帧数")
        if duration_frames <= 0:
            raise ContentUnitValidationError("大型风灵生命周期必须为正帧数")
        if isinstance(tick_count, bool) or not isinstance(tick_count, int) or tick_count <= 0:
            raise ContentUnitValidationError("大型风灵按拍数必须为正整数")
        last_tick = tick_count * SUCROSE_SPIRIT_TICK_PERIOD_FRAMES
        next_tick = last_tick + SUCROSE_SPIRIT_TICK_PERIOD_FRAMES
        if not last_tick < duration_frames <= next_tick:
            raise ContentUnitValidationError(
                "大型风灵按拍预算与生命周期不自洽："
                f"{tick_count} 拍 × {SUCROSE_SPIRIT_TICK_PERIOD_FRAMES} 帧 "
                f"对不上生命周期 {duration_frames} 帧"
            )

    @property
    def duration_frames(self) -> int:
        """生命周期帧数（C2 延长后为 8s 窗口 + 1）。"""

        return self._duration_frames

    @property
    def tick_count(self) -> int:
        """按拍数（C2 延长后为 4 拍）。"""

        return self._tick_count

    def build_state(
        self,
        config: Mapping[str, object],
        entity: SpatialEntity,
        frame: int,
        previous: CreatedObjectRuntimeState | None,
    ) -> CreatedObjectRuntimeState:
        entry = config.get("entry")
        if entry != SUCROSE_ELEMENTAL_BURST_ACTION_KEY:
            raise ContentUnitValidationError(f"大型风灵创建配置 entry 非法：{entry!r}")
        # 刷新按新建语义处理：节奏与染色都从创建帧重开，不继承旧态。
        del previous
        return SucroseSpiritRuntimeState(
            entity=entity,
            type_key=self.type_key,
            schedules=(
                CreatedObjectTickState(
                    schedule_key=SUCROSE_SPIRIT_ATTACK_SCHEDULE_KEY,
                    next_tick_frame=frame + SUCROSE_SPIRIT_TICK_PERIOD_FRAMES,
                ),
                CreatedObjectTickState(
                    schedule_key=SUCROSE_SPIRIT_PROBE_SCHEDULE_KEY,
                    next_tick_frame=frame + SUCROSE_SPIRIT_PROBE_INTERVAL_FRAMES,
                ),
            ),
            owner_slot=self._slot,
        )

    def on_tick(
        self,
        state: CreatedObjectRuntimeState,
        schedule: CreatedObjectTickState,
        frame: int,
        context: SimulationContext,
    ) -> Sequence[ImpactRequest]:
        if not isinstance(state, SucroseSpiritRuntimeState):
            raise SucroseSpiritError("大型风灵 tick 收到非本类型运行态")
        if schedule.schedule_key == SUCROSE_SPIRIT_ATTACK_SCHEDULE_KEY:
            # 推进基于原定 tick 帧：无目标（空放）也照常按拍推进节奏。
            schedule.next_tick_frame = frame + SUCROSE_SPIRIT_TICK_PERIOD_FRAMES
            return self._attack_requests(state, frame, context)
        if schedule.schedule_key == SUCROSE_SPIRIT_PROBE_SCHEDULE_KEY:
            return self._probe_tick(state, schedule, frame, context)
        raise SucroseSpiritError(f"大型风灵未知 tick 调度：{schedule.schedule_key}")

    # ------------------------------------------------------------------
    # attack：索敌 + AOE，产出风伤；已染色时同帧追加染色伤害（共用目标集合）。
    # ------------------------------------------------------------------
    def _attack_requests(
        self,
        state: SucroseSpiritRuntimeState,
        frame: int,
        context: SimulationContext,
    ) -> tuple[ImpactRequest, ...]:
        target_refs = self._resolve_attack_targets(context, state)
        if not target_refs:
            return ()
        request_id = f"tick:{state.entity.entity_id}:{frame}:{SUCROSE_SPIRIT_ATTACK_SCHEDULE_KEY}"
        requests: list[ImpactRequest] = [
            ImpactRequest(
                frame=frame,
                kind=ImpactKind.DAMAGE,
                impact_key=SUCROSE_SPIRIT_ANEMO_TICK_IMPACT_KEY,
                owner_slot=self._slot,
                request_id=request_id,
                target_refs=target_refs,
                damage_spec=replace(
                    self._anemo_spec,
                    impact_ref=f"{request_id}:damage",
                ),
            )
        ]
        absorbed_element = state.absorbed_element
        if absorbed_element is not None:
            # request_id 内嵌染色通道的 impact_key（与动作影响点的请求同惯例）：
            # 「爆发发生了元素转化」在运行期只能由这段伤害观测到（C6 的触发
            # 判据读的就是它），故身份里必须带通道键，不能只有 tick 序号。
            absorbed_id = f"{request_id}:{self._absorbed_channel.impact_key}"
            requests.append(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.DAMAGE,
                    impact_key=self._absorbed_channel.impact_key,
                    owner_slot=self._slot,
                    request_id=absorbed_id,
                    target_refs=target_refs,
                    damage_spec=self._absorbed_channel.build(
                        absorbed_element,
                        impact_ref=f"{absorbed_id}:damage",
                    ),
                )
            )
        return tuple(requests)

    def _resolve_attack_targets(
        self,
        context: SimulationContext,
        state: SucroseSpiritRuntimeState,
    ) -> tuple[str, ...]:
        """索敌 + AOE：圆柱 15 就近取锚点，锚点处展开爆发圆柱 AOE（r=8）。

        「就近」由项目「分数」策略承载（X/Z 就近、并列取 ``entity_id`` 较小者，
        奥黛塔舞步 / 桑多涅棱晶弹先例）；AOE 展开语义与动作影响点一致（以选中
        目标为锚点、随风灵朝向旋转本地偏移），锚点只取一个。
        """

        space_runtime = context.space_runtime
        if space_runtime is None:
            return ()
        candidates = space_runtime.entities_in_radius(
            state.entity.position,
            self._search_radius,
            kinds={SpatialEntityKind.TARGET},
        )
        if not candidates:
            return ()
        anchor = min(
            candidates,
            key=lambda entity: (
                entity.position.distance_xz_to(state.entity.position),
                entity.entity_id,
            ),
        )
        area = self._anemo_area.resolve(anchor.position, state.entity.facing)
        entities = space_runtime.entities_in_area(area, kinds={SpatialEntityKind.TARGET})
        resolved = space_runtime.resolve_candidate_targets(
            tuple(entity.entity_id for entity in entities)
        )
        return tuple(candidate.target_id for candidate in resolved)

    # ------------------------------------------------------------------
    # probe：判定区内读元素附着，首次探到即固定并停机。
    # ------------------------------------------------------------------
    def _probe_tick(
        self,
        state: SucroseSpiritRuntimeState,
        schedule: CreatedObjectTickState,
        frame: int,
        context: SimulationContext,
    ) -> tuple[ImpactRequest, ...]:
        """染色探测：命中最优先附着元素即固定并停机，否则按周期续探。"""

        if state.absorbed_element is not None:
            raise SucroseSpiritError("大型风灵染色已固定但探测调度仍在运行")
        element = self._probe_absorbed_element(context, state)
        if element is None:
            schedule.next_tick_frame = frame + SUCROSE_SPIRIT_PROBE_INTERVAL_FRAMES
            return ()
        state.absorbed_element = element
        # 首次探到即固定：停机后续探测（置 None 由运行时基座放过自推进校验）。
        schedule.next_tick_frame = None
        return ()

    def _probe_absorbed_element(
        self,
        context: SimulationContext,
        state: SucroseSpiritRuntimeState,
    ) -> Element | None:
        """读判定区内敌人的元素附着，按优先级取最高者（无附着返回 ``None``）。

        优先级顺序取内容数据表（火 > 水 > 雷 > 冰，第 4 档兼容 CRYO 与 FROZEN，
        两者均对应冰元素伤害）；先把区内目标的附着种类并集再比优先级，与目标
        遍历顺序无关（结果确定性）。风灵自身不读角色附着，只判定「敌人」。
        """

        entities = self._probe_entities(context, state)
        if not entities:
            return None
        aura_runtime = context.get_system(AuraRuntime)
        if not isinstance(aura_runtime, AuraRuntime):
            raise SucroseSpiritError("缺少 AuraRuntime，无法读取大型风灵判定区内的元素附着")
        present: set[AuraKind] = set()
        for entity in entities:
            view = aura_runtime.view(ElementalSubjectRef.target(entity.entity_id))
            present.update(component.aura_kind for component in view.components)
        if not present:
            return None
        for aura_kind, element in SUCROSE_SPIRIT_ABSORPTION_PRIORITY:
            if aura_kind in present:
                return element
        return None

    def _probe_entities(
        self,
        context: SimulationContext,
        state: SucroseSpiritRuntimeState,
    ) -> tuple[SpatialEntity, ...]:
        """判定区（攻击盒）内的敌人：盒体以风灵自身为原点、随风灵朝向旋转。"""

        space_runtime = context.space_runtime
        if space_runtime is None:
            return ()
        area = self._probe_area.resolve(state.entity.position, state.entity.facing)
        return space_runtime.entities_in_area(area, kinds={SpatialEntityKind.TARGET})
