"""server 请求级日志中间件测试。"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from fastapi.testclient import TestClient

from genshin_sim.application import ApplicationError, ApplicationFacade, WorkspaceInfo
from genshin_sim.infrastructure.logging import LogContextFilter
from genshin_sim.server import create_app

_REQUEST_LOGGING_LOGGER = "genshin_sim.server.request_logging"


class _RecordHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def _capture_records() -> Iterator[list[logging.LogRecord]]:
    """捕获请求日志中间件的记录，并按管理 handler 方式注入上下文字段。"""

    logger = logging.getLogger(_REQUEST_LOGGING_LOGGER)
    previous_level = logger.level
    recorder = _RecordHandler()
    recorder.addFilter(LogContextFilter())
    logger.setLevel(logging.INFO)
    logger.addHandler(recorder)
    try:
        yield recorder.records
    finally:
        logger.setLevel(previous_level)
        logger.removeHandler(recorder)


def _completion_records(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [record for record in records if record.getMessage() == "HTTP 请求完成"]


def test_request_completion_log_and_header_echo(application_facade) -> None:
    app = create_app(application_facade())

    with _capture_records() as records, TestClient(app) as client:
        response = client.get("/api/v1/workspace")

    assert response.status_code == 200
    request_id = response.headers["x-request-id"]
    assert request_id

    completions = _completion_records(records)
    assert len(completions) == 1
    record = completions[0]
    assert record.levelno == logging.INFO
    assert getattr(record, "status_code", None) == 200
    assert getattr(record, "request_id", None) == request_id
    assert getattr(record, "method", None) == "GET"
    assert getattr(record, "path", None) == "/api/v1/workspace"
    duration_ms = getattr(record, "duration_ms", None)
    assert isinstance(duration_ms, float)
    assert duration_ms >= 0


def test_request_id_reused_from_header(application_facade) -> None:
    app = create_app(application_facade())

    with _capture_records() as records, TestClient(app) as client:
        response = client.get("/api/v1/workspace", headers={"X-Request-ID": "req-42"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-42"
    completions = _completion_records(records)
    assert getattr(completions[0], "request_id", None) == "req-42"


def test_invalid_request_id_header_falls_back_to_generated(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.get("/api/v1/workspace", headers={"X-Request-ID": "x" * 200})

    assert response.status_code == 200
    # 超长请求头值被拒绝，回落为生成的 32 位 hex 标识。
    assert len(response.headers["x-request-id"]) == 32


def test_unhandled_exception_logged_once_with_stack_and_context() -> None:
    class _BoomFacade:
        def get_workspace(self) -> WorkspaceInfo:
            raise RuntimeError("boom")

    app = create_app(cast(ApplicationFacade, _BoomFacade()))

    with _capture_records() as records, TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/workspace")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"

    # 完整栈只记录一次，且带请求上下文；错误处理器不再重复记录。
    error_records = [record for record in records if record.levelno == logging.ERROR]
    assert len(error_records) == 1
    assert error_records[0].exc_info is not None
    assert error_records[0].getMessage() == "未处理的 HTTP 请求错误"

    completions = _completion_records(records)
    assert len(completions) == 1
    assert getattr(completions[0], "status_code", None) == 500
    assert getattr(completions[0], "request_id", None) == getattr(
        error_records[0], "request_id", None
    )


def test_application_error_response_flows_through_middleware() -> None:
    class _MissingFacade:
        def get_workspace(self) -> WorkspaceInfo:
            raise ApplicationError("not_found", "workspace missing")

    app = create_app(cast(ApplicationFacade, _MissingFacade()))

    with _capture_records() as records, TestClient(app) as client:
        response = client.get("/api/v1/workspace")

    assert response.status_code == 404
    # 已处理错误的响应仍经过中间件，回显 X-Request-ID。
    assert response.headers["x-request-id"]

    completions = _completion_records(records)
    assert len(completions) == 1
    assert getattr(completions[0], "status_code", None) == 404
    assert getattr(completions[0], "request_id", None) == response.headers["x-request-id"]
