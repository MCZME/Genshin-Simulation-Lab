"""HTTP 统一错误映射。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from genshin_sim.application import ApplicationError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """注册统一错误响应，避免把内部异常结构直接暴露给前端。"""

    @app.exception_handler(ApplicationError)
    async def _handle_application_error(
        request: Request,
        exc: ApplicationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": list(exc.details),
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
