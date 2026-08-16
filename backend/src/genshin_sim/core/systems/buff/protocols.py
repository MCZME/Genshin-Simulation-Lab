from __future__ import annotations

from typing import Protocol

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.buff.models import BuffRecord


class BuffReader(Protocol):
    def active(
        self,
        frame: int,
        target_ref: AttributeSubjectRef | None = None,
        definition_key: str | None = None,
        mechanic_key: str | None = None,
    ) -> tuple[BuffRecord, ...]: ...
