"""砂糖内容包公共导出（窄导出）。

包根只暴露稳定入口：角色 handler key / 资产身份键、内容单元工厂，以及效果
payload 的 handler key 与工厂（由 ``bootstrap_content_units`` 注册）。
内部实现符号按需从 ``data`` / ``actions`` / ``impacts`` 等子模块导入。
"""

from genshin_sim.content.characters.mondstadt.sucrose.content import (
    create_sucrose_content_unit,
)
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ASSET_KEY,
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C1_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C2_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C3_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C4_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C5_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
    SUCROSE_PASSIVE_A1_HANDLER_KEY,
    SUCROSE_PASSIVE_A4_HANDLER_KEY,
    SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
)
from genshin_sim.content.characters.mondstadt.sucrose.effects import (
    create_sucrose_constellation_c1,
    create_sucrose_constellation_c2,
    create_sucrose_constellation_c3,
    create_sucrose_constellation_c4,
    create_sucrose_constellation_c5,
    create_sucrose_constellation_c6,
    create_sucrose_passive_a1,
    create_sucrose_passive_a4,
    create_sucrose_passive_witches_eve,
)

__all__ = [
    "SUCROSE_ASSET_KEY",
    "SUCROSE_CHARACTER_HANDLER_KEY",
    "SUCROSE_CONSTELLATION_C1_HANDLER_KEY",
    "SUCROSE_CONSTELLATION_C2_HANDLER_KEY",
    "SUCROSE_CONSTELLATION_C3_HANDLER_KEY",
    "SUCROSE_CONSTELLATION_C4_HANDLER_KEY",
    "SUCROSE_CONSTELLATION_C5_HANDLER_KEY",
    "SUCROSE_CONSTELLATION_C6_HANDLER_KEY",
    "SUCROSE_PASSIVE_A1_HANDLER_KEY",
    "SUCROSE_PASSIVE_A4_HANDLER_KEY",
    "SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY",
    "create_sucrose_constellation_c1",
    "create_sucrose_constellation_c2",
    "create_sucrose_constellation_c3",
    "create_sucrose_constellation_c4",
    "create_sucrose_constellation_c5",
    "create_sucrose_constellation_c6",
    "create_sucrose_content_unit",
    "create_sucrose_passive_a1",
    "create_sucrose_passive_a4",
    "create_sucrose_passive_witches_eve",
]
