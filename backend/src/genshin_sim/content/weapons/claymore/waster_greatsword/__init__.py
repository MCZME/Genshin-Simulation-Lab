"""训练大剑内容包（窄导出）。"""

from genshin_sim.content.weapons.claymore.waster_greatsword.content import (
    create_waster_greatsword_content_unit,
)
from genshin_sim.content.weapons.claymore.waster_greatsword.data import (
    WASTER_GREATSWORD_ASSET_KEY,
    WASTER_GREATSWORD_HANDLER_KEY,
)

__all__ = [
    "WASTER_GREATSWORD_ASSET_KEY",
    "WASTER_GREATSWORD_HANDLER_KEY",
    "create_waster_greatsword_content_unit",
]
