from __future__ import annotations

from typing import cast

from genshin_sim.core.coordination.elemental_reaction.spatial import (
    ReactionSpatialPlanningAdapter,
    publish_space_entity_facts,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3


def _entity(entity_id: str) -> SpatialEntity:
    return SpatialEntity(
        entity_id=entity_id,
        kind=SpatialEntityKind.REACTION_OBJECT,
        position=Vector3(1, 0, 2),
    )


def test_publish_space_entity_facts_publishes_creation_and_removal_in_plan_order():
    space = Space()
    adapter = ReactionSpatialPlanningAdapter(space)
    space.add_entity(_entity("target:removed"))
    context = SimulationContext()

    planner = adapter.begin_batch(operation_id="space-facts", frame=0)
    planner.prepare_create_entity(_entity("reaction_object:created"))
    planner.prepare_remove("target:removed")
    plan = planner.seal()
    adapter.commit_prevalidated(plan)

    with adapter.event_publication_guard():
        publish_space_entity_facts(context, plan)

    events = [
        event
        for event in context.events.frame_events
        if event.event_type in {EventType.SPACE_ENTITY_CREATED, EventType.SPACE_ENTITY_REMOVED}
    ]
    assert [event.event_type for event in events] == [
        EventType.SPACE_ENTITY_CREATED,
        EventType.SPACE_ENTITY_REMOVED,
    ]
    created = events[0].payload.to_dict()
    assert created["frame"] == 0
    created_entity = cast(dict[str, object], created["entity"])
    assert created_entity["entity_id"] == "reaction_object:created"
    removed = events[1].payload.to_dict()
    assert removed["frame"] == 0
    removed_entity = cast(dict[str, object], removed["entity"])
    assert removed_entity["entity_id"] == "target:removed"


def test_publish_space_entity_facts_skips_publish_without_events_engine():
    space = Space()
    adapter = ReactionSpatialPlanningAdapter(space)
    planner = adapter.begin_batch(operation_id="space-facts-no-engine", frame=0)
    planner.prepare_create_entity(_entity("reaction_object:created"))
    plan = planner.seal()
    adapter.commit_prevalidated(plan)

    result = publish_space_entity_facts(object(), plan)

    assert result is None
