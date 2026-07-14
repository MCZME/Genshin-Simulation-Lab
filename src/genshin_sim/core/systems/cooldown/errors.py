class CooldownError(Exception):
    code = "cooldown_error"


class CooldownValidationError(CooldownError, ValueError):
    code = "cooldown_validation_error"


class CooldownDefinitionNotFoundError(CooldownError, LookupError):
    code = "cooldown_definition_not_found"


class DuplicateCooldownDefinitionError(CooldownError, ValueError):
    code = "duplicate_cooldown_definition"


class CooldownRecordNotFoundError(CooldownError, LookupError):
    code = "cooldown_record_not_found"


class CooldownFrameRegressionError(CooldownError, ValueError):
    code = "cooldown_frame_regression"


class CooldownNotNormalizedError(CooldownError):
    code = "cooldown_not_normalized"


class StaleCooldownPlanError(CooldownError):
    code = "stale_cooldown_plan"


class DuplicateCooldownRequestError(CooldownError, ValueError):
    code = "duplicate_cooldown_request"


class CooldownDurationResolutionError(CooldownError, ValueError):
    code = "cooldown_duration_resolution_error"


class CooldownInvariantError(CooldownError, ValueError):
    code = "cooldown_invariant_error"


class CooldownReentrancyError(CooldownError):
    code = "cooldown_reentrancy_error"
