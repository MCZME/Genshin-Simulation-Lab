"""元素共鸣静态属性 provider 构造。"""

from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
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
from genshin_sim.core.systems.resonance.errors import (
    ResonanceDefinitionNotFoundError,
    ResonanceValidationError,
)
from genshin_sim.core.systems.resonance.models import (
    ResonanceActivation,
    ResonanceDefinition,
)
from genshin_sim.core.systems.resonance.ports import (
    CharacterShieldPresenceReadPort,
    LunarCagePresenceReadPort,
)


def build_resonance_static_providers(
    *,
    activation: ResonanceActivation,
    definitions: Iterable[ResonanceDefinition],
    slots: Iterable[int],
) -> tuple[StaticModifierProvider, ...]:
    """按激活集合为每个队伍槽位构造静态属性 provider。"""

    by_key = {definition.key: definition for definition in definitions}
    missing = [key for key in activation.active_keys if key not in by_key]
    if missing:
        raise ResonanceDefinitionNotFoundError(f"激活共鸣缺少定义：{', '.join(missing)}")
    providers: list[StaticModifierProvider] = []
    for slot in sorted(slots):
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ResonanceValidationError("队伍槽位必须是正整数")
        subject_ref = AttributeSubjectRef.character(f"character:slot_{slot}")
        provider_key = f"resonance.static.slot_{slot}"
        terms: list[ModifierTerm] = []
        for key in activation.active_keys:
            for modifier in by_key[key].static_modifiers:
                terms.append(
                    ModifierTerm(
                        target_key=modifier.target_key,
                        stage=modifier.stage,
                        value=modifier.value,
                        provider_key=provider_key,
                        source_ref=RuntimeSourceRef(
                            RuntimeSourceKind.SYSTEM,
                            f"resonance:{key}",
                        ),
                        audit_tags=modifier.audit_tags,
                        provider_display_name=modifier.display_name,
                    )
                )
        if terms:
            providers.append(
                StaticModifierProvider(
                    ModifierProviderSpec(
                        provider_key=provider_key,
                        writes=frozenset(term.target_key for term in terms),
                        owner_ref=subject_ref,
                        display_name="元素共鸣",
                    ),
                    tuple(terms),
                    subject_ref=subject_ref,
                )
            )
    return tuple(providers)


class ResonanceCryoCritDamageProvider:
    """双冰：攻击受冰元素影响的敌人时暴击率 +15%。

    冰元素影响沿用统一口径 ``affected_aura_kinds(Element.CRYO)``（``cryo`` 或
    ``frozen``），与冰风迷途的勇士 4 件套同一口径。

    按请求的 ``can_crit`` 自筛：``crit_rate_add`` 由通用、月曜与星烁三个公式
    放行，剧变因不可暴击而不放行。
    """

    provider_spec = DamageModifierProviderSpec(
        provider_key="resonance.cryo.crit_rate",
        writes=frozenset({DamageModifierStage.CRIT_RATE_ADD}),
        display_name="元素共鸣（双冰）暴击率提升",
    )

    def __init__(self, active: bool) -> None:
        self._active = active
        self._element_aura_port: TargetElementAuraReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        element_aura_port: TargetElementAuraReadPort,
    ) -> None:
        self._element_aura_port = element_aura_port

    def contribute(self, query, scope):
        del scope
        if not self._active or self._element_aura_port is None:
            return ()
        if not query.request.can_crit:
            return ()
        target_ref = query.request.target_ref
        if target_ref.kind is not AttributeSubjectKind.TARGET:
            return ()
        if not self._element_aura_port.is_affected_by(
            target_ref,
            Element.CRYO,
            query.request.frame,
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.CRIT_RATE_ADD,
                value=0.15,
                provider_key=self.provider_spec.provider_key,
                source_ref=RuntimeSourceRef(
                    RuntimeSourceKind.SYSTEM,
                    "resonance:cryo",
                ),
                audit_tags=("resonance.cryo",),
            ),
        )


class ResonanceGeoDamageProvider:
    """双岩：处于护盾庇护下或存在月笼时造成的伤害 +15%。

    ``damage_bonus_add`` 是通用公式独有的增伤槽；月曜与星烁的增伤位是各自的
    ``lunar_base_damage_bonus_add`` / ``stellar_base_bonus_add``，不放行本阶段。
    """

    provider_spec = DamageModifierProviderSpec(
        provider_key="resonance.geo.damage_bonus",
        writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
        display_name="元素共鸣（双岩）伤害提升",
    )

    def __init__(self, active: bool) -> None:
        self._active = active
        self._shield_port: CharacterShieldPresenceReadPort | None = None
        self._lunar_cage_port: LunarCagePresenceReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        shield_port: CharacterShieldPresenceReadPort,
        lunar_cage_port: LunarCagePresenceReadPort,
    ) -> None:
        self._shield_port = shield_port
        self._lunar_cage_port = lunar_cage_port

    def contribute(self, query, scope):
        del scope
        if not self._active or self._shield_port is None or self._lunar_cage_port is None:
            return ()
        if query.request.formula_key is not FORMULA_KEY_GENERAL:
            return ()
        shielded = self._shield_port.has_active_shield(
            query.request.source_ref,
            query.request.frame,
        )
        if not shielded and not self._lunar_cage_port.has_active_lunar_cage():
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=0.15,
                provider_key=self.provider_spec.provider_key,
                source_ref=RuntimeSourceRef(
                    RuntimeSourceKind.SYSTEM,
                    "resonance:geo",
                ),
                audit_tags=("resonance.geo",),
            ),
        )
