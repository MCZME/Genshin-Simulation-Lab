from __future__ import annotations

from dataclasses import dataclass


class BuffSystemError(Exception):
    code = "buff_system_error"


class BuffValidationError(BuffSystemError, ValueError):
    code = "buff_validation_error"


class BuffDefinitionError(BuffSystemError):
    code = "buff_definition_error"


class BuffDefinitionNotFoundError(BuffDefinitionError, LookupError):
    code = "buff_definition_not_found"


class BuffDefinitionConflictError(BuffDefinitionError, ValueError):
    code = "buff_definition_conflict"


class BuffModifierBindingError(BuffSystemError):
    code = "buff_modifier_binding_error"


class BuffApplicationConflictError(BuffSystemError):
    code = "buff_application_conflict"


class BuffInstanceNotFoundError(BuffSystemError, LookupError):
    code = "buff_instance_not_found"


class BuffPlanConflictError(BuffSystemError):
    code = "buff_plan_conflict"


class BuffReentrancyError(BuffSystemError):
    code = "buff_reentrancy_error"


class BuffImpactContractError(BuffSystemError):
    code = "buff_impact_contract_error"


@dataclass(frozen=True, slots=True)
class BuffErrorDetail:
    code: str
    message: str
