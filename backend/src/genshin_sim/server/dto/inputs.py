"""输入校验 HTTP DTO。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from genshin_sim.server.dto.common import Diagnostic


class InputMemberRequest(BaseModel):
    """一个已展开成员：稳定 item_id + 完整 SimulationInput 文档。"""

    item_id: str = Field(min_length=1)
    input: dict[str, Any]


class ValidateInputsRequest(BaseModel):
    """POST /api/v1/inputs/validate 请求体。"""

    members: list[InputMemberRequest] = Field(min_length=1)


class MemberValidationResponse(BaseModel):
    """单个成员的校验结果。"""

    item_id: str
    ok: bool
    details: list[Diagnostic] = Field(default_factory=list)


class ValidateInputsResponse(BaseModel):
    """输入校验响应；顶层 ok 为全部成员通过。"""

    ok: bool
    members: list[MemberValidationResponse]
