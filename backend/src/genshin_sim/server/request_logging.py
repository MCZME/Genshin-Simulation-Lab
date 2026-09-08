"""HTTP 请求级日志上下文与完成日志。"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import MutableMapping
from typing import Any

from starlette.datastructures import MutableHeaders

from genshin_sim.infrastructure.logging import logging_context

logger = logging.getLogger(__name__)

_REQUEST_ID_HEADER = b"x-request-id"
_REQUEST_ID_HEADER_NAME = "X-Request-ID"
_MAX_REQUEST_ID_LENGTH = 128


class RequestLoggingMiddleware:
    """为每个 HTTP 请求注入日志上下文并记录完成日志。

    纯 ASGI 中间件：请求处理路径上的所有日志自动携带
    request_id/method/path；响应头回显 X-Request-ID；未处理异常在
    请求上下文仍激活时记录完整栈，之后按既有错误模型继续传播，
    500 响应仍由外层统一错误处理器生成。
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(scope)
        started = time.perf_counter()
        status_code = 500  # 响应未开始即失败时的兜底值

        async def send_wrapper(message: Any) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append(_REQUEST_ID_HEADER_NAME, request_id)
            await send(message)

        with logging_context(
            request_id=request_id,
            method=scope["method"],
            path=scope["path"],
        ):
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                # 未处理异常的唯一完整栈记录点；外层错误处理器不再重复记录。
                logger.exception("未处理的 HTTP 请求错误")
                raise
            finally:
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                logger.info(
                    "HTTP 请求完成",
                    extra={"status_code": status_code, "duration_ms": duration_ms},
                )


def _resolve_request_id(scope: MutableMapping[str, Any]) -> str:
    """优先复用请求头 X-Request-ID，缺失或非法时生成。"""

    for name, value in scope.get("headers") or ():
        if name == _REQUEST_ID_HEADER:
            candidate = value.decode("latin-1").strip()
            if candidate and len(candidate) <= _MAX_REQUEST_ID_LENGTH:
                return candidate
            break
    return uuid.uuid4().hex
