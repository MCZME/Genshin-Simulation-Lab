from typing import Protocol

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.coordination.character_ability_condition.models import (
    CharacterAbilityConditionQuery,
    CharacterAbilityConditionResult,
)
from genshin_sim.core.systems.cooldown import CooldownConditionResult, CooldownQuery
from genshin_sim.core.systems.energy import BurstEnergyConditionResult


class CooldownConditionReadPort(Protocol):
    def query_condition(self, query: CooldownQuery) -> CooldownConditionResult: ...


class BurstEnergyConditionReadPort(Protocol):
    def query_burst_condition(
        self, character_ref: AttributeSubjectRef, frame: int
    ) -> BurstEnergyConditionResult: ...


class CharacterAbilityConditionPort(Protocol):
    def evaluate(
        self, query: CharacterAbilityConditionQuery
    ) -> CharacterAbilityConditionResult: ...
