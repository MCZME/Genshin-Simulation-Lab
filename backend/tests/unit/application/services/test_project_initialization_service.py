from __future__ import annotations

from pathlib import Path

import pytest

from genshin_sim.application.errors import ConfigFileError
from genshin_sim.application.services.project_initialization import (
    AssetInitializationPlan,
    AssetInitializationStrategy,
    ProjectInitializationService,
)
from genshin_sim.infrastructure.file_storage.project_config import ProjectConfigFileStore

VALID_CONFIG = 'schema_version = 1\n\n[workspace]\ndata_dir = "data"\n'


class RecordingInit:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def __call__(self, path: str | Path) -> Path:
        resolved = Path(path)
        self.paths.append(resolved)
        return resolved


class RecordingBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, ...]] = []

    def build(self, *args: str | Path) -> Path:
        resolved = tuple(Path(arg) for arg in args)
        self.calls.append(resolved)
        return resolved[0]


class FixedSelector:
    def __init__(self, plan: AssetInitializationPlan) -> None:
        self.plan = plan

    def select(self) -> AssetInitializationPlan:
        return self.plan


class WritingTemplateProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    def provide(self, project_root: str | Path) -> Path | None:
        path = Path(project_root) / "config.example.toml"
        path.write_text(self.content, encoding="utf-8")
        return path


def _make_service(plan: AssetInitializationPlan):
    result_init = RecordingInit()
    manifest_builder = RecordingBuilder()
    source_builder = RecordingBuilder()
    service = ProjectInitializationService(
        config_store=ProjectConfigFileStore(),
        init_result_database=result_init,
        build_from_manifest=manifest_builder.build,
        rebuild_from_source=source_builder.build,
        asset_selector=FixedSelector(plan),
    )
    return service, result_init, manifest_builder, source_builder


def _write_template(root: Path, content: str = VALID_CONFIG) -> Path:
    path = root / "config.example.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_initialize_creates_workspace_and_builds_from_manifest(tmp_path):
    _write_template(tmp_path)
    manifest = tmp_path / "assets.json"
    plan = AssetInitializationPlan(
        AssetInitializationStrategy.FROM_MANIFEST,
        manifest,
    )
    service, result_init, manifest_builder, source_builder = _make_service(plan)
    asset_db = tmp_path / "data" / "assets" / "assets.db"

    result = service.initialize(tmp_path, asset_db_path=asset_db)

    assert (tmp_path / "config.toml").exists()
    for name in ("inputs", "results", "exports", "templates", "logs"):
        assert (tmp_path / "data" / name).is_dir()
    assert result_init.paths == [tmp_path / "data" / "results" / "results.db"]
    assert manifest_builder.calls == [(asset_db, manifest)]
    assert source_builder.calls == []
    assert result.asset_plan is plan
    assert result.warnings == ()


def test_initialize_fetch_source_plan_rebuilds_asset_database(tmp_path):
    _write_template(tmp_path)
    plan = AssetInitializationPlan(AssetInitializationStrategy.FETCH_SOURCE)
    service, result_init, manifest_builder, source_builder = _make_service(plan)
    asset_db = tmp_path / "assets.db"

    result = service.initialize(tmp_path, asset_db_path=asset_db)

    assert source_builder.calls == [(asset_db,)]
    assert manifest_builder.calls == []
    assert result.asset_plan.strategy is AssetInitializationStrategy.FETCH_SOURCE
    assert result_init.paths


def test_initialize_continues_with_existing_valid_config_and_missing_template(tmp_path):
    (tmp_path / "config.toml").write_text(VALID_CONFIG, encoding="utf-8")
    plan = AssetInitializationPlan(AssetInitializationStrategy.FETCH_SOURCE)
    service, result_init, _, source_builder = _make_service(plan)

    result = service.initialize(tmp_path, asset_db_path=tmp_path / "assets.db")

    assert (tmp_path / "data" / "inputs").is_dir()
    assert result_init.paths
    assert source_builder.calls
    assert len(result.warnings) == 1
    assert "缺少配置模板" in result.warnings[0]


def test_initialize_raises_when_config_and_template_missing(tmp_path):
    plan = AssetInitializationPlan(AssetInitializationStrategy.FETCH_SOURCE)
    service, result_init, _, source_builder = _make_service(plan)

    with pytest.raises(ConfigFileError, match="缺少 config.toml"):
        service.initialize(tmp_path, asset_db_path=tmp_path / "assets.db")

    assert result_init.paths == []
    assert source_builder.calls == []


def test_initialize_raises_on_invalid_config(tmp_path):
    (tmp_path / "config.toml").write_text("schema_version = [", encoding="utf-8")
    plan = AssetInitializationPlan(AssetInitializationStrategy.FETCH_SOURCE)
    service, result_init, _, source_builder = _make_service(plan)

    with pytest.raises(ConfigFileError, match="不是有效 TOML"):
        service.initialize(tmp_path, asset_db_path=tmp_path / "assets.db")

    assert result_init.paths == []
    assert source_builder.calls == []


def test_initialize_raises_on_invalid_template(tmp_path):
    _write_template(tmp_path, content="schema_version = [")
    plan = AssetInitializationPlan(AssetInitializationStrategy.FETCH_SOURCE)
    service, _, _, _ = _make_service(plan)

    with pytest.raises(ConfigFileError, match="不是有效 TOML"):
        service.initialize(tmp_path, asset_db_path=tmp_path / "assets.db")


def test_initialize_uses_template_provider_when_template_missing(tmp_path):
    provider = WritingTemplateProvider(VALID_CONFIG)
    plan = AssetInitializationPlan(AssetInitializationStrategy.FETCH_SOURCE)
    result_init = RecordingInit()
    source_builder = RecordingBuilder()
    service = ProjectInitializationService(
        config_store=ProjectConfigFileStore(),
        init_result_database=result_init,
        build_from_manifest=RecordingBuilder().build,
        rebuild_from_source=source_builder.build,
        asset_selector=FixedSelector(plan),
        template_provider=provider,
    )

    result = service.initialize(tmp_path, asset_db_path=tmp_path / "assets.db")

    assert (tmp_path / "config.toml").exists()
    assert result_init.paths
    assert source_builder.calls
    assert result.warnings and "缺少配置模板" in result.warnings[0]


def test_initialize_manifest_plan_without_path_raises(tmp_path):
    _write_template(tmp_path)
    plan = AssetInitializationPlan(AssetInitializationStrategy.FROM_MANIFEST)
    service, result_init, manifest_builder, _ = _make_service(plan)

    with pytest.raises(ValueError, match="必须提供 manifest 路径"):
        service.initialize(tmp_path, asset_db_path=tmp_path / "assets.db")

    assert manifest_builder.calls == []
    assert result_init.paths
