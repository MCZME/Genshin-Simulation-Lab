"""属性探针·单手剑：静态属性修饰武器（角色状态详情验证用合成内容）。

提供穿戴者固定的生命值上限加成与攻击力百分比加成，用来验证 content
属性 provider 的词条来源、归属过滤与前端展开显示。所有数值均为测试
固定值，不代表任何真实游戏数据。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import WeaponContentUnitRequest
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STAT_HP_MAX,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
)

ATTRIBUTE_PROBE_WEAPON_HANDLER_KEY = "weapon.testing.attribute_probe"
ATTRIBUTE_PROBE_WEAPON_ASSET_KEY = "weapon:test_attribute_probe"
ATTRIBUTE_PROBE_WEAPON_CONTENT_VERSION = "dev-attribute-probe-weapon"

# 探针武器固定值：生命值上限 +1000、攻击力 +30%。
ATTRIBUTE_PROBE_WEAPON_FLAT_HP_VALUE = 1000.0
ATTRIBUTE_PROBE_WEAPON_ATK_PERCENT_VALUE = 0.3


def create_attribute_probe_weapon_content_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """属性探针武器内容单元工厂。"""

    if request.weapon_key != ATTRIBUTE_PROBE_WEAPON_ASSET_KEY:
        raise ContentUnitValidationError(
            f"{ATTRIBUTE_PROBE_WEAPON_HANDLER_KEY!r} 只绑定 "
            f"{ATTRIBUTE_PROBE_WEAPON_ASSET_KEY}，收到 {request.weapon_key!r}"
        )
    owner_ref = AttributeSubjectRef.character(f"character:slot_{request.slot}")
    provider_key = f"{ATTRIBUTE_PROBE_WEAPON_HANDLER_KEY}.static.slot:{request.slot}"
    source_ref = RuntimeSourceRef(
        RuntimeSourceKind.CONTENT,
        f"{ATTRIBUTE_PROBE_WEAPON_HANDLER_KEY}:static:slot:{request.slot}",
    )
    terms = (
        ModifierTerm(
            target_key=STAT_HP_MAX,
            stage=ModifierStage.FLAT_ADD,
            value=ATTRIBUTE_PROBE_WEAPON_FLAT_HP_VALUE,
            provider_key=provider_key,
            source_ref=source_ref,
            audit_tags=("attribute_probe_weapon_flat_hp",),
        ),
        ModifierTerm(
            target_key=STAT_ATK_TOTAL,
            stage=ModifierStage.PERCENT_ADD,
            value=ATTRIBUTE_PROBE_WEAPON_ATK_PERCENT_VALUE,
            provider_key=provider_key,
            source_ref=source_ref,
            audit_tags=("attribute_probe_weapon_atk_percent",),
        ),
    )
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset(term.target_key for term in terms),
            owner_ref=owner_ref,
            display_name="属性探针·武器被动",
        ),
        terms,
        subject_ref=owner_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=ATTRIBUTE_PROBE_WEAPON_HANDLER_KEY,
        version=ATTRIBUTE_PROBE_WEAPON_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"purpose": "testing_attribute_probe_weapon"},
    )
