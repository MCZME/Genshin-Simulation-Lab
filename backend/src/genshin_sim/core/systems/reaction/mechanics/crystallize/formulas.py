"""普通结晶的直接等级表与捕获吸收量公式。"""

from __future__ import annotations

import math

from genshin_sim.core.systems.reaction.models import (
    CapturedCrystallizeShieldBasis,
    CrystallizeSourceObservation,
)


class CrystallizeLevelOutOfRangeError(ValueError):
    """结晶来源等级不在已冻结的 1-100 直接表中。"""


# 维护者提供的三位小数直接表；不得用曲线或插值重建。
_LEVEL_COEFFICIENTS = (
    91.179,
    98.707,
    106.236,
    113.764,
    121.293,
    128.821,
    136.350,
    143.878,
    151.407,
    158.936,
    169.991,
    181.076,
    192.190,
    204.048,
    215.938,
    227.862,
    247.685,
    267.542,
    287.431,
    303.826,
    320.225,
    336.627,
    352.319,
    368.010,
    383.702,
    394.432,
    405.181,
    415.949,
    426.737,
    437.544,
    450.600,
    463.700,
    476.845,
    491.127,
    502.554,
    514.012,
    531.409,
    549.979,
    568.584,
    584.996,
    605.670,
    626.386,
    646.052,
    665.755,
    685.496,
    700.839,
    723.333,
    745.865,
    768.435,
    786.791,
    809.538,
    832.329,
    855.162,
    878.039,
    899.484,
    919.361,
    946.039,
    974.764,
    1003.578,
    1030.077,
    1056.635,
    1085.246,
    1113.924,
    1149.258,
    1178.064,
    1200.223,
    1227.660,
    1257.243,
    1284.917,
    1314.752,
    1342.665,
    1372.752,
    1396.321,
    1427.312,
    1458.374,
    1482.335,
    1511.910,
    1541.549,
    1569.153,
    1596.814,
    1622.419,
    1648.073,
    1666.376,
    1684.678,
    1702.980,
    1726.104,
    1754.671,
    1785.866,
    1817.137,
    1851.060,
    1885.067,
    1921.749,
    1958.523,
    2006.194,
    2041.568,
    2054.472,
    2065.975,
    2174.722,
    2186.768,
    2198.813,
)


def crystallize_level_coefficient(source_level: int) -> float:
    """查找来源等级对应的结晶系数，越界不进行任何拟合。"""

    if isinstance(source_level, bool) or not isinstance(source_level, int):
        raise CrystallizeLevelOutOfRangeError("结晶来源等级必须是 1 到 100 的整数")
    if not 1 <= source_level <= len(_LEVEL_COEFFICIENTS):
        raise CrystallizeLevelOutOfRangeError("结晶来源等级必须在 1 到 100 之间")
    return _LEVEL_COEFFICIENTS[source_level - 1]


def elemental_mastery_bonus(elemental_mastery: float) -> float:
    """结晶冻结的元素精通增益；不读取任何 Damage 或 Shield 领域状态。"""

    if isinstance(elemental_mastery, bool) or not isinstance(elemental_mastery, int | float):
        raise ValueError("elemental_mastery 必须是数字")
    mastery = float(elemental_mastery)
    if not math.isfinite(mastery) or mastery < 0:
        raise ValueError("elemental_mastery 必须是有限非负数")
    return (40 / 9) * mastery / (1400 + mastery)


def capture_crystallize_shield_basis(
    observation: CrystallizeSourceObservation,
    *,
    captured_frame: int,
) -> CapturedCrystallizeShieldBasis:
    """在 occurrence 成立时将来源数值捕获为晶片的不可变基础。"""

    if not isinstance(observation, CrystallizeSourceObservation):
        raise ValueError("observation 必须是 CrystallizeSourceObservation")
    coefficient = crystallize_level_coefficient(observation.source_level)
    bonus = elemental_mastery_bonus(observation.elemental_mastery)
    return CapturedCrystallizeShieldBasis(
        observation.source_ref,
        captured_frame,
        observation.source_level,
        observation.elemental_mastery,
        coefficient,
        bonus,
        coefficient * (1 + bonus),
    )
