from __future__ import annotations

from typing import cast

from genshin_sim.core.actions import ActionManager
from genshin_sim.core.elements import AuraAmount, AuraKind, Element, ElementalSubjectRef
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.events import EventEngine, EventType
from genshin_sim.core.impacts import (
    ElementalApplicationSpec,
    ImpactDispatcher,
    ImpactKind,
    ImpactRequest,
    ImpactRuntime,
)
from genshin_sim.core.impacts.runtime import ImpactRequestDispatcher
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import (
    CreatedObjectRuntime,
    CreatedObjectRuntimeState,
    CreatedObjectSpec,
    CreatedObjectTickSpec,
    ImpactAreaSpec,
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.aura import (
    AuraRuntime,
    AuraStrength,
    CharacterAuraImpactRequestHandler,
)
from genshin_sim.core.systems.aura_icd import (
    AuraIcdRuntime,
    IcdDefinition,
    IcdDefinitionRegistry,
    no_cooldown_definition,
    standard_icd_definition,
)


class _TeamStub:
    def __init__(self) -> None:
        self.current_character = CharacterRuntimeState(
            slot=1,
            character_key="character:1",
            level=90,
        )


class _SpaceStub:
    def __init__(self) -> None:
        self.team_state = _TeamStub()


class _Context:
    def __init__(self) -> None:
        self.space_runtime = _SpaceStub()


def _aura_request(
    *,
    request_id: str,
    target_refs: tuple[str, ...],
    frame: int = 3,
    icd_sequence_key: str | None = "icd.standard",
) -> ImpactRequest:
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.APPLY_AURA,
        impact_key="barbara.elemental_skill.self_wet",
        owner_slot=1,
        request_id=request_id,
        target_refs=target_refs,
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref="barbara.elemental_skill.self_wet",
            element=Element.HYDRO,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
            icd_tag_key="元素战技" if icd_sequence_key is not None else None,
            icd_sequence_key=icd_sequence_key,
        ),
    )


def _handler_pair():
    events = EventEngine()
    aura_runtime = AuraRuntime()
    icd_runtime = AuraIcdRuntime(
        IcdDefinitionRegistry(
            (
                standard_icd_definition(),
                no_cooldown_definition(),
                IcdDefinition("icd.barbara.ring", 90, (AuraAmount.one(),)),
            )
        )
    )
    return (
        CharacterAuraImpactRequestHandler(aura_runtime, icd_runtime, events),
        aura_runtime,
        icd_runtime,
        events,
    )


def test_character_aura_handler_applies_hydro_to_character_subject():
    handler, aura_runtime, _, events = _handler_pair()

    record = handler.handle_impact_request(
        _Context(),
        _aura_request(request_id="impact:self_wet", target_refs=("player:active",)),
    )

    subject = ElementalSubjectRef.character("character:slot_1")
    assert record.subject_refs == (subject,)
    assert aura_runtime.view(subject).component_for(AuraKind.HYDRO) is not None
    assert [event.event_type for event in events.frame_events] == [
        EventType.AURA_ICD_RESOLVED,
        EventType.AURA_APPLIED,
    ]


def test_character_aura_handler_respects_icd_window():
    handler, aura_runtime, _, _ = _handler_pair()
    context = _Context()

    first = handler.handle_impact_request(
        context,
        _aura_request(request_id="impact:self_wet:1", target_refs=("player:active",)),
    )
    second = handler.handle_impact_request(
        context,
        _aura_request(
            request_id="impact:self_wet:2",
            target_refs=("player:active",),
            frame=20,
        ),
    )

    assert len(first.aura_request_ids) == 1
    assert second.aura_request_ids == ()
    subject = ElementalSubjectRef.character("character:slot_1")
    assert aura_runtime.view(subject).component_for(AuraKind.HYDRO) is not None


class _RecordingElementalSettlement:
    def __init__(self) -> None:
        self.aura_requests: list[ImpactRequest] = []

    def settle_aura_impact(self, context, request: ImpactRequest) -> None:
        del context
        self.aura_requests.append(request)

    def settle_damage_impact(self, context, request: ImpactRequest) -> None:
        raise AssertionError("本测试不应处理伤害请求")


