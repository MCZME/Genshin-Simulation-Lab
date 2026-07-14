from __future__ import annotations


class EnergySystemError(Exception):
    code = "energy_error"


class EnergyValidationError(EnergySystemError, ValueError):
    code = "energy_validation_error"


class CharacterEnergyNotFoundError(EnergySystemError, LookupError):
    code = "character_energy_not_found"


class UnsupportedEnergySubjectError(EnergySystemError, ValueError):
    code = "unsupported_energy_subject"


class UnsupportedEnergyResourceError(EnergySystemError, ValueError):
    code = "unsupported_energy_resource"


class UnsupportedEnergyElementError(EnergySystemError, ValueError):
    code = "unsupported_energy_element"


class UnsupportedEnergyOperationError(EnergySystemError, ValueError):
    code = "unsupported_energy_operation"


class InvalidEnergyAttributeError(EnergySystemError, ValueError):
    code = "invalid_energy_attribute"


class EnergyPlanConflictError(EnergySystemError):
    code = "energy_plan_conflict"


class EnergyReentrancyError(EnergySystemError):
    code = "energy_reentrancy_error"


class DuplicateEnergyRequestError(EnergySystemError):
    code = "duplicate_energy_request"


class EnergyPickupNotFoundError(EnergySystemError, LookupError):
    code = "energy_pickup_not_found"


class InsufficientEnergyAtSpendError(EnergySystemError):
    code = "insufficient_energy_at_spend"
