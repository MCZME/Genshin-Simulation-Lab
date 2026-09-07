from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from typing import cast

from genshin_sim.core.systems.cooldown.enums import (
    CooldownDurationMode,
    CooldownDurationOperation,
    CooldownDurationStage,
)
from genshin_sim.core.systems.cooldown.errors import CooldownDurationResolutionError
from genshin_sim.core.systems.cooldown.models import (
    CooldownDefinition,
    CooldownDurationResolution,
    CooldownDurationTerm,
)
from genshin_sim.core.systems.cooldown.policies import STAGE_ORDER


class CooldownDurationResolver:
    """解析已经由外部领域确定的基础时长和修正项。"""

    def resolve(
        self,
        definition: CooldownDefinition,
        requested_base_duration_frames: int | None,
        terms: tuple[CooldownDurationTerm, ...],
    ) -> CooldownDurationResolution:
        if definition.duration_mode is CooldownDurationMode.FIXED:
            if requested_base_duration_frames is not None:
                raise CooldownDurationResolutionError("FIXED 冷却不能覆盖基础时长")
            base = definition.base_duration_frames
        else:
            if requested_base_duration_frames is None:
                raise CooldownDurationResolutionError("REQUEST_PROVIDED 冷却必须提供基础时长")
            base = requested_base_duration_frames

        seen: set[tuple[str, str]] = set()
        for term in terms:
            marker = (term.term_key, term.source_ref)
            if marker in seen:
                raise CooldownDurationResolutionError("重复的 duration term")
            seen.add(marker)

        current = Decimal(base)
        totals: list[tuple[CooldownDurationStage, Decimal]] = []
        completed: dict[CooldownDurationStage, Decimal] = {}
        normalized_terms = tuple(terms)
        for stage in STAGE_ORDER:
            for term in sorted(
                (item for item in normalized_terms if item.stage is stage), key=lambda x: x.sort_key
            ):
                value = cast(Decimal, term.value)
                if term.operation is CooldownDurationOperation.MULTIPLY_CURRENT:
                    current *= value
                elif term.operation is CooldownDurationOperation.ADD_REFERENCE_PERCENT:
                    assert term.reference_stage is not None
                    current += completed[term.reference_stage] * value
                else:
                    assert term.reference_stage is not None
                    current -= completed[term.reference_stage] * value
            completed[stage] = current
            totals.append((stage, current))

        truncated = max(Decimal(0), current)
        rounded = int(truncated.to_integral_value(rounding=ROUND_CEILING))
        return CooldownDurationResolution(
            base_duration_frames=base,
            resolved_duration_frames=rounded,
            terms=tuple(
                sorted(
                    normalized_terms,
                    key=lambda item: (STAGE_ORDER.index(item.stage), item.sort_key),
                )
            ),
            stage_totals=tuple(totals),
            rounded_from=None if truncated == Decimal(rounded) else truncated,
            source_refs=tuple(
                sorted({definition.source_ref, *(term.source_ref for term in terms)})
            ),
        )
