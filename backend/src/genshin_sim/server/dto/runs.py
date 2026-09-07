"""批次运行 HTTP DTO。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from genshin_sim.application import BatchMemberState, BatchRunState
from genshin_sim.server.dto.inputs import InputMemberRequest


class RunMemberStatus(BaseModel):
    """批次状态视图中的成员记录。"""

    item_id: str
    state: BatchMemberState
    session_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class RunStatusResponse(BaseModel):
    """批次状态视图；成员顺序与提交顺序一致。"""

    run_id: str
    name: str
    state: BatchRunState
    concurrency: int
    cancel_requested: bool
    member_count: int
    members: list[RunMemberStatus]


class SubmitRunRequest(BaseModel):
    """POST /api/v1/runs 请求体。"""

    name: str = ""
    concurrency: int | None = Field(default=None, ge=1, le=16)
    members: list[InputMemberRequest] = Field(min_length=1)
