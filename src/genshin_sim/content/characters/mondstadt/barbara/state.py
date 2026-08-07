from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara.constants import (
    BARBARA_STATE_LAST_ACTION_KEY,
    BARBARA_STATE_LAST_START_FRAME,
)
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)


def barbara_state_schema(owner_ref: str) -> StateSchema:
    """芭芭拉动作状态机的宿主状态 schema。"""

    return StateSchema(
        owner_ref=owner_ref,
        fields=(
            StateField(
                name=BARBARA_STATE_LAST_ACTION_KEY,
                field_type=StateFieldType.STRING,
                default="",
            ),
            StateField(
                name=BARBARA_STATE_LAST_START_FRAME,
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
            ),
        ),
    )
