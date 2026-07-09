from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from genshin_sim.application.execution import (
    CompletedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.cli.main import main
from genshin_sim.infrastructure.results_sqlite import SQLiteResultWriter


def test_main_without_args_prints_help(capsys):
    assert main([]) == 0

    captured = capsys.readouterr()
    assert "usage: genshin-sim" in captured.out


def test_cli_can_write_log_file(tmp_path, capsys):
    db_path = tmp_path / "assets.db"
    log_path = tmp_path / "cli.log"

    assert main(["--log-file", str(log_path), "assets", "build", "--db", str(db_path)]) == 0
    _flush_project_handlers()

    captured = capsys.readouterr()
    assert "built local static asset database" in captured.out
    text = log_path.read_text(encoding="utf-8")
    assert "command=assets.build" in text
    assert "CLI command started" in text
    assert "资产数据库已构建" in text


def test_cli_debug_logs_traceback_for_failures(tmp_path, capsys):
    missing_config = tmp_path / "missing.json"

    assert main(["--debug", "config", "validate", str(missing_config)]) == 1

    captured = capsys.readouterr()
    assert "Traceback" in captured.err
    assert "error:" in captured.err


def test_cli_assets_build_and_info(tmp_path, capsys):
    db_path = tmp_path / "assets.db"

    assert main(["assets", "build", "--db", str(db_path)]) == 0
    assert main(["assets", "info", "--db", str(db_path)]) == 0

    captured = capsys.readouterr()
    assert "built local static asset database" in captured.out
    assert "characters: 1" in captured.out
    assert "weapons: 1" in captured.out


def test_cli_assets_build_from_manifest(tmp_path, capsys):
    db_path = tmp_path / "assets.db"
    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "asset_manifest",
                "meta": {"data_version": "cli-fixture-1"},
                "characters": [
                    {
                        "asset_key": "character:cli_fixture",
                        "source_id": "cli_fixture",
                        "name": "CLI Fixture",
                        "element": "pyro",
                        "weapon_type": "polearm",
                        "rarity": 4,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert main(["assets", "build", "--db", str(db_path), "--manifest", str(manifest_path)]) == 0
    assert main(["assets", "info", "--db", str(db_path)]) == 0
    assert main(["assets", "list", "--db", str(db_path), "characters"]) == 0

    captured = capsys.readouterr()
    assert "built asset database from manifest" in captured.out
    assert "data_version: cli-fixture-1" in captured.out
    assert "character:cli_fixture" in captured.out


def test_cli_assets_fetch_source_uses_project_amber_service(tmp_path, capsys, monkeypatch):
    cache_dir = tmp_path / "source-cache"

    def fake_fetch_source(output_dir, **kwargs):
        del kwargs
        return _FakeSourceSummary(output_dir=Path(output_dir))

    monkeypatch.setattr("genshin_sim.cli.main.fetch_project_amber_source_cache", fake_fetch_source)

    assert main(["assets", "fetch-source", "--out", str(cache_dir)]) == 0

    captured = capsys.readouterr()
    assert f"fetched asset source cache: {cache_dir}" in captured.out
    assert "source_name: project-amber-yatta" in captured.out
    assert "characters: 1" in captured.out
    assert "character_details: 0" in captured.out


def test_cli_assets_build_manifest_uses_project_amber_converter(tmp_path, capsys, monkeypatch):
    cache_dir = tmp_path / "source-cache"
    manifest_path = tmp_path / "manifest.json"

    def fake_build_manifest(source_cache_dir, output_path):
        return _FakeManifestSummary(
            output_path=Path(output_path),
            source_cache_dir=Path(source_cache_dir),
        )

    monkeypatch.setattr(
        "genshin_sim.cli.main.build_asset_manifest_from_project_amber_cache",
        fake_build_manifest,
    )

    assert (
        main(
            [
                "assets",
                "build-manifest",
                "--source-cache",
                str(cache_dir),
                "--out",
                str(manifest_path),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert f"built asset manifest: {manifest_path}" in captured.out
    assert f"source_cache: {cache_dir}" in captured.out
    assert "character_level_stats: 98" in captured.out
    assert "weapon_level_stats: 96" in captured.out


def test_cli_assets_audit_manifest_prints_report(tmp_path, capsys, monkeypatch):
    manifest_path = tmp_path / "manifest.json"

    def fake_audit_manifest(path):
        return _FakeAuditReport(
            manifest_path=Path(path),
            issues=(
                _FakeAuditIssue(
                    code="incomplete_character_level_stats",
                    message="1 个角色缺少完整等级属性",
                ),
            ),
        )

    monkeypatch.setattr("genshin_sim.cli.main.audit_asset_manifest", fake_audit_manifest)

    assert (
        main(
            [
                "assets",
                "audit-manifest",
                "--manifest",
                str(manifest_path),
                "--max-issues",
                "1",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert f"资产 manifest: {manifest_path}" in captured.out
    assert "状态: FAILED" in captured.out
    assert "character_level_stats: 98 (完整覆盖 0/1)" in captured.out
    assert "- [incomplete_character_level_stats] 1 个角色缺少完整等级属性" in captured.out


def test_cli_assets_validate_list_and_inspect_use_assets_service(tmp_path, capsys):
    db_path = tmp_path / "assets.db"

    assert main(["assets", "build", "--db", str(db_path)]) == 0
    assert main(["assets", "validate", "--db", str(db_path)]) == 0
    assert main(["assets", "list", "--db", str(db_path), "characters"]) == 0
    assert main(["assets", "inspect", "--db", str(db_path), "character:test_character"]) == 0

    captured = capsys.readouterr()
    assert "asset database OK" in captured.out
    assert "character:test_character" in captured.out
    assert "Test Character" in captured.out
    assert "character.testing.runtime_probe" in captured.out


def test_cli_config_validate_uses_config_service(tmp_path, capsys):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "simulation_config",
                "meta": {"name": "CLI Config"},
                "team": [],
                "scene": {"targets": []},
                "input_trace": [],
                "rules": {"enabled": []},
                "run_options": {"max_frames": 10},
            }
        ),
        encoding="utf-8",
    )

    assert main(["config", "validate", str(config_path)]) == 0

    captured = capsys.readouterr()
    assert "config OK: CLI Config" in captured.out


def test_cli_results_list_and_inspect_use_results_service(tmp_path, capsys):
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    session_id = writer.save_run(
        CompletedSimulationRun(
            config_schema_version=1,
            config_kind="simulation_config",
            config_meta={"name": "CLI Run"},
            config_snapshot={"schema_version": 1, "kind": "simulation_config"},
            summary=SimulationRunSummary(
                stop_reason="MAX_FRAMES",
                end_frame=10,
                frames_run=10,
            ),
            events=(
                RecordedEvent(
                    frame=1,
                    event_type="SIMULATION_STARTED",
                    data={},
                ),
            ),
            created_at="2026-07-04T00:00:00+00:00",
        )
    )

    assert main(["results", "list", "--results-db", str(db_path)]) == 0
    assert main(["results", "inspect", "--results-db", str(db_path), session_id]) == 0

    captured = capsys.readouterr()
    assert "CLI Run" in captured.out
    assert "MAX_FRAMES" in captured.out
    assert session_id in captured.out


def _flush_project_handlers() -> None:
    for handler in logging.getLogger("genshin_sim").handlers:
        handler.flush()


@dataclass(frozen=True, slots=True)
class _FakeSourceSummary:
    output_dir: Path
    source_name: str = "project-amber-yatta"
    source_version: str = "default"
    character_count: int = 1
    weapon_count: int = 1
    character_detail_count: int = 0
    weapon_detail_count: int = 0
    file_count: int = 6
    content_hash: str = "abc123"


@dataclass(frozen=True, slots=True)
class _FakeManifestSummary:
    output_path: Path
    source_cache_dir: Path
    character_count: int = 1
    character_level_stat_count: int = 98
    weapon_count: int = 1
    weapon_level_stat_count: int = 96
    content_hash: str = "manifest123"


@dataclass(frozen=True, slots=True)
class _FakeAuditIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class _FakeAuditReport:
    manifest_path: Path
    data_version: str = "audit-fixture-1"
    character_count: int = 1
    character_level_stat_count: int = 98
    character_level_complete_count: int = 0
    weapon_count: int = 1
    weapon_level_stat_count: int = 96
    weapon_level_complete_count: int = 1
    artifact_set_count: int = 0
    artifact_set_bonus_count: int = 0
    talent_scaling_count: int = 0
    effect_payload_count: int = 0
    issues: tuple[_FakeAuditIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def issue_count(self) -> int:
        return len(self.issues)
