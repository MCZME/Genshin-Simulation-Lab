"""generic 武器被动的「命中触发追加伤害」部件。

不带键：判定条件、资产参数解读与钩子实现与具体武器无关；proc 伤害契约
（元素、倍率分量、主攻击标签、显示名）由各武器内容包编译后传入。

钩子订阅 ``DAMAGE_RESOLVED`` 事实，只读取事实与只读上下文，只产出下一轮结算要
消费的 ``ImpactRequest``，不直接写任何领域状态。触发窗口保存为钩子实例字段
（与西风系列一致）：``ContentCompiler`` 对每个宿主只允许一个内容状态挂载；
一旦引入快照恢复或重放，窗口必须迁到内容状态挂载。
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation.random_source import RandomSource
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL

# 敌方目标判据按 entity_id 前缀区分，与西风系列一致。
_ENEMY_TARGET_PREFIX = "target:"


class HitProcDamageError(Exception):
    """命中追加伤害部件运行期错误。"""


class HitProcDamageHook:
    """装备者攻击命中敌人时，按间隔（可选概率门控）对命中目标追加一段伤害。

    ``attack_tags`` 是触发用主攻击标签集合（如「普通攻击」）；传空元组表示
    「任意直接伤害命中」（公式键为通用公式，排除反应伤害）。proc 本身携带
    独立的主攻击标签，因此不会触发其他「命中触发」被动（包括自身）。
    """

    def __init__(
        self,
        *,
        handler_key: str,
        impact_key: str,
        owner_ref: str,
        slot: int,
        damage_spec: DamageImpactSpec,
        attack_tags: tuple[str, ...],
        interval_frames: int,
        probability: float = 1.0,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("命中追加伤害 handler_key 必须是非空字符串")
        if not isinstance(impact_key, str) or not impact_key.strip():
            raise ContentUnitValidationError("命中追加伤害 impact_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("命中追加伤害 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("命中追加伤害必须绑定正整数队伍槽位")
        if not isinstance(damage_spec, DamageImpactSpec):
            raise ContentUnitValidationError("命中追加伤害 damage_spec 必须是 DamageImpactSpec")
        if damage_spec.area is not None:
            raise ContentUnitValidationError("单体命中追加伤害不应携带 AOE 区域")
        tags = tuple(attack_tags)
        if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise ContentUnitValidationError("命中追加伤害 attack_tags 必须是非空字符串元组")
        if isinstance(interval_frames, bool) or not isinstance(interval_frames, int):
            raise ContentUnitValidationError("命中追加伤害触发间隔必须是整数帧数")
        if interval_frames <= 0:
            raise ContentUnitValidationError("命中追加伤害触发间隔必须为正帧数")
        if isinstance(probability, bool) or not isinstance(probability, int | float):
            raise ContentUnitValidationError("命中追加伤害触发概率必须是数字")
        if not 0.0 <= float(probability) <= 1.0:
            raise ContentUnitValidationError("命中追加伤害触发概率必须在 0 到 1 之间")
        self._impact_key = impact_key
        self._owner_ref = owner_ref
        self._slot = slot
        self._damage_spec = damage_spec
        self._attack_tags = frozenset(tags)
        self._interval_frames = interval_frames
        self._probability = float(probability)
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
        if not self._is_direct_hit(result):
            return HookResult()
        if not self._dealt_damage(result):
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            self._interval_frames
        ):
            return HookResult()
        if self._probability < 1.0 and not self._roll_probability(context):
            return HookResult()
        request_id = f"hook:{self.hook_key}:{frame}"
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.DAMAGE,
                    impact_key=self._impact_key,
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

    def _is_direct_hit(self, result: object) -> bool:
        """触发面判定：有标签集合时按主攻击标签过滤；为空时按通用公式放行。

        通用公式过滤排除反应伤害（超载爆炸、感电等不是「攻击命中」）。
        """

        if self._attack_tags:
            return getattr(result, "main_attack_tag", None) in self._attack_tags
        return getattr(result, "formula_key", None) == FORMULA_KEY_GENERAL

    @staticmethod
    def _dealt_damage(result: object) -> bool:
        damage = getattr(result, "final_damage", None)
        if isinstance(damage, bool) or not isinstance(damage, int | float):
            return False
        return damage > 0

    def _roll_probability(self, context: object) -> bool:
        random_source = getattr(getattr(context, "simulation", None), "random_source", None)
        if random_source is None:
            raise HitProcDamageError(f"命中追加伤害缺少装配期注入的仿真随机源：{self.hook_key}")
        typed_source = cast("RandomSource", random_source)
        return typed_source.roll(self._probability)
