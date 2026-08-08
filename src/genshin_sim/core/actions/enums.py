"""动作领域枚举。"""

from __future__ import annotations

from enum import StrEnum


class ActionOwnerKind(StrEnum):
    TEAM = "team"
    CHARACTER = "character"


class InputPhysicalState(StrEnum):
    HELD = "held"
    RELEASED = "released"


class InputControlState(StrEnum):
    LISTENING = "listening"
    DETACHED = "detached"
    CANCELED = "canceled"


class ActionInterpretationTrigger(StrEnum):
    PRESS = "press"
    HOLD = "hold"
    RELEASE = "release"
    CANCEL = "cancel"


class ActionInterpretationKind(StrEnum):
    WAIT = "wait"
    REJECT = "reject"
    START_ACTION = "start_action"
    CONTROL_ACTION = "control_action"


class InputSessionPolicy(StrEnum):
    KEEP_LISTENING = "keep_listening"
    DETACH = "detach"
    CANCEL = "cancel"


class ActionLifecycle(StrEnum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELED = "canceled"


class ActionLifecycleDirective(StrEnum):
    CONTINUE = "continue"
    FINISH = "finish"
    CANCEL = "cancel"


class ActionDecisionRejectReason(StrEnum):
    INVALID_START_FRAME = "invalid_start_frame"
    INVALID_OWNER = "invalid_owner"
    SESSION_NOT_ACTIVE = "session_not_active"
    SESSION_ALREADY_BOUND = "session_already_bound"
    LOCK_CONFLICT = "lock_conflict"
    INTERRUPT_NOT_ALLOWED = "interrupt_not_allowed"
    INSTANCE_NOT_FOUND = "instance_not_found"
    INVALID_COMMAND = "invalid_command"
    UNSUPPORTED_ACTION = "unsupported_action"


class SnapshotPolicy(StrEnum):
    RESOLVE_ON_IMPACT = "resolve_on_impact"
    SNAPSHOT_ON_EMIT = "snapshot_on_emit"