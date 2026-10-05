"""星烁辉映（Radiance）证据的反应域类型与内容侧窄只读端口。

辉映·星超导 / 辉映·星扩散 Buff 携带的直伤星烁基础系数以 Buff 载荷词条
（不进入属性系统）承载；本模块只定义证据的领域形态与读取协议，适配器
由元素反应协调层实现（见 ``core/coordination/elemental_reaction/``），
装配期注册为仿真系统供角色内容读取。
"""

from __future__ import annotations

from enum import Enum, auto
from typing import NamedTuple, Protocol, runtime_checkable


class RadianceVariant(Enum):
    """辉映变体：星超导 / 星扩散。"""

    CONDUCT = auto()
    SWIRL = auto()


class RadianceEvidence(NamedTuple):
    """一次辉映证据读取的结果：变体与直伤星烁基础系数。"""

    variant: RadianceVariant
    direct_base_multiplier: float


@runtime_checkable
class StellarRadianceEvidencePort(Protocol):
    """内容侧读取辉映证据的窄只读端口。

    只回答"证据是什么"，不暴露 Buff 实例、definition key 或词条细节；
    不允许任何写入。语义口径：

    - ``resolve``：星超导优先（同一角色同时满足两种辉映条件时只有辉映·星
      超导生效，读取优先级在此执行，Buff 层不互斥）；无任何辉映时返回
      ``None``；
    - ``variant_multiplier``：按变体直读对应辉映的直伤星烁基础系数；该
      变体辉映缺席时返回 ``0.0``（不是回落 1.0，回落口径由调用方承担）。
    """

    def resolve(self, *, owner_ref: str, frame: int) -> RadianceEvidence | None: ...

    def variant_multiplier(
        self, *, owner_ref: str, variant: RadianceVariant, frame: int
    ) -> float: ...
