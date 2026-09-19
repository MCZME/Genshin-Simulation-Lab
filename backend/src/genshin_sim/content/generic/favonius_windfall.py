"""generic 西风系列武器被动「顺风而行」部件。

不带键：本模块只承载与具体武器无关的判定条件、资产参数解读与事件钩子实现。
西风系列各武器在自己的内容包里声明 ``handler_key`` 与 Impact 键，包装时传给
这里的钩子；钩子不自带任何武器级键。

钩子订阅 ``DAMAGE_RESOLVED`` 事实，只读取事实与只读上下文，只产出下一轮结算要
消费的 ``ImpactRequest``，不直接写能量或任何领域状态。

触发窗口保存为钩子实例字段（``_last_proc_frame``）：
``ContentCompiler._register_state_schema`` 对每个宿主只允许一个内容状态挂载，
武器挂载到宿主体上会与宿主角色自身的状态段冲突；当前也没有快照恢复链路需要
折叠还原该窗口。一旦引入快照恢复或重放，窗口必须迁到内容状态挂载，并同步放宽
“一个宿主一个 state schema”的装配约束。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import cast

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.random_source import RandomSource
from genshin_sim.core.systems.damage import CritOutcome

# 本部件声明的帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
WINDFALL_FRAMES_PER_SECOND = 60

# 产球形态：3 个无元素微粒。资产效果参数不含数量与元素，由本部件声明。
WINDFALL_PICKUP_KIND = "particle"
WINDFALL_PICKUP_ELEMENT = "clear"
WINDFALL_PARTICLE_COUNT = 3

# 载体延迟抽样区间（闭区间，工程约定，不是游戏真值）。
WINDFALL_TRAVEL_FRAMES_MIN = 20
WINDFALL_TRAVEL_FRAMES_MAX = 50

# 本部件对资产效果参数的位置约定：components[0] 是触发概率，components[1] 是
# 间隔秒数，两者的 values 都按精炼顺序给出取值。资产参数的整体形态由资产侧决定，
# 装配层不承诺也不校验它（见 D-080），因此这里的解析规则是本部件的实现细节。
_PROBABILITY_INDEX = 0
_INTERVAL_SECONDS_INDEX = 1
_REQUIRED_COMPONENT_COUNT = 2

# 敌方目标判据按 entity_id 前缀区分，不按目标类型字段。
_ENEMY_TARGET_PREFIX = "target:"


class FavoniusWindfallError(Exception):
    """顺风而行部件运行期错误。"""


class FavoniusWindfallHook:
    """顺风而行：暴击命中敌人时，在触发窗口内按概率产出无元素微粒。

    ``handler_key`` 是包装本部件的内容包 handler 键，用于状态归属与产球标签；
    ``impact_key`` 是该内容包声明的 Impact 键，用于产出身份与钩子键。
    """

    def __init__(
        self,
        *,
        handler_key: str,
        impact_key: str,
        owner_ref: str,
        slot: int,
        probability: float,
        interval_frames: int,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("顺风而行 handler_key 必须是非空字符串")
        if not isinstance(impact_key, str) or not impact_key.strip():
            raise ContentUnitValidationError("顺风而行 impact_key 必须是非空字符串")
        if isinstance(probability, bool) or not isinstance(probability, int | float):
            raise ContentUnitValidationError("顺风而行触发概率必须是数字")
        if not 0.0 <= float(probability) <= 1.0:
            raise ContentUnitValidationError("顺风而行触发概率必须在 0 到 1 之间")
        if isinstance(interval_frames, bool) or not isinstance(interval_frames, int):
            raise ContentUnitValidationError("顺风而行触发间隔必须是整数帧数")
        if interval_frames <= 0:
            raise ContentUnitValidationError("顺风而行触发间隔必须为正帧数")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("顺风而行必须绑定正整数队伍槽位")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("顺风而行 owner_ref 必须是非空字符串")
        self._handler_key = handler_key
        self._impact_key = impact_key
        self._owner_ref = owner_ref
        self._slot = slot
        self._probability = float(probability)
        self._interval_frames = interval_frames
        self._last_proc_frame: int | None = None
        self.hook_key = f"{impact_key}:{owner_ref}"
        self.state_key = handler_key
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def last_proc_frame(self) -> int | None:
        """最近一次成功触发的帧；仅供测试与结果投影读取。"""

        return self._last_proc_frame

    def handle(self, event: object, context: object) -> HookResult:
        frame = getattr(event, "frame", 0)
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        if not self._is_owner_result(result):
            return HookResult()
        if not self._hit_enemy(result):
            return HookResult()
        if getattr(result, "crit_outcome", None) is not CritOutcome.CRITICAL:
            return HookResult()
        if not self._dealt_damage(result):
            return HookResult()
        if not self._owner_on_field(context):
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            self._interval_frames
        ):
            return HookResult()
        random_source = getattr(getattr(context, "simulation", None), "random_source", None)
        if random_source is None:
            raise FavoniusWindfallError(f"顺风而行缺少装配期注入的仿真随机源：{self.hook_key}")
        typed_source = cast("RandomSource", random_source)
        if not typed_source.roll(self._probability):
            return HookResult()
        travel_frames = roll_travel_frames(typed_source)
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=self._impact_key,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "spawn_pickup",
                            "pickup_kind": WINDFALL_PICKUP_KIND,
                            "element": WINDFALL_PICKUP_ELEMENT,
                            "count": WINDFALL_PARTICLE_COUNT,
                            "travel_frames": travel_frames,
                            "tags": [self._handler_key],
                        }
                    },
                ),
            )
        )

    def _is_owner_result(self, result: object) -> bool:
        source_ref = getattr(result, "source_ref", None)
        return getattr(source_ref, "entity_id", None) == self._owner_ref

    @staticmethod
    def _hit_enemy(result: object) -> bool:
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        return isinstance(target_id, str) and target_id.startswith(_ENEMY_TARGET_PREFIX)

    @staticmethod
    def _dealt_damage(result: object) -> bool:
        damage = getattr(result, "final_damage", None)
        if isinstance(damage, bool) or not isinstance(damage, int | float):
            return False
        return damage > 0

    def _owner_on_field(self, context: object) -> bool:
        states = getattr(context, "states", None)
        active_slot = getattr(states, "active_slot", None)
        return active_slot == self._slot


def roll_travel_frames(random_source: RandomSource) -> int:
    """按闭区间常数抽取一次载体延迟，固定消耗随机源的 1 次取值。"""

    span = WINDFALL_TRAVEL_FRAMES_MAX - WINDFALL_TRAVEL_FRAMES_MIN + 1
    return WINDFALL_TRAVEL_FRAMES_MIN + int(random_source.next() * span)


def windfall_parameters(
    params: Mapping[str, object],
    refinement: int,
) -> tuple[float, int]:
    """按资产效果参数与精炼返回（触发概率, 触发间隔帧数）。

    参数缺失、精炼越界或取值非法都在组装阶段失败，不静默回退默认值。
    """

    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("顺风而行精炼必须是整数")

    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or len(components) < _REQUIRED_COMPONENT_COUNT
    ):
        raise ContentUnitValidationError(
            "顺风而行缺少资产效果参数：components 需同时给出触发概率与间隔秒数"
        )

    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"顺风而行精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
            f"实际 {refinement}"
        )

    offset = refinement - refinement_min
    probability = _component_value(components[_PROBABILITY_INDEX], offset, label="触发概率")
    interval_seconds = _component_value(
        components[_INTERVAL_SECONDS_INDEX], offset, label="触发间隔"
    )
    if not 0.0 <= probability <= 1.0:
        raise ContentUnitValidationError(f"顺风而行触发概率必须在 0 到 1 之间，实际 {probability}")
    if interval_seconds <= 0.0:
        raise ContentUnitValidationError(f"顺风而行触发间隔必须为正数秒，实际 {interval_seconds}")
    return probability, round(interval_seconds * WINDFALL_FRAMES_PER_SECOND)


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"顺风而行缺少资产效果参数 {key}（整数）")
    return value


def _component_value(component: object, offset: int, *, label: str) -> float:
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"顺风而行{label}分量必须是对象")
    values = component.get("values")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ContentUnitValidationError(f"顺风而行{label}分量缺少 values 序列")
    if offset >= len(values):
        raise ContentUnitValidationError(
            f"顺风而行{label}分量的 values 未覆盖该精炼（需要下标 {offset}，实际 {len(values)} 项）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"顺风而行{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number):
        raise ContentUnitValidationError(f"顺风而行{label}分量在该精炼下不是有限数值")
    return number
