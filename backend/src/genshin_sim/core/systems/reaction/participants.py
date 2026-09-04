"""Reaction occurrence 的角色参与者快照。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from genshin_sim.core.elements import AuraKind, ElementalSourceRef
from genshin_sim.core.systems.aura import AuraView


@dataclass(frozen=True, slots=True)
class ReactionParticipantSnapshot:
    """一次 Reaction occurrence 使用的角色来源集合。"""

    participant_refs: tuple[ElementalSourceRef, ...] = ()

    def __post_init__(self) -> None:
        refs = tuple(self.participant_refs)
        if any(not isinstance(item, ElementalSourceRef) for item in refs):
            raise ValueError("participant_refs 必须是 ElementalSourceRef 序列")
        object.__setattr__(self, "participant_refs", tuple(sorted(set(refs))))

    def to_dict(self) -> dict[str, object]:
        return {"participant_refs": [item.to_dict() for item in self.participant_refs]}


def freeze_character_participants(
    observed_aura: AuraView,
    *,
    used_aura_kinds: Iterable[AuraKind],
    character_source_refs: Iterable[ElementalSourceRef],
    triggering_source_ref: ElementalSourceRef | None = None,
) -> ReactionParticipantSnapshot:
    """从消费前 Aura 观察和当前触发来源冻结角色参与者。"""

    if not isinstance(observed_aura, AuraView):
        raise ValueError("observed_aura 必须是 AuraView")
    aura_kinds = tuple(used_aura_kinds)
    if any(not isinstance(item, AuraKind) for item in aura_kinds):
        raise ValueError("used_aura_kinds 必须是 AuraKind 序列")
    character_refs = tuple(character_source_refs)
    if any(not isinstance(item, ElementalSourceRef) for item in character_refs):
        raise ValueError("character_source_refs 必须是 ElementalSourceRef 序列")
    character_source_keys = {item.source_key for item in character_refs}
    if triggering_source_ref is not None and not isinstance(
        triggering_source_ref,
        ElementalSourceRef,
    ):
        raise ValueError("triggering_source_ref 必须是 ElementalSourceRef 或 None")

    participants = {
        ElementalSourceRef(contribution.contributor_ref.source_key)
        for component in observed_aura.components
        if component.aura_kind in set(aura_kinds)
        for contribution in component.contributions
        if not contribution.remaining_amount.is_zero
        and contribution.contributor_ref.source_key in character_source_keys
    }
    if (
        triggering_source_ref is not None
        and triggering_source_ref.source_key in character_source_keys
    ):
        participants.add(ElementalSourceRef(triggering_source_ref.source_key))
    return ReactionParticipantSnapshot(tuple(participants))


def freeze_aura_character_participants(
    observed_aura: AuraView,
    *,
    used_aura_kinds: Iterable[AuraKind],
) -> ReactionParticipantSnapshot:
    """从 Aura 贡献账本直接冻结角色参与者，供雷暴云攻击等周期结算使用。"""

    if not isinstance(observed_aura, AuraView):
        raise ValueError("observed_aura 必须是 AuraView")
    aura_kinds = frozenset(used_aura_kinds)
    if any(not isinstance(item, AuraKind) for item in aura_kinds):
        raise ValueError("used_aura_kinds 必须是 AuraKind 集合")
    participants = {
        ElementalSourceRef(contribution.contributor_ref.source_key)
        for component in observed_aura.components
        if component.aura_kind in aura_kinds
        for contribution in component.contributions
        if not contribution.remaining_amount.is_zero
        and contribution.contributor_ref.source_key.startswith("character:")
    }
    return ReactionParticipantSnapshot(tuple(participants))
