"""已确认的同时元素施加策略。"""

from __future__ import annotations

from genshin_sim.core.coordination.elemental_reaction.models import (
    SimultaneousElementApplicationBatch,
    SimultaneousElementApplicationPolicyResult,
    SimultaneousElementApplicationStrategy,
)
from genshin_sim.core.elements import Element


class NoAuraElectroHydroCoexistencePolicy:
    """无 Aura 的水雷同到达只形成共存 Aura，不按任一元素为先手。"""

    policy_key = "simultaneous_application.no_aura_electro_hydro_coexistence"

    def evaluate(
        self,
        batch: SimultaneousElementApplicationBatch,
    ) -> SimultaneousElementApplicationPolicyResult | None:
        if batch.observed_aura.components or len(batch.applications) != 2:
            return None
        if frozenset(item.element for item in batch.applications) != frozenset(
            (Element.HYDRO, Element.ELECTRO)
        ):
            return None
        return SimultaneousElementApplicationPolicyResult(
            policy_key=self.policy_key,
            strategy=SimultaneousElementApplicationStrategy.SUPPORTED_COMMUTATIVE,
        )


class NoAuraHydroCryoFrozenPolicy:
    """无 Aura 的等量水冰同到达以整体冻结结果落地，不虚构先后命中。"""

    policy_key = "simultaneous_application.no_aura_hydro_cryo_frozen"

    def evaluate(
        self,
        batch: SimultaneousElementApplicationBatch,
    ) -> SimultaneousElementApplicationPolicyResult | None:
        if batch.observed_aura.components or len(batch.applications) != 2:
            return None
        applications_by_element = {item.element: item for item in batch.applications}
        if frozenset(applications_by_element) != frozenset((Element.HYDRO, Element.CRYO)):
            return None
        if (
            applications_by_element[Element.HYDRO].elemental_amount
            != applications_by_element[Element.CRYO].elemental_amount
        ):
            return None
        return SimultaneousElementApplicationPolicyResult(
            policy_key=self.policy_key,
            strategy=SimultaneousElementApplicationStrategy.SUPPORTED_COMMUTATIVE,
        )
