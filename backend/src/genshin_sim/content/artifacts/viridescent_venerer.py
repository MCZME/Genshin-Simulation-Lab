"""翠绿之影圣遗物套装实现。

资产数据来源：Project Amber / Yatta 当前默认数据（``artifact_set:15002``，
效果 affix ``2150020`` / ``2150021``）。

效果与落点：

- 2 件套：获得 15% 风元素伤害加成 -> ``bonus.damage.anemo`` ``flat_add``，
  静态绑定穿戴者。
- 4 件套·扩散增伤：扩散反应造成的伤害提升 60% -> 剧变公式专属阶段
  ``transformative_reaction_bonus_add``。
- 4 件套·星扩散增伤：星扩散反应造成的伤害提升 20% -> 星烁公式专属阶段
  ``stellar_reaction_bonus_add``。
- 4 件套·减抗：根据扩散元素降低受影响敌人 40% 对应元素抗性，持续 10 秒；
  星扩散固定降低 40% 冰元素抗性 -> 目标主体 ``resistance.<element>``
  ``flat_add`` Buff（值 ``-0.4``，600 帧），经装配期注入的
  ``REACTION_OCCURRED`` 钩子投放。

行为约定：

- 触发归属：只认**穿戴者**触发的扩散 / 星扩散（``occurrence.source_ref``
  的 ``source_key`` 等于穿戴者），并额外要求**触发那一刻穿戴者在场上**
  （``team_state.active_slot``）：官方口径「减抗需穿戴者在前台触发扩散，
  后台不触发」。这里的「前台」只是**触发条件**——减抗一旦触发，即成为目标
  身上独立的 10 秒状态，与穿戴者随后是否留场、是否换人无关。
- 减抗目标取 occurrence 的 ``subject_ref``：只有**触发该次扩散的敌人**受
  减抗；被扩散范围命中、但自身未触发该次反应的敌人不受影响。
- 2 件套风伤与 4 件套扩散 / 星扩散增伤为常驻效果，不设前台门槛。
- 减抗不可叠加：同元素（含不同穿戴者）按元素冲突键互相替换（``REPLACE``）；
  不同元素各自独立定义、可共存（官方「同元素类型的抗性降低效果无法叠加」）。
  四种元素抗性各成一个 Buff 定义，由投放侧按扩散元素选定定义。
- 两个伤害 provider 都自筛公式，越界阶段会被 ``validate_formula_modifier_stages``
  硬拒绝并让整次结算失败，而不是静默跳过。
"""

from __future__ import annotations

import math

