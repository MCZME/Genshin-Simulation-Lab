"""开发者测试内容包：仅在开发者模式下注册与可见。

本包内的内容实现与配套资产行数据由代码直接定义，不进入正式资产库；
`register_test_content_units` 是唯一注册入口，由
`content.bootstrap_content_units.create_default_content_unit_registry(developer_mode=True)`
按需调用。
"""

from genshin_sim.content.test.bootstrap_test_content_units import (
    register_test_content_units,
)
from genshin_sim.content.test.characters.runtime_probe import (
    RUNTIME_PROBE_ACTION_KEY,
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    RUNTIME_PROBE_IMPACT_KEY,
    create_runtime_probe_content_unit,
)

__all__ = [
    "RUNTIME_PROBE_ACTION_KEY",
    "RUNTIME_PROBE_CHARACTER_HANDLER_KEY",
    "RUNTIME_PROBE_IMPACT_KEY",
    "create_runtime_probe_content_unit",
    "register_test_content_units",
]
