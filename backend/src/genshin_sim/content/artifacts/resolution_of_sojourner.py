"""行者之心圣遗物套装实现。

效果与落点：

- 2 件套：攻击力提高 18% -> ``stat.atk.total`` 的 ``percent_add``，
  静态绑定穿戴者。
- 4 件套：重击的暴击率提升 30% -> 通用公式 ``crit_rate_add`` 阶段，
  按 ``main_attack_tag == "重击"`` 过滤，静态绑定穿戴者，不落 Buff。

行为约定：

- 4 件套是「瞬时作用于一次伤害」的判定，与影中沉凝的幻灭 C3 同型：
  ``crit_rate_add`` 的契约语义就是「只参与本次伤害的暴击率调整」，写进
  面板或做成有生命周期的 Buff 都会把作用域放大到多次伤害。
- 「重击」按内容层攻击标签约定识别：各角色重击伤害统一使用
  ``"重击"`` 主攻击标签。
- 伤害 provider 自筛公式：``crit_rate_add`` 只属于通用公式，越界阶段
  会被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
"""

from __future__ import annotations

from genshin_sim.content.artifacts._common import (
    CHARGED_ATTACK_MAIN_ATTACK_TAG,
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
    STAT_ATK_TOTAL,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    StaticModifierProvider,
)
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

RESOLUTION_OF_SOJOURNER_KEY_PREFIX = "artifact.resolution_of_sojourner"
RESOLUTION_OF_SOJOURNER_HANDLER_KEY = RESOLUTION_OF_SOJOURNER_KEY_PREFIX
RESOLUTION_OF_SOJOURNER_2P_HANDLER_KEY = f"{RESOLUTION_OF_SOJOURNER_KEY_PREFIX}.2p"
RESOLUTION_OF_SOJOURNER_4P_HANDLER_KEY = f"{RESOLUTION_OF_SOJOURNER_KEY_PREFIX}.4p"
RESOLUTION_OF_SOJOURNER_CONTENT_VERSION = "release"

RESOLUTION_OF_SOJOURNER_2P_AUDIT_TAG = "resolution_of_sojourner_2p"
RESOLUTION_OF_SOJOURNER_4P_AUDIT_TAG = "resolution_of_sojourner_4p"


def create_resolution_of_sojourner_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """行者之心套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    require_set_row(request, handler_key=RESOLUTION_OF_SOJOURNER_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=RESOLUTION_OF_SOJOURNER_HANDLER_KEY,
        version=RESOLUTION_OF_SOJOURNER_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "resolution_of_sojourner_set_identity"},
    )


def create_resolution_of_sojourner_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """行者之心 2 件套：攻击力提高。"""

    require_piece_count(
        request,
        expected=2,
        handler_key=RESOLUTION_OF_SOJOURNER_2P_HANDLER_KEY,
    )
    (atk_percent,) = parse_component_values(
        request.params,
        count=1,
        purpose="2 件套攻击力加成",
    )
    subject_ref = AttributeSubjectRef.character(slot_owner_ref(request.slot))
    provider_key = f"{RESOLUTION_OF_SOJOURNER_KEY_PREFIX}.2p.atk_percent.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({STAT_ATK_TOTAL}),
            owner_ref=subject_ref,
            display_name="行者之心 2件套",
        ),
        (
            ModifierTerm(
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                value=atk_percent,
                provider_key=provider_key,
                source_ref=content_source_ref(
                    RESOLUTION_OF_SOJOURNER_KEY_PREFIX, "2p", request.slot
                ),
                audit_tags=(RESOLUTION_OF_SOJOURNER_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=RESOLUTION_OF_SOJOURNER_2P_HANDLER_KEY,
        version=RESOLUTION_OF_SOJOURNER_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "resolution_of_sojourner_2p"},
    )


def create_resolution_of_sojourner_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """行者之心 4 件套：重击的暴击率提升。"""

    require_piece_count(
        request,
        expected=4,
        handler_key=RESOLUTION_OF_SOJOURNER_4P_HANDLER_KEY,
    )
    (crit_rate,) = parse_component_values(
        request.params,
        count=1,
        purpose="4 件套重击暴击率加成",
    )
    owner_ref = slot_owner_ref(request.slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=RESOLUTION_OF_SOJOURNER_4P_HANDLER_KEY,
        version=RESOLUTION_OF_SOJOURNER_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=(
            ResolutionOfSojournerChargedCritProvider(
                owner_ref=owner_ref,
                slot=request.slot,
                crit_rate=crit_rate,
            ),
        ),
        metadata={"piece_count": 4, "purpose": "resolution_of_sojourner_4p"},
    )


class ResolutionOfSojournerChargedCritProvider:
    """4 件套：装备者的重击暴击率提升。

    ``crit_rate_add`` 只属于通用公式；必须自筛公式，否则会在反应伤害
    查询上被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
    """

    def __init__(self, *, owner_ref: str, slot: int, crit_rate: float) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._crit_rate = crit_rate
        self._provider_key = f"{RESOLUTION_OF_SOJOURNER_KEY_PREFIX}.4p.charged_crit.slot:{slot}"
        self._source_ref = content_source_ref(RESOLUTION_OF_SOJOURNER_KEY_PREFIX, "4p", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.CRIT_RATE_ADD}),
            owner_ref=self._owner_ref,
            display_name="行者之心 4件套",
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
        if request.formula_key is not FORMULA_KEY_GENERAL:
            return ()
        if request.main_attack_tag != CHARGED_ATTACK_MAIN_ATTACK_TAG:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.CRIT_RATE_ADD,
                value=self._crit_rate,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(RESOLUTION_OF_SOJOURNER_4P_AUDIT_TAG,),
            ),
        )
