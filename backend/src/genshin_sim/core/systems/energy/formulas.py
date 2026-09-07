from __future__ import annotations

import math

from genshin_sim.core.systems.energy.errors import InvalidEnergyAttributeError
from genshin_sim.core.systems.energy.models import EnergyElement, EnergyPickupKind


def pickup_kind_multiplier(kind: EnergyPickupKind) -> float:
    return 1.0 if kind is EnergyPickupKind.PARTICLE else 3.0


def element_multiplier(pickup_element: EnergyElement, character_element: EnergyElement) -> float:
    if pickup_element is character_element:
        return 3.0
    if pickup_element is EnergyElement.CLEAR:
        return 2.0
    return 1.0


def field_multiplier(*, is_active: bool, team_size: int) -> float:
    if is_active:
        return 1.0
    if team_size < 1 or team_size > 4:
        raise ValueError("team_size 必须在 1 到 4 之间")
    return 1.0 - 0.1 * team_size


def recharge_multiplier(recharge_bonus: float | int) -> float:
    if isinstance(recharge_bonus, bool) or not isinstance(recharge_bonus, int | float):
        raise InvalidEnergyAttributeError("stat.energy_recharge 必须是有限数字")
    result = 1.0 + float(recharge_bonus)
    if not math.isfinite(result) or result <= 0:
        raise InvalidEnergyAttributeError("stat.energy_recharge 必须产生有限正倍率")
    return result
