"""命令行入口。

CLI 只负责参数解析、调用 application facade 和格式化输出，
不直接访问基础设施、service 或仿真核心。
"""

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

from genshin_sim.application import (
    ApplicationFacade,
    AssetInitializationPlan,
    AssetInitializationSelector,
    AssetInitializationStrategy,
    ProjectConfig,
    create_cli_application,
)
from genshin_sim.infrastructure.logging import (
    LoggingSettings,
    coerce_log_level,
    configure_logging,
    logging_context,
)

DEFAULT_ASSET_DB = Path("data") / "assets" / "assets.db"
DEFAULT_ASSET_MANIFEST = Path("data") / "assets" / "manifests" / "project_amber_yatta.json"
DEFAULT_ASSET_SOURCE_CACHE = (
    Path("data") / "assets" / "sources" / "project_amber_yatta" / "default"
)
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

        logger.info("命令开始")
        try:
            exit_code = int(handler(args))
        except Exception as exc:
            if getattr(args, "debug", False):
                logger.exception("命令失败")
            elif _should_log_cli_failure(args):
                logger.error("命令失败：%s", exc)
                logger.debug("命令失败堆栈", exc_info=True)
            else:
                logger.debug("命令失败", exc_info=True)
            print(f"error: {exc}", file=sys.stderr)
            return 1
        logger.info("命令结束", extra={"exit_code": exit_code})
        return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genshin-sim")
    _add_logging_arguments(parser)
    subparsers = parser.add_subparsers(dest="command")

    _add_assets_parser(subparsers)
    _add_input_parser(subparsers)
    _add_project_parser(subparsers)
    _add_run_parser(subparsers)
    _add_results_parser(subparsers)
    return parser


def _add_logging_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--debug", action="store_true", help="启用调试日志。")
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVEL_CHOICES,
        help="设置控制台日志级别。",
    )
    parser.add_argument("--log-file", type=Path, help="写入轮转日志文件。")


