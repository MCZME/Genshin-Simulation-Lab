from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from genshin_sim.core.attributes.errors import (
    AttributeValidationError,
    UnknownAttributeError,
)
from genshin_sim.core.attributes.keys import (
    BONUS_DAMAGE_ANEMO,
    BONUS_DAMAGE_CRYO,
    BONUS_DAMAGE_DENDRO,
    BONUS_DAMAGE_ELECTRO,
    BONUS_DAMAGE_GEO,
    BONUS_DAMAGE_HYDRO,
    BONUS_DAMAGE_PHYSICAL,
    BONUS_DAMAGE_PYRO,
    BONUS_HEALING_INCOMING,
    BONUS_HEALING_OUTGOING,
    BONUS_SHIELD_STRENGTH,
    PUBLIC_ATTRIBUTE_KEYS,
    RESISTANCE_ANEMO,
    RESISTANCE_CRYO,
    RESISTANCE_DENDRO,
    RESISTANCE_ELECTRO,
    RESISTANCE_GEO,
    RESISTANCE_HYDRO,
    RESISTANCE_PHYSICAL,
    RESISTANCE_PYRO,
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    STAT_CRIT_DAMAGE,
    STAT_CRIT_RATE,
    STAT_DEF_BASE,
    STAT_DEF_TOTAL,
    STAT_ELEMENTAL_MASTERY,
    STAT_ENERGY_RECHARGE,
    STAT_HP_BASE,
    STAT_HP_MAX,
    AttributeKey,
)
from genshin_sim.core.attributes.models import (
    AttributeSubjectKind,
    ModifierStage,
    validate_finite_float,
)


class MissingValuePolicy(StrEnum):
    USE_DEFAULT = "use_default"
    ERROR = "error"


class AttributeVisibility(StrEnum):
    PUBLIC = "public"
    CONTENT_PRIVATE = "content_private"


class OverridePolicy(StrEnum):
    FORBIDDEN = "forbidden"
    SINGLE = "single"


class ModifierStackingPolicy(StrEnum):
    HIGHEST = "highest"
    LOWEST = "lowest"


@dataclass(frozen=True, slots=True)
class AttributeDefinition:
    key: AttributeKey
    owner_kinds: frozenset[AttributeSubjectKind]
    policy_key: str
    dependencies: tuple[AttributeKey, ...] = ()
    default_value: float = 0.0
    missing_value_policy: MissingValuePolicy = MissingValuePolicy.USE_DEFAULT
    lower_bound: float | None = None
    upper_bound: float | None = None
    override_policy: OverridePolicy = OverridePolicy.FORBIDDEN
    visibility: AttributeVisibility = AttributeVisibility.PUBLIC
    namespace_owner: str | None = None

    def __post_init__(self) -> None:
        owner_kinds = frozenset(self.owner_kinds)
        if not owner_kinds:
            raise AttributeValidationError("属性定义必须至少支持一个主体类型")
        for owner_kind in owner_kinds:
            if not isinstance(owner_kind, AttributeSubjectKind):
                raise AttributeValidationError("属性定义包含不受支持的主体类型")
        if not isinstance(self.policy_key, str) or not self.policy_key.strip():
            raise AttributeValidationError("policy_key 必须是非空字符串")
        object.__setattr__(self, "owner_kinds", owner_kinds)
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(
            self,
            "default_value",
            validate_finite_float(self.default_value, "default_value"),
        )
        if self.lower_bound is not None:
            object.__setattr__(
                self,
                "lower_bound",
                validate_finite_float(self.lower_bound, "lower_bound"),
            )
        if self.upper_bound is not None:
            object.__setattr__(
                self,
                "upper_bound",
                validate_finite_float(self.upper_bound, "upper_bound"),
            )
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise AttributeValidationError("属性定义 lower_bound 不能大于 upper_bound")
        if not isinstance(self.missing_value_policy, MissingValuePolicy):
            raise AttributeValidationError("missing_value_policy 不受支持")
        if not isinstance(self.override_policy, OverridePolicy):
            raise AttributeValidationError("override_policy 不受支持")
        if not isinstance(self.visibility, AttributeVisibility):
            raise AttributeValidationError("visibility 不受支持")
        if self.visibility is AttributeVisibility.CONTENT_PRIVATE:
            if not self.namespace_owner:
                raise AttributeValidationError("私有属性必须声明 namespace_owner")
            if not str(self.key).startswith(f"{self.namespace_owner}."):
                raise AttributeValidationError("私有属性 key 必须位于 namespace_owner 命名空间内")
        elif self.namespace_owner is not None:
            raise AttributeValidationError("公共属性不能声明 namespace_owner")


@dataclass(frozen=True, slots=True)
class ModifierStackingGroupDefinition:
    group_key: str
    target_key: AttributeKey
    stage: ModifierStage
    policy: ModifierStackingPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.group_key, str) or not self.group_key.strip():
            raise AttributeValidationError("stacking group_key 必须是非空字符串")
        if not isinstance(self.stage, ModifierStage):
            raise AttributeValidationError("stacking group stage 不受支持")
        if not isinstance(self.policy, ModifierStackingPolicy):
            raise AttributeValidationError("stacking policy 不受支持")


