class CharacterAbilityConditionError(Exception):
    code = "character_ability_condition_error"


class CharacterAbilityConditionValidationError(CharacterAbilityConditionError, ValueError):
    code = "character_ability_condition_validation_error"


class CharacterAbilitySubjectMappingError(CharacterAbilityConditionError, ValueError):
    code = "character_ability_subject_mapping_error"


class CharacterAbilityConditionConflictError(CharacterAbilityConditionError):
    code = "character_ability_condition_conflict"
