"""内容单元 ContentUnit 契约。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from genshin_sim.content.definitions.effects import EffectSpec
from genshin_sim.content.models import EventHook, Modifier
from genshin_sim.core.actions import Action, ActionInterpreter
from genshin_sim.core.attributes import (
    AttributeDefinition,
    ModifierProvider,
    ModifierStackingGroupDefinition,
)
from genshin_sim.core.contracts.json import JSONValue, validate_json_compatible
from genshin_sim.core.contracts.phases import MountPoint
from genshin_sim.core.contracts.state_schema import StateSchema
from genshin_sim.core.impacts import ImpactFactory
from genshin_sim.core.space import CreatedObjectBehavior
from genshin_sim.core.systems.aura_icd import IcdDefinition
from genshin_sim.core.systems.buff import BuffDefinition
from genshin_sim.core.systems.cooldown import (
    CooldownDefinition,
    CooldownDurationTerm,
    CooldownKey,
)
from genshin_sim.core.systems.damage import (
    DamageModifierProvider,
    DamageModifierStackingGroupDefinition,
)
from genshin_sim.core.systems.infusion import InfusionDefinition


class ContentUnitError(Exception):
    """内容单元错误基类。"""


class ContentUnitValidationError(ContentUnitError, ValueError):
    """内容单元定义不合法。"""


class ContentUnitOwnerType(StrEnum):
    """内容单元所有者类型。"""

    CHARACTER = "character"
    WEAPON = "weapon"
    ARTIFACT = "artifact"


@dataclass(frozen=True, slots=True)
class ContentUnit:
    """一个内容单元：身份 + 编译参数 + 能力切片 + 挂点声明。

    ``actions``/``modifiers``/``buff_definitions``/``cooldown_definitions``
    等切片在 M0 阶段以对象占位，后续里程碑钉死具体协议类型。
    """

    owner_type: ContentUnitOwnerType
    owner_key: str
    handler_key: str
    version: str
    slot: int | None = None
    compiled_params: Mapping[str, JSONValue] = field(default_factory=dict)
    action_interpreter: ActionInterpreter | None = None
    actions: Sequence[Action] = field(default_factory=tuple)
    effects: Sequence[EffectSpec] = field(default_factory=tuple)
    state_schema: StateSchema | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)
    impact_factories: Mapping[str, ImpactFactory] = field(default_factory=dict)
    created_object_behaviors: Mapping[str, CreatedObjectBehavior] = field(default_factory=dict)
    event_hooks: Sequence[EventHook] = field(default_factory=tuple)
    modifiers: Sequence[Modifier] = field(default_factory=tuple)
    attribute_definitions: Sequence[AttributeDefinition] = field(default_factory=tuple)
    attribute_stacking_groups: Sequence[ModifierStackingGroupDefinition] = field(
        default_factory=tuple
    )
    attribute_providers: Sequence[ModifierProvider] = field(default_factory=tuple)
    damage_modifier_providers: Sequence[DamageModifierProvider] = field(default_factory=tuple)
    damage_modifier_stacking_groups: Sequence[DamageModifierStackingGroupDefinition] = field(
        default_factory=tuple
    )
    buff_definitions: Sequence[BuffDefinition] = field(default_factory=tuple)
    infusion_definitions: Sequence[InfusionDefinition] = field(default_factory=tuple)
    aura_icd_definitions: Sequence[IcdDefinition] = field(default_factory=tuple)
    cooldown_definitions: Sequence[CooldownDefinition] = field(default_factory=tuple)
    talent_level_boosts: Mapping[str, int] = field(default_factory=dict)
    cooldown_duration_terms: Mapping[
        CooldownKey,
        tuple[CooldownDurationTerm, ...],
    ] = field(default_factory=dict)
    reaction_capabilities: Sequence[str] = field(default_factory=tuple)
    mount_points: Sequence[MountPoint] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.owner_type, ContentUnitOwnerType):
            raise TypeError("owner_type 必须是 ContentUnitOwnerType")
        _require_non_empty(self.owner_key, "owner_key")
        _require_non_empty(self.handler_key, "handler_key")
        _require_non_empty(self.version, "version")
        if self.slot is not None:
            _require_positive_int(self.slot, "slot")
        if self.owner_type is ContentUnitOwnerType.CHARACTER and self.slot is None:
            raise ContentUnitValidationError("角色内容单元必须提供正整数 slot")
        validate_json_compatible(self.compiled_params, path="compiled_params")
        object.__setattr__(self, "compiled_params", dict(self.compiled_params))
        object.__setattr__(self, "actions", tuple(self.actions))
        object.__setattr__(self, "effects", tuple(self.effects))
        validate_json_compatible(self.metadata, path="metadata")
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(self, "impact_factories", dict(self.impact_factories))
        object.__setattr__(
            self,
            "created_object_behaviors",
            dict(self.created_object_behaviors),
        )
        object.__setattr__(self, "event_hooks", tuple(self.event_hooks))
        object.__setattr__(self, "modifiers", tuple(self.modifiers))
        object.__setattr__(
            self,
            "attribute_definitions",
            tuple(self.attribute_definitions),
        )
        object.__setattr__(
            self,
            "attribute_stacking_groups",
            tuple(self.attribute_stacking_groups),
        )
        object.__setattr__(
            self,
            "attribute_providers",
            tuple(self.attribute_providers),
        )
        object.__setattr__(
            self,
            "damage_modifier_providers",
            tuple(self.damage_modifier_providers),
        )
        object.__setattr__(
            self,
            "damage_modifier_stacking_groups",
            tuple(self.damage_modifier_stacking_groups),
        )
        object.__setattr__(self, "buff_definitions", tuple(self.buff_definitions))
        object.__setattr__(
            self,
            "infusion_definitions",
            tuple(self.infusion_definitions),
        )
        for definition in self.infusion_definitions:
            if not isinstance(definition, InfusionDefinition):
                raise ContentUnitValidationError(
                    "infusion_definitions 成员必须是 InfusionDefinition"
                )
        if self.infusion_definitions and self.owner_type is not ContentUnitOwnerType.CHARACTER:
            raise ContentUnitValidationError("只有角色内容单元可以贡献附魔定义")
        object.__setattr__(
            self,
            "aura_icd_definitions",
            tuple(self.aura_icd_definitions),
        )
        for definition in self.aura_icd_definitions:
            if not isinstance(definition, IcdDefinition):
                raise ContentUnitValidationError("aura_icd_definitions 成员必须是 IcdDefinition")
        object.__setattr__(
            self,
            "cooldown_definitions",
            tuple(self.cooldown_definitions),
        )
        for definition in self.cooldown_definitions:
            if not isinstance(definition, CooldownDefinition):
                raise ContentUnitValidationError(
                    "cooldown_definitions 成员必须是 CooldownDefinition"
                )
        object.__setattr__(self, "talent_level_boosts", dict(self.talent_level_boosts))
        for talent_key, boost in self.talent_level_boosts.items():
            if not isinstance(talent_key, str) or not talent_key.strip():
                raise ContentUnitValidationError("talent_level_boosts 天赋键必须是非空字符串")
            if isinstance(boost, bool) or not isinstance(boost, int) or boost <= 0:
                raise ContentUnitValidationError("talent_level_boosts 等级提升必须是正整数")
        object.__setattr__(
            self,
            "cooldown_duration_terms",
            {key: tuple(terms) for key, terms in self.cooldown_duration_terms.items()},
        )
        for key, terms in self.cooldown_duration_terms.items():
            if not isinstance(key, CooldownKey):
                raise ContentUnitValidationError("cooldown_duration_terms 键必须是 CooldownKey")
            for term in terms:
                if not isinstance(term, CooldownDurationTerm):
                    raise ContentUnitValidationError(
                        "cooldown_duration_terms 成员必须是 CooldownDurationTerm"
                    )
        object.__setattr__(
            self,
            "reaction_capabilities",
            tuple(self.reaction_capabilities),
        )
        object.__setattr__(self, "mount_points", tuple(self.mount_points))
        self._validate_interpreter_slice()
        self._validate_created_object_behaviors()
        self._validate_impact_factory_keys()
        self._validate_effect_keys()
        self._validate_reaction_capabilities()
        self._validate_mount_points()

    def _validate_effect_keys(self) -> None:
        keys = [effect.effect_key for effect in self.effects]
        if len(keys) != len(set(keys)):
            raise ContentUnitValidationError("effects 中不能包含重复 effect_key")

    def _validate_interpreter_slice(self) -> None:
        if self.action_interpreter is None:
            return
        if self.owner_type is not ContentUnitOwnerType.CHARACTER:
            raise ContentUnitValidationError("只有角色内容单元可以贡献动作解释器")
        if self.slot is None:
            raise ContentUnitValidationError("角色动作解释器必须绑定队伍槽位")

    def _validate_created_object_behaviors(self) -> None:
        if not self.created_object_behaviors:
            return
        if self.owner_type is not ContentUnitOwnerType.CHARACTER:
            raise ContentUnitValidationError("只有角色内容单元可以贡献内容创建对象行为")
        for behavior_key in self.created_object_behaviors:
            _require_non_empty(behavior_key, "created_object_behaviors key")

    def _validate_impact_factory_keys(self) -> None:
        for impact_key in self.impact_factories:
            _require_non_empty(impact_key, "impact_factories key")

    def _validate_reaction_capabilities(self) -> None:
        capabilities = self.reaction_capabilities
        if not capabilities:
            return
        if self.owner_type is not ContentUnitOwnerType.CHARACTER:
            raise ContentUnitValidationError("只有角色内容单元可以声明 reaction capabilities")
        if self.slot is None:
            raise ContentUnitValidationError("声明 reaction capabilities 的角色必须提供 slot")
        for capability in capabilities:
            if not isinstance(capability, str) or not capability.strip():
                raise ContentUnitValidationError("reaction capability 必须是非空字符串")
        if len(set(capabilities)) != len(capabilities):
            raise ContentUnitValidationError("reaction_capabilities 不能包含重复 key")

    def _validate_mount_points(self) -> None:
        pairs = [(point.phase, point.key) for point in self.mount_points]
        if len(pairs) != len(set(pairs)):
            raise ContentUnitValidationError("mount_points 不能包含重复 (phase, key)")


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContentUnitValidationError(f"{field_name} 必须是非空字符串")


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContentUnitValidationError(f"{field_name} 必须是正整数")
