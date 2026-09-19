"""西风长枪顺风而行的事件钩子。

钩子订阅 ``DAMAGE_RESOLVED`` 事实，本身只读取事实与只读上下文，只产出下一轮
结算要消费的 ``ImpactRequest``，不直接写能量或任何领域状态。

触发窗口保存为钩子实例字段（``_last_proc_frame``）：
``ContentCompiler._register_state_schema`` 对每个宿主只允许一个内容状态挂载，
武器挂载到宿主体上会与宿主角色自身的状态段冲突；当前也没有快照恢复链路需要
折叠还原该窗口。一旦引入快照恢复或重放，窗口必须迁到内容状态挂载，并同步放宽
“一个宿主一个 state schema”的装配约束。
"""

from __future__ import annotations

from typing import cast

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.polearm.favonius_lance.data import (
    FAVONIUS_LANCE_HANDLER_KEY,
    FAVONIUS_LANCE_PARTICLE_COUNT,
    FAVONIUS_LANCE_PICKUP_ELEMENT,
    FAVONIUS_LANCE_PICKUP_KIND,
    FAVONIUS_LANCE_TRAVEL_FRAMES_MAX,
    FAVONIUS_LANCE_TRAVEL_FRAMES_MIN,
    FAVONIUS_LANCE_WINDFALL_IMPACT_KEY,
)
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.random_source import RandomSource
from genshin_sim.core.systems.damage import CritOutcome

_ENEMY_TARGET_PREFIX = "target:"


class FavoniusLanceHookError(Exception):
    """顺风而行钩子运行期错误。"""


class FavoniusLanceWindfallHook:
    """顺风而行：暴击命中敌人时，在触发窗口内按概率产出无元素微粒。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        probability: float,
        interval_frames: int,
    ) -> None:
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
        self._owner_ref = owner_ref
        self._slot = slot
        self._probability = float(probability)
        self._interval_frames = interval_frames
        self._last_proc_frame: int | None = None
        self.hook_key = f"weapon.favonius_lance.windfall:{owner_ref}"
        self.state_key = FAVONIUS_LANCE_HANDLER_KEY
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
            raise FavoniusLanceHookError(f"顺风而行缺少装配期注入的仿真随机源：{self.hook_key}")
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
                    impact_key=FAVONIUS_LANCE_WINDFALL_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "spawn_pickup",
                            "pickup_kind": FAVONIUS_LANCE_PICKUP_KIND,
                            "element": FAVONIUS_LANCE_PICKUP_ELEMENT,
                            "count": FAVONIUS_LANCE_PARTICLE_COUNT,
                            "travel_frames": travel_frames,
                            "tags": ["weapon.favonius_lance"],
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

    span = FAVONIUS_LANCE_TRAVEL_FRAMES_MAX - FAVONIUS_LANCE_TRAVEL_FRAMES_MIN + 1
    return FAVONIUS_LANCE_TRAVEL_FRAMES_MIN + int(random_source.next() * span)
