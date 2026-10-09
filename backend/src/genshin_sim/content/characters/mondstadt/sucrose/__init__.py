"""砂糖内容包公共导出（窄导出）。

包根只暴露稳定入口：角色 handler key / 资产身份键与内容单元工厂。
内部实现符号按需从 ``data`` / ``actions`` / ``impacts`` 等子模块导入。
"""

from genshin_sim.content.characters.mondstadt.sucrose.content import (
    create_sucrose_content_unit,
)
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ASSET_KEY,
    SUCROSE_CHARACTER_HANDLER_KEY,
)

__all__ = [
    "SUCROSE_ASSET_KEY",
    "SUCROSE_CHARACTER_HANDLER_KEY",
    "create_sucrose_content_unit",
]
