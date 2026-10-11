"""吃虎鱼刀被动的事件钩子：攻击命中时按概率对命中敌人追加一段攻击力伤害。

「攻击命中」按任意直接伤害判定（公式键为通用公式，排除超载爆炸等反应伤害）；
概率投点走装配期注入的仿真随机源（与西风系列同一条确定性随机序列）。触发
窗口保存为钩子实例字段（与西风系列一致）。

proc 本身携带「武器技能」主攻击标签（源数据为空标签，仿真契约要求非空，见
data.py 口径说明），因此不会触发其他「命中触发」被动（包括自身）。
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.sword.fillet_blade.data import (
    FILLET_BLADE_PROC_IMPACT_KEY,
)
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation.random_source import RandomSource
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL

# 敌方目标判据按 entity_id 前缀区分，与西风系列一致。
_ENEMY_TARGET_PREFIX = "target:"


class DecisiveProcError(Exception):
    """决部件运行期错误。"""


class DecisiveProcHook:
    """装备者攻击命中敌人时，按概率与间隔对命中目标追加一段攻击力伤害。"""

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        slot: int,
        damage_spec: DamageImpactSpec,
        interval_frames: int,
        probability: float,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("决 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("决 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("决必须绑定正整数队伍槽位")
        if not isinstance(damage_spec, DamageImpactSpec):
            raise ContentUnitValidationError("决 damage_spec 必须是 DamageImpactSpec")
        if damage_spec.area is not None:
            raise ContentUnitValidationError("决为单体追加伤害，不应携带 AOE 区域")
        if interval_frames <= 0:
            raise ContentUnitValidationError("决触发间隔必须为正帧数")
        if isinstance(probability, bool) or not isinstance(probability, int | float):
            raise ContentUnitValidationError("决触发概率必须是数字")
        if not 0.0 <= float(probability) <= 1.0:
            raise ContentUnitValidationError("决触发概率必须在 0 到 1 之间")
        self._owner_ref = owner_ref
        self._slot = slot
        self._damage_spec = damage_spec
        self._interval_frames = interval_frames
        self._probability = float(probability)
        self._last_proc_frame: int | None = None
        self.hook_key = f"{FILLET_BLADE_PROC_IMPACT_KEY}:{owner_ref}"
        self.state_key = handler_key
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def last_proc_frame(self) -> int | None:
        """最近一次成功追加伤害的帧；仅供测试与结果投影读取。"""

        return self._last_proc_frame

    def handle(self, event: object, context: object) -> HookResult:
        frame = getattr(event, "frame", 0)
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        if not isinstance(target_id, str) or not target_id.startswith(_ENEMY_TARGET_PREFIX):
            return HookResult()
        source_ref = getattr(result, "source_ref", None)
        if getattr(source_ref, "entity_id", None) != self._owner_ref:
            return HookResult()
        if getattr(result, "formula_key", None) != FORMULA_KEY_GENERAL:
            return HookResult()
        if not self._dealt_damage(result):
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            self._interval_frames
        ):
            return HookResult()
        if not self._roll_probability(context):
            return HookResult()
        request_id = f"hook:{self.hook_key}:{frame}"
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.DAMAGE,
                    impact_key=FILLET_BLADE_PROC_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=request_id,
                    target_refs=(target_id,),
                    damage_spec=replace(
                        self._damage_spec,
                        impact_ref=f"{request_id}:damage",
                    ),
                ),
            )
        )

    @staticmethod
    def _dealt_damage(result: object) -> bool:
        damage = getattr(result, "final_damage", None)
        if isinstance(damage, bool) or not isinstance(damage, int | float):
            return False
        return damage > 0

    def _roll_probability(self, context: object) -> bool:
        random_source = getattr(getattr(context, "simulation", None), "random_source", None)
        if random_source is None:
            raise DecisiveProcError(f"决缺少装配期注入的仿真随机源：{self.hook_key}")
        typed_source = cast("RandomSource", random_source)
        return typed_source.roll(self._probability)
