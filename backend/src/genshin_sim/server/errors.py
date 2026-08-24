"""HTTP 统一错误映射。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from genshin_sim.application import ApplicationError

logger = logging.getLogger(__name__)

_NOT_FOUND_CODES = {"not_found"}
_CONFLICT_CODES = {"workspace_not_initialized", "already_exists"}
_VALIDATION_CODES = {
    "validation_failed",
    "batch_empty",
    "batch_too_large",
    "duplicate_item_id",
    "invalid_members",
    "invalid_member",
    "invalid_item_id",
    "invalid_concurrency",
}


def register_error_handlers(app: FastAPI) -> None:
    """注册统一错误响应，避免把内部异常结构直接暴露给前端。"""

    @app.exception_handler(ApplicationError)
    async def _handle_application_error(
        request: Request,
        exc: ApplicationError,
    ) -> JSONResponse:
        status_code = _status_for_application_error(exc)
        return JSONResponse(
            status_code=status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": list(exc.details),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "code": "validation_failed",
                "message": "请求字段校验失败",
                "details": [_validation_detail(error) for error in exc.errors()],
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理的 HTTP 请求错误", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "internal server error",
                "details": [],
            },
        )


def _status_for_application_error(exc: ApplicationError) -> int:
    if exc.code in _NOT_FOUND_CODES:
        return 404
    if exc.code in _CONFLICT_CODES:
        return 409
    if exc.code in _VALIDATION_CODES:
        return 400
    return 500


def _validation_detail(error: dict[str, Any]) -> dict[str, Any]:
    location = tuple(
        str(part)
        for part in error.get("loc", ())
        if part not in {"body", "query", "path", "header"}
    )
    return {
        "severity": "error",
        "code": str(error.get("type", "request_invalid")),
        "message": str(error.get("msg", "请求字段无效")),
        "item_id": None,
        "path": ".".join(location) if location else None,
    }
