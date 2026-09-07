from enum import StrEnum


class CooldownSubjectType(StrEnum):
    CHARACTER = "character"


class AbilityKind(StrEnum):
    ELEMENTAL_SKILL = "elemental_skill"
    ELEMENTAL_BURST = "elemental_burst"


class CooldownDurationMode(StrEnum):
    FIXED = "fixed"
    REQUEST_PROVIDED = "request_provided"


class CooldownDurationStage(StrEnum):
    BASE = "base"
    OWNER_ADJUSTMENT = "owner_adjustment"
    DURATION_INCREASE = "duration_increase"
    EXTERNAL_ADJUSTMENT = "external_adjustment"
    FINALIZE = "finalize"


class CooldownDurationOperation(StrEnum):
    MULTIPLY_CURRENT = "multiply_current"
    ADD_REFERENCE_PERCENT = "add_reference_percent"
    SUBTRACT_REFERENCE_PERCENT = "subtract_reference_percent"


class CooldownConditionReason(StrEnum):
    CHARGE_AVAILABLE = "charge_available"
    NO_AVAILABLE_CHARGE = "no_available_charge"


class CooldownMutationReason(StrEnum):
    NO_ACTIVE_RECOVERY = "no_active_recovery"
    NO_EFFECT = "no_effect"


class CooldownFactKind(StrEnum):
    STARTED = "started"
    CHARGE_RECOVERED = "charge_recovered"
    REDUCED = "reduced"
    RESET = "reset"
    CHAIN_COMPLETED = "chain_completed"