from genshin_sim.content.artifacts._common import (
    FRAMES_PER_SECOND,
    content_source_ref,
    parse_component_values,
    require_piece_count,
    require_set_row,
    slot_owner_ref,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.models import HookResult
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.core.attributes import (
    BONUS_DAMAGE_ANEMO,
    ELEMENT_TO_RESISTANCE_KEY,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
)
from genshin_sim.core.elements import (
    AuraKind,
    Element,
    ElementalSubjectKind,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffModifierValue,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import (
    FORMULA_KEY_STELLAR_REACTION,
    FORMULA_KEY_TRANSFORMATIVE_REACTION,
)
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
    STELLAR_SWIRL_REACTION_KEY,
    STELLAR_SWIRL_WIND_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.swirl.mechanic import (
    SWIRL_DAMAGE_TAGS,
    SWIRL_REACTION_KEY,
)

VIRIDESCENT_VENERER_KEY_PREFIX = "artifact.viridescent_venerer"
VIRIDESCENT_VENERER_HANDLER_KEY = VIRIDESCENT_VENERER_KEY_PREFIX
VIRIDESCENT_VENERER_2P_HANDLER_KEY = f"{VIRIDESCENT_VENERER_KEY_PREFIX}.2p"
VIRIDESCENT_VENERER_4P_HANDLER_KEY = f"{VIRIDESCENT_VENERER_KEY_PREFIX}.4p"
VIRIDESCENT_VENERER_CONTENT_VERSION = "release"

VIRIDESCENT_VENERER_2P_AUDIT_TAG = "viridescent_venerer_2p"
VIRIDESCENT_VENERER_4P_AUDIT_TAG = "viridescent_venerer_4p"

# 减抗作用的元素：风套只对可被扩散的火 / 水 / 雷 / 冰生效。
VIRIDESCENT_VENERER_SHRED_ELEMENTS = (
    Element.PYRO,
    Element.HYDRO,
    Element.ELECTRO,
    Element.CRYO,
)
_SHRED_ELEMENT_LABELS = {
    Element.PYRO: "火",
    Element.HYDRO: "水",
    Element.ELECTRO: "雷",
    Element.CRYO: "冰",
}
# 被扩散的附着类型到减抗元素：冻结按冰归并（与砂糖 A1、双冰共鸣同一口径）。
_AURA_KIND_TO_SHRED_ELEMENT = {
    AuraKind.PYRO: Element.PYRO,
    AuraKind.HYDRO: Element.HYDRO,
    AuraKind.ELECTRO: Element.ELECTRO,
    AuraKind.CRYO: Element.CRYO,
    AuraKind.FROZEN: Element.CRYO,
}
# 星扩散固定降冰抗（文案：对敌人触发星扩散反应时降低其 40% 冰元素抗性）。
STELLAR_SWIRL_SHRED_ELEMENT = Element.CRYO


def viridescent_venerer_shred_definition_key(element: Element) -> str:
    """某元素减抗 Buff 的定义键（每元素一个，互不冲突）。"""

    return f"{VIRIDESCENT_VENERER_KEY_PREFIX}.4p.resistance_shred.{element.value}"


def viridescent_venerer_shred_conflict_key(element: Element) -> str:
    """某元素减抗的冲突键：不含槽位，跨穿戴者同元素互相替换、不可叠加。"""

    return f"{VIRIDESCENT_VENERER_KEY_PREFIX}.4p.resistance_shred.{element.value}"


def viridescent_venerer_shred_term_key(element: Element) -> str:
    """某元素减抗的属性词条键。"""

    return f"{VIRIDESCENT_VENERER_KEY_PREFIX}.4p.resistance_shred.{element.value}.term"


def create_viridescent_venerer_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """翠绿之影套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    require_set_row(request, handler_key=VIRIDESCENT_VENERER_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=VIRIDESCENT_VENERER_HANDLER_KEY,
        version=VIRIDESCENT_VENERER_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "viridescent_venerer_set_identity"},
    )


def create_viridescent_venerer_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """翠绿之影 2 件套：获得 15% 风元素伤害加成。"""

    require_piece_count(
        request,
        expected=2,
        handler_key=VIRIDESCENT_VENERER_2P_HANDLER_KEY,
    )
    (anemo_bonus,) = parse_component_values(
        request.params,
        count=1,
        purpose="2 件套风元素伤害加成",
    )
    subject_ref = AttributeSubjectRef.character(slot_owner_ref(request.slot))
    provider_key = f"{VIRIDESCENT_VENERER_KEY_PREFIX}.2p.anemo_bonus.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({BONUS_DAMAGE_ANEMO}),
            owner_ref=subject_ref,
            display_name="翠绿之影 2件套",
        ),
        (
            ModifierTerm(
                target_key=BONUS_DAMAGE_ANEMO,
                stage=ModifierStage.FLAT_ADD,
                value=anemo_bonus,
                provider_key=provider_key,
                source_ref=content_source_ref(VIRIDESCENT_VENERER_KEY_PREFIX, "2p", request.slot),
                audit_tags=(VIRIDESCENT_VENERER_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=VIRIDESCENT_VENERER_2P_HANDLER_KEY,
        version=VIRIDESCENT_VENERER_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "viridescent_venerer_2p"},
    )


def create_viridescent_venerer_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """翠绿之影 4 件套：扩散 / 星扩散增伤与按扩散元素的目标减抗。"""

    require_piece_count(
        request,
        expected=4,
        handler_key=VIRIDESCENT_VENERER_4P_HANDLER_KEY,
    )
    (
        swirl_bonus,
        stellar_swirl_bonus,
        swirl_res_shred,
        duration_seconds,
        stellar_cryo_shred,
    ) = parse_component_values(
        request.params,
        count=5,
        purpose="4 件套扩散增伤/星扩散增伤/减抗值/持续时间/星扩散冰抗降低",
    )
    duration_frames = round(duration_seconds * FRAMES_PER_SECOND)
    if duration_frames <= 0:
        raise ContentUnitValidationError("4 件套持续时间必须折算为正帧数")
    if not math.isfinite(swirl_res_shred) or swirl_res_shred <= 0:
        raise ContentUnitValidationError("4 件套减抗值必须为正数")
    if not math.isfinite(stellar_cryo_shred) or stellar_cryo_shred <= 0:
        raise ContentUnitValidationError("4 件套星扩散冰抗降低值必须为正数")

    owner_ref = slot_owner_ref(request.slot)
    hook = ViridescentSwirlResistanceShredHook(
        owner_ref=owner_ref,
        slot=request.slot,
        duration_frames=duration_frames,
        swirl_res_shred=swirl_res_shred,
        stellar_cryo_shred=stellar_cryo_shred,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=VIRIDESCENT_VENERER_4P_HANDLER_KEY,
        version=VIRIDESCENT_VENERER_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=(
            _reaction_bonus_provider(
                owner_ref=owner_ref,
                slot=request.slot,
                scope="swirl",
                stage=DamageModifierStage.TRANSFORMATIVE_REACTION_BONUS_ADD,
                formula_key=FORMULA_KEY_TRANSFORMATIVE_REACTION,
                main_attack_tags=SWIRL_DAMAGE_TAGS,
                bonus=swirl_bonus,
                display_name="翠绿之影 4件套·扩散增伤",
            ),
            _reaction_bonus_provider(
                owner_ref=owner_ref,
                slot=request.slot,
                scope="stellar_swirl",
                stage=DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
                formula_key=FORMULA_KEY_STELLAR_REACTION,
                main_attack_tags=frozenset(
                    {STELLAR_SWIRL_WIND_DAMAGE_TAG, STELLAR_SWIRL_ICE_DAMAGE_TAG}
                ),
                bonus=stellar_swirl_bonus,
                display_name="翠绿之影 4件套·星扩散增伤",
            ),
        ),
        event_hooks=(hook,),
        buff_definitions=tuple(
            _build_resistance_shred_buff_definition(element)
            for element in VIRIDESCENT_VENERER_SHRED_ELEMENTS
        ),
        metadata={"piece_count": 4, "purpose": "viridescent_venerer_4p"},
    )


def _reaction_bonus_provider(
    *,
    owner_ref: str,
    slot: int,
    scope: str,
    stage: DamageModifierStage,
    formula_key: str,
    main_attack_tags: frozenset[str],
    bonus: float,
    display_name: str,
) -> ViridescentReactionBonusProvider:
    return ViridescentReactionBonusProvider(
        owner_ref=owner_ref,
        slot=slot,
        scope=scope,
        stage=stage,
        formula_key=formula_key,
        main_attack_tags=main_attack_tags,
        bonus=bonus,
        display_name=display_name,
    )


def _build_resistance_shred_buff_definition(element: Element) -> BuffDefinition:
    """某元素的减抗 Buff 定义：目标抗性 ``flat_add``，值由投放侧填负数。"""

    return BuffDefinition(
        definition_key=viridescent_venerer_shred_definition_key(element),
        mechanic_key=f"{VIRIDESCENT_VENERER_KEY_PREFIX}.4p.resistance_shred",
        handler_key=VIRIDESCENT_VENERER_4P_HANDLER_KEY,
        conflict_key=viridescent_venerer_shred_conflict_key(element),
        target_kinds=frozenset({AttributeSubjectKind.TARGET}),
        application_policy=BuffApplicationPolicy.REPLACE,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name=f"翠绿之影 4件套·{_SHRED_ELEMENT_LABELS[element]}抗性降低",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=viridescent_venerer_shred_term_key(element),
                target_key=ELEMENT_TO_RESISTANCE_KEY[element.value],
                stage=ModifierStage.FLAT_ADD,
                audit_tags=(VIRIDESCENT_VENERER_4P_AUDIT_TAG,),
            ),
        ),
    )


class ViridescentReactionBonusProvider:
    """4 件套：装备者造成的扩散 / 星扩散反应伤害提升。

    只对「装备者本人作为来源」且 ``main_attack_tag`` 命中对应反应标签集合的
    查询贡献对应公式的专属阶段；每个 provider 都自筛公式，越界阶段会被
    ``validate_formula_modifier_stages`` 硬拒绝。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        scope: str,
        stage: DamageModifierStage,
        formula_key: str,
        main_attack_tags: frozenset[str],
        bonus: float,
        display_name: str,
    ) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._stage = stage
        self._formula_key = formula_key
        self._main_attack_tags = frozenset(main_attack_tags)
        self._bonus = bonus
        self._provider_key = f"{VIRIDESCENT_VENERER_KEY_PREFIX}.4p.{scope}.slot:{slot}"
        self._source_ref = content_source_ref(VIRIDESCENT_VENERER_KEY_PREFIX, f"4p:{scope}", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({stage}),
            owner_ref=self._owner_ref,
            display_name=display_name,
        )

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        request = query.request
        if request.source_ref != self._owner_ref:
            return ()
        if request.formula_key != self._formula_key:
            return ()
        if request.main_attack_tag not in self._main_attack_tags:
            return ()
        return (
            DamageModifierTerm(
                stage=self._stage,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(VIRIDESCENT_VENERER_4P_AUDIT_TAG,),
            ),
        )


class ViridescentSwirlResistanceShredHook:
    """4 件套：穿戴者在前台触发扩散 / 星扩散时，对触发反应的敌人投放减抗 Buff。

    - 触发面 ``REACTION_OCCURRED``：``reaction_key`` 属普通扩散或星扩散。
    - 归属过滤：``occurrence.source_ref.source_key`` 必须等于穿戴者。
    - 触发前台判定：**仅在触发这一刻**要求穿戴者槽位等于当前场上槽位
      （官方「减抗需穿戴者在前台触发扩散」）；判定通过与否只决定这一次要不要
      投放减抗，投放出的减抗作为目标自身的时长状态独立存在，不随后续换人失效。
    - 目标：``occurrence.subject_ref``——只有触发该次扩散的敌人受减抗。
    - 元素：普通扩散取 ``transition.aura_kind`` 映射（冻结归冰）；星扩散固定冰。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        duration_frames: int,
        swirl_res_shred: float,
        stellar_cryo_shred: float,
    ) -> None:
        if duration_frames <= 0:
            raise ContentUnitValidationError("4 件套持续时间必须是正帧数")
        if not math.isfinite(swirl_res_shred) or swirl_res_shred <= 0:
            raise ContentUnitValidationError("4 件套减抗值必须为正数")
        if not math.isfinite(stellar_cryo_shred) or stellar_cryo_shred <= 0:
            raise ContentUnitValidationError("4 件套星扩散冰抗降低值必须为正数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._duration_frames = duration_frames
        self._swirl_res_shred = swirl_res_shred
        self._stellar_cryo_shred = stellar_cryo_shred
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self.hook_key = f"{VIRIDESCENT_VENERER_4P_HANDLER_KEY}:{owner_ref}"
        self.state_key = VIRIDESCENT_VENERER_4P_HANDLER_KEY
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
        fact_id = getattr(occurrence, "occurrence_ref", None)
        if not isinstance(fact_id, str) or not fact_id.strip():
            return HookResult()

        element, shred_value = self._resolve_element_and_shred(occurrence)
        if element is None:
            return HookResult()
        # 归属过滤：必须是穿戴者本人触发的扩散 / 星扩散。
        source_key = getattr(getattr(occurrence, "source_ref", None), "source_key", None)
        if source_key != self._owner_ref:
            return HookResult()
        # 触发前台判定：只在此刻要求穿戴者在场上；投放出的减抗独立计时，
        # 不因穿戴者随后离场而中断或失效。
        if not self._is_owner_on_field_at_trigger(context):
            return HookResult()
        # 减抗目标是触发该次反应的敌人本身。
        subject_ref = getattr(occurrence, "subject_ref", None)
        if not isinstance(subject_ref, ElementalSubjectRef):
            return HookResult()
        if subject_ref.kind is not ElementalSubjectKind.TARGET:
            return HookResult()
        target_ref = AttributeSubjectRef.target(subject_ref.entity_id)
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        return HookResult(
            buff_requests=(
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{frame}:{fact_id}",
                    frame=frame,
                    order=0,
                    definition_key=viridescent_venerer_shred_definition_key(element),
                    target_ref=target_ref,
                    source_context=RuntimeSourceRef(
                        RuntimeSourceKind.CONTENT,
                        f"{VIRIDESCENT_VENERER_KEY_PREFIX}:4p:resistance_shred:{element.value}",
                    ),
                    duration_frames=self._duration_frames,
                    applier_ref=self._owner_subject_ref,
                    modifier_values=(
                        BuffModifierValue(
                            viridescent_venerer_shred_term_key(element),
                            -shred_value,
                        ),
                    ),
                ),
            ),
        )

    def _resolve_element_and_shred(
        self,
        occurrence: object,
    ) -> tuple[Element | None, float]:
        """由反应 occurrence 决定减抗元素与减抗幅度；非扩散类返回 None。"""

        reaction_key = getattr(occurrence, "reaction_key", None)
        if reaction_key == SWIRL_REACTION_KEY:
            aura_kind = getattr(getattr(occurrence, "transition", None), "aura_kind", None)
            element = _AURA_KIND_TO_SHRED_ELEMENT.get(aura_kind) if aura_kind is not None else None
            if element is None:
                return None, 0.0
            return element, self._swirl_res_shred
        if reaction_key == STELLAR_SWIRL_REACTION_KEY:
            return STELLAR_SWIRL_SHRED_ELEMENT, self._stellar_cryo_shred
        return None, 0.0

    def _is_owner_on_field_at_trigger(self, context: object) -> bool:
        """触发那一刻穿戴者是否在场上。

        这是**触发条件**，不是减抗的持续条件：返回 False 只表示不投放这次减抗；
        返回 True 时投放的减抗由目标自身的时长状态承载，与穿戴者是否留场无关。
        """

        team_state = getattr(context, "states", None)
        active_slot = getattr(team_state, "active_slot", None)
        return active_slot == self._slot
