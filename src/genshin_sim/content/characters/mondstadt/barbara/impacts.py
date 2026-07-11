from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from genshin_sim.content.characters.mondstadt.barbara.constants import (
    BARBARA_CHARACTER_HANDLER_KEY,
)
from genshin_sim.core.impacts import ImpactRequest


class BarbaraActionImpactFactory:
    """记录芭芭拉动作影响点已由 content 展开。"""

    def create_impact_requests(self, request: ImpactRequest) -> Sequence[ImpactRequest]:
        params = dict(request.params)
        params["barbara"] = {
            "handler_key": BARBARA_CHARACTER_HANDLER_KEY,
            "source_impact_key": request.impact_key,
        }
        return (replace(request, params=params),)
