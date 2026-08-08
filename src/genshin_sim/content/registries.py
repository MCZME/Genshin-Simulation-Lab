"""内容单元注册模型（新模型）。

内容工厂按内容类型注册，产出 ``ContentUnit``；请求携带命座、天赋等级、
精炼、套装件数等编译期证据，供内容编译阶段使用。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.definitions.content_unit import ContentUnit


class ContentUnitRegistryError(Exception):
    """内容单元注册表错误基类。"""


class DuplicateContentUnitFactoryError(ContentUnitRegistryError, ValueError):
    """同一个 handler_key 在内容单元注册表中重复注册。"""


class ContentUnitFactoryNotFoundError(ContentUnitRegistryError, LookupError):
    """请求的 handler_key 未在对应内容类型中注册。"""


@dataclass(frozen=True, slots=True)
class CharacterContentUnitRequest:
    """角色内容单元编译请求。"""

    handler_key: str
    character_key: str
    slot: int
    constellation: int = 0
    talent_levels: Mapping[str, int] = field(default_factory=dict)
    talent_scalings: tuple[TalentScalingEntry, ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)
    asset: Any | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.handler_key, "handler_key")
        _require_non_empty(self.character_key, "character_key")
        _require_positive_int(self.slot, "slot")
        _require_bounded_int(self.constellation, 0, 6, "constellation")
        talent_levels = dict(self.talent_levels)
        for talent_key, level in talent_levels.items():
            _require_non_empty(talent_key, "talent_levels key")
            _require_positive_int(level, f"talent_levels.{talent_key}")
        object.__setattr__(self, "talent_levels", talent_levels)
        object.__setattr__(self, "talent_scalings", tuple(self.talent_scalings))
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class WeaponContentUnitRequest:
    """武器内容单元编译请求。"""

    handler_key: str
    weapon_key: str
    slot: int
    refinement: int = 1
    params: Mapping[str, Any] = field(default_factory=dict)
    asset: Any | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.handler_key, "handler_key")
        _require_non_empty(self.weapon_key, "weapon_key")
        _require_positive_int(self.slot, "slot")
        _require_positive_int(self.refinement, "refinement")
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class ArtifactContentUnitRequest:
    """圣遗物内容单元编译请求。"""

    handler_key: str
    artifact_key: str
    slot: int
    artifact_kind: str = "artifact_set"
    piece_count: int | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    asset: Any | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.handler_key, "handler_key")
        _require_non_empty(self.artifact_key, "artifact_key")
        _require_non_empty(self.artifact_kind, "artifact_kind")
        _require_positive_int(self.slot, "slot")
        if self.piece_count is not None:
            _require_non_negative_int(self.piece_count, "piece_count")
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class EffectContentUnitRequest:
    """效果 payload 内容单元编译请求。"""

    handler_key: str
    effect_key: str
    effect_kind: str
    owner_type: str
    owner_key: str
    slot: int | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    unlock_key: str | None = None
    asset: Any | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.handler_key, "handler_key")
        _require_non_empty(self.effect_key, "effect_key")
        _require_non_empty(self.effect_kind, "effect_kind")
        _require_non_empty(self.owner_type, "owner_type")
        _require_non_empty(self.owner_key, "owner_key")
        if self.slot is not None:
            _require_positive_int(self.slot, "slot")
        if self.unlock_key is not None:
            _require_non_empty(self.unlock_key, "unlock_key")
        object.__setattr__(self, "params", dict(self.params))


type CharacterContentUnitFactory = Callable[
    [CharacterContentUnitRequest],
    ContentUnit | None,
]
type WeaponContentUnitFactory = Callable[[WeaponContentUnitRequest], ContentUnit | None]
type ArtifactContentUnitFactory = Callable[
    [ArtifactContentUnitRequest],
    ContentUnit | None,
]
type EffectContentUnitFactory = Callable[[EffectContentUnitRequest], ContentUnit | None]
type ContentUnitFactory = (
    CharacterContentUnitFactory
    | WeaponContentUnitFactory
    | ArtifactContentUnitFactory
    | EffectContentUnitFactory
)


class ContentUnitRegistry:
    """按内容类型显式注册内容单元工厂。"""

    def __init__(self) -> None:
        self._character_factories: dict[str, CharacterContentUnitFactory] = {}
        self._weapon_factories: dict[str, WeaponContentUnitFactory] = {}
        self._artifact_factories: dict[str, ArtifactContentUnitFactory] = {}
        self._effect_factories: dict[str, EffectContentUnitFactory] = {}

    @property
    def handler_keys(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    *self._character_factories,
                    *self._weapon_factories,
                    *self._artifact_factories,
                    *self._effect_factories,
                }
            )
        )

    def register_character_factory(
        self,
        handler_key: str,
        factory: CharacterContentUnitFactory,
        *,
        replace: bool = False,
    ) -> CharacterContentUnitFactory:
        _ensure_can_register(
            (
                self._character_factories,
                self._weapon_factories,
                self._artifact_factories,
                self._effect_factories,
            ),
            handler_key,
            replace=replace,
        )
        return _register_factory(
            self._character_factories,
            handler_key,
            factory,
            replace=replace,
        )

    def register_weapon_factory(
        self,
        handler_key: str,
        factory: WeaponContentUnitFactory,
        *,
        replace: bool = False,
    ) -> WeaponContentUnitFactory:
        _ensure_can_register(
            (
                self._character_factories,
                self._weapon_factories,
                self._artifact_factories,
                self._effect_factories,
            ),
            handler_key,
            replace=replace,
        )
        return _register_factory(
            self._weapon_factories,
            handler_key,
            factory,
            replace=replace,
        )

    def register_artifact_factory(
        self,
        handler_key: str,
        factory: ArtifactContentUnitFactory,
        *,
        replace: bool = False,
    ) -> ArtifactContentUnitFactory:
        _ensure_can_register(
            (
                self._character_factories,
                self._weapon_factories,
                self._artifact_factories,
                self._effect_factories,
            ),
            handler_key,
            replace=replace,
        )
        return _register_factory(
            self._artifact_factories,
            handler_key,
            factory,
            replace=replace,
        )

    def register_effect_factory(
        self,
        handler_key: str,
        factory: EffectContentUnitFactory,
        *,
        replace: bool = False,
    ) -> EffectContentUnitFactory:
        _ensure_can_register(
            (
                self._character_factories,
                self._weapon_factories,
                self._artifact_factories,
                self._effect_factories,
            ),
            handler_key,
            replace=replace,
        )
        return _register_factory(
            self._effect_factories,
            handler_key,
            factory,
            replace=replace,
        )

    def register_noop_handler(
        self,
        handler_key: str,
        *,
        replace: bool = False,
    ) -> None:
        """注册四类内容均为空贡献的占位 handler_key。"""

        _require_non_empty(handler_key, "handler_key")
        if not replace:
            for registry in self._factory_maps():
                if handler_key in registry:
                    raise DuplicateContentUnitFactoryError(f"重复 handler_key：{handler_key}")
        for registry in self._factory_maps():
            cast(dict[str, Any], registry)[handler_key] = _noop_factory

    def has_character_handler(self, handler_key: str | None) -> bool:
        return handler_key is not None and handler_key in self._character_factories

    def has_weapon_handler(self, handler_key: str | None) -> bool:
        return handler_key is not None and handler_key in self._weapon_factories

    def has_artifact_handler(self, handler_key: str | None) -> bool:
        return handler_key is not None and handler_key in self._artifact_factories

    def has_effect_handler(self, handler_key: str | None) -> bool:
        return handler_key is not None and handler_key in self._effect_factories

    def create_character(
        self,
        request: CharacterContentUnitRequest,
    ) -> ContentUnit | None:
        return _require_factory(
            self._character_factories,
            request.handler_key,
            content_type="角色",
        )(request)

    def create_weapon(
        self,
        request: WeaponContentUnitRequest,
    ) -> ContentUnit | None:
        return _require_factory(
            self._weapon_factories,
            request.handler_key,
            content_type="武器",
        )(request)

    def create_artifact(
        self,
        request: ArtifactContentUnitRequest,
    ) -> ContentUnit | None:
        return _require_factory(
            self._artifact_factories,
            request.handler_key,
            content_type="圣遗物",
        )(request)

    def create_effect(
        self,
        request: EffectContentUnitRequest,
    ) -> ContentUnit | None:
        return _require_factory(
            self._effect_factories,
            request.handler_key,
            content_type="效果",
        )(request)

    def _factory_maps(
        self,
    ) -> tuple[
        dict[str, CharacterContentUnitFactory],
        dict[str, WeaponContentUnitFactory],
        dict[str, ArtifactContentUnitFactory],
        dict[str, EffectContentUnitFactory],
    ]:
        return (
            self._character_factories,
            self._weapon_factories,
            self._artifact_factories,
            self._effect_factories,
        )


def _noop_factory(request: object) -> None:
    del request
    return None


def _register_factory[RequestT](
    registry: dict[str, Callable[[RequestT], ContentUnit | None]],
    handler_key: str,
    factory: Callable[[RequestT], ContentUnit | None],
    *,
    replace: bool,
) -> Callable[[RequestT], ContentUnit | None]:
    _require_non_empty(handler_key, "handler_key")
    if not callable(factory):
        raise ContentUnitRegistryError("内容单元工厂必须可调用")
    if handler_key in registry and not replace:
        raise DuplicateContentUnitFactoryError(f"重复 handler_key：{handler_key}")
    registry[handler_key] = factory
    return factory


def _ensure_can_register(
    registries: tuple[Mapping[str, ContentUnitFactory], ...],
    handler_key: str,
    *,
    replace: bool,
) -> None:
    _require_non_empty(handler_key, "handler_key")
    if replace:
        return
    for registry in registries:
        if handler_key in registry:
            raise DuplicateContentUnitFactoryError(f"重复 handler_key：{handler_key}")


def _require_factory[FactoryT: ContentUnitFactory](
    registry: dict[str, FactoryT],
    handler_key: str,
    *,
    content_type: str,
) -> FactoryT:
    try:
        return registry[handler_key]
    except KeyError as exc:
        raise ContentUnitFactoryNotFoundError(
            f"缺少{content_type}内容单元工厂：{handler_key}"
        ) from exc


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContentUnitRegistryError(f"{field_name} 必须是非空字符串")


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContentUnitRegistryError(f"{field_name} 必须是正整数")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContentUnitRegistryError(f"{field_name} 必须是非负整数")


def _require_bounded_int(value: int, minimum: int, maximum: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ContentUnitRegistryError(f"{field_name} 必须在 {minimum} 到 {maximum} 之间")
