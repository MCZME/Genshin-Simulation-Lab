from __future__ import annotations

from typing import Protocol

from genshin_sim.core.events import GameEvent
from genshin_sim.core.systems.health import (
    CharacterDamageApplication,
    CharacterDamagePlan,
    HealthCommitReceipt,
)
from genshin_sim.core.systems.shield import (
    ShieldAbsorptionPlan,
    ShieldAbsorptionRequest,
    ShieldCommitReceipt,
)


class ShieldAbsorptionPort(Protocol):
    def prepare_absorption(self, request: ShieldAbsorptionRequest) -> ShieldAbsorptionPlan: ...
    def validate(self, plan: ShieldAbsorptionPlan) -> None: ...
    def commit_prevalidated(self, plan: ShieldAbsorptionPlan) -> ShieldCommitReceipt: ...
    def events_for(self, receipt: ShieldCommitReceipt) -> tuple[GameEvent, ...]: ...


class CharacterHealthDamagePort(Protocol):
    def prepare_damage(self, request: CharacterDamageApplication) -> CharacterDamagePlan: ...
    def validate(self, plan: CharacterDamagePlan) -> None: ...
    def commit_prevalidated(self, plan: CharacterDamagePlan) -> HealthCommitReceipt: ...
    def events_for(self, receipt: HealthCommitReceipt) -> tuple[GameEvent, ...]: ...
