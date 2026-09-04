"""应用层配置、输入模型与公开出口通用错误。"""

from collections.abc import Sequence
from typing import Any


class ConfigError(ValueError):
    """无效配置或输入的基础错误。"""


class ConfigFileError(ConfigError):
    """配置文件无法读取或解析。"""


class ApplicationError(Exception):
    """应用公开能力的基础错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        details: Sequence[Any] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = tuple(details)
