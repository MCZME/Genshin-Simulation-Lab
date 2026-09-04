from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

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


class _FakeManifestSync:
    def __init__(self) -> None:
        self.validated: list[tuple[str, HandlerBinding]] = []
        self.updated: list[tuple[str, HandlerBinding]] = []
        self.synced: list[tuple[str, tuple[HandlerBinding, ...]]] = []

    def validate(self, manifest_path, binding: HandlerBinding) -> None:
        self.validated.append((str(manifest_path), binding))

    def update(self, manifest_path, binding: HandlerBinding) -> Path:
        self.updated.append((str(manifest_path), binding))
        return Path(manifest_path)

    def sync(self, manifest_path, bindings: Sequence[HandlerBinding]) -> Path:
        self.synced.append((str(manifest_path), tuple(bindings)))
        return Path(manifest_path)


def _service_with_manifest() -> tuple[
    AssetHandlerBindingService, _FakeBindingRepository, _FakeManifestSync
]:
    service, repository = _service()
    manifest_sync = _FakeManifestSync()
    return (
        AssetHandlerBindingService(
            repository=repository,
            content_unit_registry=_registry(),
            manifest_validator=manifest_sync.validate,
            manifest_updater=manifest_sync.update,
            manifest_syncer=manifest_sync.sync,
        ),
        repository,
        manifest_sync,
    )


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


def test_set_handler_with_manifest_paths_validates_then_updates_manifest():
    service, repository, manifest_sync = _service_with_manifest()

    binding = service.set_handler(
        HandlerBindingKind.CHARACTER,
        "character:test",
        "character.test.real",
        manifest_paths=("manifest-a.json",),
    )

    assert binding.handler_key == "character.test.real"
    assert manifest_sync.validated == [("manifest-a.json", binding)]
    assert manifest_sync.updated == [("manifest-a.json", binding)]
    assert repository.set_calls == [("character", "character:test", "character.test.real", None)]


def test_set_handler_same_value_still_syncs_manifest():
    service, repository, manifest_sync = _service_with_manifest()
    repository.set_handler_binding("character", "character:test", "character.test.real")

    binding = service.set_handler(
        HandlerBindingKind.CHARACTER,
        "character:test",
        "character.test.real",
        manifest_paths=("manifest-a.json",),
    )

    assert binding.handler_key == "character.test.real"
    assert manifest_sync.updated == [("manifest-a.json", binding)]
    assert len(repository.set_calls) == 1


def test_reset_handler_with_manifest_paths_updates_manifest():
    service, repository, manifest_sync = _service_with_manifest()

    binding = service.reset_handler(
        HandlerBindingKind.EFFECT,
        "character:test:passive:1",
        manifest_paths=("manifest-a.json",),
    )

    assert binding.handler_key == "character.unimplemented_passive"
    assert manifest_sync.updated == [("manifest-a.json", binding)]
    assert repository.set_calls[-1][2] == "character.unimplemented_passive"


def test_sync_handlers_to_manifests_writes_all_bindings():
    service, _repository, manifest_sync = _service_with_manifest()

    result = service.sync_handlers_to_manifests(("manifest-a.json", "manifest-b.json"))

    assert result == {"manifest-a.json": 6, "manifest-b.json": 6}
    assert len(manifest_sync.synced) == 2
    assert all(len(bindings) == 6 for _path, bindings in manifest_sync.synced)


def test_set_handler_with_manifest_but_no_updater_fails_before_db_update():
    service, repository = _service()
    service = AssetHandlerBindingService(
        repository=repository,
        content_unit_registry=_registry(),
        manifest_validator=lambda _path, _binding: None,
    )

    with pytest.raises(ApplicationServiceError, match="manifest 写回器"):
        service.set_handler(
            HandlerBindingKind.CHARACTER,
            "character:test",
            "character.test.real",
            manifest_paths=("manifest-a.json",),
        )

    assert repository.set_calls == []
