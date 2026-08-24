"""分析模板 HTTP DTO。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TemplateColumnDto(BaseModel):
    name: str
    type: str


class TemplateParamDto(BaseModel):
    name: str
    type: str
    required: bool
    binding: list[str]


class TemplateRelationDto(BaseModel):
    name: str
    columns: list[str]
    required: bool


class TemplateOutputDto(BaseModel):
    columns: list[TemplateColumnDto]


class TemplateDeclarationDto(BaseModel):
    template_id: str
    display_name: str
    params: list[TemplateParamDto]
    relations: list[TemplateRelationDto]
    output: TemplateOutputDto


class TemplateListResponse(BaseModel):
    items: list[TemplateDeclarationDto]


class RelationPayload(BaseModel):
    columns: list[str]
    rows: list[list[Any]]


class ExecuteTemplateRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    relations: dict[str, RelationPayload] = Field(default_factory=dict)


class TemplateResultResponse(BaseModel):
    columns: list[TemplateColumnDto]
    rows: list[list[Any]]
    truncated: bool
