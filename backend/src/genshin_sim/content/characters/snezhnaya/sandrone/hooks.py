"""桑多涅命座效果的事件钩子。

C4 棱晶谐振炮：订阅 ``DAMAGE_RESOLVED`` 事实，命中敌人且伤害事实的
**来源是桑多涅自己**、攻击标签为 ``星超导冰`` 或 ``星扩散冰`` 时，按内置冷却
召唤协同攻击——冰元素伤害、视为**对应**星烁反应伤害（星烁直伤请求、单体、
无 AOE、无附着）。

来源判定按伤害事实的 ``source_ref`` 与宿主角色引用比对（与 C2 暴伤 provider
同口径）：只认桑多涅制造的伤害事实，队伍其他角色触发的星扩散反应本体伤害
不计触发。标签与倍率按触发标签查表（见 ``_VARIANTS_BY_TRIGGER_TAG``）。
协同攻击自带的标签同样计触发，被冷却窗口吸收；星超导反应的触发行为本身
不产生伤害事实、天然不触发。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

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
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER,
    STELLAR_SWIRL_DIRECT_BASE_MULTIPLIER,
    AttributeKey,
    AttributeSubjectRef,
)
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.systems.damage.stellar import StellarReactionDamageInput
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
)

# 敌方目标判据按 entity_id 前缀区分（与西风系列武器钩子同口径）。
_ENEMY_TARGET_PREFIX = "target:"


class _CoordinatedAttackVariant(NamedTuple):
    """一次协同攻击的产出变体：产出标签与星烁基础系数词条。"""

    main_attack_tag: str
    base_multiplier_key: AttributeKey


# 触发标签 → 产出变体。官方文本要求协同攻击"视为**对应**星烁反应造成的伤害"，
# 因此产出标签与星烁基础系数都随触发来源取；星超导雷／星扩散风不在触发集合内
# （不是桑多涅制造的反应伤害）。
_VARIANTS_BY_TRIGGER_TAG: Mapping[str, _CoordinatedAttackVariant] = {
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG: _CoordinatedAttackVariant(
        main_attack_tag=STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
        base_multiplier_key=STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER,
    ),
    STELLAR_SWIRL_ICE_DAMAGE_TAG: _CoordinatedAttackVariant(
        main_attack_tag=STELLAR_SWIRL_ICE_DAMAGE_TAG,
        base_multiplier_key=STELLAR_SWIRL_DIRECT_BASE_MULTIPLIER,
    ),
}


class SandroneConstellationError(RuntimeError):
    """桑多涅命座 hook 运行期错误（接线缺失或契约不完整）。"""


class SandroneC4CoordinatedAttackHook:
    """C4 棱晶谐振炮：桑多涅的星超导冰／星扩散冰伤害命中敌人时打出协同攻击。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        attack_ratio: float,
        swirl_ratio: float,
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
        if isinstance(swirl_ratio, bool) or not isinstance(swirl_ratio, int | float):
            raise ContentUnitValidationError("C4 协同攻击星扩散倍率必须是数字")
        if swirl_ratio <= 0.0:
            raise ContentUnitValidationError("C4 协同攻击星扩散倍率必须为正数")
        if (
            isinstance(cooldown_frames, bool)
            or not isinstance(cooldown_frames, int)
            or cooldown_frames <= 0
        ):
            raise ContentUnitValidationError("C4 协同攻击内置冷却必须为正整数帧数")
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._attack_ratio = float(attack_ratio)
        self._swirl_ratio = float(swirl_ratio)
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

    @property
    def attack_ratio(self) -> float:
        """星超导冰触发档的攻击力倍率；仅供测试与诊断读取。"""

        return self._attack_ratio

    @property
    def swirl_ratio(self) -> float:
        """星扩散冰触发档的攻击力倍率；仅供测试与诊断读取。"""

        return self._swirl_ratio

    @property
    def cooldown_frames(self) -> int:
        """协同攻击内置冷却帧数；仅供测试与诊断读取。"""

        return self._cooldown_frames

    @property
    def ascension_bonus(self) -> float:
        """C6 星烁擢升（覆盖本协同攻击）；仅供测试与诊断读取。"""

        return self._ascension_bonus

    def _attack_ratio_for(self, variant: _CoordinatedAttackVariant) -> float:
        """按产出变体取攻击力倍率档：星超导冰取星超导档，星扩散冰取星扩散档。"""

        return (
            self._attack_ratio
            if variant.main_attack_tag == STELLAR_CONDUCT_CRYO_DAMAGE_TAG
            else self._swirl_ratio
        )

    def handle(self, event: object, context: object) -> HookResult:
        if getattr(event, "event_type", None) is not EventType.DAMAGE_RESOLVED:
            return HookResult()
        frame = getattr(event, "frame", 0)
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        # 先判来源：只认桑多涅自己造成的伤害事实（与 C2 暴伤 provider 同口径）。
        if getattr(result, "source_ref", None) != self._owner_subject_ref:
            return HookResult()
        trigger_tag = getattr(result, "main_attack_tag", None)
        if not isinstance(trigger_tag, str):
            return HookResult()
        variant = _VARIANTS_BY_TRIGGER_TAG.get(trigger_tag)
        if variant is None:
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
        # 星烁基础系数取对应反应的词条（非角色当前辉映状态的证据）；无任何辉映
        # 证据时保守回落 1.0。
        evidence = radiance_evidence(simulation, self._owner_ref, frame)
        base_multiplier = (
            resolve_attribute_final_value(
                simulation,
                self._owner_ref,
                variant.base_multiplier_key,
                frame,
            )
            if evidence is not None
            else 1.0
        )
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
                        main_attack_tag=variant.main_attack_tag,
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
                            scaling_value=atk * self._attack_ratio_for(variant),
                            stellar_base_multiplier=base_multiplier,
                            stellar_base_bonus=stellar_base_bonus_for_atk(atk),
                            stellar_ascension_bonus=self._ascension_bonus,
                        ),
                    ),
                ),
            ),
        )
