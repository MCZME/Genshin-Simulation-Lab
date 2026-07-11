from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from genshin_sim.content.models import ContentRuntimeContribution

NOOP_HANDLER_KEY = "generic.noop"


class RegistryError(Exception):
    """handler 注册表错误基类。"""


class DuplicateHandlerError(RegistryError, ValueError):
    """同一个 handler_key 在内容注册表中被重复注册。"""


class HandlerNotFoundError(RegistryError, LookupError):
    """请求的 handler_key 未在对应内容类型中注册。"""


@dataclass(frozen=True, slots=True)
class CharacterRuntimeRequest:
    """角色内容在组装期创建运行时贡献所需的上下文。"""

    handler_key: str
    character_key: str
    slot: int
    params: Mapping[str, Any] = field(default_factory=dict)
    asset: Any | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.handler_key, "handler_key")
        _validate_non_empty_text(self.character_key, "character_key")
        _validate_slot(self.slot, "slot")
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class WeaponRuntimeRequest:
    """武器内容在组装期创建运行时贡献所需的上下文。"""

    handler_key: str
    weapon_key: str
    slot: int
    params: Mapping[str, Any] = field(default_factory=dict)
    asset: Any | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.handler_key, "handler_key")
        _validate_non_empty_text(self.weapon_key, "weapon_key")
        _validate_slot(self.slot, "slot")
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class ArtifactRuntimeRequest:
    """圣遗物内容在组装期创建运行时贡献所需的上下文。"""

    handler_key: str
    artifact_key: str
    slot: int
    artifact_kind: str = "artifact_set"
    piece_count: int | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    asset: Any | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.handler_key, "handler_key")
        _validate_non_empty_text(self.artifact_key, "artifact_key")
        _validate_non_empty_text(self.artifact_kind, "artifact_kind")
        _validate_slot(self.slot, "slot")
        if self.piece_count is not None and (
            isinstance(self.piece_count, bool) or self.piece_count < 0
        ):
            raise RegistryError("piece_count 提供时必须是非负整数")
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class ImpactRuntimeRequest:
    """资产 payload 在组装期创建 impact 运行时贡献所需的上下文。"""

    handler_key: str
    owner_type: str
    owner_key: str
    slot: int | None
    impact_key: str
    impact_kind: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.handler_key, "handler_key")
        _validate_non_empty_text(self.owner_type, "owner_type")
        _validate_non_empty_text(self.owner_key, "owner_key")
        _validate_non_empty_text(self.impact_key, "impact_key")
        _validate_non_empty_text(self.impact_kind, "impact_kind")
        if self.slot is not None:
            _validate_slot(self.slot, "slot")
        object.__setattr__(self, "params", dict(self.params))


type RuntimeContribution = ContentRuntimeContribution | None
type CharacterHandlerFactory = Callable[[CharacterRuntimeRequest], RuntimeContribution]
type WeaponHandlerFactory = Callable[[WeaponRuntimeRequest], RuntimeContribution]
type ArtifactHandlerFactory = Callable[[ArtifactRuntimeRequest], RuntimeContribution]
type ImpactHandlerFactory = Callable[[ImpactRuntimeRequest], RuntimeContribution]
type HandlerFactory = (
    CharacterHandlerFactory | WeaponHandlerFactory | ArtifactHandlerFactory | ImpactHandlerFactory
)


class RuntimeHandler(Protocol):
    """一个 handler_key 可以同时为多类内容提供装配期入口。"""

    def prepare_character_runtime(
        self,
        request: CharacterRuntimeRequest,
    ) -> RuntimeContribution:
        ...

    def prepare_weapon_runtime(
        self,
        request: WeaponRuntimeRequest,
    ) -> RuntimeContribution:
        ...

    def prepare_artifact_runtime(
        self,
        request: ArtifactRuntimeRequest,
    ) -> RuntimeContribution:
        ...

    def prepare_impact_runtime(
        self,
        request: ImpactRuntimeRequest,
    ) -> RuntimeContribution:
        ...


class NoOpRuntimeHandler:
    """用于测试内容和通用 payload 的占位 handler。"""

    def prepare_character_runtime(
        self,
        request: CharacterRuntimeRequest,
    ) -> RuntimeContribution:
        del request
        return None

    def prepare_weapon_runtime(
        self,
        request: WeaponRuntimeRequest,
    ) -> RuntimeContribution:
        del request
        return None

    def prepare_artifact_runtime(
        self,
        request: ArtifactRuntimeRequest,
    ) -> RuntimeContribution:
        del request
        return None

    def prepare_impact_runtime(
        self,
        request: ImpactRuntimeRequest,
    ) -> RuntimeContribution:
        del request
        return None


