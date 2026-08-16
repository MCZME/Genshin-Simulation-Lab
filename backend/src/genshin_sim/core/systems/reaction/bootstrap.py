"""当前生产元素反应能力的显式组装入口。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.systems.reaction.establishment_gates import (
    ReactionEstablishmentGateDefinition,
)
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateDefinition
from genshin_sim.core.systems.reaction.mechanics.bloom import (
    bloom_definition,
    bloom_explosion_definition,
    bloom_gate_definitions,
    burgeon_definition,
    hyperbloom_definition,
)
from genshin_sim.core.systems.reaction.mechanics.burning import (
    burning_definition,
    burning_gate_definitions,
)
from genshin_sim.core.systems.reaction.mechanics.catalyze import (
    aggravate_definition,
    quicken_definition,
    spread_definition,
)
from genshin_sim.core.systems.reaction.mechanics.crystallize import (
    crystallize_definition,
    crystallize_establishment_gate_definition,
)
from genshin_sim.core.systems.reaction.mechanics.electro_charged import (
    electro_charged_definition,
    electro_charged_gate_definitions,
)
from genshin_sim.core.systems.reaction.mechanics.frozen import frozen_definition
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom import lunar_bloom_definition
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize import (
    lunar_crystallize_definition,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged import (
    lunar_electro_charged_definition,
    lunar_electro_charged_gate_definitions,
)
from genshin_sim.core.systems.reaction.mechanics.melt import melt_definition
from genshin_sim.core.systems.reaction.mechanics.overloaded import (
    overloaded_definition,
    overloaded_gate_definitions,
)
from genshin_sim.core.systems.reaction.mechanics.shattered import (
    shattered_definition,
    shattered_gate_definitions,
)
from genshin_sim.core.systems.reaction.mechanics.superconduct import (
    superconduct_definition,
    superconduct_gate_definitions,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import (
    swirl_definition,
    swirl_gate_definitions,
)
from genshin_sim.core.systems.reaction.mechanics.vaporize import vaporize_definition
from genshin_sim.core.systems.reaction.runtime import ReactionRegistry, ReactionRuntime


@dataclass(frozen=True, slots=True)
class ReactionBootstrap:
    reaction_registry: ReactionRegistry
    damage_gate_definitions: tuple[ReactionDamageGateDefinition, ...]
    establishment_gate_definitions: tuple[ReactionEstablishmentGateDefinition, ...]

    def create_runtime(self) -> ReactionRuntime:
        return ReactionRuntime(
            self.reaction_registry,
            gate_definitions=self.damage_gate_definitions,
            establishment_gate_definitions=self.establishment_gate_definitions,
        )


def create_default_reaction_bootstrap() -> ReactionBootstrap:
    """组装当前生产支持的全部反应 Definition 与 Gate。"""

    return ReactionBootstrap(
        reaction_registry=ReactionRegistry(
            (
                vaporize_definition(),
                melt_definition(),
                overloaded_definition(),
                superconduct_definition(),
                frozen_definition(),
                shattered_definition(),
                electro_charged_definition(),
                swirl_definition(),
                crystallize_definition(),
                burning_definition(),
                quicken_definition(),
                aggravate_definition(),
                spread_definition(),
                bloom_definition(),
                lunar_bloom_definition(),
                bloom_explosion_definition(),
                hyperbloom_definition(),
                burgeon_definition(),
                lunar_electro_charged_definition(),
                lunar_crystallize_definition(),
            )
        ),
        damage_gate_definitions=(
            *overloaded_gate_definitions(),
            *superconduct_gate_definitions(),
            *shattered_gate_definitions(),
            *electro_charged_gate_definitions(),
            *swirl_gate_definitions(),
            *burning_gate_definitions(),
            *bloom_gate_definitions(),
            *lunar_electro_charged_gate_definitions(),
        ),
        establishment_gate_definitions=(crystallize_establishment_gate_definition(),),
    )
