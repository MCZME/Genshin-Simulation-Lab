from __future__ import annotations

from dataclasses import replace

import pytest

from genshin_sim.application.services import AssetHandlerBindingService, HandlerBindingKind
from genshin_sim.application.services.errors import ApplicationServiceError
from genshin_sim.assets import AssetNotFoundError, HandlerBinding
from genshin_sim.content.registries import ContentUnitRegistry


class _FakeBindingRepository:
    def __init__(
        self,
        bindings: dict[tuple[str, str, int | None], HandlerBinding],
    ) -> None:
        self.bindings = dict(bindings)
        self.set_calls: list[tuple[str, str, str | None, int | None]] = []

    def get_handler_binding(
        self,
        kind: str,
        key: str,
        pieces: int | None = None,
    ) -> HandlerBinding:
        try:
            return self.bindings[(kind, key, pieces)]
        except KeyError as exc:
            raise AssetNotFoundError(f"{kind} not found: {key}") from exc

    def set_handler_binding(
        self,
        kind: str,
        key: str,
        handler_key: str | None,
        pieces: int | None = None,
    ) -> None:
        marker = (kind, key, pieces)
        binding = self.bindings[marker]
        self.bindings[marker] = replace(binding, handler_key=handler_key)
        self.set_calls.append((kind, key, handler_key, pieces))

    def list_handler_bindings(
        self,
        kind: str,
        owner_key: str | None = None,
    ) -> tuple[HandlerBinding, ...]:
        return tuple(
            binding
            for (entry_kind, _key, _pieces), binding in self.bindings.items()
            if entry_kind == kind
        )


def _registry() -> ContentUnitRegistry:
    registry = ContentUnitRegistry()
    registry.register_character_factory("character.test.real", lambda request: None)
    registry.register_weapon_factory("weapon.test.real", lambda request: None)
    registry.register_artifact_factory("artifact.test.real", lambda request: None)
    registry.register_effect_factory("effect.test.real", lambda request: None)
    return registry


def _service() -> tuple[AssetHandlerBindingService, _FakeBindingRepository]:
    repository = _FakeBindingRepository(
        {
            ("character", "character:test", None): HandlerBinding(
                kind="character",
                key="character:test",
                handler_key=None,
            ),
            ("weapon", "weapon:test", None): HandlerBinding(
                kind="weapon",
                key="weapon:test",
                handler_key=None,
            ),
            ("artifact-set", "artifact_set:test", None): HandlerBinding(
                kind="artifact-set",
                key="artifact_set:test",
                handler_key=None,
            ),
            ("artifact-bonus", "artifact_set:test", 2): HandlerBinding(
                kind="artifact-bonus",
                key="artifact_set:test",
                pieces=2,
                handler_key="artifact.unimplemented_set_bonus",
            ),
            ("effect", "character:test:passive:1", None): HandlerBinding(
                kind="effect",
                key="character:test:passive:1",
                effect_kind="passive",
                handler_key="character.unimplemented_passive",
            ),
            ("effect", "character:test:constellation:1", None): HandlerBinding(
                kind="effect",
                key="character:test:constellation:1",
                effect_kind="constellation",
                handler_key="character.unimplemented_constellation",
            ),
        }
    )
    return AssetHandlerBindingService(
        repository=repository,
        content_unit_registry=_registry(),
    ), repository


def test_set_handler_updates_binding_and_requires_registration():
    service, repository = _service()

    binding = service.set_handler(
        HandlerBindingKind.CHARACTER,
        "character:test",
        "character.test.real",
    )

    assert binding.handler_key == "character.test.real"
    assert repository.set_calls == [("character", "character:test", "character.test.real", None)]


def test_set_handler_same_value_is_idempotent():
    service, repository = _service()
    repository.set_handler_binding(
        "character",
        "character:test",
        "character.test.real",
    )

    binding = service.set_handler(
        HandlerBindingKind.CHARACTER,
        "character:test",
        "character.test.real",
    )

    assert binding.handler_key == "character.test.real"
    assert len(repository.set_calls) == 1


def test_set_handler_rejects_empty_handler_key():
    service, _ = _service()

    with pytest.raises(ApplicationServiceError, match="handler_key 不能为空"):
        service.set_handler(HandlerBindingKind.CHARACTER, "character:test", "  ")


def test_set_handler_rejects_unregistered_handler():
    service, _ = _service()

    with pytest.raises(ApplicationServiceError, match="handler 未注册"):
        service.set_handler(
            HandlerBindingKind.CHARACTER,
            "character:test",
            "character.not_registered",
        )


def test_set_handler_rejects_missing_target():
    service, _ = _service()

    with pytest.raises(AssetNotFoundError):
        service.set_handler(
            HandlerBindingKind.CHARACTER,
            "character:missing",
            "character.test.real",
        )


@pytest.mark.parametrize(
    ("kind", "key", "pieces", "expected"),
    [
        (HandlerBindingKind.CHARACTER, "character:test", None, None),
        (HandlerBindingKind.WEAPON, "weapon:test", None, None),
        (HandlerBindingKind.ARTIFACT_SET, "artifact_set:test", None, None),
        (
            HandlerBindingKind.ARTIFACT_BONUS,
            "artifact_set:test",
            2,
            "artifact.unimplemented_set_bonus",
        ),
        (
            HandlerBindingKind.EFFECT,
            "character:test:passive:1",
            None,
            "character.unimplemented_passive",
        ),
        (
            HandlerBindingKind.EFFECT,
            "character:test:constellation:1",
            None,
            "character.unimplemented_constellation",
        ),
    ],
)
def test_reset_handler_targets(kind, key, pieces, expected):
    service, repository = _service()

    binding = service.reset_handler(kind, key, pieces=pieces)

    assert binding.handler_key == expected
    assert repository.set_calls[-1][2] == expected


def test_show_handlers_passes_through_repository():
    service, repository = _service()

    result = service.show_handlers(HandlerBindingKind.EFFECT)

    assert result == repository.list_handler_bindings("effect")