def _add_assets_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    assets_parser = subparsers.add_parser("assets", help="管理本地资产数据库。")
    assets_subparsers = assets_parser.add_subparsers(dest="assets_command")

    init_parser = assets_subparsers.add_parser("init", help="初始化空资产数据库。")
    _add_asset_db_argument(init_parser)
    init_parser.set_defaults(handler=_cmd_assets_init)

    build_parser = assets_subparsers.add_parser("build", help="构建资产数据库。")
    _add_asset_db_argument(build_parser)
    build_parser.add_argument(
        "--manifest",
        type=Path,
        help="从本地资产 manifest JSON 文件构建。",
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

    validate_parser = assets_subparsers.add_parser("validate", help="校验资产数据库。")
    _add_asset_db_argument(validate_parser)
    validate_parser.set_defaults(handler=_cmd_assets_validate)

    info_parser = assets_subparsers.add_parser("info", help="打印资产数据库信息。")
    _add_asset_db_argument(info_parser)
    info_parser.set_defaults(handler=_cmd_assets_info)

    list_parser = assets_subparsers.add_parser("list", help="列出资产。")
    _add_asset_db_argument(list_parser)
    list_parser.add_argument(
        "asset_type",
        choices=("characters", "weapons", "artifact-sets"),
    )
    list_parser.set_defaults(handler=_cmd_assets_list)

    inspect_parser = assets_subparsers.add_parser("inspect", help="查看单个资产。")
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
    set_handler_parser.add_argument(
        "--manifest",
        action="append",
        type=Path,
        default=[],
        help="同时写回指定资产 manifest，可重复传入。",
    )
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
    reset_handler_parser.add_argument(
        "--manifest",
        action="append",
        type=Path,
        default=[],
        help="同时写回指定资产 manifest，可重复传入。",
    )
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

    sync_handlers_parser = assets_subparsers.add_parser(
        "sync-handlers",
        help="把资产数据库中的 handler_key 绑定写回指定资产 manifest。",
    )
    _add_asset_db_argument(sync_handlers_parser)
    sync_handlers_parser.add_argument(
        "--manifest",
        action="append",
        type=Path,
        required=True,
        help="要同步的资产 manifest，可重复传入。",
    )
    sync_handlers_parser.add_argument(
        "--kind",
        choices=("character", "weapon", "artifact-set", "artifact-bonus", "effect"),
        help="只同步指定类别；缺省同步全部类别。",
    )
    sync_handlers_parser.set_defaults(handler=_cmd_assets_sync_handlers)


def _add_input_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    input_parser = subparsers.add_parser("input", help="操作模拟输入文件。")
    input_subparsers = input_parser.add_subparsers(dest="input_command")

    validate_parser = input_subparsers.add_parser("validate", help="校验模拟输入文件。")
    validate_parser.add_argument("input_path")
    validate_parser.set_defaults(handler=_cmd_input_validate)

    list_parser = input_subparsers.add_parser("list", help="列出项目 inputs 目录中的模拟输入。")
    _add_project_root_argument(list_parser)
    list_parser.set_defaults(handler=_cmd_input_list)


def _add_project_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    project_parser = subparsers.add_parser("project", help="管理项目配置。")
    project_subparsers = project_parser.add_subparsers(dest="project_command")

    init_parser = project_subparsers.add_parser("init", help="初始化默认 config.toml。")
    _add_project_root_argument(init_parser)
    init_parser.add_argument(
        "--asset-manifest",
        type=Path,
        help="从指定 manifest 构建资产库（跳过交互选择）。",
    )
    init_parser.add_argument(
        "--fetch-assets",
        action="store_true",
        help="通过 fetch-source 完全重新构建资产库（跳过交互选择）。",
    )
    init_parser.add_argument(
        "--asset-db",
        type=Path,
        default=None,
        help="资产库路径（默认：<root>/data/assets/assets.db）。",
    )
    init_parser.set_defaults(handler=_cmd_project_init)

    show_parser = project_subparsers.add_parser("show", help="显示项目配置与工作区路径。")
    _add_project_root_argument(show_parser)
    show_parser.set_defaults(handler=_cmd_project_show)


def _add_project_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="项目根目录（默认：当前目录）。",
    )


def _add_run_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    run_parser = subparsers.add_parser("run", help="通过应用服务运行模拟输入。")
    run_parser.add_argument("input_path")
    _add_project_root_argument(run_parser)
    _add_asset_db_argument(run_parser)
    _add_result_db_argument(run_parser)
    run_parser.set_defaults(handler=_cmd_run)


def _add_results_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    results_parser = subparsers.add_parser("results", help="读取本地结果数据库。")
    results_subparsers = results_parser.add_subparsers(dest="results_command")

    init_parser = results_subparsers.add_parser("init", help="初始化结果数据库。")
    _add_result_db_argument(init_parser)
    _add_project_root_argument(init_parser)
    init_parser.set_defaults(handler=_cmd_results_init)

    list_parser = results_subparsers.add_parser("list", help="列出已保存的运行。")
    _add_result_db_argument(list_parser)
    _add_project_root_argument(list_parser)
    list_parser.add_argument("--limit", type=int, default=50)
    list_parser.add_argument(
        "--state",
        choices=("completed", "failed", "cancelled"),
        default=None,
        help="按运行状态过滤。",
    )
    list_parser.set_defaults(handler=_cmd_results_list)

    inspect_parser = results_subparsers.add_parser("inspect", help="查看单个已保存运行。")
    _add_result_db_argument(inspect_parser)
    _add_project_root_argument(inspect_parser)
    inspect_parser.add_argument("session_id")
    inspect_parser.set_defaults(handler=_cmd_results_inspect)

    events_parser = results_subparsers.add_parser("events", help="列出单个已保存运行的事件。")
    _add_result_db_argument(events_parser)
    _add_project_root_argument(events_parser)
    events_parser.add_argument("session_id")
    events_parser.add_argument("--frame-min", type=int, default=None)
    events_parser.add_argument("--frame-max", type=int, default=None)
    events_parser.add_argument("--event-type", default=None)
    events_parser.add_argument("--offset", type=int, default=None)
    events_parser.add_argument("--limit", type=int, default=None)
    events_parser.set_defaults(handler=_cmd_results_events)


