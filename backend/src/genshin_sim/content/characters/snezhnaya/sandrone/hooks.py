"""桑多涅命座效果的事件钩子。

C4 棱晶谐振炮：订阅 ``DAMAGE_RESOLVED`` 事实，星超导冰标签的伤害命中敌人时
按内置冷却召唤协同攻击——125% 攻击力冰元素伤害、视为星超导反应伤害（星烁
直伤请求、单体、无 AOE、无附着）。触发不区分伤害来源：任何星超导冰
伤害命中（含桑多涅自身直伤星变体与星超导反应本体伤害）都计一次触发，内置
冷却保证频率；星超导反应的触发行为本身不产生伤害事实、天然不触发（规划
3.7）。协同攻击自带的星超导冰标签同样计触发，被冷却窗口吸收。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_C4_ATTACK_IMPACT_KEY,
    SANDRONE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    radiance_evidence,
    resolve_attribute_final_value,
    stellar_base_bonus_for_atk,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.systems.damage.stellar import StellarReactionDamageInput
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
)

# 敌方目标判据按 entity_id 前缀区分（与西风系列武器钩子同口径）。
_ENEMY_TARGET_PREFIX = "target:"


class SandroneConstellationError(RuntimeError):
    """桑多涅命座 hook 运行期错误（接线缺失或契约不完整）。"""


class SandroneC4CoordinatedAttackHook:
    """C4 棱晶谐振炮：星超导冰伤害命中敌人时按内置冷却打出协同攻击。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        attack_ratio: float,
        cooldown_frames: int,
        ascension_bonus: float = 0.0,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("C4 协同攻击 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("C4 协同攻击必须绑定正整数队伍槽位")
        if isinstance(attack_ratio, bool) or not isinstance(attack_ratio, int | float):
            raise ContentUnitValidationError("C4 协同攻击倍率必须是数字")
        if attack_ratio <= 0.0:
            raise ContentUnitValidationError("C4 协同攻击倍率必须为正数")
        if (
            isinstance(cooldown_frames, bool)
            or not isinstance(cooldown_frames, int)
            or cooldown_frames <= 0
        ):
            raise ContentUnitValidationError("C4 协同攻击内置冷却必须为正整数帧数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._attack_ratio = float(attack_ratio)
        self._cooldown_frames = cooldown_frames
        self._ascension_bonus = float(ascension_bonus)
        self._last_proc_frame: int | None = None
        self.hook_key = f"sandrone.c4:{owner_ref}"
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        """宿主角色引用：解锁评估与状态归属按此匹配。"""

        return self._owner_ref

    @property
    def state_key(self) -> str:
        """钩子不持有内容状态，挂载键与宿主角色内容状态一致。"""

        return SANDRONE_CHARACTER_HANDLER_KEY

    @property
    def last_proc_frame(self) -> int | None:
        """最近一次协同攻击触发帧；仅供测试读取。"""

        return self._last_proc_frame

    def handle(self, event: object, context: object) -> HookResult:
        if getattr(event, "event_type", None) is not EventType.DAMAGE_RESOLVED:
            return HookResult()
        frame = getattr(event, "frame", 0)
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        if getattr(result, "main_attack_tag", None) != STELLAR_CONDUCT_CRYO_DAMAGE_TAG:
            return HookResult()
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        if not isinstance(target_id, str) or not target_id.startswith(_ENEMY_TARGET_PREFIX):
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            self._cooldown_frames
        ):
            return HookResult()
        simulation = getattr(context, "simulation", None)
        if not isinstance(simulation, SimulationContext):
            raise SandroneConstellationError(f"C4 协同攻击缺少仿真上下文：{self.hook_key}")
        atk = resolve_attribute_final_value(
            simulation,
            self._owner_ref,
            STAT_ATK_TOTAL,
            frame,
        )
        evidence = radiance_evidence(simulation, self._owner_ref, frame)
        base_multiplier = evidence.direct_base_multiplier if evidence is not None else 1.0
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.DAMAGE,
                    impact_key=SANDRONE_C4_ATTACK_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    target_refs=(target_id,),
                    damage_spec=DamageImpactSpec(
                        impact_ref=f"{SANDRONE_C4_ATTACK_IMPACT_KEY}:{frame}",
                        main_attack_tag=STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
                        element=Element.CRYO,
                        scaling_terms=(),
                        can_crit=True,
                        strike_type=None,
                        range_type="远程",
                        elemental_amount=AuraAmount.zero(),
                        display_name="棱晶谐振炮协同攻击",
                        area=None,
                        stellar_reaction=StellarReactionDamageInput(
                            mode="character_direct",
                            scaling_value=atk * self._attack_ratio,
                            stellar_base_multiplier=base_multiplier,
                            stellar_base_bonus=stellar_base_bonus_for_atk(atk),
                            stellar_ascension_bonus=self._ascension_bonus,
                        ),
                    ),
                ),
            ),
        )
