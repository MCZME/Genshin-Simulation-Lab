from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.content.characters.testing.runtime_probe.constants import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
)


@dataclass(frozen=True, slots=True)
class RuntimeProbeState:
    """用于验证内容状态注入的小型状态扩展。"""

    schema_version: int = 1
    probe_key: str = RUNTIME_PROBE_CHARACTER_HANDLER_KEY
