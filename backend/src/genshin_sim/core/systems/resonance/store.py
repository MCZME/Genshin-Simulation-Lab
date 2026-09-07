"""元素共鸣领域状态的唯一真值来源。"""

from __future__ import annotations

from genshin_sim.core.systems.resonance.errors import ResonanceValidationError
from genshin_sim.core.systems.resonance.models import (
    ResonanceActivation,
    TeamElementComposition,
)

RESONANCE_ELECTRO_PARTICLE_COOLDOWN_FRAMES = 300


class ResonanceStore:
    """保存激活集合与构成快照；激活集合在组装期确定，运行期只读。"""

    def __init__(
        self,
        activation: ResonanceActivation,
        composition: TeamElementComposition | None = None,
    ) -> None:
        if not isinstance(activation, ResonanceActivation):
            raise ResonanceValidationError("共鸣激活集合必须是 ResonanceActivation")
        if composition is not None and not isinstance(composition, TeamElementComposition):
            raise ResonanceValidationError("队伍构成必须是 TeamElementComposition")
        self._activation = activation
        self._composition = composition
        self._version = 0
        self._last_electro_particle_frame: int | None = None

    @property
    def activation(self) -> ResonanceActivation:
        return self._activation

    @property
    def active_keys(self) -> tuple[str, ...]:
        return self._activation.active_keys

    @property
    def composition(self) -> TeamElementComposition | None:
        return self._composition

    @property
    def version(self) -> int:
        return self._version

    @property
    def last_electro_particle_frame(self) -> int | None:
        return self._last_electro_particle_frame

    def try_claim_electro_particle(self, frame: int) -> bool:
        """尝试认领一次双雷微粒掉落；5 秒冷却内拒绝。"""

        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ResonanceValidationError("双雷微粒认领帧必须是非负整数")
        if (
            self._last_electro_particle_frame is not None
            and frame - self._last_electro_particle_frame
            < RESONANCE_ELECTRO_PARTICLE_COOLDOWN_FRAMES
        ):
            return False
        self._last_electro_particle_frame = frame
        self._version += 1
        return True
