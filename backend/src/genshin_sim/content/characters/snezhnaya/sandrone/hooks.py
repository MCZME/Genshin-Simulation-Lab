"""桑多涅内容事件钩子。

C4 棱晶谐振炮：订阅 ``DAMAGE_RESOLVED`` 事实，命中敌人且伤害事实的
**来源是桑多涅自己**、攻击标签为 ``星超导冰`` 或 ``星扩散冰`` 时，按内置冷却
召唤协同攻击——冰元素伤害、视为**对应**星烁反应伤害（星烁直伤请求、单体、
无 AOE、无附着）。

来源判定按伤害事实的 ``source_ref`` 与宿主角色引用比对（与 C2 暴伤 provider
同口径）：只认桑多涅制造的伤害事实，队伍其他角色触发的星扩散反应本体伤害
不计触发。标签与倍率按触发标签查表（见 ``_VARIANTS_BY_TRIGGER_TAG``）。
协同攻击自带的标签同样计触发，被冷却窗口吸收；星超导反应的触发行为本身
不产生伤害事实、天然不触发。

产球：冷凝射线与战技棱晶弹命中产 1 冰微粒（任意变体、共用 2.5s 判定
冷却），见 ``SandroneParticleHook``。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_STATE_LAST_PARTICLE_FRAME,
    SANDRONE_C4_ATTACK_IMPACT_KEY,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_PARTICLE_COOLDOWN_FRAMES,
    SANDRONE_PARTICLE_COUNT,
    SANDRONE_PARTICLE_ELEMENT,
    SANDRONE_PARTICLE_SPAWN_IMPACT_KEY,
    SANDRONE_PARTICLE_TRAVEL_FRAMES,
    SANDRONE_PARTICLE_TRIGGER_IMPACT_KEYS,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    radiance_evidence,
    resolve_attribute_final_value,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.state_container import StatePatchRequest
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
from genshin_sim.core.systems.damage import DamageScalingTerm
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
        # 星烁基础系数取对应反应的词条（非角色当前辉映状态的证据）；无任何辉映
        # 证据时保守回落 1.0。P6 基础增伤与 C6 擢升由 provider 词条在结算期
        # 叠加，不在此折叠。
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
                        # 倍率与属性分开承载（D-082）：协同攻击档位系数进
                        # scaling_terms，属性由公式侧从攻击力面板读取。
                        scaling_terms=(
                            DamageScalingTerm(
                                component_key=SANDRONE_C4_ATTACK_IMPACT_KEY,
                                attribute_key=STAT_ATK_TOTAL,
                                coefficient=self._attack_ratio_for(variant),
                            ),
                        ),
                        can_crit=True,
                        strike_type=None,
                        range_type="远程",
                        elemental_amount=AuraAmount.zero(),
                        display_name="棱晶谐振炮协同攻击",
                        area=None,
                        stellar_reaction=StellarReactionDamageInput(
                            mode="character_direct",
                            stellar_base_multiplier=base_multiplier,
                        ),
                    ),
                ),
            ),
        )


class SandroneParticleHook:
    """产球：冷凝射线与战技棱晶弹命中产 1 冰微粒，共用 2.5s 判定冷却。

    订阅 ``DAMAGE_RESOLVED``，命中按伤害实际结算帧判定（棱晶弹影响点在
    动作展开帧结算、射线即时）。触发影响点按伤害结果 ``request_id`` 内嵌的
    impact_key 匹配：动作影响点 id 形如 ``action:{instance_id}:{impact_key}``，
    法洁欧产出的请求 id 内嵌影响键，多目标伤害在此基础上追加
    ``:target:{id}:{index}`` 后缀，均保持影响键可识别。冷却游标在 hook
    实例（与 C4 同口径）：同帧多条命中事实（射线与 C6 追加段同帧）即时
    去重，最近产球帧同时写入内容状态 ``fageou_last_particle_frame`` 供
    审计（0 表示尚未产球）。产球经 ``ImpactKind.ENERGY`` 的
    ``spawn_pickup`` 出口，归属宿主桑多涅（冰属性微粒）。星超导/星扩散
    变体同样产球——产球与变体无关。
    """

    def __init__(self, *, owner_ref: str, slot: int) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("产球 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("产球 hook 必须绑定正整数队伍槽位")
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._last_proc_frame: int | None = None
        self.hook_key = f"sandrone.particle:{owner_ref}"
        self.state_key = SANDRONE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        """宿主角色引用：状态段归属校验按此匹配。"""

        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context  # 冷却游标在 hook 实例；内容状态字段随产出同步写入。
        if getattr(event, "event_type", None) is not EventType.DAMAGE_RESOLVED:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        if getattr(result, "source_ref", None) != self._owner_subject_ref:
            return HookResult()
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        if not isinstance(target_id, str) or not target_id.startswith(_ENEMY_TARGET_PREFIX):
            return HookResult()
        request_id = getattr(result, "request_id", None)
        if not isinstance(request_id, str) or not any(
            key in request_id for key in SANDRONE_PARTICLE_TRIGGER_IMPACT_KEYS
        ):
            return HookResult()

        frame = getattr(event, "frame", 0)
        if (
            self._last_proc_frame is not None
            and frame - self._last_proc_frame < SANDRONE_PARTICLE_COOLDOWN_FRAMES
        ):
            return HookResult()
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=SANDRONE_PARTICLE_SPAWN_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "spawn_pickup",
                            "pickup_kind": "particle",
                            "element": SANDRONE_PARTICLE_ELEMENT.value,
                            "count": SANDRONE_PARTICLE_COUNT,
                            "travel_frames": SANDRONE_PARTICLE_TRAVEL_FRAMES,
                            "tags": (),
                        }
                    },
                ),
            ),
            state_patches=(
                StatePatchRequest(
                    owner_ref=self._owner_ref,
                    state_key=self.state_key,
                    fields={FAGEOU_STATE_LAST_PARTICLE_FRAME: frame},
                ),
            ),
        )
