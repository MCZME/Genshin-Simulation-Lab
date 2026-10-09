"""砂糖内容事件钩子：产球与固有天赋 A1 / A4。

产球（维护者提供的角色产球表，实施规划 §6.5）：战技技能伤害命中产 4 风微粒
（100% 概率、判定冷却 0.4s = 24 帧）。概率 100% 无分布可选，不消费
``RandomSource``。触发面为战技命中的影响点（「元素战技（对己方非角色单位）」
行本期不实现，见 §6.3，不涉及产球）；触发影响点按伤害结果 ``request_id`` 内嵌
的 impact_key 匹配；判定冷却游标在 hook 实例，最近产球帧同步写入内容状态
``sucrose_last_particle_frame`` 供审计（0 表示尚未产球）。产球经
``ImpactKind.ENERGY`` 的 ``spawn_pickup`` 出口，归属宿主砂糖（风属性微粒）。

固有天赋（实施规划 §11.5）：

- A1「触媒置换术」订阅 ``REACTION_OCCURRED``，按「砂糖触发的扩散 / 星扩散」
  取被扩散附着元素，向队伍中与之一致、且不含砂糖自己的角色投放 +50 精通
  （覆盖刷新 8s）。队伍「槽位 → 元素」映射取自能量系统的角色档案——角色资产
  元素是能量档案的一部分，是运行期唯一可读的槽位元素来源。
- A4「小小的慧风」订阅 ``DAMAGE_RESOLVED``，按「伤害归属砂糖 ∧ 主攻击标签为
  元素战技 / 元素爆发 ∧ 命中敌人」触发，触发帧解析砂糖的**快照**元素精通并按
  比例折算，向队伍中所有角色（不含砂糖自己）投放（覆盖刷新 8s）。快照在伤害
  结算之后读取，因而晚于同一 proc 内通过 Buff 施加的精通来源（如圣遗物套装
  的精通加成），与实施规划 §11.5「同一 proc 内晚于教官四件套」的口径一致。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_A1_BUFF_DEFINITION_KEY,
    SUCROSE_A1_DURATION_FRAMES,
    SUCROSE_A1_MASTERY_TERM_KEY,
    SUCROSE_A1_MECHANIC_KEY,
    SUCROSE_A1_TRIGGER_REACTION_KEYS,
    SUCROSE_A4_BUFF_DEFINITION_KEY,
    SUCROSE_A4_DURATION_FRAMES,
    SUCROSE_A4_MASTERY_RATIO,
    SUCROSE_A4_MASTERY_TERM_KEY,
    SUCROSE_A4_MECHANIC_KEY,
    SUCROSE_A4_TRIGGER_MAIN_ATTACK_TAGS,
    SUCROSE_AURA_ELEMENT_MAP,
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_PARTICLE_COOLDOWN_FRAMES,
    SUCROSE_PARTICLE_COUNT,
    SUCROSE_PARTICLE_ELEMENT,
    SUCROSE_PARTICLE_SPAWN_IMPACT_KEY,
    SUCROSE_PARTICLE_TRAVEL_FRAMES,
    SUCROSE_PARTICLE_TRIGGER_IMPACT_KEYS,
    SUCROSE_STATE_LAST_PARTICLE_FRAME,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.hooks import HookContext
from genshin_sim.content.models import HookResult
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.attributes import (
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.attributes.resolver import AttributeResolver
from genshin_sim.core.elements import Element
from genshin_sim.core.entity_states import CharacterRuntimeState
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue
from genshin_sim.core.systems.energy import EnergyRuntime

# 敌方目标判据按 entity_id 前缀区分（与奥黛塔产球 hook 同口径）。
_ENEMY_TARGET_PREFIX = "target:"


class SucroseParticleHook:
    """产球：战技技能伤害命中产 4 风微粒，命中后 24 帧内不重复产球。"""

    def __init__(self, *, owner_ref: str, slot: int) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("产球 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("产球 hook 必须绑定正整数队伍槽位")
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._last_proc_frame: int | None = None
        self.hook_key = f"sucrose.particle:{owner_ref}"
        self.state_key = SUCROSE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        """宿主角色引用：状态段归属校验按此匹配。"""

        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context  # 判定冷却游标在 hook 实例；内容状态字段随产出同步写入。
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
            key in request_id for key in SUCROSE_PARTICLE_TRIGGER_IMPACT_KEYS
        ):
            return HookResult()

        frame = getattr(event, "frame", 0)
        if (
            self._last_proc_frame is not None
            and frame - self._last_proc_frame < SUCROSE_PARTICLE_COOLDOWN_FRAMES
        ):
            return HookResult()
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=SUCROSE_PARTICLE_SPAWN_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "spawn_pickup",
                            "pickup_kind": "particle",
                            "element": SUCROSE_PARTICLE_ELEMENT.value,
                            "count": SUCROSE_PARTICLE_COUNT,
                            "travel_frames": SUCROSE_PARTICLE_TRAVEL_FRAMES,
                            "tags": (),
                        }
                    },
                ),
            ),
            state_patches=(
                StatePatchRequest(
                    owner_ref=self._owner_ref,
                    state_key=self.state_key,
                    fields={SUCROSE_STATE_LAST_PARTICLE_FRAME: frame},
                ),
            ),
        )


def _require_positive_frames(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContentUnitValidationError(f"{label} 必须是正整数帧数")
    return value


def _require_positive_number(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0.0:
        raise ContentUnitValidationError(f"{label} 必须为正数")
    return float(value)


def _team_characters(context: object) -> tuple[CharacterRuntimeState, ...]:
    """队伍角色运行态序列（未注册队伍运行态时为空）。"""

    if not isinstance(context, HookContext) or context.states is None:
        return ()
    return tuple(context.states.characters)


def _team_subject_refs(
    context: object,
    *,
    excluding_slot: int,
) -> tuple[AttributeSubjectRef, ...]:
    """队伍角色主体（按槽位升序，排除指定槽位）。

    目标为**角色主体**而非队伍作用域：A1 需要按元素逐个筛选，A4 需要排除砂糖
    自己；主体逐个投放也让两支天赋的作用范围与「除砂糖自己」的文本口径逐字对应。
    """

    return tuple(
        AttributeSubjectRef.character(character.combat_entity_id)
        for character in _team_characters(context)
        if character.slot != excluding_slot
    )


def _team_element_map(context: object) -> dict[int, Element]:
    """槽位 → 元素：读能量系统的角色档案（角色资产元素随档案进入运行期）。

    能量档案是运行期唯一可读的「槽位 → 元素」来源；档案缺失（未装配能量系统）
    或元素不受 ``Element`` 支持（无元素资源角色）时该槽位不参与，A1 自然不发
    该角色，不引入特例分支。
    """

    if not isinstance(context, HookContext):
        return {}
    runtime = context.simulation.get_system(EnergyRuntime)
    if not isinstance(runtime, EnergyRuntime):
        return {}
    store = runtime.energy_store
    elements: dict[int, Element] = {}
    for character in _team_characters(context):
        ref = AttributeSubjectRef.character(character.combat_entity_id)
        if not store.contains(ref):
            continue
        profile = store.require_profile(ref)
        try:
            elements[character.slot] = Element(profile.element.value)
        except ValueError:
            continue
    return elements


class SucroseCatalystConversionHook:
    """A1 触媒置换术：砂糖触发扩散 / 星扩散时，与被扩散元素同元素的队友 +50 精通。

    触发面为 ``REACTION_OCCURRED``，判据两条：反应键属普通扩散 / 星扩散，且
    发生源的 ``source_key`` 是砂糖自己——既覆盖风灵离场后触发的扩散（伤害归属
    仍是砂糖），也排除锅巴与环境物体等非砂糖来源。被扩散元素取反应的
    ``transition.aura_kind``（FROZEN 与染色判定同口径映射为冰）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        duration_frames: int = SUCROSE_A1_DURATION_FRAMES,
        mastery_flat: float = 50.0,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("A1 触媒置换术 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("A1 触媒置换术 hook 必须绑定正整数队伍槽位")
        self._owner_ref = owner_ref
        self._slot = slot
        self._duration_frames = _require_positive_frames(duration_frames, "A1 精通加成持续时间")
        self._mastery_flat = _require_positive_number(mastery_flat, "A1 精通加成值")
        self._source_context = RuntimeSourceRef(
            RuntimeSourceKind.MECHANIC,
            SUCROSE_A1_MECHANIC_KEY,
        )
        self.hook_key = f"sucrose.passive.a1:{owner_ref}"
        self.state_key = SUCROSE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("REACTION_OCCURRED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        """宿主角色引用：状态段归属校验按此匹配。"""

        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        if getattr(event, "event_type", None) is not EventType.REACTION_OCCURRED:
            return HookResult()
        occurrence = getattr(getattr(event, "payload", None), "occurrence", None)
        if occurrence is None:
            return HookResult()
        if getattr(occurrence, "reaction_key", None) not in SUCROSE_A1_TRIGGER_REACTION_KEYS:
            return HookResult()
        if getattr(getattr(occurrence, "source_ref", None), "source_key", None) != self._owner_ref:
            return HookResult()
        transition = getattr(occurrence, "transition", None)
        aura_kind = getattr(transition, "aura_kind", None)
        element = SUCROSE_AURA_ELEMENT_MAP.get(aura_kind) if aura_kind is not None else None
        if element is None:
            return HookResult()
        elements = _team_element_map(context)
        refs = tuple(
            AttributeSubjectRef.character(character.combat_entity_id)
            for character in _team_characters(context)
            if character.slot != self._slot and elements.get(character.slot) is element
        )
        if not refs:
            return HookResult()
        frame = getattr(event, "frame", 0)
        return HookResult(
            buff_requests=tuple(
                ApplyBuffRequest(
                    request_id=f"{self.hook_key}:{frame}:{ref.entity_id}",
                    frame=frame,
                    order=index,
                    definition_key=SUCROSE_A1_BUFF_DEFINITION_KEY,
                    target_ref=ref,
                    source_context=self._source_context,
                    duration_frames=self._duration_frames,
                    modifier_values=(
                        BuffModifierValue(SUCROSE_A1_MASTERY_TERM_KEY, self._mastery_flat),
                    ),
                )
                for index, ref in enumerate(refs)
            ),
        )


class SucroseMollisFavoniusHook:
    """A4 小小的慧风：E / Q 命中敌人时，全队（除砂糖）按砂糖快照精通的 20% 提升精通。

    触发面为 ``DAMAGE_RESOLVED``：伤害归属砂糖、主攻击标签为元素战技 / 元素爆发、
    命中敌人（``target:`` 前缀）三者同时成立即触发，不区分是哪一拍、哪一次命中；
    风灵按拍输出故每拍覆盖刷新。加成值为**触发帧的快照**：在伤害结算之后解析
    砂糖的元素精通并按比例折算，之后砂糖精通变化不影响已投放的数值；
    属性解析器未接线时视为未生效，不投放。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        ratio: float = SUCROSE_A4_MASTERY_RATIO,
        duration_frames: int = SUCROSE_A4_DURATION_FRAMES,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("A4 小小的慧风 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("A4 小小的慧风 hook 必须绑定正整数队伍槽位")
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._ratio = _require_positive_number(ratio, "A4 精通折算比例")
        self._duration_frames = _require_positive_frames(duration_frames, "A4 精通加成持续时间")
        self._source_context = RuntimeSourceRef(
            RuntimeSourceKind.MECHANIC,
            SUCROSE_A4_MECHANIC_KEY,
        )
        self.hook_key = f"sucrose.passive.a4:{owner_ref}"
        self.state_key = SUCROSE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        """宿主角色引用：状态段归属校验按此匹配。"""

        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        if getattr(event, "event_type", None) is not EventType.DAMAGE_RESOLVED:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        if getattr(result, "source_ref", None) != self._owner_subject_ref:
            return HookResult()
        if getattr(result, "main_attack_tag", None) not in SUCROSE_A4_TRIGGER_MAIN_ATTACK_TAGS:
            return HookResult()
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        if not isinstance(target_id, str) or not target_id.startswith(_ENEMY_TARGET_PREFIX):
            return HookResult()

        frame = getattr(event, "frame", 0)
        value = self._snapshot_mastery(context, frame) * self._ratio
        if value <= 0.0:
            return HookResult()
        refs = _team_subject_refs(context, excluding_slot=self._slot)
        if not refs:
            return HookResult()
        return HookResult(
            buff_requests=tuple(
                ApplyBuffRequest(
                    request_id=f"{self.hook_key}:{frame}:{ref.entity_id}",
                    frame=frame,
                    order=index,
                    definition_key=SUCROSE_A4_BUFF_DEFINITION_KEY,
                    target_ref=ref,
                    source_context=self._source_context,
                    duration_frames=self._duration_frames,
                    modifier_values=(BuffModifierValue(SUCROSE_A4_MASTERY_TERM_KEY, value),),
                )
                for index, ref in enumerate(refs)
            ),
        )

    def _snapshot_mastery(self, context: object, frame: int) -> float:
        if not isinstance(context, HookContext):
            return 0.0
        resolver = context.simulation.get_system(AttributeResolver)
        if not isinstance(resolver, AttributeResolver):
            return 0.0
        resolution = resolver.resolve(
            AttributeQuery(
                subject_ref=self._owner_subject_ref,
                attribute_key=STAT_ELEMENTAL_MASTERY,
                frame=frame,
            )
        )
        return float(resolution.final_value)
