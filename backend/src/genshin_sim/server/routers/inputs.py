"""输入校验 HTTP 路由。"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request

from genshin_sim.application import (
    ApplicationFacade,
    BatchDiagnostic,
    BatchMember,
    BatchMemberValidation,
    BatchValidationResult,
)
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.common import Diagnostic
from genshin_sim.server.dto.inputs import (
    MemberValidationResponse,
    ValidateInputsRequest,
    ValidateInputsResponse,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["inputs"],
    dependencies=[Depends(require_initialized)],
)


@router.post("/inputs/validate", response_model=ValidateInputsResponse)
def validate_inputs(
    request: Request,
    payload: ValidateInputsRequest,
) -> ValidateInputsResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    result = facade.validate_batch_inputs(
        tuple(BatchMember(item_id=member.item_id, input=member.input) for member in payload.members)
    )
    return _validation_to_dto(result)


def _validation_to_dto(result: BatchValidationResult) -> ValidateInputsResponse:
    return ValidateInputsResponse(
        ok=result.ok,
        members=[_member_to_dto(member) for member in result.members],
    )


def _member_to_dto(member: BatchMemberValidation) -> MemberValidationResponse:
    return MemberValidationResponse(
        item_id=member.item_id,
        ok=member.ok,
        details=[_diagnostic_to_dto(detail) for detail in member.details],
    )


def _diagnostic_to_dto(detail: BatchDiagnostic) -> Diagnostic:
    return Diagnostic(
        severity=detail.severity,
        code=detail.code,
        message=detail.message,
        item_id=detail.item_id,
        path=detail.path,
    )
