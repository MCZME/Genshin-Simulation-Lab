from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.coordination.character_ability_condition.errors import (
    CharacterAbilityConditionConflictError,
    CharacterAbilityConditionValidationError,
)
from genshin_sim.core.coordination.character_ability_condition.models import (
    AbilityConditionBlockingReason,
    AbilityConditionDelegation,
    CharacterAbilityConditionQuery,
    CharacterAbilityConditionResult,
)
from genshin_sim.core.coordination.character_ability_condition.protocols import (
    BurstEnergyConditionReadPort,
    CooldownConditionReadPort,
)
from genshin_sim.core.systems.cooldown import (
    AbilityKind,
    CooldownKey,
    CooldownQuery,
    CooldownSubjectRef,
)
from genshin_sim.core.systems.energy import BurstEnergyConditionStatus


class CharacterAbilityConditionCoordinator:
    """组合冷却与标准元素能量证据的无状态只读协调器。"""

    def __init__(
        self,
        cooldown_port: CooldownConditionReadPort,
        energy_port: BurstEnergyConditionReadPort,
    ) -> None:
        self._cooldown_port = cooldown_port
        self._energy_port = energy_port

    def evaluate(self, query: CharacterAbilityConditionQuery) -> CharacterAbilityConditionResult:
        if not isinstance(query, CharacterAbilityConditionQuery):
            raise CharacterAbilityConditionValidationError(
                "query 必须是 CharacterAbilityConditionQuery"
            )
        cooldown_query = CooldownQuery(
            CooldownKey(CooldownSubjectRef.character(query.character_id), query.ability_key),
            query.frame,
        )
        cooldown = self._cooldown_port.query_condition(cooldown_query)
        if cooldown.query != cooldown_query or cooldown.view.key != cooldown_query.key:
            raise CharacterAbilityConditionConflictError("冷却条件证据与查询 key 不一致")
        if cooldown.query.frame != query.frame:
            raise CharacterAbilityConditionConflictError("冷却条件证据 frame 不一致")
        ability_kind = cooldown.view.ability_kind
        if ability_kind is AbilityKind.ELEMENTAL_SKILL:
            return CharacterAbilityConditionResult(
                query,
                ability_kind,
                cooldown.satisfied,
                cooldown,
                None,
                ()
                if cooldown.satisfied
                else (AbilityConditionBlockingReason.COOLDOWN_UNAVAILABLE,),
                (),
            )
        if ability_kind is not AbilityKind.ELEMENTAL_BURST:
            raise CharacterAbilityConditionValidationError("不支持的角色能力类型")
        character_ref = AttributeSubjectRef.character(query.character_id)
        energy = self._energy_port.query_burst_condition(character_ref, query.frame)
        if energy.character_ref != character_ref or energy.frame != query.frame:
            raise CharacterAbilityConditionConflictError("爆发能量条件证据主体或 frame 不一致")
        blocking: list[AbilityConditionBlockingReason] = []
        if not cooldown.satisfied:
            blocking.append(AbilityConditionBlockingReason.COOLDOWN_UNAVAILABLE)
        delegation: tuple[AbilityConditionDelegation, ...] = ()
        if energy.status is BurstEnergyConditionStatus.INSUFFICIENT_ENERGY:
            blocking.append(AbilityConditionBlockingReason.STANDARD_ENERGY_UNAVAILABLE)
        elif energy.status is BurstEnergyConditionStatus.NONSTANDARD_RESOURCE:
            delegation = (AbilityConditionDelegation.CONTENT_PRIVATE_RESOURCE,)
        return CharacterAbilityConditionResult(
            query,
            ability_kind,
            not blocking,
            cooldown,
            energy,
            tuple(blocking),
            delegation,
        )
