"""结果查询 HTTP DTO。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class EventItem(BaseModel):
    """单条事件。"""

    ordinal: int
    frame: int
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)


class EventPageResponse(BaseModel):
    """事件分页响应。"""

    items: list[EventItem]
    offset: int
    limit: int
    total: int


class DamageEventView(BaseModel):
    """DAMAGE_RESOLVED 的规范化伤害视图。"""

    summary: dict[str, Any]
    audit: Any = None


class EventDetailResponse(BaseModel):
    """单条事件详情。"""

    session_id: str
    ordinal: int
    frame: int
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    damage: DamageEventView | None = None


class FrameTeamCharacter(BaseModel):
    """帧状态中的队伍角色身份。"""

    slot: int
    character_key: str
    combat_entity_id: str


class FrameTeam(BaseModel):
    """帧状态中的队伍身份与场上角色。"""

    active_slot: int | None
    slots: list[int]
    characters: list[FrameTeamCharacter]


class FrameHealth(BaseModel):
    """帧状态中的角色生命。"""

    current_hp: float
    max_hp: float | None = None
    hp_ratio: float | None = None


class FrameEnergy(BaseModel):
    """帧状态中的角色能量。"""

    current_energy: float
    capacity: float | None = None
    burst_ready: bool = False


class FrameCharacterState(BaseModel):
    """帧状态中的单个角色状态。"""

    slot: int
    character_key: str
    combat_entity_id: str
    active: bool
    health: FrameHealth
    energy: FrameEnergy
    attributes: dict[str, Any] = Field(default_factory=dict)
    buffs: list[dict[str, Any]] = Field(default_factory=list)
    shields: list[dict[str, Any]] = Field(default_factory=list)
    infusion: list[dict[str, Any]] = Field(default_factory=list)
    cooldowns: list[dict[str, Any]] = Field(default_factory=list)
    content_states: list[dict[str, Any]] = Field(default_factory=list)


class FrameCoverage(BaseModel):
    """帧状态逐组折叠标注。"""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    characters_health: str = Field(alias="characters.health")
    characters_energy: str = Field(alias="characters.energy")
    characters_attributes: str = Field(alias="characters.attributes")
    characters_buffs: str = Field(alias="characters.buffs")
    characters_shields: str = Field(alias="characters.shields")
    characters_infusion: str = Field(alias="characters.infusion")
    characters_cooldowns: str = Field(alias="characters.cooldowns")
    characters_content_states: str = Field(alias="characters.content_states")
    aura: str
    aura_icd: str
    reaction: str
    space: str


class FrameStateResponse(BaseModel):
    """指定帧的帧末角色状态。"""

    session_id: str
    frame: int
    time_seconds: float
    team: FrameTeam
    characters: list[FrameCharacterState]
    resonance: dict[str, Any] = Field(default_factory=dict)
    moonsign: dict[str, Any] = Field(default_factory=dict)
    coverage: FrameCoverage
