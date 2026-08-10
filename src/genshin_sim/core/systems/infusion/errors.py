from __future__ import annotations

from dataclasses import dataclass


class InfusionSystemError(Exception):
    code = "infusion_system_error"


class InfusionValidationError(InfusionSystemError, ValueError):
    code = "infusion_validation_error"


class InfusionDefinitionError(InfusionSystemError):
    code = "infusion_definition_error"


class InfusionDefinitionNotFoundError(InfusionDefinitionError, LookupError):
    code = "infusion_definition_not_found"


class InfusionDefinitionConflictError(InfusionDefinitionError, ValueError):
    code = "conflicting_infusion_definition"


class InfusionApplicationConflictError(InfusionSystemError):
    code = "infusion_application_conflict"


class InfusionInstanceNotFoundError(InfusionSystemError, LookupError):
    code = "infusion_source_not_found"


class InfusionPlanConflictError(InfusionSystemError):
    code = "infusion_commit_conflict"


class InfusionReentrancyError(InfusionSystemError):
    code = "infusion_reentrancy_error"


class InfusionImpactContractError(InfusionSystemError):
    code = "infusion_impact_contract_error"


class UnsupportedWeaponAuraRuleError(InfusionSystemError):
    code = "unsupported_weapon_aura_rule"


@dataclass(frozen=True, slots=True)
class InfusionErrorDetail:
    code: str
    message: str
