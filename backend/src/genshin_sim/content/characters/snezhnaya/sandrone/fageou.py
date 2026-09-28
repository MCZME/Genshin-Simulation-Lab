"""法洁欧与解算模式：内容专属状态机的 FRAME_STARTED 周期 hook。

法洁欧不做空间创建物：模式机（待机/解算/过载）与解算功率
（0–100）承载在角色内容状态挂载（state_key = handler key，与连段状态同
段），本 hook 每帧读取字段、推进功率动力学与双轨射击节奏，演化结果经
``state_patch`` 意图写回，射击/射线以影响请求产出、由同帧下一轮结算消费。

时序锚定约定：所有节奏字段存绝对帧（solve_start / next_shot / next_ray），
解释器在按下/松开帧经 ``state_patch`` 提交转移（round 0 结算，先于本帧
hook 运行），hook 是状态字段与当前帧的纯函数——转移与节奏均无漂移。

直线几何：瞄准方向取桑多涅实体 facing，出发点取其位置；
射线为长条 oriented box 一次穿透全部命中（即时结算、一条攻击根、多目标
聚合），子弹沿直线取首个交点（单一实例），飞行延迟在发射时按距离一次性
折算、经 hook 内 pending 队列在未来帧兑现（统一意图队列不支持未来帧到期，
采用内容 pending 退路）。

切人（宿主不在场）视为松开：解算退出并清节奏字段、过载按住停火保持模式，
两种情况都不再产出射击/射线，功率按后台倍率衰减；已在途的子弹请求按
原定结算帧兑现。
"""

from __future__ import annotations

