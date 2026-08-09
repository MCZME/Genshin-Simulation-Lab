from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, cast

from genshin_sim.application.services import (
    AssetDatabaseService,
    AssetHandlerBindingService,
    AssetManifestAuditService,
    AssetManifestBuildService,
    AssetSourceCacheService,
    AssetsService,
    ConfigValidationService,
    ResultDatabaseService,
    ResultsService,
    SimulationTaskService,
)
from genshin_sim.content import create_default_content_unit_registry
from genshin_sim.infrastructure.assets_project_amber import (
    build_asset_manifest_from_project_amber_cache,
    fetch_project_amber_source_cache,
)
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    audit_asset_manifest,
    build_asset_database_from_manifest,
    init_asset_database,
    validate_asset_database,
    write_minimal_static_asset_database,
)
from genshin_sim.infrastructure.logging import (
    LoggingSettings,
    coerce_log_level,
    configure_logging,
    logging_context,
)
from genshin_sim.infrastructure.results_sqlite import (
    SQLiteResultRepository,
    SQLiteResultWriter,
    init_result_database,
)

DEFAULT_ASSET_DB = Path("data/assets/assets.db")
DEFAULT_ASSET_MANIFEST = Path("data/assets/manifests/project_amber_yatta.json")
DEFAULT_ASSET_SOURCE_CACHE = Path("data/assets/sources/project_amber_yatta/default")
DEFAULT_RESULT_DB = Path("data/results/results.db")
ENV_LOG_FILE = "GENSHIN_SIM_LOG_FILE"
ENV_LOG_LEVEL = "GENSHIN_SIM_LOG_LEVEL"
LOG_LEVEL_CHOICES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        _configure_cli_logging(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    with logging_context(**_cli_log_context(args)):
        handler = getattr(args, "handler", None)
        if handler is None:
            parser.print_help()
            return 0

        logger.info("CLI command started")
        try:
            exit_code = int(handler(args))
        except Exception as exc:
            if getattr(args, "debug", False):
                logger.exception("CLI command failed")
            elif _should_log_cli_failure(args):
                logger.error("CLI command failed: %s", exc)
                logger.debug("CLI command traceback", exc_info=True)
            else:
                logger.debug("CLI command failed", exc_info=True)
            print(f"error: {exc}", file=sys.stderr)
            return 1
        logger.info("CLI command finished", extra={"exit_code": exit_code})
        return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genshin-sim")
    _add_logging_arguments(parser)
    subparsers = parser.add_subparsers(dest="command")

    _add_assets_parser(subparsers)
    _add_config_parser(subparsers)
    _add_run_parser(subparsers)
    _add_results_parser(subparsers)
    return parser


def _add_logging_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVEL_CHOICES,
        help="Set the console log level.",
    )
    parser.add_argument("--log-file", type=Path, help="Write logs to a rotating file.")


