from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AttributeErrorDetail:
    code: str
    message: str


class AttributeSystemError(Exception):
    """属性系统结构化错误基类。"""

    code = "attribute_error"


class AttributeValidationError(AttributeSystemError, ValueError):
    code = "attribute_validation_error"


class UnknownAttributeError(AttributeSystemError, LookupError):
    code = "unknown_attribute"


class UnsupportedOwnerError(AttributeSystemError, ValueError):
    code = "unsupported_owner"


class MissingAttributeValueError(AttributeSystemError, LookupError):
    code = "missing_attribute_value"


class CircularDependencyError(AttributeSystemError, RuntimeError):
    code = "circular_dependency"


class InvalidModifierStageError(AttributeSystemError, ValueError):
    code = "invalid_modifier_stage"


class ProviderDependencyViolationError(AttributeSystemError, RuntimeError):
    code = "provider_dependency_violation"


class MissingQueryTargetError(AttributeSystemError, ValueError):
    code = "missing_query_target"


class ConflictingOverrideError(AttributeSystemError, RuntimeError):
    code = "conflicting_override"
