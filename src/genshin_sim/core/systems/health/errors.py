from __future__ import annotations


class HealthSystemError(Exception):
    """生命值系统结构化错误基类。"""

    code = "health_error"


class HealthValidationError(HealthSystemError, ValueError):
    code = "health_validation_error"


class CharacterHealthNotFoundError(HealthSystemError, LookupError):
    code = "character_health_not_found"


class InvalidMaxHealthError(HealthSystemError, ValueError):
    code = "invalid_max_health"


class InvalidCurrentHealthError(HealthSystemError, ValueError):
    code = "invalid_current_health"


class UnsupportedHealthSubjectError(HealthSystemError, ValueError):
    code = "unsupported_health_subject"