def _add_assets_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    assets_parser = subparsers.add_parser("assets", help="Manage the local asset database.")
    assets_subparsers = assets_parser.add_subparsers(dest="assets_command")

    init_parser = assets_subparsers.add_parser("init", help="Initialize an empty asset DB.")
    _add_asset_db_argument(init_parser)
    init_parser.set_defaults(handler=_cmd_assets_init)

    build_parser = assets_subparsers.add_parser(
        "build",
        help="Build an asset DB.",
    )
    _add_asset_db_argument(build_parser)
    build_parser.add_argument(
        "--manifest",
        type=Path,
        help="Build from a local asset manifest JSON file.",
    )
    build_parser.set_defaults(handler=_cmd_assets_build)

    fetch_source_parser = assets_subparsers.add_parser(
        "fetch-source",
        help="抓取开发期资产源 raw cache。",
    )
    fetch_source_parser.add_argument(
        "--source",
        choices=("project-amber-yatta",),
        default="project-amber-yatta",
        help="资产源名称。",
    )
    fetch_source_parser.add_argument(
        "--character-id",
        action="append",
        default=[],
        help="按 Project Amber ID 抓取一个角色详情，可重复传入。",
    )
    fetch_source_parser.add_argument(
        "--weapon-id",
        action="append",
        default=[],
        help="按 Project Amber ID 抓取一个武器详情，可重复传入。",
    )
    fetch_source_parser.add_argument(
        "--artifact-set-id",
        action="append",
        default=[],
        help="按 Project Amber ID 抓取一个圣遗物套装详情，可重复传入。",
    )
    fetch_source_parser.add_argument(
        "--all-details",
        action="store_true",
        help="抓取全部角色、武器和圣遗物套装详情，可能较慢。",
    )
    fetch_source_parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_ASSET_SOURCE_CACHE,
        help="输出 raw source cache 目录。",
    )
    fetch_source_parser.set_defaults(handler=_cmd_assets_fetch_source)

    build_manifest_parser = assets_subparsers.add_parser(
        "build-manifest",
        help="从本地 raw source cache 构建资产 manifest。",
    )
    build_manifest_parser.add_argument(
        "--source",
        choices=("project-amber-yatta",),
        default="project-amber-yatta",
        help="资产源名称。",
    )
    build_manifest_parser.add_argument(
        "--source-cache",
        type=Path,
        default=DEFAULT_ASSET_SOURCE_CACHE,
        help="本地 raw source cache 目录。",
    )
    build_manifest_parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_ASSET_MANIFEST,
        help="输出资产 manifest JSON 路径。",
    )
    build_manifest_parser.set_defaults(handler=_cmd_assets_build_manifest)

    audit_manifest_parser = assets_subparsers.add_parser(
        "audit-manifest",
        help="验收资产 manifest 的数据完整性。",
    )
    audit_manifest_parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_ASSET_MANIFEST,
        help="待验收的资产 manifest JSON 路径。",
    )
    audit_manifest_parser.add_argument(
        "--max-issues",
        type=int,
        default=20,
        help="最多打印的问题数量。",
    )
    audit_manifest_parser.set_defaults(handler=_cmd_assets_audit_manifest)

    validate_parser = assets_subparsers.add_parser("validate", help="Validate an asset DB.")
    _add_asset_db_argument(validate_parser)
    validate_parser.set_defaults(handler=_cmd_assets_validate)

    info_parser = assets_subparsers.add_parser("info", help="Print asset DB info.")
    _add_asset_db_argument(info_parser)
    info_parser.set_defaults(handler=_cmd_assets_info)

    list_parser = assets_subparsers.add_parser("list", help="List assets.")
    _add_asset_db_argument(list_parser)
    list_parser.add_argument(
        "asset_type",
        choices=("characters", "weapons", "artifact-sets"),
    )
    list_parser.set_defaults(handler=_cmd_assets_list)

    inspect_parser = assets_subparsers.add_parser("inspect", help="Inspect one asset.")
    _add_asset_db_argument(inspect_parser)
    inspect_parser.add_argument("asset_key")
    inspect_parser.set_defaults(handler=_cmd_assets_inspect)

    set_handler_parser = assets_subparsers.add_parser(
        "set-handler",
        help="设置资产 handler_key（主动修改临时资产数据库）。",
    )
    _add_asset_db_argument(set_handler_parser)
    set_handler_parser.add_argument(
        "--kind",
        required=True,
        choices=("character", "weapon", "artifact-set", "artifact-bonus", "effect"),
    )
    set_handler_parser.add_argument("--key", required=True)
    set_handler_parser.add_argument("--handler-key", required=True)
    set_handler_parser.add_argument("--pieces", type=int)
    set_handler_parser.set_defaults(handler=_cmd_assets_set_handler)

    reset_handler_parser = assets_subparsers.add_parser(
        "reset-handler",
        help="重置资产 handler_key（可空类别清空，效果回到占位键）。",
    )
    _add_asset_db_argument(reset_handler_parser)
    reset_handler_parser.add_argument(
        "--kind",
        required=True,
        choices=("character", "weapon", "artifact-set", "artifact-bonus", "effect"),
    )
    reset_handler_parser.add_argument("--key", required=True)
    reset_handler_parser.add_argument("--pieces", type=int)
    reset_handler_parser.set_defaults(handler=_cmd_assets_reset_handler)

    show_handlers_parser = assets_subparsers.add_parser(
        "show-handlers",
        help="查看资产 handler_key 绑定。",
    )
    _add_asset_db_argument(show_handlers_parser)
    show_handlers_parser.add_argument(
        "--kind",
        required=True,
        choices=("character", "weapon", "artifact-set", "artifact-bonus", "effect"),
    )
    show_handlers_parser.add_argument("--owner")
    show_handlers_parser.set_defaults(handler=_cmd_assets_show_handlers)


