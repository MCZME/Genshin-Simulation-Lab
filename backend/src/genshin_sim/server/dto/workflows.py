"""工作流存档 HTTP DTO。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WorkflowCreateRequest(BaseModel):
    """创建工作流请求；name 缺省时使用默认名称。"""

    name: str | None = None


class WorkflowListItem(BaseModel):
    """工作流列表项，不携带完整定义。"""

    id: str
    name: str
    updated_at: str


class WorkflowListResponse(BaseModel):
    """工作流存档列表。"""

    items: list[WorkflowListItem]


class WorkflowResponse(BaseModel):
    """工作流创建/读取/保存响应。"""

    id: str
    name: str
    updated_at: str
    definition: dict[str, Any]
