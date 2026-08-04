"""协调器对剧变来源属性的窄观察实现。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.attributes import (
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeQueryContext,
    AttributeResolver,
    AttributeSubjectRef,
)
from genshin_sim.core.elements import (
    ElementalSourceRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.systems.damage.level_multipliers import transformative_level_multiplier
from genshin_sim.core.systems.reaction import (
    CrystallizeSourceObservation,
    TransformativeSourceObservation,
)


@dataclass(frozen=True, slots=True)
class CharacterTransformativeSourceObserver:
    """只支持已确认的队伍角色来源。"""

    attribute_resolver: AttributeResolver

    def observe(
        self,
        *,
        frame: int,
        source_ref: ElementalSourceRef,
        owner_slot: int,
        source_level: int,
        observation_ref: str,
    ) -> TransformativeSourceObservation:
        if source_level > 90:
            raise ValueError("角色剧变来源等级不能超过 90")
        subject = AttributeSubjectRef.character(f"character:slot_{owner_slot}")
        mastery = self.attribute_resolver.resolve(
            AttributeQuery(
                subject_ref=subject,
                attribute_key=STAT_ELEMENTAL_MASTERY,
                frame=frame,
                context=AttributeQueryContext(),
            )
        ).final_value
        table_key, level_multiplier = transformative_level_multiplier(
            TransformativeReactionSourceKind.CHARACTER,
            source_level,
        )
        return TransformativeSourceObservation(
            source_ref=source_ref,
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=source_level,
            elemental_mastery=mastery,
            level_multiplier_table_key=table_key,
            level_multiplier=level_multiplier,
            source_observation_ref=observation_ref,
            source_owner_slot=owner_slot,
        )


@dataclass(frozen=True, slots=True)
class CharacterCrystallizeSourceObserver:
    """结晶只捕获角色等级与元素精通，不读取剧变等级系数。"""

    attribute_resolver: AttributeResolver

    def observe(
        self,
        *,
        frame: int,
        source_ref: ElementalSourceRef,
        owner_slot: int,
        source_level: int,
    ) -> CrystallizeSourceObservation:
        subject = AttributeSubjectRef.character(f"character:slot_{owner_slot}")
        mastery = self.attribute_resolver.resolve(
            AttributeQuery(
                subject_ref=subject,
                attribute_key=STAT_ELEMENTAL_MASTERY,
                frame=frame,
                context=AttributeQueryContext(),
            )
        ).final_value
        return CrystallizeSourceObservation(source_ref, source_level, mastery)
