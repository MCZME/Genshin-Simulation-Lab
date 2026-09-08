"""HTTP 服务启动入口。"""

from __future__ import annotations

from pathlib import Path

import uvicorn

from genshin_sim.application import create_server_application, resolve_logs_dir
from genshin_sim.infrastructure.logging import LoggingSettings, configure_logging
from genshin_sim.server import create_app

SERVER_LOG_FILE_NAME = "server.jsonl"


def run_server(
    *,
    project_root: str | Path,
    asset_db_path: str | Path | None = None,
    result_db_path: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """组装进程执行的应用并启动同源 HTTP 服务。"""

    _configure_server_logging(project_root)
    application = create_server_application(
        project_root=project_root,
        asset_db_path=asset_db_path,
        result_db_path=result_db_path,
    )
    app = create_app(application)
    uvicorn.run(app, host=host, port=port)


def _configure_server_logging(project_root: str | Path) -> None:
    """server 常驻进程日志：单文件大小轮转，写入项目 logs 目录。"""

    configure_logging(
        LoggingSettings(file_path=resolve_logs_dir(project_root) / SERVER_LOG_FILE_NAME)
    )


def main(argv: list[str] | None = None) -> int:
    """为打包入口保留的 server 启动命令。"""

    import argparse

    parser = argparse.ArgumentParser(prog="genshin-sim-server")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--db", dest="asset_db", type=Path, default=None)
    parser.add_argument("--results-db", dest="result_db", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    run_server(
        project_root=args.root,
        asset_db_path=args.asset_db,
        result_db_path=args.result_db,
        host=args.host,
        port=args.port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
