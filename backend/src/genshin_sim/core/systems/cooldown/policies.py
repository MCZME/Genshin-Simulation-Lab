from genshin_sim.core.systems.cooldown.enums import (
    CooldownDurationOperation,
    CooldownDurationStage,
)
from genshin_sim.core.systems.cooldown.errors import CooldownDurationResolutionError

STAGE_ORDER = (
    CooldownDurationStage.BASE,
    CooldownDurationStage.OWNER_ADJUSTMENT,
    CooldownDurationStage.DURATION_INCREASE,
    CooldownDurationStage.EXTERNAL_ADJUSTMENT,
    CooldownDurationStage.FINALIZE,
)


def validate_term_policy(
    stage: CooldownDurationStage,
    operation: CooldownDurationOperation,
    reference_stage: CooldownDurationStage | None,
) -> None:
    if operation is CooldownDurationOperation.MULTIPLY_CURRENT:
        if reference_stage is not None:
            raise CooldownDurationResolutionError("MULTIPLY_CURRENT 不能提供 reference_stage")
        return
    if reference_stage is None:
        raise CooldownDurationResolutionError("百分比操作必须提供 reference_stage")
    if STAGE_ORDER.index(reference_stage) >= STAGE_ORDER.index(stage):
        raise CooldownDurationResolutionError("reference_stage 必须早于当前阶段")
