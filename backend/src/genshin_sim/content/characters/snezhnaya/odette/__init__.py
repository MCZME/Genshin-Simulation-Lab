"""奥黛塔内容包公共导出（窄导出）。

包根只暴露稳定入口：角色 handler key、内容单元工厂与效果行 handler 键。
内部实现符号按需从 ``data`` / ``actions`` / ``impacts`` / ``content`` 子模块
导入；效果行工厂随对应切片落地后加入导出。
"""

from genshin_sim.content.characters.snezhnaya.odette.content import (
    create_odette_content_unit,
)
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_CONSTELLATION_C1_HANDLER_KEY,
    ODETTE_CONSTELLATION_C2_HANDLER_KEY,
    ODETTE_CONSTELLATION_C3_HANDLER_KEY,
    ODETTE_CONSTELLATION_C4_HANDLER_KEY,
    ODETTE_CONSTELLATION_C5_HANDLER_KEY,
    ODETTE_CONSTELLATION_C6_HANDLER_KEY,
    ODETTE_PASSIVE_P4_HANDLER_KEY,
    ODETTE_PASSIVE_P5_HANDLER_KEY,
    ODETTE_PASSIVE_P6_HANDLER_KEY,
    ODETTE_PASSIVE_P8_HANDLER_KEY,
)
from genshin_sim.content.characters.snezhnaya.odette.effects import (
    create_odette_constellation_c1,
    create_odette_constellation_c2,
    create_odette_constellation_c3,
    create_odette_constellation_c4,
    create_odette_constellation_c5,
    create_odette_constellation_c6,
    create_odette_passive_p4,
    create_odette_passive_p5,
    create_odette_passive_p6,
)

__all__ = [
    "ODETTE_CHARACTER_HANDLER_KEY",
    "ODETTE_CONSTELLATION_C1_HANDLER_KEY",
    "ODETTE_CONSTELLATION_C2_HANDLER_KEY",
    "ODETTE_CONSTELLATION_C3_HANDLER_KEY",
    "ODETTE_CONSTELLATION_C4_HANDLER_KEY",
    "ODETTE_CONSTELLATION_C5_HANDLER_KEY",
    "ODETTE_CONSTELLATION_C6_HANDLER_KEY",
    "ODETTE_PASSIVE_P4_HANDLER_KEY",
    "ODETTE_PASSIVE_P5_HANDLER_KEY",
    "ODETTE_PASSIVE_P6_HANDLER_KEY",
    "ODETTE_PASSIVE_P8_HANDLER_KEY",
    "create_odette_constellation_c1",
    "create_odette_constellation_c2",
    "create_odette_constellation_c3",
    "create_odette_constellation_c4",
    "create_odette_constellation_c5",
    "create_odette_constellation_c6",
    "create_odette_content_unit",
    "create_odette_passive_p4",
    "create_odette_passive_p5",
    "create_odette_passive_p6",
]
