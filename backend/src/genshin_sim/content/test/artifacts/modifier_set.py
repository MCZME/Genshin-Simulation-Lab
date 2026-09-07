"""词条探针套装：静态伤害修饰圣遗物（伤害审计验证用合成内容）。

- 2 件套：基础伤害加值 +120（走 BaseDamageAddition，审计 addition_key
  为 ``provider_key.base_damage_flat_add``）。
- 4 件套：基础伤害加值 +80、减防 +20%、增伤 +12%。
所有数值均为测试固定值，不代表任何真实游戏数据。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.content.test.modifiers import OwnerScopedStaticDamageModifierProvider
from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)

MODIFIER_SET_HANDLER_KEY = "artifact.testing.modifier_set"
MODIFIER_SET_ASSET_KEY = "artifact_set:test_modifier_set"
MODIFIER_SET_CONTENT_VERSION = "dev-modifier-set"

MODIFIER_SET_2P_PROVIDER_KEY = f"{MODIFIER_SET_HANDLER_KEY}.2p.base_flat"
MODIFIER_SET_4P_PROVIDER_KEY = f"{MODIFIER_SET_HANDLER_KEY}.4p"

# 探针套装固定值：2 件套基础伤害 +120；4 件套基础伤害 +80、减防 +20%、增伤 +12%。
MODIFIER_SET_2P_BASE_FLAT_VALUE = 120.0
MODIFIER_SET_4P_BASE_FLAT_VALUE = 80.0
MODIFIER_SET_4P_DEFENSE_REDUCTION_VALUE = 0.2
MODIFIER_SET_4P_DAMAGE_BONUS_VALUE = 0.12


def create_modifier_set_content_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """词条探针套装内容单元工厂（按件数分支）。"""

    if request.artifact_key != MODIFIER_SET_ASSET_KEY:
        raise ContentUnitValidationError(
            f"handler {MODIFIER_SET_HANDLER_KEY!r} 只绑定 "
            f"{MODIFIER_SET_ASSET_KEY}，收到 {request.artifact_key!r}"
        )
    if request.artifact_kind != "artifact_set_bonus":
        raise ContentUnitValidationError(f"{MODIFIER_SET_HANDLER_KEY} 只绑定套装效果，不绑定套装行")
    if request.piece_count == 2:
        return _create_two_piece_unit(request)
    if request.piece_count == 4:
        return _create_four_piece_unit(request)
    raise ContentUnitValidationError(
        f"{MODIFIER_SET_HANDLER_KEY} 不支持 {request.piece_count} 件套"
    )


def _create_two_piece_unit(request: ArtifactContentUnitRequest) -> ContentUnit:
    (base_flat,) = _parse_values(request.params, count=1, purpose="2 件套基础伤害加值")
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=MODIFIER_SET_HANDLER_KEY,
        version=MODIFIER_SET_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=_providers(
            request.slot,
            MODIFIER_SET_2P_PROVIDER_KEY,
            "探针套装·二件套基础伤害",
            ((DamageModifierStage.BASE_DAMAGE_FLAT_ADD, base_flat),),
        ),
        metadata={"piece_count": 2, "purpose": "testing_modifier_set_2p"},
    )


def _create_four_piece_unit(request: ArtifactContentUnitRequest) -> ContentUnit:
    base_flat, defense_reduction, damage_bonus = _parse_values(
        request.params,
        count=3,
        purpose="4 件套基础伤害/减防/增伤",
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=MODIFIER_SET_HANDLER_KEY,
        version=MODIFIER_SET_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=_providers(
            request.slot,
            MODIFIER_SET_4P_PROVIDER_KEY,
            "探针套装·四件套",
            (
                (DamageModifierStage.BASE_DAMAGE_FLAT_ADD, base_flat),
                (DamageModifierStage.DEFENSE_REDUCTION, defense_reduction),
                (DamageModifierStage.DAMAGE_BONUS_ADD, damage_bonus),
            ),
        ),
        metadata={"piece_count": 4, "purpose": "testing_modifier_set_4p"},
    )


def _providers(
    slot: int,
    provider_key: str,
    display_name: str,
    stages: tuple[tuple[DamageModifierStage, float], ...],
) -> tuple[OwnerScopedStaticDamageModifierProvider, ...]:
    """按阶段/数值表构造归属过滤到穿戴者的静态 provider。"""

    owner_ref = AttributeSubjectRef.character(f"character:slot_{slot}")
    source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, provider_key)
    terms = tuple(
        DamageModifierTerm(
            stage=stage,
            value=value,
            provider_key=provider_key,
            source_ref=source_ref,
        )
        for stage, value in stages
    )
    return (
        OwnerScopedStaticDamageModifierProvider(
            DamageModifierProviderSpec(
                provider_key=provider_key,
                writes=frozenset(stage for stage, _ in stages),
                owner_ref=owner_ref,
                display_name=display_name,
            ),
            terms,
            owner_ref=owner_ref,
        ),
    )


def _parse_values(
    params: Mapping[str, object],
    *,
    count: int,
    purpose: str,
) -> tuple[float, ...]:
    """从套装效果 params 读取固定值列表（与正式内容 components 约定一致）。"""

    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes))
        or len(components) < count
    ):
        raise ContentUnitValidationError(f"{purpose} 缺少 components 参数")
    values: list[float] = []
    for index in range(count):
        component = components[index]
        if not isinstance(component, Mapping):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 必须是对象")
        raw_values = component.get("values")
        if (
            not isinstance(raw_values, Sequence)
            or isinstance(raw_values, (str, bytes))
            or not raw_values
        ):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 缺少 values")
        value = raw_values[0]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须是数字")
        number = float(value)
        if number <= 0:
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须为正数")
        values.append(number)
    return tuple(values)
