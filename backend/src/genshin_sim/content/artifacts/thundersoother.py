"""平息鸣雷的尊者圣遗物套装实现。

效果与落点：

- 2 件套：雷元素抗性提高 40% -> ``resistance.electro`` ``flat_add``，
  静态绑定穿戴者。
- 4 件套：对处于雷元素影响下的敌人造成的伤害提升 35% -> 通用公式
  ``damage_bonus_add`` 阶段，条件经装配期注入的
  ``TargetElementAuraReadPort`` 查目标是否受雷元素影响，静态绑定穿戴者，
  不落 Buff。

行为约定：

- 「处于雷元素影响下」沿用统一口径 ``affected_aura_kinds(Element.ELECTRO)``：
  只认 ``electro`` 分量；雷元素没有燃烧/冻结式的衍生持久分量，激化按
  ``core.elements.AURA_KIND_ELEMENT`` 归草，不算受雷元素影响。
- 伤害 provider 自筛公式：``damage_bonus_add`` 只属于通用公式，越界
  阶段会被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
- 附着端口未绑定时（装配完成前）不贡献，条件不会提前生效。
"""

from __future__ import annotations

from genshin_sim.content.artifacts._common import (
    content_source_ref,
    parse_component_values,
    require_piece_count,
    require_set_row,
    slot_owner_ref,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.core.attributes import (
    RESISTANCE_ELECTRO,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    StaticModifierProvider,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.aura.ports import TargetElementAuraReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

THUNDERSOOTHER_KEY_PREFIX = "artifact.thundersoother"
THUNDERSOOTHER_HANDLER_KEY = THUNDERSOOTHER_KEY_PREFIX
THUNDERSOOTHER_2P_HANDLER_KEY = f"{THUNDERSOOTHER_KEY_PREFIX}.2p"
THUNDERSOOTHER_4P_HANDLER_KEY = f"{THUNDERSOOTHER_KEY_PREFIX}.4p"
THUNDERSOOTHER_CONTENT_VERSION = "release"

THUNDERSOOTHER_2P_AUDIT_TAG = "thundersoother_2p"
THUNDERSOOTHER_4P_AUDIT_TAG = "thundersoother_4p"

THUNDERSOOTHER_AFFECTED_ELEMENT = Element.ELECTRO


def create_thundersoother_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """平息鸣雷的尊者套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    require_set_row(request, handler_key=THUNDERSOOTHER_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=THUNDERSOOTHER_HANDLER_KEY,
        version=THUNDERSOOTHER_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "thundersoother_set_identity"},
    )


def create_thundersoother_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """平息鸣雷的尊者 2 件套：雷元素抗性提高。"""

    require_piece_count(
        request,
        expected=2,
        handler_key=THUNDERSOOTHER_2P_HANDLER_KEY,
    )
    (resistance,) = parse_component_values(
        request.params,
        count=1,
        purpose="2 件套雷元素抗性加成",
    )
    subject_ref = AttributeSubjectRef.character(slot_owner_ref(request.slot))
    provider_key = f"{THUNDERSOOTHER_KEY_PREFIX}.2p.electro_res.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({RESISTANCE_ELECTRO}),
            owner_ref=subject_ref,
            display_name="平息鸣雷的尊者 2件套",
        ),
        (
            ModifierTerm(
                target_key=RESISTANCE_ELECTRO,
                stage=ModifierStage.FLAT_ADD,
                value=resistance,
                provider_key=provider_key,
                source_ref=content_source_ref(THUNDERSOOTHER_KEY_PREFIX, "2p", request.slot),
                audit_tags=(THUNDERSOOTHER_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=THUNDERSOOTHER_2P_HANDLER_KEY,
        version=THUNDERSOOTHER_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "thundersoother_2p"},
    )


def create_thundersoother_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """平息鸣雷的尊者 4 件套：对受雷元素影响的敌人伤害提升。"""

    require_piece_count(
        request,
        expected=4,
        handler_key=THUNDERSOOTHER_4P_HANDLER_KEY,
    )
    (damage_bonus,) = parse_component_values(
        request.params,
        count=1,
        purpose="4 件套对雷影响敌人伤害加成",
    )
    owner_ref = slot_owner_ref(request.slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=THUNDERSOOTHER_4P_HANDLER_KEY,
        version=THUNDERSOOTHER_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=(
            ThundersootherElectroAffectedBonusProvider(
                owner_ref=owner_ref,
                slot=request.slot,
                bonus=damage_bonus,
            ),
        ),
        metadata={"piece_count": 4, "purpose": "thundersoother_4p"},
    )


class ThundersootherElectroAffectedBonusProvider:
    """4 件套：对处于雷元素影响下的敌人造成的伤害提升。

    ``damage_bonus_add`` 只属于通用公式；必须自筛公式，否则会在反应伤害
    查询上被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
    """

    def __init__(self, *, owner_ref: str, slot: int, bonus: float) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._bonus = bonus
        self._provider_key = f"{THUNDERSOOTHER_KEY_PREFIX}.4p.electro_bonus.slot:{slot}"
        self._source_ref = content_source_ref(THUNDERSOOTHER_KEY_PREFIX, "4p", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name="平息鸣雷的尊者 4件套",
        )
        self._aura_port: TargetElementAuraReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        element_aura_port: TargetElementAuraReadPort,
    ) -> None:
        """装配期注入目标附着只读端口；未绑定时不贡献。"""

        self._aura_port = element_aura_port

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        request = query.request
        if request.source_ref != self._owner_ref:
            return ()
        if request.formula_key is not FORMULA_KEY_GENERAL:
            return ()
        if request.target_ref.kind is not AttributeSubjectKind.TARGET:
            return ()
        port = self._aura_port
        if port is None:
            return ()
        if not port.is_affected_by(
            request.target_ref,
            THUNDERSOOTHER_AFFECTED_ELEMENT,
            request.frame,
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(THUNDERSOOTHER_4P_AUDIT_TAG,),
            ),
        )
