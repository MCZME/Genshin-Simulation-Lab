"""共鸣反应响应阶段测试：双雷微粒与双草精通意图。"""

from __future__ import annotations

from typing import cast

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.contracts.intents import IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.coordination.resonance_reaction import ResonanceReactionStage
from genshin_sim.core.events import EventEngine
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.systems.buff.models import ApplyBuffRequest
from genshin_sim.core.systems.resonance import (
    ResonanceActivation,
    ResonanceRuntime,
    ResonanceStore,
    TeamElementComposition,
)
from tests.helpers.events import (
    make_damage_resolved_event,
    make_event_context,
    make_reaction_occurrence_event,
)
from tests.helpers.resonance_ports import (
    FakeLunarCagePresencePort,
    FakeShieldPresencePort,
)

ELECTRO_TRIGGERS = frozenset({"reaction.electro_charged"})
EM_30_TRIGGERS = frozenset({"reaction.bloom"})
EM_20_TRIGGERS = frozenset({"reaction.aggravate"})


def _stage(
    active_keys: tuple[str, ...],
    queue: IntentQueue,
    *,
    shield_present: bool = False,
    lunar_cage_present: bool = False,
) -> ResonanceReactionStage:
    store = ResonanceStore(
        ResonanceActivation(active_keys),
        TeamElementComposition.from_counts(2, {}),
    )
    runtime = ResonanceRuntime(store, EventEngine())
    return ResonanceReactionStage(
        resonance_runtime=runtime,
        intent_queue=queue,
        team_slots=(1, 2),
        electro_particle_triggers=ELECTRO_TRIGGERS,
        dendro_em_30_triggers=EM_30_TRIGGERS,
        dendro_em_20_triggers=EM_20_TRIGGERS,
        dendro_em_30_definition_key="buff.definition:resonance.dendro.em_30",
        dendro_em_20_definition_key="buff.definition:resonance.dendro.em_20",
        geo_res_shred_definition_key="buff.definition:resonance.geo.res_shred",
        shield_presence_port=FakeShieldPresencePort(shield_present),
        lunar_cage_presence_port=FakeLunarCagePresencePort(lunar_cage_present),
    )


def test_stage_enqueues_single_electro_particle_within_cooldown():
    queue = IntentQueue()
    stage = _stage(("resonance.electro",), queue)

    first = make_reaction_occurrence_event(10, "reaction.electro_charged", "occ:1")
    second = make_reaction_occurrence_event(10, "reaction.electro_charged", "occ:2")
    stage.update_frame(make_event_context(10, (first,)), 10)
    stage.update_frame(make_event_context(10, (second,)), 10)

    intents = queue.drain_sorted()
    assert len(intents) == 1
    assert intents[0].kind is IntentKind.IMPACT
    assert intents[0].source_ref == "resonance.electro"
    payload = cast(ImpactRequest, intents[0].payload)
    assert payload.kind is ImpactKind.ENERGY
    energy_payload = cast(dict, payload.params["energy"])
    assert energy_payload["operation"] == "spawn_pickup"
    assert energy_payload["element"] == "electro"

    third = make_reaction_occurrence_event(310, "reaction.electro_charged", "occ:3")
    stage.update_frame(make_event_context(310, (third,)), 310)
    assert queue.pending_count == 1


def test_stage_enqueues_dendro_em_30_for_all_slots():
    queue = IntentQueue()
    stage = _stage(("resonance.dendro",), queue)

    stage.update_frame(
        make_event_context(
            20, (make_reaction_occurrence_event(20, "reaction.bloom", "occ:bloom"),)
        ),
        20,
    )

    intents = queue.drain_sorted()
    assert len(intents) == 2
    assert {intent.kind for intent in intents} == {IntentKind.BUFF}
    requests = [cast(ApplyBuffRequest, intent.payload) for intent in intents]
    assert all(isinstance(request, ApplyBuffRequest) for request in requests)
    assert {request.definition_key for request in requests} == {
        "buff.definition:resonance.dendro.em_30"
    }
    assert {request.target_ref.entity_id for request in requests} == {
        "character:slot_1",
        "character:slot_2",
    }
    assert all(request.modifier_values[0].term_key == "elemental_mastery" for request in requests)


def test_stage_uses_em_20_for_aggravate():
    queue = IntentQueue()
    stage = _stage(("resonance.dendro",), queue)

    stage.update_frame(
        make_event_context(
            20, (make_reaction_occurrence_event(20, "reaction.aggravate", "occ:agg"),)
        ),
        20,
    )

    requests = [cast(ApplyBuffRequest, intent.payload) for intent in queue.drain_sorted()]
    assert all(
        request.definition_key == "buff.definition:resonance.dendro.em_20" for request in requests
    )


def test_stage_ignores_reactions_when_resonances_inactive():
    queue = IntentQueue()
    stage = _stage((), queue)

    stage.update_frame(
        make_event_context(
            30,
            (
                make_reaction_occurrence_event(30, "reaction.electro_charged", "occ:1"),
                make_reaction_occurrence_event(30, "reaction.bloom", "occ:2"),
            ),
        ),
        30,
    )

    assert queue.is_empty()


def test_stage_enqueues_intents_for_next_settlement_round():
    queue = IntentQueue()
    stage = _stage(("resonance.dendro",), queue)

    stage.update_frame(
        make_event_context(40, (make_reaction_occurrence_event(40, "reaction.bloom", "occ:1"),)),
        40,
    )

    intents = queue.drain_sorted()
    assert all(intent.frame == 40 for intent in intents)
    assert all(intent.phase is FramePhase.SETTLEMENT for intent in intents)
    assert all(intent.round == 1 for intent in intents)


def test_stage_enqueues_geo_res_shred_when_shielded():
    queue = IntentQueue()
    stage = _stage(("resonance.geo",), queue, shield_present=True)

    stage.update_frame(make_event_context(50, (make_damage_resolved_event(50, "dmg:1"),)), 50)

    intents = queue.drain_sorted()
    assert len(intents) == 1
    assert intents[0].source_ref == "resonance.geo"
    request = cast(ApplyBuffRequest, intents[0].payload)
    assert request.definition_key == "buff.definition:resonance.geo.res_shred"
    assert request.target_ref == AttributeSubjectRef.target("target:1")
    assert request.applier_ref == AttributeSubjectRef.character("character:slot_1")
    assert request.modifier_values[0].term_key == "resistance_geo"


def test_stage_enqueues_geo_res_shred_when_lunar_cage_present():
    queue = IntentQueue()
    stage = _stage(("resonance.geo",), queue, lunar_cage_present=True)

    stage.update_frame(make_event_context(50, (make_damage_resolved_event(50, "dmg:2"),)), 50)

    assert queue.pending_count == 1


def test_stage_skips_geo_res_shred_without_shield_or_cage():
    queue = IntentQueue()
    stage = _stage(("resonance.geo",), queue)

    stage.update_frame(make_event_context(50, (make_damage_resolved_event(50, "dmg:3"),)), 50)

    assert queue.is_empty()
