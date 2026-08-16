from __future__ import annotations

from enum import StrEnum


class InfusionMode(StrEnum):
    """附魔模式：可覆盖武器附魔与不可覆盖元素转化。"""

    INFUSION = "infusion"
    CONVERSION = "conversion"


class RefreshPolicy(StrEnum):
    """来源挂载策略。"""

    ONCE = "once"
    PERIODIC = "periodic"


class InfusionLifecycleState(StrEnum):
    """来源记录生命周期状态。"""

    ACTIVE = "active"
    EXPIRED = "expired"
    REMOVED = "removed"


class InfusionApplicationOutcome(StrEnum):
    """一次施加的结果类型。"""

    CREATED = "created"
    REFRESHED = "refreshed"
    REPLACED = "replaced"


class InfusionRemovalReason(StrEnum):
    """来源离开活动状态的原因。"""

    EXPIRED = "expired"
    REPLACED = "replaced"
    DISPELLED = "dispelled"
    CONSUMED = "consumed"
    EXPLICIT = "explicit"


class EffectiveElementReason(StrEnum):
    """最终元素解析原因码。"""

    NO_ACTIVE_SOURCE = "no_active_source"
    CONVERSION = "conversion"
    SINGLE_SOURCE = "single_source"
    CONSUMED = "consumed"
    FREEZE = "freeze"
    ELECTRO_CHARGED = "electro_charged"
