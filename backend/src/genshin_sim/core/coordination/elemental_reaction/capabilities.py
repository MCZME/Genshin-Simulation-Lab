"""Reaction 队伍 capability 的中立证据模型。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.elements import ElementalSubjectKind, ElementalSubjectRef

REACTION_CAPABILITY_PREFIX = "reaction_capability:"


def validate_reaction_capability_key(value: str, name: str = "capability_key") -> None:
    if (
        not isinstance(value, str)
        or not value.startswith(REACTION_CAPABILITY_PREFIX)
        or not value[len(REACTION_CAPABILITY_PREFIX) :].strip()
    ):
        raise ValueError(f"{name} 必须是以 {REACTION_CAPABILITY_PREFIX!r} 开头的非空字符串")


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


@dataclass(frozen=True, slots=True)
class ReactionCapabilityEvidence:
    """一次队伍 capability 的提供者证据。"""

    capability_key: str
    provider_ref: ElementalSubjectRef

    def __post_init__(self) -> None:
        validate_reaction_capability_key(self.capability_key)
        if not isinstance(self.provider_ref, ElementalSubjectRef):
            raise ValueError("provider_ref 必须是 ElementalSubjectRef")
        if self.provider_ref.kind is not ElementalSubjectKind.CHARACTER:
            raise ValueError("Reaction capability provider_ref 必须是角色主体")

    def to_dict(self) -> dict[str, object]:
        return {
            "capability_key": self.capability_key,
            "provider_ref": {
                "kind": self.provider_ref.kind.value,
                "entity_id": self.provider_ref.entity_id,
            },
        }


@dataclass(frozen=True, slots=True)
class ReactionEligibilityView:
    """同一帧、同一队伍的不可变 capability 准入观察。"""

    team_ref: str
    frame: int
    evidence: tuple[ReactionCapabilityEvidence, ...] = ()

    def __post_init__(self) -> None:
        _text(self.team_ref, "team_ref")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        evidence = tuple(self.evidence)
        if any(not isinstance(item, ReactionCapabilityEvidence) for item in evidence):
            raise ValueError("evidence 必须是 ReactionCapabilityEvidence 序列")
        ordered = tuple(
            sorted(
                evidence,
                key=lambda item: (item.capability_key, item.provider_ref.entity_id),
            )
        )
        identities = tuple((item.capability_key, item.provider_ref) for item in ordered)
        if len(set(identities)) != len(identities):
            raise ValueError("同一 capability 不能由同一角色重复提供")
        object.__setattr__(self, "evidence", ordered)

    def has(self, capability_key: str) -> bool:
        validate_reaction_capability_key(capability_key)
        return any(item.capability_key == capability_key for item in self.evidence)

    def providers_for(self, capability_key: str) -> tuple[ElementalSubjectRef, ...]:
        validate_reaction_capability_key(capability_key)
        return tuple(
            item.provider_ref for item in self.evidence if item.capability_key == capability_key
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "team_ref": self.team_ref,
            "frame": self.frame,
            "evidence": [item.to_dict() for item in self.evidence],
        }
