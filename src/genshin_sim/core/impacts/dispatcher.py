from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from genshin_sim.core.impacts.models import ImpactRequest


class ImpactFactory(Protocol):
    """把通用影响入口请求展开为一个或多个机制请求。"""

    def create_impact_requests(self, request: ImpactRequest) -> Sequence[ImpactRequest]:
        """根据入口请求创建待结算影响请求。"""
        ...


class ImpactDispatcher:
    """按 ``impact_key`` 分发影响请求的最小运行时入口。"""

    def __init__(self, factories: Mapping[str, ImpactFactory] | None = None) -> None:
        self._factories: dict[str, ImpactFactory] = {}
        if factories is not None:
            for impact_key, factory in factories.items():
                self.register(impact_key, factory)

    @property
    def factory_keys(self) -> tuple[str, ...]:
        return tuple(self._factories)

    def has_factory(self, impact_key: str) -> bool:
        return impact_key in self._factories

    def register(self, impact_key: str, factory: ImpactFactory) -> None:
        _validate_impact_key(impact_key)
        self._factories[impact_key] = factory

    def dispatch(self, request: ImpactRequest) -> tuple[ImpactRequest, ...]:
        factory = self._factories.get(request.impact_key)
        if factory is None:
            msg = f"未注册 impact factory：{request.impact_key}"
            raise KeyError(msg)
        return tuple(factory.create_impact_requests(request))


def _validate_impact_key(impact_key: str) -> None:
    if not impact_key.strip():
        msg = "impact_key 必须是非空字符串"
        raise ValueError(msg)