class AttributeDefinitionRegistry:
    """保存属性定义和叠加组定义的只读注册表。"""

    def __init__(
        self,
        definitions: tuple[AttributeDefinition, ...] = (),
        stacking_groups: tuple[ModifierStackingGroupDefinition, ...] = (),
    ) -> None:
        self._definitions: dict[AttributeKey, AttributeDefinition] = {}
        self._stacking_groups: dict[str, ModifierStackingGroupDefinition] = {}
        for definition in definitions:
            self.register(definition)
        for group in stacking_groups:
            self.register_stacking_group(group)

    @property
    def definitions(self) -> tuple[AttributeDefinition, ...]:
        return tuple(self._definitions.values())

    @property
    def stacking_groups(self) -> tuple[ModifierStackingGroupDefinition, ...]:
        return tuple(self._stacking_groups.values())

    def register(self, definition: AttributeDefinition) -> AttributeDefinition:
        if definition.key in self._definitions:
            raise AttributeValidationError(f"重复属性定义：{definition.key}")
        self._definitions[definition.key] = definition
        return definition

    def get(self, key: AttributeKey) -> AttributeDefinition:
        try:
            return self._definitions[key]
        except KeyError as exc:
            raise UnknownAttributeError(f"未知属性：{key}") from exc

    def contains(self, key: AttributeKey) -> bool:
        return key in self._definitions

    def register_stacking_group(
        self,
        group: ModifierStackingGroupDefinition,
    ) -> ModifierStackingGroupDefinition:
        if group.group_key in self._stacking_groups:
            raise AttributeValidationError(f"重复 stacking group：{group.group_key}")
        self._stacking_groups[group.group_key] = group
        return group

    def get_stacking_group(self, group_key: str) -> ModifierStackingGroupDefinition | None:
        return self._stacking_groups.get(group_key)


def create_public_attribute_registry() -> AttributeDefinitionRegistry:
    owner_both = frozenset({AttributeSubjectKind.CHARACTER, AttributeSubjectKind.TARGET})
    character_only = frozenset({AttributeSubjectKind.CHARACTER})
    definitions: list[AttributeDefinition] = [
        AttributeDefinition(STAT_HP_BASE, owner_both, "base_sum"),
        AttributeDefinition(STAT_ATK_BASE, character_only, "base_sum"),
        AttributeDefinition(STAT_DEF_BASE, owner_both, "base_sum"),
        AttributeDefinition(STAT_HP_MAX, owner_both, "total_stat", dependencies=(STAT_HP_BASE,)),
        AttributeDefinition(
            STAT_ATK_TOTAL,
            character_only,
            "total_stat",
            dependencies=(STAT_ATK_BASE,),
        ),
        AttributeDefinition(
            STAT_DEF_TOTAL,
            owner_both,
            "total_stat",
            dependencies=(STAT_DEF_BASE,),
        ),
    ]
    additive_keys = tuple(
        key
        for key in PUBLIC_ATTRIBUTE_KEYS
        if key
        not in {
            STAT_HP_BASE,
            STAT_ATK_BASE,
            STAT_DEF_BASE,
            STAT_HP_MAX,
            STAT_ATK_TOTAL,
            STAT_DEF_TOTAL,
        }
    )
    for key in additive_keys:
        if str(key).startswith("resistance."):
            owners = owner_both
        elif key == BONUS_SHIELD_STRENGTH:
            owners = character_only
        else:
            owners = owner_both
        definitions.append(AttributeDefinition(key, owners, "additive", default_value=0.0))
    return AttributeDefinitionRegistry(tuple(definitions))


PUBLIC_ADDITIVE_KEYS = (
    STAT_CRIT_RATE,
    STAT_CRIT_DAMAGE,
    STAT_ELEMENTAL_MASTERY,
    STAT_ENERGY_RECHARGE,
    BONUS_HEALING_OUTGOING,
    BONUS_HEALING_INCOMING,
    BONUS_SHIELD_STRENGTH,
    BONUS_DAMAGE_PHYSICAL,
    BONUS_DAMAGE_PYRO,
    BONUS_DAMAGE_HYDRO,
    BONUS_DAMAGE_ELECTRO,
    BONUS_DAMAGE_CRYO,
    BONUS_DAMAGE_ANEMO,
    BONUS_DAMAGE_GEO,
    BONUS_DAMAGE_DENDRO,
    RESISTANCE_PHYSICAL,
    RESISTANCE_PYRO,
    RESISTANCE_HYDRO,
    RESISTANCE_ELECTRO,
    RESISTANCE_CRYO,
    RESISTANCE_ANEMO,
    RESISTANCE_GEO,
    RESISTANCE_DENDRO,
)
