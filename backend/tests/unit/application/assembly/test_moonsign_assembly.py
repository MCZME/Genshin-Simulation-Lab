"""月兆装配测试：content metadata 识别、等级与运行时绑定。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

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
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_LUNAR_REACTION
from genshin_sim.core.systems.moonsign import (
    MOONSIGN_LUNAR_BONUS_PROVIDER_KEY,
    MoonsignLevel,
)
from tests.helpers import damage
from tests.helpers.assembly import minimal_input
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
        config=minimal_input(),
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


def _action_started_event(owner_slot: int) -> GameEvent:
    """在给定帧触发一次指定角色的动作开始事件。"""

    return GameEvent(
        EventType.ACTION_STARTED,
        10,
        ActionStartedPayload(
            instance_id=1,
            frame=10,
            action_key="character.test.skill",
            owner_slot=owner_slot,
            ability_key="elemental_skill",
        ),
    )


def _lunar_bonus_terms(provider, frame: int):
    """在月曜公式查询上收集 provider 词条（会话对 provider 无副作用）。"""

    query = damage.provider_query_stub(frame=frame, formula_key=FORMULA_KEY_LUNAR_REACTION)
    return tuple(provider.contribute(query, damage.NullResolutionSession()))


def test_moonsign_bundle_registers_a_bound_lunar_bonus_provider():
    """装配产物带出已绑定端口的月曜增伤 provider，随动作生效、到期后一并归零。"""

    assets = make_team_asset_bundles(("pyro", "pyro", "pyro", "pyro"))
    bundle = build_moonsign_bundle(
        content_units=(_moonsign_unit(1), _moonsign_unit(2)),
        assets=assets,
        attribute_resolver=_attribute_resolver(assets),
        event_engine=EventEngine(),
    )
    (provider,) = bundle.damage_providers
    assert provider.provider_spec.provider_key == MOONSIGN_LUNAR_BONUS_PROVIDER_KEY
    # 装配期早于动作，端口尚未写入，provider 不贡献词条。
    assert _lunar_bonus_terms(provider, 10) == ()

    context = SimpleNamespace(
        current_frame=10,
        events=SimpleNamespace(frame_events=(_action_started_event(3),)),
    )
    bundle.runtime.update_frame(context, 10)

    # 动作开始后增伤经真实属性解析落到端口，provider 与端口给出同一个值。
    assert bundle.runtime.lunar_reaction_bonus(10) == 0.09
    assert bundle.store.bonus is not None
    assert bundle.store.bonus.source_ref == AttributeSubjectRef.character("character:slot_3")
    terms = _lunar_bonus_terms(provider, 10)
    assert len(terms) == 1
    assert terms[0].value == pytest.approx(bundle.runtime.lunar_reaction_bonus(10))
    # 增伤时长 1200 帧，到期后端口与 provider 同时回到 0。
    assert _lunar_bonus_terms(provider, 1209)
    assert _lunar_bonus_terms(provider, 1210) == ()


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
