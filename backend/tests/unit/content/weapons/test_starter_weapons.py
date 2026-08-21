"""1 星基础武器内容单元测试。

测试只验证代码层行为：注册表注册、内容单元身份与绑定校验；
不验证资产数据库中的 handler 绑定和数值数据。
"""

from __future__ import annotations

import pytest

from genshin_sim.content import (
    APPRENTICE_NOTES_ASSET_KEY,
    APPRENTICE_NOTES_HANDLER_KEY,
    BEGINNER_PROTECTOR_ASSET_KEY,
    BEGINNER_PROTECTOR_HANDLER_KEY,
    DULL_BLADE_ASSET_KEY,
    DULL_BLADE_HANDLER_KEY,
    HUNTER_BOW_ASSET_KEY,
    HUNTER_BOW_HANDLER_KEY,
    WASTER_GREATSWORD_ASSET_KEY,
    WASTER_GREATSWORD_HANDLER_KEY,
    create_default_content_unit_registry,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import WeaponContentUnitRequest

_STARTER_WEAPON_BINDINGS = (
    (DULL_BLADE_HANDLER_KEY, DULL_BLADE_ASSET_KEY),
    (WASTER_GREATSWORD_HANDLER_KEY, WASTER_GREATSWORD_ASSET_KEY),
    (BEGINNER_PROTECTOR_HANDLER_KEY, BEGINNER_PROTECTOR_ASSET_KEY),
    (APPRENTICE_NOTES_HANDLER_KEY, APPRENTICE_NOTES_ASSET_KEY),
    (HUNTER_BOW_HANDLER_KEY, HUNTER_BOW_ASSET_KEY),
)


def test_default_registry_creates_stat_only_starter_weapon_units():
    registry = create_default_content_unit_registry()

    for handler_key, asset_key in _STARTER_WEAPON_BINDINGS:
        assert registry.has_weapon_handler(handler_key)
        unit = registry.create_weapon(
            WeaponContentUnitRequest(
                handler_key=handler_key,
                weapon_key=asset_key,
                slot=1,
            )
        )
        assert unit is not None
        assert unit.owner_type is ContentUnitOwnerType.WEAPON
        assert unit.owner_key == asset_key
        assert unit.handler_key == handler_key
        assert unit.version
        assert unit.actions == ()
        assert unit.modifiers == ()
        assert unit.buff_definitions == ()
        assert unit.infusion_definitions == ()
        assert unit.impact_factories == {}


def test_starter_weapon_factories_reject_mismatched_asset_key():
    registry = create_default_content_unit_registry()

    for handler_key, _asset_key in _STARTER_WEAPON_BINDINGS:
        with pytest.raises(ContentUnitValidationError, match="只绑定"):
            registry.create_weapon(
                WeaponContentUnitRequest(
                    handler_key=handler_key,
                    weapon_key="weapon:99999",
                    slot=1,
                )
            )
