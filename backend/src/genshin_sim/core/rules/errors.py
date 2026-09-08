"""规则系统错误。"""


class RuleSystemError(Exception):
    """规则系统错误基类。"""


class DuplicateRuleKeyError(RuleSystemError):
    """注册中心出现重复规则 key。"""


class UnknownRuleKeyError(RuleSystemError):
    """激活了未注册的规则。"""


class DuplicateRuleTypeError(RuleSystemError):
    """多条规则产出同一规则类型。"""


class RuleValidationError(RuleSystemError):
    """规则激活或参数校验失败。"""
