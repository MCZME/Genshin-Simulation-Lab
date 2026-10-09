"""无反应附着分支的元素持久性边界集成测试。

风、岩与物理不形成持久 Aura：目标无 Aura 时，风/岩正元素预算只参与同一次
反应判定，不进入普通附着分支。本文件冻结该边界，避免「首个风元素角色接入
时，裸目标直接报错」的回退。
"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, Element
from tests.helpers.reactions import aura_request, target_subject


def test_anemo_apply_aura_on_bare_target_writes_no_persistent_aura(
    reaction_assembled,
) -> None:
    assembled = reaction_assembled(
        meta_name="anemo aura boundary",
        max_frames=200,
        elemental_mastery=0.0,
    )
    subject = target_subject()
    assert assembled.aura_runtime.view(subject).components == ()

    record = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(Element.ANEMO, "boundary:anemo:bare", impact_key="boundary.anemo"),
    )

    assert record.reaction_occurrence_refs == ()
    assert assembled.aura_runtime.view(subject).components == ()
    assert assembled.aura_runtime.view(subject).revision == 0


def test_anemo_apply_aura_on_bare_target_keeps_snapshots_untouched(
    reaction_assembled,
) -> None:
    assembled = reaction_assembled(
        meta_name="anemo aura boundary snapshots",
        max_frames=200,
        elemental_mastery=0.0,
    )
    aura_before = assembled.aura_runtime.snapshot()
    reaction_before = assembled.reaction_runtime.snapshot(0)

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(Element.ANEMO, "boundary:anemo:snapshot", impact_key="boundary.anemo"),
    )

    assert assembled.aura_runtime.snapshot() == aura_before
    assert assembled.reaction_runtime.snapshot(0) == reaction_before


def test_geo_apply_aura_on_bare_target_writes_no_persistent_aura(
    reaction_assembled,
) -> None:
    assembled = reaction_assembled(
        meta_name="geo aura boundary",
        max_frames=200,
        elemental_mastery=0.0,
    )
    subject = target_subject()

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(Element.GEO, "boundary:geo:bare", impact_key="boundary.geo"),
    )

    assert assembled.aura_runtime.view(subject).components == ()


def test_hydro_apply_aura_on_bare_target_still_establishes_aura(
    reaction_assembled,
) -> None:
    """反向保护：可持久元素在裸目标上的普通附着行为不变。"""

    assembled = reaction_assembled(
        meta_name="hydro aura boundary",
        max_frames=200,
        elemental_mastery=0.0,
    )
    subject = target_subject()

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(Element.HYDRO, "boundary:hydro:bare", impact_key="boundary.hydro"),
    )

    component = assembled.aura_runtime.view(subject).component_for(AuraKind.HYDRO)
    assert component is not None
    assert component.aura_kind is AuraKind.HYDRO