from collections.abc import Mapping
from math import hypot
from typing import cast

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_BENCH_DECAY_MULTIPLIER,
    FAGEOU_BULLET_SPEED_M_PER_S,
    FAGEOU_DRAIN_PER_SECOND,
    FAGEOU_MODE_IDLE,
    FAGEOU_MODE_OVERLOAD,
    FAGEOU_MODE_SOLVE,
    FAGEOU_OVERLOAD_EXIT_POWER,
    FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES,
    FAGEOU_POWER_DECAY_PER_SECOND,
    FAGEOU_POWER_MAX,
    FAGEOU_POWER_RISE_PER_SECOND,
    FAGEOU_PRE_SWING_FRAMES,
    FAGEOU_RAY_FIRST_OFFSET_FRAMES,
    FAGEOU_RAY_HIT_POWER_GAIN,
    FAGEOU_RAY_INTERVAL_FRAMES,
    FAGEOU_RAY_LENGTH,
    FAGEOU_RAY_WIDTH,
    FAGEOU_SOLVE_SHOT_INTERVAL_FRAMES,
    FAGEOU_STATE_BEAM_BONUS,
    FAGEOU_STATE_DRAIN_ACTIVE,
    FAGEOU_STATE_EXTRA_SEGMENTS_LEFT,
    FAGEOU_STATE_MODE,
    FAGEOU_STATE_NEXT_RAY_FRAME,
    FAGEOU_STATE_NEXT_SHOT_FRAME,
    FAGEOU_STATE_POWER,
    FAGEOU_STATE_PRISM2_BOOST_UNTIL,
    FAGEOU_STATE_RAY_COUNT,
    FAGEOU_STATE_SOLVE_START_FRAME,
    FAGEOU_STATE_TACTICS_EXPIRE_FRAME,
    FAGEOU_STATE_TACTICS_STACKS,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_CHARGED_ATTACK_ACTION_KEY,
    SANDRONE_CHARGED_ATTACK_EXTRA_IMPACT_KEY,
    SANDRONE_CHARGED_ATTACK_OVERLOAD_IMPACT_KEY,
    SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
    SANDRONE_CHARGED_ATTACK_SWEEP_IMPACT_KEY,
    SANDRONE_P4_TACTICS_DURATION_FRAMES,
    SANDRONE_P4_TACTICS_MAX_STACKS,
    SANDRONE_P4_TACTICS_POWER_STEP,
    SANDRONE_RAY_INDEX_TAG_PREFIX,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    SandroneStellarAttackChannel,
    resolve_stellar_attack_spec,
)
from genshin_sim.content.generic.chain_state import chain_state_schema
from genshin_sim.content.hooks import HookContext
from genshin_sim.content.models import HookResult
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.space import (
    OrientedBoxArea,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID

FRAMES_PER_SECOND = 60.0


class SandroneFageouError(RuntimeError):
    """法洁欧状态机运行期错误（接线缺失或契约不完整）。"""


def sandrone_state_schema(owner_ref: str) -> StateSchema:
    """连段状态 + 法洁欧模式机 + 被动/命座字段的合并状态 schema。"""

    chain = chain_state_schema(owner_ref)
    machine = (
        StateField(
            name=FAGEOU_STATE_MODE,
            field_type=StateFieldType.ENUM,
            default=FAGEOU_MODE_IDLE,
            allowed_values=(FAGEOU_MODE_IDLE, FAGEOU_MODE_SOLVE, FAGEOU_MODE_OVERLOAD),
        ),
        StateField(
            name=FAGEOU_STATE_POWER,
            field_type=StateFieldType.FLOAT,
            default=0.0,
            non_negative=True,
            max_value=FAGEOU_POWER_MAX,
            clamp=True,
        ),
        StateField(
            name=FAGEOU_STATE_SOLVE_START_FRAME,
            field_type=StateFieldType.INT,
            default=0,
            non_negative=True,
        ),
        StateField(
            name=FAGEOU_STATE_NEXT_SHOT_FRAME,
            field_type=StateFieldType.INT,
            default=0,
            non_negative=True,
        ),
        StateField(
            name=FAGEOU_STATE_NEXT_RAY_FRAME,
            field_type=StateFieldType.INT,
            default=0,
            non_negative=True,
        ),
        StateField(
            name=FAGEOU_STATE_DRAIN_ACTIVE,
            field_type=StateFieldType.BOOL,
            default=False,
        ),
        StateField(
            name=FAGEOU_STATE_RAY_COUNT,
            field_type=StateFieldType.INT,
            default=0,
            non_negative=True,
        ),
        StateField(
            name=FAGEOU_STATE_EXTRA_SEGMENTS_LEFT,
            field_type=StateFieldType.INT,
            default=0,
            non_negative=True,
        ),
        StateField(
            name=FAGEOU_STATE_TACTICS_STACKS,
            field_type=StateFieldType.INT,
            default=0,
            non_negative=True,
            max_value=SANDRONE_P4_TACTICS_MAX_STACKS,
            clamp=True,
        ),
        StateField(
            name=FAGEOU_STATE_TACTICS_EXPIRE_FRAME,
            field_type=StateFieldType.INT,
            default=0,
            non_negative=True,
        ),
        StateField(
            name=FAGEOU_STATE_PRISM2_BOOST_UNTIL,
            field_type=StateFieldType.INT,
            default=0,
            non_negative=True,
        ),
        StateField(
            name=FAGEOU_STATE_BEAM_BONUS,
            field_type=StateFieldType.FLOAT,
            default=0.0,
            non_negative=True,
        ),
    )
    return StateSchema(owner_ref=owner_ref, fields=chain.fields + machine)


class SandroneFageouHook:
    """解算模式状态机：功率动力学 + 射击/射线双轨 + 直线几何命中。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        damage_specs: Mapping[str, DamageImpactSpec],
        stellar_channel: SandroneStellarAttackChannel | None = None,
        pre_swing_frames: int = FAGEOU_PRE_SWING_FRAMES,
        solve_shot_interval_frames: int = FAGEOU_SOLVE_SHOT_INTERVAL_FRAMES,
        overload_shot_interval_frames: int = FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES,
        ray_first_offset_frames: int = FAGEOU_RAY_FIRST_OFFSET_FRAMES,
        ray_interval_frames: int = FAGEOU_RAY_INTERVAL_FRAMES,
        power_rise_per_second: float = FAGEOU_POWER_RISE_PER_SECOND,
        ray_hit_power_gain: float = FAGEOU_RAY_HIT_POWER_GAIN,
        power_decay_per_second: float = FAGEOU_POWER_DECAY_PER_SECOND,
        bench_decay_multiplier: float = FAGEOU_BENCH_DECAY_MULTIPLIER,
        drain_per_second: float = FAGEOU_DRAIN_PER_SECOND,
        overload_exit_power: float = FAGEOU_OVERLOAD_EXIT_POWER,
        power_max: float = FAGEOU_POWER_MAX,
        ray_length: float = FAGEOU_RAY_LENGTH,
        ray_width: float = FAGEOU_RAY_WIDTH,
        bullet_speed_m_per_s: float = FAGEOU_BULLET_SPEED_M_PER_S,
        p4_unlocked: bool = False,
        c2_index_tag_enabled: bool = False,
        c6_extra_normal_spec: DamageImpactSpec | None = None,
        c6_extra_stellar_channel: SandroneStellarAttackChannel | None = None,
        c6_extra_segments: int = 0,
    ) -> None:
        missing = {
            SANDRONE_CHARGED_ATTACK_SWEEP_IMPACT_KEY,
            SANDRONE_CHARGED_ATTACK_OVERLOAD_IMPACT_KEY,
            SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
        } - set(damage_specs)
        if missing:
            raise SandroneFageouError(f"法洁欧缺少伤害契约：{sorted(missing)}")
        if c6_extra_segments and (c6_extra_normal_spec is None):
            raise SandroneFageouError("C6 追加段已启用但缺少普通段伤害契约")
        if c6_extra_stellar_channel is not None and c6_extra_segments == 0:
            raise SandroneFageouError("C6 星烁追加段通道在未启用追加段时不应存在")
        self._owner_ref = owner_ref
        self._slot = slot
        self._damage_specs: dict[str, DamageImpactSpec] = dict(damage_specs)
        self._stellar_channel = stellar_channel
        self._pre_swing_frames = pre_swing_frames
        self._solve_shot_interval = solve_shot_interval_frames
        self._overload_shot_interval = overload_shot_interval_frames
        self._ray_first_offset = ray_first_offset_frames
        self._ray_interval = ray_interval_frames
        self._rise_per_frame = power_rise_per_second / FRAMES_PER_SECOND
        self._ray_hit_gain = ray_hit_power_gain
        self._decay_per_frame = power_decay_per_second / FRAMES_PER_SECOND
        self._bench_decay_multiplier = bench_decay_multiplier
        self._drain_per_frame = drain_per_second / FRAMES_PER_SECOND
        self._overload_exit_power = overload_exit_power
        self._power_max = power_max
        self._ray_length = ray_length
        self._ray_width = ray_width
        self._bullet_speed_m_per_s = bullet_speed_m_per_s
        self._p4_unlocked = p4_unlocked
        self._c2_index_tag_enabled = c2_index_tag_enabled
        self._c6_extra_normal_spec = c6_extra_normal_spec
        self._c6_extra_stellar_channel = c6_extra_stellar_channel
        self._c6_extra_segments = c6_extra_segments
        self._pending: list[tuple[int, ImpactRequest, int]] = []
        self._request_counter = 0
        self.hook_key = f"sandrone.fageou:{owner_ref}"
        self.state_key = SANDRONE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("FRAME_STARTED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def handle(self, event: object, context: object) -> HookResult:
        if getattr(event, "event_type", None) is not EventType.FRAME_STARTED:
            return HookResult()
        frame = getattr(event, "frame", 0)
        if frame <= 0:
            return HookResult()

        hook_context = cast(HookContext, context)
        state = hook_context.state(self._owner_ref)
        requests = self._due_pending_requests(frame)
        fields: dict[str, JSONValue] = {}

        def put(name: str, value: JSONValue) -> None:
            if state.get(name) != value:
                fields[name] = value

        def as_number(name: str, default: float) -> float:
            raw = state.get(name, default)
            if isinstance(raw, bool) or not isinstance(raw, int | float):
                return default
            return float(raw)

        mode = state.get(FAGEOU_STATE_MODE, FAGEOU_MODE_IDLE)
        power = as_number(FAGEOU_STATE_POWER, 0.0)
        solve_start = int(as_number(FAGEOU_STATE_SOLVE_START_FRAME, 0))
        next_shot = int(as_number(FAGEOU_STATE_NEXT_SHOT_FRAME, 0))
        next_ray = int(as_number(FAGEOU_STATE_NEXT_RAY_FRAME, 0))
        drain_active = bool(state.get(FAGEOU_STATE_DRAIN_ACTIVE, False))
        ray_count = int(as_number(FAGEOU_STATE_RAY_COUNT, 0))
        extra_segments_left = int(as_number(FAGEOU_STATE_EXTRA_SEGMENTS_LEFT, 0))
        tactics_stacks = int(as_number(FAGEOU_STATE_TACTICS_STACKS, 0))
        tactics_expire = int(as_number(FAGEOU_STATE_TACTICS_EXPIRE_FRAME, 0))

        if tactics_stacks > 0 and frame >= tactics_expire:
            # P4 改进战术按统一过期帧整体失效（每次获得叠层刷新，见 data.py）。
            tactics_stacks = 0
            tactics_expire = 0
            put(FAGEOU_STATE_TACTICS_STACKS, tactics_stacks)
            put(FAGEOU_STATE_TACTICS_EXPIRE_FRAME, tactics_expire)

        if drain_active:
            # E 排空：约 0.5s 排满功率，排空期间停火。功率每
            # 跨越一个 10 点阈值获得一层改进战术（P4，突破 1 阶解锁；未解锁
            # 时排空只清功率不计层），满功率排空拿满 10 层。
            power_before = power
            power = max(0.0, power - self._drain_per_frame)
            if power <= 0.0:
                drain_active = False
            if self._p4_unlocked:
                crossings = int(power_before // SANDRONE_P4_TACTICS_POWER_STEP) - int(
                    power // SANDRONE_P4_TACTICS_POWER_STEP
                )
                if crossings > 0:
                    tactics_stacks = min(SANDRONE_P4_TACTICS_MAX_STACKS, tactics_stacks + crossings)
                    tactics_expire = frame + SANDRONE_P4_TACTICS_DURATION_FRAMES
                    put(FAGEOU_STATE_TACTICS_STACKS, tactics_stacks)
                    put(FAGEOU_STATE_TACTICS_EXPIRE_FRAME, tactics_expire)
            put(FAGEOU_STATE_POWER, power)
            put(FAGEOU_STATE_DRAIN_ACTIVE, drain_active)
            return self._result(fields, requests)

        off_field = self._is_off_field(hook_context)
        if off_field and mode == FAGEOU_MODE_SOLVE:
            # 切人视为松开：法洁欧不在场开火，解算退出并清节奏字段，功率
            # 转入后台衰减；回到场上后需重新按住重击进入解算。
            mode = FAGEOU_MODE_IDLE
            solve_start = 0
            next_shot = 0
            next_ray = 0
            put(FAGEOU_STATE_MODE, mode)
            put(FAGEOU_STATE_SOLVE_START_FRAME, solve_start)
            put(FAGEOU_STATE_NEXT_SHOT_FRAME, next_shot)
            put(FAGEOU_STATE_NEXT_RAY_FRAME, next_ray)
        elif off_field and mode == FAGEOU_MODE_OVERLOAD and next_shot:
            # 过载按住中切人：停火（清射击轨）并保持过载模式，功率按后台
            # 衰减直到跨越退出门回待机。
            next_shot = 0
            put(FAGEOU_STATE_NEXT_SHOT_FRAME, next_shot)

        if mode == FAGEOU_MODE_SOLVE:
            if frame >= solve_start:
                power = min(self._power_max, power + self._rise_per_frame)
            if next_shot and frame >= next_shot:
                # 子弹请求由 pending 队列在命中帧兑现，不在本轮直接产出。
                self._fire_bullet(hook_context, frame, SANDRONE_CHARGED_ATTACK_SWEEP_IMPACT_KEY)
                next_shot += self._solve_shot_interval
            if next_ray and frame >= next_ray and power < self._power_max:
                ray_count += 1
                # C6：自第 3 次发射冷凝射线起开启追加段记账（每会话一次），
                # 之后每条真正发射的射线各追加一段，至多 c6_extra_segments 段。
                if ray_count == 3 and self._c6_extra_segments > 0:
                    extra_segments_left = self._c6_extra_segments
                request, hit, targets = self._fire_ray(
                    hook_context,
                    frame,
                    ray_count=ray_count,
                )
                if request is not None:
                    requests.append(request)
                    if extra_segments_left > 0:
                        # 追加段叠加在射线之上：与伴随射线同帧、同命中集合，
                        # 不提供射线命中功率增量，也不改变射线节奏。
                        extra = self._fire_extra_segment(hook_context, frame, targets)
                        if extra is not None:
                            requests.append(extra)
                        extra_segments_left -= 1
                if hit:
                    power = min(self._power_max, power + self._ray_hit_gain)
                next_ray += self._ray_interval
            if power >= self._power_max:
                # 满功率进入过载：射击轨换节奏不重置相位。
                mode = FAGEOU_MODE_OVERLOAD
                next_shot = frame + self._overload_shot_interval
                next_ray = 0
        elif mode == FAGEOU_MODE_OVERLOAD:
            if next_shot:
                # 按住过载：功率冻结，30F 间隔过载射击无限持续。
                if frame >= next_shot:
                    self._fire_bullet(
                        hook_context,
                        frame,
                        SANDRONE_CHARGED_ATTACK_OVERLOAD_IMPACT_KEY,
                    )
                    next_shot += self._overload_shot_interval
            else:
                # 松开停火但模式保持过载，衰减跨越阈值后回待机。
                power = max(
                    0.0,
                    power - self._decay_per_frame * self._decay_multiplier(hook_context),
                )
                if power < self._overload_exit_power:
                    mode = FAGEOU_MODE_IDLE
        else:
            power = max(
                0.0,
                power - self._decay_per_frame * self._decay_multiplier(hook_context),
            )

        put(FAGEOU_STATE_MODE, mode)
        put(FAGEOU_STATE_POWER, power)
        put(FAGEOU_STATE_SOLVE_START_FRAME, solve_start)
        put(FAGEOU_STATE_NEXT_SHOT_FRAME, next_shot)
        put(FAGEOU_STATE_NEXT_RAY_FRAME, next_ray)
        put(FAGEOU_STATE_RAY_COUNT, ray_count)
        put(FAGEOU_STATE_EXTRA_SEGMENTS_LEFT, extra_segments_left)
        return self._result(fields, requests)

    def _result(
        self,
        fields: dict[str, JSONValue],
        requests: list[ImpactRequest],
    ) -> HookResult:
        patches = ()
        if fields:
            patches = (
                StatePatchRequest(
                    owner_ref=self._owner_ref,
                    state_key=self.state_key,
                    fields=fields,
                ),
            )
        return HookResult(impact_requests=tuple(requests), state_patches=patches)

    def _is_off_field(self, context: HookContext) -> bool:
        """宿主是否不在场：当前场上槽位存在且与宿主槽位不同。"""

        simulation = context.simulation
        if simulation is None:
            return False
        space_runtime = simulation.space_runtime
        if space_runtime is None:
            return False
        active_slot = space_runtime.team_state.active_slot
        return active_slot is not None and active_slot != self._slot

    def _decay_multiplier(self, context: HookContext) -> float:
        """后台衰减倍率：当前场角色为 1.0，宿主下场时 ×3（文本 300%）。"""

        if self._is_off_field(context):
            return self._bench_decay_multiplier
        return 1.0

    def _aim(self, context: HookContext) -> tuple[Vector3, Vector3] | None:
        """瞄准方向与出发点：桑多涅实体位置与 facing（X/Z 归一）。"""

        simulation = context.simulation
        if simulation is None:
            return None
        space_runtime = simulation.space_runtime
        if space_runtime is None:
            return None
        entity = space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID)
        if entity is None:
            return None
        length = hypot(entity.facing.x, entity.facing.z)
        if length == 0.0:
            return None
        direction = Vector3(x=entity.facing.x / length, y=0.0, z=entity.facing.z / length)
        return entity.position, direction

    def _resolve_ray_targets(
        self,
        context: HookContext,
        origin: Vector3,
        direction: Vector3,
    ) -> tuple[str, ...]:
        """射线穿透：以 facing 定向的长条 oriented box 一次求交全部命中。"""

        simulation = context.simulation
        if simulation is None:
            return ()
        space_runtime = simulation.space_runtime
        if space_runtime is None:
            return ()
        half = self._ray_length / 2
        area = OrientedBoxArea(
            center=Vector3(
                x=origin.x + direction.x * half,
                y=origin.y,
                z=origin.z + direction.z * half,
            ),
            facing=direction,
            length=self._ray_length,
            width=self._ray_width,
        )
        entities = space_runtime.entities_in_area(area, kinds={SpatialEntityKind.TARGET})
        candidates = space_runtime.resolve_candidate_targets(
            tuple(entity.entity_id for entity in entities)
        )
        return tuple(candidate.target_id for candidate in candidates)

    def _resolve_bullet(
        self,
        context: HookContext,
        origin: Vector3,
        direction: Vector3,
        frame: int,
    ) -> tuple[str, float] | None:
        """子弹直线求交：沿 facing 直线的首个交点（单一实例）。

        命中判定用敌人碰撞圆柱半径（|横向偏移| ≤ 半径、前向 > 0），延迟
        距离取起点到目标位置的 X/Z 距离。该规则按各实体自身的碰撞半径绕线
        判定，``entities_in_area`` 的区域命中只做实体中心点 contain，无法
        表达，因此按空间实体枚举自建求交；类型与生命周期过滤口径与区域
        查询一致。
        """

        simulation = context.simulation
        if simulation is None:
            return None
        space_runtime = simulation.space_runtime
        if space_runtime is None:
            return None
        right_x = -direction.z
        right_z = direction.x
        best: tuple[float, float, SpatialEntity] | None = None
        for entity in space_runtime.entities:
            if entity.kind is not SpatialEntityKind.TARGET or not entity.is_active_at(frame):
                continue
            delta_x = entity.position.x - origin.x
            delta_z = entity.position.z - origin.z
            forward = delta_x * direction.x + delta_z * direction.z
            if forward <= 0.0:
                continue
            right = delta_x * right_x + delta_z * right_z
            if abs(right) > entity.collision_box.radius:
                continue
            if best is None or forward < best[0]:
                best = (forward, hypot(delta_x, delta_z), entity)
        if best is None:
            return None
        _, distance, entity = best
        candidates = space_runtime.resolve_candidate_targets((entity.entity_id,))
        if not candidates:
            return None
        return candidates[0].target_id, distance

    def _fire_bullet(
        self,
        context: HookContext,
        frame: int,
        impact_key: str,
    ) -> bool:
        """子弹出膛：发射时解析直线几何并折算延迟帧，命中结算排未来帧。

        返回是否把子弹请求排入 pending 队列；请求由到期帧经 ``HookResult``
        兑现，不在本轮直接产出。
        """

        aim = self._aim(context)
        if aim is None:
            return False
        origin, direction = aim
        hit = self._resolve_bullet(context, origin, direction, frame)
        if hit is None:
            return False
        target_id, distance = hit
        delay_frames = int(round(distance / self._bullet_speed_m_per_s * FRAMES_PER_SECOND))
        resolve_frame = frame + delay_frames
        request = self._damage_request(
            frame=resolve_frame,
            impact_key=impact_key,
            target_refs=(target_id,),
        )
        self._pending.append((resolve_frame, request, self._request_counter))
        return True

    def _fire_ray(
        self,
        context: HookContext,
        frame: int,
        *,
        ray_count: int = 0,
    ) -> tuple[ImpactRequest | None, bool, tuple[str, ...]]:
        """射线即时结算：穿透多目标聚合为一条攻击根，命中返回功率增量证据。

        发射时按辉映状态查表分派：持用辉映·星超导/星扩散时射线契约切换为
        星变体并附组装好的星烁输入（stellar.py），否则走普通射线契约。
        C6 追加段由调用方另记为独立影响点，不改变本契约；C2 下请求携带
        射线会话序号附加标签供暴伤 provider 定向。
        """

        aim = self._aim(context)
        if aim is None:
            return None, False, ()
        origin, direction = aim
        targets = self._resolve_ray_targets(context, origin, direction)
        if not targets:
            return None, False, ()
        request = self._damage_request(
            frame=frame,
            impact_key=SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
            target_refs=targets,
            damage_spec=self._ray_damage_spec(context, frame),
            tags=self._ray_session_tags(ray_count),
        )
        return request, True, targets

    def _fire_extra_segment(
        self,
        context: HookContext,
        frame: int,
        targets: tuple[str, ...],
    ) -> ImpactRequest | None:
        """C6 追加段：与伴随射线同帧同命中集合，按辉映查表分派。

        普通段与星变体都由编译期从资产命座第 6 层效果行解析的契约承载
        （普通 100% 攻击力；星超导 80% / 星扩散 120%）。追加段不提供射线
        命中功率增量。
        """

        if self._c6_extra_normal_spec is None:
            return None
        damage_spec: DamageImpactSpec = self._c6_extra_normal_spec
        if self._c6_extra_stellar_channel is not None:
            stellar_spec = resolve_stellar_attack_spec(
                self._c6_extra_stellar_channel,
                simulation=getattr(context, "simulation", None),
                owner_ref=self._owner_ref,
                frame=frame,
            )
            if stellar_spec is not None:
                damage_spec = stellar_spec
        return self._damage_request(
            frame=frame,
            impact_key=SANDRONE_CHARGED_ATTACK_EXTRA_IMPACT_KEY,
            target_refs=targets,
            damage_spec=damage_spec,
        )

    def _ray_session_tags(self, ray_count: int) -> tuple[str, ...]:
        """C2 射线会话序号标签：由 provider 换算为逐射线暴伤（仅星超导冰）。"""

        if not self._c2_index_tag_enabled:
            return ()
        return (f"{SANDRONE_RAY_INDEX_TAG_PREFIX}{ray_count}",)

    def _ray_damage_spec(
        self,
        context: HookContext,
        frame: int,
    ) -> DamageImpactSpec:
        normal_spec = self._damage_specs[SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY]
        if self._stellar_channel is None:
            return normal_spec
        stellar_spec = resolve_stellar_attack_spec(
            self._stellar_channel,
            simulation=context.simulation,
            owner_ref=self._owner_ref,
            frame=frame,
        )
        return normal_spec if stellar_spec is None else stellar_spec

    def _damage_request(
        self,
        *,
        frame: int,
        impact_key: str,
        target_refs: tuple[str, ...],
        damage_spec: DamageImpactSpec | None = None,
        tags: tuple[str, ...] = (),
    ) -> ImpactRequest:
        self._request_counter += 1
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.DAMAGE,
            impact_key=impact_key,
            owner_slot=self._slot,
            action_key=SANDRONE_CHARGED_ATTACK_ACTION_KEY,
            request_id=f"{self.hook_key}:{impact_key}:{frame}:{self._request_counter}",
            target_refs=target_refs,
            tags=tags,
            damage_spec=damage_spec if damage_spec is not None else self._damage_specs[impact_key],
        )

    def _due_pending_requests(self, frame: int) -> list[ImpactRequest]:
        if not self._pending:
            return []
        due = [entry for entry in self._pending if entry[0] <= frame]
        if not due:
            return []
        self._pending = [entry for entry in self._pending if entry[0] > frame]
        due.sort(key=lambda entry: (entry[0], entry[2]))
        return [entry[1] for entry in due]