def _add_config_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    config_parser = subparsers.add_parser("config", help="Work with SimulationConfig files.")
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    validate_parser = config_subparsers.add_parser("validate", help="Validate a config file.")
    validate_parser.add_argument("config_path")
    validate_parser.set_defaults(handler=_cmd_config_validate)


def _add_run_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    run_parser = subparsers.add_parser("run", help="Run a config through application services.")
    run_parser.add_argument("config_path")
    _add_asset_db_argument(run_parser)
    _add_result_db_argument(run_parser)
    run_parser.set_defaults(handler=_cmd_run)


def _add_results_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    results_parser = subparsers.add_parser("results", help="Read the local result database.")
    results_subparsers = results_parser.add_subparsers(dest="results_command")

    init_parser = results_subparsers.add_parser("init", help="Initialize a result DB.")
    _add_result_db_argument(init_parser)
    init_parser.set_defaults(handler=_cmd_results_init)

    list_parser = results_subparsers.add_parser("list", help="List saved runs.")
    _add_result_db_argument(list_parser)
    list_parser.add_argument("--limit", type=int, default=50)
    list_parser.set_defaults(handler=_cmd_results_list)

    inspect_parser = results_subparsers.add_parser("inspect", help="Inspect one saved run.")
    _add_result_db_argument(inspect_parser)
    inspect_parser.add_argument("session_id")
    inspect_parser.set_defaults(handler=_cmd_results_inspect)


def _add_asset_db_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", dest="asset_db", type=Path, default=DEFAULT_ASSET_DB)


def _add_result_db_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--results-db", dest="result_db", type=Path, default=DEFAULT_RESULT_DB)


def _cmd_assets_init(args: argparse.Namespace) -> int:
    path = _asset_database_service().init_database(args.asset_db)
    print(f"initialized asset database: {path}")
    return 0


def _cmd_assets_build(args: argparse.Namespace) -> int:
    manifest_path = getattr(args, "manifest", None)
    service = _asset_database_service(manifest_path=manifest_path)
    path = service.build_database(args.asset_db)
    if manifest_path is None:
        print(f"built local static asset database: {path}")
    else:
        print(f"built asset database from manifest: {path}")
    return 0


def _cmd_assets_fetch_source(args: argparse.Namespace) -> int:
    if args.source != "project-amber-yatta":
        raise ValueError(f"不支持的资产源：{args.source}")

    def fetch_source_cache(output_dir: str | Path):
        return fetch_project_amber_source_cache(
            output_dir,
            character_ids=args.character_id,
            weapon_ids=args.weapon_id,
            artifact_set_ids=args.artifact_set_id,
            include_all_details=bool(args.all_details),
        )

    summary = AssetSourceCacheService(
        fetch_source_cache=fetch_source_cache,
    ).fetch_source_cache(args.out)
    print(f"fetched asset source cache: {summary.output_dir}")
    print(f"source_name: {summary.source_name}")
    print(f"source_version: {summary.source_version}")
    print(f"characters: {summary.character_count}")
    print(f"weapons: {summary.weapon_count}")
    print(f"artifact_sets: {summary.artifact_set_count}")
    print(f"character_details: {summary.character_detail_count}")
    print(f"weapon_details: {summary.weapon_detail_count}")
    print(f"artifact_set_details: {summary.artifact_set_detail_count}")
    print(f"files: {summary.file_count}")
    print(f"content_hash: {summary.content_hash}")
    return 0


def _cmd_assets_build_manifest(args: argparse.Namespace) -> int:
    if args.source != "project-amber-yatta":
        raise ValueError(f"不支持的资产源：{args.source}")
    summary = AssetManifestBuildService(
        build_manifest=build_asset_manifest_from_project_amber_cache,
    ).build_manifest(args.source_cache, args.out)
    print(f"built asset manifest: {summary.output_path}")
    print(f"source_cache: {summary.source_cache_dir}")
    print(f"characters: {summary.character_count}")
    print(f"character_level_stats: {summary.character_level_stat_count}")
    print(f"weapons: {summary.weapon_count}")
    print(f"weapon_level_stats: {summary.weapon_level_stat_count}")
    print(f"artifact_sets: {summary.artifact_set_count}")
    print(f"artifact_set_bonuses: {summary.artifact_set_bonus_count}")
    print(f"talent_scalings: {summary.talent_scaling_count}")
    print(f"effect_payloads: {summary.effect_payload_count}")
    print(f"content_hash: {summary.content_hash}")
    return 0