class HandlerRegistry:
    """按内容类型显式注册 handler_key 的装配期注册表。"""

    def __init__(self) -> None:
        self._character_factories: dict[str, CharacterHandlerFactory] = {}
        self._weapon_factories: dict[str, WeaponHandlerFactory] = {}
        self._artifact_factories: dict[str, ArtifactHandlerFactory] = {}
        self._impact_factories: dict[str, ImpactHandlerFactory] = {}

    @property
    def handler_keys(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    *self._character_factories,
                    *self._weapon_factories,
                    *self._artifact_factories,
                    *self._impact_factories,
                }
            )
        )

    def register_character_factory(
        self,
        handler_key: str,
        factory: CharacterHandlerFactory,
        *,
        replace: bool = False,
    ) -> CharacterHandlerFactory:
        _ensure_can_register_all(self._factory_maps(), handler_key, replace=replace)
        return _register_factory(self._character_factories, handler_key, factory, replace=replace)

    def register_weapon_factory(
        self,
        handler_key: str,
        factory: WeaponHandlerFactory,
        *,
        replace: bool = False,
    ) -> WeaponHandlerFactory:
        _ensure_can_register_all(self._factory_maps(), handler_key, replace=replace)
        return _register_factory(self._weapon_factories, handler_key, factory, replace=replace)

    def register_artifact_factory(
        self,
        handler_key: str,
        factory: ArtifactHandlerFactory,
        *,
        replace: bool = False,
    ) -> ArtifactHandlerFactory:
        _ensure_can_register_all(self._factory_maps(), handler_key, replace=replace)
        return _register_factory(self._artifact_factories, handler_key, factory, replace=replace)

    def register_impact_factory(
        self,
        handler_key: str,
        factory: ImpactHandlerFactory,
        *,
        replace: bool = False,
    ) -> ImpactHandlerFactory:
        _ensure_can_register_all(self._factory_maps(), handler_key, replace=replace)
        return _register_factory(self._impact_factories, handler_key, factory, replace=replace)

    def register_handler(
        self,
        handler_key: str,
        handler: RuntimeHandler,
        *,
        replace: bool = False,
    ) -> RuntimeHandler:
        _ensure_can_register_all(self._factory_maps(), handler_key, replace=replace)
        _register_factory(
            self._character_factories,
            handler_key,
            handler.prepare_character_runtime,
            replace=replace,
        )
        _register_factory(
            self._weapon_factories,
            handler_key,
            handler.prepare_weapon_runtime,
            replace=replace,
        )
        _register_factory(
            self._artifact_factories,
            handler_key,
            handler.prepare_artifact_runtime,
            replace=replace,
        )
        _register_factory(
            self._impact_factories,
            handler_key,
            handler.prepare_impact_runtime,
            replace=replace,
        )
        return handler

    def has_handler(self, handler_key: str | None) -> bool:
        return handler_key is not None and handler_key in self.handler_keys

    def has_character_handler(self, handler_key: str | None) -> bool:
        return handler_key is not None and handler_key in self._character_factories

    def has_weapon_handler(self, handler_key: str | None) -> bool:
        return handler_key is not None and handler_key in self._weapon_factories

    def has_artifact_handler(self, handler_key: str | None) -> bool:
        return handler_key is not None and handler_key in self._artifact_factories

    def has_impact_handler(self, handler_key: str | None) -> bool:
        return handler_key is not None and handler_key in self._impact_factories

    def create_character(self, request: CharacterRuntimeRequest) -> RuntimeContribution:
        return _require_factory(
            self._character_factories,
            request.handler_key,
            content_type="character",
        )(request)

    def create_weapon(self, request: WeaponRuntimeRequest) -> RuntimeContribution:
        return _require_factory(
            self._weapon_factories,
            request.handler_key,
            content_type="weapon",
        )(request)

    def create_artifact(self, request: ArtifactRuntimeRequest) -> RuntimeContribution:
        return _require_factory(
            self._artifact_factories,
            request.handler_key,
            content_type="artifact",
        )(request)

    def create_impact(self, request: ImpactRuntimeRequest) -> RuntimeContribution:
        return _require_factory(
            self._impact_factories,
            request.handler_key,
            content_type="impact",
        )(request)

    def __contains__(self, handler_key: object) -> bool:
        return isinstance(handler_key, str) and self.has_handler(handler_key)

    def _factory_maps(self) -> tuple[Mapping[str, HandlerFactory], ...]:
        return (
            self._character_factories,
            self._weapon_factories,
            self._artifact_factories,
            self._impact_factories,
        )


def _register_factory[RequestT](
    registry: dict[str, Callable[[RequestT], RuntimeContribution]],
    handler_key: str,
    factory: Callable[[RequestT], RuntimeContribution],
    *,
    replace: bool,
) -> Callable[[RequestT], RuntimeContribution]:
    _validate_non_empty_text(handler_key, "handler_key")
    if not callable(factory):
        raise RegistryError("handler 工厂必须可调用")
    if handler_key in registry and not replace:
        raise DuplicateHandlerError(f"重复 handler_key：{handler_key}")
    registry[handler_key] = factory
    return factory


def _ensure_can_register_all(
    registries: tuple[Mapping[str, HandlerFactory], ...],
    handler_key: str,
    *,
    replace: bool,
) -> None:
    _validate_non_empty_text(handler_key, "handler_key")
    if replace:
        return
    for registry in registries:
        if handler_key in registry:
            raise DuplicateHandlerError(f"重复 handler_key：{handler_key}")


def _require_factory[FactoryT: HandlerFactory](
    registry: dict[str, FactoryT],
    handler_key: str,
    *,
    content_type: str,
) -> FactoryT:
    try:
        return registry[handler_key]
    except KeyError as exc:
        raise HandlerNotFoundError(
            f"缺少{_content_type_label(content_type)} handler：{handler_key}"
        ) from exc


def _content_type_label(content_type: str) -> str:
    return {
        "character": "角色",
        "weapon": "武器",
        "artifact": "圣遗物",
        "impact": "impact",
    }.get(content_type, content_type)


def _validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{field_name} 必须是非空字符串")


def _validate_slot(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RegistryError(f"{field_name} 必须是整数")
