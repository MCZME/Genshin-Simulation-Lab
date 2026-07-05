from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, overload

NOOP_HANDLER_KEY = "generic.noop"


class RegistryError(Exception):
    """Base error for handler registry failures."""


class DuplicateHandlerError(RegistryError, ValueError):
    """A handler_key was registered more than once."""


class HandlerNotFoundError(RegistryError, LookupError):
    """A handler_key was requested but not registered."""


@dataclass(frozen=True, slots=True)
class RuntimeHandlerRequest:
    """Context passed to a content handler during assembly."""

    handler_key: str
    owner_type: str
    owner_key: str
    slot: int | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    asset: Any | None = None

    def __post_init__(self) -> None:
        if not self.handler_key:
            raise RegistryError("handler_key must be non-empty")
        if not self.owner_type:
            raise RegistryError("owner_type must be non-empty")
        if not self.owner_key:
            raise RegistryError("owner_key must be non-empty")


class RuntimeHandler(Protocol):
    """Minimal runtime preparation hook for content handlers."""

    def prepare_runtime(self, request: RuntimeHandlerRequest) -> object | None:
        ...


HandlerFactory = Callable[[RuntimeHandlerRequest], object | None]


@dataclass(frozen=True, slots=True)
class _RuntimeHandlerAdapter:
    factory: HandlerFactory

    def prepare_runtime(self, request: RuntimeHandlerRequest) -> object | None:
        return self.factory(request)


class NoOpRuntimeHandler:
    """Placeholder handler used for test content and generic effects."""

    def prepare_runtime(self, request: RuntimeHandlerRequest) -> None:
        del request


class HandlerRegistry:
    """Explicit handler_key registry."""

    def __init__(self, factories: Mapping[str, HandlerFactory] | None = None) -> None:
        self._factories: dict[str, HandlerFactory] = {}
        for handler_key, factory in (factories or {}).items():
            self.register_factory(handler_key, factory)

    @property
    def handler_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def register_factory(
        self,
        handler_key: str,
        factory: HandlerFactory,
        *,
        replace: bool = False,
    ) -> HandlerFactory:
        if not handler_key:
            raise RegistryError("handler_key must be non-empty")
        if not callable(factory):
            raise RegistryError("handler factory must be callable")
        if handler_key in self._factories and not replace:
            raise DuplicateHandlerError(f"duplicate handler_key: {handler_key}")
        self._factories[handler_key] = factory
        return factory

    def register_handler(
        self,
        handler_key: str,
        handler: RuntimeHandler,
        *,
        replace: bool = False,
    ) -> RuntimeHandler:
        self.register_factory(handler_key, handler.prepare_runtime, replace=replace)
        return handler

    def has_handler(self, handler_key: str | None) -> bool:
        return handler_key is not None and handler_key in self._factories

    def get_factory(self, handler_key: str) -> HandlerFactory:
        if handler_key not in self._factories:
            raise HandlerNotFoundError(f"missing handler: {handler_key}")
        return self._factories[handler_key]

    def require_handler(self, handler_key: str) -> HandlerFactory:
        return self.get_factory(handler_key)

    @overload
    def create(self, target: str) -> RuntimeHandler:
        ...

    @overload
    def create(self, target: RuntimeHandlerRequest) -> object | None:
        ...

    def create(
        self,
        target: str | RuntimeHandlerRequest,
    ) -> RuntimeHandler | object | None:
        if isinstance(target, RuntimeHandlerRequest):
            return self.prepare_runtime(target)
        return _RuntimeHandlerAdapter(self.get_factory(target))

    def prepare_runtime(self, request: RuntimeHandlerRequest) -> object | None:
        return self.get_factory(request.handler_key)(request)

    def __contains__(self, handler_key: object) -> bool:
        return isinstance(handler_key, str) and handler_key in self._factories
