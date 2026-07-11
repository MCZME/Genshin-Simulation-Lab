from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from genshin_sim.content.characters.testing.runtime_probe.constants import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.core.impacts import ImpactRequest


class RuntimeProbeImpactFactory:
    """记录 impact 分发已到达 content 的测试工厂。"""

    def create_impact_requests(self, request: ImpactRequest) -> Sequence[ImpactRequest]:
        params = dict(request.params)
        params["runtime_probe"] = {
            "handler_key": RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
            "source_impact_key": request.impact_key,
        }
        return (replace(request, params=params),)