def test_dispatcher_splits_character_and_target_aura_refs():
    handler, aura_runtime, _, _ = _handler_pair()
    settlement = _RecordingElementalSettlement()
    dispatcher = ImpactRequestDispatcher(
        character_aura_handler=handler,
        elemental_settlement_coordinator=settlement,
    )

    dispatcher.dispatch_requests(
        _Context(),
        (
            _aura_request(
                request_id="impact:mixed",
                target_refs=("player:active", "target_1"),
            ),
        ),
    )

    subject = ElementalSubjectRef.character("character:slot_1")
    assert aura_runtime.view(subject).component_for(AuraKind.HYDRO) is not None
    assert settlement.aura_requests[0].target_refs == ("target_1",)


class _AuraAreaTickBehavior:
    def create_tick_requests(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
    ) -> tuple[ImpactRequest, ...]:
        del state
        return (
            ImpactRequest(
                frame=frame,
                kind=ImpactKind.APPLY_AURA,
                impact_key="barbara.ring.wet",
                owner_slot=1,
                request_id=f"ring:wet:{frame}",
                anchor_entity_id="player:active",
                elemental_application_spec=ElementalApplicationSpec(
                    impact_ref="barbara.ring.wet",
                    element=Element.HYDRO,
                    elemental_strength=AuraStrength.WEAK,
                    elemental_amount=AuraAmount.one(),
                    icd_tag_key="元素战技",
                    icd_sequence_key="icd.barbara.ring",
                    area=ImpactAreaSpec(
                        shape="圆柱",
                        radius=2.0,
                        local_offset_xz=Vector3(0.0, -0.25, 0.0),
                    ),
                ),
            ),
        )


class _CapturingRequestDispatcher:
    def __init__(self) -> None:
        self.requests: list[ImpactRequest] = []

    def dispatch_requests(self, context, requests: tuple[ImpactRequest, ...]) -> None:
        del context
        self.requests.extend(requests)


class _NoActionManager:
    def due_impact_points(self, frame: int) -> tuple:
        del frame
        return ()


def test_impact_runtime_expands_aura_area_for_created_object_tick():
    ctx = SimulationContext()
    space = Space(
        [
            SpatialEntity(
                "player:active",
                SpatialEntityKind.ACTIVE_CHARACTER,
                position=Vector3(0.0, 0.0, 0.0),
            ),
            SpatialEntity(
                "target:target_1",
                SpatialEntityKind.TARGET,
                position=Vector3(1.0, 0.0, 0.0),
            ),
            SpatialEntity(
                "target:target_2",
                SpatialEntityKind.TARGET,
                position=Vector3(9.0, 0.0, 0.0),
            ),
        ]
    )
    created_object_runtime = CreatedObjectRuntime({"barbara.ring.wet": _AuraAreaTickBehavior()})
    created_object_runtime.create_or_refresh(
        CreatedObjectSpec(
            object_key="barbara.ring",
            duration_frames=300,
            tick_schedules=(
                CreatedObjectTickSpec(
                    "barbara.ring.wet",
                    first_tick_frame_offset=1,
                    interval_frames=90,
                ),
            ),
            follow_entity_id="player:active",
        ),
        frame=1,
    )
    ctx.space_runtime = SpaceRuntime(
        space=space,
        team_state=TeamRuntimeState(
            [CharacterRuntimeState(slot=1, character_key="character:1", level=90)]
        ),
        targets=TargetRuntimeCollection(
            (
                TargetRuntimeState(
                    target_id="target_1",
                    level=90,
                    resistance={},
                ),
                TargetRuntimeState(
                    target_id="target_2",
                    level=90,
                    resistance={},
                ),
            )
        ),
        created_object_runtime=created_object_runtime,
    )
    capturing = _CapturingRequestDispatcher()
    impact_runtime = ImpactRuntime(
        cast(ActionManager, _NoActionManager()),
        ImpactDispatcher({}),
        cast(ImpactRequestDispatcher, capturing),
    )

    impact_runtime.update_frame(ctx, 2)

    assert len(capturing.requests) == 1
    assert set(capturing.requests[0].target_refs) == {
        "player:active",
        "target_1",
    }