def _cmd_assets_audit_manifest(args: argparse.Namespace) -> int:
    report = AssetManifestAuditService(audit_manifest=audit_asset_manifest).audit_manifest(
        args.manifest
    )
    max_issues = max(0, int(args.max_issues))

    print(f"资产 manifest: {report.manifest_path}")
    print(f"状态: {'OK' if report.ok else 'FAILED'}")
    print(f"data_version: {report.data_version}")
    print(f"characters: {report.character_count}")
    print(
        "character_level_stats: "
        f"{report.character_level_stat_count} "
        f"(完整覆盖 {report.character_level_complete_count}/{report.character_count})"
    )
    print(f"weapons: {report.weapon_count}")
    print(
        "weapon_level_stats: "
        f"{report.weapon_level_stat_count} "
        f"(完整覆盖 {report.weapon_level_complete_count}/{report.weapon_count})"
    )
    print(f"artifact_sets: {report.artifact_set_count}")
    print(f"artifact_set_bonuses: {report.artifact_set_bonus_count}")
    print(f"talent_scalings: {report.talent_scaling_count}")
    print(f"effect_payloads: {report.effect_payload_count}")
    print(f"issues: {report.issue_count}")
    for issue in report.issues[:max_issues]:
        print(f"- [{issue.code}] {issue.message}")
    omitted = report.issue_count - max_issues
    if omitted > 0:
        print(f"... 还有 {omitted} 个问题未打印")
    return 0 if report.ok else 1


def _cmd_assets_validate(args: argparse.Namespace) -> int:
    _asset_database_service().validate_database(args.asset_db)
    print(f"asset database OK: {args.asset_db}")
    return 0


def _cmd_assets_info(args: argparse.Namespace) -> int:
    info = AssetsService(SQLiteAssetRepository(args.asset_db)).get_info()
    print(f"schema_version: {info.meta.get('schema_version', '')}")
    print(f"data_version: {info.meta.get('data_version', '')}")
    print(f"characters: {info.character_count}")
    print(f"weapons: {info.weapon_count}")
    print(f"artifact_sets: {info.artifact_set_count}")
    return 0


def _cmd_assets_list(args: argparse.Namespace) -> int:
    service = AssetsService(SQLiteAssetRepository(args.asset_db))
    for item in service.list_assets(args.asset_type):
        print(f"{item.asset_key}\t{item.name}")
    return 0


def _cmd_assets_inspect(args: argparse.Namespace) -> int:
    item = AssetsService(SQLiteAssetRepository(args.asset_db)).inspect_asset(args.asset_key)
    print(_to_json(item))
    return 0


def _cmd_assets_set_handler(args: argparse.Namespace) -> int:
    binding = _asset_handler_binding_service(args.asset_db).set_handler(
        args.kind,
        args.key,
        args.handler_key,
        pieces=args.pieces,
    )
    print(f"set {binding.kind} handler: {binding.key} -> {binding.handler_key}")
    return 0


def _cmd_assets_reset_handler(args: argparse.Namespace) -> int:
    binding = _asset_handler_binding_service(args.asset_db).reset_handler(
        args.kind,
        args.key,
        pieces=args.pieces,
    )
    print(f"reset {binding.kind} handler: {binding.key} -> {binding.handler_key}")
    return 0


def _cmd_assets_show_handlers(args: argparse.Namespace) -> int:
    bindings = _asset_handler_binding_service(args.asset_db).show_handlers(
        args.kind,
        owner_key=args.owner,
    )
    for binding in bindings:
        pieces = "" if binding.pieces is None else str(binding.pieces)
        handler_key = "" if binding.handler_key is None else binding.handler_key
        print(f"{binding.key}\t{pieces}\t{handler_key}")
    return 0


