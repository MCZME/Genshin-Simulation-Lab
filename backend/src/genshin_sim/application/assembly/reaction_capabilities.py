"""从内容单元组装静态 Reaction capability 证据。"""

from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.core.coordination.elemental_reaction.capabilities import (
    ReactionCapabilityEvidence,
    ReactionEligibilityView,
)
from genshin_sim.core.elements import ElementalSubjectRef


class StaticReactionEligibilityPort:
    """当前阶段只读的装配期 capability 端口。"""

    def __init__(self, evidence: Iterable[ReactionCapabilityEvidence]) -> None:
        try:
            self._evidence = ReactionEligibilityView(
                team_ref="team:assembly",
                frame=0,
                evidence=tuple(evidence),
            ).evidence
        except ValueError as exc:
            raise InvalidRuntimePayloadError(f"Reaction capability 证据非法：{exc}") from exc

    @property
    def evidence(self) -> tuple[ReactionCapabilityEvidence, ...]:
        return self._evidence

    def evidence_for(self, frame: int, team_ref: str) -> ReactionEligibilityView:
        return ReactionEligibilityView(
            team_ref=team_ref,
            frame=frame,
            evidence=self._evidence,
        )


def build_static_reaction_eligibility_port(
    content_units: Iterable[ContentUnit],
) -> StaticReactionEligibilityPort:
    evidence: list[ReactionCapabilityEvidence] = []
    for unit in content_units:
        if not unit.reaction_capabilities:
            continue
        if unit.owner_type is not ContentUnitOwnerType.CHARACTER or unit.slot is None:
            raise InvalidRuntimePayloadError(
                f"{unit.handler_key} 的 Reaction capability 必须来自带 slot 的角色 content"
            )
        if unit.slot <= 0:
            raise InvalidRuntimePayloadError(f"{unit.handler_key} 的角色 slot 必须是正整数")
        provider_ref = ElementalSubjectRef.character(f"character:slot_{unit.slot}")
        evidence.extend(
            ReactionCapabilityEvidence(capability_key, provider_ref)
            for capability_key in unit.reaction_capabilities
        )
    return StaticReactionEligibilityPort(evidence)
