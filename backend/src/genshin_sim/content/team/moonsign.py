"""月兆（挪德卡徕地区效果）内容定义：非月兆角色月曜增伤参数。"""

from __future__ import annotations

from genshin_sim.core.elements import Element
from genshin_sim.core.systems.moonsign import MoonsignScaling

MOONSIGN_BONUS_CAP = 0.36
MOONSIGN_BONUS_DURATION_FRAMES = 1200

MOONSIGN_SCALING_BY_ELEMENT: dict[Element, MoonsignScaling] = {
    Element.PYRO: MoonsignScaling(divisor=100.0, ratio=0.009),
    Element.ELECTRO: MoonsignScaling(divisor=100.0, ratio=0.009),
    Element.CRYO: MoonsignScaling(divisor=100.0, ratio=0.009),
    Element.HYDRO: MoonsignScaling(divisor=1000.0, ratio=0.006),
    Element.GEO: MoonsignScaling(divisor=100.0, ratio=0.01),
    Element.ANEMO: MoonsignScaling(divisor=100.0, ratio=0.0225),
    Element.DENDRO: MoonsignScaling(divisor=100.0, ratio=0.0225),
}
