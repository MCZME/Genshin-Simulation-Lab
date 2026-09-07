"""应用服务错误。"""


class ApplicationServiceError(Exception):
    """应用服务的基础错误。"""


class AnalysisPlanValidationError(ValueError):
    """分析节点计划不合法。details 逐项给出 node_id 与原因。"""

    def __init__(self, message: str, details=()) -> None:
        super().__init__(message)
        self.details = tuple(details)
