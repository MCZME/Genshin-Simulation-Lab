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
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
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
    TargetAuraFrozenReadPort,
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
                    )
                )
        if terms:
            providers.append(
                StaticModifierProvider(
                    ModifierProviderSpec(
                        provider_key=provider_key,
                        writes=frozenset(term.target_key for term in terms),
                        owner_ref=subject_ref,
                    ),
                    tuple(terms),
                    subject_ref=subject_ref,
                )
            )
    return tuple(providers)


class ResonanceCryoCritDamageProvider:
    """双冰：攻击冰附着或冻结目标时暴击率 +15%。"""

    provider_spec = DamageModifierProviderSpec(
        provider_key="resonance.cryo.crit_rate",
        writes=frozenset({DamageModifierStage.CRIT_RATE_ADD}),
    )

    def __init__(self, active: bool) -> None:
        self._active = active
        self._aura_frozen_port: TargetAuraFrozenReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        aura_frozen_port: TargetAuraFrozenReadPort,
    ) -> None:
        self._aura_frozen_port = aura_frozen_port

    def contribute(self, query, session):
        del session
        if not self._active or self._aura_frozen_port is None:
            return ()
        target_ref = query.request.target_ref
        if target_ref.kind is not AttributeSubjectKind.TARGET:
            return ()
        if not self._aura_frozen_port.has_cryo_or_frozen(
            target_ref,
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
    """双岩：处于护盾庇护下或存在月笼时造成的伤害 +15%。"""

    provider_spec = DamageModifierProviderSpec(
        provider_key="resonance.geo.damage_bonus",
        writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
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

    def contribute(self, query, session):
        del session
        if not self._active or self._shield_port is None or self._lunar_cage_port is None:
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
