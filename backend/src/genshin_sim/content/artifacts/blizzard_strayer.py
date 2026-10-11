"""冰风迷途的勇士圣遗物套装实现。

效果与落点：

- 2 件套：获得 15% 冰元素伤害加成 -> ``bonus.damage.cryo``
  ``flat_add``，静态绑定穿戴者。
- 4 件套：攻击处于冰元素影响下的敌人时，暴击率提高 20%；若敌人处于
  冻结状态下，则暴击率额外提高 20% -> 通用公式 ``crit_rate_add`` 阶段，
  条件经装配期注入的 ``TargetElementAuraReadAdapter`` 查目标的冰附着
  与冻结状态，静态绑定穿戴者，不落 Buff。

行为约定：

- 「处于冰元素影响下」按 Aura 分量判定：目标带有 ``cryo`` 分量**或**
  处于冻结状态即成立（冻结目标按游戏行为属于受冰元素影响，与双冰
  共鸣 ``ResonanceCryoCritDamageProvider`` 同一口径）。
- 「冻结状态」经 Reaction 运行态查询 ``frozen_state_for``。
- 两段暴击率合并为一条 ``crit_rate_add`` term：受冰影响未冻结贡献
  0.2，冻结贡献合计 0.4。
- ``crit_rate_add`` 只属于通用公式，必须自筛公式，越界阶段会被
  ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
- 附着端口未绑定时（装配完成前）不贡献，条件不会提前生效。
"""

from __future__ import annotations

from typing import Protocol

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
    BONUS_DAMAGE_CRYO,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    StaticModifierProvider,
)
from genshin_sim.core.elements import AuraKind
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

BLIZZARD_STRAYER_KEY_PREFIX = "artifact.blizzard_strayer"
BLIZZARD_STRAYER_HANDLER_KEY = BLIZZARD_STRAYER_KEY_PREFIX
BLIZZARD_STRAYER_2P_HANDLER_KEY = f"{BLIZZARD_STRAYER_KEY_PREFIX}.2p"
BLIZZARD_STRAYER_4P_HANDLER_KEY = f"{BLIZZARD_STRAYER_KEY_PREFIX}.4p"
BLIZZARD_STRAYER_CONTENT_VERSION = "release"

BLIZZARD_STRAYER_2P_AUDIT_TAG = "blizzard_strayer_2p"
BLIZZARD_STRAYER_4P_AUDIT_TAG = "blizzard_strayer_4p"

BLIZZARD_STRAYER_AFFECTED_AURA_KIND = AuraKind.CRYO


class TargetElementAuraReadPort(Protocol):
    """内容侧条件效果读取目标元素附着与冻结状态的窄只读端口。"""

    def has_component(
        self,
        target_ref: AttributeSubjectRef,
        aura_kind: AuraKind,
        frame: int,
    ) -> bool: ...

    def is_frozen(self, target_ref: AttributeSubjectRef, frame: int) -> bool: ...


def create_blizzard_strayer_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """冰风迷途的勇士套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    require_set_row(request, handler_key=BLIZZARD_STRAYER_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=BLIZZARD_STRAYER_HANDLER_KEY,
        version=BLIZZARD_STRAYER_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "blizzard_strayer_set_identity"},
    )


def create_blizzard_strayer_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """冰风迷途的勇士 2 件套：获得冰元素伤害加成。"""

    require_piece_count(
        request,
        expected=2,
        handler_key=BLIZZARD_STRAYER_2P_HANDLER_KEY,
    )
    (cryo_bonus,) = parse_component_values(
        request.params,
        count=1,
        purpose="2 件套冰元素伤害加成",
    )
    subject_ref = AttributeSubjectRef.character(slot_owner_ref(request.slot))
    provider_key = f"{BLIZZARD_STRAYER_KEY_PREFIX}.2p.cryo_bonus.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({BONUS_DAMAGE_CRYO}),
            owner_ref=subject_ref,
            display_name="冰风迷途的勇士 2件套",
        ),
        (
            ModifierTerm(
                target_key=BONUS_DAMAGE_CRYO,
                stage=ModifierStage.FLAT_ADD,
                value=cryo_bonus,
                provider_key=provider_key,
                source_ref=content_source_ref(BLIZZARD_STRAYER_KEY_PREFIX, "2p", request.slot),
                audit_tags=(BLIZZARD_STRAYER_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=BLIZZARD_STRAYER_2P_HANDLER_KEY,
        version=BLIZZARD_STRAYER_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "blizzard_strayer_2p"},
    )


def create_blizzard_strayer_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """冰风迷途的勇士 4 件套：对冰影响/冻结敌人的条件暴击率。"""

    require_piece_count(
        request,
        expected=4,
        handler_key=BLIZZARD_STRAYER_4P_HANDLER_KEY,
    )
    cryo_crit, frozen_crit = parse_component_values(
        request.params,
        count=2,
        purpose="4 件套冰影响暴击率/冻结额外暴击率",
    )
    owner_ref = slot_owner_ref(request.slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=BLIZZARD_STRAYER_4P_HANDLER_KEY,
        version=BLIZZARD_STRAYER_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=(
            BlizzardStrayerCryoCritProvider(
                owner_ref=owner_ref,
                slot=request.slot,
                cryo_crit=cryo_crit,
                frozen_crit=frozen_crit,
            ),
        ),
        metadata={"piece_count": 4, "purpose": "blizzard_strayer_4p"},
    )


class BlizzardStrayerCryoCritProvider:
    """4 件套：攻击冰影响/冻结敌人的条件暴击率。

    ``crit_rate_add`` 只属于通用公式；必须自筛公式，否则会在反应伤害
    查询上被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        cryo_crit: float,
        frozen_crit: float,
    ) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._cryo_crit = cryo_crit
        self._frozen_crit = frozen_crit
        self._provider_key = f"{BLIZZARD_STRAYER_KEY_PREFIX}.4p.cryo_crit.slot:{slot}"
        self._source_ref = content_source_ref(BLIZZARD_STRAYER_KEY_PREFIX, "4p", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.CRIT_RATE_ADD}),
            owner_ref=self._owner_ref,
            display_name="冰风迷途的勇士 4件套·条件暴击率",
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
        frozen = port.is_frozen(request.target_ref, request.frame)
        cryo_affected = frozen or port.has_component(
            request.target_ref,
            BLIZZARD_STRAYER_AFFECTED_AURA_KIND,
            request.frame,
        )
        if not cryo_affected:
            return ()
        crit_rate = self._cryo_crit + (self._frozen_crit if frozen else 0.0)
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.CRIT_RATE_ADD,
                value=crit_rate,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(BLIZZARD_STRAYER_4P_AUDIT_TAG,),
            ),
        )
