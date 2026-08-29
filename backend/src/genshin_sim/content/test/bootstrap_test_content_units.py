"""开发者测试内容单元注册入口。

只在开发者模式下被 ``create_default_content_unit_registry`` 调用；
测试 handler_key 统一使用 ``testing.*`` 命名空间，与正式内容隔离。
"""

from __future__ import annotations

from genshin_sim.content.registries import ContentUnitRegistry
from genshin_sim.content.test.characters.runtime_probe import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    create_runtime_probe_content_unit,
)


def register_test_content_units(registry: ContentUnitRegistry) -> None:
    """把开发者测试内容单元工厂注册进给定注册表。"""

    registry.register_character_factory(
        RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
        create_runtime_probe_content_unit,
    )
