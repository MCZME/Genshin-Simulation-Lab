"""伤害事实两级作用域经 Impact 请求到伤害结果的纵向链路。

锁定跨模块装配闭环：请求级事实随 ``ImpactRequest`` 透传到每次目标结算，
会话级事实经注册的转发容器在结算当刻读取；provider 按声明读取后产出词条，
取值原样进入审计载荷。合成输入与接线属于本层；作用域叠加与越权边界由
``tests/unit`` 下的伤害事实用例承担。
"""

from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_GENERAL,
    DamageFactIndex,
    DamageFactSpec,
    DamageFactValue,
    DamageModifierIndex,
    DamageModifierProviderSpec,
    DamageProfile,
    DamageProfileRegistry,
    DamageQuery,
    DamageRequestHandler,
    DamageResolutionScope,
    DamageResolver,
    DamageResult,
    DamageScalingTerm,
    FixedCriticalDecisionProvider,
    create_default_damage_formula_registry,
)
from genshin_sim.core.systems.damage.enums import DamageModifierStage
from genshin_sim.core.systems.damage.models import DamageModifierTerm
from tests.helpers import damage

SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.facts.channel")

FACT_KEY = "testing.facts.counter"
PROVIDER_KEY = "testing.facts.bonus"
STORE = "session-store"


class _StateStore:
    """测试用底层状态 store：会话级事实真值的唯一持有者。"""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}


class _ForwardingContainer:
    """会话容器的规定形态：无状态转发视图，直读 store。"""

    def __init__(self, store: _StateStore) -> None:
        self.fact_spec = DamageFactSpec(
            provider_key="testing.facts",
            facts=frozenset({FACT_KEY}),
        )
        self._store = store

    def read_fact(self, key: str) -> DamageFactValue | None:
        return cast("DamageFactValue | None", self._store.values.get(key))


class _FactBonusProvider:
    """事实超过阈值时产出 0.25 增伤的 provider。"""

    def __init__(self, *, reads_facts: frozenset[str], threshold: float) -> None:
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=PROVIDER_KEY,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            reads_facts=reads_facts,
        )
        self._threshold = threshold

    def contribute(
        self, query: DamageQuery, scope: DamageResolutionScope
    ) -> tuple[DamageModifierTerm, ...]:
        del query
        value = scope.read_fact(FACT_KEY)
        if value is None or float(value) <= self._threshold:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=0.25,
                provider_key=PROVIDER_KEY,
                source_ref=RuntimeSourceRef(RuntimeSourceKind.CONTENT, PROVIDER_KEY),
            ),
        )


def _handler(
    *,
    session_store: _StateStore | None = None,
    request_fact_keys: frozenset[str] = frozenset(),
) -> DamageRequestHandler:
    provider = _FactBonusProvider(reads_facts=frozenset({FACT_KEY}), threshold=0.5)
    containers = (_ForwardingContainer(session_store),) if session_store is not None else ()
    return DamageRequestHandler(
        DamageResolver(
            attribute_resolver=damage.make_attribute_resolver(
                (damage.SOURCE,),
                target=damage.TARGET,
                source_context=SOURCE_CONTEXT,
                base_hp=damage.BASE_HP,
            ),
            modifier_index=DamageModifierIndex((provider,)),
            fact_index=DamageFactIndex(containers),
            request_fact_keys=request_fact_keys,
            formula_registry=create_default_damage_formula_registry(
                critical_decision_provider=FixedCriticalDecisionProvider()
            ),
        ),
        profile_registry=DamageProfileRegistry(
            (DamageProfile(FORMULA_KEY_GENERAL, frozenset({"test.damage"})),)
        ),
    )


def _context() -> SimulationContext:
    target = TargetRuntimeState("star", level=90, spatial_entity_id="target:star")
    return SimulationContext(
        space_runtime=SpaceRuntime(
            space=Space(
                (
                    SpatialEntity(
                        "target:star",
                        SpatialEntityKind.TARGET,
                        Vector3(0.0, 0.0, 0.0),
                    ),
                )
            ),
            team_state=TeamRuntimeState(
                (
                    CharacterRuntimeState(
                        1, "character:test", 90, combat_entity_id="character:slot_1"
                    ),
                )
            ),
            targets=TargetRuntimeCollection((target,)),
        )
    )


def _request(*, request_facts: dict[str, DamageFactValue] | None = None) -> ImpactRequest:
    return ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="action.test",
        owner_slot=1,
        request_id="root:facts:1",
        target_refs=("star",),
        request_facts=request_facts or {},
        damage_spec=DamageImpactSpec(
            impact_ref="impact:facts:1",
            main_attack_tag="test.damage",
            element=Element.HYDRO,
            scaling_terms=(DamageScalingTerm("hp", STAT_HP_MAX, 1.0),),
            can_crit=False,
        ),
    )


def _provider_term_value(result: DamageResult) -> float:
    terms = [term for term in result.applied_terms if term.provider_key == PROVIDER_KEY]
    assert len(terms) == 1
    return float(terms[0].value)


def test_request_level_fact_flows_through_handler_to_term_and_audit() -> None:
    handler = _handler(request_fact_keys=frozenset({FACT_KEY}))

    baseline_results = handler.handle_impact_request(_context(), _request())
    boosted_results = handler.handle_impact_request(
        _context(),
        _request(request_facts={FACT_KEY: 1}),
    )

    assert len(baseline_results) == 1
    assert len(boosted_results) == 1
    baseline = baseline_results[0]
    boosted = boosted_results[0]
    assert PROVIDER_KEY not in {term.provider_key for term in baseline.applied_terms}
    assert _provider_term_value(boosted) == pytest.approx(0.25)
    # 请求级事实随结果与审计载荷固化，复现不依赖结算后回读容器。
    assert boosted.request_facts == {FACT_KEY: 1}
    audit = cast(dict[str, object], boosted.to_audit_dict())
    assert audit["request_facts"] == {FACT_KEY: 1}


def test_session_level_fact_read_through_registered_container() -> None:
    store = _StateStore()
    handler = _handler(session_store=store)

    baseline_results = handler.handle_impact_request(_context(), _request())
    store.values[FACT_KEY] = 1
    boosted_results = handler.handle_impact_request(_context(), _request())

    baseline = baseline_results[0]
    boosted = boosted_results[0]
    assert PROVIDER_KEY not in {term.provider_key for term in baseline.applied_terms}
    assert _provider_term_value(boosted) == pytest.approx(0.25)
    # 会话级取值是结算当刻的活值，不进入请求级审计快照。
    assert boosted.request_facts == {}
