"""仿真上下文、时钟、模拟器和运行结果模型。"""

from genshin_sim.core.protocols import (
    FrameUpdatable,
    RuntimeWorld,
)
from genshin_sim.core.simulation.clock import FrameClock
from genshin_sim.core.simulation.context import (
    SimulationContext,
    get_context,
)
from genshin_sim.core.simulation.input import (
    SUPPORTED_INPUT_KEYS,
    InputSessionBoundary,
    InputSessionPlan,
    InputSessionTrace,
    InputTraceCompiler,
    InputTraceError,
    KeyEvent,
    KeyInputFrame,
    KeyPhase,
)
from genshin_sim.core.simulation.intent_queue import (
    DuplicateIntentError,
    IntentQueue,
    IntentQueueError,
)
from genshin_sim.core.simulation.pipeline import (
    DuplicatePhaseHandlerError,
    FramePipeline,
    FramePipelineError,
    FramePipelineRoundLimitError,
    PhaseHandlerBinding,
)
from genshin_sim.core.simulation.settlement import (
    DuplicateIntentHandlerError,
    FrameZeroIntentError,
    IntentKindHandler,
    IntentSettlementError,
    IntentSettlementRecord,
    IntentSettlementRuntime,
)
from genshin_sim.core.simulation.simulator import (
    SimulationResult,
    SimulationStopReason,
    Simulator,
)
from genshin_sim.core.simulation.team import (
    TeamRuntimeState,
    TeamSwitchResult,
    TeamSwitchStatus,
)
from genshin_sim.core.simulation.world import BasicRuntimeWorld

__all__ = [
    "SUPPORTED_INPUT_KEYS",
    "BasicRuntimeWorld",
    "DuplicateIntentError",
    "DuplicateIntentHandlerError",
    "DuplicatePhaseHandlerError",
    "FrameUpdatable",
    "FrameClock",
    "FramePipeline",
    "FramePipelineError",
    "FramePipelineRoundLimitError",
    "FrameZeroIntentError",
    "IntentKindHandler",
    "IntentQueue",
    "IntentQueueError",
    "IntentSettlementError",
    "IntentSettlementRecord",
    "IntentSettlementRuntime",
    "InputTraceError",
    "InputSessionBoundary",
    "InputSessionPlan",
    "InputSessionTrace",
    "InputTraceCompiler",
    "KeyInputFrame",
    "KeyEvent",
    "KeyPhase",
    "PhaseHandlerBinding",
    "RuntimeWorld",
    "SimulationContext",
    "SimulationResult",
    "SimulationStopReason",
    "Simulator",
    "TeamRuntimeState",
    "TeamSwitchResult",
    "TeamSwitchStatus",
    "get_context",
]
