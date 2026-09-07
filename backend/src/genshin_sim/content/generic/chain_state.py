"""generic 连段宿主状态 schema。

角色动作解释器用 ``chain_last_action_key`` / ``chain_last_start_frame`` 记录
上次启动的动作与起始帧；写入统一经 ``state_patch`` 意图提交。
"""

from __future__ import annotations

from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)

CHAIN_STATE_LAST_ACTION_KEY = "chain_last_action_key"
CHAIN_STATE_LAST_START_FRAME = "chain_last_start_frame"


def chain_state_schema(owner_ref: str) -> StateSchema:
    """构造连段宿主状态 schema（generic 形状，owner 由内容包传入）。"""

    return StateSchema(
        owner_ref=owner_ref,
        fields=(
            StateField(
                name=CHAIN_STATE_LAST_ACTION_KEY,
                field_type=StateFieldType.STRING,
                default="",
            ),
            StateField(
                name=CHAIN_STATE_LAST_START_FRAME,
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
            ),
        ),
    )
