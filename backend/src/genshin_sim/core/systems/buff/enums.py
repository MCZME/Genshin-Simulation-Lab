from __future__ import annotations

from enum import StrEnum


class BuffLifecycleState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REMOVED = "removed"


class BuffApplicationPolicy(StrEnum):
    REPLACE = "replace"
    REFRESH = "refresh"
    STACK_REFRESH = "stack_refresh"
    COEXIST = "coexist"


class BuffApplicationOutcome(StrEnum):
    CREATED = "created"
    REPLACED = "replaced"
    REFRESHED = "refreshed"
    STACKED = "stacked"
    STACK_CAPPED_REFRESHED = "stack_capped_refreshed"


class BuffRemovalReason(StrEnum):
    EXPIRED = "expired"
    REPLACED = "replaced"
    DISPELLED = "dispelled"
    CONSUMED = "consumed"
    EXPLICIT = "explicit"


class BuffValueRefreshPolicy(StrEnum):
    KEEP_INITIAL = "keep_initial"
    REPLACE_LATEST = "replace_latest"


class BuffStackScaling(StrEnum):
    CONSTANT = "constant"
    LINEAR = "linear"
