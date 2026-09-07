"""词条探针大剑：静态伤害修饰武器（伤害审计验证用合成内容）。

覆盖武器来源的修饰阶段并演示叠加组拒绝：两个暴击率词条同组竞争，
按 HIGHEST 策略只保留高值，低值进入审计 rejected_terms。
所有数值均为测试固定值，不代表任何真实游戏数据。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import WeaponContentUnitRequest
from genshin_sim.content.test.modifiers import OwnerScopedStaticDamageModifierProvider
from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStackingGroupDefinition,
    DamageModifierStackingPolicy,
    DamageModifierStage,
    DamageModifierTerm,
)

MODIFIER_BLADE_HANDLER_KEY = "weapon.testing.modifier_blade"
MODIFIER_BLADE_ASSET_KEY = "weapon:test_modifier_blade"
MODIFIER_BLADE_CONTENT_VERSION = "dev-modifier-blade"

MODIFIER_BLADE_CRIT_RATE_GROUP_KEY = "testing.modifier_blade.crit_rate_highest"
MODIFIER_BLADE_CRIT_RATE_NEW_PROVIDER_KEY = f"{MODIFIER_BLADE_HANDLER_KEY}.crit_rate.new"
MODIFIER_BLADE_CRIT_RATE_OLD_PROVIDER_KEY = f"{MODIFIER_BLADE_HANDLER_KEY}.crit_rate.old"
MODIFIER_BLADE_CRIT_DAMAGE_PROVIDER_KEY = f"{MODIFIER_BLADE_HANDLER_KEY}.crit_damage"
MODIFIER_BLADE_DEFENSE_IGNORE_PROVIDER_KEY = f"{MODIFIER_BLADE_HANDLER_KEY}.defense_ignore"

# 探针武器固定值：新暴击率词条 +15%（同组竞争生效）、旧词条 +10%（被拒）、
# 暴击伤害 +40%、无视防御 +25%。
MODIFIER_BLADE_CRIT_RATE_NEW_VALUE = 0.15
MODIFIER_BLADE_CRIT_RATE_OLD_VALUE = 0.1
MODIFIER_BLADE_CRIT_DAMAGE_VALUE = 0.4
MODIFIER_BLADE_DEFENSE_IGNORE_VALUE = 0.25


def create_modifier_blade_content_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """词条探针大剑内容单元工厂。"""

    if request.weapon_key != MODIFIER_BLADE_ASSET_KEY:
        raise ContentUnitValidationError(
            f"handler {MODIFIER_BLADE_HANDLER_KEY!r} 只绑定 "
            f"{MODIFIER_BLADE_ASSET_KEY}，收到 {request.weapon_key!r}"
        )
    owner_ref = AttributeSubjectRef.character(f"character:slot_{request.slot}")
    source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, MODIFIER_BLADE_HANDLER_KEY)

    def term(stage: DamageModifierStage, value: float, provider_key: str) -> DamageModifierTerm:
        return DamageModifierTerm(
            stage=stage,
            value=value,
            provider_key=provider_key,
            source_ref=source_ref,
            stacking_group=MODIFIER_BLADE_CRIT_RATE_GROUP_KEY
            if stage is DamageModifierStage.CRIT_RATE_ADD
            else None,
        )

    providers = (
        OwnerScopedStaticDamageModifierProvider(
            DamageModifierProviderSpec(
                provider_key=MODIFIER_BLADE_CRIT_RATE_NEW_PROVIDER_KEY,
                writes=frozenset({DamageModifierStage.CRIT_RATE_ADD}),
                owner_ref=owner_ref,
                display_name="探针武器·暴击率（新词条）",
            ),
            (
                term(
                    DamageModifierStage.CRIT_RATE_ADD,
                    MODIFIER_BLADE_CRIT_RATE_NEW_VALUE,
                    MODIFIER_BLADE_CRIT_RATE_NEW_PROVIDER_KEY,
                ),
            ),
            owner_ref=owner_ref,
        ),
        OwnerScopedStaticDamageModifierProvider(
            DamageModifierProviderSpec(
                provider_key=MODIFIER_BLADE_CRIT_RATE_OLD_PROVIDER_KEY,
                writes=frozenset({DamageModifierStage.CRIT_RATE_ADD}),
                owner_ref=owner_ref,
                display_name="探针武器·暴击率（旧词条）",
            ),
            (
                term(
                    DamageModifierStage.CRIT_RATE_ADD,
                    MODIFIER_BLADE_CRIT_RATE_OLD_VALUE,
                    MODIFIER_BLADE_CRIT_RATE_OLD_PROVIDER_KEY,
                ),
            ),
            owner_ref=owner_ref,
        ),
        OwnerScopedStaticDamageModifierProvider(
            DamageModifierProviderSpec(
                provider_key=MODIFIER_BLADE_CRIT_DAMAGE_PROVIDER_KEY,
                writes=frozenset({DamageModifierStage.CRIT_DAMAGE_ADD}),
                owner_ref=owner_ref,
                display_name="探针武器·暴击伤害",
            ),
            (
                term(
                    DamageModifierStage.CRIT_DAMAGE_ADD,
                    MODIFIER_BLADE_CRIT_DAMAGE_VALUE,
                    MODIFIER_BLADE_CRIT_DAMAGE_PROVIDER_KEY,
                ),
            ),
            owner_ref=owner_ref,
        ),
        OwnerScopedStaticDamageModifierProvider(
            DamageModifierProviderSpec(
                provider_key=MODIFIER_BLADE_DEFENSE_IGNORE_PROVIDER_KEY,
                writes=frozenset({DamageModifierStage.DEFENSE_IGNORE}),
                owner_ref=owner_ref,
                display_name="探针武器·无视防御",
            ),
            (
                term(
                    DamageModifierStage.DEFENSE_IGNORE,
                    MODIFIER_BLADE_DEFENSE_IGNORE_VALUE,
                    MODIFIER_BLADE_DEFENSE_IGNORE_PROVIDER_KEY,
                ),
            ),
            owner_ref=owner_ref,
        ),
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=MODIFIER_BLADE_HANDLER_KEY,
        version=MODIFIER_BLADE_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=providers,
        damage_modifier_stacking_groups=(
            DamageModifierStackingGroupDefinition(
                group_key=MODIFIER_BLADE_CRIT_RATE_GROUP_KEY,
                stage=DamageModifierStage.CRIT_RATE_ADD,
                policy=DamageModifierStackingPolicy.HIGHEST,
            ),
        ),
        metadata={"purpose": "testing_modifier_blade"},
    )
