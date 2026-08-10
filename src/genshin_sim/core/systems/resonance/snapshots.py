"""元素共鸣快照模型。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.systems.resonance.errors import ResonanceValidationError


@dataclass(frozen=True, slots=True)
class ResonanceSnapshot:
    """指定帧的活跃共鸣集合与构成概要。"""

    frame: int
    active_keys: tuple[str, ...]
    team_size: int
    established_frame: int = 0
    last_electro_particle_frame: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ResonanceValidationError("快照帧必须是非负整数")
        if (
            isinstance(self.team_size, bool)
            or not isinstance(self.team_size, int)
            or self.team_size < 0
        ):
            raise ResonanceValidationError("队伍人数必须是非负整数")
        keys = tuple(self.active_keys)
        if keys != tuple(sorted(set(keys))) or any(not key for key in keys):
            raise ResonanceValidationError("快照活跃共鸣 key 必须非空且稳定排序去重")
        object.__setattr__(self, "active_keys", keys)
        if self.last_electro_particle_frame is not None and (
            isinstance(self.last_electro_particle_frame, bool)
            or not isinstance(self.last_electro_particle_frame, int)
            or self.last_electro_particle_frame < 0
        ):
            raise ResonanceValidationError("双雷微粒最近帧必须是非负整数或 None")

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "active_keys": tuple(self.active_keys),
            "team_size": self.team_size,
            "established_frame": self.established_frame,
            "last_electro_particle_frame": self.last_electro_particle_frame,
        }
