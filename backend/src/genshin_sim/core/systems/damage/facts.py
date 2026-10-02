"""伤害事实的取值协议、会话容器声明和注册索引。

伤害事实是 provider 判定输入，与"伤害定义（编译期冻结）"和"属性通道（修饰
属性值）"并列，承载两者都表达不了的运行时状态。取值分两个作用域：

- **请求级事实**：发射方构造 ``ImpactRequest`` 时绑定，随请求走到结算，
  承载"发射时刻就确定且沿途不变"的身份与快照（如弹序、施放帧功率）。
  存放在请求上，不经过本模块的容器。
- **会话级事实**：内容侧定义并维护的模拟状态投影（下称事实容器）。容器
  自身不保存真值——它是转发到底层状态 store 的无状态视图，伤害系统只读。
  它跨帧存活、由内容侧自身逻辑推进，存在的理由是为伤害修饰提供判定依据。

边界：

- 伤害系统绝不写入事实，provider 只能读自己声明过的 key；
- 容器不得持有状态、不得缓存、不得有推进逻辑，一律转发底层 store；
- 清零与快照归底层状态所有者的既有链路，容器不承担生命周期职责；
- 凡是能表达为"修饰某个属性值"的状态走属性系统，不进事实。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.damage.errors import (
    ConflictingDamageFactError,
    DamageValidationError,
)

type DamageFactValue = float | int | bool | str
"""事实容器允许暴露的取值：有限标量与文本，保证可比较、可序列化。"""


def validate_damage_fact_value(value: object, key: str) -> DamageFactValue:
    """校验容器读出的取值属于受支持的事实类型。"""

    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DamageValidationError(f"伤害事实 {key} 的取值必须是有限数")
        return value
    if isinstance(value, str):
        return value
    raise DamageValidationError(f"伤害事实 {key} 的取值类型不受支持：{type(value).__name__}")


@dataclass(frozen=True, slots=True)
class DamageFactSpec:
    """一个事实容器对外暴露的身份与 key 空间声明。

    容器必须把全部 key 声明在 ``provider_key`` 命名空间下，注册索引据此在
    装配期一次性检出重复注册，不依赖运行期才暴露冲突。
    """

    provider_key: str
    facts: frozenset[str]
    owner_ref: AttributeSubjectRef | None = None
    display_name: str | None = None

    def __post_init__(self) -> None:
        """校验身份、key 命名空间与可选展示名。"""

        if not isinstance(self.provider_key, str) or not self.provider_key.strip():
            raise DamageValidationError("伤害事实 provider_key 必须是非空字符串")
        facts = frozenset(self.facts)
        if not facts:
            raise DamageValidationError("伤害事实 facts 不能为空")
        prefix = f"{self.provider_key}."
        for key in facts:
            if not isinstance(key, str) or not key.strip():
                raise DamageValidationError("伤害事实 key 必须是非空字符串")
            if not key.startswith(prefix):
                raise DamageValidationError(
                    f"伤害事实 key {key} 必须落在 {self.provider_key} 命名空间下"
                )
        if self.owner_ref is not None and not isinstance(self.owner_ref, AttributeSubjectRef):
            raise DamageValidationError("伤害事实 owner_ref 不受支持")
        if self.display_name is not None and (
            not isinstance(self.display_name, str) or not self.display_name.strip()
        ):
            raise DamageValidationError("伤害事实 display_name 必须是非空字符串")
        object.__setattr__(self, "facts", facts)


@runtime_checkable
class DamageFactProvider(Protocol):
    """内容侧定义并维护的会话级模拟状态视图（无状态转发）。

    实现必须转发到底层状态 store（角色状态、领域 store 等），取值反映调用
    当刻的模拟状态；实现自身不得保存变量、不得缓存、不得推进状态——推进
    归状态所有者，清零与快照也归底层 store 的既有链路。
    """

    @property
    def fact_spec(self) -> DamageFactSpec:
        """返回容器的身份与所提供的事实 key。"""

        ...

    def read_fact(self, key: str) -> DamageFactValue | None:
        """读取一个事实；容器不持有该 key 时返回 ``None``。"""

        ...


class DamageFactIndex:
    """按稳定顺序注册伤害事实容器，并在装配期检出 key 冲突。"""

    def __init__(self, providers: Sequence[DamageFactProvider] = ()) -> None:
        """注册容器，拒绝重复身份。

        key 归属由 ``DamageFactSpec`` 的命名空间前缀强制，不同容器不可能声明
        同一个 key，因此这里只需要拒绝重复的容器身份。
        """

        self._providers: dict[str, DamageFactProvider] = {}
        self._owner_keys: dict[str, str] = {}
        for provider in providers:
            spec = provider.fact_spec
            if spec.provider_key in self._providers:
                raise ConflictingDamageFactError(f"重复伤害事实容器：{spec.provider_key}")
            for key in sorted(spec.facts):
                self._owner_keys[key] = spec.provider_key
            self._providers[spec.provider_key] = provider

    @property
    def provider_keys(self) -> tuple[str, ...]:
        """按稳定字典序返回已注册容器的 provider key。"""

        return tuple(sorted(self._providers))

    @property
    def fact_keys(self) -> tuple[str, ...]:
        """按稳定字典序返回全部已注册的事实 key。"""

        return tuple(sorted(self._owner_keys))

    def owner_of(self, key: str) -> DamageFactSpec | None:
        """返回提供该 key 的容器声明；没有容器提供时返回 ``None``。"""

        provider_key = self._owner_keys.get(key)
        if provider_key is None:
            return None
        return self._providers[provider_key].fact_spec

    def provides(self, key: str) -> bool:
        """判断是否存在容器提供该事实 key。"""

        return key in self._owner_keys

    def read(self, key: str) -> DamageFactValue | None:
        """按全限定 key 读取事实；没有容器提供该 key 时返回 ``None``。"""

        provider_key = self._owner_keys.get(key)
        if provider_key is None:
            return None
        value = self._providers[provider_key].read_fact(key)
        if value is None:
            return None
        return validate_damage_fact_value(value, key)
