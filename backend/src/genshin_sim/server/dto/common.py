"""HTTP 公共 DTO。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Diagnostic(BaseModel):
    """面向输入的诊断项；item_id/path 可空。"""

    severity: str = "error"
    code: str
    message: str
    item_id: str | None = None
    path: str | None = None


class ErrorResponse(BaseModel):
    """统一错误响应。"""

    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)
