"""Reaction Effect 的默认范围目标资格端口。"""

from __future__ import annotations

from genshin_sim.core.coordination.elemental_reaction.models import (
    ReactionTargetCapability,
    ReactionTargetEligibility,
    ReactionTargetRelation,
)
from genshin_sim.core.elements import ElementalSubjectRef


class DefaultReactionTargetEligibilityPort:
    """显式映射现有 scene target；不从空间标签或名称推断关系。"""

    def evaluate(self, context, *, entity, distance_xz: float) -> ReactionTargetEligibility:
        if context.space_runtime is None:
            raise RuntimeError("缺少 SpaceRuntime，无法读取 Reaction 目标资格")
        target = context.space_runtime.targets.get_by_spatial_entity_id(entity.entity_id)
        if target is not None:
            return ReactionTargetEligibility(
                subject_ref=ElementalSubjectRef.target(target.spatial_entity_id),
                spatial_entity_id=target.spatial_entity_id,
                distance_xz=distance_xz,
                relation=ReactionTargetRelation.HOSTILE,
                capabilities=frozenset(
                    {
                        ReactionTargetCapability.AURA,
                        ReactionTargetCapability.DAMAGE,
                        ReactionTargetCapability.ATTRIBUTE_STATUS,
                    }
                ),
            )
        capabilities = frozenset()
        if entity.kind.value == "active_character":
            subject_ref = ElementalSubjectRef.character(entity.entity_id)
            relation = ReactionTargetRelation.SELF
            capabilities = frozenset({ReactionTargetCapability.DAMAGE})
        elif entity.kind.value == "created_object":
            subject_ref = ElementalSubjectRef.created_object(entity.entity_id)
            relation = ReactionTargetRelation.NEUTRAL_OR_UNKNOWN
        else:
            subject_ref = ElementalSubjectRef.target(entity.entity_id)
            relation = ReactionTargetRelation.NEUTRAL_OR_UNKNOWN
        return ReactionTargetEligibility(
            subject_ref=subject_ref,
            spatial_entity_id=entity.entity_id,
            distance_xz=distance_xz,
            relation=relation,
            capabilities=capabilities,
            reason=(None if entity.kind.value == "active_character" else "unsupported_subject"),
        )
