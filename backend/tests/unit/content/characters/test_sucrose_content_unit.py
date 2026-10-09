"""砂糖内容单元装配单元的接线校验。

不做仿真的部分在此锁定：内容单元身份、动作集合形状、下落攻击的通用接管、
影响工厂覆盖面与宿主状态 schema。倍率数值取合成值，只验证接线。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.sucrose.actions import (
    SucroseActionInterpreter,
)
from genshin_sim.content.characters.mondstadt.sucrose.content import (
    create_sucrose_content_unit,
)
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ACTION_TABLE,
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_CHARGED_ATTACK_ACTION_KEY,
    SUCROSE_CONTENT_VERSION,
    SUCROSE_HIT_IMPACT_KEYS,
    SUCROSE_JUMP_ACTION_KEY,
    SUCROSE_NORMAL_ATTACK_ACTION_KEYS,
    SUCROSE_PLUNGE_ACTION_KEY,
    SUCROSE_PLUNGE_COLLISION_IMPACT_KEY,
    SUCROSE_PLUNGE_LANDING_IMPACT_KEY,
)
from genshin_sim.content.generic.chain_state import (
    CHAIN_STATE_LAST_ACTION_KEY,
    CHAIN_STATE_LAST_START_FRAME,
)
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.core.actions import FallPlungeAction
from tests.helpers import sucrose as sucrose_helpers


def _content_unit():
    return create_sucrose_content_unit(
        CharacterContentUnitRequest(
            handler_key=SUCROSE_CHARACTER_HANDLER_KEY,
            character_key=sucrose_helpers.SUCROSE_CHARACTER_KEY,
            slot=1,
            talent_levels={"normal_attack": 1},
            talent_scalings=sucrose_helpers.minimal_sucrose_scaling_entries(),
        )
    )


def test_content_unit_identity_and_version():
    unit = _content_unit()
    assert unit.handler_key == SUCROSE_CHARACTER_HANDLER_KEY
    assert unit.owner_key == sucrose_helpers.SUCROSE_CHARACTER_KEY
    assert unit.version == SUCROSE_CONTENT_VERSION
    assert unit.slot == 1


def test_content_unit_declares_state_schema_and_interpreter():
    unit = _content_unit()
    assert isinstance(unit.action_interpreter, SucroseActionInterpreter)
    assert unit.state_schema is not None
    assert unit.state_schema.owner_ref == "character:slot_1"
    field_names = tuple(field.name for field in unit.state_schema.fields)
    assert CHAIN_STATE_LAST_ACTION_KEY in field_names
    assert CHAIN_STATE_LAST_START_FRAME in field_names


def test_content_unit_actions_cover_action_table():
    unit = _content_unit()
    action_keys = {action.action_key for action in unit.actions}
    expected = set(SUCROSE_ACTION_TABLE)
    assert action_keys == expected
    for action_key in SUCROSE_NORMAL_ATTACK_ACTION_KEYS:
        assert action_key in action_keys
    assert SUCROSE_CHARGED_ATTACK_ACTION_KEY in action_keys
    assert SUCROSE_JUMP_ACTION_KEY in action_keys


def test_plunge_action_is_handed_over_to_generic_plunge():
    unit = _content_unit()
    plunges = [action for action in unit.actions if action.action_key == SUCROSE_PLUNGE_ACTION_KEY]
    assert len(plunges) == 1
    plunge = plunges[0]
    assert isinstance(plunge, FallPlungeAction)
    assert plunge.collision_impact_key == SUCROSE_PLUNGE_COLLISION_IMPACT_KEY
    assert plunge.landing_impact_key == SUCROSE_PLUNGE_LANDING_IMPACT_KEY


def test_impact_factories_cover_all_sucrose_hit_keys():
    unit = _content_unit()
    assert set(unit.impact_factories) == set(SUCROSE_HIT_IMPACT_KEYS)


def test_content_unit_declares_no_cooldown_or_icd_slices_in_s1():
    """S1 不含冷却 / ICD 切片；这两类切片随 S2 / S3 接入。"""

    unit = _content_unit()
    assert unit.cooldown_definitions == ()
    assert unit.aura_icd_definitions == ()
    assert unit.created_object_types == {}
    assert unit.event_hooks == ()
