from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.energy.models import EnergyElement


@dataclass(frozen=True, slots=True)
class CharacterEnergySnapshot:
    character_ref: AttributeSubjectRef
    character_key: str
    element: EnergyElement
    current_energy: float
    capacity: float
    burst_ready: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "character_ref": {
                "kind": self.character_ref.kind.value,
                "entity_id": self.character_ref.entity_id,
            },
            "character_key": self.character_key,
            "element": self.element.value,
            "current_energy": self.current_energy,
            "capacity": self.capacity,
            "burst_ready": self.burst_ready,
        }


@dataclass(frozen=True, slots=True)
class EnergySnapshot:
    frame: int
    characters: tuple[CharacterEnergySnapshot, ...]
    pending_pickups: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "characters": tuple(item.to_dict() for item in self.characters),
            "pending_pickups": self.pending_pickups,
        }
