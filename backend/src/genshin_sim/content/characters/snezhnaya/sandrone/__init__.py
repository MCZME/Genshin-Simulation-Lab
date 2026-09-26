"""桑多涅内容包公共导出（窄导出）。

包根只暴露稳定入口：角色 handler key、资产身份键与内容单元工厂。
内部实现符号按需从 ``data`` / ``actions`` / ``impacts`` / ``content``
子模块导入。
"""

from genshin_sim.content.characters.snezhnaya.sandrone.content import (
    create_sandrone_content_unit,
)
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ASSET_KEY,
    SANDRONE_CHARACTER_HANDLER_KEY,
)

__all__ = [
    "SANDRONE_ASSET_KEY",
    "SANDRONE_CHARACTER_HANDLER_KEY",
    "create_sandrone_content_unit",
]