def _add_asset_db_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", dest="asset_db", type=Path, default=DEFAULT_ASSET_DB)


def _add_result_db_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--results-db",
        dest="result_db",
        type=Path,
        default=None,
        help="结果数据库路径（默认：由项目 config.toml 决定）。",
    )


def _resolve_result_db(args: argparse.Namespace) -> Path:
    result_db = getattr(args, "result_db", None)
    if result_db is not None:
        return Path(result_db)
    resolved = getattr(args, "_resolved_result_db", None)
    if resolved is not None:
        return Path(resolved)
    return _load_project_config(args).results_db(_project_root(args))


def _cmd_assets_init(args: argparse.Namespace) -> int:
    path = _application(args).init_asset_database(args.asset_db)
    print(f"initialized asset database: {path}")
    return 0


def _cmd_assets_build(args: argparse.Namespace) -> int:
    manifest_path = getattr(args, "manifest", None)
    path = _application(args).build_asset_database(args.asset_db, manifest_path=manifest_path)
    if manifest_path is None:
        print(f"built local static asset database: {path}")
    else:
        print(f"built asset database from manifest: {path}")
    return 0


def _cmd_assets_fetch_source(args: argparse.Namespace) -> int:
    summary = _application(args).fetch_asset_source(
        args.out,
        source=args.source,
        character_ids=args.character_id,
        weapon_ids=args.weapon_id,
        artifact_set_ids=args.artifact_set_id,
        include_all_details=bool(args.all_details),
    )
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
    summary = _application(args).build_asset_manifest(args.source_cache, args.out)
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
    report = _application(args).audit_asset_manifest(args.manifest)
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
    _application(args).validate_asset_database(args.asset_db)
    print(f"asset database OK: {args.asset_db}")
    return 0


def _cmd_assets_info(args: argparse.Namespace) -> int:
    info = _application(args).get_asset_db_info()
    print(f"schema_version: {info.meta.get('schema_version', '')}")
    print(f"data_version: {info.meta.get('data_version', '')}")
    print(f"characters: {info.character_count}")
    print(f"weapons: {info.weapon_count}")
    print(f"artifact_sets: {info.artifact_set_count}")
    return 0


def _cmd_assets_list(args: argparse.Namespace) -> int:
    for item in _application(args).list_assets(args.asset_type):
        print(f"{item.asset_key}	{item.name}")
    return 0


def _cmd_assets_inspect(args: argparse.Namespace) -> int:
    item = _application(args).inspect_asset(args.asset_key)
    print(_to_json(item))
    return 0


def _cmd_assets_set_handler(args: argparse.Namespace) -> int:
    binding = _application(args).set_asset_handler(
        args.kind,
        args.key,
        args.handler_key,
        pieces=args.pieces,
        manifest_paths=tuple(args.manifest),
    )
    print(f"set {binding.kind} handler: {binding.key} -> {binding.handler_key}")
    return 0


def _cmd_assets_reset_handler(args: argparse.Namespace) -> int:
    binding = _application(args).reset_asset_handler(
        args.kind,
        args.key,
        pieces=args.pieces,
        manifest_paths=tuple(args.manifest),
    )
    print(f"reset {binding.kind} handler: {binding.key} -> {binding.handler_key}")
    return 0


def _cmd_assets_show_handlers(args: argparse.Namespace) -> int:
    bindings = _application(args).list_asset_handlers(args.kind, owner_key=args.owner)
    for binding in bindings:
        pieces = "" if binding.pieces is None else str(binding.pieces)
        handler_key = "" if binding.handler_key is None else binding.handler_key
        print(f"{binding.key}	{pieces}	{handler_key}")
    return 0


