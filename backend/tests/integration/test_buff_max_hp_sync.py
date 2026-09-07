"""Buff 动态最大生命同步的纵向集成测试。"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import ContentUnitRegistry
from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffModifierValue,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.health import CharacterDamageApplication
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers.assembly import static_asset_input_payload
from tests.helpers.fixture_assets import write_fixture_asset_database

MAX_HP_HANDLER_KEY = "character.testing.max_hp_buff"
MAX_HP_DEFINITION_KEY = "buff.testing.max_hp_up"


def _max_hp_buff_content_unit(request) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version="dev-test",
        slot=request.slot,
        buff_definitions=(
            BuffDefinition(
                definition_key=MAX_HP_DEFINITION_KEY,
                mechanic_key="testing.max_hp_up",
                handler_key=request.handler_key,
                conflict_key=MAX_HP_DEFINITION_KEY,
                target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
                application_policy=BuffApplicationPolicy.REPLACE,
                value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
                max_stacks=1,
                attribute_modifiers=(
                    BuffAttributeModifierTemplate(
                        term_key="max_hp_flat",
                        target_key=STAT_HP_MAX,
                        stage=ModifierStage.FLAT_ADD,
                    ),
                ),
                tags=frozenset({"testing.max_hp"}),
            ),
        ),
        metadata={"purpose": "buff_max_hp_sync_vertical"},
    )


def test_intent_applied_max_hp_buff_scales_hp_until_expiry(tmp_path: Path):
    asset_db = tmp_path / "assets.db"
    write_fixture_asset_database(asset_db, character_handler_key=MAX_HP_HANDLER_KEY)
    unit_registry = ContentUnitRegistry()
    unit_registry.register_character_factory(MAX_HP_HANDLER_KEY, _max_hp_buff_content_unit)
    config = SimulationInput.from_mapping(
        static_asset_input_payload(
            meta_name="buff max hp sync",
            max_frames=8,
            input_trace=[],
        )
    )
    assembled = SimulationAssembler(
        SQLiteAssetRepository(asset_db),
        content_unit_registry=unit_registry,
    ).assemble(config)

    character_ref = AttributeSubjectRef.character(
        assembled.space_runtime.team_state.current_character.combat_entity_id
    )
    initial_max_hp = assembled.health_runtime.get_max_hp(character_ref, 0)
    assembled.health_runtime.apply_damage(
        CharacterDamageApplication(
            change_id="testing.damage:1",
            frame=0,
            target_ref=character_ref,
            amount=initial_max_hp * 0.4,
        )
    )
    hp_before_buff = assembled.health_runtime.get_current_hp(character_ref)
    assert hp_before_buff == initial_max_hp * 0.6

    lifecycle_events: list = []
    for event_type in (
        EventType.BUFF_APPLIED,
        EventType.BUFF_REMOVED,
        EventType.CHARACTER_MAX_HP_CHANGED,
    ):
        assembled.context.events.subscribe(event_type, lifecycle_events.append)

    assembled.intent_queue.enqueue(
        IntentEnvelope(
            intent_id="testing.buff:1",
            kind=IntentKind.BUFF,
            frame=1,
            phase=FramePhase.SETTLEMENT,
            payload=ApplyBuffRequest(
                request_id="testing.buff-req:1",
                frame=1,
                order=0,
                definition_key=MAX_HP_DEFINITION_KEY,
                target_ref=character_ref,
                source_context=RuntimeSourceRef(
                    RuntimeSourceKind.SYSTEM,
                    "testing.max_hp_up",
                ),
                duration_frames=3,
                stack_delta=1,
                modifier_values=(BuffModifierValue("max_hp_flat", 500.0),),
                applier_ref=None,
            ),
        )
    )

    result = assembled.simulator.run()

    # 世界在意图结算完成后即按空闲规则结束（Buff 不阻止空闲停止），
    # 生效同步发生在 frame 1 的结算阶段。
    assert result.end_frame == 1
    assert assembled.health_runtime.get_max_hp(character_ref, 1) == initial_max_hp + 500.0
    assert (
        assembled.health_runtime.get_current_hp(character_ref)
        == hp_before_buff * (initial_max_hp + 500.0) / initial_max_hp
    )

    # 手动推进帧到过期边界，验证失效同步。
    while assembled.context.current_frame < 4:
        frame = assembled.context.advance_frame()
        assembled.runtime_world.update_frame(assembled.context, frame)

    assert assembled.health_runtime.get_max_hp(character_ref, 4) == initial_max_hp
    assert assembled.health_runtime.get_current_hp(character_ref) == hp_before_buff
    assert not assembled.buff_store.active(4)

    events = [(event.frame, event.event_type) for event in lifecycle_events]
    assert events == [
        (1, EventType.BUFF_APPLIED),
        (1, EventType.CHARACTER_MAX_HP_CHANGED),
        (4, EventType.BUFF_REMOVED),
        (4, EventType.CHARACTER_MAX_HP_CHANGED),
    ]

    max_hp_events = [
        event
        for event in lifecycle_events
        if event.event_type is EventType.CHARACTER_MAX_HP_CHANGED
    ]
    assert max_hp_events[0].payload.result.old_max_hp == initial_max_hp
    assert max_hp_events[0].payload.result.new_max_hp == initial_max_hp + 500.0
    assert max_hp_events[0].payload.result.hp_before == max_hp_events[
        0
    ].payload.result.hp_after * initial_max_hp / (initial_max_hp + 500.0)
