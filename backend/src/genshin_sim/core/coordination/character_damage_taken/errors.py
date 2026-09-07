from __future__ import annotations


class CharacterDamageTakenError(Exception):
    """角色受伤协调错误基类。"""


class CharacterDamageTakenValidationError(CharacterDamageTakenError, ValueError):
    pass


class CharacterDamageTakenTargetError(CharacterDamageTakenValidationError):
    pass


class CharacterDamageTakenPlanConflictError(CharacterDamageTakenError):
    pass


class CharacterDamageTakenCommitError(CharacterDamageTakenError):
    pass


class CharacterDamageTakenReentrancyError(CharacterDamageTakenError):
    pass