def _cmd_assets_sync_handlers(args: argparse.Namespace) -> int:
    result = _application(args).sync_asset_handlers(tuple(args.manifest), kind=args.kind)
    for manifest_path, count in sorted(result.items()):
        print(f"synced {count} handler bindings to {manifest_path}")
    return 0


def _cmd_input_validate(args: argparse.Namespace) -> int:
    config = _application(args).validate_input_file(args.input_path)
    print(f"input OK: {config.meta.name}")
    return 0


def _cmd_input_list(args: argparse.Namespace) -> int:
    for item in _application(args).list_inputs():
        status = "error" if item.error else "ok"
        name = item.name or "-"
        print(f"{item.input_key}	{status}	{name}	{item.path}")
    return 0


def _cmd_project_init(args: argparse.Namespace) -> int:
    if args.asset_manifest is not None and args.fetch_assets:
        raise ValueError("--asset-manifest 与 --fetch-assets 不能同时使用")

    root = Path(args.root)
    asset_db_path = args.asset_db or (root / DEFAULT_ASSET_DB)

    selector = _CliAssetInitializationSelector(
        manifest_path=args.asset_manifest,
        fetch_source=args.fetch_assets,
    )
    result = _application(args).initialize_project(
        root,
        asset_db_path=asset_db_path,
        selector=selector,
    )

    print(f"initialized project config: {result.config_path}")
    print(f"data_dir: {result.data_dir}")
    for path in result.workspace_dirs:
        print(f"workspace dir: {path}")
    print(f"result database: {result.result_db_path}")
    print(f"asset database: {result.asset_db_path} ({result.asset_plan.strategy.value})")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


class _CliAssetInitializationSelector(AssetInitializationSelector):
    """CLI 的资产库初始化方式选择器：优先使用参数，否则交互询问。"""

    def __init__(
        self,
        *,
        manifest_path: Path | None,
        fetch_source: bool,
    ) -> None:
        self.manifest_path = manifest_path
        self.fetch_source = fetch_source

    def select(self) -> AssetInitializationPlan:
        if self.manifest_path is not None:
            return AssetInitializationPlan(
                AssetInitializationStrategy.FROM_MANIFEST,
                self.manifest_path,
            )
        if self.fetch_source:
            return AssetInitializationPlan(AssetInitializationStrategy.FETCH_SOURCE)
        return self._prompt()

    def _prompt(self) -> AssetInitializationPlan:
        print("选择资产库构建方式：")
        print("1) 通过 fetch-source 完全重新构建")
        print("2) 从 manifest 文件构建")
        choice = input("请输入 1 或 2：").strip()
        if choice == "1":
            return AssetInitializationPlan(AssetInitializationStrategy.FETCH_SOURCE)
        if choice == "2":
            manifest = input("请输入 manifest 文件路径：").strip()
            if not manifest:
                raise ValueError("manifest 路径不能为空")
            return AssetInitializationPlan(
                AssetInitializationStrategy.FROM_MANIFEST,
                Path(manifest),
            )
        raise ValueError(f"不支持的选项：{choice}")


