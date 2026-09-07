"""被怜爱的少女 4 件套：不同穿戴者的实例相互独立。"""

from __future__ import annotations

from genshin_sim.content import (
    MAIDEN_BELOVED_4P_TERM_KEY,
    MAIDEN_BELOVED_ASSET_KEY,
    MAIDEN_BELOVED_HANDLER_KEY,
    create_maiden_beloved_content_unit,
    maiden_beloved_4p_definition_key,
)
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffDefinitionRegistry,
    BuffModifierValue,
    BuffResolver,
    BuffRuntime,
    BuffStore,
)


def _four_piece_request(slot: int) -> ArtifactContentUnitRequest:
    return ArtifactContentUnitRequest(
        handler_key=MAIDEN_BELOVED_HANDLER_KEY,
        artifact_key=MAIDEN_BELOVED_ASSET_KEY,
        slot=slot,
        artifact_kind="artifact_set_bonus",
        piece_count=4,
        params={
            "components": (
                {"kind": "numeric", "format": "number", "values": [10.0]},
                {"kind": "numeric", "format": "percent", "values": [0.2]},
            )
        },
    )


def test_maiden_4p_buffs_from_different_wearers_coexist_on_same_target():
    first = create_maiden_beloved_content_unit(_four_piece_request(slot=1))
    second = create_maiden_beloved_content_unit(_four_piece_request(slot=2))
    registry = BuffDefinitionRegistry((first.buff_definitions[0], second.buff_definitions[0]))
    store = BuffStore()
    runtime = BuffRuntime(
        definition_registry=registry,
        resolver=BuffResolver(),
        buff_store=store,
        event_engine=SimulationContext().events,
    )
    target = AttributeSubjectRef.character("character:slot_1")

    def apply_wearer(slot: int, frame: int) -> None:
        runtime.apply(
            ApplyBuffRequest(
                request_id=f"test.maiden.slot{slot}.{frame}",
                frame=frame,
                order=0,
                definition_key=maiden_beloved_4p_definition_key(slot),
                target_ref=target,
                source_context=RuntimeSourceRef(
                    RuntimeSourceKind.CONTENT,
                    f"maiden:slot:{slot}",
                ),
                duration_frames=600,
                applier_ref=AttributeSubjectRef.character(f"character:slot_{slot}"),
                modifier_values=(
                    BuffModifierValue(term_key=MAIDEN_BELOVED_4P_TERM_KEY, value=0.2),
                ),
            )
        )

    apply_wearer(1, frame=1)
    apply_wearer(2, frame=2)
    apply_wearer(1, frame=3)

    active = [record for record in store.records if record.is_active_at(10)]
    assert len(active) == 2
    assert {record.definition.definition_key for record in active} == {
        maiden_beloved_4p_definition_key(1),
        maiden_beloved_4p_definition_key(2),
    }
    wearer_1_active = [
        record
        for record in active
        if record.definition.definition_key == maiden_beloved_4p_definition_key(1)
    ]
    assert len(wearer_1_active) == 1
    assert wearer_1_active[0].created_frame == 3
