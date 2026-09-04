"""运行期共享契约：帧阶段、统一意图、JSON 兼容值与状态 schema。"""

from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.json import JSONValue, validate_json_compatible
from genshin_sim.core.contracts.phases import (
    MAX_SETTLEMENT_ROUNDS,
    PHASE_ORDER,
    SETTLEMENT_STAGE_ORDER,
    FramePhase,
    MountPoint,
    SettlementStage,
)
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
    StateSchemaConflictError,
    StateSchemaError,
    StateSchemaFragment,
    StateSchemaValidationError,
    merge_state_schema_fragments,
)

__all__ = [
    "FramePhase",
    "IntentEnvelope",
    "IntentKind",
    "JSONValue",
    "MAX_SETTLEMENT_ROUNDS",
    "MountPoint",
    "PHASE_ORDER",
    "SETTLEMENT_STAGE_ORDER",
    "SettlementStage",
    "StateField",
    "StateFieldType",
    "StateSchema",
    "StateSchemaConflictError",
    "StateSchemaError",
    "StateSchemaFragment",
    "StateSchemaValidationError",
    "merge_state_schema_fragments",
    "validate_json_compatible",
]