def _cmd_project_show(args: argparse.Namespace) -> int:
    root = Path(args.root)
    application = _application(args)
    config = application.load_project(root)
    print(f"schema_version: {config.schema_version}")
    print(f"data_dir: {config.workspace.data_dir}")
    for key, path in sorted(application.workspace_paths(root).items()):
        print(f"{key}: {path}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    outcome = _application(args).run_file_and_wait(args.input_path)
    if outcome.session_id is None:
        message = outcome.error_message or outcome.error_code or "仿真任务未完成"
        raise RuntimeError(message)
    print(f"session_id: {outcome.session_id}")
    detail = _application(args).get_run(outcome.session_id)
    if detail.summary is not None:
        print(f"stop_reason: {detail.summary.stop_reason}")
        print(f"frames_run: {detail.summary.frames_run}")
    return 0


def _cmd_results_init(args: argparse.Namespace) -> int:
    path = _application(args).init_result_database(_resolve_result_db(args))
    print(f"initialized result database: {path}")
    return 0


def _cmd_results_list(args: argparse.Namespace) -> int:
    application = _application(args)
    for item in application.list_results(limit=args.limit, state=args.state):
        print(
            f"{item.session_id}	{item.created_at}	{item.state}	{item.name}	"
            f"{item.stop_reason}	{item.frames_run}	{item.event_count}"
        )
    return 0


def _cmd_results_inspect(args: argparse.Namespace) -> int:
    detail = _application(args).get_run(args.session_id)
    print(
        _to_json(
            {
                "session_id": detail.session_id,
                "state": detail.state,
                "created_at": detail.created_at,
                "summary": None if detail.summary is None else detail.summary.to_dict(),
                "event_count": len(detail.events),
                "events": [event.to_dict() for event in detail.events],
                "input_snapshot": detail.input_snapshot,
                "initial_snapshot": detail.initial_snapshot,
                "error_code": detail.error_code,
                "error_message": detail.error_message,
            }
        )
    )
    return 0


def _cmd_results_events(args: argparse.Namespace) -> int:
    application = _application(args)
    events = application.get_run_events(
        args.session_id,
        frame_min=args.frame_min,
        frame_max=args.frame_max,
        event_type=args.event_type,
        offset=args.offset,
        limit=args.limit,
    )
    for event in events:
        print(
            f"{event.frame}	{event.event_type}	"
            f"{json.dumps(event.data, ensure_ascii=False, sort_keys=True)}"
        )
    return 0


def _to_json(value: Any) -> str:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(cast(Any, value))
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _application(args: argparse.Namespace) -> ApplicationFacade:
    return create_cli_application(
        project_root=_project_root(args),
        asset_db_path=getattr(args, "asset_db", None),
        result_db_path=getattr(args, "result_db", None),
    )


def _configure_cli_logging(args: argparse.Namespace) -> None:
    debug = bool(getattr(args, "debug", False))
    explicit_level = _resolve_cli_log_level(args)
    file_path = _resolve_cli_log_file(args)
    console_level = logging.DEBUG if debug else explicit_level or logging.WARNING
    file_level = logging.DEBUG if debug else explicit_level or logging.INFO

    file_dir = None
    if _should_resolve_project_config(args):
        config = _load_project_config(args)
        if getattr(args, "result_db", None) is None:
            args._resolved_result_db = config.results_db(_project_root(args))
        if file_path is None:
            file_dir = config.logs_dir(_project_root(args))

    enabled_levels = [console_level]
    if file_path is not None or file_dir is not None:
        enabled_levels.append(file_level)

    configure_logging(
        LoggingSettings(
            level=_minimum_log_level(*enabled_levels),
            console_level=console_level,
            file_path=file_path,
            file_dir=file_dir,
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
        "result_db": getattr(args, "_resolved_result_db", None) or getattr(args, "result_db", None),
        "project_root": getattr(args, "root", None),
    }


def _should_resolve_project_config(args: argparse.Namespace) -> bool:
    if getattr(args, "handler", None) is None:
        return False
    return not (
        getattr(args, "command", None) == "project"
        and getattr(args, "project_command", None) == "init"
    )


def _load_project_config(args: argparse.Namespace) -> ProjectConfig:
    return _application(args).load_project(_project_root(args))


def _project_root(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd())


def _cli_command_name(args: argparse.Namespace) -> str:
    parts = [
        getattr(args, "command", None),
        getattr(args, "assets_command", None),
        getattr(args, "input_command", None),
        getattr(args, "project_command", None),
        getattr(args, "results_command", None),
    ]
    return ".".join(part for part in parts if part) or "help"


def _should_log_cli_failure(args: argparse.Namespace) -> bool:
    return _resolve_cli_log_level(args) is not None or _resolve_cli_log_file(args) is not None


if __name__ == "__main__":
    raise SystemExit(main())