def _cmd_config_validate(args: argparse.Namespace) -> int:
    config = ConfigValidationService().validate_file(args.config_path)
    print(f"config OK: {config.meta.name}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    service = SimulationTaskService.create(
        asset_repository=SQLiteAssetRepository(args.asset_db),
        result_writer=SQLiteResultWriter(args.result_db),
    )
    outcome = service.run_file_and_wait(args.config_path)
    print(f"session_id: {outcome.session_id}")
    if outcome.summary is None:
        raise RuntimeError("仿真任务完成但缺少摘要")
    print(f"stop_reason: {outcome.summary.stop_reason}")
    print(f"frames_run: {outcome.summary.frames_run}")
    return 0


def _cmd_results_init(args: argparse.Namespace) -> int:
    path = ResultDatabaseService(init_result_database).init_database(args.result_db)
    print(f"initialized result database: {path}")
    return 0


def _cmd_results_list(args: argparse.Namespace) -> int:
    service = ResultsService(SQLiteResultRepository(args.result_db))
    for item in service.list_runs(limit=args.limit):
        print(
            f"{item.session_id}\t{item.created_at}\t{item.name}\t"
            f"{item.stop_reason}\t{item.frames_run}\t{item.event_count}"
        )
    return 0


def _cmd_results_inspect(args: argparse.Namespace) -> int:
    detail = ResultsService(SQLiteResultRepository(args.result_db)).inspect_run(args.session_id)
    print(
        _to_json(
            {
                "session_id": detail.session_id,
                "created_at": detail.created_at,
                "summary": detail.summary.to_dict(),
                "event_count": len(detail.events),
                "events": [event.to_dict() for event in detail.events],
                "config_snapshot": detail.config_snapshot,
            }
        )
    )
    return 0


def _to_json(value: Any) -> str:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(cast(Any, value))
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _asset_database_service(manifest_path: Path | None = None) -> AssetDatabaseService:
    build_database = write_minimal_static_asset_database
    if manifest_path is not None:

        def build_database(db_path: str | Path) -> Path:
            return build_asset_database_from_manifest(db_path, manifest_path)

    return AssetDatabaseService(
        init_database=init_asset_database,
        build_database=build_database,
        validate_database=validate_asset_database,
    )


def _asset_handler_binding_service(asset_db: Path) -> AssetHandlerBindingService:
    return AssetHandlerBindingService(
        repository=SQLiteAssetRepository(asset_db),
        content_unit_registry=create_default_content_unit_registry(),
    )


def _configure_cli_logging(args: argparse.Namespace) -> None:
    debug = bool(getattr(args, "debug", False))
    explicit_level = _resolve_cli_log_level(args)
    file_path = _resolve_cli_log_file(args)
    console_level = logging.DEBUG if debug else explicit_level or logging.WARNING
    file_level = logging.DEBUG if debug else explicit_level or logging.INFO
    enabled_levels = [console_level]
    if file_path is not None:
        enabled_levels.append(file_level)

    configure_logging(
        LoggingSettings(
            level=_minimum_log_level(*enabled_levels),
            console_level=console_level,
            file_path=file_path,
            file_level=file_level,
        )
    )


def _resolve_cli_log_level(args: argparse.Namespace) -> str | None:
    return getattr(args, "log_level", None) or os.environ.get(ENV_LOG_LEVEL)


def _resolve_cli_log_file(args: argparse.Namespace) -> Path | None:
    file_path = getattr(args, "log_file", None)
    if file_path is not None:
        return file_path
    env_file_path = os.environ.get(ENV_LOG_FILE)
    return None if env_file_path is None else Path(env_file_path)


def _minimum_log_level(*levels: int | str) -> int:
    return min(coerce_log_level(level) for level in levels)


def _cli_log_context(args: argparse.Namespace) -> dict[str, object]:
    return {
        "command": _cli_command_name(args),
        "operation_id": uuid.uuid4().hex,
        "asset_db": getattr(args, "asset_db", None),
        "result_db": getattr(args, "result_db", None),
    }


def _cli_command_name(args: argparse.Namespace) -> str:
    parts = [
        getattr(args, "command", None),
        getattr(args, "assets_command", None),
        getattr(args, "config_command", None),
        getattr(args, "results_command", None),
    ]
    return ".".join(part for part in parts if part) or "help"


def _should_log_cli_failure(args: argparse.Namespace) -> bool:
    return _resolve_cli_log_level(args) is not None or _resolve_cli_log_file(args) is not None


if __name__ == "__main__":
    raise SystemExit(main())
