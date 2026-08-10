"""月兆装配测试：content metadata 识别、等级与运行时绑定。"""

from __future__ import annotations

from types import SimpleNamespace

from genshin_sim.application.assembly.attributes import build_attribute_runtime
from genshin_sim.application.assembly.moonsign import build_moonsign_bundle
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.events import (
    ActionStartedPayload,
    EventEngine,
    EventType,
    GameEvent,
)
from genshin_sim.core.systems.moonsign import MoonsignLevel
from tests.helpers.assembly import minimal_config
from tests.helpers.team_assets import (
    TeamAssetBundle,
    make_attribute_bundles,
    make_team_asset_bundles,
)


def _moonsign_unit(slot: int) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=f"character:moonsign_{slot}",
        handler_key=f"character.moonsign_{slot}",
        version="dev-test",
        slot=slot,
        metadata={"moonsign": True, "region_key": "nodkrai"},
    )


def _attribute_resolver(assets: tuple[TeamAssetBundle, ...]):
    return build_attribute_runtime(
        config=minimal_config(),
        assets=make_attribute_bundles(assets),
        content_units=(),
    ).resolver


def test_moonsign_bundle_detects_metadata_and_sets_ascendant_level():
    assets = make_team_asset_bundles(("pyro", "hydro", "electro", "geo"))
    bundle = build_moonsign_bundle(
        content_units=(_moonsign_unit(1), _moonsign_unit(2)),
        assets=assets,
        attribute_resolver=_attribute_resolver(assets),
        event_engine=EventEngine(),
    )

    assert bundle.store.level is MoonsignLevel.ASCENDANT
    assert bundle.store.moonsign_character_refs == (
        AttributeSubjectRef.character("character:slot_1"),
        AttributeSubjectRef.character("character:slot_2"),
    )
    assert bundle.runtime.level is MoonsignLevel.ASCENDANT
    assert bundle.runtime.has_nascent
    assert bundle.runtime.has_ascendant


def test_moonsign_bundle_applies_bonus_through_real_attribute_resolution():
    assets = make_team_asset_bundles(("pyro", "pyro", "pyro", "pyro"))
    bundle = build_moonsign_bundle(
        content_units=(_moonsign_unit(1), _moonsign_unit(2)),
        assets=assets,
        attribute_resolver=_attribute_resolver(assets),
        event_engine=EventEngine(),
    )
    event = GameEvent(
        EventType.ACTION_STARTED,
        10,
        ActionStartedPayload(
            instance_id=1,
            frame=10,
            action_key="character.test.skill",
            owner_slot=3,
            ability_key="elemental_skill",
        ),
    )
    context = SimpleNamespace(
        current_frame=10,
        events=SimpleNamespace(frame_events=(event,)),
    )

    bundle.runtime.update_frame(context, 10)

    assert bundle.runtime.lunar_reaction_bonus(10) == 0.09
    assert bundle.store.bonus is not None
    assert bundle.store.bonus.source_ref == AttributeSubjectRef.character("character:slot_3")


def test_moonsign_bundle_without_markers_stays_none():
    assets = make_team_asset_bundles(("pyro", "hydro", "electro", "geo"))
    bundle = build_moonsign_bundle(
        content_units=(),
        assets=assets,
        attribute_resolver=_attribute_resolver(assets),
        event_engine=EventEngine(),
    )
    assert bundle.store.level is MoonsignLevel.NONE
    assert not bundle.runtime.has_nascent
