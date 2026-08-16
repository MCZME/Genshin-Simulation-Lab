"""应用层配置与输入模型通用错误。"""


class ConfigError(ValueError):
    """无效配置或输入的基础错误。"""


class ConfigFileError(ConfigError):
    """配置文件无法读取或解析。"""
