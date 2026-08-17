"""CLI 入口（genshin_sim.cli.main）的端到端命令测试。

单一关注点：所有命令族共用同一 argparse 入口、项目配置解析与日志初始化路径；
拆文件会重复整套入口夹具。当前行数超过测试规范 §4 的 500 行软信号，
后续按命令族拆分时同步收敛共享脚手架。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from genshin_sim.application.execution import (
    CompletedSimulationRun,
    FailedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.cli.main import main
from genshin_sim.infrastructure.results_sqlite import SQLiteResultWriter
from tests.helpers.logging import flush_project_handlers


def test_main_without_args_prints_help(capsys):
    assert main([]) == 0

    captured = capsys.readouterr()
    assert "usage: genshin-sim" in captured.out


def test_cli_can_write_log_file(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "assets.db"
    log_path = tmp_path / "cli.log"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)

    assert main(["--log-file", str(log_path), "assets", "build", "--db", str(db_path)]) == 0
    flush_project_handlers()

    captured = capsys.readouterr()
    assert "built local static asset database" in captured.out
    text = log_path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in text.splitlines() if line]
    assert any(
        record["message"] == "命令开始" and record["fields"].get("command") == "assets.build"
        for record in records
    )
    assert any(record["message"] == "资产数据库已构建" for record in records)


def test_cli_debug_logs_traceback_for_failures(tmp_path, capsys, monkeypatch):
    missing_config = tmp_path / "missing.json"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)

    assert main(["--debug", "input", "validate", str(missing_config)]) == 1

    captured = capsys.readouterr()
    assert "Traceback" in captured.err
    assert "error:" in captured.err


def test_cli_assets_build_and_info(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "assets.db"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)

    assert main(["assets", "build", "--db", str(db_path)]) == 0
    assert main(["assets", "info", "--db", str(db_path)]) == 0

    captured = capsys.readouterr()
    assert "built local static asset database" in captured.out
    assert "characters: 1" in captured.out
    assert "weapons: 1" in captured.out


def test_cli_assets_build_from_manifest(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "assets.db"
    manifest_path = tmp_path / "assets.json"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)
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
                        "burst_energy_cost": 40.0,
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
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)

    def fake_fetch_source(output_dir, **kwargs):
        del kwargs
        return _FakeSourceSummary(output_dir=Path(output_dir))

    monkeypatch.setattr(
        "genshin_sim.application.bootstrap.fetch_project_amber_source_cache",
        fake_fetch_source,
    )

    assert main(["assets", "fetch-source", "--out", str(cache_dir)]) == 0

    captured = capsys.readouterr()
    assert f"fetched asset source cache: {cache_dir}" in captured.out
    assert "source_name: project-amber-yatta" in captured.out
    assert "characters: 1" in captured.out
    assert "artifact_sets: 1" in captured.out
    assert "character_details: 0" in captured.out
    assert "artifact_set_details: 0" in captured.out


def test_cli_assets_build_manifest_uses_project_amber_converter(tmp_path, capsys, monkeypatch):
    cache_dir = tmp_path / "source-cache"
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)

    def fake_build_manifest(source_cache_dir, output_path):
        return _FakeManifestSummary(
            output_path=Path(output_path),
            source_cache_dir=Path(source_cache_dir),
        )

    monkeypatch.setattr(
        "genshin_sim.application.bootstrap.build_asset_manifest_from_project_amber_cache",
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
    assert "artifact_sets: 1" in captured.out
    assert "artifact_set_bonuses: 2" in captured.out
    assert "talent_scalings: 8" in captured.out
    assert "effect_payloads: 1" in captured.out


def test_cli_assets_audit_manifest_prints_report(tmp_path, capsys, monkeypatch):
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)

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

    monkeypatch.setattr(
        "genshin_sim.application.bootstrap.audit_asset_manifest",
        fake_audit_manifest,
    )

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


def test_cli_assets_validate_list_and_inspect_use_assets_service(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "assets.db"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)

    assert main(["assets", "build", "--db", str(db_path)]) == 0
    assert main(["assets", "validate", "--db", str(db_path)]) == 0
    assert main(["assets", "list", "--db", str(db_path), "characters"]) == 0
    assert main(["assets", "inspect", "--db", str(db_path), "character:test_character"]) == 0

    captured = capsys.readouterr()
    assert "asset database OK" in captured.out
    assert "character:test_character" in captured.out
    assert "Test Character" in captured.out
    assert "character.testing.runtime_probe" in captured.out


def test_cli_config_validate_uses_config_service(tmp_path, capsys, monkeypatch):
    input_path = tmp_path / "config.json"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)
    input_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "kind": "simulation_input",
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

    assert main(["input", "validate", str(input_path)]) == 0

    captured = capsys.readouterr()
    assert "input OK: CLI Config" in captured.out


def test_cli_project_init_creates_workspace_and_asset_database(tmp_path, capsys):
    (tmp_path / "config.example.toml").write_text(
        '# 项目配置\nschema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(json.dumps(_minimal_manifest()), encoding="utf-8")

    assert (
        main(
            [
                "project",
                "init",
                "--root",
                str(tmp_path),
                "--asset-manifest",
                str(manifest_path),
            ]
        )
        == 0
    )

    config_path = tmp_path / "config.toml"
    captured = capsys.readouterr()
    assert config_path.exists()
    assert f"initialized project config: {config_path}" in captured.out
    for name in ("inputs", "results", "exports", "templates", "logs"):
        assert (tmp_path / "data" / name).is_dir()
    assert (tmp_path / "data" / "results" / "results.db").exists()
    assert (tmp_path / "data" / "assets" / "assets.db").exists()
    assert "result database:" in captured.out
    assert "asset database:" in captured.out


def test_cli_project_show_prints_config_and_paths(tmp_path, capsys):
    (tmp_path / "config.example.toml").write_text(
        '# 项目配置\nschema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(json.dumps(_minimal_manifest()), encoding="utf-8")

    assert (
        main(
            [
                "project",
                "init",
                "--root",
                str(tmp_path),
                "--asset-manifest",
                str(manifest_path),
            ]
        )
        == 0
    )

    assert main(["project", "show", "--root", str(tmp_path)]) == 0

    captured = capsys.readouterr()
    assert "schema_version: 1" in captured.out
    assert "data_dir: data" in captured.out
    assert f"inputs: {tmp_path / 'data' / 'inputs'}" in captured.out


def test_cli_project_show_missing_config_fails(tmp_path, capsys):
    assert main(["project", "show", "--root", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "无法读取项目配置文件" in captured.err


def test_cli_project_init_missing_config_and_template_fails(tmp_path, capsys):
    assert main(["project", "init", "--root", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "缺少 config.toml" in captured.err


def test_cli_project_init_continues_with_existing_valid_config(tmp_path, capsys):
    (tmp_path / "config.toml").write_text(
        'schema_version = 1\n\n[workspace]\ndata_dir = "lab"\n',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(json.dumps(_minimal_manifest()), encoding="utf-8")

    assert (
        main(
            [
                "project",
                "init",
                "--root",
                str(tmp_path),
                "--asset-manifest",
                str(manifest_path),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert (tmp_path / "lab" / "inputs").is_dir()
    assert (tmp_path / "lab" / "results" / "results.db").exists()
    assert "warning: 缺少配置模板" in captured.err


def test_cli_project_init_rejects_invalid_template(tmp_path, capsys):
    (tmp_path / "config.example.toml").write_text(
        "schema_version = [",
        encoding="utf-8",
    )

    assert main(["project", "init", "--root", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "不是有效 TOML" in captured.err


def test_cli_project_init_rejects_conflicting_asset_flags(tmp_path, capsys):
    (tmp_path / "config.example.toml").write_text(
        '# 项目配置\nschema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "assets.json"

    assert (
        main(
            [
                "project",
                "init",
                "--root",
                str(tmp_path),
                "--asset-manifest",
                str(manifest_path),
                "--fetch-assets",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "不能同时使用" in captured.err


def test_cli_project_init_fetch_assets_rebuilds_from_source(tmp_path, capsys, monkeypatch):
    (tmp_path / "config.example.toml").write_text(
        '# 项目配置\nschema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )

    def fake_fetch(output_dir, **kwargs):
        del output_dir, kwargs
        return None

    def fake_build_manifest(source_cache_dir, output_path):
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(_minimal_manifest()), encoding="utf-8")
        return _FakeManifestSummary(
            output_path=target,
            source_cache_dir=Path(source_cache_dir),
        )

    monkeypatch.setattr(
        "genshin_sim.application.bootstrap.fetch_project_amber_source_cache",
        fake_fetch,
    )
    monkeypatch.setattr(
        "genshin_sim.application.bootstrap.build_asset_manifest_from_project_amber_cache",
        fake_build_manifest,
    )

    assert main(["project", "init", "--root", str(tmp_path), "--fetch-assets"]) == 0

    captured = capsys.readouterr()
    assert (tmp_path / "data" / "assets" / "assets.db").exists()
    assert "asset database:" in captured.out


def test_cli_input_list_lists_project_inputs(tmp_path, capsys):
    (tmp_path / "config.example.toml").write_text(
        '# 项目配置\nschema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(json.dumps(_minimal_manifest()), encoding="utf-8")
    assert (
        main(
            [
                "project",
                "init",
                "--root",
                str(tmp_path),
                "--asset-manifest",
                str(manifest_path),
            ]
        )
        == 0
    )
    inputs_dir = tmp_path / "data" / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    (inputs_dir / "rotation.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "kind": "simulation_input",
                "meta": {"name": "Rotation Demo", "description": ""},
                "team": [],
                "scene": {"player": {}, "targets": []},
                "input_trace": [],
                "rules": {"enabled": []},
                "run_options": {"max_frames": 10},
            }
        ),
        encoding="utf-8",
    )

    assert main(["input", "list", "--root", str(tmp_path)]) == 0

    captured = capsys.readouterr()
    assert "rotation\tok\tRotation Demo" in captured.out


def test_cli_results_list_uses_project_config_data_dir(tmp_path, capsys):
    (tmp_path / "config.toml").write_text(
        'schema_version = 1\n\n[workspace]\ndata_dir = "lab"\n',
        encoding="utf-8",
    )
    lab_result_db = tmp_path / "lab" / "results" / "results.db"
    writer = SQLiteResultWriter(lab_result_db)
    writer.save_run(
        CompletedSimulationRun(
            input_schema_version=2,
            input_kind="simulation_input",
            input_meta={"name": "Lab Run"},
            input_snapshot={"schema_version": 2, "kind": "simulation_input"},
            summary=SimulationRunSummary(
                stop_reason="MAX_FRAMES",
                end_frame=1,
                frames_run=1,
            ),
            events=(),
        )
    )

    assert main(["results", "list", "--root", str(tmp_path)]) == 0

    captured = capsys.readouterr()
    assert "Lab Run" in captured.out


def test_cli_results_list_and_inspect_use_results_service(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "results.db"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)
    writer = SQLiteResultWriter(db_path)
    session_id = writer.save_run(
        CompletedSimulationRun(
            input_schema_version=2,
            input_kind="simulation_input",
            input_meta={"name": "CLI Run"},
            input_snapshot={"schema_version": 2, "kind": "simulation_input"},
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


def test_cli_results_events_filters_by_frame(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "results.db"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)
    writer = SQLiteResultWriter(db_path)
    session_id = writer.save_run(
        CompletedSimulationRun(
            input_schema_version=2,
            input_kind="simulation_input",
            input_meta={"name": "CLI Events"},
            input_snapshot={"schema_version": 2, "kind": "simulation_input"},
            summary=SimulationRunSummary(
                stop_reason="MAX_FRAMES",
                end_frame=2,
                frames_run=2,
            ),
            events=(
                RecordedEvent(frame=1, event_type="INPUT_KEY_RECEIVED", data={"key": "keyboard.e"}),
                RecordedEvent(frame=2, event_type="DAMAGE_RESOLVED", data={"damage": 100}),
            ),
        )
    )

    assert (
        main(
            [
                "results",
                "events",
                session_id,
                "--results-db",
                str(db_path),
                "--frame-min",
                "2",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line]
    assert len(lines) == 1
    assert "2\tDAMAGE_RESOLVED" in lines[0]


def test_cli_results_list_filters_by_state(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "results.db"
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)
    writer = SQLiteResultWriter(db_path)
    writer.save_run(
        CompletedSimulationRun(
            input_schema_version=2,
            input_kind="simulation_input",
            input_meta={"name": "CLI Completed"},
            input_snapshot={"schema_version": 2, "kind": "simulation_input"},
            summary=SimulationRunSummary(
                stop_reason="MAX_FRAMES",
                end_frame=1,
                frames_run=1,
            ),
            events=(),
        )
    )
    writer.save_failed_run(
        FailedSimulationRun(
            session_id="failed-cli",
            input_schema_version=2,
            input_kind="simulation_input",
            input_meta={"name": "CLI Failed"},
            input_snapshot={"schema_version": 2, "kind": "simulation_input"},
            error_message="boom",
        )
    )

    assert (
        main(
            [
                "results",
                "list",
                "--results-db",
                str(db_path),
                "--state",
                "failed",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert "CLI Failed" in captured.out
    assert "CLI Completed" not in captured.out


def test_cli_creates_per_invocation_log_file_in_logs_dir(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)
    db_path = tmp_path / "assets.db"

    assert main(["assets", "build", "--db", str(db_path)]) == 0
    flush_project_handlers()

    log_files = list((tmp_path / "data" / "logs").glob("genshin-sim-*.jsonl"))
    assert len(log_files) == 1
    record = json.loads(log_files[0].read_text(encoding="utf-8").splitlines()[0])
    assert record["message"] == "命令开始"
    assert record["fields"]["command"] == "assets.build"
    assert record["fields"]["operation_id"]


def test_cli_requires_project_config(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert main(["assets", "build", "--db", str(tmp_path / "assets.db")]) == 1

    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "无法读取项目配置文件" in captured.err


def test_cli_explicit_log_file_takes_precedence_over_default_logs_dir(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    _write_project_config(tmp_path)
    db_path = tmp_path / "assets.db"
    log_path = tmp_path / "custom.jsonl"

    assert (
        main(
            [
                "--log-file",
                str(log_path),
                "assets",
                "build",
                "--db",
                str(db_path),
            ]
        )
        == 0
    )
    flush_project_handlers()

    assert log_path.exists()
    assert list((tmp_path / "data" / "logs").glob("genshin-sim-*.jsonl")) == []


def _minimal_manifest() -> dict:
    return {
        "schema_version": 1,
        "kind": "asset_manifest",
        "meta": {"data_version": "init-fixture-1"},
        "characters": [
            {
                "asset_key": "character:init_fixture",
                "source_id": "init_fixture",
                "name": "Init Fixture",
                "element": "pyro",
                "weapon_type": "polearm",
                "rarity": 4,
                "burst_energy_cost": 40.0,
            }
        ],
    }


def _write_project_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'schema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )
    return config_path


@dataclass(frozen=True, slots=True)
class _FakeSourceSummary:
    output_dir: Path
    source_name: str = "project-amber-yatta"
    source_version: str = "default"
    character_count: int = 1
    weapon_count: int = 1
    artifact_set_count: int = 1
    character_detail_count: int = 0
    weapon_detail_count: int = 0
    artifact_set_detail_count: int = 0
    file_count: int = 5
    content_hash: str = "abc123"


@dataclass(frozen=True, slots=True)
class _FakeManifestSummary:
    output_path: Path
    source_cache_dir: Path
    character_count: int = 1
    character_level_stat_count: int = 98
    weapon_count: int = 1
    weapon_level_stat_count: int = 96
    artifact_set_count: int = 1
    artifact_set_bonus_count: int = 2
    talent_scaling_count: int = 8
    effect_payload_count: int = 1
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
