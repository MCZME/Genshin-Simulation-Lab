"""仿真随机源。

一个仿真在装配期创建一个 ``RandomSource``：它持有一个随机种子，对外提供
一条按调用顺序取值的随机序列。请求方只取结果，不声明用途；取值顺序由代码
执行顺序决定，因此相同种子、相同代码与相同输入必然得到相同序列。

本模块不进快照、不发布事件、不参与帧推进。领域系统与 content 不得自建
``random.Random``，只能消费装配期注入的同一个随机源。
"""

from __future__ import annotations

import math
import random


class RandomSourceError(ValueError):
    """随机源参数或状态错误。"""


class RandomSource:
    """一次仿真唯一的随机序列。"""

    def __init__(self, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise RandomSourceError(f"随机种子必须是整数，实际为 {type(seed).__name__}")
        self._seed = seed
        self._rng = random.Random(seed)
        self._draw_count = 0

    @property
    def seed(self) -> int:
        """本次仿真的随机种子。"""

        return self._seed

    @property
    def draw_count(self) -> int:
        """已经提供的随机结果数量。"""

        return self._draw_count

    def next(self) -> float:
        """返回序列中的下一个 ``[0, 1)`` 随机结果。"""

        value = self._rng.random()
        self._draw_count += 1
        return value

    def roll(self, probability: float) -> bool:
        """按概率返回一次判定结果。

        概率为 ``0`` 或 ``1`` 时结果确定，不消耗序列；其余情况取下一个结果。
        """

        if isinstance(probability, bool) or not isinstance(probability, int | float):
            raise RandomSourceError(f"概率必须是数字，实际为 {type(probability).__name__}")
        chance = float(probability)
        if not math.isfinite(chance) or chance < 0.0 or chance > 1.0:
            raise RandomSourceError(f"概率必须是 0 到 1 之间的有限数字，实际为 {probability!r}")
        if chance <= 0.0:
            return False
        if chance >= 1.0:
            return True
        return self.next() < chance
