"""结果查询 HTTP DTO。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunListItem(BaseModel):
    """历史运行列表项。"""

    session_id: str
    state: str
    name: str
    stop_reason: str
    end_frame: int
    frames_run: int
    created_at: str
    event_count: int


class RunListResponse(BaseModel):
    """历史运行列表。"""

    items: list[RunListItem]


class RunSummary(BaseModel):
    """运行摘要。"""

    stop_reason: str
    end_frame: int
    frames_run: int


class RunDetailResponse(BaseModel):
    """运行详情（不含事件流、初始快照与完整输入文档）。"""

    session_id: str
    state: str
    name: str
    summary: RunSummary | None
    error_code: str | None
    error_message: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    event_count: int


class MetricValue(BaseModel):
    """单个指标数值与口径说明。"""

    key: str
    value: float
    definition: str


class ShareValue(BaseModel):
    """按分组统计的占比指标。"""

    group: str
    value: float
    definition: str


class MetricsResponse(BaseModel):
    """摘要指标响应，与 DamageMetrics.to_dict() 一致。"""

    frames_run: int
    frames_per_second: int
    total_damage: MetricValue
    dps: MetricValue
    highest_hit: MetricValue
    average_hit: MetricValue
    damage_share_by_source: list[ShareValue]
    damage_share_by_kind: list[ShareValue]
    total_healing: MetricValue
    healing_share_by_source: list[ShareValue]


class EventItem(BaseModel):
    """单条事件。"""

    frame: int
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)


class EventPageResponse(BaseModel):
    """事件分页响应。"""

    items: list[EventItem]
    offset: int
    limit: int
    total: int
