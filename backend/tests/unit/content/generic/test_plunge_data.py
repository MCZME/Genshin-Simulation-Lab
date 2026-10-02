"""generic 通用下落攻击资料（按武器类型）的单元测试。

预期值来自通用攻击数据表。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.generic.plunge import (
    PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE,
    PlungeCollisionData,
    PlungeLandingData,
    PlungeWeaponAttackData,
)
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.space.geometry import Vector3


def test_mapping_covers_all_five_weapon_types():
    assert set(PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE) == {
        "sword",
        "claymore",
        "polearm",
        "catalyst",
        "bow",
    }


@pytest.mark.parametrize(
    ("weapon_type", "collision", "landing"),
    (
        pytest.param(
            "sword",
            PlungeCollisionData(
                aoe_shape="球",
                aoe_radius=1.0,
                aoe_offset=Vector3(0.0, 0.0, 1.0),
                elemental_amount=0,
                strike_type=StrikeType.SLASH,
                range_type="近战",
            ),
            PlungeLandingData(
                aoe_shape="圆柱",
                aoe_offset=Vector3(0.0, -0.5, 1.0),
                low_aoe_radius=3.0,
                high_aoe_radius=5.0,
                elemental_amount=1,
                strike_type=StrikeType.BLUNT,
                range_type="近战",
            ),
            id="sword",
        ),
        pytest.param(
            "claymore",
            PlungeCollisionData(
                aoe_shape="球",
                aoe_radius=1.0,
                aoe_offset=Vector3(0.0, 0.0, 1.0),
                elemental_amount=0,
                strike_type=StrikeType.SLASH,
                range_type="近战",
            ),
            PlungeLandingData(
                aoe_shape="圆柱",
                aoe_offset=Vector3(0.0, -0.5, 1.0),
                low_aoe_radius=3.0,
                high_aoe_radius=5.0,
                elemental_amount=1,
                strike_type=StrikeType.BLUNT,
                range_type="近战",
            ),
            id="claymore",
        ),
        pytest.param(
            "polearm",
            PlungeCollisionData(
                aoe_shape="球",
                aoe_radius=1.0,
                aoe_offset=Vector3(0.0, 0.0, 1.0),
                elemental_amount=0,
                strike_type=StrikeType.SLASH,
                range_type="近战",
            ),
            PlungeLandingData(
                aoe_shape="圆柱",
                aoe_offset=Vector3(0.0, -0.5, 1.0),
                low_aoe_radius=3.0,
                high_aoe_radius=5.0,
                elemental_amount=1,
                strike_type=StrikeType.BLUNT,
                range_type="近战",
            ),
            id="polearm",
        ),
        pytest.param(
            "catalyst",
            PlungeCollisionData(
                aoe_shape="球",
                aoe_radius=1.5,
                aoe_offset=Vector3(0.0, 0.0, 0.0),
                elemental_amount=0,
                strike_type=StrikeType.DEFAULT,
                range_type="默认",
            ),
            PlungeLandingData(
                aoe_shape="圆柱",
                aoe_offset=Vector3(0.0, -0.5, 0.0),
                low_aoe_radius=3.0,
                high_aoe_radius=3.5,
                elemental_amount=1,
                strike_type=StrikeType.DEFAULT,
                range_type="默认",
            ),
            id="catalyst",
        ),
        pytest.param(
            "bow",
            PlungeCollisionData(
                aoe_shape="球",
                aoe_radius=1.0,
                aoe_offset=Vector3(0.0, 0.0, 0.0),
                elemental_amount=0,
                strike_type=StrikeType.PIERCE,
                range_type="近战",
            ),
            PlungeLandingData(
                aoe_shape="圆柱",
                aoe_offset=Vector3(0.0, -0.5, 0.0),
                low_aoe_radius=3.0,
                high_aoe_radius=3.5,
                elemental_amount=1,
                strike_type=StrikeType.PIERCE,
                range_type="近战",
            ),
            id="bow",
        ),
    ),
)
def test_weapon_type_data_matches_source_table(
    weapon_type: str,
    collision: PlungeCollisionData,
    landing: PlungeLandingData,
):
    data = PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE[weapon_type]

    assert isinstance(data, PlungeWeaponAttackData)
    assert data.main_attack_tag == "下落攻击"
    assert data.collision == collision
    assert data.landing == landing
