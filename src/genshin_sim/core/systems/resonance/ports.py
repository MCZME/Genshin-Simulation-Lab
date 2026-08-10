"""元素共鸣对外提供的窄只读端口实现。"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Protocol

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import AuraKind, ElementalSubjectKind, ElementalSubjectRef
from genshin_sim.core.systems.aura.models import AuraDurationTerm
from genshin_sim.core.systems.cooldown import (
    CooldownDurationOperation,
    CooldownDurationStage,
    CooldownDurationTerm,
    CooldownKey,
)
from genshin_sim.core.systems.resonance.models import ResonanceActivation, ResonanceDefinition


class TargetAuraFrozenReadPort(Protocol):
    """查询目标是否处于冰附着或冻结状态。"""

    def has_cryo_or_frozen(
        self,
        target_ref: AttributeSubjectRef,
        frame: int,
    ) -> bool: ...


class CharacterShieldPresenceReadPort(Protocol):
    """查询角色是否处于护盾庇护下。"""

    def has_active_shield(
        self,
        character_ref: AttributeSubjectRef,
        frame: int,
    ) -> bool: ...


class LunarCagePresenceReadPort(Protocol):
    """查询队伍附近是否存在活动月笼（第一版按存在即生效）。"""

    def has_active_lunar_cage(self) -> bool: ...


class ResonanceAuraDurationTermProvider:
    """按激活共鸣为角色主体的指定 Aura 提供时长修正 term。"""

    def __init__(
        self,
        activation: ResonanceActivation,
        definitions: tuple[ResonanceDefinition, ...],
    ) -> None:
        by_key = {definition.key: definition for definition in definitions}
        multipliers: dict[AuraKind, Fraction] = {}
        for key in activation.active_keys:
            for rule in by_key[key].aura_duration_rules:
                multipliers[rule.aura_kind] = (
                    multipliers.get(rule.aura_kind, Fraction(1)) * rule.multiplier
                )
        self._multipliers = multipliers

    def duration_terms_for(
        self,
        subject_ref: ElementalSubjectRef,
        aura_kind: AuraKind,
    ) -> tuple[AuraDurationTerm, ...]:
        if subject_ref.kind is not ElementalSubjectKind.CHARACTER:
            return ()
        multiplier = self._multipliers.get(aura_kind)
        if multiplier is None:
            return ()
        return (
            AuraDurationTerm(
                term_key=f"resonance.duration.{aura_kind.value}",
                source_ref="resonance",
                multiplier=multiplier,
            ),
        )


class ResonanceCooldownDurationTermProvider:
    """按激活共鸣为任意角色能力冷却提供统一的时长修正 term。"""

    def __init__(
        self,
        activation: ResonanceActivation,
        definitions: tuple[ResonanceDefinition, ...],
    ) -> None:
        by_key = {definition.key: definition for definition in definitions}
        multiplier: Fraction | None = None
        for key in activation.active_keys:
            candidate = by_key[key].cooldown_duration_multiplier
            if candidate is None:
                continue
            multiplier = candidate if multiplier is None else multiplier * candidate
        self._multiplier = multiplier

    def terms_for(self, key: CooldownKey) -> tuple[CooldownDurationTerm, ...]:
        del key
        if self._multiplier is None:
            return ()
        return (
            CooldownDurationTerm(
                term_key="resonance.cooldown",
                source_ref="resonance",
                stage=CooldownDurationStage.OWNER_ADJUSTMENT,
                operation=CooldownDurationOperation.MULTIPLY_CURRENT,
                value=Decimal(self._multiplier.numerator) / Decimal(self._multiplier.denominator),
            ),
        )
